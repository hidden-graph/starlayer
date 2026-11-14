"""``starlayer.graph`` re-exports pyoxigraph's term classes: the same objects, so a term built either way is one term."""

import pyoxigraph as ox
import starlayer.graph as graph
from starlayer.graph import (
    BaseDirection,
    BlankNode,
    Literal,
    NamedNode,
    StarLayerGraph,
    Triple,
)


def test_the_term_classes_are_pyoxigraphs_own():
    assert (NamedNode, BlankNode, Literal, Triple, BaseDirection) == (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple, ox.BaseDirection)
    assert {"NamedNode", "BlankNode", "Literal", "Triple", "BaseDirection"} <= set(graph.__all__)


def test_a_term_built_from_the_export_is_the_term_the_graph_holds():
    g = StarLayerGraph()
    g.add((NamedNode("urn:a"), NamedNode("urn:p"), Literal("x", language="ar", direction=BaseDirection.RTL)))
    g.add((BlankNode("b"), NamedNode("urn:q"), Triple(NamedNode("urn:s"), NamedNode("urn:p"), NamedNode("urn:o"))))
    assert (ox.NamedNode("urn:a"), ox.NamedNode("urn:p"), ox.Literal("x", language="ar", direction=ox.BaseDirection.RTL)) in g
    assert len(g) == 2
