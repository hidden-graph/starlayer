"""W3C SPARQL 1.2 test suite - execution correctness, run against
StarLayerGraph directly.

This is deliberately the "B vs A" check, not the "C vs A" check the
downstream starsparql project's own tests/test_w3c_sparql12.py does:
the *original* W3C query text is executed here exactly as published, with
zero involvement from starsparql's own SPARQL-1.2-to-algebra-to-text
translation pipeline. Any failure reported here is a real, standalone
starlayergraph/rdflib execution defect, independent of anything that project's
own translation might separately get right or wrong - a query that fails
here would still fail even if that project's translation pipeline were
perfect. See docs/rdflib-upstream-issues.md for confirmed rdflib bugs found
via this same test suite while building starsparql.

Two test shapes:
1. QueryEvaluationTest (SELECT-shaped, .srj expected results) - compare
   bindings, order/set-independent. `.srx`-only tests (no `.srj`) are
   skipped - this harness's JSON results parser has no XML counterpart.
2. QueryEvaluationTest (CONSTRUCT-shaped, .ttl expected results) - compare
   by graph isomorphism, after skolemizing any TripleTerm value to a
   stable URIRef first (see _skolemize_graph - rdflib.compare.to_isomorphic
   requires every term to be a real rdflib.term.Node, which
   starlayergraph.model.triple.TripleTerm deliberately isn't), AND mapping any
   anonymous-reifier rr:N URIRef (starlayergraph's own internal skolemization of
   an anonymous reifier - see starlayergraph/model/encoding.py's RR_NS) back to
   a fresh BNode first. The latter is necessary, not cosmetic: rr:N
   numbering is assignment-order-dependent (confirmed via construct-3 -
   actual and expected mint the same reifiers in different orders, so e.g.
   "rr#0" on one side is "rr#3" on the other for the structurally same
   reifier), and to_isomorphic's blank-node canonicalization - which is
   exactly the "up to consistent relabeling" comparison this needs - only
   applies to genuine BNodes, not arbitrary URIRefs regardless of
   namespace.

UpdateEvaluationTest is collected (via the shared index) but not exercised
here - this file is scoped to query evaluation.
"""

from __future__ import annotations

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.compare import to_isomorphic
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.namespace import RDF
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph.graph.starlayer_dataset import StarLayerDataset
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.encoding import RR_NS
from starlayergraph.model.triple import TripleTerm

from .harness import (
    bindings_match,
    clear_fuseki,
    clear_oxigraph,
    data_format,
    load_index,
    fuseki_available,
    oxigraph_available,
    FUSEKI_QUERY_URL,
    FUSEKI_UPDATE_URL,
    OXIGRAPH_QUERY_URL,
    OXIGRAPH_UPDATE_URL,
    parse_srj,
)

_DATASET_FORMATS = {"trig12", "nq12"}


def _new_graph(entry) -> StarLayerGraph | StarLayerDataset:
    """A fixture's data may define named graphs (TriG/N-Quads) - those need a
    real multi-graph Dataset, not a single StarLayerGraph (which raises "You
    performed a query operation requiring a dataset" the moment a query uses
    GRAPH against data that was never loaded into any graph at all, since a
    lone StarLayerGraph has no notion of a graph name other than its own).
    StarLayerDataset.query()/.parse() have the same shape as StarLayerGraph's
    own (confirmed by reading starlayer_dataset.py), so callers don't need to
    branch on which one they got back.
    """
    if entry.data_file and data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset()
    return StarLayerGraph()


