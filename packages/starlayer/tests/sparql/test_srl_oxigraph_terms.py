"""SRL on the Oxigraph wrapper: pyoxigraph terms in goal patterns, row keys, and prefixes of the inferred graph."""

import pyoxigraph as ox
import pytest
import rdflib
from starlayer.graph.oxgraph import OxDataset, OxGraph
from starlayer.sparql import srl

EX = "http://example.org/"
RULES = f"PREFIX ex: <{EX}> RULE {{ ?x ex:exposedTo ?v }} WHERE {{ ?x ex:hasVulnerability ?v }}"
DATA = f"@prefix ex: <{EX}> . ex:db ex:hasVulnerability ex:v1 ."


def _ex(name):
    return ox.NamedNode(EX + name)


def _graph(cls=OxGraph):
    g = cls()
    g.parse(data=DATA, format="turtle")
    return g


@pytest.fixture(scope="module")
def ruleset():
    return srl.parse_ruleset(RULES)


def test_query_with_pyoxigraph_goal_terms(ruleset):
    goal = srl.TriplePattern(subject=rdflib.Variable("x"), predicate=_ex("exposedTo"), object=_ex("v1"))
    assert list(ruleset.query(_graph(), goal)) == [{ox.Variable("x"): _ex("db")}]


@pytest.mark.parametrize("cls", [OxGraph, OxDataset])
def test_query_with_pyoxigraph_variables(ruleset, cls):
    goal = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("exposedTo"), object=ox.Variable("v"))
    assert ruleset.query(_graph(cls), goal) == [{ox.Variable("x"): _ex("db"), ox.Variable("v"): _ex("v1")}]


def test_query_with_rdflib_goal_terms_on_oxigraph_gives_ox_variable_keys(ruleset):
    goal = srl.TriplePattern(
        subject=rdflib.Variable("x"), predicate=rdflib.URIRef(EX + "exposedTo"), object=rdflib.URIRef(EX + "v1")
    )
    assert ruleset.query(_graph(), goal) == [{ox.Variable("x"): _ex("db")}]


def test_query_on_an_rdflib_graph_keeps_rdflib_rows_and_takes_pyoxigraph_goal(ruleset):
    g = rdflib.Graph()
    g.parse(data=DATA, format="turtle")
    goal = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("exposedTo"), object=_ex("v1"))
    assert ruleset.query(g, goal) == [{rdflib.Variable("x"): rdflib.URIRef(EX + "db")}]


def test_query_with_pyoxigraph_literal_goals():
    rules = srl.parse_ruleset(f'PREFIX ex: <{EX}> RULE {{ ?x ex:label "a" }} WHERE {{ ?x ex:p ?y }}')
    g = OxGraph()
    g.parse(data=f"@prefix ex: <{EX}> . ex:s ex:p ex:o .", format="turtle")
    hit = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("label"), object=ox.Literal("a"))
    assert rules.query(g, hit) == [{ox.Variable("x"): _ex("s")}]
    miss = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("label"), object=ox.Literal("b"))
    assert rules.query(g, miss) == []


def test_query_with_a_pyoxigraph_blank_node_goal(ruleset):
    # as in a SPARQL pattern, a blank node matches anything and is not reported
    goal = srl.TriplePattern(subject=ox.BlankNode("b0"), predicate=_ex("exposedTo"), object=ox.Variable("v"))
    assert ruleset.query(_graph(), goal) == [{ox.Variable("v"): _ex("v1")}]


def test_query_with_a_pyoxigraph_triple_term_goal():
    rules = srl.parse_ruleset(f"PREFIX ex: <{EX}> RULE {{ ?x ex:says <<( ?x ex:p ?y )>> }} WHERE {{ ?x ex:p ?y }}")
    g = OxGraph()
    g.parse(data=f"@prefix ex: <{EX}> . ex:s ex:p ex:o .", format="turtle")
    triple = ox.Triple(_ex("s"), _ex("p"), _ex("o"))
    goal = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("says"), object=triple)
    assert rules.query(g, goal) == [{ox.Variable("x"): _ex("s")}]


