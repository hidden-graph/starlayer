"""Regression tests for the SRL bug hunt (parser, well-formedness, stratification, evaluation)."""

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql import srl

PRE = "PREFIX : <http://e/>\n"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _data(update: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.update(PRE + "INSERT DATA { " + update + " }")
    return g


def test_stratifier_unifies_repeated_variables():
    # the head `:x :ok :y` can never match the body pattern `?s :bad ?s`'s dependency on `?s :ok ?s`
    rs = srl.parse_ruleset(
        PRE + "RULE { :x :ok :y } WHERE { ?s :q ?o NOT { ?s :bad ?s } }\nRULE { ?s :bad ?s } WHERE { ?s :ok ?s }\n"
    )
    list(rs.infer(_data(":a :q :b")))


def test_stratifier_keeps_a_real_dependency_with_repeated_variables():
    rs = srl.parse_ruleset(
        PRE + "RULE { ?x :ok ?x } WHERE { ?x :q ?o NOT { ?x :bad ?x } }\nRULE { ?s :bad ?s } WHERE { ?s :ok ?s }\n"
    )
    with pytest.raises(srl.SRLError):
        list(rs.infer(_data(":a :q :b")))
