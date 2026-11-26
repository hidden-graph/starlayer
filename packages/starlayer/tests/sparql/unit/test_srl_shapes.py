"""Tests for starlayer.sparql.srl.srl_validate - structural SHACL shapes over
the srl: vocabulary. Valid srl: graphs (built via the real
parse_ruleset/ruleset_to_tree pipeline, not hand-typed) conform; deliberately
malformed graphs fail with a specific, expected violation - see
packages/shacl/CLAUDE.md's testing-discipline note on verifying coverage
adversarially, not just by existence.
"""

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph as Graph
from starlayer.graph.ordinals import ORD as TREE_ORD
from starlayer.graph.ordinals import _integer as ordinal
from starlayer.graph.ordinals import write_ordered
from starlayer.sparql.srl import (  # noqa: E402
    parse_ruleset,
    ruleset_to_tree,
    srl_validate,
)
from tests.support.terms import RDF, NamedNode, Namespace, lit

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
    outcome = srl_validate(g)
    conforms = outcome.conforms
    report_text = outcome.report_text
    assert conforms, report_text


def test_assignment_and_filter_roundtrip_conforms():
    text = """
    PREFIX : <http://example.org/>
    RULE { ?x :flag true } WHERE GROUND { ?x :severity ?s . SET (?y := ?s + 1) . FILTER(?y >= 9.0) }
    """
    rs = parse_ruleset(text)
    g, _root = ruleset_to_tree(rs)
    outcome = srl_validate(g)
    conforms = outcome.conforms
    report_text = outcome.report_text
    assert conforms, report_text


def _minimal_ruleset_graph():
    g = Graph()
    root = NamedNode("urn:x")
    g.add((root, RDF.type, SRL.RuleSet))
    return g, root


def _rule(g, root, *, body=(), head=(), flag=True, at=0):
    """A hand-built srl:Rule, ``at`` its position in the rule set; ``body`` and ``head`` are nodes put into the ordered sequences."""
    rule = ox.BlankNode()
    g.add((rule, RDF.type, SRL.Rule))
    if flag is not None:
        g.add((rule, SRL.ruleEvaldata, lit(flag)))
    write_ordered(g, rule, SRL.body, body)
    write_ordered(g, rule, SRL.head, head)
    g.add((root, SRL.rules, rule))
    g.add((rule, TREE_ORD, ordinal(at)))
    return rule


def _blank_triple(g, predicate=None):
    predicate = NamedNode("http://example.org/p") if predicate is None else predicate
    tp = ox.BlankNode()
    g.add((tp, RDF.type, SRL.TriplePattern))
    g.add((tp, SRL.subject, NamedNode("http://example.org/a")))
    g.add((tp, SRL.predicate, predicate))
    g.add((tp, SRL.object, lit("x")))
    return tp


def test_a_hand_built_rule_set_with_ordinals_conforms():
    """The baseline of the three negatives below: the same graph, made right, conforms."""
    g, root = _minimal_ruleset_graph()
    _rule(g, root, body=[_blank_triple(g)], head=[_blank_triple(g)])
    assert srl_validate(g).conforms, srl_validate(g).report_text


def test_rule_missing_body_is_rejected():
    """A hand-broken srl:Rule missing its required srl:ruleEvaldata flag is rejected: the shape enforces required properties, and the
    sequences (an empty one is no triples at all) are not what makes a rule incomplete."""
    g, root = _minimal_ruleset_graph()
    _rule(g, root, flag=None)
    outcome = srl_validate(g)
    assert outcome.conforms is False and "ruleEvaldata" in outcome.report_text


def test_triple_pattern_with_literal_predicate_is_rejected():
    """srl:predicate must be an IRI or Variable, never a Literal - a real
    RDF-1.2-shape correctness check, not just cardinality."""
    g, root = _minimal_ruleset_graph()
    _rule(g, root, body=[_blank_triple(g, lit("not-a-predicate"))])
    outcome = srl_validate(g)
    assert outcome.conforms is False and "srl:predicate" in outcome.report_text


def test_body_rejects_a_child_that_is_not_a_body_element():
    """srl:body holds srl:BodyElement: a typed child of another class is rejected."""
    g, root = _minimal_ruleset_graph()
    bogus = ox.BlankNode()
    g.add((bogus, RDF.type, NamedNode("urn:Bogus")))
    _rule(g, root, body=[bogus])
    outcome = srl_validate(g)
    assert outcome.conforms is False and "srl:body holds" in outcome.report_text


# --- srl_validate() on a parsed rule set: the shapes, then the §4.2 conditions ------------------------

