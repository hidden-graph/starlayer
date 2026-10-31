"""Tests for the prototype hand-written SPARQL 1.2 query parser (``starlayer.sparql.parse_sparql``).

Three gates:

1. the W3C SPARQL 1.2 syntax fixtures vendored under ``tests/sparql/w3c_sparql12/data`` and the SPARQL 1.1 syntax and
   query fixtures under ``tests/sparql/w3c_sparql11/data``: every positive query must parse, every negative query
   must be rejected (update fixtures are out of scope here: SPARQL Update is the next piece of work);
2. the sqe fixpoint: text -> new tree -> ``sqe_tree_to_text`` -> new tree is the same tree;
3. agreement with the current rdflib-based path (``sqe_parse_to_tree``) on the sqe feature queries, the sqe
   modifier queries and the W3C queries. The current path costs about a second per query (it validates every
   tree with SHACL), so this gate is opt-in with the other sqe suites: ``pytest --sqe-coverage``.
"""

from __future__ import annotations

import pytest
from rdflib import RDF, XSD, Literal, URIRef, Variable
from starlayer.sparql.parse_sparql import (
    Node,
    SparqlSyntaxError,
    parse_sparql,
    sparql_to_tree,
    tokenize,
)
from starlayer.sparql.sqe import sqe_tree_to_text, sqe_validate
from tests.sparql.parse_sparql_support import (
    canonical_graph,
    current_tree,
    entry_key,
    same_tree,
    w3c11_entries,
    w3c_entries,
)

_POSITIVE = [e for e in w3c_entries("PositiveSyntaxTest", "QueryEvaluationTest") if e.query_file.endswith(".rq")]
_NEGATIVE = [e for e in w3c_entries("NegativeSyntaxTest") if e.query_file.endswith(".rq")]
# SPARQL 1.1: the syntax-query suite, the query-evaluation queries of every category (extra positive material), the negative
# syntax tests of aggregates/grouping/construct (and the syntax-fed SERVICE ones).
_POSITIVE11 = w3c11_entries("PositiveSyntaxTest", "QueryEvaluationTest", ext=".rq")
_NEGATIVE11 = w3c11_entries("NegativeSyntaxTest", ext=".rq")


# ---------------------------------------------------------------------------
# Gate 1: W3C syntax tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _POSITIVE, reason="W3C SPARQL 1.2 test data not fetched")
@pytest.mark.parametrize("entry", _POSITIVE, ids=entry_key)
def test_w3c_positive_syntax_parses(entry):
    parse_sparql(entry.read(entry.query_file))


@pytest.mark.skipif(not _NEGATIVE, reason="W3C SPARQL 1.2 test data not fetched")
@pytest.mark.parametrize("entry", _NEGATIVE, ids=entry_key)
def test_w3c_negative_syntax_is_rejected(entry):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql(entry.read(entry.query_file))


@pytest.mark.skipif(not _POSITIVE11, reason="W3C SPARQL 1.1 test data not fetched")
@pytest.mark.parametrize("entry", _POSITIVE11, ids=lambda e: e.key)
def test_w3c11_positive_syntax_parses(entry):
    parse_sparql(entry.read())


@pytest.mark.skipif(not _NEGATIVE11, reason="W3C SPARQL 1.1 test data not fetched")
@pytest.mark.parametrize("entry", _NEGATIVE11, ids=lambda e: e.key)
def test_w3c11_negative_syntax_is_rejected(entry):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql(entry.read())


def test_w3c_suites_are_not_empty():
    assert len(_POSITIVE) >= 160 and len(_NEGATIVE) >= 80
    assert len(_POSITIVE11) >= 320 and len(_NEGATIVE11) >= 35


# ---------------------------------------------------------------------------
# Gate 2: the tree renders to text that parses back to the same tree
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _POSITIVE, reason="W3C SPARQL 1.2 test data not fetched")
@pytest.mark.parametrize("entry", _POSITIVE, ids=entry_key)
def test_tree_text_fixpoint(entry):
    from rdflib.compare import isomorphic

    tree = sparql_to_tree(entry.read(entry.query_file))
    again = sparql_to_tree(sqe_tree_to_text(*tree))
    assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0]))