def _new_oxigraph_graph(entry) -> StarLayerGraph | StarLayerDataset:
    """Same shape as _new_graph(), but backed by a live Oxigraph endpoint via
    the native rdf-1.2 backend instead of the in-memory default - no special
    loading path of its own, same .parse()/.query() calls either way.

    A plain (non-dataset) StarLayerGraph is given
    ``rdflib.graph.DATASET_DEFAULT_GRAPH_ID`` as its identifier rather than
    an arbitrary graph name: that sentinel is what tells the native
    backend's write/read paths (StarLayerGraph._native_scoped()) this graph
    stands for a dataset's own default graph, so its triples go to the
    endpoint's real (unnamed) default graph - the same place an unmodified
    query with no GRAPH clause looks by default. Anything else would need
    the query text itself changed to add a GRAPH wrapper, which defeats the
    point of this whole test file (running each W3C query exactly as
    published, see the module docstring).
    """
    store = SPARQLUpdateStore(query_endpoint=OXIGRAPH_QUERY_URL, update_endpoint=OXIGRAPH_UPDATE_URL)
    if entry.data_file and data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset(store=store, backend="rdf-1.2")
    return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")


def _new_fuseki_graph(entry) -> StarLayerGraph | StarLayerDataset:
    """Same as _new_oxigraph_graph(), against a live Fuseki endpoint instead
    - see that function's own docstring for why DATASET_DEFAULT_GRAPH_ID
    matters here."""
    store = SPARQLUpdateStore(query_endpoint=FUSEKI_QUERY_URL, update_endpoint=FUSEKI_UPDATE_URL)
    if entry.data_file and data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset(store=store, backend="rdf-1.2")
    return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")


ALL_ENTRIES = load_index()

EVAL_SELECT = [
    e
    for e in ALL_ENTRIES
    if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".srj")
]
EVAL_CONSTRUCT = [
    e
    for e in ALL_ENTRIES
    if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".ttl")
]

# Known, understood divergences between Oxigraph and the in-memory backend -
# not starlayergraph bugs, so not "fixed" here, but also not silently masked.
# Each is an xfail(strict=True): if Oxigraph's own behavior ever changes to
# match, the xfail flips to an unexpected pass (XPASS) and fails loudly
# rather than staying silently green. Same pattern already used by
# tests/integration/test_cross_backend_parity.py's numeric-lexical-form gap.
#
# order-1/order-2 (ORDER BY across a blank node/IRI/literal/triple-term) used
# to be here too - blank nodes had to be skolemized to a BN_NS URI to survive
# StarLayerGraph._native_add()'s one-HTTP-request-per-triple write path (see
# backends/native.py's skolemize_bnode()), which made Oxigraph's own engine
# treat them as URIs rather than blank nodes for ORDER BY's term-kind rule.
# Fixed 2026-08-04 by StarLayerGraph._native_add_many(): StarLayerGraph.parse()/
# addN() now batch every triple for one graph into a single SPARQL Update
# request, so real (unskolemized) blank-node syntax survives correctly - see
# its own docstring for why that's safe there specifically (every triple
# lands in the *same* request) but not for the single-triple add() path,
# which still skolemizes and still needs to (a blank node reused across
# separate add() calls, or across StarLayerDataset named-graph contexts,
# still only has request-scoped identity without it).
#
# op-2 used to be here too - Oxigraph didn't preserve the canonical
# xsd:decimal lexical form on round-trip ("123.0" came back as "123"), same
# underlying gap as test_cross_backend_parity.py's numeric-lexical-form
# case. Fixed 2026-08-05 the same way as that one: client-side
# canonicalization in starlayergraph/backends/native.py::_parse_json_term.
# Empty for now - kept (rather than removed) since this is a real, likely
# to recur, category of cross-engine divergence.
_OXIGRAPH_KNOWN_DIVERGENCES: dict = {}


def _mark_known_divergences(entries, known: dict):
    """Wrap each entry whose test_iri is a key in `known` in
    pytest.param(..., marks=xfail(strict=True, reason=...)); every other
    entry passes through unchanged. Shared by both the Oxigraph-specific and
    in-memory-backend-specific divergence sets below - same mechanism, two
    different known-issue tables."""
    return [
        pytest.param(e, marks=pytest.mark.xfail(strict=True, reason=known[key]))
        if (key := e.test_iri.rsplit("#", 1)[-1]) in known
        else e
        for e in entries
    ]


