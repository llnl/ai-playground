"""Cards urls. It houses the card create, detail, update, delete, and search table urls."""

from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import path, reverse

from . import views

app_name = "cards"


def cards_by_category(request, **kwargs):
    """Redirect to CardAllView with search criteria."""
    url = reverse("cards:card_all")
    params = {key: value for key, value in kwargs.items() if value not in (None, "")}

    # Automatically converts dict to url query string
    # params = {"owner": "me", "category": "agent"} becomes owner=me&category=agent
    # params = {"category": ["agent", "mcp_server"]} becomes category=agent&category=mcp_server
    query_string = urlencode(params, doseq=True)

    return redirect(f"{url}?{query_string}")


urlpatterns = [
    # ex: /cards/
    # path("", views.IndexView.as_view(), name="index"),
    # /apps/cards/create/ Create a new card
    path("create/", views.CardCreateView.as_view(), name="card_create"),
    #
    # These URLs use the all/ view but pass in different search criteria
    #
    # /apps/cards/all/ View and search all cards
    path("all/", views.CardAllView.as_view(), name="card_all"),
    # /apps/cards/mcp_servers/ View all MCP Server cards
    path("mcp_servers/", cards_by_category, {"category": "mcp_server"}, name="card_mcp_servers"),
    # path("mcp_servers/", views.CardMCPServersView.as_view(), name="card_mcp_servers"),
    # /apps/cards/agents/ View all Agent cards
    path("agents/", cards_by_category, {"category": "agent"}, name="card_agents"),
    # /apps/cards/skills/ View all SKILL.md cards
    path("skills/", cards_by_category, {"category": "skills_md"}, name="card_skills"),
    # /apps/cards/trending/ View trending cards
    path("trending/", cards_by_category, {"trending": "true"}, name="trending"),
    # /apps/cards/my_cards/ View user owned cards
    path("my_cards/", cards_by_category, {"owner": "me"}, name="my_cards"),
    #
    # These URLs use the primary key <int:pk> meaning each datatable entry will have its own url
    #
    # /apps/cards/1/ View detailed information about a card
    path("<int:pk>/detail", views.CardDetailView.as_view(), name="card_detail"),
    # /apps/cards/1/ View form to update card
    path("<int:pk>/update/", views.CardUpdateView.as_view(), name="card_update"),
    # /apps/cards/1/ View to delete card
    path("<int:pk>/delete/", views.CardDeleteView.as_view(), name="card_delete"),
]
