"""Integration tests for proxy identity authentication and group synchronization."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import JsonResponse
from django.test import TestCase, override_settings
from django.urls import path


def identity(request):
    """Expose the authenticated identity for middleware integration tests."""
    return JsonResponse({"username": request.user.get_username(), "authenticated": request.user.is_authenticated})


urlpatterns = [path("identity/", identity)]


@override_settings(
    ROOT_URLCONF=__name__,
    AUTHENTICATION_BACKENDS=["config.proxy_auth.ProxyUserBackend"],
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "config.proxy_auth.ProxyUserMiddleware",
    ],
)
class ProxyAuthTests(TestCase):
    """Exercise login, session changes, and proxy group ownership."""

    def test_first_request_provisions_and_logs_in_user(self):
        """Create an ordinary account from the trusted identity header."""
        response = self.client.get(
            "/identity/", headers={"X-Forwarded-User": "example-user", "X-Forwarded-Groups": "team-one,team-two"}
        )
        self.assertEqual(response.json(), {"username": "example-user", "authenticated": True})
        user = get_user_model().objects.get(username="example-user")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.email, "")
        self.assertSetEqual(set(user.groups.values_list("name", flat=True)), {"proxy:team-one", "proxy:team-two"})

    def test_existing_user_and_local_groups_are_preserved(self):
        """Keep the existing account, email, and locally assigned memberships."""
        user = get_user_model().objects.create_user(username="example-user", email="example@example.org")
        local_group = Group.objects.create(name="local-editors")
        matching_local_group = Group.objects.create(name="team-one")
        user.groups.add(local_group, matching_local_group)
        self.client.get(
            "/identity/", headers={"X-Forwarded-User": "example-user", "X-Forwarded-Groups": "team-one,team-two"}
        )
        self.client.get(
            "/identity/", headers={"X-Forwarded-User": "example-user", "X-Forwarded-Groups": " team-two , team-two, "}
        )
        user.refresh_from_db()
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(user.email, "example@example.org")
        self.assertSetEqual(
            set(user.groups.values_list("name", flat=True)), {"local-editors", "team-one", "proxy:team-two"}
        )

    def test_missing_groups_clear_proxy_memberships(self):
        """Remove stale proxy groups when the groups header disappears."""
        self.client.get("/identity/", headers={"X-Forwarded-User": "example-user", "X-Forwarded-Groups": "team-one"})
        self.client.get("/identity/", headers={"X-Forwarded-User": "example-user"})
        self.assertFalse(get_user_model().objects.get(username="example-user").groups.exists())

    def test_missing_or_blank_identity_logs_out_proxy_session(self):
        """Require a nonempty identity header on every authenticated request."""
        for headers in ({}, {"X-Forwarded-User": "   "}):
            with self.subTest(headers=headers):
                self.client.get("/identity/", headers={"X-Forwarded-User": "example-user"})
                response = self.client.get("/identity/", headers=headers)
                self.assertFalse(response.json()["authenticated"])

    def test_changed_identity_switches_users(self):
        """Never retain a previous user's session when the proxy identity changes."""
        self.client.get("/identity/", headers={"X-Forwarded-User": "first-user"})
        response = self.client.get("/identity/", headers={"X-Forwarded-User": "second-user"})
        self.assertEqual(response.json()["username"], "second-user")

    @override_settings(
        TRUST_PROXY_HEADERS=True,
        ALLOWED_HOSTS=["*"],
        USE_X_FORWARDED_HOST=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_WORMHOLE_SCHEME", "https"),
        MIDDLEWARE=[
            "config.middleware.NormalizeProxyHostMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "config.proxy_auth.ProxyUserMiddleware",
        ],
    )
    def test_canonical_origin_is_required_before_proxy_login(self):
        """Authenticate dynamic proxy hosts only after canonical origin validation."""
        response = self.client.get("/identity/", headers={"X-Forwarded-User": "example-user"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.exists())
        response = self.client.get(
            "/identity/",
            headers={
                "Host": "wh-piko:8000",
                "X-Wormhole-Host": "generated.users.example.org",
                "X-Wormhole-Scheme": "https",
                "X-Forwarded-Host": "generated.users.example.org,generated.users.example.org",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-User": "example-user",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"username": "example-user", "authenticated": True})
        self.assertEqual(response.wsgi_request.get_host(), "generated.users.example.org")
        self.assertTrue(response.wsgi_request.is_secure())

    def test_inactive_users_cannot_log_in(self):
        """Respect Django account deactivation."""
        get_user_model().objects.create_user(username="example-user", is_active=False)
        response = self.client.get("/identity/", headers={"X-Forwarded-User": "example-user"})
        self.assertFalse(response.json()["authenticated"])

    async def test_async_requests_use_forwarded_identity(self):
        """Support ASGI requests through Django's synchronous middleware adapter."""
        response = await self.async_client.get(
            "/identity/", headers={"X-Forwarded-User": "async-user", "X-Forwarded-Groups": "team-one"}
        )
        self.assertEqual(response.json(), {"username": "async-user", "authenticated": True})
        response = await self.async_client.get("/identity/")
        self.assertFalse(response.json()["authenticated"])

    def test_invalid_headers_are_rejected(self):
        """Reject invalid identities and oversized group names without provisioning."""
        for headers in (
            {"X-Forwarded-User": "invalid user"},
            {"X-Forwarded-User": "example-user", "X-Forwarded-Groups": "group" * 40},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get("/identity/", headers=headers).status_code, 403)
        self.assertFalse(get_user_model().objects.exists())

    @override_settings(
        AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
    )
    def test_disabled_mode_ignores_forwarded_identity(self):
        """Keep ordinary authentication unchanged when proxy middleware is absent."""
        response = self.client.get("/identity/", headers={"X-Forwarded-User": "example-user"})
        self.assertFalse(response.json()["authenticated"])
        self.assertFalse(get_user_model().objects.exists())
