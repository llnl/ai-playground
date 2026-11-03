"""Validate and persist shared card data with type-specific profile data.

The shared and profile forms remain separate so registration interfaces can
show only fields relevant to the selected resource type. The save helper joins
their writes in one transaction and enforces the one-card/one-profile contract.
"""

from typing import Any, TypedDict

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.forms import formset_factory
from django.forms.formsets import BaseFormSet

from .models import AgentProfile, Cards, MCPServerProfile, SkillProfile


class OwnershipContact(TypedDict):
    """Represent one owner in the ``Cards.ownership_contacts`` JSON value."""

    owner_name: str
    owner_type: str
    contact_emails: list[str]
    institutions: list[str]


def _lines(value: object) -> list[str]:
    """Normalize a submitted list or delimited string into clean values.

    Commas and line breaks are accepted so the server-side fallback remains
    usable without JavaScript. Whitespace-only values are discarded.

    Args:
        value: A list, string, or empty value supplied by a Django form field.

    Returns:
        Stripped, non-empty strings in their submitted order.
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").replace(",", "\n").splitlines() if item.strip()]


class StringListField(forms.CharField):
    """Edit a JSON string list as one plain-text value per line."""

    widget = forms.Textarea(attrs={"rows": 3, "data-repeatable": "items"})

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize an optional field with line-oriented fallback guidance.

        Callers may override ``required`` or ``help_text``. The textarea is
        progressively enhanced into repeatable controls by ``card-form.js``.
        """
        kwargs.setdefault("required", False)
        kwargs.setdefault("help_text", "Enter one item per line.")
        super().__init__(*args, **kwargs)

    def prepare_value(self, value: object) -> object:
        """Convert a stored string list to editable newline-delimited text.

        Args:
            value: A model value or already prepared form value.

        Returns:
            Newline-delimited text for lists; all other values unchanged.
        """
        if isinstance(value, list):
            return "\n".join(value)
        return value

    def to_python(self, value: object) -> list[str]:
        """Convert submitted text into the list expected by JSON model fields.

        Args:
            value: Submitted textarea text, a list from a programmatic client,
                or an empty value.

        Returns:
            A normalized list of non-empty strings.

        Raises:
            ValidationError: If a mapping is submitted instead of a string list.
        """
        if isinstance(value, dict):
            raise ValidationError("Enter one item per line.")
        return _lines(value)


class ToolListField(StringListField):
    """Edit MCP tool objects without exposing raw JSON to users."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Configure the field for structured tool-row enhancement.

        The browser presents separate name and description controls. Their
        values are serialized into the hidden textarea as ``name | description``
        so the same server-side parser also supports no-JavaScript submissions.
        """
        kwargs.setdefault("help_text", "Add each tool with a name and description.")
        super().__init__(*args, **kwargs)
        self.widget.attrs["data-repeatable"] = "tools"

    def prepare_value(self, value: object) -> object:
        """Serialize stored tool objects for the textarea fallback.

        Args:
            value: A list of tool dictionaries or an already prepared value.

        Returns:
            One ``name | description`` entry per line for lists, otherwise the
            original value.
        """
        if isinstance(value, list):
            lines = []
            for tool in value:
                if isinstance(tool, dict):
                    name = tool.get("name", "")
                    description = tool.get("description", "")
                    lines.append(f"{name} | {description}".rstrip(" |"))
            return "\n".join(lines)
        return value

    def to_python(self, value: object) -> list[dict[str, str]]:
        """Convert compact tool lines into JSON-compatible dictionaries.

        Args:
            value: Submitted text containing one tool per line.

        Returns:
            Tool dictionaries containing a required-by-shape ``name`` key and
            an optional ``description`` key.
        """
        tools: list[dict[str, str]] = []
        for line in _lines(value):
            name, separator, description = line.partition("|")
            tool = {"name": name.strip()}
            if separator and description.strip():
                tool["description"] = description.strip()
            tools.append(tool)
        return tools


