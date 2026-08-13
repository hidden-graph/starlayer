"""Phase 4: Prologue (BASE/PREFIX) round-trip.

Not cosmetic: confirmed empirically that a reconstructed Query with an
empty Prologue silently gives a *wrong* result for BASE-relative IRI()/
URI() builtin resolution (Builtin_IRI calls ctx.prologue.absolutize()) —
real evaluation-time behavior, not just prettier regenerated text. Also
confirmed rdflib's own algebra.translateAlgebra never reads query.prologue
at all (byte-identical output regardless of prologue content), so this
phase can't and doesn't attempt to make regenerated query text use
prefixed names — see vocab.py's "Prologue (BASE/PREFIX)" section.
"""

from rdflib import Graph
from rdflib.plugins.sparql.algebra import translateAlgebra
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery
from rdflib.plugins.sparql.update import evalUpdate

from starsparql import query_to_rdf, rdf_to_query, rdf_to_update, update_to_rdf


def test_base_relative_iri_resolution_survives_roundtrip():
    g = Graph()
    g.parse(data='@prefix : <http://example.org/> . :s :p "foo" .', format="turtle")

    query_text = """
        BASE <http://example.org/base/>
        SELECT ?iri WHERE { ?s ?p ?lit . BIND(IRI(?lit) AS ?iri) }
    """
    prepared = prepareQuery(query_text)
    original = list(evalQuery(g, prepared)["bindings"])

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    roundtripped = list(evalQuery(g, reconstructed)["bindings"])

    assert original == roundtripped
    from rdflib import URIRef, Variable

    assert original[0][Variable("iri")] == URIRef("http://example.org/base/foo")


def test_prefix_bindings_survive_roundtrip():
    query_text = "PREFIX foaf: <http://xmlns.com/foaf/0.1/> SELECT ?name WHERE { ?p foaf:name ?name }"
    prepared = prepareQuery(query_text)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)

    namespaces = dict(reconstructed.prologue.namespace_manager.namespaces())
    assert str(namespaces["foaf"]) == "http://xmlns.com/foaf/0.1/"


def test_translate_algebra_output_unaffected_by_prologue():
    """Documents the rdflib limitation this phase works around rather than
    fixes: translateAlgebra's output is identical with or without a
    populated prologue, so this phase can't make regenerated text use
    prefixed names."""
    query_text = "PREFIX foaf: <http://xmlns.com/foaf/0.1/> SELECT ?name WHERE { ?p foaf:name ?name }"
    prepared = prepareQuery(query_text)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)

    assert translateAlgebra(prepared) == translateAlgebra(reconstructed)
    assert "foaf:" not in translateAlgebra(reconstructed)


def test_update_base_relative_iri_resolution_survives_roundtrip():
    g_original = Graph()
    g_original.parse(data='@prefix : <http://example.org/> . :s :p "foo" .', format="turtle")
    g_roundtripped = Graph()
    g_roundtripped.parse(data='@prefix : <http://example.org/> . :s :p "foo" .', format="turtle")

    update_text = """
        PREFIX : <http://example.org/>
        BASE <http://example.org/base/>
        INSERT { ?s :resolved ?iri }
        WHERE { ?s :p ?lit . BIND(IRI(?lit) AS ?iri) }
    """
    from rdflib.plugins.sparql.processor import prepareUpdate

    evalUpdate(g_original, prepareUpdate(update_text))

    graph, root = update_to_rdf(prepareUpdate(update_text))
    reconstructed = rdf_to_update(graph, root)
    evalUpdate(g_roundtripped, reconstructed)

    assert set(g_original) == set(g_roundtripped)
