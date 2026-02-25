# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