class OwnershipForm(forms.Form):
    """Collect one organizational owner for the nested JSON contract."""

    owner_name = forms.CharField(
        label="Team, group, or individual name",
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Example: Applied AI Team"}),
    )
    owner_type = forms.ChoiceField(
        label="Owner type",
        choices=(("team", "Team"), ("group", "Group"), ("individual", "Individual")),
    )
    contact_emails = forms.CharField(
        label="Contact emails",
        widget=forms.Textarea(
            attrs={"rows": 2, "data-repeatable": "emails", "placeholder": "Example: ai-team@example.org"}
        ),
        help_text="Enter one email address per line.",
    )
    institutions = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "data-repeatable": "institutions", "placeholder": "Example: Example Laboratory"}
        ),
        help_text="Enter one institution per line.",
    )

    def clean_contact_emails(self) -> list[str]:
        """Normalize and validate all email addresses for this owner.

        Returns:
            Valid email addresses in submitted order.

        Raises:
            ValidationError: If one or more addresses fail Django's email
                validator. All invalid addresses are reported together.
        """
        emails = _lines(self.cleaned_data["contact_emails"])
        errors: list[str] = []
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                errors.append(f"{email} is not a valid email address.")
        if errors:
            raise ValidationError(errors)
        return emails

    def clean_institutions(self) -> list[str]:
        """Return normalized institution names for ownership JSON storage."""
        return _lines(self.cleaned_data.get("institutions"))


OwnershipFormSet = formset_factory(OwnershipForm, extra=0, can_delete=True, min_num=1, validate_min=True)


def ownership_initial(contacts: list[OwnershipContact] | None) -> list[dict[str, str]]:
    """Convert ownership JSON into initial values for the owner formset.

    Args:
        contacts: Stored organizational owners, or ``None`` for a new card.

    Returns:
        Form rows with email and institution lists joined into textarea values.
    """
    return [
        {
            "owner_name": contact.get("owner_name", ""),
            "owner_type": contact.get("owner_type", "team"),
            "contact_emails": "\n".join(contact.get("contact_emails", [])),
            "institutions": "\n".join(contact.get("institutions", [])),
        }
        for contact in (contacts or [])
        if isinstance(contact, dict)
    ]


def ownership_contacts_from_formset(formset: BaseFormSet) -> list[OwnershipContact]:
    """Build model-ready ownership JSON from a validated owner formset.

    Args:
        formset: A bound formset whose ``is_valid()`` method has returned true.

    Returns:
        Non-deleted owner rows using the keys required by the model validator.
    """
    return [
        {
            "owner_name": form.cleaned_data["owner_name"],
            "owner_type": form.cleaned_data["owner_type"],
            "contact_emails": form.cleaned_data["contact_emails"],
            "institutions": form.cleaned_data["institutions"],
        }
        for form in formset.forms
        if form.cleaned_data and not form.cleaned_data.get("DELETE")
    ]


