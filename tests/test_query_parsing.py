"""Tests for query parsing functionality."""

import pytest

from fastapi_refine.core.query import parse_bool, parse_uuid


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


# TODO: Add more tests for:
# - parse_filters
# - parse_sorters
# - resolve_pagination
# - FilterConfig
# - SortConfig
