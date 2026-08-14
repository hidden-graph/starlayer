"""Guards against a real class of bug that shipped silently before this test
existed: an `sh:select`/`sh:ask`/`sh:construct` query embedded in a shape -
either a test fixture or the shipped meta-shape/UI-hint assets - referencing
a function name the current SPARQL grammar doesn't actually support. Two
real instances: `isTripleTerm(...)` in two fixtures (the grammar only ever
recognized `isTRIPLE`, left over from the old text-rewriter this project
replaced) and a stale `stsh:` namespace in the shipped meta-shapes pointing
at the pre-rename `pyshacl-starlight` vocabulary. Both would have failed
this test immediately instead of sitting broken until something happened to
execute them.

Only *parses* each embedded query (via `starsparql.parse12.prepare_query_12`
- the same grammar `StarLayerGraph.query()` uses at runtime), doesn't
execute it - fast, and needs no fixture data or focus/value bindings.
"""

from __future__ import annotations

import glob
import os

import pytest
from rdflib import Graph, Namespace

from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starsparql.parse12 import prepare_query_12

SH = Namespace("http://www.w3.org/ns/shacl#")

_HERE = os.path.dirname(__file__)
_ASSETS_DIR = os.path.join(_HERE, "..", "..", "starshacl", "assets")
_FIXTURES_DIR = os.path.join(_HERE, "..", "fixtures", "shapes")


def _parse_ttl(path: str) -> Graph:
    """Plain Turtle covers the large majority of fixtures; only the ones
    using real RDF 1.2 syntax (triple terms, annotations) need the turtle12
    parser instead."""
    g = Graph()
    try:
        g.parse(path, format="turtle")
        return g
    except Exception:
        pass
    sl = StarLayerGraph()
    sl.parse(path, format="turtle12")
    return sl


def _collect_embedded_queries() -> list[tuple[str, str]]:
    paths = sorted(
        glob.glob(os.path.join(_ASSETS_DIR, "*.ttl")) + glob.glob(os.path.join(_FIXTURES_DIR, "*.ttl"))
    )
    found: list[tuple[str, str]] = []
    for path in paths:
        try:
            g = _parse_ttl(path)
        except Exception:
            # A handful of fixtures are deliberately malformed *Turtle* to
            # test parser-error handling itself, not shape semantics - not
            # this test's concern, skip rather than fail.
            continue
        rel = os.path.relpath(path, os.path.join(_HERE, "..", ".."))
        for pred in (SH.select, SH.ask, SH.construct):
            for _, _, text in g.triples((None, pred, None)):
                found.append((rel, str(text)))
    return found


_QUERIES = _collect_embedded_queries()


@pytest.mark.parametrize(
    "path,query_text",
    _QUERIES,
    ids=[f"{path}:{i}" for i, (path, _) in enumerate(_QUERIES)],
)
def test_embedded_sparql_parses(path: str, query_text: str) -> None:
    prepare_query_12(query_text)


def test_found_at_least_one_embedded_query() -> None:
    """Guard against the collector itself silently finding nothing (e.g. a
    path typo) and this whole file quietly testing zero cases."""
    assert len(_QUERIES) > 0
