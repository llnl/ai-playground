"""Temporary opt-in request header diagnostics for troubleshooting deployments."""

from django.conf import settings
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def diagnostic_headers(request: HttpRequest) -> JsonResponse:
    """Return received headers and authentication status, redacting common credentials."""
    if not settings.HEADER_DIAGNOSTICS_ENABLED:
        raise Http404

    sensitive_parts = ("authorization", "cookie", "token", "secret", "key", "credential", "password")
    headers = {
        name: "[REDACTED]" if any(part in name.lower() for part in sensitive_parts) else value
        for name, value in request.headers.items()
    }
    user = getattr(request, "user", None)
    authenticated = bool(user and user.is_authenticated)
    response = JsonResponse(
        {
            "headers": headers,
            "authentication": {
                "proxy_enabled": getattr(settings, "PROXY_AUTH_ENABLED", False),
                "proxy_middleware_installed": "config.proxy_auth.ProxyUserMiddleware" in settings.MIDDLEWARE,
                "user_header_present": bool(request.headers.get("X-Forwarded-User", "").strip()),
                "authenticated": authenticated,
                "username": user.get_username() if authenticated else None,
            },
        },
        json_dumps_params={"indent": 2},
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
