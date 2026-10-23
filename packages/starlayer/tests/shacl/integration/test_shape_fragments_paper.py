"""``extract_subgraph()`` against the Shape Fragments paper (Delva, Dimou, Jakubowski, Van den Bussche, arXiv 2112.11796) and
its W3C-style companion specification (github.com/Shape-Fragments/shape-fragments-spec). GitHub issue #11.

The paper's Conformance Theorem: the fragment of a graph that conforms to a shapes graph itself conforms to it. A fragment
holds the target triples too, so the check here keeps each focus node as an explicit ``sh:targetNode`` and asks whether it
still conforms *inside* the fragment (without that, a fragment that dropped the targets would pass vacuously: its nodes
are no longer targeted). The cases are the paper's own examples plus one per constructor Table 2 defines.

Until 2026-10-23 four of them failed (class evidence and ``sh:not`` were not extracted) and the target triples were left
out. They are fixed, and these tests are the oracle that keeps the theorem true: a fixed example set, cases for what
only shows up when several shapes' fragments are unioned, and a randomized check."""

import re
import warnings

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from rdflib import RDF, RDFS, Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import extract_subgraph, validate

E = Namespace("http://e/")
PREFIXES = (
    "@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)


def _graph(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + ttl, format="turtle12")
    return graph


def _with_focus_targets(shapes: str, focus: list[str]) -> str:
    """The same shapes, with each ``sh:targetClass`` replaced by ``sh:targetNode`` for the given focus nodes."""
    return re.sub(r"sh:targetClass :\w+", "sh:targetNode " + ", ".join(f":{f}" for f in focus), shapes)


def _conforms(data: StarLayerGraph, shapes: StarLayerGraph) -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return validate(data, shapes, meta_shacl=False).conforms


def _fragment_conforms(shapes: str, data: str, focus: list[str]) -> bool:
    strict = _graph(_with_focus_targets(shapes, focus))
    graph = _graph(data)
    assert _conforms(graph, strict), "the test graph must conform to start with"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fragment = extract_subgraph(graph, strict)
    return _conforms(fragment, strict)


# name -> (focus nodes, shapes, data)
CASES = {
    "workshop paper: qualifiedMinCount and class (paper section 2)": (
        ["p1"],
        ":W sh:targetClass :WorkshopPaper ; sh:property [ sh:path :author ; sh:qualifiedMinCount 1 ; sh:qualifiedValueShape [ sh:class :Student ] ] .",
        ":p1 a :WorkshopPaper ; :author :Anne, :Bob, :Alice . :Anne a :Professor . :Bob a :Professor . :Alice a :Student .",
    ),
    "person with an address shape: node, datatype, maxCount (paper section 2)": (
        ["v"],
        ":A a sh:NodeShape ; sh:property [ sh:path :postalCode ; sh:datatype xsd:string ; sh:maxCount 1 ] . "
        ":P a sh:NodeShape ; sh:targetClass :Person ; sh:property [ sh:path :address ; sh:minCount 1 ; sh:node :A ] .",
        ':v a :Person ; :address :x . :x :postalCode "9000" . :x :other :y .',
    ),
    "HappyAtWork: not and disjoint (paper section 2)": (
        ["v"],
        ":H sh:targetClass :Person ; sh:not [ sh:property [ sh:path :friend ; sh:disjoint :colleague ] ] .",
        ":v a :Person ; :friend :a, :b ; :colleague :b, :c .",
    ),
    "Example 3.8, shape 1: minCount 1 author": (
        ["p1"],
        ":S1 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:minCount 1 ] .",
        ":p1 a :paper ; :auth :Anne, :Bob . :Anne a :prof . :Bob a :student .",
    ),
    "Example 3.8, shape 2: at most one author who is not a student": (
        ["p1"],
        ":S2 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:qualifiedMaxCount 1 ; sh:qualifiedValueShape [ sh:not [ sh:class :student ] ] ] .",
        ":p1 a :paper ; :auth :Anne, :Bob . :Anne a :prof . :Bob a :student .",
    ),
    "Example 3.8, both shapes in one schema (the fragments are unioned)": (
        ["p1"],
        ":S1 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:minCount 1 ] . "
        ":S2 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:qualifiedMaxCount 1 ; sh:qualifiedValueShape [ sh:not [ sh:class :student ] ] ] .",
        ":p1 a :paper ; :auth :Anne, :Bob . :Anne a :prof . :Bob a :student .",
    ),
    "class on a value": (
        ["t"],
        ":S sh:targetClass :Task ; sh:property [ sh:path :assignee ; sh:class :Person ] .",
        ":t a :Task ; :assignee :ann . :ann a :Person .",
    ),
    "class through a subclass": (
        ["t"],
        ":S sh:targetClass :Task ; sh:property [ sh:path :assignee ; sh:class :Person ] .",
        ":t a :Task ; :assignee :ann . :ann a :Student . :Student rdfs:subClassOf :Person .",
    ),
    "xone": (
        ["t"],
        ":S sh:targetClass :T ; sh:xone ( [ sh:property [ sh:path :a ; sh:minCount 1 ] ] [ sh:property [ sh:path :b ; sh:minCount 1 ] ] ) .",
        ":t a :T ; :a 1 .",
    ),
    "xone where the other disjunct fails only because a triple is there": (
        ["t"],
        ":S sh:targetClass :T ; sh:xone ( [ sh:property [ sh:path :a ; sh:minCount 1 ] ] [ sh:not [ sh:property [ sh:path :c ; sh:minCount 1 ] ] ] ) .",
        ":t a :T ; :a 1 ; :c 1 .",
    ),
    "not around a minCount (the node has no :c)": (
        ["t"],
        ":S sh:targetClass :T ; sh:not [ sh:property [ sh:path :c ; sh:minCount 1 ] ] .",
        ":t a :T ; :a 1 .",
    ),
    "not around a maxCount (the node has at least two :c)": (
        ["t"],
        ":S sh:targetClass :T ; sh:not [ sh:property [ sh:path :c ; sh:maxCount 1 ] ] .",
        ":t a :T ; :c 1, 2 .",
    ),
    "not around a class (the value is not a Person)": (
        ["t"],
        ":S sh:targetClass :T ; sh:property [ sh:path :p ; sh:not [ sh:class :Person ] ] .",
        ":t a :T ; :p :x . :x a :Robot .",
    ),
    "not inside a nested shape": (
        ["t"],
        ":N sh:property [ sh:path :age ; sh:not [ sh:datatype xsd:string ] ] . :S sh:targetClass :T ; sh:property [ sh:path :p ; sh:node :N ] .",
        ":t a :T ; :p :x . :x :age 7 .",
    ),
    "equals": (
        ["t"],
        ":S sh:targetClass :T ; sh:property [ sh:path :a ; sh:equals :b ] .",
        ":t a :T ; :a 1 ; :b 1 .",
    ),
    "or": (
        ["t"],
        ":S sh:targetClass :T ; sh:or ( [ sh:property [ sh:path :a ; sh:minCount 1 ] ] [ sh:property [ sh:path :b ; sh:minCount 1 ] ] ) .",
        ":t a :T ; :a 1 ; :b 2 .",
    ),
}


@pytest.mark.parametrize(("focus", "shapes", "data"), list(CASES.values()), ids=list(CASES))
def test_the_focus_node_still_conforms_inside_its_fragment(focus, shapes, data) -> None:
    """The paper's Conformance Theorem / Sufficiency Lemma, made non-vacuous by keeping the focus node a target."""
    assert _fragment_conforms(shapes, data, focus)


# --------------------------------------------------------------------------- the target triples (spec section 5.2)
def _fragment(shapes: str, data: str, **kwargs) -> set[tuple]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return set(extract_subgraph(_graph(data), _graph(shapes), **kwargs))


def test_the_fragment_holds_the_target_triples() -> None:
    shapes = ":S sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:minCount 1 ] ."
    data = ":p1 a :paper ; :auth :Anne ."
    assert (E.p1, RDF.type, E.paper) in _fragment(shapes, data)
    assert (E.p1, RDF.type, E.paper) not in _fragment(shapes, data, include_targets=False)


def test_a_class_target_includes_the_subclass_chain_that_makes_the_node_a_member() -> None:
    shapes = ":S sh:targetClass :Animal ; sh:property [ sh:path :name ; sh:minCount 1 ] ."
    data = ':rex a :Dog ; :name "Rex" . :Dog rdfs:subClassOf :Mammal . :Mammal rdfs:subClassOf :Animal . :Dog rdfs:subClassOf :Pet .'
    fragment = _fragment(shapes, data)
    assert {(E.rex, RDF.type, E.Dog), (E.Dog, RDFS.subClassOf, E.Mammal), (E.Mammal, RDFS.subClassOf, E.Animal)} <= fragment
    assert (E.Dog, RDFS.subClassOf, E.Pet) not in fragment  # not on a path to :Animal


def test_a_subjects_of_target_includes_the_triples_with_that_predicate() -> None:
    shapes = ":S sh:targetSubjectsOf :owns ; sh:property [ sh:path :name ; sh:minCount 1 ] ."
    data = ':a :owns :x, :y ; :name "A" . :b :name "B" .'
    fragment = _fragment(shapes, data)
    assert {(E.a, E.owns, E.x), (E.a, E.owns, E.y)} <= fragment
    assert not any(s == E.b for s, _, _ in fragment)


def test_an_objects_of_target_includes_the_triples_pointing_at_the_node() -> None:
    shapes = ":S sh:targetObjectsOf :owns ; sh:property [ sh:path :name ; sh:minCount 1 ] ."
    data = ':a :owns :x . :x :name "X" . :b :owns :y . :y :name "Y" .'
    assert {(E.a, E.owns, E.x), (E.b, E.owns, E.y)} <= _fragment(shapes, data)


def test_a_node_target_has_no_target_triple() -> None:
    shapes = ":S sh:targetNode :a ; sh:property [ sh:path :name ; sh:minCount 1 ] ."
    data = ':a a :T ; :name "A" .'
    assert _fragment(shapes, data) == _fragment(shapes, data, include_targets=False) == {(E.a, E.name, _lit("A"))}


def _lit(value: str):
    from rdflib import Literal

    return Literal(value)


def test_a_node_that_is_not_a_target_contributes_nothing() -> None:
    assert _fragment(":S sh:targetClass :T ; sh:property [ sh:path :a ; sh:minCount 1 ] .", ":x a :U ; :a 1 .") == set()


def test_class_evidence_is_the_paper_neighborhood() -> None:
    """The workshop example (paper section 2): the author triple, the student's type triple, and the paper's own type."""
    shapes, data = CASES["workshop paper: qualifiedMinCount and class (paper section 2)"][1:]
    assert _fragment(shapes, data) == {
        (E.p1, RDF.type, E.WorkshopPaper),
        (E.p1, E.author, E.Alice),
        (E.Alice, RDF.type, E.Student),
    }


def test_negation_keeps_the_evidence_that_makes_it_hold() -> None:
    """HappyAtWork: the friend who is also a colleague, and the paper's neighborhood is contained in what we return."""
    shapes, data = CASES["HappyAtWork: not and disjoint (paper section 2)"][1:]
    fragment = _fragment(shapes, data)
    assert {(E.v, RDF.type, E.Person), (E.v, E.friend, E.b), (E.v, E.colleague, E.b)} <= fragment


# --------------------------------------------------------------------------- randomized: the Conformance Theorem
NODES = ["n0", "n1", "n2"]
CLASSES = ["A", "B"]


@st.composite
def _constraint(draw, depth: int = 0):
    """A node-shape constraint on :p / :q values, as Turtle for the inside of a shape."""
    path = draw(st.sampled_from(["p", "q"]))
    kinds = ["min", "max", "class", "qmin", "qmax", "hasvalue", "equals", "disjoint"]
    if depth < 1:
        kinds += ["node", "not", "or", "xone"]
    kind = draw(st.sampled_from(kinds))
    cls = draw(st.sampled_from(CLASSES))
    count = draw(st.integers(1, 2))
    if kind == "min":
        return f"sh:property [ sh:path :{path} ; sh:minCount {count} ]"
    if kind == "max":
        return f"sh:property [ sh:path :{path} ; sh:maxCount {count} ]"
    if kind == "class":
        return f"sh:property [ sh:path :{path} ; sh:class :{cls} ]"
    if kind == "qmin":
        return f"sh:property [ sh:path :{path} ; sh:qualifiedMinCount {count} ; sh:qualifiedValueShape [ sh:class :{cls} ] ]"
    if kind == "qmax":
        return f"sh:property [ sh:path :{path} ; sh:qualifiedMaxCount {count} ; sh:qualifiedValueShape [ sh:class :{cls} ] ]"
    if kind == "hasvalue":
        return f"sh:property [ sh:path :{path} ; sh:hasValue :{draw(st.sampled_from(NODES))} ]"
    if kind == "equals":
        return f"sh:property [ sh:path :{path} ; sh:equals :{'q' if path == 'p' else 'p'} ]"
    if kind == "disjoint":
        return f"sh:property [ sh:path :{path} ; sh:disjoint :{'q' if path == 'p' else 'p'} ]"
    inner = [draw(_constraint(depth + 1)) for _ in range(2)]
    if kind == "node":
        return f"sh:property [ sh:path :{path} ; sh:node [ {inner[0]} ] ]"
    if kind == "not":
        return f"sh:not [ {inner[0]} ]"
    members = " ".join(f"[ {i} ]" for i in inner)
    return f"sh:{'or' if kind == 'or' else 'xone'} ( {members} )"


@st.composite
def _case(draw):
    constraints = draw(st.lists(_constraint(), min_size=1, max_size=3))
    shapes = ":S sh:targetClass :T ; " + " ; ".join(constraints) + " ."
    triples = []
    for node in NODES:
        for cls in draw(st.lists(st.sampled_from(CLASSES + ["T"]), max_size=2, unique=True)):
            triples.append(f":{node} a :{cls} .")
        for pred in ("p", "q"):
            for obj in draw(st.lists(st.sampled_from(NODES), max_size=2, unique=True)):
                triples.append(f":{node} :{pred} :{obj} .")
    return shapes, " ".join(triples)


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow])
@given(_case())
def test_the_conformance_theorem_holds_for_random_shapes_and_graphs(case) -> None:
    """Generate a shape and a graph; when the graph conforms, its fragment must too (focus nodes kept as targets)."""
    shapes, data = case
    graph = _graph(data)
    focus = sorted({s.rsplit("/", 1)[-1] for s in map(str, graph.subjects(RDF.type, E["T"]))})
    assume(focus)
    strict = _graph(_with_focus_targets(shapes, focus))
    assume(_conforms(graph, strict))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fragment = extract_subgraph(graph, strict)
    assert _conforms(fragment, strict), (shapes, data)
