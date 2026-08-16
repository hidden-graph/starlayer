import pytest
from rdflib import Literal, Namespace, URIRef
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starshacl import StarShaclValidator

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

pyshacl = pytest.importorskip("pyshacl")


def test_sparql_constraint_conforms_when_triple_term_present() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_says_triple_term.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_sparql_constraint_violates_when_triple_term_absent() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, Literal("something else")))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_says_triple_term.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.SPARQLConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_sparql_constraint_own_severity_overrides_shape_severity() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's sparql-001
    fixture: sh:sparql's own constraint node (the value of sh:sparql,
    distinct from the shape it's attached to) can carry its own
    sh:severity, per the spec's SPARQL-based Constraints section - the same
    way it already carries its own sh:message/sh:deactivated (both already
    correctly read by pySHACL). pySHACL's own SPARQLBasedConstraint never
    read sh:severity from that node, always reporting the shape's own
    severity (sh:Violation by default here, since the shape itself has no
    sh:severity override) regardless of what the constraint declares.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:sparql [
                sh:message "Cannot have a label" ;
                sh:severity sh:Warning ;
                sh:select \"\"\"
                    SELECT $this ?value
                    WHERE { $this <http://www.w3.org/2000/01/rdf-schema#label> ?value . }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:alice rdfs:label "should not have a label" .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_sparql_constraint_resolves_prefix_via_ambient_shapes_graph_declare() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's prefixes-002
    fixture: with no explicit sh:prefixes reference on the sh:sparql
    constraint at all, prefix resolution should still fall back to any
    sh:ShapesGraph-typed node's own sh:declare, found anywhere in the
    shapes graph (SHACL 1.2 Core). pySHACL's own
    SPARQLQueryHelper.collect_prefixes() only ever consults such ambient
    declares as an *addition* to an explicit sh:prefixes reference - if
    that reference is absent, it returns immediately, never falling back to
    ambient discovery at all. Deliberately does not also honor an
    owl:Ontology-declared prefix the way the already-covered
    explicit-sh:prefixes-reference case does - the fixture's own
    owl:Ontology declares the same prefix letter mapped to a *different*,
    wrong namespace as a deliberate distractor.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            ex:WrongDistractorOntology a owl:Ontology ;
              sh:declare [ sh:namespace "http://wrong.example.org/ns#"^^xsd:anyURI ; sh:prefix "test" ] .

            ex:SomeShapesGraph a sh:ShapesGraph ;
              sh:declare [ sh:namespace "http://test.example.org/ns#"^^xsd:anyURI ; sh:prefix "test" ] .

            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:sparql [
                sh:select "SELECT $this ?value WHERE { $this ex:flagged ?value . FILTER (?value = test:Bad) . }"
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:flagged <http://test.example.org/ns#Bad> .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.SPARQLConstraintComponent in {
        o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    }


def test_sparql_constraint_binds_value_per_property_value_node() -> None:
    # pySHACL's own sh:sparql (SPARQLConstraintComponent) only ever pre-binds
    # $this - it never auto-binds $value per value node the way this test's
    # name might suggest (confirmed via pyshacl.constraints.sparql.
    # sparql_based_constraints.SPARQLBasedConstraint._evaluate_sparql_constraint's
    # own comment: "we don't use value_nodes in the sparql constraint. All
    # queries are done on the corresponding focus node"). The fixture
    # (rdf12_sparql_value_predicate.ttl) instead derives ?value itself via
    # $PATH (pySHACL's own path-substitution mechanism) and a real WHERE-clause
    # join - covers a property-shape-scoped sh:sparql constraint that inspects
    # a triple-term value's predicate component via the PREDICATE() accessor,
    # rather than only matching against $this.
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, (EX.bob, EX.likes, EX.dave)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_value_predicate.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    violations = [
        s
        for s, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
        if o == SH.SPARQLConstraintComponent
    ]
    assert len(violations) == 1


def test_sparql_constraint_binds_value_conforms_when_all_predicates_match() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.dave)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_value_predicate.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_sparql_constraint_conforms_with_nested_multi_pattern_join() -> None:
    # Broader binding-shape coverage: a triple-term accessor (OBJECT())
    # feeding into a SECOND, unrelated join pattern (ex:age), not just a
    # single flat WHERE pattern - confirms StarLayerGraph.query() handles a
    # multi-pattern nested join, not only the simplest single-pattern case.
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.carol, EX.age, Literal(30)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_nested_join.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_sparql_constraint_violates_with_nested_multi_pattern_join() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))
    data.add((EX.carol, EX.age, Literal(10)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_sparql_nested_join.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.SPARQLConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_construct_rule_mints_new_triple_term_reification() -> None:
    data = StarLayerGraph()
    data.add((EX.bob, EX.knows, EX.carol))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rules_reify_new_triple_term.ttl"), format="turtle12")

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
    reifies_triples = list(result.data_graph.triples((EX.stmt1, RDF_REIFIES, None)))
    assert len(reifies_triples) == 1
    _, _, obj = reifies_triples[0]
    assert isinstance(obj, TripleTerm)
    assert obj == TripleTerm(EX.bob, EX.knows, EX.carol)


def test_sparql_constraint_resolves_prefix_via_sh_declare_not_turtle_prefix() -> None:
    """sh:declare/sh:prefixes (pyshacl/helper/sparql_query_helper.py::
    SPARQLQueryHelper.collect_prefixes()) is a separate mechanism from
    ordinary Turtle @prefix bindings - the SPARQL query text is just a
    string literal as far as Turtle parsing is concerned, so a prefix used
    only inside the query string must be resolved via sh:declare at query
    time, not via any @prefix in the surrounding shapes-graph Turtle. This
    shape deliberately declares no @prefix myex: at all.
    """
    data = StarLayerGraph()
    data.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Person ; ex:score 80 .
        ex:bob a ex:Person ; ex:score 20 .
    """, format="turtle")

    shapes = StarLayerGraph()
    shapes.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PrefixSet sh:declare [
            sh:prefix "myex" ;
            sh:namespace "http://example.org/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ;
        ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:sparql [
            sh:prefixes ex:PrefixSet ;
            sh:select "SELECT $this WHERE { $this myex:score ?s . FILTER (?s < 50) }" ;
          ] .
    """, format="turtle")

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert "ex:bob" in result.report_text
    assert "ex:alice" not in result.report_text.split("Focus Node:")[-1]