EVAL_SELECT_OXIGRAPH = _mark_known_divergences(EVAL_SELECT, _OXIGRAPH_KNOWN_DIVERGENCES)

# Same mechanism as _OXIGRAPH_KNOWN_DIVERGENCES above, for Fuseki. A first
# full run (2026-08-10) against a live Fuseki 5.5.0 endpoint found 8
# failures - 5 turned out to be a real starlayergraph bug (extract_fields()
# silently dropped a non-empty bracketed property list used as a
# statement's own subject, e.g. `[ :q :z ] .` - see
# starlayergraph/parsers/syntax.py's own comment there), now fixed, not listed
# here. These 3 are a genuine Fuseki-only conformance bug: TRIPLE()
# validates its `predicate` argument but not its `subject` argument
# (confirmed against a second engine, Oxigraph, which correctly rejects the
# identical case) - see docs/fuseki-upstream-issues.md Issue 1.
#
# NOT fixed by upgrading the container - confirmed directly (2026-08-10)
# against a live jena-6.1.0 endpoint (the latest release at the time):
# apache/jena#3658 (merged 2025-12-20, first released in jena-6.0.0) only
# restricts a triple term's subject in `VALUES`/`BIND`-wrapped *literal*
# `<<( )>>` syntax - it never touched TRIPLE()'s own function
# implementation, which every fixture below actually uses
# (`BIND(TRIPLE(?subject, ?predicate, ?object) AS ?triple)`). Re-ran
# expression/triple-on-triple-terms.rq itself through StarLayerGraph
# against jena-6.1.0: identical failure to jena-5.5.0. Reported upstream as
# apache/jena#4141 (2026-08-10, open) - see docs/fuseki-upstream-issues.md
# Issue 1's "Status" section for the full investigation.
_FUSEKI_KNOWN_DIVERGENCES: dict = {
    "triple-on-literals": "Jena ARQ: TRIPLE() doesn't validate its subject argument - "
    "reported upstream as apache/jena#4141 - see docs/fuseki-upstream-issues.md Issue 1",
    "triple-on-str-literals": "Jena ARQ: TRIPLE() doesn't validate its subject argument - "
    "reported upstream as apache/jena#4141 - see docs/fuseki-upstream-issues.md Issue 1",
    "triple-on-triple-terms": "Jena ARQ: TRIPLE() doesn't validate its subject argument - "
    "reported upstream as apache/jena#4141 - see docs/fuseki-upstream-issues.md Issue 1",
}

EVAL_SELECT_FUSEKI = _mark_known_divergences(EVAL_SELECT, _FUSEKI_KNOWN_DIVERGENCES)

