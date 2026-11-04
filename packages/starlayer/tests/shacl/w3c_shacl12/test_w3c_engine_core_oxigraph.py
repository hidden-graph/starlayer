"""The vendored W3C SHACL 1.2 ``tests/core`` Validate entries run through the native engine reading straight from
Oxigraph: data and shapes graphs are loaded into separate in-memory ``pyoxigraph.Store`` objects and handed to
``validate()`` as ``OxigraphGraph`` views (``preserves_lexical_forms = False``; the rdflib/OxGraph path in
``test_w3c_engine_core.py`` has it True).

``KNOWN_FAILURES`` lists entries that fail only because Oxigraph rewrites literals when it stores them (upstream:
oxigraph/oxigraph#526, #1989 and the open PR #2010; tracked here as starlayer issue #190). They are STRICT xfails: when a
pyoxigraph release with the fix is installed they will XPASS and fail, which is the signal to delete the entries (issue
#190 lists the steps). Any other failure is a real to-do.
"""

from __future__ import annotations

import pytest
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph

from .closure import node_closure
from .comparison import conforms_of, find_report_node, result_multiset
from .ids import portable_id
from .known_failures import STORE_NORMALIZATION as KNOWN_FAILURES
from .manifest import ManifestEntry
from .namespaces import MF, SH, SHT
from .test_w3c_engine_core import _ENTRIES, _graph
from .test_w3c_validate import VENDOR_ROOT


def pytest_generate_tests(metafunc):
    if "entry" in metafunc.fixturenames:
        params = []
        for e in _ENTRIES:
            pid = portable_id(e, VENDOR_ROOT)
            marks = [pytest.mark.xfail(strict=True, reason=KNOWN_FAILURES[pid])] if pid in KNOWN_FAILURES else []
            params.append(pytest.param(e, id=pid, marks=marks))
        metafunc.parametrize("entry", params)


def test_engine_core_oxigraph(entry: ManifestEntry) -> None:
    data = OxigraphGraph.from_graph(_graph(entry, SHT.dataGraph))
    shapes = OxigraphGraph.from_graph(_graph(entry, SHT.shapesGraph))
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
