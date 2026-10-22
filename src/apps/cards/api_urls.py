"""URL routes for the versioned cards REST API.

The router generates standard collection and detail routes under
``/api/v1/cards/`` for GET, POST, PUT, PATCH, and DELETE, along with the
category-specific collection actions declared by ``CardViewSet``.
"""

from rest_framework.routers import DefaultRouter

from .api import CardViewSet

router = DefaultRouter()
router.register("cards", CardViewSet, basename="card")

urlpatterns = router.urls
