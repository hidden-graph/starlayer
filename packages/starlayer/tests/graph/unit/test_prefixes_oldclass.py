"""test_prefixes: the identity of a reduced copy of an unnamed graph (a blank-node identifier in the old class; an
OxGraph's default graph has the one DefaultGraph identity), deleted with the old class at D1."""

from rdflib import Namespace as _Namespace
from starlayer.graph import StarLayerGraph

_EX = _Namespace("http://ex.org/")


def test_a_reduced_copy_of_an_unnamed_graph_is_not_given_a_shared_identity() -> None:
    g = StarLayerGraph()
    g.add((_EX.a, _EX.p, _EX.b))
    assert g.reduce_prefixes().identifier != g.identifier  # a blank-node identity means nothing; the copy gets its own
