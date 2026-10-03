"""Tests for starlayer.sparql.srl.ruleset_to_text - the inverse of
parse_ruleset, working directly on the parsed dataclass tree
(no RDF involved). Round-trip-focused: parse text -> render text -> parse
again -> compare the two RuleSets by value.
"""

from starlayer.sparql.srl import parse_ruleset, ruleset_to_text

WORKED_EXAMPLE_RULES = """
PREFIX ex: <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
RULE { ?x ex:exposedTo ?v } WHERE { ?x ex:hasVulnerability ?v . }
RULE { ?x ex:exposedTo ?v } WHERE { ?x ex:dependsOn ?y . ?y ex:exposedTo ?v . }
RULE { ?x ex:status ex:criticallyExposed }
WHERE { ?x ex:exposedTo ?v . ?v ex:severity ?s . FILTER(?s >= 9.0) }
RULE { ?x ex:status ex:safeToDeploy }
WHERE { ?x rdf:type ex:Component . NOT { ?x ex:status ex:criticallyExposed } }
RULE { [] rdf:type ex:Notification ; ex:concerns ?x }
WHERE { ?x ex:status ex:criticallyExposed . }
DATA { ex:db ex:hasVulnerability ex:vuln1 . }
"""


def _roundtrip(text):
    rs = parse_ruleset(text)
    rendered = ruleset_to_text(rs)
    rs2 = parse_ruleset(rendered)
    return rs, rendered, rs2


def test_full_worked_example_roundtrips_through_text():
    rs, _rendered, rs2 = _roundtrip(WORKED_EXAMPLE_RULES)
    assert rs == rs2


def test_simple_filter_expression_renders_and_reparses():
    """The exact shape that originally crashed rdflib's own
    _AlgebraTranslator (a bare, non-&&/|| comparison, never run through a
    full parseQuery/translateQuery pipeline) - see ssyn_to_text.py's
    _simplify_expr_immutable docstring for the full account."""
    text = "PREFIX ex: <http://example.org/>\nRULE { ?x ex:p true } WHERE { ?x ex:q ?s . FILTER(?s > 26) }"
    rs, rendered, rs2 = _roundtrip(text)
    assert "FILTER" in rendered
    assert rs == rs2


def test_conjunction_and_disjunction_render_and_reparse():
    text = (
        "PREFIX ex: <http://example.org/>\n"
        "RULE { ?x ex:p true } WHERE { ?x ex:q ?s . FILTER(?s > 20 && (?s < 30 || ?s = 25)) }"
    )
    rs, _rendered, rs2 = _roundtrip(text)
    assert rs == rs2


def test_assignment_expression_renders_and_reparses():
    text = "PREFIX ex: <http://example.org/>\nRULE { ?x ex:p ?y } WHERE { ?x ex:q ?s . SET (?y := ?s + 1) }"
    rs, rendered, rs2 = _roundtrip(text)
    assert "SET" in rendered
    assert rs == rs2


def test_negation_with_data_flag_renders_and_reparses():
    text = "PREFIX ex: <http://example.org/>\nRULE { ?x ex:p true } WHERE { ?x ex:q true . NOT DATA { ?x ex:r true } }"
    rs, rendered, rs2 = _roundtrip(text)
    assert "NOT DATA" in rendered
    assert rs == rs2


def test_where_data_rule_renders_and_reparses():
    text = "PREFIX ex: <http://example.org/>\nRULE { ?x ex:p ?y } WHERE DATA { ?x ex:q ?y . }"
    rs, rendered, rs2 = _roundtrip(text)
    assert "WHERE DATA" in rendered
    assert rs == rs2


def test_rule_id_renders_and_reparses():
    text = "PREFIX ex: <http://example.org/>\nRULE <http://example.org/r1> { ?x ex:p ?y } WHERE { ?x ex:q ?y . }"
    rs, rendered, rs2 = _roundtrip(text)
    assert rs.rules[0].id.n3() in rendered or str(rs.rules[0].id) in rendered
    assert rs == rs2


def test_imports_renders_and_reparses():
    text = "IMPORTS <http://example.org/other>\nPREFIX ex: <http://example.org/>\nRULE { ?x ex:p ?y } WHERE { ?x ex:q ?y . }"
    rs, rendered, rs2 = _roundtrip(text)
    assert "IMPORTS" in rendered
    assert rs == rs2


def test_no_rdf_involved_at_all(monkeypatch):
    """ruleset_to_text must not go through ruleset_to_tree/tree_to_ruleset
    (the RDF encode/decode pair) at all - confirm by breaking
    ruleset_to_tree and checking rendering still works."""
    import starlayer.sparql.srl as srl_module

    def _boom(*args, **kwargs):
        raise AssertionError("ruleset_to_text must not call ruleset_to_tree")

    monkeypatch.setattr(srl_module, "ruleset_to_tree", _boom)
    rs = parse_ruleset("PREFIX ex: <http://example.org/>\nRULE { ?x ex:p ?y } WHERE { ?x ex:q ?y . }")
    ruleset_to_text(rs)  # must not raise
