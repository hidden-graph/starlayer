"""starlayer.graph.interop: the RDF 1.2 Interoperability "basic encoding" over pyoxigraph terms."""

from __future__ import annotations

import warnings

import pyoxigraph as ox
import pytest
from starlayer.graph.interop import (
    decode_directions,
    encode_directions,
    from_basic,
    to_basic,
)

DG = ox.DefaultGraph()
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
TYPE = ox.NamedNode(RDF + "type")
SUBJ = ox.NamedNode(RDF + "propositionFormSubject")
PRED = ox.NamedNode(RDF + "propositionFormPredicate")
OBJ = ox.NamedNode(RDF + "propositionFormObject")
B = ox.BlankNode


def q(s, p, o, g=DG):
    return ox.Quad(s, p, o, g)


def tt(s, p, o):
    return ox.Triple(s, p, o)










class TestAgainstTheOldEncoding:
    """The old graph classes hold triple terms as content-hash IRIs under tt: with the same vocabulary. Same
    structure, different node naming (IRI versus blank node). The old module has no to_basic()/from_basic()
    functions; its raw triples (rdflib.Graph.triples on a StarLayerGraph) are the encoding."""

    @staticmethod
    def _old_raw(turtle):
        import rdflib
        from starlayer.graph import StarLayerGraph

        g = StarLayerGraph()
        g.parse(data=turtle, format="turtle12")
        conv = {rdflib.URIRef: lambda t: ox.NamedNode(str(t)), rdflib.BNode: lambda t: ox.BlankNode(str(t))}

        def term(t):
            if isinstance(t, rdflib.Literal):
                return ox.Literal(str(t), datatype=ox.NamedNode(str(t.datatype))) if t.datatype else ox.Literal(str(t), language=t.language)
            return conv[type(t)](t)

        return [ox.Quad(term(s), term(p), term(o), DG) for s, p, o in rdflib.Graph.triples(g, (None, None, None))]

    CASES = [
        "<http://e/a> <http://e/p> <<( <http://e/s> <http://e/q> <http://e/o> )>> .",
        "<http://e/a> <http://e/p> <<( _:x <http://e/q> <<( <http://e/s> <http://e/p> \"v\"@en--ltr )>> )>> . _:x <http://e/n> 1 .",
        "<http://e/a> <http://e/p> <<( <http://e/s> <http://e/q> <http://e/o> )>> . <http://e/b> <http://e/r> <<( <http://e/s> <http://e/q> <http://e/o> )>> .",
    ]

    @pytest.mark.parametrize("turtle", CASES)
    def test_same_structure_different_node_names(self, turtle):
        from starlayer.graph.rdfc_native import isomorphic

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            old = self._old_raw(turtle)
        assert any(x.subject.value.startswith("https://github.com/hidden-graph/starlayergraph/ns/tt#") for x in old if isinstance(x.subject, ox.NamedNode))
        original = list(ox.parse(turtle.encode(), format=ox.RdfFormat.TURTLE, rename_blank_nodes=False))
        original = [q(x.subject, x.predicate, x.object) for x in original]
        mine = encode_directions(to_basic(original))
        # same dataset up to blank-node naming once the old IRI nodes are read as blank nodes
        old_as_bnodes = _iri_forms_to_bnodes(old)
        assert isomorphic(old_as_bnodes, mine)
        # and the old encoding decodes with the new from_basic
        assert set(decode_directions(from_basic(old, accept_iri_nodes=True))) == set(original) or isomorphic(
            decode_directions(from_basic(old, accept_iri_nodes=True)), original)


def _iri_forms_to_bnodes(quads):
    ns = "https://github.com/hidden-graph/starlayergraph/ns/tt#"

    def f(t):
        return ox.BlankNode("T" + t.value[len(ns):]) if isinstance(t, ox.NamedNode) and t.value.startswith(ns) else t

    return [ox.Quad(f(x.subject), x.predicate, f(x.object), x.graph_name) for x in quads]


