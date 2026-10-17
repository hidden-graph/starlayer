"""Property paths in SRL rule bodies: only ``/`` and ``^`` are allowed (§5), and
they are expanded into plain triple patterns when the rule is built."""

from __future__ import annotations

import pytest
from rdflib import BNode, URIRef, Variable
from starlayer.graph import StarLayerGraph
from starlayer.sparql import srl
from starlayer.sparql.srl import SRLParseError, parse_ruleset

EX = "http://example.org/"
P = f"PREFIX ex: <{EX}>\n"


def _u(local):
    return URIRef(EX + local)


def _base():
    g = StarLayerGraph()
    g.parse(
        data=f"""@prefix ex: <{EX}> .
        ex:frontend ex:dependsOn ex:app . ex:app ex:dependsOn ex:db . ex:db ex:hasVulnerability ex:vuln1 .""",
        format="turtle12",
    )
    return g


def _inferred(rule_text):
    return {tuple(t) for t in parse_ruleset(P + rule_text).infer(_base())}


def test_a_sequence_path_is_expanded_into_two_triple_patterns_joined_by_a_blank_node():
    body = (
        parse_ruleset(
            P + "RULE { ?x ex:r ?v } WHERE { ?x ex:dependsOn/ex:hasVulnerability ?v }"
        )
        .rules[0]
        .body
    )
    assert len(body) == 2
    first, second = body
    assert first.subject == Variable("x") and first.predicate == _u("dependsOn")
    assert isinstance(first.object, BNode) and second.subject == first.object
    assert second.predicate == _u("hasVulnerability") and second.object == Variable("v")


def test_an_inverse_path_swaps_subject_and_object():
    body = (
        parse_ruleset(P + "RULE { ?v ex:r ?x } WHERE { ?v ^ex:hasVulnerability ?x }")
        .rules[0]
        .body
    )
    assert [(t.subject, t.predicate, t.object) for t in body] == [
        (Variable("x"), _u("hasVulnerability"), Variable("v"))
    ]


@pytest.mark.parametrize(
    "rule, expected",
    [
        (
            "RULE { ?x ex:r ?v } WHERE { ?x ex:dependsOn/ex:hasVulnerability ?v }",
            {(_u("app"), _u("r"), _u("vuln1"))},
        ),
        (
            "RULE { ?v ex:r ?x } WHERE { ?v ^ex:hasVulnerability ?x }",
            {(_u("vuln1"), _u("r"), _u("db"))},
        ),
        (
            "RULE { ?v ex:r ?x } WHERE { ?v ^(ex:dependsOn/ex:hasVulnerability) ?x }",
            {(_u("vuln1"), _u("r"), _u("app"))},
        ),
        (
            "RULE { ?x ex:r ?v } WHERE { ?x ex:dependsOn/ex:dependsOn/ex:hasVulnerability ?v }",
            {(_u("frontend"), _u("r"), _u("vuln1"))},
        ),
        (
            "RULE { ?x ex:r ?y } WHERE { ?x ex:dependsOn/^ex:dependsOn ?y }",
            {
                (_u("frontend"), _u("r"), _u("frontend")),
                (_u("app"), _u("r"), _u("app")),
            },
        ),
    ],
)
def test_paths_find_the_right_answers(rule, expected):
    assert _inferred(rule) == expected


def test_a_path_inside_not():
    # frontend depends on something but cannot reach a vulnerability in two steps; app can
    inferred = _inferred(
        "RULE { ?x ex:safe ex:yes } WHERE { ?x ex:dependsOn ?y . NOT { ?x ex:dependsOn/ex:hasVulnerability ?v } }"
    )
    assert inferred == {(_u("frontend"), _u("safe"), _u("yes"))}


@pytest.mark.parametrize(
    "path",
    [
        "ex:dependsOn|ex:hasVulnerability",
        "ex:dependsOn+",
        "ex:dependsOn*",
        "ex:dependsOn?",
        "!ex:dependsOn",
    ],
)
def test_any_other_path_operator_is_rejected_with_a_clear_message(path):
    with pytest.raises(SRLParseError, match="only the / and \\^ operators"):
        parse_ruleset(P + f"RULE {{ ?x ex:r ?v }} WHERE {{ ?x {path} ?v }}")


def test_a_path_is_not_allowed_in_a_rule_head():
    with pytest.raises(SRLParseError):
        parse_ruleset(P + "RULE { ?x ex:a/ex:b ?v } WHERE { ?x ex:dependsOn ?v }")


def test_a_rule_using_a_path_depends_on_the_rule_that_produces_its_predicates():
    plan = parse_ruleset(
        P
        + "RULE { ?x ex:hasVulnerability ?v } WHERE { ?x ex:inherits ?y . ?y ex:hasVulnerability ?v }\n"
        + "RULE { ?x ex:r ?v } WHERE { ?x ex:dependsOn/ex:hasVulnerability ?v }"
    ).plan()
    assert (1, 0, "open") in {(e.source, e.target, e.label) for e in plan.edges}


def test_a_path_rule_set_round_trips_through_text_and_rdf_in_its_expanded_form():
    rules = parse_ruleset(
        P + "RULE { ?x ex:r ?v } WHERE { ?x ex:dependsOn/ex:hasVulnerability ?v }"
    )
    text = srl.ruleset_to_text(rules)
    assert srl.ruleset_to_text(parse_ruleset(text)) == text
    graph, root = srl.ruleset_to_tree(rules)
    assert srl.srl_validate(graph)[0] is True
    assert srl.ruleset_to_text(srl.tree_to_ruleset(graph, root)) == text
