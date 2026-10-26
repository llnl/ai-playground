"""Tests for environment-configured host validation and trusted proxy settings."""

import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import NormalizeProxyHostMiddleware


class ProxySettingsTests(SimpleTestCase):
    """Validate configuration without loading credentials or connecting to a database."""

    def load_settings(self, **environment):
        """Load the settings module with a controlled environment and no dotenv file."""
        base_environment = dict.fromkeys(
            ("SECRET_KEY", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"), "settings-test-only"
        )
        with patch.dict(os.environ, base_environment | environment, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def test_default_configuration_does_not_trust_proxy_headers(self):
        """Use local hosts, non-debug mode, and ordinary authentication by default."""
        configuration = self.load_settings()
        self.assertFalse(configuration["DEBUG"])
        self.assertEqual(configuration["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]"])
        self.assertFalse(configuration["PROXY_AUTH_ENABLED"])
        self.assertFalse(configuration["USE_X_FORWARDED_HOST"])
        self.assertIsNone(configuration["SECURE_PROXY_SSL_HEADER"])
        self.assertEqual(configuration["AUTHENTICATION_BACKENDS"], ["django.contrib.auth.backends.ModelBackend"])
        self.assertNotIn("config.proxy_auth.ProxyUserMiddleware", configuration["MIDDLEWARE"])
        self.assertNotIn("config.middleware.NormalizeProxyHostMiddleware", configuration["MIDDLEWARE"])

    def test_proxy_authentication_enables_forwarding_trust(self):
        """Install remote authentication after normal authentication middleware."""
        configuration = self.load_settings(PROXY_AUTH_ENABLED="true")
        self.assertTrue(configuration["TRUST_PROXY_HEADERS"])
        self.assertEqual(configuration["ALLOWED_HOSTS"], ["*"])
        self.assertTrue(configuration["USE_X_FORWARDED_HOST"])
        self.assertEqual(configuration["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_WORMHOLE_SCHEME", "https"))
        self.assertEqual(configuration["AUTHENTICATION_BACKENDS"], ["config.proxy_auth.ProxyUserBackend"])
        middleware = configuration["MIDDLEWARE"]
        self.assertEqual(middleware[0], "config.middleware.NormalizeProxyHostMiddleware")
        self.assertEqual(
            middleware.index("config.proxy_auth.ProxyUserMiddleware"),
            middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        )

    def test_forwarding_trust_can_be_configured_independently(self):
        """Allow trusted proxy deployment with or without remote authentication."""
        for authentication, trust in (("false", "true"), ("true", "false")):
            with self.subTest(authentication=authentication, trust=trust):
                configuration = self.load_settings(PROXY_AUTH_ENABLED=authentication, TRUST_PROXY_HEADERS=trust)
                self.assertEqual(configuration["TRUST_PROXY_HEADERS"], trust == "true")
                self.assertEqual(configuration["PROXY_AUTH_ENABLED"], authentication == "true")
                self.assertEqual(configuration["USE_X_FORWARDED_HOST"], trust == "true")
                self.assertEqual(
                    "config.middleware.NormalizeProxyHostMiddleware" in configuration["MIDDLEWARE"], trust == "true"
                )
                self.assertEqual(
                    configuration["SECURE_PROXY_SSL_HEADER"],
                    ("HTTP_X_WORMHOLE_SCHEME", "https") if trust == "true" else None,
                )

    def test_explicit_hosts_and_debug_are_environment_controlled(self):
        """Trim host lists and parse explicit debug and proxy flags."""
        configuration = self.load_settings(
            ALLOWED_HOSTS=" app.example.org, localhost, ,", DEBUG=" TRUE ", PROXY_AUTH_ENABLED=" FALSE "
        )
        self.assertEqual(configuration["ALLOWED_HOSTS"], ["app.example.org", "localhost"])
        self.assertTrue(configuration["DEBUG"])
        self.assertFalse(configuration["PROXY_AUTH_ENABLED"])

    def test_trusted_proxy_does_not_require_a_configured_hostname(self):
        """Use mandatory canonical-header validation instead of a static allowlist."""
        configuration = self.load_settings(PROXY_AUTH_ENABLED=" TRUE ", ALLOWED_HOSTS="old.example.org")
        self.assertTrue(configuration["PROXY_AUTH_ENABLED"])
        self.assertEqual(configuration["ALLOWED_HOSTS"], ["*"])

    def test_local_requests_ignore_forwarding_headers(self):
        """Do not accept an untrusted forwarded host or HTTPS claim in local mode."""
        configuration = self.load_settings()
        with override_settings(
            **{
                name: configuration[name]
                for name in ("ALLOWED_HOSTS", "USE_X_FORWARDED_HOST", "SECURE_PROXY_SSL_HEADER", "DEBUG")
            }
        ):
            request = RequestFactory().get(
                "/",
                headers={
                    "Host": "localhost:8000",
                    "X-Forwarded-Host": "untrusted.example",
                    "X-Forwarded-Proto": "https",
                },
            )
            self.assertEqual(request.get_host(), "localhost:8000")
            self.assertFalse(request.is_secure())

    def test_proxy_requests_validate_the_canonical_host_and_scheme(self):
        """Apply runtime configuration to the captured canonical header shape."""
        configuration = self.load_settings(PROXY_AUTH_ENABLED="true")
        with override_settings(
            **{
                name: configuration[name]
                for name in (
                    "ALLOWED_HOSTS",
                    "USE_X_FORWARDED_HOST",
                    "SECURE_PROXY_SSL_HEADER",
                    "DEBUG",
                    "TRUST_PROXY_HEADERS",
                )
            }
        ):
            request = RequestFactory().get(
                "/",
                headers={
                    "Host": "wh-piko:8000",
                    "X-Wormhole-Host": "app.example.org",
                    "X-Wormhole-Scheme": "https",
                    "X-Forwarded-Host": "app.example.org",
                    "X-Forwarded-Proto": "https",
                },
            )
            NormalizeProxyHostMiddleware(lambda request: HttpResponse())(request)
            self.assertEqual(request.get_host(), "app.example.org")
            self.assertTrue(request.is_secure())
