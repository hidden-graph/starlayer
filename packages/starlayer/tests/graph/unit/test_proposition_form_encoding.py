"""The internal triple-term encoding uses the RDF 1.2 Interoperability
vocabulary: each triple term is a node typed ``rdf:PropositionForm`` with
``rdf:propositionFormSubject/Predicate/Object``. Only the node's name differs
from the spec's "basic encoding" (a stable content hash instead of a fresh blank
node), and ``serialize()``/``parse()`` of plain RDF formats convert between the
two."""

from rdflib import BNode, Graph, Namespace
from rdflib.compare import isomorphic
from rdflib.namespace import RDF
from starlayer.graph import StarLayerGraph
from starlayer.graph.model.encoding import (
    TT_CLASS,
    TT_NS,
    TT_OBJECT,
    TT_PREDICATE,
    TT_SUBJECT,
)

EX = Namespace("http://ex/")
RAW = Graph.triples  # the store as it is, with nothing hidden


def _raw(g):
    return list(RAW(g, (None, None, None)))


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data="PREFIX ex: <http://ex/>\n" + ttl, format="turtle12")
    return g


class TestStoredShape:
    def test_a_triple_term_is_typed_and_described_with_the_spec_vocabulary(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "v" .')
        nodes = {s for s, p, o in _raw(g) if p == RDF.type and o == TT_CLASS}
        assert len(nodes) == 1
        (node,) = nodes
        assert str(node).startswith(TT_NS)
        assert set(g.objects(node, TT_SUBJECT)) == set()  # hidden from reads...
        assert set(RAW(g, (node, TT_SUBJECT, None))) == {(node, TT_SUBJECT, EX.s)}
        assert set(RAW(g, (node, TT_PREDICATE, None))) == {(node, TT_PREDICATE, EX.p)}
        assert set(RAW(g, (node, TT_OBJECT, None))) == {(node, TT_OBJECT, EX.o)}

    def test_the_classic_reification_predicates_are_not_used(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "v" .')
        preds = {p for _s, p, _o in _raw(g)}
        assert not preds & {RDF.subject, RDF.predicate, RDF.object}

    def test_the_same_triple_term_is_described_once(self):
        g = _graph("ex:alice ex:believes <<( ex:c ex:age 30 )>> .\nex:josh ex:believes <<( ex:c ex:age 30 )>> .")
        assert len([1 for _s, p, o in _raw(g) if p == RDF.type and o == TT_CLASS]) == 1
        assert len(_raw(g)) == 2 + 4

    def test_a_nested_triple_term_has_its_own_typed_node(self):
        g = _graph("ex:alice ex:believes <<( ex:bob ex:said <<( ex:c ex:age 30 )>> )>> .")
        assert len([1 for _s, p, o in _raw(g) if p == RDF.type and o == TT_CLASS]) == 2

    def test_a_sparql_insert_writes_the_type_triple_too(self):
        g = StarLayerGraph()
        g.update("PREFIX ex: <http://ex/> INSERT DATA { ex:a ex:believes <<( ex:c ex:age 30 )>> }")
        assert len([1 for _s, p, o in _raw(g) if p == RDF.type and o == TT_CLASS]) == 1
        assert len(list(g.triple_terms())) == 1


class TestHiddenFromReaders:
    def test_encoding_triples_are_not_visible(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "v" .')
        assert len(g) == 2  # rdf:reifies and ex:q
        preds = {p for _s, p, _o in g.triples((None, None, None))}
        assert not preds & {TT_SUBJECT, TT_PREDICATE, TT_OBJECT}
        assert not list(g.triples((None, RDF.type, TT_CLASS)))

    def test_a_select_over_everything_does_not_return_them(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "v" .')
        rows = list(g.query("SELECT * WHERE { ?s ?p ?o }"))
        assert len(rows) == 2

    def test_other_rdf_type_triples_stay_visible(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "v" .\nex:x a ex:Thing .')
        assert (EX.x, RDF.type, EX.Thing) in g

    def test_genuine_classic_reification_is_not_mistaken_for_the_encoding(self):
        g = StarLayerGraph()
        g.add((EX.st, RDF.type, RDF.Statement))
        g.add((EX.st, RDF.subject, EX.a))
        g.add((EX.st, RDF.predicate, EX.b))
        g.add((EX.st, RDF.object, EX.c))
        assert (EX.st, RDF.subject, EX.a) in g
        assert len(g) == 4


class TestRetrieval:
    def test_triple_terms_are_found_by_type_when_the_registry_is_rebuilt(self):
        g = _graph("ex:alice ex:believes <<( ex:c ex:age 30 )>> .")
        other = StarLayerGraph(store=g.store, identifier=g.identifier)
        assert list(other.triple_terms()) == []  # a new wrapper starts with an empty registry
        other._build_registry_from_store()
        assert len(list(other.triple_terms())) == 1


class TestBasicEncodingExchange:
    BASIC = """@prefix ex: <http://ex/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
_:r1 rdf:reifies _:gen1 . _:r1 ex:q "some value" .
_:gen1 a rdf:PropositionForm ;
  rdf:propositionFormSubject ex:s ; rdf:propositionFormPredicate ex:p ; rdf:propositionFormObject ex:o .
"""

    def test_serialize_to_a_plain_format_is_the_spec_basic_encoding(self):
        g = _graph('<< ex:s ex:p ex:o >> ex:q "some value" .')
        plain = Graph().parse(data=g.serialize(format="turtle"), format="turtle")
        assert isomorphic(plain, Graph().parse(data=self.BASIC, format="turtle"))

    def test_parse_of_the_basic_encoding_gives_real_triple_terms(self):
        g = StarLayerGraph()
        g.parse(data=self.BASIC, format="turtle")
        (tt,) = list(g.triple_terms())
        assert (tt.subject, tt.predicate, tt.object) == (EX.s, EX.p, EX.o)
        assert len(g) == 2

    def test_a_nested_encoding_round_trips(self):
        g = _graph("ex:alice ex:believes <<( ex:bob ex:said <<( ex:c ex:age 30 )>> )>> .")
        back = StarLayerGraph()
        back.parse(data=g.serialize(format="turtle"), format="turtle")
        assert g.isomorphic(back)
        assert len(list(back.triple_terms())) == 2

    def test_a_node_missing_a_property_is_left_alone(self):
        g = StarLayerGraph()
        g.parse(
            data="@prefix ex: <http://ex/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> ."
            "_:g a rdf:PropositionForm ; rdf:propositionFormSubject ex:s ; rdf:propositionFormPredicate ex:p .",
            format="turtle",
        )
        assert list(g.triple_terms()) == []
        assert any(isinstance(s, BNode) for s, _p, _o in _raw(g))
