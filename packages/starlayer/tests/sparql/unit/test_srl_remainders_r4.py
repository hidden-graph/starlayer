"""SRL evaluation remainders of GitHub issues #79 and #96."""

import warnings

import pytest
from rdflib import Dataset, Graph, Namespace, URIRef, Variable
from starlayer import StarLayerDataset, StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.sparql.srl import SRLError, SRLParseError, parse_ruleset

warnings.simplefilter("ignore")
E = Namespace("http://e/")
PREFIX = "PREFIX : <http://e/>\n"


def _graph(data="@prefix : <http://e/> . :a :p :b . :b :p :c ."):
    g = Graph()
    g.parse(data=data, format="turtle")
    return g


def test_now_is_one_instant_for_the_whole_evaluation():
    rules = parse_ruleset(PREFIX + "RULE { ?o :t ?n } WHERE { ?s :p ?o SET(?n := NOW()) }")
    inferred = rules.infer(_graph())
    assert len(inferred) == 2
    assert len({o for _, _, o in inferred}) == 1


def test_now_differs_between_evaluations():
    rules = parse_ruleset(PREFIX + "RULE { :x :t ?n } WHERE { :a :p :b SET(?n := NOW()) }")
    first = {o for _, _, o in rules.infer(_graph())}
    second = {o for _, _, o in rules.infer(_graph())}
    assert first != second


def test_infer_and_query_accept_a_dataset():
    rules = parse_ruleset(PREFIX + "RULE { ?x :q ?y } WHERE { ?x :p ?y }")
    ds = Dataset()
    ds.add((E.a, E.p, E.b))
    ds.add((E.c, E.p, E.d, URIRef("http://e/g")))
    assert set(rules.infer(ds)) == {(E.a, E.q, E.b)}  # the default graph, as the dataset's own queries see it
    union = Dataset(default_union=True)
    union.add((E.a, E.p, E.b, URIRef("http://e/g")))
    assert set(rules.infer(union)) == {(E.a, E.q, E.b)}
    goal = rules.rules[0].head[0]
    assert {tuple(sorted(m.items())) for m in rules.query(ds, goal)} == {
        ((Variable("x"), E.a), (Variable("y"), E.b))
    }


def test_infer_accepts_a_starlayer_dataset():
    rules = parse_ruleset(PREFIX + "RULE { ?x :q ?y } WHERE { ?x :p ?y }")
    ds = StarLayerDataset()
    ds.add((E.a, E.p, E.b))
    assert set(rules.infer(ds)) == {(E.a, E.q, E.b)}


def test_document_base_wins_over_the_base_argument():
    text = "BASE <http://b/x/>\nRULE { ?x <q> ?y } WHERE { ?x <p> ?y }"
    assert str(parse_ruleset(text, base="http://c/").rules[0].head[0].predicate) == "http://b/x/q"


def test_base_argument_is_the_initial_base():
    text = "RULE { ?x <q> ?y } WHERE { ?x <p> ?y }"
    assert str(parse_ruleset(text, base="http://c/").rules[0].head[0].predicate) == "http://c/q"


def test_undeclared_prefix_is_an_srl_parse_error():
    with pytest.raises(SRLParseError) as info:
        parse_ruleset("RULE { ?x u:q ?y } WHERE { ?x u:p ?y }")
    assert isinstance(info.value, SRLError)


@pytest.mark.parametrize("make", [Graph, StarLayerGraph])
def test_triple_function_in_set(make):
    g = make()
    g.add((E.a, E.p, E.b))
    rules = parse_ruleset(PREFIX + "RULE { ?s :t ?n } WHERE { ?s :p ?o SET(?n := TRIPLE(?s, :p, ?o)) }")
    assert set(rules.infer(g)) == {(E.a, E.t, TripleTerm(E.a, E.p, E.b))}


def test_triple_term_syntax_in_set_and_filter():
    g = _graph()
    set_rule = parse_ruleset(PREFIX + "RULE { ?s :t ?n } WHERE { ?s :p ?o SET(?n := <<( ?s :p ?o )>>) }")
    assert len(set_rule.infer(g)) == 2
    keep = parse_ruleset(
        PREFIX + "RULE { ?s :t ?o } WHERE { ?s :p ?o FILTER(TRIPLE(?s, :p, ?o) = <<( :a :p :b )>>) }"
    )
    assert set(keep.infer(g)) == {(E.a, E.t, E.b)}
    typed = parse_ruleset(PREFIX + "RULE { ?s :t ?o } WHERE { ?s :p ?o FILTER(isTRIPLE(<<( ?s :p ?o )>>)) }")
    assert len(typed.infer(g)) == 2
