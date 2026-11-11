"""Configure staff-facing administration for cards, profiles, and metrics.

The admin interface is an operational tool for reviewing and correcting stored
metadata. It does not replace the user-facing registration workflow or alter
the authorization rules enforced by the catalog views.
"""

from django.contrib import admin

from .models import AgentProfile, CardMetrics, Cards, MCPServerProfile, SkillProfile


@admin.register(Cards)
class CardsAdmin(admin.ModelAdmin):
    """Present shared metadata in searchable, filterable admin views.

    The edit form groups catalog fields by purpose so staff can distinguish
    displayed organizational ownership from the Django user used for record
    authorization. Type-specific metadata is managed through the corresponding
    profile admin rather than being mixed into this shared form.
    """

    list_display = ("name", "resource_type", "domain", "status", "owner", "updated_at")
    list_filter = ("resource_type", "status", "from_official_team")
    search_fields = ("name", "short_description", "long_description", "domain", "ownership_contacts", "tags")
    fieldsets = (
        (
            "Shared metadata",
            {"fields": ("name", "short_description", "long_description", "resource_type", "domain", "tags")},
        ),
        ("Ownership and contacts", {"fields": ("owner", "ownership_contacts", "from_official_team")}),
        (
            "Release and links",
            {
                "fields": (
                    "status",
                    "version",
                    "documentation_url",
                    "repository_url",
                    "license",
                    "last_verified",
                    "logo",
                )
            },
        ),
    )


@admin.register(MCPServerProfile)
class MCPServerProfileAdmin(admin.ModelAdmin):
    """Let staff inspect and edit MCP-specific metadata by parent card.

    Common deployment attributes appear in the list view, while the generated
    fieldset includes all editable profile fields, including the card relation.
    """

    list_display = ("card", "protocol_version", "transport", "deployment_mode")
    fieldsets = (
        (
            "Type-specific metadata",
            {"fields": [field.name for field in MCPServerProfile._meta.fields if field.editable]},
        ),
    )


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    """Let staff inspect and edit agent-specific metadata by parent card.

    Model and framework fields appear in the list view to make operational
    review easier without opening each profile.
    """

    list_display = ("card", "agent_type", "primary_model", "framework")
    fieldsets = (
        ("Type-specific metadata", {"fields": [field.name for field in AgentProfile._meta.fields if field.editable]}),
    )


@admin.register(SkillProfile)
class SkillProfileAdmin(admin.ModelAdmin):
    """Let staff inspect and edit skill-specific metadata by parent card.

    Format and activation method appear in the list view, with every editable
    profile field available on the generated change form.
    """

    list_display = ("card", "skill_format", "activation_method")
    fieldsets = (
        ("Type-specific metadata", {"fields": [field.name for field in SkillProfile._meta.fields if field.editable]}),
    )


admin.site.register(CardMetrics)
