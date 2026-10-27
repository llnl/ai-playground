"""Gunicorn settings for the container's WSGI application."""

from pathlib import Path

chdir = str(Path(__file__).resolve().parent / "src")
wsgi_app = "config.wsgi:application"
bind = "0.0.0.0:8000"
accesslog = "-"
errorlog = "-"
control_socket_disable = True
