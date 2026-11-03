"""The vendored W3C SHACL 1.2 ``tests/node-expr`` entries run through the native engine: ``sht:EvalNodeExpr`` entries
call ``starlayer.shacl_engine.expressions.evaluate_expression``; the ``constraints`` ``sht:Validate`` entries call
``validate``. As in ``test_w3c_node_expr.py``, the fixture document is both data graph and shapes graph.

No xfail shims: a failing entry is a to-do.
"""

from __future__ import annotations

import pytest

from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.executor import Context
from starlayer.shacl_engine.expressions import evaluate_expression
from starlayer.shacl_engine.plan import Plan
from starlayer.shacl_engine.terms import from_engine, to_engine

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
from .namespaces import MF, SHT
from .test_w3c_validate import TOP_MANIFEST, VENDOR_ROOT


def _entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [
        e
        for e in iter_manifest_entries(TOP_MANIFEST)
        if "/tests/node-expr/" in str(e.source_path).replace("\\", "/")
        and e.entry_type in (SHT.EvalNodeExpr, SHT.Validate)
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


def _eval(entry: ManifestEntry) -> None:
    graph = clone_graph(load_document(entry.source_path), StarLayerGraph)
    action = next(entry.graph.objects(entry.iri, MF.action))
    expr = next(entry.graph.objects(action, SHT.nodeExpr))
    focus = next(entry.graph.objects(action, SHT.focusNode), None)
    ignore = next(entry.graph.objects(action, SHT.ignoreOrder), None)
    prefix = str(SHT) + "scope-"
    scope = {
        str(p)[len(prefix) :]: [o]
        for p, o in entry.graph.predicate_objects(action)
        if str(p).startswith(prefix)
    }
    expected = list(entry.graph.items(next(entry.graph.objects(entry.iri, MF.result))))
    actual = [  # the engine speaks pyoxigraph terms: convert in and out
        from_engine(t)
        for t in evaluate_expression(
            Context(data=graph, plan=Plan(shapes_graph=graph)),
            to_engine(expr),
            to_engine(focus),
            {k: [to_engine(o) for o in v] for k, v in scope.items()},
        )
    ]
    assert _same_terms(actual, expected, ordered=not (ignore is not None and ignore.toPython())), f"{actual} != {expected}"


def _same_terms(actual, expected, ordered: bool) -> bool:
    """Equal term lists, a literal being equal to one of the same value: the engine's graphs are Oxigraph stores, which rewrite a
    literal's lexical form on insert (``"4.0"^^xsd:decimal`` is ``"4"``, ``"04"^^xsd:integer`` is ``"4"``; starlayer #190), and a
    computed decimal has no fixed lexical form either."""
    import pyoxigraph as ox
    from starlayer.shacl_engine.xsd_values import parse, term_equal, value_equal

    def same(a, b):
        if isinstance(a, ox.Literal) and isinstance(b, ox.Literal) and parse(a) is not None and parse(b) is not None:
            return value_equal(a, b)
        return term_equal(a, b)

    if len(actual) != len(expected):
        return False
    left, right = [to_engine(t) for t in actual], [to_engine(t) for t in expected]
    if ordered:
        return all(same(a, b) for a, b in zip(left, right, strict=True))
    for a in left:
        match = next((b for b in right if same(a, b)), None)
        if match is None:
            return False
        right.remove(match)
    return True


def _validate(entry: ManifestEntry) -> None:
    action = next(entry.graph.objects(entry.iri, MF.action))
    data = clone_graph(
        load_document(uri_to_path(next(entry.graph.objects(action, SHT.dataGraph)))),
        StarLayerGraph,
    )
    shapes = clone_graph(
        load_document(uri_to_path(next(entry.graph.objects(action, SHT.shapesGraph)))),
        StarLayerGraph,
    )
    expected = next(entry.graph.objects(entry.iri, MF.result))
    expected_graph = node_closure(entry.graph, expected)
    expected_node = find_report_node(expected_graph)
    outcome = validate(data, shapes)
    actual_node = find_report_node(outcome.report_graph)
    assert outcome.conforms == conforms_of(expected_graph, expected_node)
    assert result_multiset(outcome.report_graph, actual_node) == result_multiset(
        expected_graph, expected_node
    )


def test_engine_node_expr(entry: ManifestEntry) -> None:
    (_eval if entry.entry_type == SHT.EvalNodeExpr else _validate)(entry)
