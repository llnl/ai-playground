"""Cards app context processors.

Context processors make double curly braces variables availabe in HTML templates {{my_variable}}.
"""

from typing import Any

from django.http import HttpRequest

from .models import Cards


def card_stats(request: HttpRequest) -> dict[str, Any]:
    """Return catalog-wide counts for the shared statistics widget.

    Institutions are nested under ownership contacts, so their count is built
    from the distinct institution names across all cards. The request is part
    of Django's context-processor interface but is not otherwise inspected.

    Args:
        request: The current HTTP request.

    Returns:
        Counts for all cards, resource types, distinct institutions, MCP
        servers, agents, and skills.
    """
    cards = Cards.objects.all()

    return {
        "total_cards": cards.count(),
        "unique_categories": cards.values("resource_type").distinct().count(),
        "unique_institutions": len(
            {
                institution
                for card in cards
                for contact in card.ownership_contacts
                if isinstance(contact, dict)
                for institution in contact.get("institutions", [])
            }
        ),
        "total_mcp_servers": cards.filter(resource_type="mcp_server").count(),
        "total_agents": cards.filter(resource_type="agent").count(),
        "total_skills_md": cards.filter(resource_type="skill").count(),
    }
