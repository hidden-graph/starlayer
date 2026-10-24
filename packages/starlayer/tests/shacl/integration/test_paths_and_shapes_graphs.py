"""path_values()/is_inverse() (GitHub issue #30) and shapes_graphs()/shapes_graph_members() (GitHub issue #17)."""

import pytest
from rdflib import Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl.paths import is_inverse, path_values
from starlayer.shacl.shapes_graphs import shapes_graph_members, shapes_graphs

EX = Namespace("http://e/")
SH_PATH = Namespace("http://www.w3.org/ns/shacl#").path
PREFIXES = (
    "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
)


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


# ---------------------------------------------------------------- paths (#30)
DATA = _graph("ex:a ex:p ex:b . ex:b ex:p ex:c . ex:c ex:p ex:a . ex:a ex:q ex:d . ex:x ex:r ex:a .")


def _path(ttl: str):
    shapes = _graph("ex:S sh:path " + ttl + " .")
    return shapes, shapes.value(EX.S, SH_PATH)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("ex:p", {EX.b}),
        ("[ sh:inversePath ex:p ]", {EX.c}),
        ("[ sh:alternativePath ( ex:p ex:q ) ]", {EX.b, EX.d}),
        ("( ex:p ex:p )", {EX.c}),
        ("[ sh:zeroOrMorePath ex:p ]", {EX.a, EX.b, EX.c}),
        ("[ sh:oneOrMorePath ex:p ]", {EX.a, EX.b, EX.c}),
        ("[ sh:zeroOrOnePath ex:p ]", {EX.a, EX.b}),
        ("( [ sh:inversePath ex:r ] ex:p )", set()),
        ("( ex:p [ sh:inversePath ex:p ] )", {EX.a}),
    ],
)
def test_each_path_form_from_a_path_written_in_another_graph(path, expected) -> None:
    shapes, root = _path(path)
    assert path_values(DATA, EX.a, root, shapes) == frozenset(expected)


def test_a_path_in_the_data_graph_itself_needs_no_shapes_graph() -> None:
    graph = _graph("ex:a ex:p ex:b . ex:S sh:path [ sh:inversePath ex:p ] .")
    root = graph.value(EX.S, SH_PATH)
    assert path_values(graph, EX.b, root) == frozenset({EX.a})


def test_a_repetition_path_stops_on_a_cycle() -> None:
    shapes, root = _path("[ sh:oneOrMorePath ex:p ]")
    assert path_values(DATA, EX.b, root, shapes) == frozenset({EX.a, EX.b, EX.c})


def test_an_unrecognized_blank_node_path_raises() -> None:
    shapes = _graph("ex:S sh:path [ ex:nonsense ex:p ] .")
    root = shapes.value(EX.S, SH_PATH)
    with pytest.raises(NotImplementedError):
        path_values(DATA, EX.a, root, shapes)


def test_is_inverse_is_true_only_for_a_top_level_inverse_path() -> None:
    inverse, inverse_root = _path("[ sh:inversePath ex:p ]")
    seq, seq_root = _path("( [ sh:inversePath ex:p ] ex:q )")
    plain, plain_root = _path("ex:p")
    assert is_inverse(inverse, inverse_root)
    assert not is_inverse(seq, seq_root)
    assert not is_inverse(plain, plain_root)


# ---------------------------------------------------------------- shapes graphs (#17)
PACKAGED = """
ex:G1 a sh:ShapesGraph ; rdfs:member ex:ByMember ; owl:imports ex:G2 .
ex:G2 a sh:ShapesGraph ; rdfs:member ex:Imported .
ex:G3 a sh:ShapesGraph .
ex:ByMember a sh:NodeShape .
ex:ByDefinition a sh:NodeShape ; rdfs:isDefinedBy ex:G1 .
ex:Imported a sh:NodeShape .
ex:Other a sh:NodeShape ; rdfs:isDefinedBy ex:G3 .
ex:Loose a sh:NodeShape .
"""


def test_shapes_graphs_lists_the_declared_modules_sorted() -> None:
    assert shapes_graphs(_graph(PACKAGED)) == [EX.G1, EX.G2, EX.G3]


def test_a_graph_with_no_shapes_graph_lists_none() -> None:
    assert shapes_graphs(_graph("ex:S a sh:NodeShape .")) == []


def test_members_by_all_three_mechanisms() -> None:
    members = shapes_graph_members(_graph(PACKAGED), EX.G1)
    assert members == frozenset({EX.ByMember, EX.ByDefinition, EX.Imported})


def test_a_module_without_imports_has_only_its_own_members() -> None:
    assert shapes_graph_members(_graph(PACKAGED), EX.G2) == frozenset({EX.Imported})
    assert shapes_graph_members(_graph(PACKAGED), EX.G3) == frozenset({EX.Other})


def test_a_shape_in_no_module_is_in_no_membership() -> None:
    graph = _graph(PACKAGED)
    assert all(EX.Loose not in shapes_graph_members(graph, g) for g in shapes_graphs(graph))


def test_an_iri_that_is_not_a_shapes_graph_gives_none_not_empty() -> None:
    assert shapes_graph_members(_graph(PACKAGED), EX.Nope) is None
    assert shapes_graph_members(_graph(PACKAGED), EX.Loose) is None


def test_an_import_that_is_not_a_local_shapes_graph_raises() -> None:
    with pytest.raises(ValueError, match="owl:imports"):
        shapes_graph_members(_graph("ex:G1 a sh:ShapesGraph ; owl:imports ex:Missing ."), EX.G1)


def test_an_import_cycle_terminates() -> None:
    graph = _graph("ex:A a sh:ShapesGraph ; owl:imports ex:B ; rdfs:member ex:x . ex:B a sh:ShapesGraph ; owl:imports ex:A ; rdfs:member ex:y .")
    assert shapes_graph_members(graph, EX.A) == frozenset({EX.x, EX.y})


def test_extract_shapes_graph_agrees_with_the_members() -> None:
    graph = _graph(PACKAGED)
    extracted = StarShaclSchema(shacl_graph=graph).extract_shapes_graph(EX.G1)
    for member in shapes_graph_members(graph, EX.G1):
        assert (member, None, None) in extracted
    assert (EX.Loose, None, None) not in extracted and (EX.Other, None, None) not in extracted
