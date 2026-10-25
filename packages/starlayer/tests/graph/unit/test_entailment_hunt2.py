"""Entailment fixes from the third hunt (GitHub issue #97): the query-time RDFS rewrite agrees with materialized infer()."""

import warnings

import pytest
from starlayer.graph import ENTAILMENT, StarLayerGraph

warnings.simplefilter("ignore")
SCHEMA = """@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
:hasMother rdfs:subPropertyOf :hasParent . :hasParent rdfs:domain :Child ; rdfs:range :Parent .
:Child rdfs:subClassOf :Person . :typedBy rdfs:subPropertyOf rdf:type .
:a :hasMother :b . :c :typedBy :Child . :d a :Child ."""
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _graph(turtle=SCHEMA):
    g = StarLayerGraph()
    g.parse(data=turtle, format="turtle12")
    return g


def _members(rows):
    return sorted({str(r[0]).rsplit("/", 1)[-1] for r in rows})


@pytest.mark.parametrize(
    ("cls", "expected"),
    [("Child", ["a", "c", "d"]), ("Person", ["a", "c", "d"]), ("Parent", ["b"])],
)
def test_type_query_sees_domain_range_and_typing_through_subproperties(cls, expected):
    rows = _graph().query(f"PREFIX : <http://e/> SELECT ?x {{ ?x a :{cls} }}", entailment=ENTAILMENT.RDFS)
    assert _members(rows) == expected


@pytest.mark.parametrize("cls", ["Child", "Person", "Parent"])
def test_rewrite_agrees_with_the_materialized_closure(cls):
    g = _graph()
    closure = g.infer(entailment=ENTAILMENT.RDFS, mode="full")
    materialized = sorted(
        {str(s).rsplit("/", 1)[-1] for s, p, o in closure.triples((None, None, None))
         if str(p) == RDF_TYPE and str(o) == f"http://e/{cls}"}
    )
    rows = g.query(f"PREFIX : <http://e/> SELECT ?x {{ ?x a :{cls} }}", entailment=ENTAILMENT.RDFS)
    assert _members(rows) == materialized


def test_a_subproperty_query_still_works():
    rows = _graph().query("PREFIX : <http://e/> SELECT ?x { ?x :hasParent ?y }", entailment=ENTAILMENT.RDFS)
    assert _members(rows) == ["a"]


@pytest.mark.parametrize(
    "regimes",
    [ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"], {ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}],
    ids=["rdfs", "owl-rl", "both"],
)
def test_infer_is_idempotent(regimes):
    g = _graph(
        "@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . :a :p :b . :p rdfs:domain :C ."
    )
    once = g.infer(entailment=regimes, mode="full")
    twice = once.infer(entailment=regimes, mode="full")
    assert set(twice) == set(once)
