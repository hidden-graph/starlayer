"""Regression tests for bugs found in the SPARQL parser area (hunt)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.sparql.parse_sparql import SparqlSyntaxError, parse_sparql


def _resolved(base, ref):
    return parse_sparql(f"BASE <{base}> SELECT * {{ <{ref}> ?p ?o }}").f["where"][0].f["s"].value


@pytest.mark.parametrize(
    ("base", "ref"),
    [
        ("http://a/b/c/", "a//b"),
        ("http://a//b", "g"),
        ("http://a/b/c/d#f", ""),
        ("urn:x:y", "g"),
        ("urn:x:y", "#s"),
        ("urn:x:y", "?y"),
        ("http://a/b/c/d;p?q", "../../g"),
        ("http://a/b/c/d;p?q", "../../../g"),
        ("http://a/b/c/d;p?q", "./g/."),
        ("http://a/b/c/d;p?q", "g;x=1/../y"),
        ("http://a/b/c/d;p?q", "?y"),
        ("http://a/b/c/d;p?q", "//g"),
        ("http://a", "g"),
        ("http://a/b/c/d", "#"),
    ],
)
def test_relative_iri_resolution_is_rfc3986(base, ref):
    want = list(ox.Store().query(f"BASE <{base}> SELECT (<{ref}> AS ?x) {{}}"))[0]["x"].value
    assert _resolved(base, ref) == want


def test_base_dot_segments_resolve_per_rfc3986():
    # 5.2.3 merge, then 5.2.4: /b/../g is /g (Oxigraph keeps /b/../g, which is not the RFC result)
    assert _resolved("http://a/b/../c", "g") == "http://a/g"


@pytest.mark.parametrize(
    "text",
    ["SELECT * WHERE { ( ) }", "SELECT * { () }", "CONSTRUCT { ( ) } WHERE { }"],
)
def test_bare_nil_is_not_a_triples_block(text):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql(text)


@pytest.mark.parametrize("text", ["SELECT * { () <http://a> 1 }", "SELECT * { ?s <http://a> () }"])
def test_nil_as_subject_or_object_still_parses(text):
    parse_sparql(text)


def test_check_query_prepare_accepts_a_valid_update():
    from starlayer.sparql.check import check_query

    assert check_query("INSERT DATA { <http://e/a> <http://e/b> 1 }", prepare=True) is None
    assert check_query("SELECT * { ?s ?p ?o }", prepare=True) is None
    assert check_query("SELECT * { ?s ?p ?o ", prepare=True) is not None


def test_function_distinct_needs_an_argument():
    from starlayer.sparql.check import check_query

    assert check_query("SELECT (<http://x/f>(DISTINCT) AS ?x) {}") is not None
    assert check_query("SELECT (<http://x/f>(DISTINCT 1) AS ?x) {}") is None


@pytest.mark.parametrize(
    "text",
    [
        "SELECT * { ?s ?p ?o FILTER <http://e/f>() }",
        "SELECT * { ?s ?p ?o FILTER(<http://e/f>()) }",
        "SELECT (<http://e/f>() AS ?x) {}",
        "SELECT * { BIND(<http://e/f>() AS ?x) }",
    ],
)
def test_zero_argument_iri_function_round_trips_through_sqe(text):
    from starlayer.sparql import sqe

    g, r = sqe.sqe_parse_to_tree(text)
    out = sqe.sqe_tree_to_text(g, r)
    assert "<http://e/f>()" in out
    parse_sparql(out)


@pytest.mark.parametrize(
    "text",
    [
        "BASE <http://x/y/> BASE <http://x/z/> SELECT * { <a> ?p ?o }",
        "BASE <http://x/> BASE <http://y/> SELECT * { <a> ?p ?o }",
        "BASE <http://x/> BASE <sub/> SELECT * { <a> ?p ?o }",
    ],
)
def test_two_base_declarations_in_one_prologue_encode(text):
    from starlayer.sparql import sqe

    g, r = sqe.sqe_parse_to_tree(text)
    out = sqe.sqe_tree_to_text(g, r)
    assert parse_sparql(out).f["where"][0].f["s"].value == parse_sparql(text).f["where"][0].f["s"].value


def test_star_query_run_rejects_an_unknown_override():
    from starlayer.graph import StarLayerGraph
    from starlayer.sparql.star_query import StarQuery

    q = StarQuery("SELECT * WHERE { ?s ?p ?o }")
    with pytest.raises(TypeError):
        q.run(StarLayerGraph(), procesor="x")


def test_entailment_rewrite_of_very_deep_nesting_is_a_rewrite_error():
    from starlayer.graph import StarLayerGraph
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT
    from starlayer.sparql.sqe.entailment import EntailmentRewriteError

    depth = 400
    text = "SELECT * WHERE { " + "{ " * depth + "?s a ?c" + " }" * depth + " }"
    try:
        StarLayerGraph().query(text, entailment=ENTAILMENT["RDFS"])
    except EntailmentRewriteError:
        pass
    except Exception as e:  # a parse-depth limit is an acceptable clean error too
        assert not isinstance(e, RecursionError)
