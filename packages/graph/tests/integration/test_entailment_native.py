"""
tests/integration/test_entailment_native.py

Integration tests for StarLayerGraph.query(..., entailment="native") against
a real, reasoning-enabled Apache Jena Fuseki dataset. See
docs/fuseki-reasoning-setup.md for exactly how to stand up the dataset these
tests expect - confirmed live against that exact setup on 2026-09-20.

Self-skips unless a dataset named "starlayergraph-rdfs" is reachable at the
standard Fuseki base used elsewhere in this test suite (see
test_fuseki_backend.py) - this is deliberately a *separate* dataset from the
plain one that file already tests against, since it needs to be started
with `--rdfs=FILE` (or an assembler config), not the plain `--mem` setup:

    docker run -d --name fuseki-rdfs-test -p 3031:3030 \\
        -v /path/to/schema.ttl:/fuseki/schema.ttl:ro \\
        atomgraph/fuseki:6.1.0 --mem --rdfs=/fuseki/schema.ttl --update /starlayergraph-rdfs

with schema.ttl containing:

    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Manager rdfs:subClassOf ex:Employee .
    ex:worksAt rdfs:domain ex:Person .

Run:
    .venv/bin/pytest tests/integration/test_entailment_native.py -v
"""

import pytest
import requests
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph import RDF, Namespace, StarLayerGraph

pytestmark = pytest.mark.integration

FUSEKI_HOST = "http://localhost:3031"
DATASET = f"{FUSEKI_HOST}/starlayergraph-rdfs"
EX = Namespace("http://example.org/")


def _rdfs_fuseki_available() -> bool:
    try:
        r = requests.get(f"{FUSEKI_HOST}/$/ping", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


rdfs_fuseki = pytest.mark.skipif(
    not _rdfs_fuseki_available(),
    reason="No reasoning-enabled Fuseki dataset at localhost:3031 - see "
           "docs/fuseki-reasoning-setup.md and this file's own module docstring "
           "for how to start one.",
)


def _graph() -> StarLayerGraph:
    store = SPARQLUpdateStore(
        query_endpoint=f"{DATASET}/query", update_endpoint=f"{DATASET}/update"
    )
    # identifier=DATASET_DEFAULT_GRAPH_ID: g.update()'s raw-text INSERT DATA
    # calls below have no GRAPH clause, so they write to the endpoint's own
    # unnamed default graph - and _native_scoped() (which triples()/infer()
    # use, unlike query()/update()'s pure pass-through) only leaves reads
    # unscoped for this exact identifier value, wrapping any other value in
    # GRAPH <self.identifier> { ... } instead. Without this, iterating this
    # graph directly (list(g), or anything infer()/entailment="owl-rl" does
    # internally) would silently see nothing, even though g.query() finds
    # the data fine (confirmed live: a default, randomly-assigned identifier
    # reproduces exactly this mismatch).
    g = StarLayerGraph(store=store, backend="rdf-1.2", identifier=DATASET_DEFAULT_GRAPH_ID)
    g.update("CLEAR ALL")
    g.bind("ex", EX)
    return g


@rdfs_fuseki
class TestEntailmentNative:
    def test_subclass_entailment_via_fuseki_rdfs_flag(self):
        g = _graph()
        g.update("PREFIX ex: <http://example.org/> INSERT DATA { ex:alice a ex:Manager }")
        rows = list(g.query(
            "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }",
            entailment="native",
        ))
        assert [str(r[0]) for r in rows] == [str(EX.alice)]

    def test_domain_entailment_via_fuseki_rdfs_flag(self):
        g = _graph()
        g.update("PREFIX ex: <http://example.org/> INSERT DATA { ex:alice ex:worksAt ex:Acme }")
        rows = list(g.query(
            "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }",
            entailment="native",
        ))
        assert [str(r[0]) for r in rows] == [str(EX.alice)]

    def test_plain_query_without_entailment_still_works(self):
        # entailment="native" changes nothing about how the query text is
        # sent - the endpoint reasons regardless of which value (or none)
        # is passed, confirming this really is a no-op label, not new
        # client-side behavior.
        g = _graph()
        g.update("PREFIX ex: <http://example.org/> INSERT DATA { ex:alice a ex:Manager }")
        rows = list(g.query(
            "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }"
        ))
        assert [str(r[0]) for r in rows] == [str(EX.alice)]

    def test_owl_rl_delta_does_not_duplicate_what_the_backend_already_entails(self):
        # Phase D: entailment="owl-rl" against a native (backend="rdf-1.2")
        # graph reads self live via _decompose()/_native_triples() before
        # running owlrl - so anything this reasoning-enabled Fuseki dataset
        # already entails (confirmed below via a plain query, no
        # entailment= needed) is already present in that read, and owlrl's
        # own delta over it correctly doesn't re-derive it. Direct
        # demonstration of "we don't care whether the backend already
        # reasons - the impact is just a smaller delta", not simulated.
        g = _graph()
        g.update("PREFIX ex: <http://example.org/> INSERT DATA { ex:alice a ex:Manager }")

        plain = list(g.query(
            "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }"
        ))
        assert [str(r[0]) for r in plain] == [str(EX.alice)], (
            "expected the backend's own --rdfs= reasoning to already answer this "
            "without entailment= - if this fails, the rest of this test can't "
            "demonstrate anything about delta size"
        )

        rows = list(g.query(
            "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }",
            entailment="owl-rl",
        ))
        assert [str(r[0]) for r in rows] == [str(EX.alice)]
        delta = g._owl_rl_cache[0]
        assert (EX.alice, RDF.type, EX.Employee) not in delta