class CardForm(forms.ModelForm):
    """Collect and validate metadata shared by all resource types.

    Model fields are listed explicitly to prevent internal ownership and audit
    fields from becoming user-editable. Legacy fields are also rejected rather
    than silently ignored, which makes stale clients fail clearly.

    Attributes:
        obsolete_fields: Legacy request keys that cause form-wide validation
            errors when submitted.
        tags: Optional repeatable string-list field converted to the JSON list
            stored by :class:`Cards`.
        name: Human-readable resource name.
        short_description: Concise summary used in directory results.
        long_description: Detailed explanation shown on the resource page.
        resource_type: Selected MCP server, agent, or skill classification.
        domain: Single primary subject area for the resource.
        ownership_contacts: Model field populated server-side from the separate
            ownership formset rather than rendered directly by this form.
        status: Resource lifecycle state.
        version: Optional release or metadata version.
        documentation_url: Optional user-facing documentation URL.
        repository_url: Optional source repository URL.
        license: Optional license name or identifier.
        logo: Optional uploaded PNG, JPEG, or WebP image.
    """

    obsolete_fields = {"maintainers", "institution", "category", "internal_url", "external_url", "tools"}
    tags = StringListField()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Apply registration-specific labels, examples, and help text.

        The explicit field configuration keeps presentation guidance in the
        form layer while the model remains the source of persistence rules.
        """
        super().__init__(*args, **kwargs)
        field_content = {
            "name": ("Resource name", "Example: Vertex CFD MCP"),
            "short_description": ("Short description", "A concise summary shown in directory results."),
            "long_description": ("Long description", "Explain what the resource does and who it helps."),
            "domain": ("Primary domain", "Example: Scientific computing"),
            "version": ("Current version", "Example: 1.4.2"),
            "license": ("License", "Example: MIT or Apache-2.0"),
            "documentation_url": ("Documentation URL", "https://documentation.example.org/resource"),
            "repository_url": ("Repository URL", "https://git.example.org/project/repository"),
        }
        for name, (label, placeholder) in field_content.items():
            self.fields[name].label = label
            self.fields[name].widget.attrs["placeholder"] = placeholder
        self.fields["resource_type"].label = "Resource type"
        self.fields[
            "domain"
        ].help_text = (
            "Choose the main subject area for this resource. Use tags for additional domains or related topics."
        )
        self.fields["tags"].widget.attrs["placeholder"] = "Example: simulation automation"
        self.fields["tags"].widget.attrs["data-repeatable"] = "tags"
        self.fields["logo"].label = "Logo or icon"
        self.fields["logo"].help_text = "Optional. PNG, JPG, JPEG, or WebP; maximum size 5 MB."

    class Meta:
        """Expose only fields belonging to the public shared metadata contract."""

        model = Cards
        fields = [
            "name",
            "short_description",
            "long_description",
            "resource_type",
            "domain",
            "tags",
            "ownership_contacts",
            "status",
            "version",
            "documentation_url",
            "repository_url",
            "license",
            "logo",
        ]

    def clean(self) -> dict[str, Any]:
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

    Attributes:
        expected_resource_type: Canonical :class:`Cards.ResourceType` value that
            the attached card must use. Each concrete profile form overrides it.
        instance: Profile model instance being edited, or an unsaved instance
            during resource creation or a resource-type change.
    """

    expected_resource_type: str

    def clean(self) -> dict[str, Any]:
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
    """Collect MCP server metadata while assigning ``card`` server-side.

    Attributes:
        expected_resource_type: Always ``mcp_server`` for consistency checks.
        field_order: Presentation order that places the conditional connection
            fields first and the full-width tools control last.
        endpoint_url: Optional remote MCP endpoint; required when installation
            instructions are absent.
        installation_instructions: Optional local setup or execution guidance;
            required when an endpoint URL is absent.
        protocol_version: MCP protocol version implemented by the server.
        transport: Communication transport such as stdio or streamable HTTP.
        deployment_mode: How the server is hosted or executed.
        authentication_method: Authentication mechanism expected from clients.
        runtime_requirements: Repeatable list of runtimes and prerequisites.
        capabilities: Repeatable list of MCP or server capabilities.
        required_permissions: Repeatable list of filesystem, network, or service
            permissions required by the server.
        tools: Repeatable structured tool entries containing names and optional
            descriptions, stored as JSON objects.
    """

    expected_resource_type = Cards.ResourceType.MCP_SERVER
    field_order = [
        "endpoint_url",
        "installation_instructions",
        "protocol_version",
        "transport",
        "deployment_mode",
        "authentication_method",
        "runtime_requirements",
        "capabilities",
        "required_permissions",
        "tools",
    ]
    runtime_requirements = StringListField()
    capabilities = StringListField()
    tools = ToolListField()
    required_permissions = StringListField()

    class Meta:
        """Expose every MCP profile field except its managed card relation."""

        model = MCPServerProfile
        exclude = ["card"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Add MCP examples and explain its conditional connection fields.

        Neither connection field is independently required: an MCP server must
        provide an endpoint URL, installation instructions, or both. Model
        validation enforces that rule after the form has parsed both values.
        """
        super().__init__(*args, **kwargs)
        placeholders = {
            "endpoint_url": "Example: https://mcp.example.org/server",
            "installation_instructions": (
                "Example: Run uvx example-mcp-server, then add it to your MCP client configuration."
            ),
            "protocol_version": "Example: 2025-06-18",
            "transport": "Example: stdio or streamable HTTP",
            "deployment_mode": "Example: Local, remote, or containerized",
            "authentication_method": "Example: OAuth 2.0, API key, or none",
            "runtime_requirements": "Example: Python 3.12 or Node.js 22",
            "capabilities": "Example: Tools, resources, or prompts",
            "required_permissions": "Example: Read access to the project directory",
            "tools": "Example: run_simulation | Runs a simulation from an input file",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder
        self.fields["endpoint_url"].label = "Endpoint URL"
        self.fields["endpoint_url"].help_text = "Required when installation instructions are not provided."
        self.fields["installation_instructions"].label = "Installation instructions"
        self.fields["installation_instructions"].help_text = "Required when an endpoint URL is not provided."


class AgentProfileForm(ProfileForm):
    """Collect agent metadata while assigning ``card`` server-side.

    Attributes:
        expected_resource_type: Always ``agent`` for consistency checks.
        agent_type: Architectural or operational agent classification.
        primary_purpose: Required summary of the agent's intended outcome.
        supported_tasks: Repeatable list of concrete, tested jobs the agent can
            perform.
        primary_model: Main model used by the agent.
        framework: Agent framework or implementation stack.
        interface: User or system interaction method.
        deployment_mode: How the agent is hosted or executed.
        inputs: Repeatable list of accepted values or artifacts.
        outputs: Repeatable list of produced results or artifacts.
        tool_dependencies: Repeatable list of external tools, APIs, or services.
        autonomy_level: Degree to which the agent acts without intervention.
        human_approval_requirements: Actions or decisions requiring human review.
        known_limitations: Documented constraints and unsupported scenarios.
    """

    expected_resource_type = Cards.ResourceType.AGENT
    supported_tasks = StringListField()
    inputs = StringListField()
    outputs = StringListField()
    tool_dependencies = StringListField(label="Integrations and tool dependencies")

    class Meta:
        """Expose every agent profile field except its managed card relation."""

        model = AgentProfile
        exclude = ["card"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Attach concrete examples to every agent-specific text control."""
        super().__init__(*args, **kwargs)
        placeholders = {
            "agent_type": "Example: Conversational, workflow, or coding agent",
            "primary_purpose": "Example: Submit and monitor scientific computing jobs",
            "supported_tasks": "Example: Generate scheduler submission scripts",
            "primary_model": "Example: Claude Sonnet 4.5",
            "framework": "Example: LangGraph or OpenAI Agents SDK",
            "interface": "Example: Web application, chat, CLI, or API",
            "deployment_mode": "Example: Hosted service, local, or containerized",
            "inputs": "Example: Natural-language request or simulation input file",
            "outputs": "Example: Scheduler job ID or validation report",
            "tool_dependencies": "Example: Slurm API or filesystem tools",
            "autonomy_level": "Example: Suggests actions; user approves execution",
            "human_approval_requirements": "Example: Approval is required before submitting or canceling jobs.",
            "known_limitations": "Example: Does not support interactive or multi-node GPU jobs.",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder


class SkillProfileForm(ProfileForm):
    """Collect skill metadata while assigning ``card`` server-side.

    Attributes:
        expected_resource_type: Always ``skill`` for consistency checks.
        skill_format: Packaging or file format used to define the skill.
        purpose: Required explanation of what the skill enables an agent to do.
        activation_method: How the skill is loaded, selected, or invoked.
        trigger_phrases: Repeatable list of requests that should activate it.
        compatible_agents: Repeatable list of supported agents or agent classes.
        compatible_platforms: Repeatable list of supported runtimes or platforms.
        required_context: Repeatable list of information needed before use.
        dependencies: Repeatable list of packages, tools, services, or skills.
        inputs: Repeatable list of expected values or artifacts.
        outputs: Repeatable list of values or artifacts produced by the skill.
        constraints: Repeatable list of restrictions and unsupported scenarios.
        examples: Repeatable list of example requests or usage scenarios.
    """

    expected_resource_type = Cards.ResourceType.SKILL
    trigger_phrases = StringListField()
    compatible_agents = StringListField()
    compatible_platforms = StringListField()
    required_context = StringListField()
    dependencies = StringListField()
    inputs = StringListField()
    outputs = StringListField()
    constraints = StringListField()
    examples = StringListField()

    class Meta:
        """Expose every skill profile field except its managed card relation."""

        model = SkillProfile
        exclude = ["card"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Attach concrete examples to every skill-specific text control."""
        super().__init__(*args, **kwargs)
        placeholders = {
            "skill_format": "Example: SKILL.md or prompt package",
            "purpose": "Example: Teach an agent to validate simulation input files",
            "activation_method": "Example: Automatically selected from the user request",
            "trigger_phrases": "Example: Validate this simulation input",
            "compatible_agents": "Example: OpenCode or Claude Code",
            "compatible_platforms": "Example: Linux or macOS",
            "required_context": "Example: Simulation software version",
            "dependencies": "Example: Python package or command-line tool",
            "inputs": "Example: Input file path",
            "outputs": "Example: Validation report",
            "constraints": "Example: Supports version 3 input files only",
            "examples": "Example: Check model.inp before submitting the job",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder


PROFILE_FORMS = {
    Cards.ResourceType.MCP_SERVER: MCPServerProfileForm,
    Cards.ResourceType.AGENT: AgentProfileForm,
    Cards.ResourceType.SKILL: SkillProfileForm,
}


@transaction.atomic
def save_card_with_profile(card_form: CardForm, profile_form: ProfileForm, owner: Any | None = None) -> Cards:
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
