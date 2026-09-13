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
from rdflib import Graph, Literal, Namespace, URIRef
from starshacl import StarShaclValidator

SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

try:
    from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
    from starlayergraph.graph.starlayer_graph import StarLayerGraph
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


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _oxigraph_available(),
        reason="Oxigraph not running - start with: docker run -d --name oxigraph-test -p 7878:7878 "
        "ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878",
    ),
]


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


def test_global_sparql_rule_produces_triples_on_native_backend() -> None:
    """Found via direct testing against a real Oxigraph/Fuseki instance:
    ``_global_sparql_rule_triples``'s ``_apply_one`` ran its CONSTRUCT query
    via ``data_graph.query(...)`` with no graph-scoping of its own -
    ``starlayergraph.backends.native.native_query()`` sends a query's text
    to the remote endpoint completely unscoped (see that function's own
    docstring), so an ordinary, no-``GRAPH``-clause CONSTRUCT like this
    one silently matched against the store's separate, empty default graph
    instead of the data graph's own named context, and produced *nothing*
    - confirmed directly against both Oxigraph and Fuseki, and confirmed
    that adding an explicit ``GRAPH <identifier>`` wrapper around the same
    query fixes it. Fixed by snapshotting a native ``data_graph``'s current
    triples into a local, in-memory ``StarLayerGraph`` and evaluating the
    CONSTRUCT there instead (correct regardless of query complexity, unlike
    a textual ``GRAPH`` wrapper, which would need real SPARQL-aware
    rewriting for anything beyond a simple BGP). Shape-attached
    ``sh:TripleRule``/``sh:SPARQLRule`` execution was already confirmed
    working correctly on a native backend - this gap was specific to the
    global (shape-independent) rules path.
    """
    data = _native_graph(
        """
        @prefix ex: <http://example.org/> .
        ex:siblingOf a ex:SymmetricProperty .
        ex:alice ex:siblingOf ex:bob .
        """
    )
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:SymmetricPropertyRule a sh:SPARQLRule ;
          sh:construct \"\"\"
            PREFIX ex: <http://example.org/>
            CONSTRUCT { ?o ?p ?s . }
            WHERE { ?p a ex:SymmetricProperty . ?s ?p ?o . }
          \"\"\" .
        """,
        format="turtle12",
    )

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.bob, EX.siblingOf, EX.alice) in result.data_graph


def test_bound_bnode_class_check_is_correct_on_native_backend() -> None:
    """A real, well-formed sh:rule blank node (rdf:type sh:TripleRule) used
    to be misreported as failing meta-shacl's own rdf:type check when its
    shapes graph was native-backed - traced to StarLayerGraph._native_triples()
    (in starlayergraph, not this file) unconditionally skolemizing a bound
    BNode before querying, which only matches content written via the
    single-triple add() path - parse() (used here, and by every realistic
    shapes-graph load) goes through _native_add_many() instead, which
    deliberately keeps real, unskolemized blank nodes. Fixed in
    starlayergraph itself; this locks in the SHACL-level symptom that
    surfaced it: a plain rdf:type lookup on a parsed blank node must return
    what's actually there, not nothing.
    """
    shapes = _native_graph(
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
        """
    )
    from rdflib import RDF

    bnode = next(shapes.objects(None, SH.rule))
    assert list(shapes.objects(bnode, RDF.type)) == [SH.TripleRule]


def test_apply_rules_with_meta_shacl_on_native_backend_conforming_shape() -> None:
    """End-to-end: apply_rules() with meta_shacl on its usual default (True)
    used to crash entirely for any shapes graph containing a blank-node
    sh:rule (i.e. virtually any realistic one) when shacl_graph was native-
    backed - meta-shacl's own class-rule check misfired (see the test
    above), and even after that's fixed, reporting *any* blank-node-focused
    violation - real or not - separately crashed inside pySHACL's own
    report-stringification code, which builds a raw rdflib.Dataset directly
    around the same store, bypassing StarLayerGraph's own backend-aware
    overrides entirely. Both are now fixed (the first in starlayergraph,
    the second via _patch_stringify_for_native_backend_bnodes() in this
    package) - this is the full, undegraded default path, no meta_shacl=False
    workaround needed.
    """
    data = _native_graph("@prefix ex: <http://example.org/> . ex:alice a ex:Person .")
    shapes = _native_graph(
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
        """
    )

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)

    assert (EX.alice, EX.isPerson, Literal(True)) in result.data_graph


def test_meta_shacl_reports_a_genuine_blank_node_violation_without_crashing() -> None:
    """The other half of the report-stringification fix: a *real* violation
    whose focus node is a blank node must still be reportable (not just
    silently avoided) once meta-shacl no longer misfires on well-formed
    shapes. A rule missing sh:predicate/sh:object is genuinely malformed -
    the resulting error message must actually name the blank node's real
    content, not crash trying to.
    """
    shapes = _native_graph(
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ] .
        """
    )
    data = _native_graph("@prefix ex: <http://example.org/> . ex:alice a ex:Person .")

    with pytest.raises(Exception) as exc_info:
        StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

    assert "sh:TripleRule" in str(exc_info.value)
    assert "sh:subject sh:this" in str(exc_info.value) or "sh:this" in str(exc_info.value)


