"""extract_subgraph() over every property path form keeps the Conformance Theorem (GitHub issue #62).

If the data conforms to the shapes, the fragment conforms too. For sh:oneOrMorePath the fragment used to drop every edge
leaving the focus node (the focus is not one of the nodes the path reaches), so it was empty and no longer conformed.
"""

import warnings

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from rdflib import Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import extract_subgraph, validate

E = Namespace("http://e/")
PRE = "@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PRE + ttl, format="turtle12")
    return g


def _shape(path: str, extra: str = "sh:minCount 1") -> StarLayerGraph:
    return _g(f":A a sh:NodeShape ; sh:targetNode :n0 ; sh:property [ sh:path {path} ; {extra} ] .")


def _conforms(data, shapes) -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return validate(data, shapes, meta_shacl=False).conforms


def _fragment(data, shapes):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract_subgraph(data, shapes)


@pytest.mark.parametrize(
    ("path", "data", "edges"),
    [
        ("[ sh:oneOrMorePath :p ]", ":n0 :p :n1 .", {("n0", "n1")}),
        ("[ sh:oneOrMorePath :p ]", ":n0 :p :n1 . :n1 :p :n2 .", {("n0", "n1"), ("n1", "n2")}),
        ("[ sh:oneOrMorePath :p ]", ":n0 :p :n1 . :n1 :p :n0 .", {("n0", "n1"), ("n1", "n0")}),
        ("[ sh:oneOrMorePath :p ]", ":n0 :p :n1, :n2 . :n2 :p :n3 .", {("n0", "n1"), ("n0", "n2"), ("n2", "n3")}),
        ("[ sh:oneOrMorePath :p ]", ":n0 :p :n0 .", {("n0", "n0")}),
        ("[ sh:zeroOrMorePath :p ]", ":n0 :p :n1 . :n1 :p :n2 .", {("n0", "n1"), ("n1", "n2")}),
        ("[ sh:zeroOrOnePath :p ]", ":n0 :p :n1 . :n1 :p :n2 .", {("n0", "n1")}),
        ("( :p [ sh:oneOrMorePath :q ] )", ":n0 :p :n1 . :n1 :q :n2 . :n2 :q :n3 .", {("n0", "n1"), ("n1", "n2"), ("n2", "n3")}),
    ],
)
def test_the_fragment_has_every_edge_the_path_walked(path, data, edges) -> None:
    shapes, graph = _shape(path), _g(data)
    assert _conforms(graph, shapes)
    fragment = _fragment(graph, shapes)
    assert {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1]) for s, p, o in fragment if str(p).endswith(("/p", "/q"))} == edges
    assert _conforms(fragment, shapes)


def test_the_original_report_is_fixed() -> None:
    shapes, graph = _shape("[ sh:oneOrMorePath :p ]"), _g(":n0 :p :n1 .")
    fragment = _fragment(graph, shapes)
    assert len(fragment) >= 1 and _conforms(fragment, shapes)


# --- the Conformance Theorem over generated path expressions, shapes and graphs
BASE = ["p", "q"]


@st.composite
def _path(draw, depth=0):
    """A property path as a (SHACL Turtle, SPARQL property path) pair describing the same path."""
    if depth >= 2 or draw(st.integers(0, 2)) == 0:
        name = draw(st.sampled_from(BASE))
        return f":{name}", f":{name}"
    kind = draw(st.sampled_from(["inverse", "alt", "seq", "zom", "oom", "zoo"]))
    a, sa = draw(_path(depth + 1))
    if kind == "inverse":
        # SHACL's inverse path takes a predicate IRI (pySHACL and the walker assume the same), so invert only a bare predicate
        return (f"[ sh:inversePath {a} ]", f"^({sa})") if a.startswith(":") else (a, sa)
    if kind in ("zom", "oom", "zoo"):
        key, op = {"zom": ("zeroOrMorePath", "*"), "oom": ("oneOrMorePath", "+"), "zoo": ("zeroOrOnePath", "?")}[kind]
        return f"[ sh:{key} {a} ]", f"({sa}){op}"
    b, sb = draw(_path(depth + 1))
    return (f"[ sh:alternativePath ( {a} {b} ) ]", f"(({sa})|({sb}))") if kind == "alt" else (f"( {a} {b} )", f"(({sa})/({sb}))")


