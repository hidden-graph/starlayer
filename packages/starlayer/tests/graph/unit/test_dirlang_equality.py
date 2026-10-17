"""The text rewrite that keeps SPARQL equality away from ``rdf:dirLangString`` on
Oxigraph (``starlayer.graph.backends.dirlang_equality``). Pure text; no engine."""

from __future__ import annotations

import pytest
from starlayer.graph.backends.dirlang_equality import guard

GUARD_MARK = "hasLANGDIR"


def _guarded(query: str) -> bool:
    return GUARD_MARK in guard(query)


# --- equalities that are left alone ---------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * WHERE { ?s ?p ?o }",  # no comparison at all
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o = <http://example.org/x>) }",  # IRI
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o = ex:x) }",  # prefixed name
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o = 5) }",  # number
        "SELECT * WHERE { ?s ?p ?o . FILTER(5 = ?o) }",  # constant on the left
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o != true) }",  # boolean
        'SELECT * WHERE { ?s ?p ?o . FILTER(?o = "plain") }',  # simple literal
        'SELECT * WHERE { ?s ?p ?o . FILTER(?o = "hi"@en) }',  # language, no direction
        'SELECT * WHERE { ?s ?p ?o . FILTER(?o = "1"^^<http://www.w3.org/2001/XMLSchema#integer>) }',  # typed
        "SELECT * WHERE { ?s ?p ?o . FILTER(STR(?o) = STR(?p)) }",  # functions that never return one
        "SELECT * WHERE { ?s ?p ?o . FILTER(LANG(?o) = 'en') }",
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o IN (1, 2, 3)) }",  # IN over constants
        "SELECT * WHERE { ?s ?p ?o . FILTER(?o NOT IN (<http://example.org/a>)) }",
        "SELECT * WHERE { ?s ?p ?o . FILTER(?a < ?b && ?a >= ?c) }",  # not equality
        "SELECT * WHERE { ?s ?p ?o . FILTER(RAND() = ?o) }",  # cannot be evaluated twice
    ],
)
def test_a_comparison_that_cannot_involve_two_dirlangstrings_is_left_alone(query):
    assert guard(query) == query


def test_an_equals_sign_inside_an_iri_a_string_or_a_comment_is_not_an_operator():
    query = 'SELECT * WHERE { ?s <http://e/p?x=1> "a = b" . # ?a = ?b\n }'
    assert guard(query) == query


# --- equalities that are rewritten ------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * WHERE { ?s ?p ?t . FILTER(?t = ?t) }",
        "SELECT * WHERE { ?s ?p ?t . FILTER(?t != ?u) }",
        'SELECT * WHERE { ?s ?p ?t . FILTER(?t = "hi"@en--ltr) }',  # a dirLangString constant
        'SELECT * WHERE { ?s ?p ?t . FILTER(?t = STRLANGDIR("x", "en", "ltr")) }',
        "SELECT * WHERE { ?s ?p ?a . FILTER(?x + 1 = ?y) }",
        "SELECT (?a = ?b AS ?eq) WHERE { ?s ?p ?a . ?s ?q ?b }",
        "SELECT * WHERE { ?s ?p ?a . BIND(?a = ?b AS ?e) }",
        "SELECT * WHERE { ?s ?p ?a . FILTER(?a IN (?b, ?c)) }",
        "SELECT * WHERE { ?s ?p ?a . FILTER(?a NOT IN (?b)) }",
        "INSERT { ?s <http://e/same> ?o } WHERE { ?s <http://e/a> ?x . ?o <http://e/a> ?y . FILTER(?x = ?y) }",
    ],
)
def test_a_comparison_between_two_unknowns_is_guarded(query):
    assert _guarded(query)


def test_the_guarded_form_is_exactly_if_both_are_dirlang_then_sameterm_else_the_original():
    out = guard("SELECT * WHERE { ?s ?p ?t . FILTER(?t = ?u) }")
    assert out == (
        "SELECT * WHERE { ?s ?p ?t . FILTER((IF(COALESCE(hasLANGDIR(?t), false) && "
        "COALESCE(hasLANGDIR(?u), false), sameTerm(?t, ?u), ?t = ?u))) }"
    )


def test_not_equal_uses_the_negated_sameterm():
    out = guard("SELECT * WHERE { ?s ?p ?t . FILTER(?t != ?u) }")
    assert "!sameTerm(?t, ?u)" in out and "?t != ?u" in out


def test_each_comparison_in_a_conjunction_is_guarded_with_its_own_operands():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(?a = ?b && ?c != ?d) }")
    assert (
        "sameTerm(?a, ?b)" in out and "!sameTerm(?c, ?d)" in out and " && (IF(" in out
    )


def test_an_operand_is_the_whole_arithmetic_expression_not_just_the_adjacent_token():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(?x + 1 = ?y * 2) }")
    assert "sameTerm(?x + 1, ?y * 2)" in out


def test_in_is_expanded_into_guarded_comparisons():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(?a IN (?b, 'z')) }")
    assert "sameTerm(?a, ?b)" in out  # the unknown item is guarded
    assert "?a = 'z'" in out  # the constant item is not


def test_not_in_becomes_a_conjunction_of_not_equals():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(?a NOT IN (?b, ?c)) }")
    assert out.count("!sameTerm") == 2 and " && (IF(" in out


def test_nested_comparisons_are_all_guarded_and_the_output_is_balanced():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(IF(?a = ?b, 1, 2) = ?c) }")
    assert out.count("(") == out.count(")")
    assert "sameTerm(?a, ?b)" in out
    # no unguarded equality is left behind: every '=' is the original inside a guarded IF
    assert "" not in out and "" not in out


def test_guarding_is_idempotent_enough_to_leave_no_placeholder_characters():
    out = guard("SELECT * WHERE { ?s ?p ?a . FILTER(?a = ?b) }")
    assert "" not in out