# Historical note: this table used to document 4 known, understood
# limitations of the in-memory (rdf-1.1, tt:HASH content-addressed URI
# encoding + SPARQL 1.2 -> 1.1 text rewrite) backend specifically - op-2,
# order-1, order-2, construct-5 - confirmed NOT limitations of RDF 1.2/
# SPARQL 1.2 support itself (the native Oxigraph backend already passed
# all 4 cleanly with zero query rewriting, proving it). All 4 are now
# genuinely fixed as of 2026-08-05, in this order:
#
# op-2 - two fixes:
#   1. starlayergraph/query/evaluate_patches.py::patch_relational_expression_tt_hash_equality
#      patches `=`/`!=` to decode a tt:HASH URIRef's rdf:subject/predicate/
#      object encoding triples on the fly and recursively re-apply RDF 1.2
#      value-equality, instead of stock rdflib's plain URIRef string
#      equality (which can only ever agree with sameTerm).
#   2. starlayergraph/model/encoding.py::canonicalize_query_result_value
#      canonicalizes a numeric-XSD-typed literal's lexical form specifically
#      for SPARQL SELECT *results* (not for parsing/storage, which
#      deliberately preserves exact lexical form as written - see
#      parsers/syntax.py::coerce_object's own docstring/tests - a query
#      result is expected to match a real engine's own results instead,
#      e.g. "123e0" canonicalizing to "123.0").
#
# construct-5: `CONSTRUCT WHERE { :a :b ?c {| ?q ?z |} . }`'s annotation-
# shorthand reifier needed to behave like any other anonymous-blank-node-
# shaped part of a CONSTRUCT template - fresh per solution, independent of
# whatever (irrelevant) reifier identity was used purely for WHERE-clause
# pattern *matching* (the official expected output has *two* distinct
# reifiers for the same underlying triple: one from matching, one freshly
# constructed for the template's own `{| |}` re-assertion). Root cause:
# `sparql12_to_11.py::_try_split_construct_where` only recognized the
# *explicit* `CONSTRUCT { template } WHERE { where }` two-block form - for
# the `CONSTRUCT WHERE { pattern }` shorthand specifically, it fell through
# to a single-pass rewrite of `pattern` as an ordinary (non-template) WHERE
# clause, so an annotation block inside it only ever got WHERE-clause
# matching semantics for its reifier, never the template's own fresh-per-
# solution one. Fixed by teaching `_try_split_construct_where` to recognize
# this shorthand and return the *same* source text as both
# `template_inner` and `where_inner` - the caller (`_rewrite_construct_query`)
# already rewrites those two independently (matching semantics for one,
# `in_construct_template=True` fresh-BIND semantics for the other), each
# minting its own fresh internal variable names, so feeding it the same
# text twice needed no other change.
#
# order-1/order-2 - two fixes, the second a revised, more precise version
# of a first attempt that was tried and reverted:
#   1. starlayergraph/query/evaluate_patches.py::patch_order_by_tt_hash_term_kind
#      gives a tt:HASH URIRef its own ORDER BY term-kind bucket, after
#      literal per RDF 1.2, instead of stock rdflib's `_val`, which has no
#      bucket for triple terms at all and sorts one as an ordinary IRI.
#   2. Fixing (1) exposed a separate, deeper, pre-existing bug: this
#      fixture's own query shape (`{ SELECT ?v { ?s ?p ?v } ORDER BY ?v
#      OFFSET N LIMIT 1 }`, an unconstrained BGP) could incidentally match
#      the in-memory backend's own internal tt:HASH rdf:subject/predicate/
#      object encoding triples - confirmed to reproduce identically with
#      *stock, unpatched* ORDER BY too (the old, wrong sort order just
#      coincidentally kept the leaked rows outside the OFFSET/LIMIT window
#      most of the time, masking it). A first, blanket "filter every BGP
#      match against an encoding triple" fix regressed a real, previously-
#      passing test (basic-5's `<<:a :b ?o>> ?q :z .`, whose own rewritten
#      form *legitimately* needs to match these same triples to decode a
#      triple-term pattern containing a variable) and was reverted. The
#      precise fix - starlayergraph/query/evaluate_patches.py::
#      patch_bgp_skips_encoding_triples - only filters a match where the
#      *pattern's own* predicate position was unconstrained (a variable,
#      not yet bound before this triple is matched) - never one where the
#      pattern itself already specifies the predicate as a literal
#      rdf:subject/predicate/object IRI, which is exactly the shape every
#      rewriter-generated decode pattern always uses. That distinction -
#      "did the query text ask for this predicate specifically" vs "did an
#      unconstrained wildcard happen to match it" - isn't visible from the
#      matched triple's values alone (what the first attempt checked), but
#      is directly available from the pattern's own pre-match term.
_IN_MEMORY_KNOWN_DIVERGENCES: dict = {}