@st.composite
def _case(draw):
    path, sparql = draw(_path())
    extra = draw(st.sampled_from(["sh:minCount 1", "sh:minCount 2", "sh:maxCount 1", "sh:maxCount 2", "sh:minCount 1 ; sh:maxCount 3"]))
    edges = []
    for pred in BASE:
        for s in range(4):
            for o in range(4):
                if draw(st.integers(0, 4)) == 0:
                    edges.append(f":n{s} :{pred} :n{o} .")
    return path, sparql, extra, " ".join(edges) or ":n0 :other :n1 ."


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow])
@given(_case())
def test_if_the_data_conforms_so_does_its_fragment_for_any_property_path(case) -> None:
    path, _sparql, extra, data = case
    shapes, graph = _shape(path, extra), _g(data)
    assume(_conforms(graph, shapes))
    fragment = _fragment(graph, shapes)
    assert _conforms(fragment, shapes), (path, extra, data)


# --- the public path_values() against the SPARQL engine's own property paths
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow])
@given(_case())
def test_path_values_agree_with_sparql_property_paths(case) -> None:
    from rdflib import Graph
    from starlayer.shacl.paths import path_values

    path, sparql, _extra, data = case
    shapes, graph = _shape(path), _g(data)
    path_node = shapes.value(E.A, Namespace("http://www.w3.org/ns/shacl#").property)
    path_node = shapes.value(path_node, Namespace("http://www.w3.org/ns/shacl#").path)
    plain = Graph()
    for t in graph:
        plain.add(t)
    expected = {row[0] for row in plain.query(f"PREFIX : <http://e/> SELECT DISTINCT ?o WHERE {{ :n0 {sparql} ?o }}")}
    assert set(path_values(graph, E.n0, path_node, shapes)) == expected, (path, sparql, data)


@pytest.mark.parametrize(
    ("path", "sparql", "data"),
    [
        ("[ sh:zeroOrMorePath [ sh:inversePath :p ] ]", "(^:p)*", ":n1 :p :n0 . :n2 :p :n1 ."),
        ("[ sh:oneOrMorePath [ sh:inversePath :p ] ]", "(^:p)+", ":n1 :p :n0 . :n2 :p :n1 ."),
        ("[ sh:oneOrMorePath ( :p :q ) ]", "(:p/:q)+", ":n0 :p :n1 . :n1 :q :n2 . :n2 :p :n3 . :n3 :q :n4 ."),
        ("[ sh:oneOrMorePath [ sh:alternativePath ( :p :q ) ] ]", "(:p|:q)+", ":n0 :p :n1 . :n1 :q :n2 . :n2 :p :n3 ."),
        ("[ sh:zeroOrOnePath [ sh:inversePath :p ] ]", "(^:p)?", ":n1 :p :n0 . :n2 :p :n1 ."),
    ],
)
def test_a_repeated_complex_path_is_followed(path, sparql, data) -> None:
    from rdflib import Graph
    from starlayer.shacl.paths import path_values

    shapes, graph = _shape(path), _g(data)
    prop = shapes.value(E.A, Namespace("http://www.w3.org/ns/shacl#").property)
    path_node = shapes.value(prop, Namespace("http://www.w3.org/ns/shacl#").path)
    plain = Graph()
    for t in graph:
        plain.add(t)
    expected = {row[0] for row in plain.query(f"PREFIX : <http://e/> SELECT DISTINCT ?o WHERE {{ :n0 {sparql} ?o }}")}
    assert len(expected) >= 1
    assert set(path_values(graph, E.n0, path_node, shapes)) == expected
