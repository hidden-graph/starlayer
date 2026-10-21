"""``extract_subgraph()`` against the Shape Fragments paper (Delva, Dimou, Jakubowski, Van den Bussche, arXiv 2112.11796) and
its W3C-style companion specification (github.com/Shape-Fragments/shape-fragments-spec). GitHub issue #11.

The paper's Conformance Theorem: the fragment of a graph that conforms to a shapes graph itself conforms to it. Because a
fragment holds the target triples too, the check here keeps each focus node as an explicit ``sh:targetNode`` and asks
whether it still conforms *inside* the fragment. The cases are the paper's own examples plus one per constructor that
Table 2 defines. Four fail today; each is a strict xfail that names the paper section, so a fix shows up as an XPASS."""

import re
import warnings

import pytest
from starlayer import StarLayerGraph
from starlayer.shacl import extract_subgraph, validate

PREFIXES = (
    "@prefix : <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
)


def _graph(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + ttl, format="turtle12")
    return graph


# name -> (focus node, shapes, data, why it fails today or None)
CASES = {
    "workshop paper: qualifiedMinCount and class (paper section 2)": (
        "p1",
        ":W sh:targetClass :WorkshopPaper ; sh:property [ sh:path :author ; sh:qualifiedMinCount 1 ; sh:qualifiedValueShape [ sh:class :Student ] ] .",
        ":p1 a :WorkshopPaper ; :author :Anne, :Bob, :Alice . :Anne a :Professor . :Bob a :Professor . :Alice a :Student .",
        "a class constraint's evidence is missing: the triple (:Alice a :Student) is not extracted (spec section 6.1)",
    ),
    "person with an address shape: node, datatype, maxCount (paper section 2)": (
        "v",
        ":A a sh:NodeShape ; sh:property [ sh:path :postalCode ; sh:datatype xsd:string ; sh:maxCount 1 ] . "
        ":P a sh:NodeShape ; sh:targetClass :Person ; sh:property [ sh:path :address ; sh:minCount 1 ; sh:node :A ] .",
        ':v a :Person ; :address :x . :x :postalCode "9000" . :x :other :y .',
        None,
    ),
    "HappyAtWork: not and disjoint (paper section 2)": (
        "v",
        ":H sh:targetClass :Person ; sh:not [ sh:property [ sh:path :friend ; sh:disjoint :colleague ] ] .",
        ":v a :Person ; :friend :a, :b ; :colleague :b, :c .",
        "sh:not contributes no triples, so the (friend, colleague) pair that makes the node conform is missing (paper Table 2 not-disjoint; spec section 7.4)",
    ),
    "Example 3.8, shape 1: minCount 1 author": (
        "p1",
        ":S1 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:minCount 1 ] .",
        ":p1 a :paper ; :auth :Anne, :Bob . :Anne a :prof . :Bob a :student .",
        None,
    ),
    "Example 3.8, shape 2: at most one author who is not a student": (
        "p1",
        ":S2 sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:qualifiedMaxCount 1 ; sh:qualifiedValueShape [ sh:not [ sh:class :student ] ] ] .",
        ":p1 a :paper ; :auth :Anne, :Bob . :Anne a :prof . :Bob a :student .",
        None,
    ),
    "class on a value": (
        "t",
        ":S sh:targetClass :Task ; sh:property [ sh:path :assignee ; sh:class :Person ] .",
        ":t a :Task ; :assignee :ann . :ann a :Person .",
        "a class constraint's evidence is missing: the triple (:ann a :Person) is not extracted (spec section 6.1)",
    ),
    "xone": (
        "t",
        ":S sh:targetClass :T ; sh:xone ( [ sh:property [ sh:path :a ; sh:minCount 1 ] ] [ sh:property [ sh:path :b ; sh:minCount 1 ] ] ) .",
        ":t a :T ; :a 1 .",
        None,
    ),
    "not around a minCount (the node has no :c)": (
        "t",
        ":S sh:targetClass :T ; sh:not [ sh:property [ sh:path :c ; sh:minCount 1 ] ] .",
        ":t a :T ; :a 1 .",
        None,
    ),
    "not around a maxCount (the node has at least two :c)": (
        "t",
        ":S sh:targetClass :T ; sh:not [ sh:property [ sh:path :c ; sh:maxCount 1 ] ] .",
        ":t a :T ; :c 1, 2 .",
        "sh:not contributes no triples, so the two (:t :c ...) triples that make the node conform are missing (spec section 7.1)",
    ),
    "equals": (
        "t",
        ":S sh:targetClass :T ; sh:property [ sh:path :a ; sh:equals :b ] .",
        ":t a :T ; :a 1 ; :b 1 .",
        None,
    ),
    "or": (
        "t",
        ":S sh:targetClass :T ; sh:or ( [ sh:property [ sh:path :a ; sh:minCount 1 ] ] [ sh:property [ sh:path :b ; sh:minCount 1 ] ] ) .",
        ":t a :T ; :a 1 ; :b 2 .",
        None,
    ),
}


def _params():
    for name, (focus, shapes, data, why) in CASES.items():
        marks = [pytest.mark.xfail(strict=True, reason=why)] if why else []
        yield pytest.param(focus, shapes, data, id=name, marks=marks)


@pytest.mark.parametrize(("focus", "shapes", "data"), list(_params()))
def test_the_focus_node_still_conforms_inside_its_fragment(focus, shapes, data) -> None:
    """The paper's Conformance Theorem / Sufficiency Lemma, made non-vacuous by keeping the focus node a target."""
    strict_shapes = _graph(re.sub(r"sh:targetClass :\w+", f"sh:targetNode :{focus}", shapes))
    graph = _graph(data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert validate(graph, strict_shapes, meta_shacl=False).conforms, "the test graph must conform to start with"
        fragment = extract_subgraph(graph, strict_shapes)
        assert validate(fragment, strict_shapes, meta_shacl=False).conforms


@pytest.mark.xfail(
    strict=True,
    reason="the paper's neighborhood also holds the target triples (phi AND tau; spec section 5.2), e.g. (:p1 a :paper); extract_subgraph() leaves them out",
)
def test_the_fragment_holds_the_target_triples() -> None:
    shapes = _graph(":S sh:targetClass :paper ; sh:property [ sh:path :auth ; sh:minCount 1 ] .")
    graph = _graph(":p1 a :paper ; :auth :Anne .")
    fragment = extract_subgraph(graph, shapes)
    assert any(str(s).endswith("/p1") and str(o).endswith("/paper") for s, _, o in fragment)
