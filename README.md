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

### Regression tests

Install testing dependencies with `uv sync --extra tests`, then run:

```sh
uv run python src/manage.py test config apps.cards --noinput
uv run python -m unittest discover -s .github/container -p test_cleanup.py
```

The Django suite uses the PostgreSQL configuration in `src/.env`. The database
user must be permitted to create a test database; do not point tests at a
production database. Card permission integration tests require JSON containment
support and are skipped on SQLite. The cleanup tests need no database or network.

Pull-request CI runs both suites on Python 3.12 with a disposable PostgreSQL 16
service and installs WhiteNoise so collected-static-file tests also run. Require
the CI `tests` job alongside lint, changelog, and container checks in branch
protection.

### Container builds

Build the image from the repository root with `docker build -t ai-playground .`
(or `podman build -t ai-playground .`). The build requires network access to
download the base image, pinned uv version, build tooling, and dependencies.

The image includes the source, package metadata, README, and license. Dependencies
are resolved and installed during the image build with `uv sync`; the local
`uv.lock` is not included in the build context. Startup uses
`uv run --no-sync gunicorn` to select the built environment without reinstalling
dependencies.

`.dockerignore` limits the build context to required inputs and excludes
environment files, Python caches, uploaded media, and generated static files.
Supply Django and database credentials at runtime through an OpenShift Secret
or container environment variables; do not copy a populated `.env` into the image.
Configure `ALLOWED_HOSTS`, `DEBUG`, and proxy settings for the deployment as
described below.

Root-group write permissions are retained for OpenShift's arbitrary-UID model.
The image runs Gunicorn with `config.wsgi:application` from `/app/src`, binding to
`0.0.0.0:8000`. These settings live in `gunicorn.conf.py`, which the container
loads explicitly. Access logs go to stdout and error logs to stderr. Additional worker
and timeout options can be supplied using `GUNICORN_CMD_ARGS`. The optional
Gunicorn control socket is disabled to avoid writing into an arbitrary UID's
unwritable home directory on OpenShift. Django error tracebacks are logged to
stderr even with `DEBUG=false`. Keep the backend
accessible only to the trusted proxy when proxy authentication is enabled.
WhiteNoise serves collected static assets through the application with debug
mode disabled. For the bundled assets, set `RUN_COLLECTSTATIC=true` so each
container collects them before Gunicorn starts. No separate static-file server
or shared volume is needed for this per-container setup. User-uploaded media
still requires a separate storage/delivery strategy.

The container entrypoint supports optional setup before executing its command:

- `RUN_MIGRATIONS=true`: apply committed migrations with `migrate --noinput`.
- `RUN_COLLECTSTATIC=true`: collect assets into `src/staticfiles/` with
  `collectstatic --noinput` for WhiteNoise to serve.

Both options default to false and require the same Django/database environment
configuration as the application. Setup failures stop startup. The entrypoint
uses `exec` to start the configured command, preserving arguments and shutdown
signals, and never generates migrations or creates administrator accounts.

For multiple OpenShift replicas, prefer a single migration Job per release using
the same image with `RUN_MIGRATIONS=false` and command arguments
`uv run --no-sync python src/manage.py migrate --noinput`. Run it before starting
the updated application pods rather than enabling migrations in every replica.
Administrator creation remains an explicit, one-off management task.

For a self-contained Wormhole deployment, supply these runtime settings through
the OpenShift Deployment or ConfigMap, not a local `.env` file excluded from the
image:

```dotenv
PROXY_AUTH_ENABLED=true
RUN_COLLECTSTATIC=true
DEBUG=false
```

If login redirects to a missing `registration/login.html`, the application is
using password login rather than proxy login. Check the pod's effective
`PROXY_AUTH_ENABLED` setting and image version instead of adding a password
template to conceal the missing proxy configuration.

### Container publishing

`.github/workflows/container.yml` builds and smoke-tests Linux/AMD64 images on
every PR, pushes to `develop` or `main`, and published GitHub releases. Images
are published to `ghcr.io/<repository-owner>/<repository-name>`, lowercased.

| Event | Published tags |
| --- | --- |
| Same-repository PR | `pr-42`, `pr-42-sha-<12-character-commit>` |
| Push/merge to `develop` or `main` | Branch name and `sha-<12-character-commit>` |
| Stable release `v1.2.3` | `v1.2.3`, `1.2.3`, `1.2`, `1`, `latest`, and SHA tag |
| Prerelease | Release tag, full semantic version when applicable, and SHA tag; no stable aliases |

Fork PRs build and test but cannot publish. PR builds use GitHub's checked-out
merge revision, testing integration with the base branch. Branch publishing
also covers direct pushes. Non-semantic-version releases receive their release
tag and SHA tag; a stable published release also updates `latest`.

The smoke test runs the real entrypoint and Gunicorn as an arbitrary UID with
root-group membership, applies migrations to a disposable SQLite database,
collects and requests CSS, checks proxy login, and rejects direct requests
without canonical origin headers. It is not a PostgreSQL integration test.

Build jobs have read-only repository permissions. Only a separate publishing
job gets `packages: write`, logs in with `GITHUB_TOKEN`, and pushes the exact
tested image transferred through a short-lived workflow artifact. No PAT or
deployment/database secrets are required. Existing lint/changelog CI remains
separate; require both CI and container checks in branch protection.

The organization must permit Actions to publish packages. New GHCR packages
default to private: make the package public for anonymous pulls, or configure
an OpenShift image-pull secret. Use a version tag or image digest for production;
branch/PR tags move, and unlocked dependency resolution can change a rebuilt
image even for the same source revision. The workflow uses Buildx's Actions
cache and cancels outdated PR builds, not in-progress branch/release builds.

### Container retention

`.github/workflows/container-cleanup.yml` runs weekly on Sunday at 04:23 UTC
and supports **Actions → Container cleanup → Run workflow**. Scheduled runs
use the workflow on the repository's default branch; merge it there to activate
the schedule and manual button. Fork schedules may need enabling in Actions,
and GitHub can disable schedules in inactive public repositories.

Cleanup defaults to dry-run: review candidate IDs, digests, tags, and reasons in
the logs before enabling deletion. Under **Settings → Secrets and variables →
Actions → Variables**, set `GHCR_CLEANUP_ENABLED=true` to enable scheduled
deletion. A manual run's `dry_run` checkbox controls that run independently.

The policy preserves every version with a release, current branch, or unknown
tag; keeps the newest 30 SHA-only versions across both branches; and removes
older SHA-only versions after seven days. PR versions are eligible only when
all associated PRs have been closed for seven days and the version has not
changed for seven days. Deleting a version removes **all** its tags. Reserved
`pr-<number>` and `sha-<12-hex-characters>` names must not be used for releases.
Before deletion, cleanup refreshes the package metadata and associated PR states;
reopened or recently reclosed PRs protect their images even if selected earlier.

Set `GHCR_PROTECTED_DIGESTS` to whitespace- or comma-separated `sha256:...`
digests used by deployments before enabling deletion. Untagged versions are
preserved by default, because they may still be deployed by digest; the manual
`delete_untagged` option removes them after seven days unless protected.

No additional dependencies or PAT are needed. The workflow uses `GITHUB_TOKEN`
and Python's standard library. The package must grant this repository **Admin**
access under its **Package settings → Manage Actions access** to permit version
deletion; the publishing repository normally receives this automatically.
Organization policy must also allow package writes. API permission errors fail
the run rather than treating inaccessible PRs or packages as safe to delete.

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
