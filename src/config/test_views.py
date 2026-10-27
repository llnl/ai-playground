"""Tests for the application's proxy-aware login view."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from config.views import application_login


@override_settings(PROXY_AUTH_ENABLED=True, ALLOWED_HOSTS=["testserver"])
class ApplicationLoginTests(SimpleTestCase):
    """Ensure proxy login failures are clear and redirects stay on this site."""

    def test_anonymous_proxy_login_returns_clear_forbidden_response(self):
        """Report failed proxy authentication instead of loading a missing template."""
        request = RequestFactory().get("/accounts/login/")
        request.user = SimpleNamespace(is_authenticated=False)
        response = application_login(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Proxy authentication failed", response.content)
        self.assertIn("no-store", response["Cache-Control"])

    def test_authenticated_login_redirects_to_safe_destination(self):
        """Send already authenticated users to the requested local page."""
        request = RequestFactory().get("/accounts/login/", {"next": "/apps/cards/all/?category=agent"})
        request.user = SimpleNamespace(is_authenticated=True)
        response = application_login(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/apps/cards/all/?category=agent")

    def test_external_redirect_is_rejected(self):
        """Prevent proxy login from redirecting users to untrusted hosts."""
        for next_url in ("https://untrusted.example/", "//untrusted.example/"):
            with self.subTest(next_url=next_url):
                request = RequestFactory().get("/accounts/login/", {"next": next_url})
                request.user = SimpleNamespace(is_authenticated=True)
                self.assertEqual(application_login(request)["Location"], "/")

    @override_settings(PROXY_AUTH_ENABLED=False)
    def test_local_mode_still_uses_django_login(self):
        """Leave the existing local authentication flow unchanged."""
        request = RequestFactory().get("/accounts/login/")
        with patch("config.views.LoginView.as_view") as local_login:
            application_login(request)
        local_login.return_value.assert_called_once_with(request)
