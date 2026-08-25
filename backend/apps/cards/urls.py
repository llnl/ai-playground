from django.urls import path

from . import views

app_name = "cards"
urlpatterns = [
    # ex: /cards/
    # path("", views.IndexView.as_view(), name="index"),
    # ex: /cards/new
    path("new/", views.CardCreateView.as_view(), name="card_create"),
    # ex: /cards/success
    path("success/", views.card_success, name="card_success"),
    # # ex: /cards/vertex_cfd/
    # path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    # ex: /cards/all/
    path("all/", views.CardAllView.as_view(), name="card_list"),
    # # ex: /cards/category/ e.g. simulation, geometry, etc..?
    # path("<int:question_id>/vote/", views.vote, name="vote"),
]
