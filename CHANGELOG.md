# Changelog

## Unreleased

### Added
- Add scheduled GHCR retention with dry-run defaults, protected digests, refreshed PR checks, and manual cleanup controls
- Build and smoke-test container images in GitHub Actions, publishing PR, branch, and release tags to GHCR
- Container entrypoint with opt-in migrations and static collection before starting the configured command
- Opt-in request header diagnostic endpoint with credential redaction, auth status, and non-cacheable responses
- Opt-in trusted proxy login using forwarded user headers and synchronized, namespaced groups
- Initial setup of website
- Resource grid and list views with shared filtering and navigation controls

### Changed
- Move container Gunicorn options into a dedicated configuration file
- Run the container with Gunicorn on port 8000 and emit access/error logs to standard streams
- Pin container build tooling, include package metadata, and exclude local secrets from images
- Derive public origins from validated canonical Wormhole headers in trusted proxy mode; retain local host allowlisting
- Removed edit/delete buttons from list view

### Fixed
- Prefer the validated Wormhole origin over hop-specific forwarding headers changed by layered proxies
- Serve collected static assets with WhiteNoise when running Gunicorn with debug mode disabled
- Disable Gunicorn's optional home-directory control socket and log Django errors with debug mode disabled
- Accept repeated identical origin headers from trusted proxy chains and reject missing or conflicting canonical assertions
- Avoid missing login-template errors in proxy mode
