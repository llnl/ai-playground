"""Cards urls. It houses the card create, detail, update, delete, and search table urls."""

from django.urls import path

from . import views

app_name = "cards"

urlpatterns = [
    # ex: /cards/
    # path("", views.IndexView.as_view(), name="index"),
    # /apps/cards/create/ Create a new card
    path("create/", views.CardCreateView.as_view(), name="card_create"),
    # /apps/cards/all/ View and search all cards
    path("all/", views.CardAllView.as_view(), name="card_all"),
    # /apps/cards/mcp_servers/ View all MCP Server cards
    path("mcp_servers/", views.CardMCPServersView.as_view(), name="card_mcp_servers"),
    # /apps/cards/agents/ View all Agent cards
    path("agents/", views.CardAgentsView.as_view(), name="card_agents"),
    # /apps/cards/skills/ View all SKILL.md cards
    path("skills/", views.CardSkillsView.as_view(), name="card_skills"),
    # /apps/cards/trending/ View trending cards
    path("trending/", views.CardTrendingView.as_view(), name="trending"),
    # /apps/cards/trending/ View user owned cards
    path("my_cards/", views.MyCardListView.as_view(), name="my_cards"),
    #
    # These URLs use the primary key <int:pk> meaning each datatable entry will have its own url
    #
    # /apps/cards/1/ View detailed information about a card
    path("/apps/cards/<int:pk>/", views.CardDetailView.as_view(), name="card_detail"),
    # /apps/cards/1/ View form to update card
    path("<int:pk>/update/", views.CardUpdateView.as_view(), name="card_update"),
    # /apps/cards/1/ View to delete card
    path("<int:pk>/delete/", views.CardDeleteView.as_view(), name="card_delete"),
]
