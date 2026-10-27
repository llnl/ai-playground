# Container deployment

This document covers container builds, runtime behavior, OpenShift deployment,
GHCR publishing, and container retention.

## Container builds

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
described in the [proxy authentication documentation](PROXY_AUTHENTICATION.md).

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

## Container publishing

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

## Container retention

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
