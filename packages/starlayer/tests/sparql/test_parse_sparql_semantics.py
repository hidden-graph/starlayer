"""Static semantic rules of SPARQL 1.2 Query (section 19.7 notes, 18.3.1 scope) for ``parse_sparql``.

Every rule has negative cases (rejected) and positive cases (accepted); see ``parse_sparql_rules.py`` for the rules
and their sources. Besides rejection, a negative case must fail for the rule it belongs to: the error message is
checked against the rule's expected wording so a query is not rejected by accident.
"""

from __future__ import annotations

import pytest
from starlayer.sparql.parse_sparql import SparqlSyntaxError, parse_sparql

from .parse_sparql_rules import RULES

_WORDING = {
    "bnode-label": "two different basic graph patterns",
    "bind-scope": "BIND target",
    "select-alias": ("already in scope", "projected twice"),
    "aggregate-placement": ("aggregate functions",),
    "select-star-grouping": "SELECT * cannot be used",
    "values": ("VALUES", "triple term", "expected a value"),
    "reifier-path": ("reifier or annotation", "predicate", "property path"),
    "sub-select": ("expected", "FROM"),
    "prefix": ("undeclared prefix", "integer", "unexpected text"),
    "expression-signs": ("expected", "unexpected"),
    "grouping": ("not grouped", "already in scope", "SELECT * cannot", "grouped", "expected"),
}


def _id(rule):
    return f"{rule.rule}:{'ok' if rule.ok else 'bad'}:{rule.text.split(chr(10), 1)[1][:70]}"


@pytest.mark.parametrize("rule", [r for r in RULES if r.ok], ids=_id)
def test_valid_query_is_accepted(rule):
    parse_sparql(rule.text)


@pytest.mark.parametrize("rule", [r for r in RULES if not r.ok], ids=_id)
def test_invalid_query_is_rejected_for_the_right_reason(rule):
    with pytest.raises(SparqlSyntaxError) as info:
        parse_sparql(rule.text)
    wanted = _WORDING[rule.rule]
    wanted = (wanted,) if isinstance(wanted, str) else wanted
    assert any(w in str(info.value) for w in wanted), str(info.value)


def test_semantic_errors_point_at_the_offending_clause():
    with pytest.raises(SparqlSyntaxError) as info:
        parse_sparql("SELECT * {\n  ?s ?p ?o\n  BIND(1 AS ?o)\n}")
    assert (info.value.line, info.value.col) == (3, 3)
    with pytest.raises(SparqlSyntaxError) as info:
        parse_sparql("SELECT ?s (1 AS ?s)\n{ ?s ?p ?o }")
    assert info.value.line == 1


def test_every_rule_has_both_polarities():
    by_rule: dict[str, set[bool]] = {}
    for r in RULES:
        by_rule.setdefault(r.rule, set()).add(r.ok)
    assert all(v == {True, False} for v in by_rule.values()), by_rule
    assert len(RULES) >= 100
