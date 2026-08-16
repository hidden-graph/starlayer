"""Unit tests for starlayergraph.query.remote_decompose - the mechanism that lets
a query depending on starlayergraph's own custom SPARQL functions (TT_HASH_FN,
the SUBJECT/PREDICATE/OBJECT accessors, STRLANGDIR) still run against a
genuinely remote store, by stripping every algebra node that depends on one
of those functions and re-evaluating it locally against each result row.

Regression coverage for a real bug found via live Fuseki testing while
scoping the removal of starlayergraph's old text-based SPARQL 1.2 rewriter: the
new starsparql-based pipeline can lower a non-ground triple-term
pattern's predicate constraint into a bare
``FILTER(PREDICATE(?tt) = :knows)`` - a custom-function call directly
inside a Filter's own expression, not wrapped in an Extend/BIND the way
every case this module was originally built against used. Sent to a real
remote engine as-is, that FILTER raises on the unknown function and SPARQL's
own FILTER semantics exclude the row - silently, no exception, every row
gone. decompose_for_remote() must strip that Filter too, not just Extend
nodes, and re-check its condition locally per row after the round trip.
"""

from __future__ import annotations

from rdflib import URIRef, Variable
from starlayergraph.query.query_cache import prepare_query_cached
from starlayergraph.query.remote_decompose import (
    contains_custom_function_call,
    decompose_for_remote,
    evaluate_recipes_locally,
    row_passes_filters,
)

EX = "http://example.org/"


def _prepare(query_text: str):
    cache = {}
    return prepare_query_cached(cache, query_text, {"ex": EX}, None)


def test_non_ground_triple_term_pattern_strips_filter_not_just_extend():
    """The actual regression: FILTER(PREDICATE(?tt) = :knows) must be
    stripped, and the algebra must contain no custom-function call
    afterward - otherwise it's unsafe to send to a remote store at all."""
    prepared = _prepare(
        f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt ?s ?o WHERE {{
            ?stmt rdf:reifies <<( ?s ex:knows ?o )>> .
        }}
        """
    )
    recipes, filters = decompose_for_remote(prepared)
    assert filters, "expected at least one stripped Filter recipe"
    assert not contains_custom_function_call(prepared.algebra), (
        "algebra must be fully free of custom-function calls after decomposition - "
        "anything left would raise against a real remote engine"
    )


def test_stripped_filter_recipe_correctly_excludes_non_matching_rows():
    """End-to-end simulation of what StarLayerGraph.query() does with the
    decomposed recipes/filters against raw (unrestored) remote result rows -
    a row whose triple-term predicate doesn't match must be excluded, one
    that does match must survive."""
    prepared = _prepare(
        f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt ?s ?o WHERE {{
            ?stmt rdf:reifies <<( ?s ex:knows ?o )>> .
        }}
        """
    )
    recipes, filters = decompose_for_remote(prepared)
    # The internal pattern variable a stripped recipe's own expression
    # depends on (the tt:HASH-bound BGP match) - not a recipe's own output
    # variable (s/o), which is *computed from* this one, not supplied by it.
    tt_var = next(iter(recipes[0][1]["expr"]))
    # Two fake "remote rows": one whose tt:HASH actually encodes ex:knows as
    # predicate, one that doesn't. The accessor functions (SUBJECT/PREDICATE/
    # OBJECT) decode a tt:HASH URI via the process-global remember_tt_hash
    # registry, not by re-deriving components from the hash itself (a
    # one-way hash) - register both here the same way real ground-value
    # computation would (_eager_lower_value/_hash_call), so the accessor
    # calls this test exercises have something real to decode.
    from starlayergraph.model.encoding import TT_NS, remember_tt_hash, term_key, tt_hash

    def _make_tt_uri(s, p, o):
        uri = URIRef(TT_NS + tt_hash(term_key(s), term_key(p), term_key(o)))
        remember_tt_hash(uri, s, p, o)
        return uri

    matching_uri = _make_tt_uri(URIRef(EX + "a"), URIRef(EX + "knows"), URIRef(EX + "b"))
    other_uri = _make_tt_uri(URIRef(EX + "a"), URIRef(EX + "likes"), URIRef(EX + "b"))

    matching_row = {Variable("stmt"): URIRef(EX + "stmt1"), tt_var: matching_uri}
    other_row = {Variable("stmt"): URIRef(EX + "stmt2"), tt_var: other_uri}

    merged_match = evaluate_recipes_locally(recipes, matching_row, None)
    merged_other = evaluate_recipes_locally(recipes, other_row, None)

    assert row_passes_filters(filters, merged_match, None) is True
    assert row_passes_filters(filters, merged_other, None) is False


def test_ground_pattern_needs_no_filter_stripping():
    """A ground triple-term pattern lowers to a plain BGP triple with a
    literal tt:HASH URIRef term (no Extend/Filter/custom-function call
    involved at all - see lower_rdf11.py's own _lower_pattern_term
    docstring) - decompose_for_remote should find nothing to strip."""
    prepared = _prepare(
        f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {{
            ?stmt rdf:reifies <<( ex:a ex:knows ex:b )>> .
        }}
        """
    )
    recipes, filters = decompose_for_remote(prepared)
    assert recipes == []
    assert filters == []


def test_row_passes_filters_empty_list_is_always_true():
    assert row_passes_filters([], {}, None) is True
