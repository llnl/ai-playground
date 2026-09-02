from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, F, Sum
from .forms import CardForm
from .models import Cards, CardMetrics
from django.utils import timezone
from datetime import timedelta
# Create your views here.
# class CardCreateView(LoginRequiredMixin, generic.CreateView):  # assigning user means logging in
class CardCreateView(generic.CreateView):
    model = Cards
    form_class = CardForm
    template_name = "cards/create.html"

    # Make sure user gets passed into form
    # def form_valid(self, form):
    #     form.instance.owner = self.request.user
    #     return super().form_valid(form)

# class CardAllView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardAllView(generic.ListView):  # Listview automatically grabs all rows from database
    model = Cards
    template_name = "cards/all.html"
    context_object_name = "cards"  # html variable to cycle through database


    # Query based on "cards/all.html" <form method="get"> values
    def get_queryset(self):
        queryset = Cards.objects.all()

        search = self.request.GET.get("q", "").strip()
        categories = self.request.GET.getlist("category")

        # These match the model
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
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["search_query"] = self.request.GET.get("q", "")
        context["selected_categories"] = self.request.GET.getlist("category")

        return context

    # last step before sending response, increment here since other methods may be called more than once
    def render_to_response(self, context, **response_kwargs):
        today = timezone.localdate()

        for card in context["cards"]:
            metric, _ = CardMetrics.objects.get_or_create(
                card=card,
                date=today,
            )

            CardMetrics.objects.filter(pk=metric.pk).update(
                impressions=F("impressions") + 1
            )

        return super().render_to_response(context, **response_kwargs)

# class CardMCPServersView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardMCPServersView(generic.ListView):  # Listview automatically grabs all rows from database
    model = Cards
    template_name = "cards/mcp_servers.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self):
            return Cards.objects.filter(category="mcp_server")

# class CardAgentsView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardAgentsView(generic.ListView):  # Listview automatically grabs all rows from database
    model = Cards
    template_name = "cards/agents.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self):
            return Cards.objects.filter(category="agent")

# class CardSkillsView(LoginRequiredMixin, generic.ListView):  # Listview automatically grabs all rows from database
class CardSkillsView(generic.ListView):  # Listview automatically grabs all rows from database
    model = Cards
    template_name = "cards/skills.html"
    context_object_name = "cards"  # html variable to cycle through database

    def get_queryset(self):
            return Cards.objects.filter(category="skills_md")

# class MyCardListView(LoginRequiredMixin, generic.ListView):
class MyCardListView(generic.ListView):
    model = Cards
    template_name = "cards/my_cards.html"
    context_object_name = "cards"

    def get_queryset(self):
        return Cards.objects.filter(owner=self.request.user)


class CardTrendingView(generic.ListView):
    model = Cards
    template_name = "cards/trending.html"
    context_object_name = "cards"

    def get_queryset(self):
        start_date = timezone.localdate() - timedelta(days=30)

        return (
            Cards.objects
            .filter(metrics__date__gte=start_date)
            .annotate(
                total_impressions=Sum("metrics__impressions"),
                total_clicks=Sum("metrics__clicks"),
            )
            .annotate(
                trending_score=(
                    F("total_clicks") * 3
                    + F("total_impressions")
                )
            )
            .order_by("-trending_score", "name")
        )


# class CardDetailView(LoginRequiredMixin, generic.DetailView):  # DtailView shows one primary_key at a time
class CardDetailView(generic.DetailView):  # DtailView shows one primary_key at a time
    model = Cards
    template_name = "cards/detail.html"
    context_object_name = "card"

    # get is special built in function when page loads
    def get(self, request, *args, **kwargs):
            response = super().get(request, *args, **kwargs)

            metric, _ = CardMetrics.objects.get_or_create(
                card=self.object,
                date=timezone.localdate(),
            )

            CardMetrics.objects.filter(pk=metric.pk).update(
                clicks=F("clicks") + 1
            )

            return response

# class CardUpdateView(LoginRequiredMixin, generic.UpdateView):  # gives permissions to only filters below
class CardUpdateView(generic.UpdateView):  # gives permissions to only filters below
    model = Cards
    form_class = CardForm
    template_name = "cards/update.html"
    context_object_name = "cards"

    def get_queryset(self):
        return Cards.objects.filter(owner=self.request.user)

# class CardDeleteView(LoginRequiredMixin, generic.DeleteView):  # gives permissions to only filters below
class CardDeleteView(generic.DeleteView):  # gives permissions to only filters below
    model = Cards
    template_name = "cards/delete.html"
    success_url = reverse_lazy("cards:my_cards")
    context_object_name = "cards"

    # get queryset is a special method that returns only a subset of the table
    # combined with DeleteView it only give access to certain urls
    def get_queryset(self):
        return Cards.objects.filter(owner=self.request.user)