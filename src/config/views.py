"""Top level views for website."""

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache


def home(request: HttpRequest) -> HttpResponse:
    """Render the home page.

    Args:
        request (HttpRequest): The incoming HTTP request.

    Returns:
        HttpResponse: An HTTP response containing the rendered home page.
    """
    return render(request, "home.html")


@never_cache
def application_login(request: HttpRequest) -> HttpResponse:
    """Use local login normally, but never show a password form in proxy mode."""
    if not settings.PROXY_AUTH_ENABLED:
        return LoginView.as_view()(request)
    if not request.user.is_authenticated:
        return HttpResponse(
            "Proxy authentication failed: no active authenticated user was established. "
            "Check that the server was restarted with PROXY_AUTH_ENABLED=true, "
            "that the proxy sends X-Forwarded-User on this request, and that the account is active.",
            status=403,
            content_type="text/plain",
        )
    next_url = request.GET.get("next", "/")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    return redirect(next_url)