@pytest.mark.skipif(not _POSITIVE11, reason="W3C SPARQL 1.1 test data not fetched")
@pytest.mark.parametrize("entry", _POSITIVE11, ids=lambda e: e.key)
def test_w3c11_tree_text_fixpoint(entry):
    from rdflib.compare import isomorphic

    tree = sparql_to_tree(entry.read())
    again = sparql_to_tree(sqe_tree_to_text(*tree))
    assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0]))


# ---------------------------------------------------------------------------
# Gate 3: agreement with the current path (opt-in: ~1 s per query on the old side)
# ---------------------------------------------------------------------------


def _agreement_corpus() -> dict[str, str]:
    from tests.sparql.sqe_coverage.test_sqe_features import FEATURES, P
    from tests.sparql.sqe_coverage.test_sqe_modifiers import QUERIES

    corpus = {"feature/" + k: P + v for k, v in FEATURES.items()}
    corpus.update({"modifier/" + k: v for k, v in QUERIES.items()})
    corpus.update({"w3c/" + entry_key(e): e.read(e.query_file) for e in _POSITIVE})
    corpus.update({"w3c11/" + e.key: e.read() for e in _POSITIVE11})
    return corpus


# Queries on which the two paths are known to differ (name -> why); each is a strict xfail.
KNOWN_DIFFERENCES: dict[str, str] = {}


def _agreement_params():
    try:
        corpus = _agreement_corpus()
    except ImportError:  # pragma: no cover
        return []
    return [
        pytest.param(
            text,
            id=name,
            marks=[pytest.mark.xfail(strict=True, reason=KNOWN_DIFFERENCES[name])] if name in KNOWN_DIFFERENCES else [],
        )
        for name, text in corpus.items()
    ]


@pytest.mark.sqe_coverage
@pytest.mark.parametrize("text", _agreement_params())
def test_new_parser_agrees_with_current_path(text):
    try:
        old = current_tree(text)
    except Exception:  # noqa: BLE001 - the current parser rejects it (an inherited rdflib gap): nothing to compare
        pytest.skip("the current path rejects this query")
    assert same_tree(sparql_to_tree(text), old)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

P = "PREFIX : <http://e/>\n"


def test_tokenizer_positions_and_kinds():
    toks = tokenize("SELECT ?x { ?x :p 1.5 }")
    assert [(t.kind, t.text) for t in toks[:4]] == [("W", "SELECT"), ("VAR", "?x"), ("P", "{"), ("VAR", "?x")]
    assert toks[4].kind == "PNAME" and toks[5].kind == "DEC"
    assert toks[1].pos == 7


def test_less_than_is_not_an_iri():
    q = parse_sparql(P + "SELECT * { ?x :p ?y FILTER(?y<3 && ?y>1) }")
    assert q.kind == "SelectQuery"


def test_ast_of_a_small_query():
    q = parse_sparql(P + "SELECT DISTINCT ?x WHERE { ?x a :C ; :p ?y , ?z } LIMIT 2")
    assert q["modifier"] == "DISTINCT" and q["limit"] == Literal(2)
    assert [(t["s"], t["p"], t["o"]) for t in q["where"]] == [
        (Variable("x"), RDF.type, URIRef("http://e/C")),
        (Variable("x"), URIRef("http://e/p"), Variable("y")),
        (Variable("x"), URIRef("http://e/p"), Variable("z")),
    ]


def test_precedence_of_operators():
    q = parse_sparql(P + "SELECT * { FILTER(1 + 2 * 3 = 7 || false && true) }")
    top = q["where"][0]["expr"]
    assert top.kind == "ConditionalOrExpression"
    assert top["other"][0].kind == "ConditionalAndExpression"
    assert top["expr"].kind == "RelationalExpression"
    assert top["expr"]["expr"].kind == "AdditiveExpression"


def test_annotation_and_reifier_expand_to_rdf_reifies():
    q = parse_sparql(P + "SELECT * { ?s :p ?o ~ :r {| :a :b |} }")
    triples = [(t["s"], t["p"]) for t in q["where"]]
    assert triples == [
        (Variable("s"), URIRef("http://e/p")),
        (URIRef("http://e/r"), RDF.reifies if hasattr(RDF, "reifies") else URIRef(str(RDF) + "reifies")),
        (URIRef("http://e/r"), URIRef("http://e/a")),
    ]
    assert isinstance(q["where"][1]["o"], Node) and q["where"][1]["o"].kind == "TripleTerm"