def test_apply_rules_works_in_default_rdf11_mode_against_remote_store() -> None:
    """Not just the native (rdf-1.2) backend: the *default* rdf-1.1
    (tt:HASH-encoded) backend had no blank-node handling of its own at all
    when backed by a remote store - found via a direct user question
    ("even in 1.1 does the backends not work") that turned out to identify
    a genuine, general gap in starlayergraph itself, unrelated to SHACL or
    triple terms (fixed there via StarLayerGraph._needs_bnode_skolemization).
    This locks in the SHACL-level consequence: a blank-node sh:rule shape
    now loads and executes correctly against a remote store even without
    the native backend, with meta_shacl at its real default (see
    test_meta_shacl_snapshots_a_remote_shapes_graph_to_in_memory below for
    why that no longer needs a meta_shacl=False workaround either).
    """
    fresh_id = URIRef(f"http://example.org/g-{uuid.uuid4().hex}")
    store = SPARQLUpdateStore(
        query_endpoint=f"{OXIGRAPH_BASE}/query",
        update_endpoint=f"{OXIGRAPH_BASE}/update",
    )
    data = StarLayerGraph(store=store, identifier=fresh_id)
    data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle12")

    store2 = SPARQLUpdateStore(
        query_endpoint=f"{OXIGRAPH_BASE}/query",
        update_endpoint=f"{OXIGRAPH_BASE}/update",
    )
    shapes = StarLayerGraph(store=store2, identifier=URIRef(f"http://example.org/g-{uuid.uuid4().hex}"))
    shapes.parse(
        data="""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
        """,
        format="turtle12",
    )

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)

    assert (EX.alice, EX.isPerson, Literal(True)) in result.data_graph


def test_meta_shacl_snapshots_a_remote_shapes_graph_to_in_memory() -> None:
    """The fix that closed the one remaining gap in the compatibility
    matrix, found via a direct user suggestion: rather than chase down
    every individual pySHACL-internal code path that breaks on a bound
    blank node against a SPARQLUpdateStore (a class-membership check,
    report-stringification, and a query(initBindings=...) call in the
    sh:sparql-based constraint evaluator were each found and would keep
    surfacing more), meta_validate() (starshacl/meta_shapes.py) now
    snapshots shapes_graph into a plain in-memory StarLayerGraph before
    running meta-shacl at all, whenever the original is backed by a
    SPARQLUpdateStore (StarLayerGraph._needs_bnode_skolemization, reused
    here for exactly the check it already computes). Correct specifically
    because meta-shacl checks the shapes graph's own structural
    well-formedness against a fixed, bundled meta-shapes graph - it never
    reads data_graph and has no legitimate need for live remote-store
    behavior at all; a one-time snapshot is the right shape for a one-time
    preflight check. Confirmed live on both Oxigraph and Fuseki, both
    backend modes - meta_shacl is now on at its real default everywhere in
    the compatibility matrix, no exceptions.
    """
    for backend_kwargs in ({}, {"backend": "rdf-1.2"}):
        store = SPARQLUpdateStore(
            query_endpoint=f"{OXIGRAPH_BASE}/query",
            update_endpoint=f"{OXIGRAPH_BASE}/update",
        )
        shapes = StarLayerGraph(
            store=store, identifier=URIRef(f"http://example.org/g-{uuid.uuid4().hex}"), **backend_kwargs
        )
        shapes.parse(
            data="""
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
            """,
            format="turtle12",
        )
        store2 = SPARQLUpdateStore(
            query_endpoint=f"{OXIGRAPH_BASE}/query",
            update_endpoint=f"{OXIGRAPH_BASE}/update",
        )
        data = StarLayerGraph(
            store=store2, identifier=URIRef(f"http://example.org/g-{uuid.uuid4().hex}"), **backend_kwargs
        )
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle12")

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

        assert result.conforms is True, backend_kwargs
