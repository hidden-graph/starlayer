"""Direct tests of ``parse_path`` / ``eval_path`` / ``focus_nodes`` on small inline Turtle graphs."""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, Namespace
from starlayer.shacl_engine import paths as _paths
from starlayer.shacl_engine import targets as _targets
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.terms import engine_view, from_engine, to_engine
from tests.shacl.w3c_shacl12.namespaces import SH


# The engine speaks pyoxigraph terms; these tests are written with rdflib graphs and terms, so each engine function is
# wrapped: graphs through ``engine_view``, terms through ``to_engine`` / ``from_engine``.
def _out(x):
    return [(_out(v) if isinstance(v, tuple) else from_engine(v)) for v in x] if isinstance(x, (list, tuple)) else from_engine(x)


def parse_path(graph, node):
    return _paths.parse_path(engine_view(graph), to_engine(node))


def eval_path(data, path, focus):
    return _out(_paths.eval_path(engine_view(data), path, to_engine(focus)))


def declared_shape_nodes(graph):
    return _out(_targets.declared_shape_nodes(engine_view(graph)))


def shape_targets(graph, node):
    return [tuple(_out(t)) for t in _targets.shape_targets(engine_view(graph), to_engine(node))]


def focus_nodes(data, shapes, targets, conforms=None):
    targets = tuple((to_engine(p), to_engine(v)) for p, v in targets)
    wrapped = None if conforms is None else (lambda shape, n: conforms(from_engine(shape), from_engine(n)))
    return _out(_targets.focus_nodes(engine_view(data), engine_view(shapes), targets, wrapped))

EX = Namespace("http://example.com/ns#")
PFX = """@prefix ex: <http://example.com/ns#> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> . """


def g(ttl: str) -> Graph:
    return Graph().parse(data=PFX + ttl, format="turtle")


def path_of(shapes: Graph):
    return parse_path(shapes, next(shapes.objects(EX.s, SH.path)))


DATA = g("ex:a ex:p ex:b, ex:c . ex:b ex:p ex:d . ex:c ex:p ex:d . ex:d ex:p ex:a . ex:a ex:q ex:e . ex:x ex:q ex:e .")


def ev(path_ttl: str, focus=EX.a):
    return eval_path(DATA, path_of(g(f"ex:s sh:path {path_ttl} .")), focus)


def test_pred_and_inverse():
    assert ev("ex:p") == [EX.b, EX.c]
    assert ev("[ sh:inversePath ex:p ]", EX.d) == [EX.b, EX.c]


def test_sequence_is_a_set():
    assert ev("( ex:p ex:p )") == [EX.d]


def test_alternative():
    assert ev("[ sh:alternativePath ( ex:p ex:q ) ]") == [EX.b, EX.c, EX.e]


def test_closures_terminate_on_cycles():
    assert set(ev("[ sh:oneOrMorePath ex:p ]")) == {EX.b, EX.c, EX.d, EX.a}
    zm = ev("[ sh:zeroOrMorePath ex:p ]")
    assert zm[0] == EX.a and set(zm) == {EX.a, EX.b, EX.c, EX.d} and len(zm) == 4


def test_zero_or_one():
    assert ev("[ sh:zeroOrOnePath ex:p ]") == [EX.a, EX.b, EX.c]


def test_inverse_of_sequence():
    assert ev("[ sh:inversePath ( ex:p ex:p ) ]", EX.d) == [EX.a]
    assert ev("[ sh:inversePath ( ex:q ex:p ) ]", EX.e) == []


def test_node_is_original_term():
    s = g("ex:s sh:path [ sh:inversePath ex:p ] .")
    node = next(s.objects(EX.s, SH.path))
    p = parse_path(s, node)
    assert p.node == to_engine(node) and p.args[0].node == to_engine(EX.p)


@pytest.mark.parametrize(
    "ttl",
    [
        "ex:s sh:path [ sh:inversePath ex:p ; sh:zeroOrMorePath ex:q ] .",
        "ex:s sh:path ( ex:p ) .",
        "ex:s sh:path [ sh:alternativePath ( ex:p ) ] .",
        "ex:s sh:path [ sh:alternativePath ex:p ] .",
        'ex:s sh:path "lit" .',
        "ex:s sh:path [ ex:other ex:p ] .",
        "ex:s sh:path [ sh:inversePath ex:p, ex:q ] .",
    ],
)
def test_malformed_paths(ttl):
    with pytest.raises(ShapeError):
        path_of(g(ttl))


TARGETS = g("""
ex:S1 a sh:NodeShape ; sh:targetNode ex:n, "lit" ; sh:targetClass ex:C ; sh:targetSubjectsOf ex:r ; sh:targetObjectsOf ex:r .
ex:Impl a sh:NodeShape, rdfs:Class .
ex:Impl2 a sh:ShapeClass .
ex:Off a sh:NodeShape ; sh:deactivated true .
ex:OnlyTarget sh:targetNode ex:z .
ex:Plain a rdfs:Class .
""")
TDATA = g("""
ex:i1 a ex:C . ex:i2 a ex:Sub . ex:Sub rdfs:subClassOf ex:C . ex:Loop rdfs:subClassOf ex:Sub . ex:Sub rdfs:subClassOf ex:Loop .
ex:i3 a ex:Loop . ex:u ex:r ex:v . ex:i1 a ex:Impl . ex:u ex:r ex:v2 .
""")


def test_declared_shape_nodes():
    nodes = declared_shape_nodes(TARGETS)
    assert {EX.S1, EX.Impl, EX.Impl2, EX.Off, EX.OnlyTarget} <= set(nodes)
    assert EX.Plain not in nodes and len(nodes) == len(set(nodes))


def test_implicit_class_target():
    assert (SH.targetClass, EX.Impl) in shape_targets(TARGETS, EX.Impl)
    assert (SH.targetClass, EX.Impl2) in shape_targets(TARGETS, EX.Impl2)
    assert shape_targets(TARGETS, EX.Off) == [(SH.shape, EX.Off)]
    assert (SH.targetClass, EX.Plain) not in shape_targets(TARGETS, EX.Plain)


def test_focus_nodes_all_kinds():
    foc = focus_nodes(TDATA, TARGETS, tuple(shape_targets(TARGETS, EX.S1)))
    assert foc[:2] == [EX.n, Literal("lit")]
    assert set(foc) == {EX.n, Literal("lit"), EX.i1, EX.i2, EX.i3, EX.u, EX.v, EX.v2}
    assert len(foc) == len(set(foc))


def test_target_class_instances_of_implicit():
    assert focus_nodes(TDATA, TARGETS, tuple(shape_targets(TARGETS, EX.Impl))) == [EX.i1]


def test_target_where():
    t = ((SH.targetWhere, EX.W),)
    assert focus_nodes(TDATA, TARGETS, t) == []
    assert focus_nodes(TDATA, TARGETS, t, conforms=lambda shape, n: n in (EX.u, EX.v)) == [EX.u, EX.v]


def test_sh_shape_in_data():
    d = g("ex:x sh:shape ex:S1 . ex:y sh:shape ex:Other .")
    assert focus_nodes(d, TARGETS, ((SH.shape, EX.S1),)) == [EX.x]
