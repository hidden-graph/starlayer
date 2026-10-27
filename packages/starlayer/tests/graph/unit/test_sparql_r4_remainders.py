"""Remainders of GitHub issues #75 (STR of a blank node) and #93 (DELETE blank nodes, path leaks)."""

import warnings

import pytest
from rdflib import BNode, Namespace
from starlayer import StarLayerGraph
from starlayer.graph.model.triple import TripleTerm
from starlayer.sparql.parse12 import prepare_update_12

warnings.simplefilter("ignore")
E = Namespace("http://e/")
P = "PREFIX : <http://e/>\n"


def test_str_of_a_blank_node_is_an_error_so_unbound():
    g = StarLayerGraph()
    rows = list(g.query("SELECT (STR(?b) AS ?x) WHERE { BIND(BNODE() AS ?b) }"))
    assert [r[0] for r in rows] == [None]


def test_group_concat_of_str_over_a_blank_node_is_unbound_like_oxigraph():
    g = StarLayerGraph()
    g.add((E.a, E.p, BNode("b1")))
    g.add((E.a, E.p, E.o))
    rows = list(g.query(P + "SELECT (GROUP_CONCAT(STR(?o)) AS ?x) WHERE { :a :p ?o }"))
    assert [r[0] for r in rows] == [None]


@pytest.mark.parametrize(
    "update",
    [
        "DELETE DATA { :a :b <<( :a :b _:x )>> }",
        "DELETE DATA { :a :b <<( :a :b [] )>> }",
        "DELETE DATA { :a :b << :a :b _:x ~ :r >> }",
        "DELETE { ?s :p <<( :a :b _:x )>> } WHERE {}",
        "DELETE WHERE { ?s :p <<( :a :b _:x )>> }",
        "DELETE WHERE { _:x :p ?o }",
        "DELETE WHERE { ?s :p [] }",
    ],
)
def test_blank_nodes_are_rejected_in_delete_forms(update):
    with pytest.raises(ValueError):
        prepare_update_12(P + update)


def test_negated_set_and_zero_length_paths_do_not_expose_triple_term_encoding():
    g = StarLayerGraph()
    g.parse(
        data="@prefix : <http://e/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
        ":a :p :b . :r rdf:reifies <<( :a :p :b )>> . :b :q :c .",
        format="turtle12",
    )
    negated = list(g.query(P + "SELECT * WHERE { ?s !:p ?o }"))
    assert len(negated) == 2  # (:b :c) and (:r, the triple term); never the term's own components
    assert not any(isinstance(row["s"], TripleTerm) for row in negated)
    for row in g.query(P + "SELECT * WHERE { ?s :p* ?o }"):
        assert not any("PropositionForm" in str(term) or str(term) == str(E.p) for term in row)
