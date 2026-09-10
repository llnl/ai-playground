"""Top level views for website."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Render the home page.

    Args:
        request (HttpRequest): The incoming HTTP request.

    Returns:
        HttpResponse: An HTTP response containing the rendered home page.
    """
    return render(request, "home.html")
