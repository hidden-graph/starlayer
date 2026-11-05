"""The vendored W3C SHACL 1.2 ``tests/sparql`` Validate entries (component, node, property, pre-binding, targets) run
through the native engine (``starlayer.shacl_engine``), SPARQL executed by StarLayer's own query layer. Rules and functions
are out of scope for now.

No known-failure xfails while the engine is being built: a failing entry is a to-do. The pass rate per directory is the
progress measure; see ``docs/working/shacl-engine-design.md``.
"""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate

from .closure import node_closure
from .comparison import conforms_of, find_report_node, result_multiset
from .ids import portable_id
from .manifest import (
    ManifestEntry,
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from .namespaces import MF, SH, SHT
from .test_w3c_validate import TOP_MANIFEST, VENDOR_ROOT

_DIRS = ("component", "node", "property", "pre-binding", "targets")


def _entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [
        e
        for e in iter_manifest_entries(TOP_MANIFEST)
        if e.entry_type == SHT.Validate
        and any(f"/tests/sparql/{d}/" in str(e.source_path).replace("\\", "/") for d in _DIRS)
    ]


_ENTRIES = _entries()


def pytest_generate_tests(metafunc):
    if "entry" in metafunc.fixturenames:
        metafunc.parametrize("entry", _ENTRIES, ids=[portable_id(e, VENDOR_ROOT) for e in _ENTRIES])


# Deliberate deviations from the vendored fixtures: the engine follows the SHACL 1.2 SPARQL draft where the fixture follows
# the older rule (which pySHACL also implements). The entry is NOT skipped or xfailed: the test asserts the engine's own
# outcome, so a change in either direction shows up.
DEVIATIONS: dict[str, str] = {
    "tests/sparql/pre-binding/unsupported-sparql-002::unsupported-sparql-002": (
        "The fixture expects a failure for `VALUES ?any { true }`. SHACL 1.2 SPARQL Appendix A: \"SPARQL queries MUST not "
        "contain a VALUES clause that mentions any potentially pre-bound variable\"; ?any is not pre-bound, so the query "
        "is allowed and the engine runs it (Appendix F item 8, Issue 159, records the relaxation). pySHACL and the fixture "
        "keep the older rule that forbids every VALUES."
    ),
}


def _graph(entry: ManifestEntry, predicate) -> StarLayerGraph:
    action = next(entry.graph.objects(entry.iri, MF.action))
    return clone_graph(load_document(uri_to_path(next(entry.graph.objects(action, predicate)))), StarLayerGraph)


def test_engine_sparql(entry: ManifestEntry) -> None:
    data = _graph(entry, SHT.dataGraph)
    shapes = _graph(entry, SHT.shapesGraph)
    expected = next(entry.graph.objects(entry.iri, MF.result))
    if portable_id(entry, VENDOR_ROOT) in DEVIATIONS:
        outcome = validate(data, shapes)  # runs instead of failing; the query yields a row, so a violation is reported
        assert not outcome.conforms
        assert len(outcome.results) == 1
        return
    if expected == SHT.Failure:
        with pytest.raises(Exception):  # noqa: B017
            validate(data, shapes)
        return
    expected_graph = node_closure(entry.graph, expected)
    expected_node = find_report_node(expected_graph)
    disallows = next(expected_graph.objects(expected_node, SH.conformanceDisallows), None)
    outcome = validate(data, shapes, conformance_disallows=disallows)
    actual_node = find_report_node(outcome.report_graph)
    assert outcome.conforms == conforms_of(expected_graph, expected_node)
    assert result_multiset(outcome.report_graph, actual_node) == result_multiset(expected_graph, expected_node)
