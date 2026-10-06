"""Tests for starlayer.sparql.srl.parse_ruleset - SRL/SPARQL-RL text
syntax parsing (WD-sparql12-rl-20260919 §7.6 grammar), Phase 1 of the SRL
implementation plan (see docs/functionality-overview.md).

The primary fixture is the spec's own §6.6 "Worked Example" (rules R1-R5,
also introduced piecemeal across §3) - reused again by test_srl_eval.py
(once the evaluation engine exists) as the end-to-end golden test, so
getting its exact parse right here is high-value: any AST-shape mistake
here would propagate silently into that later test's own "matches the
spec's stated output" assertion.
"""

import pytest
from rdflib import RDF, BNode, Literal, URIRef, Variable

from starlayer.sparql._srl_ast import (
    _AssignmentElement as AssignmentElement,
)
from starlayer.sparql._srl_ast import (
    _FilterElement as FilterElement,
)
from starlayer.sparql._srl_ast import (
    _NegationElement as NegationElement,
)
from starlayer.sparql.srl import (
    SRLParseError,
    TriplePattern,
    parse_ruleset,
)

EX = "http://example.org/"


def _p(local):
    return URIRef(EX + local)


WORKED_EXAMPLE_PREFIXES = f"""
PREFIX : <{EX}>
PREFIX rdf: <{RDF}>
"""

R1 = "RULE { ?x :exposedTo ?v } WHERE { ?x :hasVulnerability ?v . }"
R2 = "RULE { ?x :exposedTo ?v } WHERE { ?x :dependsOn ?y . ?y :exposedTo ?v . }"
R3 = """RULE { ?x :status :criticallyExposed }
WHERE { ?x :exposedTo ?v . ?v :severity ?s . FILTER(?s >= 9.0) }"""
R4 = """RULE { ?x :status :safeToDeploy }
WHERE { ?x rdf:type :Component . NOT { ?x :status :criticallyExposed } }"""
R5 = """RULE { [] rdf:type :Notification ; :concerns ?x }
WHERE { ?x :status :criticallyExposed . }"""

WORKED_EXAMPLE_RULES = WORKED_EXAMPLE_PREFIXES + "\n".join([R1, R2, R3, R4, R5])


def test_r1_simple_rule():
    rs = parse_ruleset(WORKED_EXAMPLE_PREFIXES + R1)
    assert len(rs.rules) == 1
    (rule,) = rs.rules
    assert rule.id is None
    assert rule.data is False
    assert rule.head == [TriplePattern(Variable("x"), _p("exposedTo"), Variable("v"))]
    assert rule.body == [TriplePattern(Variable("x"), _p("hasVulnerability"), Variable("v"))]


def test_r2_recursive_rule_two_body_triples():
    rs = parse_ruleset(WORKED_EXAMPLE_PREFIXES + R2)
    (rule,) = rs.rules
    assert rule.body == [
        TriplePattern(Variable("x"), _p("dependsOn"), Variable("y")),
        TriplePattern(Variable("y"), _p("exposedTo"), Variable("v")),
    ]


def test_r3_filter_element():
    rs = parse_ruleset(WORKED_EXAMPLE_PREFIXES + R3)
    (rule,) = rs.rules
    assert len(rule.body) == 3
    assert isinstance(rule.body[0], TriplePattern)
    assert isinstance(rule.body[1], TriplePattern)
    filter_elt = rule.body[2]
    assert isinstance(filter_elt, FilterElement)
    # The expression is a real rdflib Expr tree - reused as-is (see
    # srl.py's docstring for why no bespoke SRL expression AST
    # exists); spot-check it evaluates as expected rather than trying to
    # match its internal CompValue shape exactly.
    from rdflib.plugins.sparql.evaluate import _ebv
    from rdflib.plugins.sparql.sparql import FrozenBindings, QueryContext

    ctx = QueryContext()
    c = FrozenBindings(ctx, {Variable("s"): Literal(9.5)})
    assert _ebv(filter_elt.expr, c) is True
    c2 = FrozenBindings(ctx, {Variable("s"): Literal(1.0)})
    assert _ebv(filter_elt.expr, c2) is False


