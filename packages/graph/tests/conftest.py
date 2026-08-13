"""
Shared fixtures for the starlayergraph test suite.
"""

import pathlib
import pytest
from starlayergraph.parsers.turtle_parser import StarLayerTurtleParser

# Eagerly import and install starsparql's grammar extension here, at
# collection time, before any test module gets a chance to trigger it
# lazily from inside a function body. This is the actual fix for the
# long-standing "pytest run corrupts starsparql's grammar
# installation" issue (see docs/testing-strategy.md's old tier 5 writeup,
# starsparql/CLAUDE.md finding #31): confirmed empirically that the
# corruption has nothing to do with which pipeline a test exercises (it
# reproduced with a file - test_dataset.py - that never touches
# starsparql at all, run alongside one that does) and everything to
# do with *when* grammar12.install() first runs relative to pytest's
# assertion-rewrite import hook. A conftest.py is imported by pytest during
# collection, before that hook processes ordinary test modules - forcing
# the grammar's first install here, once, sidesteps the interaction
# entirely. Confirmed via direct A/B testing: the exact same test
# combination that reliably failed without this import passes cleanly with
# it, every time.
from starsparql import grammar12
grammar12.install()

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def parser():
    return StarLayerTurtleParser()


@pytest.fixture
def fixture_ttl():
    """Return a callable: fixture_ttl(name) reads tests/fixtures/<name>."""
    def _read(name):
        return (FIXTURES_DIR / name).read_text()
    return _read


@pytest.fixture
def parse(parser):
    """Return a callable: parse(data) → rdflib.Graph."""
    return parser.parse
