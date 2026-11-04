"""Persist catalog resources, type-specific metadata, and usage metrics.

The :class:`Cards` model owns metadata shared by every catalog resource. Each
card is extended by exactly one one-to-one profile whose model corresponds to
the card's ``resource_type``. Validators in this module enforce the structures
stored in JSON fields before model or form data is saved.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models
from django.urls import reverse


def validate_string_list(value: object) -> None:
    """Validate a JSON value as a list containing only non-empty strings.

    Args:
        value: Deserialized value supplied to a JSON model or form field.

    Raises:
        ValidationError: If ``value`` is not a list or contains a non-string
            or whitespace-only item.
    """
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError("Enter a list of non-empty strings.")


def validate_object_list(value: object) -> None:
    """Validate a JSON value as a list of JSON objects.

    This validator checks the outer shape only. Individual fields within each
    object may be validated separately as the MCP tool contract evolves.

    Args:
        value: Deserialized value supplied to a JSON model or form field.

    Raises:
        ValidationError: If ``value`` is not a list or any item is not a
            dictionary.
    """
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValidationError("Enter a list of objects.")


def validate_ownership_contacts(value: object) -> None:
    """Validate the complete organizational ownership structure.

    At least one owner is required. Every owner must provide a non-empty name,
    one of the supported owner types, and at least one valid contact email.
    Institutions are optional, but when present they must be non-empty strings.
    All discovered errors are accumulated so a caller can correct multiple
    ownership entries in one validation cycle.

    Args:
        value: Deserialized JSON value containing ownership dictionaries.

    Raises:
        ValidationError: If the collection is empty, has the wrong shape, or
            contains invalid ownership or contact data.
    """
    if not isinstance(value, list) or not value:
        raise ValidationError("Add at least one owner.")

    email_validator = EmailValidator()
    errors = []
    allowed_types = {"team", "group", "individual"}
    for index, owner in enumerate(value, start=1):
        if not isinstance(owner, dict):
            errors.append(f"Owner {index} must be an object.")
            continue
        if not isinstance(owner.get("owner_name"), str) or not owner["owner_name"].strip():
            errors.append(f"Owner {index} must have a name.")
        if owner.get("owner_type") not in allowed_types:
            errors.append(f"Owner {index} must have a valid owner type.")

        emails = owner.get("contact_emails")
        if not isinstance(emails, list) or not emails:
            errors.append(f"Owner {index} must have at least one contact email.")
        else:
            for email in emails:
                try:
                    email_validator(email)
                except (ValidationError, TypeError):
                    errors.append(f"Owner {index} contains an invalid contact email.")

        institutions = owner.get("institutions", [])
        if not isinstance(institutions, list) or any(
            not isinstance(institution, str) or not institution.strip() for institution in institutions
        ):
            errors.append(f"Owner {index} institutions must be a list of non-empty strings.")

    if errors:
        raise ValidationError(errors)


class Cards(models.Model):
    """Store metadata shared by every discoverable catalog resource.

    ``owner`` identifies the Django user responsible for the record and is used
    for authorization. ``ownership_contacts`` is separate display metadata that
    identifies the teams, groups, or individuals responsible for the resource;
    its email addresses also grant edit and delete access. Type-specific fields
    live on one of the profile models rather than on this shared table.

    Fields:
        owner: Authenticated Django user who submitted or owns the record for
            authorization purposes. Deleting that user leaves the card intact.
        name: Human-readable resource name displayed throughout the catalog.
        description: General explanation of what the resource is and does.
        resource_type: Canonical type that selects the required MCP server,
            agent, or skill profile.
        domain: Broad subject area or application domain. This remains free text
            so the catalog taxonomy can evolve.
        tags: Optional list of non-empty strings used for discovery and search.
        ownership_contacts: Required organizational owners with owner types,
            contact email addresses, and optional institutions.
        from_official_team: Whether the resource comes from a team recognized as
            official by the catalog.
        status: Current lifecycle state; defaults to ``active``.
        version: Optional release or metadata version supplied by the owner.
        documentation_url: Optional URL for user-facing documentation.
        repository_url: Optional URL for the source-code repository.
        license: Optional license name or identifier governing resource use.
        last_verified: Optional date when the resource or its metadata was last
            checked.
        logo_url: Optional URL for an image representing the resource.
        created_at: Timestamp automatically recorded when the card is created.
        updated_at: Timestamp automatically refreshed whenever the card is saved.

    TODO: need to figure out a way to allow multiple owners to edit a card without
    creating a new user for each owner. This is a temporary solution until we have
    a better way to handle multiple owners. Should probably talk with Zeke about this.
    """

    class ResourceType(models.TextChoices):
        """Canonical resource types used to select the matching profile."""

        MCP_SERVER = "mcp_server", "MCP Server"
        AGENT = "agent", "Agent"
        SKILL = "skill", "Skill"

    class Status(models.TextChoices):
        """Supported lifecycle states displayed for catalog resources."""

        EXPERIMENTAL = "experimental", "Experimental"
        BETA = "beta", "Beta"
        ACTIVE = "active", "Active"
        DEPRECATED = "deprecated", "Deprecated"
        ARCHIVED = "archived", "Archived"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cards",
    )
    name = models.CharField(max_length=100)
    description = models.TextField()
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    domain = models.CharField(max_length=200)
    tags = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    ownership_contacts = models.JSONField(default=list, validators=[validate_ownership_contacts])
    from_official_team = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    version = models.CharField(max_length=100, blank=True)
    documentation_url = models.URLField(blank=True)
    repository_url = models.URLField(blank=True)
    license = models.CharField(max_length=100, blank=True)
    last_verified = models.DateField(null=True, blank=True)
    logo_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        """Return the human-readable card name used by Django and admin."""
        return self.name

    @property
    def contact_emails(self) -> list[str]:
        """Flatten contact emails from every organizational owner.

        Returns:
            Email addresses in ownership-entry order. Malformed non-dictionary
            entries and non-string email values are ignored defensively.
        """
        return [
            email
            for contact in self.ownership_contacts
            if isinstance(contact, dict)
            for email in contact.get("contact_emails", [])
            if isinstance(email, str)
        ]

    @property
    def maintainer_emails(self) -> list[str]:
        """Return contact emails under the legacy template-facing property.

        This alias is limited to permission rendering in templates while those
        templates transition from maintainer terminology to ownership contacts.

        TODO: remove this before the 1.0 release once all templates have been updated.

        Returns:
            The same flattened list as :attr:`contact_emails`.
        """
        return self.contact_emails

    def get_profile(self) -> "MCPServerProfile | AgentProfile | SkillProfile | None":
        """Return the profile relation selected by ``resource_type``.

        Returns:
            The matching MCP server, agent, or skill profile. ``None`` is
            returned when the resource type is unsupported or the expected
            one-to-one relation has not been created.
        """
        relation = {
            self.ResourceType.MCP_SERVER: "mcp_server_profile",
            self.ResourceType.AGENT: "agent_profile",
            self.ResourceType.SKILL: "skill_profile",
        }.get(self.resource_type)
        return getattr(self, relation, None) if relation else None

    def has_type_profile(self) -> bool:
        """Check that exactly one profile exists and matches ``resource_type``.

        Returns:
            ``True`` only when no unrelated profile exists and
            :meth:`get_profile` resolves to the single attached profile.
        """
        profile_names = ("mcp_server_profile", "agent_profile", "skill_profile")
        profiles = [getattr(self, name, None) for name in profile_names]
        return sum(profile is not None for profile in profiles) == 1 and self.get_profile() is not None

    def get_absolute_url(self) -> str:
        """Return the canonical detail URL used after successful form saves."""
        return reverse("cards:card_detail", kwargs={"pk": self.pk})


class TypeProfile(models.Model):
    """Provide consistency validation shared by all profile models.

    Subclasses declare ``expected_resource_type`` and a one-to-one ``card``
    relation. The abstract model prevents mismatched or duplicate profile types
    from passing application-level model validation.
    """

    expected_resource_type: str

    class Meta:
        """Mark the shared profile behavior as abstract."""

        abstract = True

    def clean(self) -> None:
        """Ensure this is the card's only profile and has the matching type.

        Raises:
            ValidationError: If the card's ``resource_type`` differs from the
                subclass's ``expected_resource_type``, or another profile model
                is already attached to the card.
        """
        super().clean()
        if self.card_id and self.card.resource_type != self.expected_resource_type:
            raise ValidationError({"card": "Profile type must match the card resource type."})
        if self.card_id:
            profile_relations = ("mcp_server_profile", "agent_profile", "skill_profile")
            other_profiles = [
                profile
                for relation in profile_relations
                if (profile := getattr(self.card, relation, None)) is not None and profile.pk != self.pk
            ]
            if other_profiles:
                raise ValidationError({"card": "A card can have only one type-specific profile."})


class MCPServerProfile(TypeProfile):
    """Store protocol, deployment, capability, and tool metadata for an MCP server.

    Fields:
        card: The shared card extended by this profile. Its resource type must
            be ``mcp_server``.
        protocol_version: Version of the Model Context Protocol implemented by
            the server.
        transport: Communication transport supported by the server, such as
            ``stdio`` or streamable HTTP.
        deployment_mode: How the server is operated, such as local, remote, or
            containerized deployment.
        endpoint_url: Network endpoint used to connect to a remotely deployed
            server.
        installation_instructions: Human-readable setup steps for servers that
            users install or run themselves.
        authentication_method: Authentication mechanism clients must use when
            connecting to the server.
        runtime_requirements: Runtimes, operating-system constraints, or other
            prerequisites needed to operate the server.
        capabilities: MCP capabilities or broader features exposed by the
            server.
        tools: Structured descriptions of tools exposed by the server. Each
            list item is stored as a JSON object.
        required_permissions: Filesystem, network, service, or other permissions
            required to run or use the server.

    The one-to-one ``card`` relation is required. At least one usable connection
    path must also be supplied through ``endpoint_url`` or
    ``installation_instructions``; the remaining fields are optional.
    """

    expected_resource_type = Cards.ResourceType.MCP_SERVER
    card = models.OneToOneField(Cards, on_delete=models.CASCADE, related_name="mcp_server_profile")
    protocol_version = models.CharField(max_length=100, blank=True)
    transport = models.CharField(max_length=100, blank=True)
    deployment_mode = models.CharField(max_length=100, blank=True)
    endpoint_url = models.URLField(blank=True)
    installation_instructions = models.TextField(blank=True)
    authentication_method = models.CharField(max_length=200, blank=True)
    runtime_requirements = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    capabilities = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    tools = models.JSONField(default=list, blank=True, validators=[validate_object_list])
    required_permissions = models.JSONField(default=list, blank=True, validators=[validate_string_list])

    def clean(self) -> None:
        """Require a remote endpoint or instructions for running the server.

        A remotely hosted server may provide only ``endpoint_url``, while a
        locally operated server may provide only ``installation_instructions``.
        Requiring one rather than both supports either deployment pattern.

        Raises:
            ValidationError: If neither connection path is provided, or if the
                shared profile consistency validation fails.
        """
        super().clean()
        if not self.endpoint_url and not self.installation_instructions.strip():
            raise ValidationError("Provide an endpoint URL or installation instructions for the MCP server.")

    def __str__(self) -> str:
        """Return a label that identifies this as the card's MCP profile."""
        return f"MCP server profile: {self.card}"