def test_r4_negation_element_body_restricted_shape():
    rs = parse_ruleset(WORKED_EXAMPLE_PREFIXES + R4)
    (rule,) = rs.rules
    assert rule.head == [TriplePattern(Variable("x"), _p("status"), _p("safeToDeploy"))]
    assert isinstance(rule.body[0], TriplePattern)
    neg = rule.body[1]
    assert isinstance(neg, NegationElement)
    assert neg.data is False
    assert neg.inner == [TriplePattern(Variable("x"), _p("status"), _p("criticallyExposed"))]


def test_r5_blank_node_head_and_semicolon_property_list():
    rs = parse_ruleset(WORKED_EXAMPLE_PREFIXES + R5)
    (rule,) = rs.rules
    assert len(rule.head) == 2
    t1, t2 = rule.head
    assert isinstance(t1.subject, BNode)
    assert t1.subject == t2.subject  # same-subject `;` chaining shares one blank node
    assert t1.predicate == RDF.type
    assert t1.object == _p("Notification")
    assert t2.predicate == _p("concerns")
    assert t2.object == Variable("x")


def test_full_worked_example_parses_five_rules():
    rs = parse_ruleset(WORKED_EXAMPLE_RULES)
    assert len(rs.rules) == 5
    assert rs.data == []
    assert rs.imports == []


def test_data_block_ground_triples_only():
    text = WORKED_EXAMPLE_PREFIXES + """
    DATA {
      :db :hasVulnerability :vuln1 .
      :vuln1 :severity 9.1 .
    }
    """
    rs = parse_ruleset(text)
    assert len(rs.data) == 1
    (block,) = rs.data
    assert block.triples == [
        TriplePattern(_p("db"), _p("hasVulnerability"), _p("vuln1")),
        TriplePattern(_p("vuln1"), _p("severity"), Literal("9.1", datatype=URIRef("http://www.w3.org/2001/XMLSchema#decimal"))),
    ]


def test_imports_decl():
    text = f"IMPORTS <{EX}other-ruleset>\n" + WORKED_EXAMPLE_PREFIXES + R1
    rs = parse_ruleset(text)
    assert rs.imports == [URIRef(EX + "other-ruleset")]


def test_where_data_and_assignment_element():
    text = WORKED_EXAMPLE_PREFIXES + "RULE { ?x :flag true } WHERE DATA { ?x :severity ?s . SET (?y := ?s + 1) . }"
    rs = parse_ruleset(text)
    (rule,) = rs.rules
    assert rule.data is True
    assert isinstance(rule.body[0], TriplePattern)
    assign = rule.body[1]
    assert isinstance(assign, AssignmentElement)
    assert assign.var == Variable("y")


def test_rule_with_explicit_id():
    text = WORKED_EXAMPLE_PREFIXES + f"RULE <{EX}r1> {{ ?x :p ?y }} WHERE {{ ?x :q ?y . }}"
    rs = parse_ruleset(text)
    (rule,) = rs.rules
    assert rule.id == _p("r1")


def test_negation_rejects_nested_negation():
    """Grammar production 23 (BodyBasicNotTriples ::= Filter) structurally
    forbids nested negation/assignment inside a NOT { } block - enforced
    by the grammar itself, not just documented."""
    text = WORKED_EXAMPLE_PREFIXES + "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { NOT { ?x :r ?y } } }"
    with pytest.raises(SRLParseError):
        parse_ruleset(text)


def test_negation_rejects_nested_assignment():
    text = WORKED_EXAMPLE_PREFIXES + "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { SET (?z := 1) } }"
    with pytest.raises(SRLParseError):
        parse_ruleset(text)


def test_malformed_text_raises_srl_parse_error():
    with pytest.raises(SRLParseError):
        parse_ruleset("this is not SRL text at all")


def test_comments_are_ignored():
    text = f"""
    PREFIX : <{EX}>
    # a leading comment
    RULE {{ ?x :p ?y }} # trailing comment
    WHERE {{ ?x :q ?y . }} # another
    """
    rs = parse_ruleset(text)
    assert len(rs.rules) == 1
