"""Tests for starlayer.sparql.srl_eval - SRL §4.3 (Rule Dependency),
§4.4 (Stratification), and §6 (Rule Set Evaluation).

The centerpiece is test_worked_example_end_to_end below: it parses the
exact base graph and rules (R1-R5) from the spec's own §6.6 "Worked
Example" and asserts the exact dependency edges, exact stratification,
and exact inferred graph the spec itself states - about as strong a
correctness oracle as is available for a pre-Recommendation spec with no
independent reference implementation.
"""

import pytest
from rdflib import RDF, BNode, Graph, Literal, URIRef, Variable

from starlayer.sparql.srl_eval import (
    StratificationError,
    build_dependency_graph,
    srl_infer,
    is_run_once,
    srl_query,
    stratify,
)
from starlayer.sparql.srl import parse_ruleset

EX = "http://example.org/"


def _p(local):
    return URIRef(EX + local)


WORKED_EXAMPLE_BASE_TTL = f"""
@prefix : <{EX}> .
:frontend a :Component ; :dependsOn :app .
:app      a :Component ; :dependsOn :db , :logger .
:db       a :Component ; :hasVulnerability :vuln1 .
:logger   a :Component .
:vuln1    :severity 9.1 .
"""

WORKED_EXAMPLE_RULES = f"""
PREFIX : <{EX}>
PREFIX rdf: <{RDF}>
RULE {{ ?x :exposedTo ?v }} WHERE {{ ?x :hasVulnerability ?v . }}
RULE {{ ?x :exposedTo ?v }} WHERE {{ ?x :dependsOn ?y . ?y :exposedTo ?v . }}
RULE {{ ?x :status :criticallyExposed }}
WHERE {{ ?x :exposedTo ?v . ?v :severity ?s . FILTER(?s >= 9.0) }}
RULE {{ ?x :status :safeToDeploy }}
WHERE {{ ?x rdf:type :Component . NOT {{ ?x :status :criticallyExposed }} }}
RULE {{ [] rdf:type :Notification ; :concerns ?x }}
WHERE {{ ?x :status :criticallyExposed . }}
"""


def _worked_example():
    base = Graph()
    base.parse(data=WORKED_EXAMPLE_BASE_TTL, format="turtle")
    ruleset = parse_ruleset(WORKED_EXAMPLE_RULES)
    return base, ruleset


def _edge_labels_by_index(ruleset, edges):
    idx = {id(r): i for i, r in enumerate(ruleset.rules)}
    return {(idx[id(e.source)], idx[id(e.target)]): e.label for e in edges}


def test_worked_example_dependency_graph_matches_spec():
    """§4.3/6.6.1: "R2 → R1 (open), R2 → R2 (open), R3 → R1 (open),
    R3 → R2 (open), R4 → R3 (closed), R5 → R3 (closed)" - the spec's own
    stated dependency edges, by rule index (R1=0 .. R5=4)."""
    _, ruleset = _worked_example()
    edges = build_dependency_graph(ruleset)
    labels = _edge_labels_by_index(ruleset, edges)
    assert labels == {
        (1, 0): "open",  # R2 -> R1
        (1, 1): "open",  # R2 -> R2 (self, recursive)
        (2, 0): "open",  # R3 -> R1
        (2, 1): "open",  # R3 -> R2
        (3, 2): "closed",  # R4 -> R3
        (4, 2): "closed",  # R5 -> R3
    }


def test_worked_example_is_run_once_matches_spec():
    """§6.6.2: "R5 has a blank node in its head, so it is a run-once rule;
    no other rule has an assignment element or a blank node in its head."""
    _, ruleset = _worked_example()
    r1, r2, r3, r4, r5 = ruleset.rules
    assert [is_run_once(r) for r in (r1, r2, r3, r4)] == [False, False, False, False]
    assert is_run_once(r5) is True


def test_worked_example_stratification_matches_spec():
    """§6.6.2: "Stratum 0: general R1, R2, R3; no run-once rules.
    Stratum 1: run-once R5; general R4"."""
    _, ruleset = _worked_example()
    layers = stratify(ruleset)
    idx = {id(r): i for i, r in enumerate(ruleset.rules)}
    layers_by_index = [
        (sorted(idx[id(r)] for r in once), sorted(idx[id(r)] for r in general)) for once, general in layers
    ]
    assert layers_by_index == [([], [0, 1, 2]), ([4], [3])]