class AgentProfile(TypeProfile):
    """Store purpose, task, model, interface, and autonomy metadata for an agent.

    Fields:
        card: The shared card extended by this profile. Its resource type must
            be ``agent``.
        agent_type: Architectural or operational classification of the agent.
        primary_purpose: Required summary of the outcome the agent is designed
            to achieve.
        supported_tasks: Concrete jobs the agent is designed and tested to
            perform, rather than broad domains or topical tags.
        primary_model: Main language, reasoning, or other model used by the
            agent.
        framework: Agent framework or software stack used by the implementation.
        interface: How users or systems interact with the agent, such as a CLI,
            web application, chat interface, or API.
        deployment_mode: How the agent is hosted or executed.
        inputs: Accepted input types or expected input values.
        outputs: Results or artifacts produced by the agent.
        tool_dependencies: External tools, APIs, or services the agent relies on.
        autonomy_level: Degree to which the agent can act without intervention.
        human_approval_requirements: Decisions or actions that require explicit
            human review or approval.
        known_limitations: Documented constraints, unsupported scenarios, or
            reliability limitations.

    ``primary_purpose`` and the one-to-one ``card`` relation are required. All
    other agent-specific fields are optional in the initial metadata contract.
    """

    expected_resource_type = Cards.ResourceType.AGENT
    card = models.OneToOneField(Cards, on_delete=models.CASCADE, related_name="agent_profile")
    agent_type = models.CharField(max_length=100, blank=True)
    primary_purpose = models.TextField()
    supported_tasks = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    primary_model = models.CharField(max_length=200, blank=True)
    framework = models.CharField(max_length=200, blank=True)
    interface = models.CharField(max_length=200, blank=True)
    deployment_mode = models.CharField(max_length=100, blank=True)
    inputs = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    outputs = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    tool_dependencies = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    autonomy_level = models.CharField(max_length=100, blank=True)
    human_approval_requirements = models.TextField(blank=True)
    known_limitations = models.TextField(blank=True)

    def __str__(self) -> str:
        """Return a label that identifies this as the card's agent profile."""
        return f"Agent profile: {self.card}"


