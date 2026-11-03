"""Cards app views. It houses the card create, detail, update, delete, and search table views."""

import json
from datetime import timedelta
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.forms.formsets import BaseFormSet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from .forms import (
    PROFILE_FORMS,
    CardForm,
    OwnershipFormSet,
    ProfileForm,
    ownership_contacts_from_formset,
    ownership_initial,
    save_card_with_profile,
)
from .models import CardMetrics, Cards


class CardRegistrationMixin:
    """Coordinate shared, ownership, and type-specific registration forms.

    Create and update pages render all profile forms so JavaScript can switch
    resource types immediately. Only the selected profile is validated and
    persisted. Ownership rows are converted to the nested JSON value expected
    by :class:`Cards` before the shared form is validated.

    Attributes:
        profile_prefixes: Stable form prefixes used to prevent similarly named
            fields from different resource profiles colliding in one request.
        object: Existing card during updates, or ``None`` during creation.
    """

    object: Cards | None
    profile_prefixes = {
        Cards.ResourceType.MCP_SERVER: "mcp",
        Cards.ResourceType.AGENT: "agent",
        Cards.ResourceType.SKILL: "skill",
    }

    def get_ownership_formset(self) -> BaseFormSet:
        """Build ownership controls from submitted or persisted metadata.

        Returns:
            A POST-bound formset during submission. On GET, update views receive
            rows converted from stored ownership JSON, while create views start
            with one team owner so the form works without JavaScript.
        """
        if self.request.method == "POST":
            return OwnershipFormSet(self.request.POST, prefix="owners")
        initial = (
            ownership_initial(self.object.ownership_contacts) if self.object is not None else [{"owner_type": "team"}]
        )
        return OwnershipFormSet(initial=initial, prefix="owners")

    def get_profile_forms(self) -> tuple[dict[str, ProfileForm], str]:
        """Build all profile forms and identify the selected resource type.

        All three forms are rendered so browser JavaScript can switch sections
        without another request. On POST they are all bound, but the view only
        validates and saves the form matching ``resource_type``. During updates,
        the existing profile is attached only to its corresponding form.

        Returns:
            A mapping from resource type to prefixed profile form, followed by
            the submitted, stored, or default MCP server resource type.
        """
        default_type = self.object.resource_type if self.object is not None else Cards.ResourceType.MCP_SERVER
        selected = self.request.POST.get("resource_type", default_type)
        current_profile = self.object.get_profile() if self.object is not None else None
        profile_forms: dict[str, ProfileForm] = {}
        for resource_type, form_class in PROFILE_FORMS.items():
            instance = (
                current_profile
                if current_profile is not None and current_profile.expected_resource_type == resource_type
                else None
            )
            profile_forms[resource_type] = form_class(
                self.request.POST if self.request.method == "POST" else None,
                instance=instance,
                prefix=self.profile_prefixes[resource_type],
            )
        return profile_forms, selected

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add profile forms and ownership controls to the template context.

        Args:
            **kwargs: Context values supplied by Django or :meth:`post`.

        Returns:
            Template context containing the shared form and all profile forms.
        """
        context = super().get_context_data(**kwargs)
        if "profile_forms" not in context:
            profile_forms, _ = self.get_profile_forms()
            context["profile_forms"] = profile_forms
        context.setdefault("ownership_formset", self.get_ownership_formset())
        return context

    def get_registration_form(self, ownership_formset: BaseFormSet) -> CardForm:
        """Build the shared card form with validated ownership JSON injected.

        Args:
            ownership_formset: Bound owner controls for the current request.

        Returns:
            A bound shared metadata form. Ownership JSON is injected only when
            the formset is valid, allowing ownership errors to remain attached
            to their individual controls.
        """
        data = self.request.POST.copy()
        if ownership_formset.is_valid():
            data["ownership_contacts"] = json.dumps(ownership_contacts_from_formset(ownership_formset))
        form_kwargs = self.get_form_kwargs()
        form_kwargs["data"] = data
        return self.get_form_class()(**form_kwargs)

    def get_registration_owner(self) -> Any | None:
        """Return the authenticated owner for creation but not updates.

        Returns:
            The requesting user when creating a card. ``None`` during updates
            preserves the card's existing authorization owner.
        """
        return self.request.user if self.object is None else None

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Validate the coordinated forms and atomically persist the resource.

        Args:
            request: Authenticated request containing shared and profile fields.
            *args: Positional arguments supplied by Django's URL dispatcher.
            **kwargs: Keyword arguments supplied by Django's URL dispatcher.

        Returns:
            A detail-page redirect on success, or the current registration page
            with shared, ownership, and selected-profile errors on failure.
        """
        self.object = self.get_object() if isinstance(self, generic.UpdateView) else None
        ownership_formset = self.get_ownership_formset()
        ownership_valid = ownership_formset.is_valid()
        form = self.get_registration_form(ownership_formset)
        profile_forms, selected = self.get_profile_forms()
        profile_form = profile_forms.get(selected, profile_forms[Cards.ResourceType.MCP_SERVER])
        if ownership_valid and form.is_valid() and profile_form.is_valid():
            self.object = save_card_with_profile(form, profile_form, owner=self.get_registration_owner())
            return generic.edit.FormMixin.form_valid(self, form)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                profile_forms=profile_forms,
                ownership_formset=ownership_formset,
            )
        )