_AGGREGATE_IN_SET = "PREFIX : <http://example.org/>\nRULE { ?x :n ?n } WHERE { ?x :p ?y . SET(?n := COUNT(?y)) }"


def test_the_shapes_reject_an_aggregate_in_set():
    """The shapes alone state it (``srl:AggregateInExpressionShape``); the run-time check in Python does not take part in ``srl_validate``."""
    from starlayer.sparql import srl

    report = srl.srl_validate(srl.ruleset_to_tree(srl.parse_ruleset(_AGGREGATE_IN_SET))[0])
    assert not report.conforms and "AggregateInExpressionShape" in report.report_text


def test_a_rule_set_that_breaks_the_conditions_loads_and_validate_reports_it():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(_AGGREGATE_IN_SET)
    assert len(ruleset.rules) == 1
    report = srl.srl_validate(srl.ruleset_to_tree(ruleset)[0])
    assert not report.conforms and "cannot contain an aggregate" in report.report_text


def test_a_valid_rule_set_passes_the_shape_check():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y . NOT { ?x :c ?y } }"
    )
    assert len(ruleset.rules) == 1


def test_validating_does_not_change_the_cached_shapes_graphs():
    from starlayer.sparql import srl

    shapes, ontology, _schema = srl._validation_graphs()
    before = (len(shapes), len(ontology))
    srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y }"
    )
    srl.parse_ruleset(
        "PREFIX : <http://example.org/>\nRULE { ?x :b ?y } WHERE { ?x :a ?y }"
    )
    assert (len(shapes), len(ontology)) == before


def test_validating_a_rule_set_does_not_validate_the_shapes_file_against_the_meta_shapes(monkeypatch):
    """The shipped shapes are checked once, by their own tests; every parse must not re-check them
    (the engine's ``meta_shacl`` preflight and starlayer's own meta-shape layer are both off for ``srl_validate``)."""
    from starlayer.shacl import meta_shapes
    from starlayer.shacl.engine import meta as engine_meta
    from starlayer.sparql.srl import srl_parse_to_tree, srl_validate

    called = []
    monkeypatch.setattr(engine_meta, "meta_validate", lambda *a, **k: called.append("meta_validate"))
    for name in ("sparql_query_problems", "meta_validate"):
        if hasattr(meta_shapes, name):
            monkeypatch.setattr(meta_shapes, name, lambda *a, _n=name, **k: called.append(_n))

    text = "PREFIX : <http://e/>\nRULE { ?x :p ?y } WHERE { ?x :q ?y }"
    parse_ruleset(text)
    graph, _root = srl_parse_to_tree(text)
    assert srl_validate(graph).conforms
    assert called == []


from starlayer.sparql import srl  # noqa: E402


class TestALiteralIsNotASubject:
    """A literal cannot be the subject of a triple, so a pattern or a head template with a constant literal subject can never match or
    produce one: the srl: shapes reject it (variables are encoded as literals of datatype spexpr:Variable and stay valid)."""

    H = "PREFIX ex: <http://example.org/> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"

    @pytest.mark.parametrize(
        "rule",
        [
            "RULE { 5 ex:p ?x } WHERE { ?x ex:age ?a }",
            'RULE { "x" ex:p ?x } WHERE { ?x ex:age ?a }',
            'RULE { "5"^^xsd:integer ex:p ?x } WHERE { ?x ex:age ?a }',
            'RULE { "x"@en ex:p ?x } WHERE { ?x ex:age ?a }',
            "RULE { ?x ex:p ?a } WHERE { ?x ex:age ?a . 5 ex:q ?x }",
            "DATA { 5 ex:p ex:o } RULE { ?x ex:p ?a } WHERE { ?x ex:age ?a }",
        ],
    )
    def test_a_constant_literal_subject_loads_and_validate_rejects_it(self, rule):
        ruleset = srl.parse_ruleset(self.H + rule)
        report = srl.srl_validate(srl.ruleset_to_tree(ruleset)[0])
        assert not report.conforms and "literal cannot be the subject" in report.report_text

    @pytest.mark.parametrize(
        "rule",
        [
            "RULE { ?a ex:p ?x } WHERE { ?x ex:age ?a }",
            "RULE { ex:s ex:p ?x . _:b ex:q ?x } WHERE { ?x ex:age ?a }",
            "RULE { ?x ex:p 5 . ?x ex:q \"x\" } WHERE { ?x ex:age ?a }",
            "RULE { ?x ex:p <<( ?x ex:q ex:r )>> } WHERE { ?x ex:age ?a }",
        ],
    )
    def test_variables_iris_blank_nodes_and_literal_objects_are_valid(self, rule):
        assert srl.parse_ruleset(self.H + rule).rules
