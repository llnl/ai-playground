"""Tests for the card models and forms."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from .forms import AgentProfileForm, CardForm, MCPServerProfileForm, SkillProfileForm, save_card_with_profile
from .models import AgentProfile, Cards, MCPServerProfile, SkillProfile

############################################
# Backend contract tests for catalog cards #
############################################


def ownership(email: str = "team@example.org") -> list[dict]:
    """Return valid ownership metadata for tests."""
    return [
        {
            "owner_name": "Applied AI Team",
            "owner_type": "team",
            "contact_emails": [email],
            "institutions": ["Example Laboratory"],
        }
    ]


def card_data(resource_type: str = Cards.ResourceType.MCP_SERVER) -> dict:
    """Return valid shared form data."""
    return {
        "name": "Example resource",
        "short_description": "A useful AI resource.",
        "long_description": "A detailed explanation of this useful AI resource.",
        "resource_type": resource_type,
        "domain": "Scientific computing",
        "tags": ["simulation", "automation"],
        "ownership_contacts": ownership(),
        "status": Cards.Status.ACTIVE,
        "version": "1.0",
        "documentation_url": "https://example.org/docs",
        "repository_url": "https://example.org/repository",
    }


class CardModelTests(TestCase):
    """Test shared and type-specific model validation."""

    def test_shared_metadata_and_multiple_owners_are_valid(self):
        """Accept the final shared schema and multiple ownership entries."""
        data = card_data()
        data["ownership_contacts"].append(
            {
                "owner_name": "Jane Researcher",
                "owner_type": "individual",
                "contact_emails": ["jane@example.org", "jane.secondary@example.org"],
                "institutions": [],
            }
        )
        card = Cards(**data)
        card.full_clean()
        self.assertEqual(card.status, Cards.Status.ACTIVE)
        self.assertEqual(len(card.contact_emails), 3)

    def test_invalid_contact_email_is_rejected(self):
        """Reject malformed emails in ownership metadata."""
        data = card_data()
        data["ownership_contacts"] = ownership("not-an-email")
        with self.assertRaises(ValidationError):
            Cards(**data).full_clean()

    def test_missing_ownership_is_rejected(self):
        """Require at least one organizational owner."""
        data = card_data()
        data["ownership_contacts"] = []
        with self.assertRaises(ValidationError):
            Cards(**data).full_clean()

    def test_profile_type_must_match_card(self):
        """Reject profiles assigned to another resource type."""
        card = Cards.objects.create(**card_data(Cards.ResourceType.AGENT))
        profile = MCPServerProfile(card=card, endpoint_url="https://example.org/mcp")
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_profile_helpers_find_exact_matching_profile(self):
        """Return the matching one-to-one profile."""
        card = Cards.objects.create(**card_data())
        profile = MCPServerProfile.objects.create(card=card, endpoint_url="https://example.org/mcp")
        self.assertEqual(card.get_profile(), profile)
        self.assertTrue(card.has_type_profile())

    def test_card_cannot_have_multiple_profile_types(self):
        """Reject a second type-specific profile for the same card."""
        card = Cards.objects.create(**card_data())
        MCPServerProfile.objects.create(card=card, endpoint_url="https://example.org/mcp")
        card.resource_type = Cards.ResourceType.AGENT
        card.save(update_fields=["resource_type"])
        with self.assertRaises(ValidationError):
            AgentProfile(card=card, primary_purpose="Help").full_clean()


class CardFormTests(TestCase):
    """Test shared and profile form validation."""

    def test_each_profile_form_accepts_valid_minimum_data(self):
        """Require only fields relevant to the selected resource type."""
        cases = (
            (MCPServerProfileForm, {"endpoint_url": "https://example.org/mcp"}),
            (AgentProfileForm, {"primary_purpose": "Submit and monitor jobs"}),
            (SkillProfileForm, {"purpose": "Teach an agent to validate input"}),
        )
        for form_class, data in cases:
            with self.subTest(form=form_class.__name__):
                self.assertTrue(form_class(data=data).is_valid())

    def test_invalid_profile_list_is_rejected(self):
        """Validate list-like profile fields at the application layer."""
        form = AgentProfileForm(data={"primary_purpose": "Help", "supported_tasks": {"bad": "shape"}})
        self.assertFalse(form.is_valid())
        self.assertIn("supported_tasks", form.errors)

    def test_mcp_profile_requires_a_connection_path(self):
        """Require either an endpoint URL or installation instructions."""
        form = MCPServerProfileForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("endpoint URL or installation instructions", form.non_field_errors()[0])

    def test_mcp_profile_accepts_installation_instructions_without_endpoint(self):
        """Allow locally installed MCP servers without a remote endpoint."""
        form = MCPServerProfileForm(data={"installation_instructions": "Install and run the server locally."})
        self.assertTrue(form.is_valid())

    def test_mcp_model_rejects_malformed_tool_objects(self):
        """Require both supported string properties on every stored tool."""
        card = Cards.objects.create(**card_data())
        profile = MCPServerProfile(
            card=card,
            endpoint_url="https://example.org/mcp",
            tools=[{"name": "run_simulation"}],
        )
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_mcp_profile_tools_are_managed_outside_profile_form(self):
        """Keep structured tools out of the scalar MCP model form."""
        form = MCPServerProfileForm(data={"endpoint_url": "https://example.org/mcp"})
        self.assertNotIn("tools", form.fields)

    def test_obsolete_fields_are_rejected(self):
        """Do not silently accept fields removed from the final contract."""
        data = card_data()
        data["internal_url"] = "https://internal.example.org"
        form = CardForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("Obsolete fields", form.non_field_errors()[0])


class CardSaveTests(TestCase):
    """Test atomic creation and update behavior."""

    def setUp(self):
        """Create the submitting user."""
        self.user = get_user_model().objects.create_user("submitter", "submitter@example.org", "password")

    def test_save_creates_exactly_one_profile_and_assigns_owner(self):
        """Create shared and matching type-specific records together."""
        card = save_card_with_profile(
            CardForm(data=card_data()),
            MCPServerProfileForm(data={"transport": "stdio", "installation_instructions": "Run the server."}),
            owner=self.user,
        )
        self.assertEqual(card.owner, self.user)
        self.assertTrue(card.has_type_profile())
        self.assertEqual(MCPServerProfile.objects.count(), 1)

    def test_mismatched_forms_create_no_partial_record(self):
        """Roll back when a profile does not match the selected resource type."""
        with self.assertRaises(ValidationError):
            save_card_with_profile(
                CardForm(data=card_data(Cards.ResourceType.AGENT)),
                MCPServerProfileForm(data={"endpoint_url": "https://example.org/mcp"}),
                owner=self.user,
            )
        self.assertFalse(Cards.objects.exists())

    def test_update_can_replace_profile_type(self):
        """Remove the old profile when the resource type changes."""
        card = save_card_with_profile(
            CardForm(data=card_data()),
            MCPServerProfileForm(data={"endpoint_url": "https://example.org/mcp"}),
            owner=self.user,
        )
        updated_data = card_data(Cards.ResourceType.SKILL)
        updated_data["name"] = card.name
        updated = save_card_with_profile(
            CardForm(data=updated_data, instance=card),
            SkillProfileForm(data={"purpose": "Reusable instructions"}),
        )
        self.assertEqual(updated.resource_type, Cards.ResourceType.SKILL)
        self.assertFalse(MCPServerProfile.objects.filter(card=updated).exists())
        self.assertTrue(SkillProfile.objects.filter(card=updated).exists())


class CardPermissionTests(TestCase):
    """Test owner, contact, staff, and unrelated-user permissions."""

    def setUp(self):
        """Create users and a card with a matching profile."""
        users = get_user_model().objects
        self.owner = users.create_user("owner", "owner@example.org", "password")
        self.contact = users.create_user("contact", "contact@example.org", "password")
        self.other = users.create_user("other", "other@example.org", "password")
        self.staff = users.create_user("staff", "staff@example.org", "password", is_staff=True)
        data = card_data()
        data["ownership_contacts"] = ownership(self.contact.email)
        self.card = Cards.objects.create(owner=self.owner, **data)
        MCPServerProfile.objects.create(card=self.card, endpoint_url="https://example.org/mcp")

    def assert_can_update(self, user, expected_status: int):
        """Assert update-page authorization for one user."""
        self.client.force_login(user)
        response = self.client.get(reverse("cards:card_update", kwargs={"pk": self.card.pk}))
        self.assertEqual(response.status_code, expected_status)

    def test_modify_permissions(self):
        """Allow owner, contact, and staff while denying unrelated users."""
        for user in (self.owner, self.contact, self.staff):
            with self.subTest(user=user.username):
                self.assert_can_update(user, 200)
        self.assert_can_update(self.other, 404)

    def test_deleted_submitter_does_not_remove_card_or_contact_access(self):
        """Preserve cards and contact authorization after owner deletion."""
        self.owner.delete()
        self.card.refresh_from_db()
        self.assertIsNone(self.card.owner)
        self.assert_can_update(self.contact, 200)


#######################################################
# Frontend contract tests for card registration forms #
#######################################################


class CardRegistrationUITests(TestCase):
    """Test repeatable ownership controls and type-specific registration forms."""

    def setUp(self):
        """Log in a user who can access registration pages."""
        self.user = get_user_model().objects.create_user("registrar", "registrar@example.org", "password")
        self.client.force_login(self.user)

    def test_create_page_renders_all_progressively_enhanced_profile_sections(self):
        """Keep every type available for no-JavaScript submission and browser switching."""
        response = self.client.get(reverse("cards:card_create"))
        self.assertContains(response, 'data-profile-section="mcp_server"')
        self.assertContains(response, 'data-profile-section="agent"')
        self.assertContains(response, 'data-profile-section="skill"')
        self.assertContains(response, 'name="owners-TOTAL_FORMS"')
        self.assertNotContains(response, 'name="ownership_contacts"')

    def test_create_accepts_line_based_lists_and_ownership_controls(self):
        """Convert friendly controls to validated JSON metadata when saving."""
        response = self.client.post(
            reverse("cards:card_create"),
            {
                "name": "Job agent",
                "short_description": "Submits and monitors jobs.",
                "long_description": "Submits jobs, monitors progress, and summarizes failures.",
                "resource_type": Cards.ResourceType.AGENT,
                "domain": "Scientific computing",
                "tags": "jobs\nautomation",
                "status": Cards.Status.ACTIVE,
                "agent-primary_purpose": "Manage scheduler jobs",
                "agent-supported_tasks": "Submit jobs\nSummarize failures",
                "owners-TOTAL_FORMS": "1",
                "owners-INITIAL_FORMS": "0",
                "owners-MIN_NUM_FORMS": "1",
                "owners-MAX_NUM_FORMS": "1000",
                "owners-0-owner_name": "Applied AI Team",
                "owners-0-owner_type": "team",
                "owners-0-contact_emails": "ai@example.org\nlead@example.org",
                "owners-0-institutions": "Example Laboratory",
            },
        )
        card = Cards.objects.get(name="Job agent")
        self.assertRedirects(response, card.get_absolute_url())
        self.assertEqual(card.tags, ["jobs", "automation"])
        self.assertEqual(card.ownership_contacts[0]["contact_emails"], ["ai@example.org", "lead@example.org"])
        self.assertEqual(card.agent_profile.supported_tasks, ["Submit jobs", "Summarize failures"])

    def test_invalid_owner_redisplays_entered_profile_values(self):
        """Display field errors without dropping selected profile input."""
        response = self.client.post(
            reverse("cards:card_create"),
            {
                "name": "Skill draft",
                "short_description": "A draft skill.",
                "long_description": "A detailed explanation of the draft skill.",
                "resource_type": Cards.ResourceType.SKILL,
                "domain": "Research",
                "status": Cards.Status.ACTIVE,
                "skill-purpose": "Validate research inputs",
                "owners-TOTAL_FORMS": "1",
                "owners-INITIAL_FORMS": "0",
                "owners-MIN_NUM_FORMS": "1",
                "owners-MAX_NUM_FORMS": "1000",
                "owners-0-owner_name": "Research Team",
                "owners-0-owner_type": "team",
                "owners-0-contact_emails": "invalid-email",
                "owners-0-institutions": "Example Laboratory",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid-email is not a valid email address")
        self.assertContains(response, "Validate research inputs")
        self.assertFalse(Cards.objects.exists())

    def test_mcp_registration_saves_structured_tool_formset(self):
        """Persist indexed tool name and description fields as JSON objects."""
        response = self.client.post(
            reverse("cards:card_create"),
            {
                "name": "Simulation MCP",
                "short_description": "Runs simulations.",
                "long_description": "Runs simulations from validated input files.",
                "resource_type": Cards.ResourceType.MCP_SERVER,
                "domain": "Scientific computing",
                "status": Cards.Status.ACTIVE,
                "mcp-endpoint_url": "https://example.org/mcp",
                "tools-TOTAL_FORMS": "1",
                "tools-INITIAL_FORMS": "0",
                "tools-MIN_NUM_FORMS": "0",
                "tools-MAX_NUM_FORMS": "1000",
                "tools-0-name": "run_simulation",
                "tools-0-description": "Runs a simulation from an input file",
                "owners-TOTAL_FORMS": "1",
                "owners-INITIAL_FORMS": "0",
                "owners-MIN_NUM_FORMS": "1",
                "owners-MAX_NUM_FORMS": "1000",
                "owners-0-owner_name": "Applied AI Team",
                "owners-0-owner_type": "team",
                "owners-0-contact_emails": "ai@example.org",
                "owners-0-institutions": "Example Laboratory",
            },
        )
        card = Cards.objects.get(name="Simulation MCP")
        self.assertRedirects(response, card.get_absolute_url())
        self.assertEqual(
            card.mcp_server_profile.tools,
            [{"name": "run_simulation", "description": "Runs a simulation from an input file"}],
        )

    def test_mcp_tool_errors_are_attached_to_structured_fields(self):
        """Redisplay a missing tool description without creating a partial card."""
        response = self.client.post(
            reverse("cards:card_create"),
            {
                "name": "Invalid MCP",
                "short_description": "Runs simulations.",
                "long_description": "Runs simulations from validated input files.",
                "resource_type": Cards.ResourceType.MCP_SERVER,
                "domain": "Scientific computing",
                "status": Cards.Status.ACTIVE,
                "mcp-endpoint_url": "https://example.org/mcp",
                "tools-TOTAL_FORMS": "1",
                "tools-INITIAL_FORMS": "0",
                "tools-MIN_NUM_FORMS": "0",
                "tools-MAX_NUM_FORMS": "1000",
                "tools-0-name": "run_simulation",
                "tools-0-description": "",
                "owners-TOTAL_FORMS": "1",
                "owners-INITIAL_FORMS": "0",
                "owners-MIN_NUM_FORMS": "1",
                "owners-MAX_NUM_FORMS": "1000",
                "owners-0-owner_name": "Applied AI Team",
                "owners-0-owner_type": "team",
                "owners-0-contact_emails": "ai@example.org",
                "owners-0-institutions": "Example Laboratory",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(Cards.objects.filter(name="Invalid MCP").exists())

    def test_logo_rejects_unsupported_file_extension(self):
        """Reject a logo format outside the documented allowlist."""
        data = card_data()
        data["logo"] = SimpleUploadedFile("logo.gif", b"not-an-image", content_type="image/gif")
        form = CardForm(data=data, files={"logo": data.pop("logo")})
        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)


################################
# Tests for the cards REST API #
################################


class CardAPITests(APITestCase):
    """Verify authentication, ownership, profiles, permissions, and type routes."""

    def setUp(self) -> None:
        """Create users and a representative card for each test."""
        self.user = get_user_model().objects.create_user(
            username="owner", email="owner@example.org", password="password"
        )
        self.other_user = get_user_model().objects.create_user(
            username="other", email="other@example.org", password="password"
        )
        self.card = Cards.objects.create(
            owner=self.user,
            name="Test card",
            description="A test card",
            resource_type=Cards.ResourceType.AGENT,
            domain="Scientific computing",
            ownership_contacts=ownership(),
        )
        AgentProfile.objects.create(card=self.card, primary_purpose="Test agent behavior")

    def test_requests_require_login(self) -> None:
        """Reject requests that do not have an authenticated user."""
        response = self.client.get("/api/v1/cards/")
        self.assertEqual(response.status_code, 403)

    def test_authenticated_user_can_list_and_create(self) -> None:
        """Allow authenticated users to list and create owned cards."""
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/v1/cards/").status_code, 200)
        response = self.client.post(
            "/api/v1/cards/",
            {
                "name": "New",
                "description": "Desc",
                "resource_type": "mcp_server",
                "domain": "Scientific computing",
                "ownership_contacts": ownership(),
                "mcp_server_profile": {"endpoint_url": "https://example.org/mcp"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["owner"], self.user.id)
        self.assertEqual(response.data["mcp_server_profile"]["endpoint_url"], "https://example.org/mcp")

    def test_only_owner_can_update(self) -> None:
        """Reject a partial update from an unrelated authenticated user."""
        self.client.force_authenticate(self.other_user)
        response = self.client.patch(f"/api/v1/cards/{self.card.pk}/", {"name": "Changed"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_resource_type_endpoint(self) -> None:
        """Return cards matching the agent resource-type route."""
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/cards/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_create_requires_matching_profile(self) -> None:
        """Reject API creation without the selected resource type's profile."""
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/cards/",
            {
                "name": "Incomplete",
                "description": "Missing its profile",
                "resource_type": "agent",
                "domain": "Automation",
                "ownership_contacts": ownership(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("agent_profile", response.data)

    def test_ownership_contact_can_update(self) -> None:
        """Allow a listed ownership contact to update through the API."""
        contact = get_user_model().objects.create_user(
            username="contact", email="team@example.org", password="password"
        )
        self.client.force_authenticate(contact)
        response = self.client.patch(f"/api/v1/cards/{self.card.pk}/", {"version": "2.0"}, format="json")
        self.assertEqual(response.status_code, 200)
