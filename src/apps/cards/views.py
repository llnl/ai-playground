"""Cards app views. It houses the card create, detail, update, delete, and search table views."""

from datetime import timedelta
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from .forms import CardForm
from .models import CardMetrics, Cards


class CardCreateView(LoginRequiredMixin, generic.CreateView):
    """Create a new card and assign it to the authenticated user."""

    model = Cards
    form_class = CardForm
    template_name = "cards/create.html"

    # Make sure user gets passed into form
    def form_valid(self, form: ModelForm) -> HttpResponse:
        """Assign the current user as owner before saving the card."""
        form.instance.owner = self.request.user
        return super().form_valid(form)


class CardDetailView(LoginRequiredMixin, generic.DetailView):
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


class CardUpdateView(LoginRequiredMixin, generic.UpdateView):
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
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Cards.objects.all()
        return Cards.objects.filter(owner=user)


class CardDeleteView(LoginRequiredMixin, generic.DeleteView):
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
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Cards.objects.all()
        return Cards.objects.filter(owner=user)


class CardAllView(LoginRequiredMixin, generic.ListView):
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
        # Logged in user
        user = self.request.user

        # Blanket query
        query = self.request.GET.get("query", "").strip()

        # Specific fields
        owner = self.request.GET.get("owner")
        categories = self.request.GET.getlist("category")

        # Specifically for trending/ url
        trending = self.request.GET.get("trending") == "true"

        # All data
        queryset = Cards.objects.all()

        # Specifically for my_cards/ url
        if owner == "me" and not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(owner=user)

        # These match the model and are a bunch of OR statements
        if query:
            queryset = queryset.filter(
                Q(owner__username__icontains=query)
                | Q(owner__email__icontains=query)
                | Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(maintainers__icontains=query)
                | Q(institution__icontains=query)
                | Q(tags__icontains=query)
            )

        if categories:
            queryset = queryset.filter(category__in=categories)

        if trending:
            start_date = timezone.localdate() - timedelta(days=30)

            queryset = (
                queryset.filter(metrics__date__gte=start_date)
                # Annotate creates temporary fields for HTML template to use
                .annotate(
                    # Coalesce protects againts Null
                    total_impressions=Coalesce(Sum("metrics__impressions"), Value(0)),
                    total_clicks=Coalesce(Sum("metrics__clicks"), Value(0)),
                )
                .annotate(  # TODO: Create better trending score
                    trending_score=F("total_clicks") * 3 + F("total_impressions")
                )
                .order_by("-trending_score", "name")
            )
        else:
            queryset.order_by("name")

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add the current search and category filters to the context for the HTML template when page refreshes.

        Args:
            **kwargs: Additional context arguments supplied by Django.

        Returns:
            dict[str, Any]: Template context containing active filters.
        """
        context = super().get_context_data(**kwargs)

        context["search_query"] = self.request.GET.get("query", "")
        context["selected_categories"] = self.request.GET.getlist("category")
        context["owner_filter"] = self.request.GET.get("owner", "")
        context["trending"] = self.request.GET.get("trending")

        return context

    # last step before sending response, increment here since other methods may be called more than once
    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        """Record an impression for each card displayed in the response.

        Uses ``__in`` to retrieve existing metrics in one query, ``bulk_create()``
        to create missing metrics efficiently, and ``update()`` to increment all
        matching impressions in one database operation. Python loops are limited
        to constructing the list of missing metric objects.

        Impressions are increased here since this is the last step before sending response.
        Otherwise other methods may be called more than once.

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
