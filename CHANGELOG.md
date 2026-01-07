# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
