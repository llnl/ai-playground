"""Tests for the temporary request header diagnostic endpoint."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import path

from config.diagnostics import diagnostic_headers

urlpatterns = [path("diagnostics/headers/", diagnostic_headers)]


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=[], PROXY_AUTH_ENABLED=False)
class DiagnosticHeadersTests(SimpleTestCase):
    """Verify opt-in access, credential redaction, and cache protection."""

    @override_settings(HEADER_DIAGNOSTICS_ENABLED=False)
    def test_disabled_endpoint_returns_not_found(self):
        """Hide diagnostics unless explicitly enabled."""
        self.assertEqual(self.client.get("/diagnostics/headers/").status_code, 404)

    @override_settings(HEADER_DIAGNOSTICS_ENABLED=True)
    def test_identity_headers_visible_and_credentials_redacted(self):
        """Expose proxy identity fields without exposing common credential headers."""
        response = self.client.get(
            "/diagnostics/headers/",
            headers={
                "X-Forwarded-User": "example-user",
                "X-Forwarded-Groups": "group-one,group-two",
                "Authorization": "Bearer example",
                "Cookie": "sessionid=example",
                "X-Auth-Request-Access-Token": "example",
                "X-Api-Key": "example",
                "X-Client-Secret": "example",
                "X-Credential": "example",
                "X-Password": "example",
            },
        )
        self.assertEqual(response.status_code, 200)
        headers = response.json()["headers"]
        self.assertEqual(headers["X-Forwarded-User"], "example-user")
        self.assertEqual(headers["X-Forwarded-Groups"], "group-one,group-two")
        for name in (
            "Authorization",
            "Cookie",
            "X-Auth-Request-Access-Token",
            "X-Api-Key",
            "X-Client-Secret",
            "X-Credential",
            "X-Password",
        ):
            with self.subTest(header=name):
                self.assertEqual(headers[name], "[REDACTED]")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    @override_settings(
        HEADER_DIAGNOSTICS_ENABLED=True,
        PROXY_AUTH_ENABLED=True,
        MIDDLEWARE=["config.proxy_auth.ProxyUserMiddleware"],
    )
    def test_authentication_status_exposes_runtime_configuration(self):
        """Distinguish missing identity headers from disabled runtime configuration."""
        request = RequestFactory().get("/diagnostics/headers/", headers={"X-Forwarded-User": "example-user"})
        request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "example-user")
        status = json.loads(diagnostic_headers(request).content)["authentication"]
        self.assertEqual(
            status,
            {
                "proxy_enabled": True,
                "proxy_middleware_installed": True,
                "user_header_present": True,
                "authenticated": True,
                "username": "example-user",
            },
        )

    def test_diagnostics_work_without_proxy_authentication_settings(self):
        """Keep the diagnostic endpoint independent of the proxy login feature."""
        request = RequestFactory().get("/diagnostics/headers/")
        configuration = SimpleNamespace(HEADER_DIAGNOSTICS_ENABLED=True, MIDDLEWARE=[])
        with patch("config.diagnostics.settings", configuration):
            status = json.loads(diagnostic_headers(request).content)["authentication"]
        self.assertFalse(status["proxy_enabled"])
        self.assertFalse(status["proxy_middleware_installed"])
        self.assertFalse(status["user_header_present"])
        self.assertFalse(status["authenticated"])
        self.assertIsNone(status["username"])

    @override_settings(HEADER_DIAGNOSTICS_ENABLED=True)
    def test_only_get_is_allowed(self):
        """Reject methods other than GET."""
        response = self.client.post("/diagnostics/headers/")
        self.assertEqual(response.status_code, 405)
        self.assertIn("no-store", response["Cache-Control"])
