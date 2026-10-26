# Changelog

## Unreleased

### Added
- Opt-in trusted proxy login using forwarded user headers and synchronized, namespaced groups
- Initial setup of website
- Resource grid and list views with shared filtering and navigation controls

### Changed
- Derive public origins from validated canonical Wormhole headers in trusted proxy mode; retain local host allowlisting
- Removed edit/delete buttons from list view

### Fixed
- Prefer the validated Wormhole origin over hop-specific forwarding headers changed by layered proxies
- Accept repeated identical origin headers from trusted proxy chains and reject missing or conflicting canonical assertions
- Avoid missing login-template errors in proxy mode
