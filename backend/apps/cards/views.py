from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import generic

from .forms import CardForm
from .models import Cards


# Create your views here.
class CardCreateView(generic.CreateView):
    model = Cards
    form_class = CardForm
    template_name = "cards/card.html"
    success_url = reverse_lazy("cards:card_success")


def card_success(request):
    return HttpResponse("Card created successfully.")


class CardAllView(generic.ListView):  # Listview automatically grabs all rows from database
    model = Cards
    template_name = "cards/all.html"
    context_object_name = "cards"  # html variable to cycle through database
