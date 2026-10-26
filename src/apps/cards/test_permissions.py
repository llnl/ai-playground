"""Regression tests for card ownership and email-based maintainer permissions."""

import json

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from .models import Cards
from .views import owned_or_maintained_filter


class CardAccessFilterTests(SimpleTestCase):
    """Check permission predicates and template controls without a database."""

    def test_blank_email_filter_matches_only_ownership(self):
        """Never add a blank-email maintainer predicate."""
        user = get_user_model()(pk=1, username="proxy-user", email="")
        self.assertEqual(owned_or_maintained_filter(user), Q(owner=user))

    def test_nonempty_email_filter_matches_ownership_or_maintenance(self):
        """Keep the existing maintainer predicate for a nonempty email."""
        user = get_user_model()(pk=1, username="maintainer", email="maintainer@example.org")
        self.assertEqual(
            owned_or_maintained_filter(user), Q(owner=user) | Q(maintainers__contains=[{"email": user.email}])
        )

    def test_detail_controls_require_ownership_or_nonempty_maintainer_email(self):
        """Exclude empty and missing emails from the detail template's permission checks."""
        user = get_user_model()(pk=1, username="proxy-user", email="")
        owner = get_user_model()(pk=2, username="owner", email="")
        card = Cards(
            pk=1,
            owner=owner,
            name="Card",
            maintainers=[{"email": ""}, {}, {"email": "maintainer@example.org"}],
        )
        self.assertEqual(card.maintainer_emails, ["maintainer@example.org"])
        content = render_to_string("cards/detail.html", {"user": user, "card": card})
        self.assertNotIn("Update resource", content)
        self.assertNotIn("Delete resource", content)
        for permitted_user in (owner, get_user_model()(pk=3, email="maintainer@example.org")):
            with self.subTest(user=permitted_user.pk):
                content = render_to_string("cards/detail.html", {"user": permitted_user, "card": card})
                self.assertIn("Update resource", content)
                self.assertIn("Delete resource", content)


@override_settings(
    PROXY_AUTH_ENABLED=False,
    TRUST_PROXY_HEADERS=False,
    AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"],
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ],
)
@skipUnlessDBFeature("supports_json_field_contains")
class CardPermissionsTests(TestCase):
    """Exercise authorization against a database supporting JSON containment."""

    def setUp(self):
        """Create an owner, a blank-email user, and a card with a blank maintainer email."""
        self.owner = get_user_model().objects.create_user(username="owner")
        self.user = get_user_model().objects.create_user(username="proxy-user")
        self.card = Cards.objects.create(
            owner=self.owner,
            name="Another user's card",
            description="Only its owner may change this card.",
            maintainers=[{"name": "Unidentified maintainer", "email": ""}, {"name": "Missing email"}],
        )
        self.client.force_login(self.user)

    def test_blank_email_cannot_update_another_users_card(self):
        """Reject both the update form and a direct update submission."""
        url = reverse("cards:card_update", args=[self.card.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"name": "Changed", "description": "Changed"}).status_code, 404)
        self.card.refresh_from_db()
        self.assertEqual(self.card.name, "Another user's card")

    def test_blank_email_cannot_delete_another_users_card(self):
        """Reject both deletion confirmation and a direct deletion submission."""
        url = reverse("cards:card_delete", args=[self.card.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Cards.objects.filter(pk=self.card.pk).exists())

    def test_blank_email_my_cards_contains_only_owned_cards(self):
        """Do not list unrelated cards as maintained by every blank-email account."""
        owned = Cards.objects.create(owner=self.user, name="Owned card", description="Owned")
        response = self.client.get(reverse("cards:card_all"), {"owner": "me"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cards"]), [owned])

    def test_blank_email_detail_hides_update_and_delete_controls(self):
        """Keep template permissions consistent with server-side authorization."""
        response = self.client.get(reverse("cards:card_detail", args=[self.card.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Update resource")
        self.assertNotContains(response, "Delete resource")
        self.assertEqual(self.card.maintainer_emails, [])

    def test_blank_email_owner_can_update_and_delete(self):
        """Preserve ownership access without requiring an email address."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("cards:card_update", args=[self.card.pk]), {"name": "Updated", "description": "Updated"}
        )
        self.assertEqual(response.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.name, "Updated")
        self.assertEqual(self.client.post(reverse("cards:card_delete", args=[self.card.pk])).status_code, 302)
        self.assertFalse(Cards.objects.filter(pk=self.card.pk).exists())

    def test_nonempty_email_maintainer_retains_access(self):
        """Preserve maintainer listing, controls, updates, and deletion for a real email."""
        self.user.email = "maintainer@example.org"
        self.user.save(update_fields=["email"])
        self.card.maintainers.append({"name": "Maintainer", "email": self.user.email})
        self.card.save(update_fields=["maintainers"])
        response = self.client.get(reverse("cards:card_all"), {"owner": "me"})
        self.assertEqual(list(response.context["cards"]), [self.card])
        response = self.client.get(reverse("cards:card_detail", args=[self.card.pk]))
        self.assertContains(response, "Update resource")
        self.assertContains(response, "Delete resource")
        self.assertEqual(
            self.client.post(
                reverse("cards:card_update", args=[self.card.pk]),
                {"name": "Updated", "description": "Updated", "maintainers": json.dumps(self.card.maintainers)},
            ).status_code,
            302,
        )
        self.card.refresh_from_db()
        self.assertEqual(self.card.name, "Updated")
        self.assertEqual(self.client.post(reverse("cards:card_delete", args=[self.card.pk])).status_code, 302)
        self.assertFalse(Cards.objects.filter(pk=self.card.pk).exists())

    def test_staff_and_superusers_retain_access_without_email(self):
        """Preserve administrative access regardless of ownership or maintainer email."""
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag):
                setattr(self.user, flag, True)
                self.user.save(update_fields=[flag])
                response = self.client.get(reverse("cards:card_all"), {"owner": "me"})
                self.assertEqual(list(response.context["cards"]), [self.card])
                response = self.client.get(reverse("cards:card_detail", args=[self.card.pk]))
                self.assertContains(response, "Update resource")
                self.assertContains(response, "Delete resource")
                for route in ("cards:card_update", "cards:card_delete"):
                    self.assertEqual(self.client.get(reverse(route, args=[self.card.pk])).status_code, 200)
                setattr(self.user, flag, False)
                self.user.save(update_fields=[flag])
