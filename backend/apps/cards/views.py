from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin

from .forms import CardForm
from .models import Cards


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

# class CardDetailView(LoginRequiredMixin, generic.DetailView):  # DtailView shows one primary_key at a time
class CardDetailView(generic.DetailView):  # DtailView shows one primary_key at a time
    model = Cards
    template_name = "cards/detail.html"
    context_object_name = "card"

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