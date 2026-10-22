"""Tests for the cards REST API."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Cards


class CardAPITests(APITestCase):
    """Verify authentication, ownership, permissions, and category routes."""

    def setUp(self) -> None:
        """Create users and a representative card for each test."""
        self.user = get_user_model().objects.create_user(username="owner", password="password")
        self.other_user = get_user_model().objects.create_user(username="other", password="password")
        self.card = Cards.objects.create(
            owner=self.user,
            name="Test card",
            description="A test card",
            category=Cards.Category.AGENT,
        )

    def test_requests_require_login(self) -> None:
        """Reject requests that do not have an authenticated user."""
        response = self.client.get("/api/v1/cards/")
        self.assertEqual(response.status_code, 403)

    def test_authenticated_user_can_list_and_create(self) -> None:
        """Allow authenticated users to list and create owned cards."""
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/v1/cards/").status_code, 200)
        response = self.client.post(
            "/api/v1/cards/",
            {"name": "New", "description": "Desc", "category": "mcp_server"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["owner"], self.user.id)

    def test_only_owner_can_update(self) -> None:
        """Reject a partial update from an unrelated authenticated user."""
        self.client.force_authenticate(self.other_user)
        response = self.client.patch(f"/api/v1/cards/{self.card.pk}/", {"name": "Changed"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_category_endpoint(self) -> None:
        """Return cards matching the agent category route."""
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/cards/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
