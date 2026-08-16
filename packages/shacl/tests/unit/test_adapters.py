from rdflib import Literal, Namespace, URIRef
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl.adapters import (
    TripleTermAdapter,
    TripleTermGraph,
    TripleTermValue,
    _SparqlAwareEncodedGraph,
)

EX = Namespace("http://example.org/")


def test_round_trip_triple_term_value() -> None:
    data = TripleTermGraph()
    tt = TripleTermValue(EX.alice, EX.knows, EX.bob)
    data.add((EX.s, EX.p, tt))

    adapter = TripleTermAdapter()
    encoded = adapter.encode_graph(data)
    decoded = adapter.decode_graph(encoded)

    assert isinstance(decoded, StarLayerGraph)
    assert (EX.s, EX.p, (EX.alice, EX.knows, EX.bob)) in decoded


def test_round_trip_nested_triple_term_value() -> None:
    data = TripleTermGraph()
    inner = TripleTermValue(EX.alice, EX.knows, EX.bob)
    outer = TripleTermValue(EX.eve, EX.claims, inner)
    data.add((EX.statement, EX.hasValue, outer))

    adapter = TripleTermAdapter()
    encoded = adapter.encode_graph(data)
    decoded = adapter.decode_graph(encoded)

    assert isinstance(decoded, StarLayerGraph)
    assert (EX.statement, EX.hasValue, (EX.eve, EX.claims, (EX.alice, EX.knows, EX.bob))) in decoded


def test_round_trip_nested_triple_term_from_starlayergraph_tuple_shorthand() -> None:
    # StarLayerGraph treats a plain 3-tuple as inline triple-term shorthand in
    # any node position (including nested). Unlike test_round_trip_nested_triple_term_value
    # above (which builds fully pre-constructed TripleTermValue objects), this
    # exercises a nested component that surfaces as a raw tuple rather than an
    # already-coerced term_factory instance - previously crashed encode_graph().
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.stmt1, EX.about, (EX.bob, EX.knows, EX.carol))))

    adapter = TripleTermAdapter.for_starlayergraph()
    encoded = adapter.encode_graph(data)
    decoded = adapter.decode_graph(encoded)

    outer = next(o for _, _, o in decoded.triples((EX.alice, EX.says, None)))
    assert outer.subject == EX.stmt1
    assert outer.predicate == EX.about
    assert outer.object == adapter.term_factory(EX.bob, EX.knows, EX.carol)


def test_round_trip_dirlangstring_value() -> None:
    # StarLayerGraph yields a real DirLangString (not an rdflib term) for RDF
    # 1.2 direction-tagged literals - previously crashed encode_graph()
    # outright (AssertionError: "Object ... must be an rdflib term") for ANY
    # data graph containing one, regardless of whether a shape referenced it.
    from starlayergraph.model.dirlangstring import DirLangString

    data = StarLayerGraph()
    data.parse(
        data='@prefix ex: <http://example.org/> .\nex:Alice ex:greeting "مرحبا"@ar--rtl .',
        format="turtle12",
    )

    adapter = TripleTermAdapter.for_starlayergraph()
    encoded = adapter.encode_graph(data)
    assert len(encoded) == 1
    encoded_value = next(o for _, _, o in encoded.triples((EX.Alice, EX.greeting, None)))
    assert isinstance(encoded_value, Literal)  # flat, RDF-1.1-safe - no crash

    decoded = adapter.decode_graph(encoded)
    decoded_value = next(o for _, _, o in decoded.triples((EX.Alice, EX.greeting, None)))
    assert decoded_value == DirLangString("مرحبا", "ar", "rtl")


def test_non_triple_nodes_untouched() -> None:
    data = TripleTermGraph()
    data.add((EX.s, EX["count"], Literal(3)))

    adapter = TripleTermAdapter()
    encoded = adapter.encode_graph(data)
    decoded = adapter.decode_graph(encoded)

    assert (EX.s, EX["count"], Literal(3)) in decoded


def test_reuses_same_uri_for_same_term() -> None:
    adapter = TripleTermAdapter()
    tt = TripleTermValue(EX.a, EX.p, EX.o)

    left = adapter._encode_node(tt)
    right = adapter._encode_node(tt)

    assert isinstance(left, URIRef)
    assert left == right


def test_registry_export_import_round_trip() -> None:
    adapter_a = TripleTermAdapter()
    tt = TripleTermValue(EX.a, EX.p, EX.o)
    encoded = adapter_a.encode_term(tt)
    payload = adapter_a.export_registry()

    adapter_b = TripleTermAdapter()
    adapter_b.import_registry(payload)

    decoded = adapter_b.decode_term(encoded)
    assert decoded == tt


def test_registry_import_rejects_namespace_mismatch() -> None:
    adapter = TripleTermAdapter()
    payload = {
        "namespace": "urn:other:",
        "entries": [],
    }

    try:
        adapter.import_registry(payload)
    except ValueError as exc:
        assert "namespace mismatch" in str(exc)
    else:
        raise AssertionError("Expected namespace mismatch to raise ValueError")


def test_sparql_aware_graph_reuses_decode_across_queries_without_mutation() -> None:
    # A real, measured performance bottleneck: a sh:construct rule under
    # iterate_rules=True calls .query() once per (focus node, construct)
    # pair per iteration, all against the same unmutated graph snapshot -
    # decoding fresh on every single call (rather than once per iteration)
    # made rule-heavy workloads scale far worse than necessary. Confirms the
    # cache is actually reused (not just correct) when nothing has changed.
    adapter = TripleTermAdapter.for_starlayergraph()
    graph = adapter.encode_graph(StarLayerGraph())
    assert isinstance(graph, _SparqlAwareEncodedGraph)
    graph.add((EX.alice, EX.knows, EX.bob))

    decode_calls = 0
    original_decode_graph = adapter.decode_graph

    def counting_decode_graph(g):
        nonlocal decode_calls
        decode_calls += 1
        return original_decode_graph(g)

    adapter.decode_graph = counting_decode_graph

    graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")

    assert decode_calls == 1


def test_sparql_aware_graph_invalidates_decode_cache_on_mutation() -> None:
    adapter = TripleTermAdapter.for_starlayergraph()
    graph = adapter.encode_graph(StarLayerGraph())
    graph.add((EX.alice, EX.knows, EX.bob))

    result1 = graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    assert {str(row.s) for row in result1} == {str(EX.alice)}

    graph.add((EX.carol, EX.knows, EX.dave))

    result2 = graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    assert {str(row.s) for row in result2} == {str(EX.alice), str(EX.carol)}


def test_sparql_aware_graph_invalidates_decode_cache_on_remove() -> None:
    adapter = TripleTermAdapter.for_starlayergraph()
    graph = adapter.encode_graph(StarLayerGraph())
    graph.add((EX.alice, EX.knows, EX.bob))
    graph.add((EX.carol, EX.knows, EX.dave))

    result1 = graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    assert {str(row.s) for row in result1} == {str(EX.alice), str(EX.carol)}

    graph.remove((EX.carol, EX.knows, EX.dave))

    result2 = graph.query("SELECT ?s WHERE { ?s <http://example.org/knows> ?o }")
    assert {str(row.s) for row in result2} == {str(EX.alice)}
