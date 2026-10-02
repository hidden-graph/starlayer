"""Round-trip tests for starlayer.sparql.srl_to_rdf/srl_from_rdf - Phase 2 of the
SRL implementation plan (see docs/functionality-overview.md): SRL text ->
srl_ast (via srl_grammar) -> srl: RDF -> srl_ast again, compared by value.

Each case parses real SRL text (reusing test_srl_grammar.py's own worked-
example fixtures where useful) rather than hand-building srl_ast trees
directly, so this also exercises the grammar and the encoder/decoder
together as a real pipeline, not just the encoder in isolation.
"""

from starlayer.sparql.srl_from_rdf import rdf_to_ruleset
from starlayer.sparql.srl_grammar import parse_ruleset
from starlayer.sparql.srl_to_rdf import ruleset_to_rdf

# The spec's own §6.6 worked example (R1-R5) - duplicated from
# test_srl_grammar.py rather than cross-imported, matching this project's
# existing convention of no test-module-to-test-module imports.
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
"""


def _roundtrip(text):
    rs = parse_ruleset(text)
    graph, root = ruleset_to_rdf(rs)
    rs2 = rdf_to_ruleset(graph, root)
    return rs, rs2, graph


def test_full_worked_example_roundtrips():
    rs, rs2, _ = _roundtrip(WORKED_EXAMPLE_RULES)
    assert rs == rs2


def test_data_block_roundtrips():
    text = """
    PREFIX : <http://example.org/>
    DATA { :db :hasVulnerability :vuln1 . :vuln1 :severity 9.1 . }
    """
    rs, rs2, _ = _roundtrip(text)
    assert rs == rs2
    assert len(rs2.data) == 1


def test_imports_roundtrips():
    text = "IMPORTS <http://example.org/other-ruleset>\nPREFIX : <http://example.org/>\nRULE { ?x :p ?y } WHERE { ?x :q ?y . }"
    rs, rs2, _ = _roundtrip(text)
    assert rs2.imports == rs.imports == [__import__("rdflib").URIRef("http://example.org/other-ruleset")]


def test_assignment_and_filter_expression_roundtrip():
    text = """
    PREFIX : <http://example.org/>
    RULE { ?x :flag true } WHERE DATA { ?x :severity ?s . SET (?y := ?s + 1) . FILTER(?y >= 9.0) }
    """
    rs, rs2, _ = _roundtrip(text)
    assert rs == rs2
    (rule,) = rs2.rules
    assert rule.data is True


def test_negation_with_data_flag_roundtrips():
    text = """
    PREFIX : <http://example.org/>
    RULE { ?x :safe true } WHERE { ?x :seen true . NOT DATA { ?x :flagged true . } }
    """
    rs, rs2, _ = _roundtrip(text)
    assert rs == rs2
    (rule,) = rs2.rules
    neg = rule.body[1]
    assert neg.data is True


def test_blank_node_identity_preserved_across_roundtrip():
    text = """
    PREFIX : <http://example.org/>
    RULE { [] a :Notification ; :concerns ?x } WHERE { ?x :status :criticallyExposed . }
    """
    rs, rs2, _ = _roundtrip(text)
    (rule,) = rs2.rules
    assert rule.head[0].subject == rule.head[1].subject


def test_root_typed_as_ruleset():
    from starlayer.sparql.srl_vocab import RULE_SET
    from rdflib import RDF

    rs = parse_ruleset("PREFIX : <http://example.org/>\nRULE { ?x :p ?y } WHERE { ?x :q ?y . }")
    graph, root = ruleset_to_rdf(rs)
    assert (root, RDF.type, RULE_SET) in graph


def test_rule_id_roundtrips():
    text = "PREFIX : <http://example.org/>\nRULE <http://example.org/r1> { ?x :p ?y } WHERE { ?x :q ?y . }"
    rs, rs2, _ = _roundtrip(text)
    assert rs2.rules[0].id == rs.rules[0].id
