"""SRL fixes from the third hunt (GitHub issue #96)."""

import signal
import warnings

import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.sparql.srl import SRLParseError, parse_ruleset

warnings.simplefilter("ignore")
E = "http://e/"
PREFIX = f"PREFIX : <{E}>\n"


def _graph(turtle):
    g = Graph()
    g.parse(data=f"@prefix : <{E}> . " + turtle, format="turtle")
    return g


class _Timeout(Exception):
    pass


def _with_timeout(seconds, fn):
    def _raise(*_):
        raise _Timeout

    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(seconds)
    try:
        return fn()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_head_blank_node_inside_a_triple_term_makes_the_rule_run_once():
    rules = parse_ruleset(PREFIX + "RULE { :a :p <<( :a :q [] )>> } WHERE { :a :q ?y }")
    inferred = _with_timeout(60, lambda: rules.infer(_graph(":a :q :b .")))
    assert len(inferred) == 1


@pytest.mark.parametrize(
    "rule",
    [
        "RULE { ?x ?v ?x } WHERE { ?x :n ?v }",  # literal as predicate
        "RULE { ?v :p ?x } WHERE { ?x :n ?v }",  # literal as subject
    ],
)
def test_head_instance_that_is_not_a_valid_triple_is_skipped(rule):
    assert len(parse_ruleset(PREFIX + rule).infer(_graph(":b :n 1 ."))) == 0


def test_valid_head_instances_are_still_inferred():
    inferred = parse_ruleset(PREFIX + "RULE { ?x :m ?v } WHERE { ?x :n ?v }").infer(_graph(":b :n 1 ."))
    assert set(inferred) == {(URIRef(E + "b"), URIRef(E + "m"), Literal(1))}


@pytest.mark.parametrize(
    "body",
    ["FILTER NOT EXISTS { ?x :q ?y }", "FILTER EXISTS { ?x :q ?y }", "SET(?z := EXISTS { ?x :q ?y })"],
)
def test_exists_is_rejected_when_the_rule_set_is_parsed(body):
    with pytest.raises(SRLParseError):
        parse_ruleset(PREFIX + f"RULE {{ ?x :q ?y }} WHERE {{ ?x :p ?y {body} }}")


def test_schema_validates_the_base_graph_plus_the_inferred_triples():
    shapes = Graph()
    shapes.parse(
        data=f"""@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix : <{E}> .
        :S a sh:NodeShape ; sh:targetNode :a ; sh:property [ sh:path :p ; sh:minCount 1 ] .""",
        format="turtle",
    )
    rules = parse_ruleset(PREFIX + "RULE { ?x :q 1 } WHERE { ?x :p ?y }")
    assert rules.infer(_graph(":a :p 1 ."), schema=shapes).validation.conforms is True
