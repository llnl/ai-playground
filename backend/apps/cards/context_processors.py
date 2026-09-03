"""Cards app context processors.

Context processors make double curly braces variables availabe in HTML templates {{my_variable}}.
"""

from typing import Any

from django.http import HttpRequest

from .models import Cards


def card_stats(request: HttpRequest) -> dict[str, Any]:
    """Return card statistics for use in HTML templates.

    Args:
        request: The current HTTP request.

    Returns:
        A dictionary containing total cards, unique categories,
        and unique institutions.
    """
    cards = Cards.objects.all()

    return {
        "total_cards": cards.count(),
        "unique_categories": (cards.exclude(category="").values("category").distinct().count()),
        "unique_institutions": (cards.exclude(institution="").values("institution").distinct().count()),
    }
