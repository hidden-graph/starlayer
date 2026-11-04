"""The vendored W3C SHACL 1.2 ``tests/core`` Validate entries run through the native engine (``starlayer.shacl_engine``).

No known-failure xfails while the engine is being built: a failing entry is a to-do. The pass rate per directory is the
progress measure; see ``docs/working/shacl-engine-design.md``.
"""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import validate

from .closure import node_closure
from .comparison import conforms_of, find_report_node, result_multiset
from .ids import portable_id
from .known_failures import STORE_NORMALIZATION
from .manifest import (
    ManifestEntry,
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from .namespaces import MF, SH, SHT
from .test_w3c_validate import TOP_MANIFEST, VENDOR_ROOT


def _entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [
        e
        for e in iter_manifest_entries(TOP_MANIFEST)
        if e.entry_type == SHT.Validate and "/tests/core/" in str(e.source_path).replace("\\", "/")
    ]


_ENTRIES = _entries()


def pytest_generate_tests(metafunc):
    if "entry" in metafunc.fixturenames:
        params = []
        for e in _ENTRIES:
            pid = portable_id(e, VENDOR_ROOT)
            marks = [pytest.mark.xfail(strict=True, reason=STORE_NORMALIZATION[pid])] if pid in STORE_NORMALIZATION else []
            params.append(pytest.param(e, id=pid, marks=marks))
        metafunc.parametrize("entry", params)


def _graph(entry: ManifestEntry, predicate) -> OxGraph:
    action = next(entry.graph.objects(entry.iri, MF.action))
    return clone_graph(load_document(uri_to_path(next(entry.graph.objects(action, predicate)))), OxGraph)


def test_engine_core(entry: ManifestEntry) -> None:
    data = _graph(entry, SHT.dataGraph)
    shapes = _graph(entry, SHT.shapesGraph)
    expected = next(entry.graph.objects(entry.iri, MF.result))
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