def test_property_path_flattening():
    q = parse_sparql(P + "SELECT * { ?s (:a|:b)|:c/^:d ?o }")
    path = q["where"][0]["p"]
    assert path.kind == "AlternativePath" and len(path["args"]) == 3


def test_version_and_prologue_are_kept():
    q = parse_sparql('VERSION "1.2"\nBASE <http://b/> PREFIX : <x#> ASK { :s :p <o> }')
    assert [d[0] for d in q["prologue"]] == ["version", "base", "prefix"]
    assert q["where"][0]["o"] == URIRef("http://b/o")


def test_unicode_escape_in_string_and_iri():
    q = parse_sparql('SELECT * { ?s <http://e/\\u0061> "\\u00e9\\n" }')
    assert q["where"][0]["p"] == URIRef("http://e/a")
    assert q["where"][0]["o"] == Literal("é\n")


@pytest.mark.parametrize(
    "text, line, col",
    [
        ("SELECT * { ?s ?p }", 1, 18),
        ("SELECT *\n{ ?s ?p ?o\n  FILTER(?o + ) }", 3, 15),
        ("SELECT * { ?s :p ?o }", 1, 15),  # undeclared prefix
        ("SELECT * { ?s ?p ?o } garbage", 1, 23),
    ],
)
def test_errors_carry_positions(text, line, col):
    with pytest.raises(SparqlSyntaxError) as info:
        parse_sparql(text)
    assert (info.value.line, info.value.col) == (line, col)


@pytest.mark.parametrize(
    "text",
    [
        "SELECT * { ?s ?p ?o ?s ?p ?o }",  # missing '.'
        "SELECT ?x ?x { ?x ?p ?o }",
        "SELECT (1 AS ?o) { ?s ?p ?o }",
        "SELECT * { ?s ?p ?o } GROUP BY ?s",
        "SELECT ?s (COUNT(?o) AS ?c) { ?s ?p ?o }",
        "SELECT (SUM(COUNT(?o)) AS ?c) { ?s ?p ?o } GROUP BY ?s",
        "SELECT * { VALUES (?a ?b) { (1) } }",
        "SELECT * { ?s ?p ?o BIND(1 AS ?o) }",
        'SELECT * { ?s ?p "unterminated }',
    ],
)
def test_rejects_ill_formed_queries(text):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql(text)


def test_new_tree_validates_against_the_sqe_shapes():
    graph, _root = sparql_to_tree(
        P + "SELECT ?s (COUNT(*) AS ?c) { ?s :p/:q* ?o OPTIONAL { ?o :r ?z } {?s :a 1} UNION {?s :b 2} "
        "BIND(CONCAT(STR(?s), 'x') AS ?k) VALUES ?v { 1 UNDEF } FILTER NOT EXISTS { ?s :n ?m } } "
        "GROUP BY ?s HAVING (COUNT(*) > 1) ORDER BY DESC(?s) LIMIT 5 OFFSET 1"
    )
    assert sqe_validate(graph)[0]


def _round_trip(text: str) -> str:
    tree = sparql_to_tree(text)
    assert sqe_validate(tree[0])[0]
    rendered = sqe_tree_to_text(*tree)
    from rdflib.compare import isomorphic

    again = sparql_to_tree(rendered)
    assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0]))
    return rendered


def test_dataset_clauses_describe_service_and_version_are_in_the_tree():
    text = (
        'VERSION "1.2" DESCRIBE ?x <http://a> FROM <http://g1> FROM NAMED <http://g2> '
        "WHERE { ?x ?p ?o SERVICE SILENT <http://s> { ?x ?q ?z } SERVICE ?e { ?z ?r ?w } } LIMIT 3"
    )
    rendered = _round_trip(text)
    assert rendered.splitlines()[:5] == [
        'VERSION "1.2"',
        "DESCRIBE ?x <http://a>",
        "FROM <http://g1>",
        "FROM NAMED <http://g2>",
        "WHERE { ?x ?p ?o . SERVICE SILENT <http://s> { ?x ?q ?z . } SERVICE ?e { ?z ?r ?w . } }",
    ]
    g, root = sparql_to_tree(text)
    from starlayer.sparql.sqe import SQE

    assert (root, RDF.type, SQE.DescribeQuery) in g and (root, RDF.type, SQE.Query) in g
    assert [str(o) for o in g.objects(root, SQE.version)] == ["1.2"]


