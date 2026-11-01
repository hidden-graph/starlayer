"""Bug-hunt reproducers for the StarLayer-owned SPARQL parser (``parse_sparql.py``) and its text rendering.

Each test is a minimal reproducer of a confirmed bug, marked ``xfail(strict=True)``; when the bug is fixed the test
XPASSes and strict mode makes that visible.
"""

from __future__ import annotations

import pytest
from starlayer.sparql.parse_sparql import SparqlSyntaxError, ast_to_tree, parse_sparql
from starlayer.sparql.sqe.to_text import sqe_tree_to_text


def _roundtrip(text: str) -> None:
    """parse -> sqe tree -> text -> parse. Parse rejection of the ORIGINAL (a depth limit) is acceptable; anything
    after a successful parse must work, and only ever fail with SparqlSyntaxError at the first stage."""
    try:
        ast = parse_sparql(text)
    except SparqlSyntaxError:
        return
    graph, root = ast_to_tree(ast)
    regenerated = sqe_tree_to_text(graph, root)
    parse_sparql(regenerated)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: TRIPLE(1, <p>, 2) (a function call, accepted) is rendered by sqe_tree_to_text as the triple-term "
    "literal '<<( 1 <p> 2 )>>', which the parser rejects (literal subject / non-IRI predicate in an expression "
    "triple term; W3C tripleterm-subject-06 is a negative test), so the regenerated query is invalid",
)
@pytest.mark.parametrize(
    "text",
    [
        "SELECT * { BIND(TRIPLE(1, <http://e/p>, 2) AS ?x) }",
        "SELECT * { BIND(TRIPLE(<http://e/s>, 1, 2) AS ?x) }",
        'SELECT * { BIND(TRIPLE(<http://e/s>, "p", 2) AS ?x) }',
        "SELECT * { BIND(TRIPLE(<<( <http://e/a> <http://e/b> <http://e/c> )>>, <http://e/p>, 2) AS ?x) }",
    ],
)
def test_triple_function_with_invalid_triple_term_components_regenerates_valid_text(text):
    graph, root = ast_to_tree(parse_sparql(text))
    parse_sparql(sqe_tree_to_text(graph, root))


@pytest.mark.xfail(
    strict=True,
    reason="BUG (low): the parser deliberately lexes glued keywords longest-first ('FILTERSTR(', 'LIMIT 1OFFSET 1', "
    "'ORDERBY' are accepted, as by Oxigraph and the scannerless reading of the grammar) but its word token swallows "
    "trailing digits, so 'LIMIT1' / 'OFFSET1' (keyword + INTEGER) are rejected, inconsistent with 'LIMIT 1OFFSET 1' "
    "being accepted; Oxigraph accepts both",
)
@pytest.mark.parametrize("text", ["SELECT * { ?s ?p ?o } LIMIT1", "SELECT * { ?s ?p ?o } LIMIT 1 OFFSET1"])
def test_keyword_glued_to_integer_is_lexed_like_other_glued_keywords(text):
    assert parse_sparql(text) is not None


@pytest.mark.xfail(
    strict=True,
    reason="BUG: text accepted at nesting depth N is regenerated with parentheses added per level "
    "('!(!(!true))'), so the regenerated text is rejected by the same parser as 'nested too deeply'",
)
def test_regenerated_text_of_accepted_deep_unary_chain_reparses():
    # 'FILTER(!!...!true)' with 110-300 '!' parses, but sqe_tree_to_text emits '!(!(...))' (twice the depth).
    for n in (120, 200, 300):
        _roundtrip("SELECT * { FILTER(" + "!" * n + "true) }")


@pytest.mark.xfail(
    strict=True,
    reason="BUG: sqe_tree_to_text raises RecursionError (not a SparqlSyntaxError / not guarded) for deeply nested "
    "groups that parse_sparql accepts",
)
def test_deeply_nested_group_renders_without_recursion_error():
    for n in (300, 350):
        _roundtrip("SELECT * " + "{ " * n + "?s ?p ?o" + " }" * n)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: sqe_tree_to_text raises RecursionError for deeply nested triple terms that parse_sparql accepts",
)
def test_deeply_nested_triple_term_renders_without_recursion_error():
    for n in (800, 900):
        _roundtrip("SELECT * { ?s ?p " + "<<( ?a ?b " * n + "?c" + " )>>" * n + " }")