EVAL_SELECT_IN_MEMORY = _mark_known_divergences(EVAL_SELECT, _IN_MEMORY_KNOWN_DIVERGENCES)
EVAL_CONSTRUCT_IN_MEMORY = _mark_known_divergences(EVAL_CONSTRUCT, _IN_MEMORY_KNOWN_DIVERGENCES)

_no_data = pytest.mark.skipif(
    not ALL_ENTRIES,
    reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py",
)

_oxigraph = pytest.mark.skipif(
    not oxigraph_available(),
    reason="Oxigraph not running - start with: "
    "docker run -d --name oxigraph-test -p 7878:7878 "
    "ghcr.io/oxigraph/oxigraph serve --location /data --bind 0.0.0.0:7878",
)

_fuseki = pytest.mark.skipif(
    not fuseki_available(),
    reason="Fuseki not running - start with: "
    "docker run -d --name fuseki-test -p 3030:3030 atomgraph/fuseki:latest --update --mem --ping /starlayergraph "
    "(see tests/integration/test_fuseki_backend.py); needs Fuseki 5.5+ for native RDF 1.2 <<( )>> syntax - "
    "not stain/jena-fuseki (only reaches 5.1.0), and not secoresearch/fuseki (tops out at 5.5.0, no longer "
    "updated).",
)


# Marker predicates for _skolemize_graph()'s TripleTerm encoding below -
# deliberately *not* the real rdf:subject/predicate/object (which some
# fixture could conceivably use as ordinary data in some other test, and
# comparing rdf:subject/predicate/object triples this function *didn't*
# generate against ones it did would be a real, if unlikely, false-match
# risk) - a private, test-only namespace makes a collision impossible.
_SKOLEM_NS = "urn:starlayergraph-test:skolem-tt#"
_SK_SUBJECT   = URIRef(_SKOLEM_NS + "subject")
_SK_PREDICATE = URIRef(_SKOLEM_NS + "predicate")
_SK_OBJECT    = URIRef(_SKOLEM_NS + "object")
_SK_TT_MARKER = URIRef(_SKOLEM_NS + "TripleTerm")


def _skolemize_graph(graph) -> Graph:
    """Convert every TripleTerm value in `graph` into ordinary triples on a
    fresh BNode, and every RR_NS anonymous-reifier URIRef into a fresh
    BNode too, so the whole thing can be handed to
    rdflib.compare.to_isomorphic() (which requires every term to be a real
    rdflib.term.Node - TripleTerm deliberately isn't one, and rr:N is a
    starlayergraph-internal skolemization of what's really an anonymous
    reifier - see starlayergraph/model/encoding.py's RR_NS).

    An earlier version of this function instead collapsed each TripleTerm
    into a *single* content-hashed URIRef (hashing its own already-
    skolemized subject/predicate/object). That broke the very "up to
    consistent BNode relabeling" comparison to_isomorphic() exists to do:
    hashing in a component's specific (arbitrary) BNode label baked
    non-canonical identity into a value to_isomorphic was never told it
    could relabel, so two graphs that actually *were* isomorphic (same
    structure, different arbitrary BNode label for "the" anonymous
    reifier) hashed to different URIs and compared as unequal - confirmed
    via construct-3/expr-1, both of which mix an RR_NS-mapped-to-BNode
    reifier with a TripleTerm nesting it.

    Encoding a TripleTerm as ordinary triples on a *fresh* BNode instead
    sidesteps the problem entirely, rather than working around it: BNode
    canonicalization is exactly what to_isomorphic() already does
    correctly, so representing "this is a triple term with these
    components" as ordinary triples (the same rdf:subject/predicate/object
    *shape* starlayergraph's own on-disk tt: encoding already uses - see
    starlayergraph.parsers.turtle_parser.decode_tt_encoded_triples - though with
    different, collision-proof predicates, see _SK_SUBJECT et al above)
    rather than pre-collapsing it into one opaque value lets
    to_isomorphic() do the comparison itself instead of this function
    trying to pre-empt it.
    """
    out = Graph()
    rr_to_bnode: dict = {}

    def skolemize(term):
        if isinstance(term, TripleTerm):
            node = BNode()
            out.add((node, RDF.type, _SK_TT_MARKER))
            out.add((node, _SK_SUBJECT, skolemize(term.subject)))
            out.add((node, _SK_PREDICATE, skolemize(term.predicate)))
            out.add((node, _SK_OBJECT, skolemize(term.object)))
            return node
        if isinstance(term, URIRef) and str(term).startswith(RR_NS):
            if term not in rr_to_bnode:
                rr_to_bnode[term] = BNode()
            return rr_to_bnode[term]
        return term

    for s, p, o in graph:
        out.add((skolemize(s), p, skolemize(o)))
    return out


