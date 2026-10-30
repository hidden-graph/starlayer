"""Negative corpus: ill-formed SRL must be rejected, never silently accepted.

Four groups: grammar errors; constructs that are SPARQL but not SRL (the parser reuses rdflib's grammar, so
these are the likeliest to leak through); the section 4.2 well-formedness conditions, which the grammar cannot
express; and rule sets that parse but cannot be stratified.
"""

from __future__ import annotations

import pytest

from .corpus import PRELUDE
from .helpers import parse_ruleset
from .known_failures import NEGATIVE_FAILURES

HEAD_BODY = "RULE {{ {head} }} WHERE {{ {body} }}"


def rule(head: str, body: str) -> str:
    return HEAD_BODY.format(head=head, body=body)


GRAMMAR = [
    ("missing-where", "RULE { ?x :p ?y }"),
    ("missing-body-braces", "RULE { ?x :p ?y } WHERE ?x :q ?y"),
    ("missing-head-braces", "RULE ?x :p ?y WHERE { ?x :q ?y }"),
    ("unbalanced-brace", "RULE { ?x :p ?y } WHERE { ?x :q ?y"),
    ("misspelt-keyword", "RULES { ?x :p ?y } WHERE { ?x :q ?y }"),
    ("select-instead-of-rule", "SELECT * WHERE { ?x :q ?y }"),
    ("construct-instead-of-rule", "CONSTRUCT { ?x :p ?y } WHERE { ?x :q ?y }"),
    ("missing-dot-between-triples", rule("?x :p ?y", "?x :a ?y ?y :b ?z")),
    ("set-with-equals", rule("?x :p ?z", "?x :q ?y SET (?z = ?y)")),
    ("set-without-parens", rule("?x :p ?z", "?x :q ?y SET ?z := ?y")),
    ("filter-without-expression", rule("?x :p ?y", "?x :q ?y FILTER")),
    ("data-with-variable", "DATA { ?x :b :c }"),
    ("data-with-filter", "DATA { :a :b :c FILTER (1 > 0) }"),
    ("data-without-braces", "DATA :a :b :c"),
    ("head-with-filter", rule("?x :p ?y FILTER (?y > 1)", "?x :q ?y")),
    ("head-with-set", rule("?x :p ?y SET (?z := 1)", "?x :q ?y")),
    ("version-not-a-string", "VERSION 1.2\n" + rule("?x :p ?y", "?x :q ?y")),
    ("prefix-without-iri", "PREFIX ex:\n" + rule("?x :p ?y", "?x :q ?y")),
    ("base-without-iri", "BASE\n" + rule("?x :p ?y", "?x :q ?y")),
    ("imports-without-iri", "IMPORTS\n" + rule("?x :p ?y", "?x :q ?y")),
    ("unknown-prefix", rule("?x ex:p ?y", "?x :q ?y")),
    ("unterminated-string", 'DATA { :a :b "oops }'),
    ("space-in-iri", "DATA { <http://example.org/a b> :b :c }"),
    ("malformed-number", "DATA { :a :b 1.2.3 }"),
    ("malformed-lang-dir", 'DATA { :a :b "x"@en-- }'),
    ("empty-blank-node-label", "DATA { _: :b :c }"),
    ("trailing-garbage", rule("?x :p ?y", "?x :q ?y") + "\n???"),
    ("trailing-stray-iri", rule("?x :p ?y", "?x :q ?y") + "\n<http://example.org/stray>"),
]

SPARQL_ONLY = [
    ("optional", rule("?x :p ?y", "?x :q ?y OPTIONAL { ?x :r ?z }")),
    ("union", rule("?x :p ?y", "{ ?x :q ?y } UNION { ?x :r ?y }")),
    ("graph", rule("?x :p ?y", "GRAPH :g { ?x :q ?y }")),
    ("values", rule("?x :p ?y", "VALUES ?y { 1 2 } ?x :q ?y")),
    ("bind", rule("?x :p ?z", "?x :q ?y BIND (?y + 1 AS ?z)")),
    ("subselect", rule("?x :p ?y", "{ SELECT ?x WHERE { ?x :q ?y } }")),
    ("minus", rule("?x :p ?y", "?x :q ?y MINUS { ?x :r ?y }")),
    ("service", rule("?x :p ?y", "SERVICE :s { ?x :q ?y }")),
    ("filter-not-exists", rule("?x :p ?y", "?x :q ?y FILTER NOT EXISTS { ?x :r ?y }")),
    ("filter-exists", rule("?x :p ?y", "?x :q ?y FILTER EXISTS { ?x :r ?y }")),
    ("filter-bound", rule("?x :p ?y", "?x :q ?y FILTER (BOUND(?y))")),
    ("filter-coalesce", rule("?x :p ?y", "?x :q ?y FILTER (COALESCE(?y, 1) > 0)")),
    ("filter-rand", rule("?x :p ?y", "?x :q ?y FILTER (RAND() > 0.5)")),
    ("aggregate-in-filter", rule("?x :p ?y", "?x :q ?y FILTER (COUNT(?y) > 1)")),
    ("path-star", rule("?x :p ?y", "?x :q* ?y")),
    ("path-plus", rule("?x :p ?y", "?x :q+ ?y")),
    ("path-optional", rule("?x :p ?y", "?x :q? ?y")),
    ("path-alternative", rule("?x :p ?y", "?x :q|:r ?y")),
    ("path-negated", rule("?x :p ?y", "?x !:q ?y")),
    ("path-in-head", rule("?x :a/:b ?y", "?x :q ?y")),
    ("order-by", rule("?x :p ?y", "?x :q ?y") + " ORDER BY ?x"),
    ("limit", rule("?x :p ?y", "?x :q ?y") + " LIMIT 1"),
]

