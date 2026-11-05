"""CONSTRUCT leaves out a template triple that instantiates to invalid RDF (SPARQL 1.1 sec 16.2.1)."""

import pyoxigraph as ox
from starlayer.graph.oxgraph import StarLayerGraph


class _Namespace:
    def __getattr__(self, name):
        return ox.NamedNode("http://x/" + name)


EX = _Namespace()


def Literal(value):  # noqa: N802
    return ox.Literal(str(value), datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))


def test_construct_drops_literal_subjects_and_non_iri_predicates():
    graph = StarLayerGraph()
    graph.add((EX.a, EX.num, Literal(1)))
    query = "PREFIX ex: <http://x/> CONSTRUCT { ?n ex:out ?n . ?s ex:ok ?n . ?s ?n ?s } WHERE { ?s ex:num ?n }"
    assert set(graph.query(query).graph) == {(EX.a, EX.ok, Literal(1))}
