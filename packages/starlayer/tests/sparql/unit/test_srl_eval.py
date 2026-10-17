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
from rdflib import RDF, BNode, Graph, URIRef, Variable
from starlayer.sparql.srl import parse_ruleset
from starlayer.sparql.srl_eval import (
    SRLImportsNotSupportedError,
    StratificationError,
    _build_dependency_graph,
    _stratify,
)

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
    edges = _build_dependency_graph(ruleset)
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
    assert [r._is_run_once for r in (r1, r2, r3, r4)] == [False, False, False, False]
    assert r5._is_run_once is True


def test_worked_example_stratification_matches_spec():
    """§6.6.2: "Stratum 0: general R1, R2, R3; no run-once rules.
    Stratum 1: run-once R5; general R4"."""
    _, ruleset = _worked_example()
    layers = _stratify(ruleset)
    idx = {id(r): i for i, r in enumerate(ruleset.rules)}
    layers_by_index = [
        (sorted(idx[id(r)] for r in once), sorted(idx[id(r)] for r in general))
        for once, general in layers
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
    gi = ruleset.infer(base)

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
    gi = ruleset.infer(base)
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
    gi = ruleset.infer(base)
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
        _stratify(ruleset)


def test_imports_rejected():
    text = f"IMPORTS <{EX}other>\nPREFIX : <{EX}>\nRULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y . }}"
    ruleset = parse_ruleset(text)
    with pytest.raises(SRLImportsNotSupportedError):
        ruleset.infer(Graph())


def test_filter_and_assignment_evaluate_correctly():
    base = Graph()
    base.parse(data=f"@prefix : <{EX}> . :a :severity 9.1 .", format="turtle")
    text = f"""
    PREFIX : <{EX}>
    RULE {{ ?x :bumped ?y }} WHERE {{ ?x :severity ?s . SET (?y := ?s + 1) . FILTER(?y > 9.0) }}
    """
    ruleset = parse_ruleset(text)
    gi = ruleset.infer(base)
    (triple,) = gi
    assert triple[0] == _p("a")
    assert float(triple[2].toPython()) == pytest.approx(10.1)


def test_query_matches_goal_pattern_against_base_and_inferred():
    base, ruleset = _worked_example()
    goal = ruleset.rules[2].head[0]  # ?x :status :criticallyExposed
    results = ruleset.query(base, goal)
    solutions = {r[Variable("x")] for r in results}
    assert solutions == {_p("db"), _p("app"), _p("frontend")}


class TestInferAndQueryInferenceParameter:
    """``inference=`` pre-entails base_graph (via StarLayerGraph.infer())
    before the rule set runs against it - a per-call parameter, not stored
    on RuleSet itself (see RuleSet.infer()'s own docstring for why)."""

    RULES = f"""
    PREFIX : <{EX}>
    RULE {{ ?x :flagged true }} WHERE {{ ?x :hasVulnerability ?v . ?v rdf:type :Vulnerability . }}
    """

    def _base_with_subclass_only(self):
        from starlayer.graph import StarLayerGraph

        base = StarLayerGraph()
        base.parse(
            data=f"""
            @prefix : <{EX}> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix rdf: <{RDF}> .
            :CriticalVuln rdfs:subClassOf :Vulnerability .
            :vuln2 rdf:type :CriticalVuln .
            :bob :hasVulnerability :vuln2 .
            """,
            format="turtle",
        )
        return base

    def test_infer_without_entailment_misses_the_subclass_fact(self):
        from starlayer.sparql.srl import parse_ruleset

        base = self._base_with_subclass_only()
        ruleset = parse_ruleset(f"PREFIX rdf: <{RDF}>\n" + self.RULES)
        gi = ruleset.infer(base)
        assert len(gi) == 0

    def test_infer_with_rdfs_entailment_sees_the_subclass_fact(self):
        from starlayer.graph.graph.entailment_regimes import ENTAILMENT
        from starlayer.sparql.srl import parse_ruleset

        base = self._base_with_subclass_only()
        ruleset = parse_ruleset(f"PREFIX rdf: <{RDF}>\n" + self.RULES)
        gi = ruleset.infer(base, inference=ENTAILMENT.RDFS)
        assert len(gi) == 1
        ((s, p, o),) = gi
        assert s == _p("bob") and p == _p("flagged") and bool(o.toPython()) is True

    def test_infer_entailment_does_not_mutate_the_callers_base_graph(self):
        from starlayer.graph.graph.entailment_regimes import ENTAILMENT
        from starlayer.sparql.srl import parse_ruleset

        base = self._base_with_subclass_only()
        before = len(base)
        ruleset = parse_ruleset(f"PREFIX rdf: <{RDF}>\n" + self.RULES)
        ruleset.infer(base, inference=ENTAILMENT.RDFS)
        assert len(base) == before

    def test_query_inference_parameter_sees_the_subclass_fact_too(self):
        from starlayer.graph.graph.entailment_regimes import ENTAILMENT
        from starlayer.sparql.srl import parse_ruleset

        base = self._base_with_subclass_only()
        ruleset = parse_ruleset(f"PREFIX rdf: <{RDF}>\n" + self.RULES)
        goal = ruleset.rules[0].head[0]  # ?x :flagged true
        rows = ruleset.query(base, goal, inference=ENTAILMENT.RDFS)
        assert {r[Variable("x")] for r in rows} == {_p("bob")}


class TestInferSchemaParameter:
    """``schema=`` validates the inferred result against a SHACL shape -
    either a bare shapes graph or an already-constructed StarShaclSchema
    (("allow both") - returns the inferred graph unchanged when omitted."""

    def _base_and_ruleset(self):
        base = Graph()
        base.parse(
            data=f"@prefix : <{EX}> . :alice :hasVulnerability :vuln1 .",
            format="turtle",
        )
        ruleset = parse_ruleset(
            f"PREFIX : <{EX}>\nRULE {{ ?x :exposedTo ?v }} WHERE {{ ?x :hasVulnerability ?v . }}"
        )
        return base, ruleset

    def _shapes(self):
        shapes = Graph()
        shapes.parse(
            data=f"""
            @prefix : <{EX}> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            :S a sh:NodeShape ; sh:targetSubjectsOf :exposedTo ;
              sh:property [ sh:path :exposedTo ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        return shapes

    def test_schema_omitted_returns_a_bare_graph_unchanged(self):
        base, ruleset = self._base_and_ruleset()
        result = ruleset.infer(base)
        assert isinstance(result, Graph)
        assert len(result) == 1

    def test_schema_as_bare_shapes_graph_returns_rules_result(self):
        from starlayer.shacl import RulesResult

        base, ruleset = self._base_and_ruleset()
        result = ruleset.infer(base, schema=self._shapes())
        assert isinstance(result, RulesResult)
        assert result.validation.conforms is True
        assert len(result.inferred_graph) == 1

    def test_schema_as_starshaclschema_instance_is_used_as_is(self):
        from starlayer.shacl import StarShaclSchema

        base, ruleset = self._base_and_ruleset()
        schema_obj = StarShaclSchema(shacl_graph=self._shapes())
        result = ruleset.infer(base, schema=schema_obj)
        assert result.validation.conforms is True

    def test_schema_detects_non_conformance(self):
        # RulesResult.inferred_graph is strictly the newly-inferred triples
        # (":alice :exposedTo :vuln1" only, same as _base_and_ruleset()'s
        # own rule) - the shape below targets subjects of :exposedTo
        # (discoverable from that alone) but also requires :severity,
        # which this rule never produces, so it's a genuine violation
        # detectable purely from the inferred output.
        base, ruleset = self._base_and_ruleset()
        shapes = Graph()
        shapes.parse(
            data=f"""
            @prefix : <{EX}> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            :S a sh:NodeShape ; sh:targetSubjectsOf :exposedTo ;
              sh:property [ sh:path :severity ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        result = ruleset.infer(base, schema=shapes)
        assert result.validation.conforms is False


def test_plan_shows_strata_and_dependency_edges_for_the_worked_example():
    """Same §6.6.2 example as above: stratum 0 holds general R1-R3, stratum 1 holds run-once R5 and general R4."""
    _, ruleset = _worked_example()
    plan = ruleset.plan()

    assert [
        (s.number, [r.index for r in s.run_once], [r.index for r in s.general])
        for s in plan.strata
    ] == [
        (0, [], [0, 1, 2]),
        (1, [4], [3]),
    ]
    # R4's NOT {} makes its dependency on R3 closed; open edges stay open
    labels = {(e.source, e.target): e.label for e in plan.edges}
    assert labels[(3, 2)] == "closed"
    assert labels[(2, 0)] == "open"
    # the edges are exactly what the private dependency graph computes
    assert len(plan.edges) == len(_build_dependency_graph(ruleset))
    # each planned rule carries its position and its rendered text
    assert plan.strata[1].general[0].text.startswith("RULE {")
    assert "safeToDeploy" in plan.strata[1].general[0].text


def test_plan_raises_stratification_error_without_running_anything():
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\nRULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y . NOT {{ ?x :p ?y }} }}"
    )
    with pytest.raises(StratificationError):
        ruleset.plan()