@pytest.mark.parametrize(
    "text",
    [
        "DESCRIBE <http://x>",
        "DESCRIBE * { ?s ?p ?o }",
        "DESCRIBE ?x <http://y> FROM <g> { ?x ?p ?o } GROUP BY ?x ORDER BY ?x LIMIT 2",
        "ASK FROM NAMED <g> { ?s ?p ?o } ORDER BY ?s LIMIT 1",
        "CONSTRUCT { ?s ?p ?o } FROM <g> WHERE { ?s ?p ?o } GROUP BY ?s ?p ?o",
        "SELECT * FROM <g> FROM NAMED <h> FROM <i> { SERVICE <http://s> { ?s ?p ?o } }",
    ],
)
def test_new_forms_round_trip_and_validate(text):
    _round_trip(text)


def test_describe_star_without_where_is_a_shape_violation():
    g, root = sparql_to_tree("DESCRIBE * { ?s ?p ?o }")
    from starlayer.sparql.sqe import SQE

    g.remove((root, SQE.where, None))
    assert not sqe_validate(g)[0]


def test_existing_trees_are_unchanged_by_the_vocabulary_additions():
    """A query without the new constructs encodes with none of the new terms."""
    from starlayer.sparql.sqe import SQE

    new_terms = {SQE[n] for n in ("DescribeQuery", "DatasetClause", "Service", "describe", "describeAll", "dataset",
                                   "source", "named", "service", "silent", "version")}  # fmt: skip
    g, _ = sparql_to_tree("SELECT ?s (COUNT(*) AS ?c) { ?s ?p ?o OPTIONAL { ?o ?q ?z } } GROUP BY ?s ORDER BY ?s LIMIT 1")
    used = {t for triple in g for t in triple}
    assert not (used & new_terms)


@pytest.mark.parametrize(
    "literal, lexical, datatype",
    [
        ("007", "007", XSD.integer),
        ("+5", "+5", XSD.integer),
        ("-0", "-0", XSD.integer),
        ("1.50", "1.50", XSD.decimal),
        ("+.5", "+.5", XSD.decimal),
        ("1E0", "1E0", XSD.double),
        ("1.0e+3", "1.0e+3", XSD.double),
        ("-.5E-02", "-.5E-02", XSD.double),
    ],
)
def test_numeric_literals_keep_their_lexical_form(literal, lexical, datatype):
    q = parse_sparql(f"SELECT * {{ ?s ?p {literal} }}")
    o = q["where"][0]["o"]
    assert str(o) == lexical and o.datatype == datatype
    rendered = sqe_tree_to_text(*sparql_to_tree(f"SELECT * {{ ?s ?p {literal} }}"))
    assert lexical in rendered


def test_typed_and_boolean_literals_keep_their_lexical_form():
    q = parse_sparql(
        'SELECT * { ?s ?p "2001-01-01T00:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> , "01"^^<http://www.w3.org/2001/XMLSchema#integer> , true }'
    )
    assert [str(t["o"]) for t in q["where"]] == ["2001-01-01T00:00:00Z", "01", "true"]
    q = parse_sparql("SELECT * { ?s ?p ?o } LIMIT 010 OFFSET 00")
    assert (str(q["limit"]), str(q["offset"])) == ("010", "00")


@pytest.mark.parametrize(
    "text",
    [
        "ASK { ?s ?p ?o FILTERSTR(?o) }",
        "ASK { ?s ?p ?o FILTERisTriple(?o) }",
        "SELECTDISTINCT?x{?x ?p ?o}",
        "SELECT * { ?s ?p ?o FILTERNOTEXISTS { ?o ?q ?r } }",
    ],
)
def test_adjacent_keywords_are_matched_longest_first(text):
    parse_sparql(text)


def test_a_word_that_is_not_made_of_keywords_is_still_an_error():
    with pytest.raises(SparqlSyntaxError):
        parse_sparql("ASK { ?s ?p ?o FILTERxyz(?o) }")
