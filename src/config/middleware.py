"""Establish the public origin asserted by an explicitly trusted Wormhole proxy."""

from ipaddress import IPv6Address

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http.request import split_domain_port


class NormalizeProxyHostMiddleware:
    """Require a valid canonical proxy origin before any other middleware runs."""

    def __init__(self, get_response):
        """Store the next middleware handler."""
        self.get_response = get_response

    def __call__(self, request):
        """Validate the canonical origin and replace hop-specific forwarding values."""
        if settings.TRUST_PROXY_HEADERS:
            host = self.normalize_header(request.META.get("HTTP_X_WORMHOLE_HOST", ""))
            scheme = self.normalize_header(request.META.get("HTTP_X_WORMHOLE_SCHEME", ""))
            self.validate_host(host)
            if scheme not in ("http", "https"):
                raise DisallowedHost("Proxy scheme must be http or https.")
            request.META["HTTP_X_WORMHOLE_HOST"] = host
            request.META["HTTP_X_WORMHOLE_SCHEME"] = scheme
            request.META["HTTP_X_FORWARDED_HOST"] = host
            request.META["HTTP_X_FORWARDED_PROTO"] = scheme
            request.get_host()
        return self.get_response(request)

    def normalize_header(self, value):
        """Require nonempty identical values and normalize whitespace and letter case."""
        values = [part.strip().lower() for part in value.split(",")]
        if not values[0] or any(part != values[0] for part in values):
            raise DisallowedHost("Proxy origin header is missing or contains conflicting or empty values.")
        return values[0]

    def validate_host(self, host):
        """Accept a hostname or bracketed IPv6 address with an optional valid port."""
        domain, port = split_domain_port(host)
        if not domain or len(domain) > 253 or (port and (len(port) > 5 or not 1 <= int(port) <= 65535)):
            raise DisallowedHost("Invalid canonical proxy host.")
        if domain.startswith("["):
            try:
                IPv6Address(domain[1:-1])
            except ValueError as error:
                raise DisallowedHost("Invalid canonical proxy IPv6 address.") from error
        elif any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in domain.split(".")
        ):
            raise DisallowedHost("Invalid canonical proxy hostname.")
