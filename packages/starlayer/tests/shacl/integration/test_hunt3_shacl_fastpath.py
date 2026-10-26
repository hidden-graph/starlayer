"""Regression tests for the third hunt's findings on GitHub issues #94 (SHACL native components) and #104 (SHACL
validator): the native fast path for triple-term graphs, ``sh:deactivated`` in ``apply_rules``/``evaluate``, list-valued
``sh:datatype``, triple terms as value nodes, module-level ``validate()`` keywords, shapes-graph modules, ``sh:nodeKind``
messages and invalid ``sh:pattern``."""

from __future__ import annotations

import pytest
from rdflib import RDF, Namespace
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, apply_rules, evaluate, validate

pytestmark = pytest.mark.shacl

SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("http://e/")
PREFIXES = (
    "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
)
TRIPLE_TERM_NOISE = " ex:z ex:r <<( ex:a ex:b ex:c )>> ."


def g(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PREFIXES + text, format="turtle12")


class TestNativeFastPathDefersToPyShacl:
    """The fast path for graphs holding a triple term checked one component and nothing else."""

    DEACTIVATED = "ex:S a sh:NodeShape ; sh:deactivated true ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:in (1 2) ] ."
    DATA = "ex:n a ex:T ; ex:p 5 ."

    def test_deactivated_shape_is_ignored_with_a_triple_term_in_the_data(self) -> None:
        assert validate(g(self.DATA), g(self.DEACTIVATED)).conforms is True
        assert validate(g(self.DATA + TRIPLE_TERM_NOISE), g(self.DEACTIVATED)).conforms is True

    def test_deactivated_property_shape_is_ignored(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:in (1 2) ; sh:deactivated true ] ."
        assert validate(g(self.DATA + TRIPLE_TERM_NOISE), g(shapes)).conforms is True

    def test_min_count_is_not_dropped(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:hasValue 1 ; sh:minCount 2 ] ."
        plain = validate(g("ex:a ex:p 1 ."), g(shapes)).conforms
        with_reifier = validate(g("ex:a ex:p 1 . ex:z ex:q ex:w ~ex:r ."), g(shapes)).conforms
        assert plain is False
        assert with_reifier is False

    def test_a_second_constraint_is_not_dropped(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:hasValue 1 ; sh:datatype xsd:integer ] ."
        assert validate(g("ex:a ex:p 'x', 1 ~ex:r ."), g(shapes)).conforms is False

    def test_property_shape_severity_is_reported(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:in (1 2) ; sh:severity sh:Warning ] ."
        result = validate(g(self.DATA + TRIPLE_TERM_NOISE), g(shapes))
        assert list(result.report_graph.objects(None, SH.resultSeverity)) == [SH.Warning]

    def test_report_of_the_fast_path_is_a_standard_report(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:in (1 2) ] ."
        result = validate(g(self.DATA + TRIPLE_TERM_NOISE), g(shapes))
        assert result.conforms is False
        report = result.report_graph
        assert len(list(report.subjects(RDF.type, SH.ValidationReport))) == 1
        assert len(list(report.subjects(RDF.type, SH.ValidationResult))) == 1
        assert list(report.objects(None, SH.resultSeverity)) == [SH.Violation]


