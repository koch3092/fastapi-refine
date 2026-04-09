# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-04-09

### Added
- Added app-level Refine error integration via `configure_refine(app)`.
- Added public error APIs: `RefineHTTPException`, `format_refine_http_exception`,
  `format_refine_validation_error`, `refine_http_exception_handler`, and
  `refine_validation_exception_handler`.
- Added contract coverage for CRUD success responses and Refine error formatting.

### Changed
- Breaking: renamed auth-related public API from `current_user_*` semantics to
  `current_principal_*` semantics in `RefineCRUDRouter` and `HookContext`.
- Breaking: `DELETE` success now returns the deleted public record snapshot instead of
  a message-only payload.
- Package-generated query/router/hook errors now use `RefineHTTPException` so apps can
  opt into a stable Refine-friendly error envelope.
- `configure_refine(app)` now has explicit installation-time snapshot semantics for
  numeric status handlers and preserves any existing `RefineHTTPException` handler.

### Fixed
- Fixed CRUD route dependency injection so `session_dep` and
  `current_principal_dep` are registered through FastAPI's dependency system.
- Fixed create/update wrapper signatures so request bodies are still treated as JSON
  bodies by FastAPI.
- Fixed direct CRUD calls to preserve principal resolution and keep yield-based
  principal dependencies alive for the full hook lifecycle.
- Fixed error formatting to preserve structured `HTTPException.detail`, JSON-encode
  non-primitive values, preserve headers, respect no-content statuses, and rebuild the
  middleware stack when `configure_refine(app)` is installed late.
- Fixed wrapped exception handlers to preserve sync threadpool execution semantics and
  dispatch `RefineHTTPException` through any app-registered custom handler.

### Notes
- Legacy `skip`/`limit` currently returns `422` in `0.3.x`; planned to become silently
  ignored after `0.5.x`.

## [0.2.0] - 2026-02-25

### Changed
- Breaking: Removed public `skip`/`limit` pagination support; only `_start`/`_end` is supported.
- Added strict pagination validation with `422` responses for invalid ranges (for example `_end < _start`).
- `PaginationConfig` now uses range-based names: `default_start`, `default_page_size`, and `max_page_size`.
- Updated `examples/basic_usage.py` to use FastAPI lifespan instead of `@app.on_event("startup")`.

### Notes
- Legacy `skip`/`limit` currently returns `422` in `0.2.x`; planned to become silently ignored after `0.5.x`.

## [0.1.0] - 2025-01-07

### Added
- Initial release
- Query parameter parsing for Refine simple-rest conventions
- Support for filtering (eq, ne, gte, lte, like operators)
- Full-text search via `q` parameter
- Multi-field sorting
- Range-based and offset-based pagination
- `RefineCRUDRouter` factory for automatic CRUD endpoint generation
- Hook system for custom logic injection
- Type-safe with full mypy support
- Built-in type converters (parse_bool, parse_uuid)
