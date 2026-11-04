"""
Shared fixtures for the starlayer.graph test suite.
"""

import pathlib

import pytest

# Eagerly import and install starlayer.sparql's grammar extension here, at
# collection time, before any test module gets a chance to trigger it
# lazily from inside a function body. This is the actual fix for the
# long-standing "pytest run corrupts starlayer.sparql's grammar
# installation" issue (see docs/testing-strategy.md's old tier 5 writeup,
# starlayer.sparql/CLAUDE.md finding #31): confirmed empirically that the
# corruption has nothing to do with which pipeline a test exercises (it
# reproduced with a file - test_dataset.py - that never touches
# starlayer.sparql at all, run alongside one that does) and everything to
# do with *when* grammar12.install() first runs relative to pytest's
# assertion-rewrite import hook. A conftest.py is imported by pytest during
# collection, before that hook processes ordinary test modules - forcing
# the grammar's first install here, once, sidesteps the interaction
# entirely. Confirmed via direct A/B testing: the exact same test
# combination that reliably failed without this import passes cleanly with
# it, every time.
import starlayer.graph  # noqa: F401  - must come before grammar12.install() (see tests/shacl/conftest.py)
from starlayer.sparql import _grammar12 as grammar12

grammar12.install()

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def parser():
    # imported here, not at module level: the hand-written Turtle parser is the old class's and goes at D1 with the tests
    # that use this fixture (the conftest then needs only its fixture_ttl and grammar install)
    from starlayer.graph.parsers.turtle_parser import StarLayerTurtleParser

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
