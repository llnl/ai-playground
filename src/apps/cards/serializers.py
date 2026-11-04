"""Translate card and profile models to and from REST API representations.

The API represents type-specific metadata as one nested profile object alongside
the shared card fields. This module validates the same model-level constraints
as the HTML form workflow and saves shared and nested records atomically.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import AgentProfile, Cards, MCPServerProfile, SkillProfile


class ValidatedModelSerializer(serializers.ModelSerializer):
    """Apply Django model validation to a proposed serializer state.

    Django REST Framework validates serializer fields but does not call a
    model's ``full_clean`` method automatically. This base class constructs the
    complete proposed model state—including unchanged fields during partial
    updates—and runs model validators before any data is written.
    """

    def validate(self, attrs: dict) -> dict:
        """Validate incoming attributes against the complete model state.

        For updates, omitted values are copied from the existing instance so
        model-level validation sees the resulting object rather than only the
        submitted fields. The parent ``card`` relation is excluded while a new
        nested profile is being validated because it is assigned during the
        enclosing card save.

        Args:
            attrs: Field values already converted and validated by DRF.

        Returns:
            The validated attributes, unchanged.

        Raises:
            serializers.ValidationError: If ``full_clean`` reports a model
                field or cross-field validation error.
        """
        attrs = super().validate(attrs)
        values = {
            field.name: getattr(self.instance, field.name)
            for field in self.Meta.model._meta.fields
            if self.instance is not None and field.name != "id"
        }
        values.update(attrs)
        candidate = self.Meta.model(**values)
        try:
            candidate.full_clean(exclude=["card"] if hasattr(candidate, "card_id") and not candidate.card_id else None)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            ) from error
        return attrs


class MCPServerProfileSerializer(ValidatedModelSerializer):
    """Serialize MCP server connection, capability, and tool metadata.

    The parent card relation is not accepted from clients. It is assigned by
    :class:`CardSerializer` after the shared card has been saved. Model
    validation requires either an endpoint URL or installation instructions.
    """

    class Meta:
        """Expose editable MCP fields while managing identity and card server-side."""

        model = MCPServerProfile
        exclude = ["id", "card"]


class AgentProfileSerializer(ValidatedModelSerializer):
    """Serialize agent purpose, task, model, and autonomy metadata.

    The parent card is assigned by :class:`CardSerializer`; clients provide
    only type-specific values. The model's required ``primary_purpose`` and
    list validators are enforced through :class:`ValidatedModelSerializer`.
    """

    class Meta:
        """Expose editable agent fields while managing identity and card server-side."""

        model = AgentProfile
        exclude = ["id", "card"]


class SkillProfileSerializer(ValidatedModelSerializer):
    """Serialize skill activation, compatibility, context, and I/O metadata.

    The parent card is assigned by :class:`CardSerializer`; clients provide
    only type-specific values. The model's required ``purpose`` and list
    validators are enforced through :class:`ValidatedModelSerializer`.
    """

    class Meta:
        """Expose editable skill fields while managing identity and card server-side."""

        model = SkillProfile
        exclude = ["id", "card"]


PROFILE_FIELDS = {
    Cards.ResourceType.MCP_SERVER: "mcp_server_profile",
    Cards.ResourceType.AGENT: "agent_profile",
    Cards.ResourceType.SKILL: "skill_profile",
}


class CardSerializer(serializers.ModelSerializer):
    """Serialize shared card metadata with exactly one matching nested profile.

    API clients select a ``resource_type`` and submit the corresponding nested
    field: ``mcp_server_profile``, ``agent_profile``, or ``skill_profile``. A
    profile is required when creating a card or changing its resource type.
    Partial updates that leave the type unchanged may omit profile data.

    ``owner`` and audit fields are read-only. The viewset supplies the
    authenticated owner during creation, while this serializer coordinates
    model validation and transactional writes for the card and profile.
    """

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    mcp_server_profile = MCPServerProfileSerializer(required=False, allow_null=True)
    agent_profile = AgentProfileSerializer(required=False, allow_null=True)
    skill_profile = SkillProfileSerializer(required=False, allow_null=True)

    class Meta:
        """Define shared, nested, and server-managed API fields."""

        model = Cards
        fields = [
            "id",
            "owner",
            "name",
            "short_description",
            "long_description",
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
            "logo",
            "mcp_server_profile",
            "agent_profile",
            "skill_profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "from_official_team", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        """Validate profile selection and the resulting shared card state.

        Nested profiles unrelated to the selected resource type are rejected.
        Creates and resource-type changes require the matching profile, while a
        normal partial update may rely on the profile already attached to the
        card. Shared model validators run against a candidate containing both
        submitted and unchanged values.

        Args:
            attrs: Shared and nested values already validated by DRF fields.

        Returns:
            The validated attributes, including nested profile data.

        Raises:
            serializers.ValidationError: If profile data does not match the
                selected resource type, a required profile is absent, or shared
                model validation fails.
        """
        attrs = super().validate(attrs)
        resource_type = attrs.get("resource_type", getattr(self.instance, "resource_type", None))
        supplied = {
            field: attrs[field] for field in PROFILE_FIELDS.values() if field in attrs and attrs[field] is not None
        }
        matching_field = PROFILE_FIELDS.get(resource_type)

        unrelated = [field for field in supplied if field != matching_field]
        if unrelated:
            raise serializers.ValidationError({field: "Profile does not match resource_type." for field in unrelated})

        changing_type = self.instance is not None and resource_type != self.instance.resource_type
        if self.instance is None or changing_type:
            if matching_field not in supplied:
                raise serializers.ValidationError(
                    {matching_field or "resource_type": "A matching profile is required."}
                )

        card_values = {
            field.name: getattr(self.instance, field.name)
            for field in Cards._meta.fields
            if self.instance is not None and field.name not in {"id", "owner"}
        }
        card_values.update({key: value for key, value in attrs.items() if key not in PROFILE_FIELDS.values()})
        candidate = Cards(**card_values)
        if self.instance is not None:
            candidate.owner = self.instance.owner
        try:
            candidate.full_clean(exclude=["owner"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> Cards:
        """Create a card and its matching profile in one transaction.

        Args:
            validated_data: Shared values plus one validated nested profile.
                The viewset also injects the authenticated ``owner`` here.

        Returns:
            The newly saved card with its profile available through the matching
            one-to-one relation.

        Raises:
            DjangoValidationError: If final model validation fails. The atomic
                transaction prevents a partial card or profile from remaining.
        """
        profile_data = self._pop_profiles(validated_data)
        card = Cards(**validated_data)
        card.full_clean()
        card.save()
        self._save_profile(card, profile_data)
        return card

    @transaction.atomic
    def update(self, instance: Cards, validated_data: dict) -> Cards:
        """Update shared metadata and update or replace its matching profile.

        When ``resource_type`` changes, all profiles attached to the card are
        removed before the newly selected profile is created. Otherwise,
        supplied nested values update the existing matching profile and omitted
        profile data leaves it unchanged.

        Args:
            instance: Existing card being updated.
            validated_data: Validated shared changes and optional nested profile
                values.

        Returns:
            The updated card instance.

        Raises:
            DjangoValidationError: If final card or profile model validation
                fails. The atomic transaction rolls back every related change.
        """
        profile_data = self._pop_profiles(validated_data)
        previous_type = instance.resource_type
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()

        if instance.resource_type != previous_type:
            for relation in PROFILE_FIELDS.values():
                profile = getattr(instance, relation, None)
                if profile is not None:
                    profile.delete()
        if profile_data:
            self._save_profile(instance, profile_data)
        return instance

    @staticmethod
    def _pop_profiles(validated_data: dict) -> dict:
        """Separate nested profile values from shared model values in place.

        Args:
            validated_data: Mutable serializer data containing shared fields and
                potentially one or more nested profile keys.

        Returns:
            A mapping of supplied non-null profile relation names to their
            validated nested values. Those keys are removed from
            ``validated_data`` so it can initialize or update ``Cards``.
        """
        return {
            field: validated_data.pop(field)
            for field in PROFILE_FIELDS.values()
            if field in validated_data and validated_data[field] is not None
        }

    @staticmethod
    def _save_profile(card: Cards, profile_data: dict) -> None:
        """Create or update the profile selected by the card's resource type.

        Args:
            card: Saved parent card whose ``resource_type`` selects the profile
                relation and model.
            profile_data: Mapping returned by :meth:`_pop_profiles`, containing
                validated values for the matching relation.

        Raises:
            KeyError: If matching nested profile data is absent. Serializer
                validation prevents this during creation and type changes.
            DjangoValidationError: If the completed profile violates model
                validation, including card/profile type consistency.
        """
        relation = PROFILE_FIELDS[card.resource_type]
        values = profile_data[relation]
        profile = getattr(card, relation, None)
        if profile is None:
            model = {
                "mcp_server_profile": MCPServerProfile,
                "agent_profile": AgentProfile,
                "skill_profile": SkillProfile,
            }[relation]
            profile = model(card=card, **values)
        else:
            for field, value in values.items():
                setattr(profile, field, value)
        profile.full_clean()
        profile.save()
