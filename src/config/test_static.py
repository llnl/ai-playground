"""Integration tests for collected static assets served without Django debug mode."""

from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

urlpatterns = []


@skipUnless(find_spec("whitenoise"), "Install the WhiteNoise dependency to run static serving tests.")
@override_settings(
    INSTALLED_APPS=["django.contrib.staticfiles"],
    ROOT_URLCONF=__name__,
    DEBUG=False,
    ALLOWED_HOSTS=["testserver"],
    STATIC_URL="/static/",
    STATICFILES_DIRS=[Path(__file__).resolve().parent.parent / "static"],
    WHITENOISE_AUTOREFRESH=False,
    MIDDLEWARE=["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware"],
)
class StaticServingTests(SimpleTestCase):
    """Verify collected CSS delivery and preservation of trusted proxy boundaries."""

    def setUp(self):
        """Collect assets into an isolated temporary directory."""
        static_directory = TemporaryDirectory()
        self.addCleanup(static_directory.cleanup)
        configuration = override_settings(STATIC_ROOT=static_directory.name)
        configuration.enable()
        self.addCleanup(configuration.disable)
        call_command("collectstatic", interactive=False, verbosity=0)

    def test_main_stylesheet_is_served_without_debug(self):
        """Serve the stylesheet referenced by the shared page template."""
        response = self.client.get("/static/css/main.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response["Content-Type"])
        self.assertIn(b"base.css", b"".join(response.streaming_content))

    def test_imported_stylesheet_is_served_and_unknown_assets_return_not_found(self):
        """Resolve CSS imports without exposing nonexistent asset paths."""
        self.assertEqual(self.client.get("/static/css/components/navbar.css").status_code, 200)
        self.assertEqual(self.client.get("/static/css/nonexistent.css").status_code, 404)

    @override_settings(
        TRUST_PROXY_HEADERS=True,
        ALLOWED_HOSTS=["*"],
        USE_X_FORWARDED_HOST=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_WORMHOLE_SCHEME", "https"),
        MIDDLEWARE=[
            "config.middleware.NormalizeProxyHostMiddleware",
            "django.middleware.security.SecurityMiddleware",
            "whitenoise.middleware.WhiteNoiseMiddleware",
        ],
    )
    def test_proxy_origin_validation_precedes_static_serving(self):
        """Require canonical proxy headers even for static asset requests."""
        self.assertEqual(self.client.get("/static/css/main.css").status_code, 400)
        headers = {
            "X-Wormhole-Host": "generated.example.org",
            "X-Wormhole-Scheme": "https",
            "X-Forwarded-Host": "wh-piko:8000",
            "X-Forwarded-Proto": "http",
        }
        self.assertEqual(self.client.get("/static/css/main.css", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.get(
                "/static/css/main.css", headers=headers | {"X-Wormhole-Host": "generated.example.org,other.example.org"}
            ).status_code,
            400,
        )