WELL_FORMEDNESS = [
    ("unbound-head-variable", rule("?x :p ?z", "?x :q ?y")),
    ("unbound-filter-variable", rule("?x :p ?y", "?x :q ?y FILTER (?z > 1)")),
    ("filter-before-binding", rule("?x :p ?y", "FILTER (?y > 1) ?x :q ?y")),
    ("set-reuses-bound-variable", rule("?x :p ?y", "?x :q ?y SET (?y := 1)")),
    ("set-uses-unbound-variable", rule("?x :p ?z", "?x :q ?y SET (?z := ?w + 1)")),
    ("set-twice-same-variable", rule("?x :p ?z", "?x :q ?y SET (?z := 1) SET (?z := 2)")),
    ("variable-only-in-negation", rule("?x :p ?z", "?x :q ?y NOT { ?x :r ?z }")),
    ("not-inside-not", rule("?x :p ?y", "?x :q ?y NOT { NOT { ?x :r ?y } }")),
    ("set-inside-not", rule("?x :p ?y", "?x :q ?y NOT { SET (?z := 1) }")),
    ("triple-term-as-subject-body", rule("?x :p ?y", "<<( ?x :q ?y )>> :conf ?c . ?x :a ?y")),
    ("triple-term-as-subject-head", rule("<<( ?x :q ?y )>> :conf 1", "?x :q ?y")),
    ("head-variable-in-data", "DATA { :a :b :c }\n" + rule("?x :p ?w", "?x :q ?y")),
]


def _check(case_id, text, request):
    if case_id in NEGATIVE_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=NEGATIVE_FAILURES[case_id], strict=True))
    with pytest.raises(Exception) as caught:  # noqa: PT011 - the type is asserted next
        parse_ruleset(PRELUDE + text)
    assert type(caught.value).__name__ in {"SRLParseError", "SRLError"}, f"raised {type(caught.value).__name__}, not an SRL error"


@pytest.mark.srl_conformance
@pytest.mark.parametrize(("case_id", "text"), GRAMMAR, ids=[c[0] for c in GRAMMAR])
def test_grammar_errors_are_rejected(case_id, text, request):
    _check(case_id, text, request)


@pytest.mark.srl_conformance
@pytest.mark.parametrize(("case_id", "text"), SPARQL_ONLY, ids=[c[0] for c in SPARQL_ONLY])
def test_sparql_only_constructs_are_rejected(case_id, text, request):
    _check(case_id, text, request)


@pytest.mark.srl_conformance
@pytest.mark.parametrize(("case_id", "text"), WELL_FORMEDNESS, ids=[c[0] for c in WELL_FORMEDNESS])
def test_well_formedness_violations_are_rejected(case_id, text, request):
    _check(case_id, text, request)


STRATIFICATION = [
    ("self-negation", rule("?x :p ?y", "?x :q ?y NOT { ?x :p ?y }")),
    ("mutual-negation", rule("?x :a ?y", "?x :q ?y NOT { ?x :b ?y }") + "\n" + rule("?x :b ?y", "?x :q ?y NOT { ?x :a ?y }")),
    ("three-rule-negation-cycle",
     rule("?x :a ?y", "?x :q ?y NOT { ?x :c ?y }") + "\n" + rule("?x :b ?y", "?x :a ?y") + "\n" + rule("?x :c ?y", "?x :b ?y")),
]


@pytest.mark.srl_conformance
@pytest.mark.parametrize(("case_id", "text"), STRATIFICATION, ids=[c[0] for c in STRATIFICATION])
def test_non_stratifiable_rule_sets_are_refused(case_id, text, request):
    from starlayer.sparql.srl_eval import StratificationError

    if case_id in NEGATIVE_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=NEGATIVE_FAILURES[case_id], strict=True))
    ruleset = parse_ruleset(PRELUDE + text)  # parses: the grammar cannot see a cycle
    with pytest.raises(StratificationError):
        ruleset.plan()
