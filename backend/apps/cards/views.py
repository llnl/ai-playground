"""Cards app views. It houses the card create, detail, update, delete, and search table views."""

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum
from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from .forms import CardForm
from .models import CardMetrics, Cards


# from django.contrib.auth.mixins import LoginRequiredMixin
# class CardCreateView(LoginRequiredMixin, generic.CreateView):  # assigning user means logging in
class CardCreateView(generic.CreateView):
    """Create a new card and assign it to the authenticated user."""

    model = Cards
    form_class = CardForm
    template_name = "cards/create.html"

    # Make sure user gets passed into form
    def form_valid(self, form: ModelForm) -> HttpResponse:
        """Assign the current user as owner before saving the card."""
        form.instance.owner = self.request.user
        return super().form_valid(form)


# class CardDetailView(LoginRequiredMixin, generic.DetailView):  # DtailView shows one primary_key at a time
class CardDetailView(generic.DetailView):  # DtailView shows one primary_key at a time
    """Display a card's details and record a daily click."""

    model = Cards
    template_name = "cards/detail.html"
    context_object_name = "card"

    # get is special built in function when page loads
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Render the card detail page and increment its daily click count.

        A daily ``CardMetrics`` record is created when one does not already
        exist for the card. The click count is incremented atomically to avoid
        race conditions when multiple requests arrive simultaneously.
        """
        response = super().get(request, *args, **kwargs)

        metric, _ = CardMetrics.objects.get_or_create(
            card=self.object,
            date=timezone.localdate(),
        )

        CardMetrics.objects.filter(pk=metric.pk).update(clicks=F("clicks") + 1)

        return response


# class CardUpdateView(LoginRequiredMixin, generic.UpdateView):  # gives permissions to only filters below
class CardUpdateView(generic.UpdateView):  # gives permissions to only filters below
    """Allow users to update only cards they own."""

    model = Cards
    form_class = CardForm
    template_name = "cards/update.html"
    context_object_name = "card"

    # get queryset is a special method that returns only a subset of the table
    # combined with DeleteView it only give access to certain urls
    def get_queryset(self) -> QuerySet:
        """Return cards owned by the current user.

        Returns:
            QuerySet: Cards belonging to the authenticated user.
        """
        return Cards.objects.filter(owner=self.request.user)


# class CardDeleteView(LoginRequiredMixin, generic.DeleteView):  # gives permissions to only filters below
class CardDeleteView(generic.DeleteView):  # gives permissions to only filters below
    """Allow users to delete only cards they own."""

    model = Cards
    template_name = "cards/delete.html"
    success_url = reverse_lazy("cards:my_cards")
    context_object_name = "card"

    # get queryset is a special method that returns only a subset of the table
    # combined with DeleteView it only give access to certain urls
    def get_queryset(self) -> QuerySet:
        """Return cards owned by the current user.

        Returns:
            QuerySet: Cards belonging to the authenticated user.
        """
        return Cards.objects.filter(owner=self.request.user)


# class CardAllView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardAllView(generic.ListView):  # Listview automatically grabs all rows from database
    """Display, search, and filter all cards."""

    model = Cards
    template_name = "cards/all.html"
    context_object_name = "cards"  # html variable to cycle through database

    # Query based on "cards/all.html" <form method="get"> values
    def get_queryset(self) -> QuerySet:
        """Return cards filtered by search text and selected categories.

        Returns:
            QuerySet: Matching cards ordered by name.
        """
        queryset = Cards.objects.all()

        search = self.request.GET.get("q", "").strip()
        categories = self.request.GET.getlist("category")

        # These match the model and are a bunch of OR statements
        if search:
            queryset = queryset.filter(
                Q(owner__username__icontains=search)
                | Q(owner__email__icontains=search)
                | Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(maintainers__icontains=search)
                | Q(institution__icontains=search)
                | Q(tags__icontains=search)
            )

        if categories:
            queryset = queryset.filter(category__in=categories)

        return queryset.order_by("name")

    # Since page refreshes, need values from before in query
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add the current search and category filters to the context for the HTML template.

        Args:
            **kwargs: Additional context arguments supplied by Django.

        Returns:
            dict[str, Any]: Template context containing active filters.
        """
        context = super().get_context_data(**kwargs)

        context["search_query"] = self.request.GET.get("q", "")
        context["selected_categories"] = self.request.GET.getlist("category")

        return context

    # last step before sending response, increment here since other methods may be called more than once
    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        """Record an impression for each card displayed in the response.

        Uses ``__in`` to retrieve existing metrics in one query, ``bulk_create()``
        to create missing metrics efficiently, and ``update()`` to increment all
        matching impressions in one database operation. Python loops are limited
        to constructing the list of missing metric objects.

        Args:
            context: Template context containing the displayed cards.
            **response_kwargs: Additional response options supplied by Django.

        Returns:
            HttpResponse: Rendered card list response.
        """
        today = timezone.localdate()
        card_ids = [card.pk for card in list(context["cards"])]

        with transaction.atomic():
            existing_ids = set(
                CardMetrics.objects.filter(
                    card_id__in=card_ids,
                    date=today,
                ).values_list("card_id", flat=True)
            )

            CardMetrics.objects.bulk_create(
                [CardMetrics(card_id=card_id, date=today) for card_id in card_ids if card_id not in existing_ids],
                ignore_conflicts=True,
            )

            CardMetrics.objects.filter(
                card_id__in=card_ids,
                date=today,
            ).update(impressions=F("impressions") + 1)

        return super().render_to_response(context, **response_kwargs)