def test_worked_example_end_to_end():
    """§6.6.3's final inference graph, reproduced exactly - 13 triples:
    3 :exposedTo, 3 :status :criticallyExposed, 3x2 Notification triples
    (fresh blank node per critically-exposed component), 1 :safeToDeploy
    (only :logger, per the stratification-correctness property the spec
    itself calls out: :frontend must NOT get an incorrect early
    :safeToDeploy)."""
    base, ruleset = _worked_example()
    gi = srl_infer(base, ruleset)

    exposed_to = set(gi.triples((None, _p("exposedTo"), None)))
    assert exposed_to == {
        (_p("db"), _p("exposedTo"), _p("vuln1")),
        (_p("app"), _p("exposedTo"), _p("vuln1")),
        (_p("frontend"), _p("exposedTo"), _p("vuln1")),
    }

    critically_exposed = set(gi.triples((None, _p("status"), _p("criticallyExposed"))))
    assert critically_exposed == {
        (_p("db"), _p("status"), _p("criticallyExposed")),
        (_p("app"), _p("status"), _p("criticallyExposed")),
        (_p("frontend"), _p("status"), _p("criticallyExposed")),
    }

    # The crucial stratification-correctness property: only :logger is
    # safe, and it's the only safeToDeploy triple - not :frontend/:app/:db,
    # which an unstratified (single-pass) evaluation would have wrongly
    # produced (see the spec's own note in §6.6.3).
    safe_to_deploy = set(gi.triples((None, _p("status"), _p("safeToDeploy"))))
    assert safe_to_deploy == {(_p("logger"), _p("status"), _p("safeToDeploy"))}

    notifications = list(gi.subjects(RDF.type, _p("Notification")))
    assert len(notifications) == 3
    assert all(isinstance(n, BNode) for n in notifications)
    assert len(set(notifications)) == 3  # a distinct fresh blank node per solution
    concerns = {gi.value(n, _p("concerns")) for n in notifications}
    assert concerns == {_p("db"), _p("app"), _p("frontend")}

    assert len(gi) == 13


def test_infer_output_never_includes_base_graph_triples():
    base, ruleset = _worked_example()
    gi = srl_infer(base, ruleset)
    assert not any(t in base for t in gi)


def test_where_data_matches_only_the_original_base_graph():
    """A surprising, directly spec-confirmed subtlety (§6.5's own
    pseudocode: every `evalRule(R, GE, G0)` call passes `G0`, the
    *original* base graph, as `evalRule`'s own `GD` parameter - not the
    algorithm's separate `GD = G0 ∪ D` variable despite the name
    collision, and not the accumulating evaluation graph `GE` either).
    A `WHERE DATA {...}`-scoped rule can therefore only ever match the
    original base graph - not the rule set's own top-level `DATA {}`
    blocks, and not anything any rule (including itself) infers. The
    `DATA {}` block's own triple still appears in the output graph
    (`GI = {t in D | t not in G0}` unconditionally seeds it in) - it's
    just invisible to `WHERE DATA` rule *matching* specifically.
    """
    base = Graph()
    base.parse(data=f"@prefix : <{EX}> . :a :seed :b .", format="turtle")
    text = f"""
    PREFIX : <{EX}>
    DATA {{ :b :seed :c . }}
    RULE {{ ?x :derived ?y }} WHERE DATA {{ ?x :seed ?y . }}
    """
    ruleset = parse_ruleset(text)
    gi = srl_infer(base, ruleset)
    # The DATA block's own fact is present (seeded directly into GI)...
    assert (_p("b"), _p("seed"), _p("c")) in gi
    # ...but the rule only ever derived from the *original* base graph,
    # never from the DATA block it nominally matches against.
    derived = set(gi.triples((None, _p("derived"), None)))
    assert derived == {(_p("a"), _p("derived"), _p("b"))}


def test_stratification_error_on_closed_self_cycle():
    """A rule whose own head feeds a negation in its own body (a closed
    self-dependency) violates §4.4.1's Stratification Condition."""
    text = f"""
    PREFIX : <{EX}>
    RULE {{ ?x :p true }} WHERE {{ ?x :q true . NOT {{ ?x :p true }} }}
    """
    ruleset = parse_ruleset(text)
    with pytest.raises(StratificationError):
        stratify(ruleset)


def test_imports_rejected():
    from starlayer.sparql.srl_eval import SRLImportsNotSupportedError

    text = f"IMPORTS <{EX}other>\nPREFIX : <{EX}>\nRULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y . }}"
    ruleset = parse_ruleset(text)
    with pytest.raises(SRLImportsNotSupportedError):
        srl_infer(Graph(), ruleset)


def test_filter_and_assignment_evaluate_correctly():
    base = Graph()
    base.parse(data=f"@prefix : <{EX}> . :a :severity 9.1 .", format="turtle")
    text = f"""
    PREFIX : <{EX}>
    RULE {{ ?x :bumped ?y }} WHERE {{ ?x :severity ?s . SET (?y := ?s + 1) . FILTER(?y > 9.0) }}
    """
    ruleset = parse_ruleset(text)
    gi = srl_infer(base, ruleset)
    (triple,) = gi
    assert triple[0] == _p("a")
    assert float(triple[2].toPython()) == pytest.approx(10.1)


def test_query_matches_goal_pattern_against_base_and_inferred():
    base, ruleset = _worked_example()
    goal = ruleset.rules[2].head[0]  # ?x :status :criticallyExposed
    results = srl_query(base, ruleset, goal)
    solutions = {r[Variable("x")] for r in results}
    assert solutions == {_p("db"), _p("app"), _p("frontend")}
