"""Tests for starlayer.sparql.srl.srl_validate - structural SHACL shapes over
the srl: vocabulary. Valid srl: graphs (built via the real
parse_ruleset/ruleset_to_tree pipeline, not hand-typed) conform; deliberately
malformed graphs fail with a specific, expected violation - see
packages/shacl/CLAUDE.md's testing-discipline note on verifying coverage
adversarially, not just by existence.
"""

import pytest
from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

pyshacl = pytest.importorskip("pyshacl")

from starlayer.sparql.srl import (  # noqa: E402
    parse_ruleset,
    ruleset_to_tree,
    srl_validate,
)

SRL = Namespace("https://github.com/hidden-graph/starlayer/ns/sparql/srl#")

WORKED_EXAMPLE_RULES = """
PREFIX : <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
RULE { ?x :exposedTo ?v } WHERE { ?x :hasVulnerability ?v . }
RULE { ?x :exposedTo ?v } WHERE { ?x :dependsOn ?y . ?y :exposedTo ?v . }
RULE { ?x :status :criticallyExposed }
WHERE { ?x :exposedTo ?v . ?v :severity ?s . FILTER(?s >= 9.0) }
RULE { ?x :status :safeToDeploy }
WHERE { ?x rdf:type :Component . NOT { ?x :status :criticallyExposed } }
RULE { [] rdf:type :Notification ; :concerns ?x }
WHERE { ?x :status :criticallyExposed . }
DATA { :db :hasVulnerability :vuln1 . }
"""


def test_worked_example_conforms():
    rs = parse_ruleset(WORKED_EXAMPLE_RULES)
    g, _root = ruleset_to_tree(rs)
    conforms, _report_graph, report_text = srl_validate(g)
    assert conforms, report_text


def test_assignment_and_filter_roundtrip_conforms():
    text = """
    PREFIX : <http://example.org/>
    RULE { ?x :flag true } WHERE DATA { ?x :severity ?s . SET (?y := ?s + 1) . FILTER(?y >= 9.0) }
    """
    rs = parse_ruleset(text)
    g, _root = ruleset_to_tree(rs)
    conforms, _report_graph, report_text = srl_validate(g)
    assert conforms, report_text


def _minimal_ruleset_graph():
    g = Graph()
    root = URIRef("urn:x")
    g.add((root, RDF.type, SRL.RuleSet))
    g.add((root, SRL.rules, RDF.nil))
    g.add((root, SRL.data, RDF.nil))
    g.add((root, SRL.imports, RDF.nil))
    return g, root


def test_rule_missing_body_is_rejected():
    """A hand-broken srl:Rule missing its required srl:body - confirms
    the shape actually enforces required properties, not just that a
    complete graph happens to pass (packages/shacl/CLAUDE.md's own
    adversarial-verification discipline)."""
    g, root = _minimal_ruleset_graph()
    rule = URIRef("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.head, RDF.nil))
    g.add((rule, SRL.ruleEvaldata, Literal(True)))
    # srl:body deliberately omitted.
    rules_list = URIRef("urn:list")
    Collection(g, rules_list, [rule])
    g.set((root, SRL.rules, rules_list))

    conforms, _report_graph, _report_text = srl_validate(g)
    assert conforms is False


def test_triple_pattern_with_literal_predicate_is_rejected():
    """srl:predicate must be an IRI or Variable, never a Literal - a real
    RDF-1.2-shape correctness check, not just cardinality."""
    g, root = _minimal_ruleset_graph()
    rule = URIRef("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.ruleEvaldata, Literal(True)))
    g.add((rule, SRL.head, RDF.nil))

    tp = URIRef("urn:tp1")
    g.add((tp, RDF.type, SRL.TriplePattern))
    g.add((tp, SRL.subject, URIRef("http://example.org/a")))
    g.add((tp, SRL.predicate, Literal("not-a-predicate")))  # invalid
    g.add((tp, SRL.object, Literal("x")))
    body_list = URIRef("urn:body")
    Collection(g, body_list, [tp])
    g.set((rule, SRL.body, body_list))

    rules_list = URIRef("urn:list")
    Collection(g, rules_list, [rule])
    g.set((root, SRL.rules, rules_list))

    conforms, _report_graph, _report_text = srl_validate(g)
    assert conforms is False


def test_body_list_rejects_a_non_body_element_member():
    """srl:BodyListShape's sh:sparql check should reject a list member
    that isn't typed as any recognized srl:BodyElement subclass."""
    g, root = _minimal_ruleset_graph()
    rule = URIRef("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.ruleEvaldata, Literal(True)))
    g.add((rule, SRL.head, RDF.nil))

    not_a_body_element = URIRef("urn:bogus")
    body_list = URIRef("urn:body")
    Collection(g, body_list, [not_a_body_element])
    g.set((rule, SRL.body, body_list))

    rules_list = URIRef("urn:list")
    Collection(g, rules_list, [rule])
    g.set((root, SRL.rules, rules_list))

    conforms, _report_graph, _report_text = srl_validate(g)
    assert conforms is False


# --- parse_ruleset() also validates against the shapes ------------------------

_AGGREGATE_IN_SET = "PREFIX : <http://example.org/>\nRULE { ?x :n ?n } WHERE { ?x :p ?y . SET(?n := COUNT(?y)) }"


def test_parse_ruleset_raises_when_the_rule_set_does_not_conform_to_the_shapes(
    monkeypatch,
):
    """The Python well-formedness check normally catches an aggregate in SET first, so switch
    it off to reach the shapes, which reject the same rule set."""
    from starlayer.sparql import srl

    monkeypatch.setattr(srl, "_check_ruleset", lambda ruleset: [])
    with pytest.raises(srl.SRLParseError, match="does not conform to the srl: shapes"):
        srl.parse_ruleset(_AGGREGATE_IN_SET)


def test_validate_false_skips_the_shape_check(monkeypatch):
    from starlayer.sparql import srl

    monkeypatch.setattr(srl, "_check_ruleset", lambda ruleset: [])
    assert len(srl.parse_ruleset(_AGGREGATE_IN_SET, validate=False).rules) == 1


def test_a_valid_rule_set_passes_the_shape_check_at_parse_time():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y . NOT { ?x :c ?y } }"
    )
    assert len(ruleset.rules) == 1


def test_validating_does_not_change_the_cached_shapes_graphs():
    from starlayer.sparql import srl

    shapes, ontology = srl._validation_graphs()
    before = (len(shapes), len(ontology))
    srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y }"
    )
    srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y }"
    )
    assert (len(shapes), len(ontology)) == before