# --- SPARQL-RL 2026-10-14: base-graph matching (WHERE DATA / NOT DATA) ---------
# The spec's Examples 9 and 10 (kilometres from miles), as written. They need
# xsd:integer() of a decimal, which starlayer.graph's operator patches fix in rdflib.

_DEFAULT_VALUE_BASE = f"""
@prefix : <{EX}> .
:A :miles 5 ; :km 8 .
:B :miles 10 .
"""


def _default_value_base():
    base = Graph()
    base.parse(data=_DEFAULT_VALUE_BASE, format="turtle")
    return base


def _km_triples(graph):
    return {
        (str(s).rsplit("/", 1)[-1], int(o))
        for s, _p, o in graph.triples((None, _p("km"), None))
    }


def test_not_data_does_not_count_as_a_dependency_on_the_rules_own_output():
    """Spec Example 9: a default-value rule negates a pattern over the same predicate it
    produces. ``NOT DATA`` matches only the base graph, so it adds no dependency edge and
    the rule set stratifies (a plain ``NOT`` here is a StratificationError)."""
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        "RULE { ?x :km ?k } WHERE { ?x :miles ?m . NOT DATA { ?x :km ?old } SET(?k := xsd:integer(?m * 1.60934)) }"
    )
    assert ruleset.plan().edges == []
    assert _km_triples(ruleset.infer(_default_value_base())) == {
        ("B", 16)
    }  # A already has a km