class TestDeactivatedShapesInRulesAndEvaluate:
    def test_apply_rules_skips_the_rules_of_a_deactivated_shape(self) -> None:
        shapes = """ex:S a sh:NodeShape ; sh:deactivated true ; sh:targetNode ex:a ;
            sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:r ; sh:object 1 ] ."""
        result = apply_rules(g("ex:a ex:q 1 ."), shacl_graph=g(shapes), meta_shacl=False)
        assert list(result.inferred_graph) == []

    def test_apply_rules_still_runs_an_active_shape(self) -> None:
        shapes = """ex:S a sh:NodeShape ; sh:targetNode ex:a ;
            sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:r ; sh:object 1 ] ."""
        result = apply_rules(g("ex:a ex:q 1 ."), shacl_graph=g(shapes), meta_shacl=False)
        assert len(list(result.inferred_graph)) == 1

    def test_evaluate_ignores_a_deactivated_node_shape(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:deactivated true ; sh:targetNode ex:a ; sh:property [ sh:path ex:v ; sh:values 5 ] ."
        assert list(evaluate(g("ex:a ex:q 1 ."), shacl_graph=g(shapes))) == []

    def test_evaluate_ignores_a_deactivated_property_shape(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:q ; sh:deactivated true ] ."
        assert list(evaluate(g("ex:a ex:q 1 ."), shacl_graph=g(shapes))) == []

    def test_evaluate_still_returns_an_active_shape(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:q ] ."
        assert len(list(evaluate(g("ex:a ex:q 1 ."), shacl_graph=g(shapes)))) == 1


class TestListValuedDatatypeChecksWellFormedness:
    @pytest.mark.parametrize(
        ("datatypes", "value"),
        [
            ("(xsd:date xsd:gYear)", '"nope"^^xsd:date'),
            ("(xsd:integer xsd:string)", '"abc"^^xsd:integer'),
            ("(xsd:byte xsd:string)", '"300"^^xsd:byte'),
        ],
    )
    def test_ill_typed_literal_violates(self, datatypes: str, value: str) -> None:
        shapes = f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:datatype {datatypes} ] ."
        assert validate(g(f"ex:a ex:p {value} ."), g(shapes)).conforms is False

    def test_well_typed_literal_conforms(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:datatype (xsd:integer xsd:string) ] ."
        assert validate(g('ex:a ex:p 5, "x" .'), g(shapes)).conforms is True


class TestTripleTermValueNodes:
    DATA = "ex:a ex:p <<( ex:s ex:q 'hello' )>> ."

    @staticmethod
    def shapes(constraint: str) -> StarLayerGraph:
        return g(f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; {constraint} ] .")

    @pytest.mark.parametrize("constraint", ["sh:node [ sh:closed true ]", "sh:node [ sh:closed sh:ByTypes ]"])
    def test_a_triple_term_is_closed(self, constraint: str) -> None:
        assert validate(g(self.DATA), self.shapes(constraint)).conforms is True

    def test_a_triple_term_has_no_rdf_subject_property(self) -> None:
        constraint = "sh:node [ sh:property [ sh:path rdf:subject ; sh:minCount 1 ] ]"
        assert validate(g(self.DATA), self.shapes(constraint)).conforms is False

    @pytest.mark.parametrize(
        "constraint",
        [
            "sh:minLength 1",
            "sh:node [ sh:minLength 1 ]",
            "sh:or ( [ sh:minLength 1 ] )",
            "sh:and ( [ sh:minLength 1 ] )",
            "sh:node [ sh:maxLength 500 ]",
            'sh:not [ sh:not [ sh:pattern "." ] ]',
        ],
    )
    def test_string_constraints_fail_a_triple_term_however_nested(self, constraint: str) -> None:
        assert validate(g(self.DATA), self.shapes(constraint)).conforms is False

    def test_not_of_a_string_constraint_holds(self) -> None:
        assert validate(g(self.DATA), self.shapes("sh:not [ sh:minLength 1 ]")).conforms is True


MODULES = """
ex:S a sh:NodeShape ; sh:targetClass ex:Animal ; rdfs:isDefinedBy ex:M1 ; sh:property [ sh:path ex:z ; sh:minCount 0 ] .
ex:T a sh:NodeShape ; sh:targetNode ex:a ; rdfs:isDefinedBy ex:M2 ; sh:property [ sh:path ex:z ; sh:minCount 1 ] .
ex:M1 a sh:ShapesGraph . ex:M2 a sh:ShapesGraph .
"""


