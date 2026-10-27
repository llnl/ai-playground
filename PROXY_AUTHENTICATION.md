# Proxy authentication

This document covers upstream proxy authentication, trusted-origin handling,
user and group synchronization, and request-header diagnostics.

## Configuration

To automatically log in users authenticated by the upstream proxy, set
`PROXY_AUTH_ENABLED=true` in `src/.env` (or the server environment) and restart.
The proxy must supply `X-Forwarded-User` on every request and may supply
`X-Forwarded-Groups` as a comma-separated list. No additional packages or model
migrations are required beyond the existing Django auth tables.

Wormhole supplies the public origin, so no generated hostname needs to be
configured in advance. For example, add these settings to `src/.env`:

```dotenv
PROXY_AUTH_ENABLED=true
DEBUG=false
```

`DEBUG` defaults to false and is independent of authentication mode. Set
`DEBUG=true` explicitly for local development.

`TRUST_PROXY_HEADERS` defaults to the value of `PROXY_AUTH_ENABLED`. When true,
the first middleware requires `X-Wormhole-Host` and `X-Wormhole-Scheme` on every
request. These headers establish the public hostname and HTTP/HTTPS scheme used
for URLs, redirects, and same-origin CSRF checks. Hostnames and ports are validated;
schemes must be `http` or `https`. Identical comma-separated assertions are
normalized, while missing, empty, malformed, or conflicting assertions are rejected.
Generic `X-Forwarded-Host` and `X-Forwarded-Proto` values may describe an internal
proxy hop, so they are replaced with the validated canonical Wormhole origin,
not treated as independent public-origin assertions. Neither they nor the
internal `Host` value can override the canonical origin.

In this mode Django's `ALLOWED_HOSTS` is `['*']`, with the mandatory first
middleware replacing static allowlisting with canonical-header validation.
No per-request changes are made to global settings. The proxy must strip and
replace the canonical headers, and untrusted clients must not reach the backend
directly. Direct requests without canonical headers are rejected, including
health probes; send probes through the trusted proxy or provide the canonical
headers from a trusted probe configuration.

Explicitly set `TRUST_PROXY_HEADERS=true` to use Wormhole without proxy login,
or `false` to disable origin-header trust independently. When disabled,
`ALLOWED_HOSTS` is a comma-separated environment setting, defaulting to localhost
addresses, and proxy origin headers are ignored. This also supports conventional
proxies using a statically configured hostname without Wormhole origin headers.

**Only enable this when the application is reachable exclusively through a
trusted authentication proxy that strips client-supplied identity headers and
sets its own.** A forwarded header, including `X-Forwarded-By`, is not proof of
trust; enforce this boundary using network restrictions or your deployment's
private proxy tunnel. Never expose the backend port directly to untrusted clients.

Existing users are matched by username; new users are created with unusable
passwords and no staff or superuser privileges. Matching an existing username
retains that account's permissions, so confirm the proxy and local username
namespaces identify the same people before enabling this. In proxy mode,
password-based login is disabled, including for the Django admin.

Groups are synchronized on every authenticated request into reserved Django
groups named `proxy:<upstream-group>`, for example `proxy:exaworks`. Removed or
missing upstream groups remove those memberships, while local groups are
preserved. Do not manually manage memberships in the `proxy:` namespace.
Groups receive no permissions automatically and never change staff/superuser
flags. Existing application authorization remains based on ownership, maintainer
email, and staff/superuser status, not proxy group names.

No email is inferred from the username. Existing emails are preserved; new
accounts have blank email until an administrator sets it or a trusted email
header is supported. Ownership works immediately, but email-based maintainer
access requires a populated email address.

A missing or blank user header ends the proxy-authenticated application session.
Application logout does not end the proxy's SSO session: the next request with a
user header logs in again. Use the proxy's logout flow to end SSO. Remove the
setting or set it to `false` and restart to return to local password login.
In proxy mode, `/accounts/login/` redirects authenticated users to a safe local
destination or returns a clear 403 for failed authentication.

## Inspecting request headers

Temporarily add `HEADER_DIAGNOSTICS_ENABLED=true` to `src/.env` (or set it in
the server environment), restart the server, and visit `/diagnostics/headers/`
through your trusted proxy. The endpoint returns the headers Django receives
as JSON, including forwarded user and group headers. The diagnostic view does
not log you in and requires no application login; it works independently of
the proxy authentication feature.

Authorization, cookie, and headers whose names contain token, secret, key,
credential, or password are redacted. Other values may still contain sensitive
information: only enable this behind a trusted, access-controlled proxy, share
only the relevant identity headers with personal values anonymized, and disable
it after diagnosis. Responses are marked non-cacheable. The endpoint returns
404 by default; remove the setting or set it to `false` and restart to disable it.

The JSON `authentication` section reports the running server's proxy setting,
middleware installation, identity-header presence, and resulting login status.
If `proxy_enabled` is false despite editing `src/.env`, restart the server and
check whether its environment overrides the file. If the header is present and
proxy mode is enabled but authentication fails, check whether the matching local
account is inactive.
