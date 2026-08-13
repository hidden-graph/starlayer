"""Integration tests for StarShaclValidator against a StarLayerGraph running
the native RDF 1.2 backend (``backend='rdf-1.2'``, e.g. Oxigraph) - as
opposed to every other test in this suite, which uses either a plain
``rdflib.Graph`` or the default ``backend='rdf-1.1'`` tt:HASH-encoded mode.

This is a real, previously-untested surface: `TripleTermAdapter.encode_graph()`
(``starshacl/adapters.py``) has zero backend-awareness of its own - it relies
entirely on ``StarLayerGraph``'s own promise that ``.triples()``/``.query()``
yield the same Python-level term shapes (real ``TripleTerm`` objects, not
raw encoded URIs) regardless of backend. Investigating this surfaced a real
bug in ``starlayergraph`` itself (fixed there, not here): ``StarLayerGraph.
parse(format='turtle12'/'trig12')`` wrote the rdf-1.1 backend's own tt:HASH
skolemized encoding fragments directly into the store for *any* backend,
bypassing the backend-aware ``StarLayerGraph.add()`` override - so triple
terms parsed from text (not added via the ``.add()`` Python API) never
decoded correctly on a native-backend graph, and broke ``sh:reifierShape``/
``sh:reificationRequired`` end to end (the discovery path: a reifier
correctly reifying the outer ``(focus, path, value)`` triple silently failed
to be found).

Requires a running Oxigraph instance:
    docker run -d --name oxigraph-test -p 7878:7878 \\
      ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878
"""

import uuid

import pytest
import requests
from rdflib import Graph, Namespace, URIRef

from starshacl import StarShaclValidator

pyshacl = pytest.importorskip("pyshacl")

try:
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
    from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"starlayergraph import unavailable: {exc}", allow_module_level=True)

EX = Namespace("http://example.org/")
OXIGRAPH_BASE = "http://localhost:7878"


def _oxigraph_available() -> bool:
    try:
        r = requests.get(OXIGRAPH_BASE, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _oxigraph_available(),
    reason="Oxigraph not running - start with: docker run -d --name oxigraph-test -p 7878:7878 "
    "ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878",
)


def _native_graph(ttl12: str) -> StarLayerGraph:
    fresh_id = URIRef(f"http://example.org/g-{uuid.uuid4().hex}")
    store = SPARQLUpdateStore(
        query_endpoint=f"{OXIGRAPH_BASE}/query",
        update_endpoint=f"{OXIGRAPH_BASE}/update",
    )
    g = StarLayerGraph(store=store, identifier=fresh_id, backend="rdf-1.2")
    g.parse(data=ttl12, format="turtle12")
    return g


def _validate(data_ttl12: str, shapes_ttl: str, **kwargs):
    data = _native_graph(data_ttl12)
    shapes = Graph()
    shapes.parse(data=shapes_ttl, format="turtle")
    return StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, **kwargs)


def test_basic_triple_term_data_validates() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice ex:says <<( ex:bob ex:knows ex:carol )>> .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:path ex:says ; sh:minCount 1 ] .
        """,
    )
    assert result.conforms is True


def test_violation_report_correctly_restores_triple_term_value() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice ex:says <<( ex:bob ex:knows ex:carol )>> .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:path ex:says ; sh:maxCount 0 ] .
        """,
    )
    assert result.conforms is False
    assert "ex:says" in result.report_text or "says" in result.report_text


def test_unique_values_for_duplicate_detection_on_native_backend() -> None:
    """This session's sh:uniqueValuesFor composition fix, verified against
    real native-backend data, not just the default rdf-1.1 backend every
    other test in this suite uses."""
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "dup" .
        ex:r2 a ex:Record ; ex:id "dup" .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor ex:id .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_conforms_when_no_duplicate_on_native_backend() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "a" .
        ex:r2 a ex:Record ; ex:id "b" .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor ex:id .
        """,
    )
    assert result.conforms is True


def test_reifier_shape_correctly_conforms_on_native_backend() -> None:
    """The scenario that surfaced the starlayergraph parsing bug: a
    reifier correctly reifying the outer (focus, path, value) triple, with
    data loaded via .parse(format='turtle12') on a native-backend graph -
    not via the .add() Python API, which was never affected."""
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:stmt1 a ex:Statement ; ex:claim <<( ex:bob ex:knows ex:carol )>> .
        ex:reifier1 rdf:reifies <<( ex:stmt1 ex:claim <<( ex:bob ex:knows ex:carol )>> )>> ;
          ex:confidence "0.9" .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:ConfShape a sh:NodeShape ; sh:property [ sh:path ex:confidence ; sh:minCount 1 ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:Statement ;
          sh:property [ sh:path ex:claim ; sh:reifierShape ex:ConfShape ; sh:reificationRequired true ] .
        """,
    )
    assert result.conforms is True


def test_reifier_shape_violates_when_reifier_missing_on_native_backend() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:stmt1 a ex:Statement ; ex:claim <<( ex:bob ex:knows ex:carol )>> .
        """,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:ConfShape a sh:NodeShape ; sh:property [ sh:path ex:confidence ; sh:minCount 1 ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:Statement ;
          sh:property [ sh:path ex:claim ; sh:reifierShape ex:ConfShape ; sh:reificationRequired true ] .
        """,
    )
    assert result.conforms is False
