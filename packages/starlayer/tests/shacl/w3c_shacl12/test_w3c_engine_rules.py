"""The vendored W3C SHACL 1.2 ``tests/sparql/rules`` ``sht:Infer`` entries run through the native rules module
(``starlayer.shacl_engine.rules.apply_rules``). Compared as the set of triples added to the data graph (equal up to blank
node naming); the caller's data graph must be left untouched.

Entries that need node expressions (``sht:NodeExpr`` compliance) are skipped until ``starlayer.shacl_engine.expressions``
exists. No known-failure xfails: a failing entry is a to-do.
"""

from __future__ import annotations

import importlib.util

import pytest
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine.rules import apply_rules
from starlayer.shacl_engine.terms import LegacyTermView, from_engine

from .ids import portable_id
from .manifest import (
    ManifestEntry,
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from .namespaces import MF, SHT
from .test_w3c_infer import _expected_triples, _same_triples
from .test_w3c_validate import TOP_MANIFEST, VENDOR_ROOT


def _entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [
        e
        for e in iter_manifest_entries(TOP_MANIFEST)
        if e.entry_type == SHT.Infer and "/tests/sparql/rules/" in str(e.source_path).replace("\\", "/")
    ]


_ENTRIES = _entries()
_HAS_EXPRESSIONS = importlib.util.find_spec("starlayer.shacl_engine.expressions") is not None


def pytest_generate_tests(metafunc):
    if "entry" in metafunc.fixturenames:
        metafunc.parametrize("entry", _ENTRIES, ids=[portable_id(e, VENDOR_ROOT) for e in _ENTRIES])


def _graph(entry: ManifestEntry, predicate) -> OxGraph:
    action = next(entry.graph.objects(entry.iri, MF.action))
    return clone_graph(load_document(uri_to_path(next(entry.graph.objects(action, predicate)))), OxGraph)


def test_engine_rules(entry: ManifestEntry) -> None:
    if SHT.NodeExpr in set(entry.graph.objects(entry.iri, SHT.compliance)) and not _HAS_EXPRESSIONS:
        pytest.skip("needs starlayer.shacl_engine.expressions (node expressions), not present yet")
    data = _graph(entry, SHT.dataGraph)
    shapes = _graph(entry, SHT.shapesGraph)
    expected = _expected_triples(entry)
    def _triples():  # the data graph holds pyoxigraph terms; the expected triples are in rdflib terms
        return {tuple(from_engine(t) for t in triple) for triple in data.triples((None, None, None))}

    before = _triples()
    result = apply_rules(data, shapes)
    assert _triples() == before, "the caller's data graph was modified"
    added = set(LegacyTermView(result.view).triples((None, None, None))) - before
    assert added == {tuple(from_engine(t) for t in triple) for triple in result.inferred}  # the engine speaks pyoxigraph terms
    assert _same_triples(added, expected), f"expected added: {expected}\nactual added: {added}"