# class CardMCPServersView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardMCPServersView(generic.ListView):  # Listview automatically grabs all rows from database
    """Display cards in the MCP Server category."""

    model = Cards
    template_name = "cards/mcp_servers.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self) -> QuerySet:
        """Return all cards assigned to the MCP Server category.

        Returns:
            QuerySet: Cards whose ``category="mcp_server"``.
        """
        return Cards.objects.filter(category="mcp_server")


# class CardAgentsView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardAgentsView(generic.ListView):  # Listview automatically grabs all rows from database
    """Display cards in the Agent category."""

    model = Cards
    template_name = "cards/agents.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self) -> QuerySet:
        """Return all cards assigned to the Agent category.

        Returns:
            QuerySet: Cards whose ``category="agent"``.
        """
        return Cards.objects.filter(category="agent")


# class CardSkillsView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardSkillsView(generic.ListView):  # Listview automatically grabs all rows from database
    """Display cards in the SKILL.md category."""

    model = Cards
    template_name = "cards/skills.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self) -> QuerySet:
        """Return all cards assigned to the SKILL.md category.

        Returns:
            QuerySet: Cards whose ``category="skills_md"``.
        """
        return Cards.objects.filter(category="skills_md")


# class MyCardListView(LoginRequiredMixin, generic.ListView):
class MyCardListView(generic.ListView):
    """Display cards owned by the authenticated user."""

    model = Cards
    template_name = "cards/my_cards.html"
    context_object_name = "cards"

    def get_queryset(self) -> QuerySet:
        """Return cards owned by the current user.

        Returns:
            QuerySet: Cards belonging to the authenticated user.
        """
        return Cards.objects.filter(owner=self.request.user)


class CardTrendingView(generic.ListView):
    """Display cards ranked by recent engagement."""

    model = Cards
    template_name = "cards/trending.html"
    context_object_name = "cards"

    def get_queryset(self) -> QuerySet:
        """Return cards ranked by engagement over the past 30 days.

        The trending score is calculated as:

        ``(total clicks * 3) + total impressions``

        Returns:
            QuerySet: Cards ordered by descending trending score,
                then alphabetically by name.
        """
        start_date = timezone.localdate() - timedelta(days=30)

        return (
            Cards.objects.filter(metrics__date__gte=start_date)
            .annotate(
                total_impressions=Sum("metrics__impressions"),
                total_clicks=Sum("metrics__clicks"),
            )
            .annotate(trending_score=(F("total_clicks") * 3 + F("total_impressions")))
            .order_by("-trending_score", "name")
        )
