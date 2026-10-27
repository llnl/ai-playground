"""Use the real application settings with an isolated SQLite database for image tests."""

from config import settings as application_settings

globals().update({name: value for name, value in vars(application_settings).items() if name.isupper()})

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/app/.container-smoke.sqlite3",
    },
}
