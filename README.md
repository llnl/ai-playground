# AI Playground

AI Playground is a project designed to improve the visibility and accessibility of AI tooling across the DOE.

In this context, "AI tooling" includes MCP servers, agents, skills, and other AI-specific resources.

## Purpose

AI Playground aims to answer two main questions:

- **Visibility**: What AI tooling exists across the DOE?
- **Availability**: Where does this tooling live, who owns it, and how can it be accessed/used?

## What users can do

AI Playground is an informational website that helps users discover and learn about existing AI tooling. It does not create or host tooling itself.

Users will be able to:

- Browse AI tooling by category
- Learn about available tools
- Search, query, and view registered tools
- Find links to the projects and systems used to store, create or manage tooling, such as MADA and URSA

## Registration workflow

Teams and individuals can register their AI tools by submitting a form on the website. Once registered, the tool will appear in the appropriate catalog category, such as:

- MCP Server
- Agent
- Skill
- Other AI tooling types

## Deployment model

Because the intended user base spans DOE organizations, including Office of Science and NNSA laboratories, AI Playground will support both public and private deployments, as well as BYOD environments.

Each environment will use a separate backend database.

## Tool metadata

Each registered tool will include the following metadata:

- Name
- Description
- Maintainer, such as a team or individual
- Institution
- Location, such as a repository or URL
- Versions
- Category, such as simulation, geometry, or scheduler
- Tags
- Logo
- Documentation link
- etc...

## Automatic registration

Tools created from the MADA library will be registered automatically in the AI Playground database.

## Getting started for developers

These instructions will show developers how to start up the website instance in order to start modifying it.

1. SSH into HPC with port forwarding: `ssh -4L 8000:localhost:8000 USER@HPC`
2. Install the environment: `uv sync`
3. Go https://launchit.llnl.gov/ and create an instance of PostgreSQL Vector
4. Create a `src/.env` file with the information below. LaunchIT will have the DB information while you will need to create a Django Key **ONLY ONCE** with `uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`

```
SECRET_KEY=...
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=...
DEBUG=True
```

5. Create an admin for your database `uv run python src/manage.py createsuperuser`
6. Configure your database with `uv run python src/manage.py makemigrations` and `uv run python src/manage.py migrate`
7. Start the server: `uv run python src/manage.py runserver`
    * You can run it on a different port with `uv run python src/manage.py runserver 8999` but be sure to update port in step 1.
8. Go to http://localhost:8000/admin/ to log in
9. Go to http://localhost:8000 to interact with the site

### Proxy authentication

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

### Inspecting request headers

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

### Project Layout

* `src/config/` contains the Django configuration files and settings
* `src/templates/` contains the high level html files that are used throughout the website
* `src/static/` contains the css, js, and images that are used throughout the website
* `src/apps/` contains the applications that are used throughout the website. A new app can be created with `uv run python src/manage.py startapp MYAPP src/apps/MYAPP`.
    * `src/apps/cards/` contains the `cards` apps that is the main focus of the website
        * `src/apps/cards/templates/` contains the html files for the cards app
        * `src/apps/cards/context_processors.py` contains data that can be called with double curly braces `{{}}` throughout the website (see `ai-playground/src/apps/cards/templates/cards/partials/stats_widget.html` for example). This references the model (datatable) `Cards` which houses the data.
        * `src/apps/cards/forms.py` contains the different forms that users can fill in for the `cards` app. This references the model (datatable) `Cards` which houses the data.
        * `src/apps/cards/models.py` contains the different models (datatables) that contain the data for the `cards` app. This is where you define the datatables and their fields. If you updated your datatables or create new ones, rerun the commands in step 7 and **git commit `src/apps/cards/migrations/*.py`**.
        * `src/apps/cards/urls.py` contains the different urls for the `cards` app. These reference the different views that connect the Python to html templates.
        * `src/apps/cards/views.py` contains the different views for the `cards` app. These connect the models, forms, and html templates to display the website.

## Release

AI Playground is distributed under the terms of the Apache License (Version 2.0) WITH LLVM Exception.

All new contributions must be made under the Apache 2.0 License WITH LLVM Exception.

See [LICENSE](./LICENSE), [COPYRIGHT](./COPYRIGHT), and [NOTICE](./NOTICE) for details.

SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

LLNL-CODE-2022047