@pytest.mark.parametrize(
    "pattern",
    [
        {"subject": "x", "predicate": _ex("exposedTo"), "object": _ex("v1")},
        {"subject": ox.Variable("x"), "predicate": None, "object": _ex("v1")},
        {"subject": ox.Variable("x"), "predicate": ox.Literal("p"), "object": _ex("v1")},
        {"subject": ox.Variable("x"), "predicate": _ex("exposedTo"), "object": 3},
    ],
)
def test_wrong_typed_goal_terms_raise(ruleset, pattern):
    with pytest.raises(TypeError):
        ruleset.query(_graph(), srl.TriplePattern(**pattern))


def test_goal_that_is_not_a_triple_pattern_raises(ruleset):
    with pytest.raises(TypeError):
        ruleset.query(_graph(), (ox.Variable("x"), _ex("p"), _ex("o")))


def test_triple_pattern_stores_rdflib_terms():
    pattern = srl.TriplePattern(subject=ox.Variable("x"), predicate=_ex("p"), object=ox.Literal("a"))
    assert pattern.subject == rdflib.Variable("x")
    assert pattern.predicate == rdflib.URIRef(EX + "p")
    assert pattern.object == rdflib.Literal("a")


@pytest.mark.parametrize("cls", [OxGraph, OxDataset])
def test_infer_has_no_rdflib_default_prefixes(ruleset, cls):
    out = ruleset.infer(_graph(cls))
    assert isinstance(out, OxGraph)
    assert dict(out.prefixes) == {"ex": EX}


def test_infer_carries_input_prefixes_and_ruleset_prefixes():
    g = OxGraph()
    g.bind("other", "http://other.example/")
    g.parse(data=DATA, format="turtle")
    rules = srl.parse_ruleset(f"PREFIX r: <{EX}r/> PREFIX ex: <{EX}> RULE {{ ?x r:q ?v }} WHERE {{ ?x ex:hasVulnerability ?v }}")
    assert dict(rules.infer(g).prefixes) == {"other": "http://other.example/", "ex": EX, "r": EX + "r/"}


def test_infer_with_no_prefixes_anywhere_has_none():
    rules = srl.parse_ruleset(f"RULE {{ ?x <{EX}q> ?v }} WHERE {{ ?x <{EX}hasVulnerability> ?v }}")
    g = OxGraph()
    g.add((_ex("db"), _ex("hasVulnerability"), _ex("v1")))
    assert dict(rules.infer(g).prefixes) == {}


def test_infer_with_a_schema_has_no_default_prefixes(ruleset):
    shapes = OxGraph()
    shapes.parse(
        data="@prefix sh: <http://www.w3.org/ns/shacl#> . [] a sh:NodeShape ; sh:targetClass <http://example.org/Nothing> .",
        format="turtle",
    )
    result = ruleset.infer(_graph(), schema=shapes)
    assert dict(result.inferred_graph.prefixes) == {"ex": EX}


def test_ruleset_to_tree_into_an_oxgraph_adds_no_prefixes(ruleset):
    tree, _root = srl.ruleset_to_tree(ruleset, OxGraph())
    assert dict(tree.prefixes) == {}


def test_default_empty_prefix_is_kept():
    rules = srl.parse_ruleset(f"PREFIX : <{EX}> RULE {{ ?x :q ?v }} WHERE {{ ?x :hasVulnerability ?v }}")
    assert rules.prefixes == {"": EX}
    assert dict(rules.infer(_graph()).prefixes)[""] == EX


def test_ruleset_prefixes_do_not_affect_equality():
    a = srl.parse_ruleset(RULES)
    b = srl.parse_ruleset(RULES.replace("ex:", "e:"))
    assert a.prefixes == {"ex": EX}
    assert b.prefixes == {"e": EX}
    assert a == b
