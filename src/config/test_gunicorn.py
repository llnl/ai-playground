"""Tests for the container's dedicated Gunicorn configuration."""

import runpy
from pathlib import Path

from django.test import SimpleTestCase
from gunicorn.config import Config


class GunicornConfigTests(SimpleTestCase):
    """Verify the configuration preserves the container's runtime settings."""

    def test_container_configuration_is_valid(self):
        """Validate settings with Gunicorn without starting a server or importing Django's WSGI app."""
        repository_root = Path(__file__).resolve().parents[2]
        configuration = runpy.run_path(str(repository_root / "gunicorn.conf.py"))
        gunicorn = Config()
        for name in ("chdir", "wsgi_app", "bind", "accesslog", "errorlog", "control_socket_disable"):
            gunicorn.set(name, configuration[name])
        self.assertEqual(gunicorn.chdir, str(repository_root / "src"))
        self.assertEqual(gunicorn.wsgi_app, "config.wsgi:application")
        self.assertEqual(gunicorn.bind, ["0.0.0.0:8000"])
        self.assertEqual(gunicorn.accesslog, "-")
        self.assertEqual(gunicorn.errorlog, "-")
        self.assertTrue(gunicorn.control_socket_disable)
