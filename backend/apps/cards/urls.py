from django.urls import path

from . import views

app_name = "cards"
urlpatterns = [
    # ex: /cards/
    # path("", views.IndexView.as_view(), name="index"),

    # ex: /cards/create
    path("create/", views.CardCreateView.as_view(), name="card_create"),

    # ex: /cards/1/ # primary key links to row in database
    path("<int:pk>/", views.CardDetailView.as_view(), name="card_detail"),

    # ex: /cards/all/
    path("all/", views.CardAllView.as_view(), name="card_all"),
    # ex: /cards/mcp_servers/
    path("mcp_servers/", views.CardMCPServersView.as_view(), name="card_mcp_servers"),
    # ex: /cards/agents/
    path("agents/", views.CardAgentsView.as_view(), name="card_agents"),
    # ex: /cards/skills/
    path("skills/", views.CardSkillsView.as_view(), name="card_skills"),

    path("trending/", views.CardTrendingView.as_view(), name="trending"),
    path("my_cards/", views.MyCardListView.as_view(), name="my_cards"),
    path("<int:pk>/update/", views.CardUpdateView.as_view(), name="card_update"),
    path("<int:pk>/delete/", views.CardDeleteView.as_view(), name="card_delete"),
]
