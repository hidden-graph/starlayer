"""``validate(OxDataset, OxDataset)`` over the W3C SHACL 1.2 core Validate entries: the fixtures are parsed straight into the
wrapper (no rdflib graph in between), which the engine accepts as a data and a shapes graph through its ``GraphView``
protocol plus ``engine_terms`` / ``sparql_query``. Known failures are the Oxigraph literal normalization ones
(starlayer #190), the same four as ``test_w3c_engine_core_oxigraph.py``; they are strict xfails.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = str(Path(__file__).resolve().parents[2])
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

from shacl.w3c_shacl12.closure import node_closure  # noqa: E402
from shacl.w3c_shacl12.comparison import conforms_of, find_report_node, result_multiset  # noqa: E402
from shacl.w3c_shacl12.ids import portable_id  # noqa: E402
from shacl.w3c_shacl12.manifest import file_uri, uri_to_path  # noqa: E402
from shacl.w3c_shacl12.namespaces import MF, SH, SHT  # noqa: E402
from shacl.w3c_shacl12.test_w3c_engine_core import _ENTRIES  # noqa: E402
from shacl.w3c_shacl12.test_w3c_engine_core_oxigraph import KNOWN_FAILURES  # noqa: E402
from shacl.w3c_shacl12.test_w3c_validate import VENDOR_ROOT  # noqa: E402
from starlayer.graph.oxgraph import OxDataset, OxGraph  # noqa: E402
from starlayer.shacl_engine import validate  # noqa: E402


def _load(entry, predicate, cls=OxDataset):
    action = next(entry.graph.objects(entry.iri, MF.action))
    path = uri_to_path(next(entry.graph.objects(action, predicate))).resolve()
    g = cls()
    g.parse(file=str(path), format="turtle", base=str(file_uri(path)))
    return g


def pytest_generate_tests(metafunc):
    if "entry" in metafunc.fixturenames:
        params = []
        for e in _ENTRIES:
            pid = portable_id(e, VENDOR_ROOT)
            marks = [pytest.mark.xfail(strict=True, reason=KNOWN_FAILURES[pid])] if pid in KNOWN_FAILURES else []
            params.append(pytest.param(e, id=pid, marks=marks))
        metafunc.parametrize("entry", params)


def _run(entry, cls):
    data = _load(entry, SHT.dataGraph, cls)
    shapes = _load(entry, SHT.shapesGraph, cls)
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


def test_validate_oxdataset(entry) -> None:
    _run(entry, OxDataset)


def test_validate_oxgraph(entry) -> None:
    _run(entry, OxGraph)
