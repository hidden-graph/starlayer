"""Phase 2e: SPARQL Update round-trip (INSERT/DELETE/Modify/graph ops).

Updates are a separate top-level algebra shape from queries
(rdflib.plugins.sparql.sparql.Update: a Prologue plus a List[CompValue] of
operations executed in order, not a single algebra tree) — see
to_rdf.update_to_rdf / from_rdf.rdf_to_update. The two features specific to
this phase: Update's "quads" field (a graph-term -> triples map, distinct
from a VALUES row despite both being raw Python dicts — see vocab.py's
"Update quads-by-graph maps" section) and several bare-keyword fields
(GraphRefAll's DEFAULT/NAMED/ALL, SILENT) that exercise the generic
bare-Python-str handling introduced alongside this phase (vocab.py's "Bare
Python strings" section).

Verified by applying both the original and round-tripped update to
independent copies of the same starting dataset and comparing the resulting
quads — not by comparing update text (this project doesn't attempt to
serialize Update algebra back to text at all; only Query algebra gets that
via rdflib's own translateAlgebra).
"""

import pytest
from rdflib import Dataset, Graph
from rdflib.plugins.sparql.processor import prepareUpdate
from rdflib.plugins.sparql.update import evalUpdate
from starsparql import rdf_to_update, update_to_rdf

PREFIXES = "PREFIX : <http://example.org/>\n"

FIXTURE_TTL = """
@prefix : <http://example.org/> .
:alice :name "Alice" ; :age 30 .
:bob :name "Bob" ; :age 25 .
"""

# Single-graph updates use a plain Graph — a Dataset's default context
# behaves as a quad store even for a graph-less INSERT/DELETE DATA, which
# rdflib's own evalInsertData doesn't handle (`g += u.triples` expects
# 4-tuples there); confirmed this is a stock-rdflib/Dataset interaction, not
# something this project's round-trip causes, by hitting it on the
# never-round-tripped original update too.
SINGLE_GRAPH_UPDATES = [
    PREFIXES + 'INSERT DATA { :carol :name "Carol" }',
    PREFIXES + "DELETE DATA { :bob :age 25 }",
    PREFIXES + "DELETE WHERE { :alice ?p ?o }",
    PREFIXES + "DELETE { ?p :age ?a } INSERT { ?p :age 99 } WHERE { ?p :age ?a }",
    PREFIXES + "CLEAR DEFAULT",
]

MULTI_GRAPH_UPDATES = [
    PREFIXES + "INSERT DATA { GRAPH :g1 { :x :y :z } }",
    PREFIXES + "INSERT DATA { GRAPH :g1 { :x :y :z } } ; DELETE DATA { GRAPH :g1 { :x :y :z } }",
    PREFIXES + "WITH :g1 DELETE { ?s ?p ?o } INSERT { ?s ?p :changed } WHERE { ?s ?p ?o }",
    PREFIXES + "INSERT DATA { GRAPH :g1 { :a :b :c } } ; DELETE WHERE { GRAPH :g1 { ?s ?p ?o } }",
    PREFIXES + "INSERT DATA { GRAPH :g1 { :a :b :c } } ; ADD :g1 TO :g2",
    PREFIXES + "INSERT DATA { GRAPH :g1 { :a :b :c } } ; CLEAR SILENT GRAPH :g1",
]


def _fresh_graph():
    g = Graph()
    g.parse(data=FIXTURE_TTL, format="turtle")
    return g


def _fresh_dataset():
    ds = Dataset()
    ds.parse(data=FIXTURE_TTL, format="turtle")
    return ds


@pytest.mark.parametrize("update_text", SINGLE_GRAPH_UPDATES)
def test_update_roundtrip_effect_equivalence_single_graph(update_text):
    g_original = _fresh_graph()
    evalUpdate(g_original, prepareUpdate(update_text))

    g_roundtripped = _fresh_graph()
    graph, root = update_to_rdf(prepareUpdate(update_text))
    reconstructed = rdf_to_update(graph, root)
    evalUpdate(g_roundtripped, reconstructed)

    assert set(g_original) == set(g_roundtripped)


@pytest.mark.parametrize("update_text", MULTI_GRAPH_UPDATES)
def test_update_roundtrip_effect_equivalence_multi_graph(update_text):
    ds_original = _fresh_dataset()
    evalUpdate(ds_original, prepareUpdate(update_text))

    ds_roundtripped = _fresh_dataset()
    graph, root = update_to_rdf(prepareUpdate(update_text))
    reconstructed = rdf_to_update(graph, root)
    evalUpdate(ds_roundtripped, reconstructed)

    assert set(ds_original.quads()) == set(ds_roundtripped.quads())