class CardCreateView(CardRegistrationMixin, LoginRequiredMixin, generic.CreateView):
    """Create a card, its ownership metadata, and one matching profile."""

    model = Cards
    form_class = CardForm
    template_name = "cards/create.html"


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


class CardUpdateView(CardRegistrationMixin, LoginRequiredMixin, generic.UpdateView):
    """Update cards accessible to their submitter, contacts, or staff.

    Shared and profile forms are validated together. Changing ``resource_type``
    replaces the old profile within the same transaction rather than retaining
    incompatible metadata.
    """

    model = Cards
    form_class = CardForm
    template_name = "cards/update.html"
    context_object_name = "card"

    def get_queryset(self) -> QuerySet:
        """Limit updates to cards the current user is authorized to modify.

        Staff and superusers receive the full queryset. Other users receive
        cards they submitted or cards listing their email in any ownership
        contact. Contact matching is performed in Python because ownership is
        currently stored as nested JSON.

        Returns:
            Cards available to the authenticated user for update.
        """
        user = self.request.user
        queryset = Cards.objects.all()

        if user.is_staff or user.is_superuser:
            return queryset

        allowed_ids = [card.pk for card in queryset if card.owner_id == user.pk or user.email in card.contact_emails]
        return queryset.filter(pk__in=allowed_ids)


class CardDeleteView(LoginRequiredMixin, generic.DeleteView):
    """Delete cards accessible to their submitter, contacts, or staff."""

    model = Cards
    template_name = "cards/delete.html"
    success_url = reverse_lazy("cards:my_cards")
    context_object_name = "card"

    # get queryset is a special method that returns only a subset of the table
    # combined with DeleteView it only give access to certain urls
    def get_queryset(self) -> QuerySet:
        """Limit deletion to cards the current user is authorized to modify.

        Staff and superusers can delete any card. Other users can delete cards
        they submitted or cards listing their email as an ownership contact.

        Returns:
            Cards available to the authenticated user for deletion.
        """
        user = self.request.user
        queryset = Cards.objects.all()

        if user.is_staff or user.is_superuser:
            return queryset

        allowed_ids = [card.pk for card in queryset if card.owner_id == user.pk or user.email in card.contact_emails]
        return queryset.filter(pk__in=allowed_ids)


class CardAllView(LoginRequiredMixin, generic.ListView):
    """Display the searchable directory and record impressions for its results."""

    model = Cards
    template_name = "cards/all.html"
    context_object_name = "cards"  # html variable to cycle through database

    # Query based on "cards/all.html" <form method="get"> values
    def get_queryset(self) -> QuerySet:
        """Apply ownership, text, resource-type, and trending filters.

        General search covers submitter identity and shared display metadata.
        Trending results aggregate the previous 30 days of metrics and rank
        clicks more heavily than impressions.

        Returns:
            Matching cards, including metric annotations for trending results.
        """
        # Logged in user
        user = self.request.user

        # Blanket query
        query = self.request.GET.get("query", "").strip()

        # Specific fields
        owner = self.request.GET.get("owner")
        resource_types = self.request.GET.getlist("resource_type")

        # Specifically for trending/ url
        trending = self.request.GET.get("trending") == "true"

        # All data
        queryset = Cards.objects.all()

        # Specifically for my_cards/ url
        if owner == "me" and not (user.is_staff or user.is_superuser):
            allowed_ids = [
                card.pk for card in queryset if card.owner_id == user.pk or user.email in card.contact_emails
            ]
            queryset = queryset.filter(pk__in=allowed_ids)

        # These match the model and are a bunch of OR statements
        if query:
            queryset = queryset.filter(
                Q(owner__username__icontains=query)
                | Q(owner__email__icontains=query)
                | Q(name__icontains=query)
                | Q(short_description__icontains=query)
                | Q(long_description__icontains=query)
                | Q(ownership_contacts__icontains=query)
                | Q(domain__icontains=query)
                | Q(tags__icontains=query)
            )

        if resource_types:
            queryset = queryset.filter(resource_type__in=resource_types)

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
        """Preserve active directory controls in the rendered template context.

        Args:
            **kwargs: Additional context arguments supplied by Django.

        Returns:
            Template context containing active filters and display mode.
        """
        context = super().get_context_data(**kwargs)

        context["search_query"] = self.request.GET.get("query", "")
        context["selected_categories"] = self.request.GET.getlist("resource_type")
        context["owner_filter"] = self.request.GET.get("owner", "")
        context["trending"] = self.request.GET.get("trending")
        context["resource_view"] = self.request.GET.get("view", "grid")

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