class SkillProfile(TypeProfile):
    """Store activation, compatibility, context, and I/O metadata for a skill.

    Fields:
        card: The shared card extended by this profile. Its resource type must
            be ``skill``.
        skill_format: Packaging or file format used to define the skill.
        purpose: Required explanation of what the skill enables an agent to do.
        activation_method: How an agent or user loads, invokes, or selects the
            skill.
        trigger_phrases: Example phrases or request patterns that should activate
            the skill.
        compatible_agents: Agents or agent classes known to support the skill.
        compatible_platforms: Runtimes or platforms on which the skill can be
            used.
        required_context: Information that must be available before the skill
            can be used successfully.
        dependencies: Packages, tools, services, or other skills required by the
            skill.
        inputs: Values or artifacts the skill expects to receive.
        outputs: Values or artifacts the skill produces.
        constraints: Operational restrictions, assumptions, or unsupported
            scenarios.
        examples: Example requests or usage scenarios demonstrating the skill.

    ``purpose`` and the one-to-one ``card`` relation are required. All other
    skill-specific fields are optional in the initial metadata contract.
    """

    expected_resource_type = Cards.ResourceType.SKILL
    card = models.OneToOneField(Cards, on_delete=models.CASCADE, related_name="skill_profile")
    skill_format = models.CharField(max_length=100, blank=True)
    purpose = models.TextField()
    activation_method = models.CharField(max_length=200, blank=True)
    trigger_phrases = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    compatible_agents = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    compatible_platforms = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    required_context = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    dependencies = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    inputs = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    outputs = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    constraints = models.JSONField(default=list, blank=True, validators=[validate_string_list])
    examples = models.JSONField(default=list, blank=True, validators=[validate_string_list])

    def __str__(self) -> str:
        """Return a label that identifies this as the card's skill profile."""
        return f"Skill profile: {self.card}"


class CardMetrics(models.Model):
    """Store one day's aggregate directory impressions and detail-page clicks.

    Fields:
        card: Catalog card whose activity is measured. Deleting the parent card
            also deletes its metrics.
        date: Calendar date represented by this aggregate row.
        impressions: Number of times the card appeared in a rendered directory
            result on this date.
        clicks: Number of times the card's detail page was opened on this date.

    The database permits only one metrics row for each card and date. Views use
    atomic updates so concurrent requests do not overwrite existing counts.
    """

    card = models.ForeignKey(Cards, on_delete=models.CASCADE, related_name="metrics")
    date = models.DateField()
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        """Keep one metric row per card and day, with newest rows first."""

        constraints = [models.UniqueConstraint(fields=["card", "date"], name="unique_card_metric_per_day")]
        ordering = ["-date"]

    def __str__(self) -> str:
        """Return the card name and metric date for admin display."""
        return f"{self.card.name} - {self.date}"
