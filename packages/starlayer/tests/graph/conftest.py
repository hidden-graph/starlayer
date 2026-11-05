"""
Shared fixtures for the starlayer.graph test suite.
"""

import pathlib

import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def fixture_ttl():
    """Return a callable: fixture_ttl(name) reads tests/fixtures/<name>."""
    def _read(name):
        return (FIXTURES_DIR / name).read_text()
    return _read

