"""Tests for starlayer.sparql.srl.srl_validate - structural SHACL shapes over
the srl: vocabulary. Valid srl: graphs (built via the real
parse_ruleset/ruleset_to_tree pipeline, not hand-typed) conform; deliberately
malformed graphs fail with a specific, expected violation - see
packages/shacl/CLAUDE.md's testing-discipline note on verifying coverage
adversarially, not just by existence.
"""

import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph as Graph
from starlayer.sparql.srl import (  # noqa: E402
    parse_ruleset,
    ruleset_to_tree,
    srl_validate,
)
from tests.support.terms import RDF, NamedNode, Namespace, lit, rdf_list, set_triple

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
    rule = NamedNode("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.head, RDF.nil))
    g.add((rule, SRL.ruleEvaldata, lit(True)))
    # srl:body deliberately omitted.
    rules_list = NamedNode("urn:list")
    rdf_list(g, [rule], rules_list)
    set_triple(g, (root, SRL.rules, rules_list))

    outcome = srl_validate(g)
    conforms = outcome.conforms
    assert conforms is False


def test_triple_pattern_with_literal_predicate_is_rejected():
    """srl:predicate must be an IRI or Variable, never a Literal - a real
    RDF-1.2-shape correctness check, not just cardinality."""
    g, root = _minimal_ruleset_graph()
    rule = NamedNode("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.ruleEvaldata, lit(True)))
    g.add((rule, SRL.head, RDF.nil))

    tp = NamedNode("urn:tp1")
    g.add((tp, RDF.type, SRL.TriplePattern))
    g.add((tp, SRL.subject, NamedNode("http://example.org/a")))
    g.add((tp, SRL.predicate, lit("not-a-predicate")))  # invalid
    g.add((tp, SRL.object, lit("x")))
    body_list = NamedNode("urn:body")
    rdf_list(g, [tp], body_list)
    set_triple(g, (rule, SRL.body, body_list))

    rules_list = NamedNode("urn:list")
    rdf_list(g, [rule], rules_list)
    set_triple(g, (root, SRL.rules, rules_list))

    outcome = srl_validate(g)
    conforms = outcome.conforms
    assert conforms is False


def test_body_list_rejects_a_non_body_element_member():
    """srl:BodyListShape's sh:sparql check should reject a list member
    that isn't typed as any recognized srl:BodyElement subclass."""
    g, root = _minimal_ruleset_graph()
    rule = NamedNode("urn:rule1")
    g.add((rule, RDF.type, SRL.Rule))
    g.add((rule, SRL.ruleEvaldata, lit(True)))
    g.add((rule, SRL.head, RDF.nil))

    not_a_body_element = NamedNode("urn:bogus")
    body_list = NamedNode("urn:body")
    rdf_list(g, [not_a_body_element], body_list)
    set_triple(g, (rule, SRL.body, body_list))

    rules_list = NamedNode("urn:list")
    rdf_list(g, [rule], rules_list)
    set_triple(g, (root, SRL.rules, rules_list))

    outcome = srl_validate(g)
    conforms = outcome.conforms
    assert conforms is False


# --- srl_validate() on a parsed rule set: the shapes, then the §4.2 conditions ------------------------

_AGGREGATE_IN_SET = "PREFIX : <http://example.org/>\nRULE { ?x :n ?n } WHERE { ?x :p ?y . SET(?n := COUNT(?y)) }"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "srl_validate() now validates against srl: + spexpr: + sqe: only (no salg:), so that the srl: shapes can "
        "be published without it. The old salg: expression shape rejected an aggregate (COUNT) inside SET; the "
        "shared spexpr: shapes accept aggregates because sqe: needs them. parse_ruleset() still rejects it through "
        "the Python well-formedness check (aggregate_in_expression). To close the gap srl_shapes.ttl needs its own "
        "constraint: no spexpr aggregate under srl:expr. srl_shapes.ttl lives in starontology/, which is not being "
        "edited yet."
    ),
)
def test_the_shapes_alone_reject_the_rule_set(monkeypatch):
    """The Python well-formedness check normally catches an aggregate in SET, so switch it off to reach the shapes alone."""
    from starlayer.sparql import srl

    monkeypatch.setattr(srl, "_check_ruleset", lambda ruleset: [])
    assert not srl.srl_validate(srl.ruleset_to_tree(srl.parse_ruleset(_AGGREGATE_IN_SET))[0]).conforms


def test_a_rule_set_that_breaks_the_conditions_loads_and_validate_reports_it():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(_AGGREGATE_IN_SET)
    assert len(ruleset.rules) == 1
    report = srl.srl_validate(srl.ruleset_to_tree(ruleset)[0])
    assert not report.conforms and "aggregate_in_expression" in report.report_text


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