@_no_data
@pytest.mark.parametrize("entry", EVAL_SELECT_IN_MEMORY, ids=lambda e: e.test_iri)
def test_eval_select_original_query(entry):
    query_text = entry.read(entry.query_file)
    expected = parse_srj(entry.read(entry.result_file))

    g = _new_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in g.query(query_text).bindings]
    assert bindings_match(actual, expected)


@_no_data
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT_IN_MEMORY, ids=lambda e: e.test_iri)
def test_eval_construct_original_query(entry):
    query_text = entry.read(entry.query_file)
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    g = _new_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual_graph = g.query(query_text).graph
    assert to_isomorphic(_skolemize_graph(actual_graph)) == to_isomorphic(_skolemize_graph(expected_graph))


# ---------------------------------------------------------------------------
# Same two checks, run against a live Oxigraph endpoint instead of the
# in-memory backend, via _new_oxigraph_graph() - the exact same .parse()/
# .query() calls as the in-memory tests above, no special loading path.
# Still the original, unmodified W3C query text either way.
# ---------------------------------------------------------------------------

@_no_data
@_oxigraph
@pytest.mark.parametrize("entry", EVAL_SELECT_OXIGRAPH, ids=lambda e: e.test_iri)
def test_eval_select_original_query_oxigraph(entry):
    query_text = entry.read(entry.query_file)
    expected = parse_srj(entry.read(entry.result_file))

    clear_oxigraph()
    g = _new_oxigraph_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in g.query(query_text).bindings]
    assert bindings_match(actual, expected)


@_no_data
@_oxigraph
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_eval_construct_original_query_oxigraph(entry):
    query_text = entry.read(entry.query_file)
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    clear_oxigraph()
    g = _new_oxigraph_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual_graph = g.query(query_text).graph
    assert to_isomorphic(_skolemize_graph(actual_graph)) == to_isomorphic(_skolemize_graph(expected_graph))


# ---------------------------------------------------------------------------
# Same two checks again, run against a live Fuseki endpoint - the second
# native rdf-1.2 engine option (see starlayergraph/backends/native.py's own
# module docstring: this repo does zero query/data rewriting for either
# native-backend engine, so what Fuseki accepts/returns is exactly what a
# client sees, same as the Oxigraph tests above).
# ---------------------------------------------------------------------------

@_no_data
@_fuseki
@pytest.mark.parametrize("entry", EVAL_SELECT_FUSEKI, ids=lambda e: e.test_iri)
def test_eval_select_original_query_fuseki(entry):
    query_text = entry.read(entry.query_file)
    expected = parse_srj(entry.read(entry.result_file))

    clear_fuseki()
    g = _new_fuseki_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in g.query(query_text).bindings]
    assert bindings_match(actual, expected)


@_no_data
@_fuseki
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_eval_construct_original_query_fuseki(entry):
    query_text = entry.read(entry.query_file)
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    clear_fuseki()
    g = _new_fuseki_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    actual_graph = g.query(query_text).graph
    assert to_isomorphic(_skolemize_graph(actual_graph)) == to_isomorphic(_skolemize_graph(expected_graph))