class TestModuleLevelValidateKeywords:
    def test_shapes_graph_resource_selects_one_module(self) -> None:
        data = "ex:a a ex:Dog ."
        assert validate(g(data), g(MODULES)).conforms is False
        assert validate(g(data), g(MODULES), shapes_graph_resource=EX.M1).conforms is True
        assert validate(g(data), g(MODULES), shapes_graph_resource=EX.M2).conforms is False
        schema = StarShaclSchema(shacl_graph=g(MODULES))
        assert schema.validate(g(data), shapes_graph_resource=EX.M1).conforms is True

    def test_shapes_graph_resource_without_a_shapes_graph_raises(self) -> None:
        with pytest.raises(ValueError, match="shapes_graph_resource"):
            validate(g("ex:a a ex:Dog ."), None, shapes_graph_resource=EX.M1)

    def test_unknown_keyword_raises(self) -> None:
        with pytest.raises(TypeError, match="bogus_option"):
            validate(g("ex:a a ex:Dog ."), g(MODULES), bogus_option=1)

    def test_unknown_keyword_raises_on_the_schema_method_too(self) -> None:
        with pytest.raises(TypeError, match="bogus_option"):
            StarShaclSchema(shacl_graph=g(MODULES)).validate(g("ex:a a ex:Dog ."), bogus_option=1)

    def test_known_pyshacl_keyword_is_accepted(self) -> None:
        assert validate(g("ex:a a ex:Dog ."), g(MODULES), shapes_graph_resource=EX.M1, abort_on_first=True).conforms


class TestModuleMemberWithNamedPropertyShapeOutsideTheModule:
    SHAPES = """
    ex:M1 a sh:ShapesGraph .
    ex:S a sh:NodeShape ; sh:targetNode ex:a ; rdfs:isDefinedBy ex:M1 ; sh:property ex:PS .
    ex:PS sh:path ex:z ; sh:minCount 1 .
    """

    def test_validation_of_the_module_does_not_crash(self) -> None:
        schema = StarShaclSchema(shacl_graph=g(self.SHAPES))
        assert schema.validate(g("ex:a a ex:Dog ."), shapes_graph_resource=EX.M1).conforms is True
        assert validate(g("ex:a a ex:Dog ."), g(self.SHAPES), shapes_graph_resource=EX.M1).conforms is True

    def test_the_whole_graph_still_checks_the_named_property_shape(self) -> None:
        assert validate(g("ex:a a ex:Dog ."), g(self.SHAPES)).conforms is False

    def test_a_member_named_property_shape_is_still_checked(self) -> None:
        shapes = self.SHAPES + "ex:PS rdfs:isDefinedBy ex:M1 ."
        schema = StarShaclSchema(shacl_graph=g(shapes))
        assert schema.validate(g("ex:a a ex:Dog ."), shapes_graph_resource=EX.M1).conforms is False


class TestNodeKindMessage:
    def test_single_kind_violation_has_pyshacls_message(self) -> None:
        shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:nodeKind sh:IRI ] ."
        result = validate(g("ex:n ex:p 'lit' ."), g(shapes))
        assert [str(m) for m in result.report_graph.objects(None, SH.resultMessage)] == ["Value is not of Node Kind sh:IRI"]

    def test_node_shape_violation_has_a_message(self) -> None:
        result = validate(g("ex:n ex:p 'lit' ."), g("ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:nodeKind sh:Literal ."))
        assert [str(m) for m in result.report_graph.objects(None, SH.resultMessage)] == [
            "Value is not of Node Kind sh:Literal"
        ]


class TestInvalidPattern:
    def test_an_invalid_regex_is_a_clean_error_naming_the_pattern(self) -> None:
        from pyshacl.errors import ConstraintLoadError

        shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:pattern "(" ] .'
        with pytest.raises(ConstraintLoadError, match="not a valid regular expression"):
            validate(g("ex:n ex:p 'a' ."), g(shapes))

    def test_a_valid_pattern_still_works(self) -> None:
        shapes = 'ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:pattern "^a+$" ] .'
        assert validate(g("ex:n ex:p 'aa' ."), g(shapes)).conforms is True
        assert validate(g("ex:n ex:p 'b' ."), g(shapes)).conforms is False
