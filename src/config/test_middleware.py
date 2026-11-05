"""Regression tests for canonical origins asserted by a trusted Wormhole proxy."""

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path


def host_details(request):
    """Expose the effective origin and a CSRF token for integration tests."""
    return JsonResponse(
        {
            "host": request.get_host(),
            "raw_host": request.META.get("HTTP_HOST"),
            "secure": request.is_secure(),
            "absolute_url": request.build_absolute_uri("/target/"),
            "csrf_token": get_token(request),
        }
    )


urlpatterns = [path("headers/", host_details)]


@override_settings(
    ROOT_URLCONF=__name__,
    MIDDLEWARE=["config.middleware.NormalizeProxyHostMiddleware", "django.middleware.csrf.CsrfViewMiddleware"],
    TRUST_PROXY_HEADERS=True,
    USE_X_FORWARDED_HOST=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_WORMHOLE_SCHEME", "https"),
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
)
class ProxyHostMiddlewareTests(SimpleTestCase):
    """Accept validated proxy origins without trusting arbitrary client host headers."""

    def setUp(self):
        """Provide canonical headers supplied by the trusted proxy."""
        self.headers = {
            "Host": "wh-piko:8000",
            "X-Wormhole-Host": "app.example.org",
            "X-Wormhole-Scheme": "https",
            "X-Forwarded-Host": "wh-piko:8000",
            "X-Forwarded-Proto": "http",
        }

    def test_canonical_headers_establish_public_origin(self):
        """Discover the public URL without knowing its hostname in configuration."""
        for host in ("app.example.org", "another.users.example.org"):
            with self.subTest(host=host):
                response = self.client.get("/headers/", headers=self.headers | {"X-Wormhole-Host": host})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["host"], host)
                self.assertEqual(response.json()["raw_host"], "wh-piko:8000")
                self.assertTrue(response.json()["secure"])
                self.assertEqual(response.json()["absolute_url"], f"https://{host}/target/")
                self.assertEqual(settings.ALLOWED_HOSTS, ["*"])

    def test_repeated_forwarded_host_is_normalized(self):
        """Collapse repeated forwarded hosts that agree with the canonical origin."""
        response = self.client.get(
            "/headers/", headers=self.headers | {"X-Forwarded-Host": "app.example.org,app.example.org"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["host"], "app.example.org")

    def test_identical_canonical_headers_support_case_whitespace_and_ports(self):
        """Normalize repeated canonical assertions and preserve a valid public port."""
        response = self.client.get(
            "/headers/",
            headers=self.headers
            | {
                "X-Wormhole-Host": "app.example.org:8443, APP.EXAMPLE.ORG:8443 ",
                "X-Wormhole-Scheme": "https, HTTPS ",
                "X-Forwarded-Host": "APP.EXAMPLE.ORG:8443",
                "X-Forwarded-Proto": "https,https",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["absolute_url"], "https://app.example.org:8443/target/")

    def test_internal_host_does_not_override_canonical_origin(self):
        """Ignore the raw backend Host when constructing the public URL."""
        response = self.client.get("/headers/", headers=self.headers | {"Host": "untrusted.example"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["host"], "app.example.org")

    def test_missing_canonical_headers_are_rejected(self):
        """Never fall back to a direct or forwarded host when canonical headers are absent."""
        for missing in ("X-Wormhole-Host", "X-Wormhole-Scheme"):
            with self.subTest(missing=missing):
                headers = {name: value for name, value in self.headers.items() if name != missing}
                headers["X-Forwarded-Host"] = "app.example.org"
                headers["X-Forwarded-Proto"] = "https"
                self.assertEqual(self.client.get("/headers/", headers=headers).status_code, 400)
        self.assertEqual(self.client.get("/headers/").status_code, 400)

    def test_conflicting_and_empty_origin_assertions_are_rejected(self):
        """Reject ambiguous or empty assertions in the authoritative origin headers."""
        for header, value in (
            ("X-Wormhole-Host", "app.example.org,other.example.org"),
            ("X-Wormhole-Host", "app.example.org,"),
            ("X-Wormhole-Host", ",app.example.org"),
            ("X-Wormhole-Host", "app.example.org,,app.example.org"),
            ("X-Wormhole-Scheme", "https,http"),
            ("X-Wormhole-Scheme", ""),
        ):
            with self.subTest(header=header, value=value):
                response = self.client.get("/headers/", headers=self.headers | {header: value})
                self.assertEqual(response.status_code, 400)

    def test_hop_specific_forwarding_headers_cannot_override_canonical_origin(self):
        """Ignore generic forwarding values even when another proxy changes them."""
        for header, value in (
            ("X-Forwarded-Host", "other.example.org"),
            ("X-Forwarded-Host", "app.example.org,wh-piko:8000"),
            ("X-Forwarded-Host", "app.example.org:443"),
            ("X-Forwarded-Host", ""),
            ("X-Forwarded-Proto", "http"),
            ("X-Forwarded-Proto", "https,http"),
            ("X-Forwarded-Proto", ""),
        ):
            with self.subTest(header=header, value=value):
                response = self.client.get("/headers/", headers=self.headers | {header: value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["absolute_url"], "https://app.example.org/target/")
                self.assertTrue(response.json()["secure"])

    def test_invalid_canonical_hosts_are_rejected(self):
        """Reject URLs, malformed hostnames, invalid IPv6 literals, and invalid ports."""
        for host in (
            "https://app.example.org",
            "user@app.example.org",
            "app.example.org/path",
            "app.example.org?query=value",
            "invalid host",
            "app..example.org",
            "app.example.org..",
            "-app.example.org",
            "app-.example.org",
            "long" * 16 + ".example.org",
            "app.example.org:0",
            "app.example.org:65536",
            "app.example.org:999999999999999999",
            "app.example.org:bad",
            "[:::]",
        ):
            with self.subTest(host=host):
                response = self.client.get("/headers/", headers=self.headers | {"X-Wormhole-Host": host})
                self.assertEqual(response.status_code, 400)

    def test_valid_ipv6_canonical_host_is_supported(self):
        """Support bracketed IPv6 origins with a public port."""
        response = self.client.get("/headers/", headers=self.headers | {"X-Wormhole-Host": "[2001:db8::1]:8443"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["absolute_url"], "https://[2001:db8::1]:8443/target/")

    def test_scheme_is_required_to_be_http_or_https(self):
        """Do not construct public origins with arbitrary URL schemes."""
        for scheme in ("ftp", "javascript", "https://", "https,"):
            with self.subTest(scheme=scheme):
                response = self.client.get("/headers/", headers=self.headers | {"X-Wormhole-Scheme": scheme})
                self.assertEqual(response.status_code, 400)
        response = self.client.get("/headers/", headers=self.headers | {"X-Wormhole-Scheme": "http"}, secure=True)
        self.assertFalse(response.json()["secure"])
        self.assertEqual(response.json()["absolute_url"], "http://app.example.org/target/")

    def test_csrf_checks_use_canonical_origin(self):
        """Allow valid same-origin submissions without adding global trusted origins."""
        client = Client(enforce_csrf_checks=True)
        token = client.get("/headers/", headers=self.headers).json()["csrf_token"]
        response = client.post(
            "/headers/", {"csrfmiddlewaretoken": token}, headers=self.headers | {"Origin": "https://app.example.org"}
        )
        self.assertEqual(response.status_code, 200)
        response = client.post(
            "/headers/", {"csrfmiddlewaretoken": token}, headers=self.headers | {"Origin": "https://untrusted.example"}
        )
        self.assertEqual(response.status_code, 403)
        response = client.post("/headers/", headers=self.headers | {"Origin": "https://app.example.org"})
        self.assertEqual(response.status_code, 403)

    def test_csrf_referer_checks_use_canonical_origin(self):
        """Validate secure referers when a browser sends no Origin header."""
        client = Client(enforce_csrf_checks=True)
        token = client.get("/headers/", headers=self.headers).json()["csrf_token"]
        for referer, expected in (("https://app.example.org/form/", 200), ("https://untrusted.example/form/", 403)):
            with self.subTest(referer=referer):
                response = client.post(
                    "/headers/", {"csrfmiddlewaretoken": token}, headers=self.headers | {"Referer": referer}
                )
                self.assertEqual(response.status_code, expected)

    @override_settings(
        TRUST_PROXY_HEADERS=False,
        USE_X_FORWARDED_HOST=False,
        SECURE_PROXY_SSL_HEADER=None,
        ALLOWED_HOSTS=["localhost"],
    )
    def test_local_mode_ignores_canonical_and_forwarded_origins(self):
        """Keep normal host allowlisting and scheme detection outside trusted mode."""
        response = self.client.get(
            "/headers/", headers=self.headers | {"Host": "localhost:8000", "X-Forwarded-Host": "other.example.org"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["host"], "localhost:8000")
        self.assertFalse(response.json()["secure"])
        self.assertEqual(response.json()["absolute_url"], "http://localhost:8000/target/")
        response = self.client.get("/headers/", headers=self.headers | {"Host": "app.example.org,app.example.org"})
        self.assertEqual(response.status_code, 400)
