"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_query_params():
    """Sample query parameters for testing."""
    return {
        "title": "test",
        "is_active": "true",
        "_sort": "created_at",
        "_order": "desc",
        "_start": "0",
        "_end": "10",
    }
