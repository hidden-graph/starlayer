"""Phase 6: native SPARQL 1.2 (triple-term) algebra representation.

Unlike every earlier phase, this one is verified *structurally*, not by
executing the original and round-tripped query/update and comparing result
rows — deliberately, per the Phase 6 plan (see CLAUDE.md / the plan file):
making a TripleTermNode-bearing algebra tree directly executable is real,
separate, future work (either a text round-trip through starlayergraph, or an
eventual 1.2-algebra -> 1.1-algebra translator this project would write
itself). Today's deliverable is the representation, not execution — so
"structural round-trip" (does the decoded tree match the original tree,
including bookkeeping like _vars) is this phase's correctness bar, the same
approach already used for SERVICE (test_phase2_forms.py's
test_service_structural_roundtrip), which can't be executed in tests either,
for an unrelated reason (it needs a live network call).

Ingestion here goes through starsparql.parse12 (prepare_query_12/
prepare_update_12), NOT rdflib's/starlayergraph's plain prepareQuery — see
grammar12.py for why: this project extends rdflib's own real SPARQL grammar
in place with new <<( s p o )>>/TRIPLE(s, p, o) productions, rather than
depending on starlayergraph's SPARQL-1.2-to-1.1 text-rewrite pipeline.
"""

from __future__ import annotations

from rdflib import Variable
from rdflib.plugins.sparql.parserutils import CompValue

from starsparql import query_to_rdf, rdf_to_query, rdf_to_update, update_to_rdf
from starsparql.parse12 import prepare_query_12, prepare_update_12
from starsparql.triple_term import TripleTermNode

PREFIXES = "PREFIX : <http://example.org/>\n"

QUERIES = [
    # ground triple term
    PREFIXES
    + "SELECT ?source WHERE { ?stmt :reifies <<( :bob :knows :carol )>> . ?stmt :source ?source . }",
    # pattern-with-variables triple term (a variable nested inside the term
    # itself, not just around it)
    PREFIXES
    + "SELECT ?source ?p WHERE { ?stmt :reifies <<( :bob ?p :carol )>> . ?stmt :source ?source . }",
    # nested triple term (a triple term used as another triple term's object)
    PREFIXES
    + "SELECT ?s WHERE { ?s :claims <<( :bob :knows <<( :carol :trusts :dave )>> )>> . }",
    # TRIPLE(...) function-call spelling, as a pattern-position term
    PREFIXES + "SELECT ?s WHERE { ?s :reifies TRIPLE(:bob, :knows, :carol) . }",
    # triple term as the subject of an ordinary triple pattern
    PREFIXES + "SELECT ?team WHERE { <<( :bob :knows :carol )>> :verifiedBy ?team . }",
]

CONSTRUCT_QUERIES = [
    PREFIXES
    + "CONSTRUCT { :dave :claims <<( :bob :knows :carol )>> } WHERE { :bob :knows :carol }",
]

UPDATES = [
    PREFIXES + "INSERT DATA { :dave :claims <<( :bob :knows :carol )>> }",
    PREFIXES
    + "INSERT { ?r :verified :true } WHERE { ?r :reifies <<( :bob ?p :carol )>> }",
]


def _strip_bookkeeping(node):
    """Deep-copy an algebra tree with the _vars/lazy bookkeeping keys
    removed and None-valued keys dropped, so two independently-built trees
    can be compared by real structure/content — same helper as
    test_phase2_forms.py's SERVICE structural round-trip test. TripleTermNode
    is a CompValue subclass, so it's handled by the same branch, no special
    casing needed."""
    if isinstance(node, CompValue):
        return {
            "__name__": node.name,
            **{
                k: _strip_bookkeeping(v)
                for k, v in node.items()
                if k not in ("_vars", "lazy") and v is not None
            },
        }
    if isinstance(node, (list, tuple)):
        return [_strip_bookkeeping(v) for v in node]
    return node


def test_queries_parse_and_translate():
    for query_text in QUERIES + CONSTRUCT_QUERIES:
        prepared = prepare_query_12(query_text)
        assert prepared.algebra is not None


def test_updates_parse_and_translate():
    for update_text in UPDATES:
        prepared = prepare_update_12(update_text)
        assert prepared.algebra is not None


def test_query_structural_roundtrip():
    for query_text in QUERIES + CONSTRUCT_QUERIES:
        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)
        reconstructed = rdf_to_query(graph, root)

        assert _strip_bookkeeping(prepared.algebra) == _strip_bookkeeping(
            reconstructed.algebra
        ), query_text
        assert prepared.algebra["_vars"] == reconstructed.algebra["_vars"], query_text


def test_update_structural_roundtrip():
    for update_text in UPDATES:
        prepared = prepare_update_12(update_text)
        graph, root = update_to_rdf(prepared)
        reconstructed = rdf_to_update(graph, root)

        assert _strip_bookkeeping(prepared.algebra) == _strip_bookkeeping(
            reconstructed.algebra
        ), update_text


def test_variable_nested_inside_triple_term_found_in_vars():
    """Direct guard for the exact defect an early spike caught: a plain,
    non-CompValue substitute for TripleTerm made rdflib's own _addVars
    bookkeeping silently under-count, since its generic recursive traversal
    (_traverseAgg) only recurses into CompValue/list/tuple/ParseResults.
    TripleTermNode being a real CompValue subclass is what avoids that -
    assert it directly here rather than only relying on the broader
    round-trip tests above to catch a regression."""
    query_text = (
        PREFIXES
        + "SELECT ?source WHERE { ?stmt :reifies <<( :bob ?p :carol )>> . ?stmt :source ?source . }"
    )
    prepared = prepare_query_12(query_text)
    assert Variable("p") in prepared.algebra["_vars"]

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    assert Variable("p") in reconstructed.algebra["_vars"]


def test_triple_term_node_is_the_decoded_type():
    """Confirms from_rdf's TripleTerm special case actually returns
    TripleTermNode, not a bare CompValue - a bare CompValue in this position
    would be unhashable and crash algebra.reorderTriples/_knownTerms the
    moment rdf_to_query recomputes _addVars/analyse bookkeeping."""
    query_text = (
        PREFIXES + "SELECT ?s WHERE { ?s :reifies <<( :bob :knows :carol )>> . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)

    triple = reconstructed.algebra["p"]["p"]["triples"][0]
    tt = triple[2]
    assert isinstance(tt, TripleTermNode)
