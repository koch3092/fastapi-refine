"""Tests for query parsing functionality."""

from __future__ import annotations

import pytest
from starlette.datastructures import QueryParams

from fastapi_refine.core.query import (
    ensure_no_legacy_pagination_params,
    parse_bool,
    parse_uuid,
    resolve_pagination,
)


class TestTypeParsers:
    """Test type converter functions."""

    def test_parse_bool_true_values(self):
        """Test parsing various true values."""
        true_values = ["1", "true", "True", "TRUE", "t", "T", "yes", "YES", "y", "Y"]
        for value in true_values:
            assert parse_bool(value) is True

    def test_parse_bool_false_values(self):
        """Test parsing various false values."""
        false_values = ["0", "false", "False", "FALSE", "f", "F", "no", "NO", "n", "N"]
        for value in false_values:
            assert parse_bool(value) is False

    def test_parse_bool_invalid_value(self):
        """Test parsing invalid boolean value."""
        with pytest.raises(ValueError):
            parse_bool("invalid")

    def test_parse_uuid(self):
        """Test parsing valid UUID."""
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = parse_uuid(uuid_str)
        assert str(result) == uuid_str

    def test_parse_uuid_invalid(self):
        """Test parsing invalid UUID."""
        with pytest.raises(ValueError):
            parse_uuid("not-a-uuid")


class TestPaginationParsing:
    """Test pagination resolution and validation."""

    def test_resolve_pagination_with_defaults(self):
        assert resolve_pagination(
            _start=None,
            _end=None,
            default_start=0,
            default_page_size=25,
            max_page_size=100,
        ) == (0, 25)

    def test_resolve_pagination_with_explicit_range(self):
        assert resolve_pagination(
            _start=10,
            _end=30,
            default_start=0,
            default_page_size=25,
            max_page_size=100,
        ) == (10, 20)

    def test_resolve_pagination_with_start_only(self):
        assert resolve_pagination(
            _start=15,
            _end=None,
            default_start=0,
            default_page_size=25,
            max_page_size=100,
        ) == (15, 25)

    def test_resolve_pagination_caps_to_max_page_size(self):
        assert resolve_pagination(
            _start=0,
            _end=500,
            default_start=0,
            default_page_size=25,
            max_page_size=100,
        ) == (0, 100)

    def test_resolve_pagination_end_before_start_raises(self):
        with pytest.raises(
            ValueError, match="`_end` must be greater than or equal to `_start`"
        ):
            resolve_pagination(
                _start=20,
                _end=10,
                default_start=0,
                default_page_size=25,
                max_page_size=100,
            )

    def test_resolve_pagination_negative_start_raises(self):
        with pytest.raises(
            ValueError, match="`_start` must be greater than or equal to 0"
        ):
            resolve_pagination(
                _start=-1,
                _end=10,
                default_start=0,
                default_page_size=25,
                max_page_size=100,
            )

    def test_reject_legacy_skip_limit_parameters(self):
        with pytest.raises(
            ValueError, match="Legacy pagination parameters are not supported"
        ):
            ensure_no_legacy_pagination_params(QueryParams("skip=0&limit=10"))
