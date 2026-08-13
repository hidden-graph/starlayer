"""Phase 2 of docs/w3c-shacl12-test-suite-plan.md: run every sht:EvalNodeExpr
entry from the vendored W3C SHACL 1.2 suite (tests/node-expr/) against
starshacl.node_expressions.eval_expr().

Format (tests/node-expr/README.md, quoted in full in the plan doc): mf:action
carries sht:nodeExpr (the expression to evaluate), optional sht:focusNode,
optional sht:ignoreOrder, and zero or more sht:scope-<name> bindings. There
is no sht:dataGraph/shapesGraph here (unlike Phase 1's sht:Validate) - the
fixture's own document doubles as both, confirmed against the real fixtures
(e.g. node-expr/shnex/nodesMatching.ttl has plain ex:Org1/ex:Company1/...
triples living directly alongside the manifest, not behind an explicit
action property).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pyshacl.shapes_graph import ShapesGraph
from starlayergraph.graph.starlayer_graph import StarLayerGraph

pyshacl = pytest.importorskip("pyshacl")

from starshacl.native_components import ensure_shape_typed
from starshacl.node_expressions import eval_expr

from .ids import portable_id
from .known_failures import KNOWN_FAILURES
from .manifest import ManifestEntry, clone_graph, iter_manifest_entries, load_document
from .namespaces import MF, SH, SHNEX, SHT

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite"
TOP_MANIFEST = VENDOR_ROOT / "tests" / "manifest.ttl"

# shnex: predicates whose value is a shape reference (see
# starshacl/node_expressions.py's _shape_conforms() call sites) -
# pySHACL's own shape-graph loader has no idea these predicates exist, so a
# shape reached *only* through one of them is never auto-discovered into
# ShapesGraph._node_shape_cache. Real SHACL usage nests these under a shape
# that's independently discoverable some other way (hence this gap is
# invisible to starshacl's existing test suite); the W3C fixtures
# construct free-floating shapes purely for direct eval_expr() testing, so
# this harness must explicitly type them first - the same fix
# starshacl/native_components.py already applies for the analogous
# sh:someValue/sh:memberShape/etc. problem (ensure_shape_typed, reused here
# directly rather than reimplemented).
_SHAPE_REFERENCING_SHNEX_PREDICATES = (
    SHNEX.filterShape,
    SHNEX.findFirst,
    SHNEX.matchAll,
    SHNEX.nodesMatching,
)


def _load_node_expr_entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [entry for entry in iter_manifest_entries(TOP_MANIFEST) if entry.entry_type == SHT.EvalNodeExpr]


_ENTRIES = _load_node_expr_entries()


def pytest_generate_tests(metafunc):
    if "entry" not in metafunc.fixturenames:
        return
    if _ENTRIES:
        metafunc.parametrize("entry", _ENTRIES, ids=[portable_id(e, VENDOR_ROOT) for e in _ENTRIES])
    else:
        metafunc.parametrize(
            "entry",
            [pytest.param(None, marks=pytest.mark.skip(reason="vendored W3C suite not found - run scripts/sync_w3c_shacl12_suite.py"))],
            ids=["no-vendored-suite"],
        )


def _build_shapes_graph(document: StarLayerGraph) -> ShapesGraph:
    graph = clone_graph(document)
    for predicate in _SHAPE_REFERENCING_SHNEX_PREDICATES:
        for shape_node in graph.objects(None, predicate):
            typing_triple = ensure_shape_typed(graph, shape_node)
            if typing_triple is not None:
                graph.add(typing_triple)
    sg = ShapesGraph(graph)
    # ShapesGraph.lookup_shape_from_node() indexes _node_shape_cache
    # directly and never populates it itself - only the .shapes/
    # .shapes_from_uris() properties trigger _build_node_shape_cache()
    # lazily. Force that here, once, so every shape ensure_shape_typed()
    # just typed (and any shape pySHACL discovers normally) is actually in
    # the cache before eval_expr() ever calls lookup_shape_from_node().
    list(sg.shapes)
    return sg


def _scope_bindings(entry: ManifestEntry, action) -> dict:
    prefix = str(SHT) + "scope-"
    scope = {}
    for predicate, value in entry.graph.predicate_objects(action):
        if str(predicate).startswith(prefix):
            scope[str(predicate)[len(prefix) :]] = value
    return scope


def test_w3c_eval_node_expr(entry: ManifestEntry) -> None:
    entry_key = portable_id(entry, VENDOR_ROOT)
    if entry_key in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[entry_key])

    document = load_document(entry.source_path)
    data_graph = clone_graph(document)
    shapes_graph = _build_shapes_graph(document)

    action = next(entry.graph.objects(entry.iri, MF.action))
    expr = next(entry.graph.objects(action, SHT.nodeExpr))
    focus_node = next(entry.graph.objects(action, SHT.focusNode), None)
    ignore_order_val = next(entry.graph.objects(action, SHT.ignoreOrder), None)
    ignore_order = bool(ignore_order_val.toPython()) if ignore_order_val is not None else False
    # Only seed "focusNode" into scope when sht:focusNode was actually given -
    # var-unbound-style fixtures rely on "focusNode" being genuinely absent
    # from scope (shnex:var must treat it as unbound) when no sht:focusNode
    # is present, not present-but-bound-to-None.
    scope = _scope_bindings(entry, action)
    if focus_node is not None:
        scope["focusNode"] = focus_node

    expected = list(entry.graph.items(next(entry.graph.objects(entry.iri, MF.result))))
    actual = eval_expr(expr, focus_node, data_graph, shapes_graph, scope=scope)

    if ignore_order:
        # "cardinality must still match" (README) - a multiset comparison,
        # not just same-elements-as-a-set.
        assert Counter(actual) == Counter(expected), (
            f"node-expr result mismatch (order-independent)\nexpected: {expected}\nactual: {actual}"
        )
    else:
        assert actual == expected, f"node-expr result mismatch\nexpected: {expected}\nactual: {actual}"