def test_where_data_rule_has_no_dependencies_and_matches_only_the_base_graph():
    """Spec Example 10: every pattern of a ``WHERE DATA`` rule matches the base graph only."""
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        "RULE { ?x :km ?k } WHERE DATA { ?x :miles ?m . NOT { ?x :km ?old } SET(?k := xsd:integer(?m * 1.60934)) }"
    )
    assert ruleset.plan().edges == []
    assert _km_triples(ruleset.infer(_default_value_base())) == {("B", 16)}


def test_plain_not_over_the_rules_own_output_is_still_a_stratification_error():
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        "RULE { ?x :km ?k } WHERE { ?x :miles ?m . NOT { ?x :km ?old } SET(?k := xsd:integer(?m * 1.60934)) }"
    )
    with pytest.raises(StratificationError):
        ruleset.plan()


def test_a_positive_pattern_in_a_rule_with_not_data_is_still_a_dependency():
    """Only the NOT DATA body is exempt; the rest of the rule still depends on what it matches."""
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\n"
        "RULE { ?x :a ?y } WHERE { ?x :base ?y }\n"
        "RULE { ?x :b ?y } WHERE { ?x :a ?y . NOT DATA { ?x :b ?y } }"
    )
    assert {(e.source, e.target, e.label) for e in ruleset.plan().edges} == {
        (1, 0, "open")
    }


def test_blank_node_in_a_body_pattern_is_treated_as_a_variable_for_dependencies():
    ruleset = parse_ruleset(
        f"PREFIX : <{EX}>\n"
        "RULE { :a :p :b } WHERE { :s :q :t }\n"
        "RULE { ?x :r ?y } WHERE { ?x :q ?y . NOT { _:z :p :b } }"
    )
    assert {(e.source, e.target, e.label) for e in ruleset.plan().edges} == {
        (1, 0, "closed")
    }


def test_triple_term_in_a_pattern_depends_on_a_triple_term_template_with_variables():
    from starlayer.sparql.triple_term import TripleTermNode

    q = _p("q")
    producer = _ast_rule(
        head=[
            _tp(
                Variable("x"),
                _p("r"),
                TripleTermNode(
                    "TripleTerm",
                    subject=Variable("a"),
                    predicate=q,
                    object=Variable("b"),
                ),
            )
        ]
    )
    consumer = _ast_rule(
        head=[_tp(Variable("x"), _p("s"), Variable("y"))],
        body=[
            _tp(
                Variable("x"),
                _p("r"),
                TripleTermNode(
                    "TripleTerm", subject=_p("s1"), predicate=q, object=_p("o1")
                ),
            )
        ],
    )
    plan = _ast_ruleset([producer, consumer]).plan()
    assert {(e.source, e.target) for e in plan.edges} == {(1, 0)}


def test_head_with_a_triple_term_containing_a_variable_makes_a_run_once_rule():
    from starlayer.sparql.triple_term import TripleTermNode

    with_var = TripleTermNode(
        "TripleTerm", subject=Variable("a"), predicate=_p("q"), object=_p("o")
    )
    ground = TripleTermNode(
        "TripleTerm", subject=_p("s"), predicate=_p("q"), object=_p("o")
    )
    assert _ast_rule(head=[_tp(Variable("x"), _p("r"), with_var)])._is_run_once is True
    assert _ast_rule(head=[_tp(Variable("x"), _p("r"), ground)])._is_run_once is False


def _tp(s, p, o):
    from starlayer.sparql.srl import TriplePattern

    return TriplePattern(subject=s, predicate=p, object=o)


def _ast_rule(head, body=None):
    from starlayer.sparql import _srl_ast

    return _srl_ast._Rule(
        head=head,
        body=body
        if body is not None
        else [_tp(Variable("x"), _p("src"), Variable("y"))],
    )


def _ast_ruleset(rules):
    from starlayer.sparql.srl import RuleSet

    return RuleSet(rules=rules)
