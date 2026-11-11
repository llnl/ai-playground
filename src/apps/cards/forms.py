"""Validate and persist shared card data with type-specific profile data.

The shared and profile forms remain separate so registration interfaces can
show only fields relevant to the selected resource type. The save helper joins
their writes in one transaction and enforces the one-card/one-profile contract.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AgentProfile, Cards, MCPServerProfile, SkillProfile


class CardForm(forms.ModelForm):
    """Collect and validate metadata shared by all resource types.

    Model fields are listed explicitly to prevent internal ownership and audit
    fields from becoming user-editable. Legacy fields are also rejected rather
    than silently ignored, which makes stale clients fail clearly.
    """

    obsolete_fields = {"maintainers", "institution", "category", "internal_url", "external_url", "tools"}

    class Meta:
        """Expose only fields belonging to the public shared metadata contract."""

        model = Cards
        fields = [
            "name",
            "description",
            "resource_type",
            "domain",
            "tags",
            "ownership_contacts",
            "from_official_team",
            "status",
            "version",
            "documentation_url",
            "repository_url",
            "license",
            "last_verified",
            "logo_url",
        ]
        widgets = {"last_verified": forms.DateInput(attrs={"type": "date"})}

    def clean(self) -> dict:
        """Reject submitted keys removed from the final metadata contract.

        Returns:
            The shared field values cleaned by ``ModelForm``.

        Raises:
            ValidationError: If the submitted payload contains any recognized
                legacy field name.
        """
        cleaned_data = super().clean()
        submitted_obsolete_fields = self.obsolete_fields.intersection(self.data)
        if submitted_obsolete_fields:
            names = ", ".join(sorted(submitted_obsolete_fields))
            raise ValidationError(f"Obsolete fields are not accepted: {names}.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    """Provide resource-type consistency validation for profile forms.

    On updates, the form instance may already reference a card. In that case,
    this form catches a type mismatch before the transactional save helper runs.
    Creation forms receive their card only during the save operation and are
    checked by :func:`save_card_with_profile` instead.
    """

    expected_resource_type: str

    def clean(self) -> dict:
        """Validate the type of a card already attached to the form instance.

        Returns:
            The profile field values cleaned by ``ModelForm``.

        Raises:
            ValidationError: If an existing profile instance belongs to a card
                with a different resource type.
        """
        cleaned_data = super().clean()
        card = self.instance.card if self.instance.card_id else None
        if card and card.resource_type != self.expected_resource_type:
            raise ValidationError("Profile type must match the card resource type.")
        return cleaned_data


class MCPServerProfileForm(ProfileForm):
    """Collect MCP server metadata while assigning ``card`` server-side."""

    expected_resource_type = Cards.ResourceType.MCP_SERVER

    class Meta:
        """Expose every MCP profile field except its managed card relation."""

        model = MCPServerProfile
        exclude = ["card"]


class AgentProfileForm(ProfileForm):
    """Collect agent metadata while assigning ``card`` server-side."""

    expected_resource_type = Cards.ResourceType.AGENT

    class Meta:
        """Expose every agent profile field except its managed card relation."""

        model = AgentProfile
        exclude = ["card"]


class SkillProfileForm(ProfileForm):
    """Collect skill metadata while assigning ``card`` server-side."""

    expected_resource_type = Cards.ResourceType.SKILL

    class Meta:
        """Expose every skill profile field except its managed card relation."""

        model = SkillProfile
        exclude = ["card"]


PROFILE_FORMS = {
    Cards.ResourceType.MCP_SERVER: MCPServerProfileForm,
    Cards.ResourceType.AGENT: AgentProfileForm,
    Cards.ResourceType.SKILL: SkillProfileForm,
}


@transaction.atomic
def save_card_with_profile(card_form: CardForm, profile_form: ProfileForm, owner=None) -> Cards:
    """Save shared metadata and exactly one matching profile atomically.

    The helper supports both creation and update. When an update changes the
    resource type, any old non-matching profile is removed before the new one is
    saved. Full model validation runs on both objects inside the transaction, so
    any failure rolls back all database changes.

    Args:
        card_form: Bound shared-metadata form, optionally containing an existing
            card instance for updates.
        profile_form: Bound form for the resource type selected by
            ``card_form``.
        owner: Optional authenticated Django user to assign on creation. When
            omitted, an existing card's owner remains unchanged.

    Returns:
        The saved card with its matching profile persisted.

    Raises:
        ValueError: If either form has not validated successfully.
        ValidationError: If the profile form type differs from the selected
            resource type or full model validation fails.
    """
    if not card_form.is_valid() or not profile_form.is_valid():
        raise ValueError("Both forms must be valid before saving.")

    resource_type = card_form.cleaned_data["resource_type"]
    if profile_form.expected_resource_type != resource_type:
        raise ValidationError("Profile type must match the card resource type.")

    card = card_form.save(commit=False)
    if owner is not None:
        card.owner = owner
    card.full_clean()
    card.save()

    # Updates may change type, so remove every non-matching profile.
    for relation in ("mcp_server_profile", "agent_profile", "skill_profile"):
        existing_profile = getattr(card, relation, None)
        if existing_profile and existing_profile.expected_resource_type != resource_type:
            existing_profile.delete()

    profile = profile_form.save(commit=False)
    profile.card = card
    profile.full_clean()
    profile.save()
    return card
