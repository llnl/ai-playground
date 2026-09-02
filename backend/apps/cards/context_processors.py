from .models import Cards


def card_stats(request):
    cards = Cards.objects.all()

    return {
        "total_cards": cards.count(),
        "unique_categories": (
            cards.exclude(category="")
            .values("category")
            .distinct()
            .count()
        ),
        "unique_institutions": (
            cards.exclude(institution="")
            .values("institution")
            .distinct()
            .count()
        ),
    }