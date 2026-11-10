"""Per-constraint sh:severity/sh:message/sh:deactivated via RDF-1.2 inline
reification annotation (SHACL 1.2 Core) - distinct from, and finer-grained
than, a shape's own sh:severity/sh:message/sh:deactivated. Found via the W3C
SHACL 1.2 test suite's severity-003/message-002/deactivated-003 fixtures;
generalised to every constraint component for GitHub issue #201.
"""

from pathlib import Path
from typing import Any

import pytest
from rdflib import RDF, Literal, Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def test_datatype_annotation_severity_overrides_shape_default() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:datatype xsd:integer {| sh:severity sh:Warning |} .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))  # focus node itself is the target; no extra data needed

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_datatype_annotation_deactivated_skips_that_constraint() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:datatype xsd:boolean {| sh:deactivated true |} .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_property_reference_annotation_deactivated_skips_only_that_reference() -> None:
    """Deactivates one specific sh:property *reference*, not the referenced
    shape's own constraints generically - a shape referenced via a second,
    non-annotated sh:property elsewhere would still be checked there.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property ex:RequiresProperty {| sh:deactivated true |} .
            ex:RequiresProperty a sh:PropertyShape ;
              sh:path ex:requiredProp ;
              sh:minCount 1 .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))  # no ex:requiredProp at all

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_property_reference_without_annotation_still_conforms_normally() -> None:
    # Confirms the annotation-filtering doesn't accidentally suppress a
    # genuinely non-deactivated sh:property reference.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:property ex:RequiresProperty .
            ex:RequiresProperty a sh:PropertyShape ;
              sh:path ex:requiredProp ;
              sh:minCount 1 .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.alice))

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert SH.MinCountConstraintComponent in {
        o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    }


# --- GitHub issue #201: every constraint component, both shape kinds ---------------------------------------------

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
"""

# The data of the issue's repro matrix.
BASE_DATA = PREFIXES + """
ex:a a ex:P ; ex:v "text", ex:other .
ex:other a ex:Dog .
"""

COMMON_SHAPES = """
ex:CatShape a sh:NodeShape ; sh:class ex:Cat .
ex:IRIShape a sh:NodeShape ; sh:nodeKind sh:IRI .
ex:ReifyShape a sh:NodeShape ; sh:property [ sh:path ex:pb ; sh:in ( true ) ] .
"""

# id -> (constraint text with {A} where the annotation goes, extra data, where it is written: "ps" or "node")
PS, NODE = "ps", "node"
CASES: dict[str, tuple[str, str, str]] = {
    "class": ("sh:class ex:Cat {A}", "", PS),
    "datatype": ("sh:datatype xsd:integer {A}", "", PS),
    "nodeKind": ("sh:nodeKind sh:IRI {A}", "", PS),
    "minCount": ("sh:minCount 3 {A}", "", PS),
    "maxCount": ("sh:maxCount 1 {A}", "", PS),
    "minLength": ("sh:minLength 10 {A}", "", PS),
    "maxLength": ("sh:maxLength 2 {A}", "", PS),
    "pattern": ('sh:pattern "^[0-9]+$" {A}', "", PS),
    "languageIn": ('sh:languageIn ( "en" ) {A}', "", PS),
    "uniqueLang": ("sh:uniqueLang true {A}", 'ex:a ex:v "x"@en, "y"@en .', PS),
    "in": ('sh:in ( "a" "b" ) {A}', "", PS),
    "hasValue": ('sh:hasValue "zzz" {A}', "", PS),
    "equals": ("sh:equals ex:w {A}", 'ex:a ex:w "text" .', PS),
    "disjoint": ("sh:disjoint ex:w {A}", 'ex:a ex:w "text" .', PS),
    "lessThan": ("sh:lessThan ex:w {A}", "ex:a ex:w 5 .", PS),
    "lessThanOrEquals": ("sh:lessThanOrEquals ex:w {A}", "ex:a ex:w 5 .", PS),
    "minInclusive": ("sh:minInclusive 5 {A}", "", PS),
    "minExclusive": ("sh:minExclusive 5 {A}", "", PS),
    "maxInclusive": ("sh:maxInclusive 5 {A}", "", PS),
    "maxExclusive": ("sh:maxExclusive 5 {A}", "", PS),
    "node": ("sh:node ex:CatShape {A}", "", PS),
    "not": ("sh:not [ sh:nodeKind sh:Literal ] {A}", "", PS),
    "and": ("sh:and ( [ sh:class ex:Cat ] [ sh:class ex:Dog ] ) {A}", "", PS),
    "or": ("sh:or ( [ sh:class ex:Cat ] [ sh:datatype xsd:integer ] ) {A}", "", PS),
    "xone": ("sh:xone ( [ sh:nodeKind sh:Literal ] [ sh:datatype xsd:string ] ) {A}", "", PS),
    "qualifiedMinCount": ("sh:qualifiedValueShape [ sh:class ex:Dog ] ; sh:qualifiedMinCount 2 {A}", "", PS),
    "qualifiedMaxCount": ("sh:qualifiedValueShape [ sh:class ex:Dog ] ; sh:qualifiedMaxCount 0 {A}", "", PS),
    "qualifiedValueShape": ("sh:qualifiedValueShape [ sh:class ex:Dog ] {A} ; sh:qualifiedMaxCount 0", "", PS),
    "sparql": (
        'sh:sparql [ sh:select """SELECT $this ?value WHERE { $this <http://example.org/v> ?value . }""" ] {A}',
        "",
        PS,
    ),
    "someValue": ("sh:someValue ex:CatShape {A}", "", PS),
    "rootClass": ("sh:rootClass ex:Cat {A}", "", PS),
    "subsetOf": ("sh:subsetOf ex:w {A}", 'ex:a ex:w "other" .', PS),
    "reifierShape": ("sh:reifierShape ex:ReifyShape {A}", 'ex:a ex:v "text" {| ex:pb false |} .', PS),
    "memberShape": ("sh:memberShape ex:IRIShape {A}", 'ex:a ex:v ( "lit" ) .', PS),
    "minListLength": ("sh:minListLength 1 {A}", "ex:a ex:v rdf:nil .", PS),
    "maxListLength": ("sh:maxListLength 0 {A}", 'ex:a ex:v ( "a" ) .', PS),
    "uniqueMembers": ("sh:uniqueMembers true {A}", 'ex:a ex:v ( "a" "a" ) .', PS),
    "singleLine": ("sh:singleLine true {A}", 'ex:a ex:v "a\\nb" .', PS),
    "uniqueValuesFor": ("sh:uniqueValuesFor ex:id {A}", 'ex:a ex:id "D" . ex:b a ex:P ; ex:id "D" .', NODE),
    "closed": ("sh:closed true {A}", "", NODE),
    # the same constraints on a node shape
    "node-level class": ("sh:class ex:Cat {A}", "", NODE),
    "node-level minLength": ("sh:minLength 30 {A}", "", NODE),
    "node-level nodeKind": ("sh:nodeKind sh:Literal {A}", "", NODE),
    "node-level and": ("sh:and ( [ sh:class ex:Cat ] ) {A}", "", NODE),
}


def _shapes(case: str, annotation: str, shape_extra: str = "") -> str:
    constraint, _, where = CASES[case]
    text = constraint.replace("{A}", annotation)
    if where == PS:
        body = f"ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .\nex:PS a sh:PropertyShape ; sh:path ex:v ; {text} {shape_extra} ."
    else:
        body = f"ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; {text} {shape_extra} ."
        if case == "closed":
            body += "\nex:Shape sh:property ex:PS .\nex:PS a sh:PropertyShape ; sh:path ex:v ."
    return PREFIXES + COMMON_SHAPES + body


def _run(shapes: str, data: str = BASE_DATA, extra_data: str = "") -> Any:
    sg = StarLayerGraph()
    sg.parse(data=shapes, format="turtle12")
    dg = StarLayerGraph()
    dg.parse(data=data + "\n" + extra_data, format="turtle12")
    return StarShaclSchema(shacl_graph=sg).validate(data_graph=dg, meta_shacl=False)


def _values(result: Any, predicate: Any) -> list[Any]:
    """The values of ``predicate`` on the top-level results (a nested sh:detail result belongs to the referenced shape)."""
    nested = set(result.report_graph.objects(None, SH.detail))
    return sorted(o for s, _, o in result.report_graph.triples((None, predicate, None)) if s not in nested)


def _case_run(case: str, annotation: str, shape_extra: str = "") -> Any:
    return _run(_shapes(case, annotation, shape_extra), extra_data=CASES[case][1])


@pytest.mark.parametrize("case", CASES)
def test_plain_constraint_violates_with_default_severity(case: str) -> None:
    result = _case_run(case, "")
    assert result.conforms is False, case
    assert set(_values(result, SH.resultSeverity)) == {SH.Violation}


@pytest.mark.parametrize("case", CASES)
def test_annotation_severity_applies_to_that_constraint(case: str) -> None:
    result = _case_run(case, "{| sh:severity sh:Info |}")
    assert result.conforms is False, case  # sh:Info is a result, so it still does not conform
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}
    assert "Info" in result.report_text or "sh:Info" in result.report_text


@pytest.mark.parametrize("case", CASES)
def test_annotation_message_replaces_default_and_shape_message(case: str) -> None:
    result = _case_run(case, '{| sh:message "custom message" |}', shape_extra='; sh:message "shape message"')
    assert set(_values(result, SH.resultMessage)) == {Literal("custom message")}, case
    assert "custom message" in result.report_text
    assert "shape message" not in result.report_text


@pytest.mark.parametrize("case", CASES)
def test_annotation_deactivated_skips_that_constraint(case: str) -> None:
    result = _case_run(case, "{| sh:deactivated true |}")
    assert result.conforms is True, case


@pytest.mark.parametrize("case", CASES)
def test_annotation_deactivated_false_does_not_deactivate(case: str) -> None:
    result = _case_run(case, "{| sh:deactivated false |}")
    assert result.conforms is False, case
    assert set(_values(result, SH.resultSeverity)) == {SH.Violation}


@pytest.mark.parametrize("case", ["class", "minCount", "pattern", "node", "qualifiedMinCount", "sparql", "closed"])
def test_unannotated_constraint_keeps_shape_level_severity_and_message(case: str) -> None:
    """The shape's own sh:severity / sh:message still apply when the constraint has no annotation."""
    result = _case_run(case, "", shape_extra="; sh:severity sh:Info ; sh:message \"shape message\"")
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}
    assert set(_values(result, SH.resultMessage)) == {Literal("shape message")}


def test_annotation_changes_only_its_own_constraint() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ; sh:severity sh:Info ; sh:message "shape message" ;
          sh:class ex:Cat {| sh:severity sh:Warning ; sh:message "cat message" |} ;
          sh:minCount 3 ;
          sh:maxLength 2 {| sh:deactivated true |} .
    """
    result = _run(shapes)
    by_component = {}
    for r in result.report_graph.subjects(RDF.type, SH.ValidationResult):
        component = result.report_graph.value(r, SH.sourceConstraintComponent)
        by_component.setdefault(component, set()).add(
            (result.report_graph.value(r, SH.resultSeverity), str(result.report_graph.value(r, SH.resultMessage)))
        )
    assert by_component == {
        SH.ClassConstraintComponent: {(SH.Warning, "cat message")},
        SH.MinCountConstraintComponent: {(SH.Info, "shape message")},
    }


def test_each_value_of_one_parameter_has_its_own_annotation() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:class ex:Cat {| sh:severity sh:Warning ; sh:message "cat" |} , ex:Dog {| sh:severity sh:Info ; sh:message "dog" |} .
    """
    result = _run(shapes)
    graph = result.report_graph
    seen = sorted(
        (str(graph.value(r, SH.resultMessage)), graph.value(r, SH.resultSeverity), str(graph.value(r, SH.value)))
        for r in graph.subjects(RDF.type, SH.ValidationResult)
    )
    assert seen == [
        ("cat", SH.Warning, "http://example.org/other"),
        ("cat", SH.Warning, "text"),
        ("dog", SH.Info, "text"),
    ]


def test_deactivating_one_value_leaves_the_other_value_running() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:class ex:Cat {| sh:deactivated true |} , ex:Dog .
    """
    result = _run(shapes)
    graph = result.report_graph
    values = [str(graph.value(r, SH.value)) for r in graph.subjects(RDF.type, SH.ValidationResult)]
    assert values == ["text"]  # only ex:Dog is checked, and only "text" is not a Dog


def test_language_tagged_annotation_messages_are_all_carried() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:minCount 3 {| sh:message "too few"@en , "zu wenige"@de |} .
    """
    result = _run(shapes)
    assert set(_values(result, SH.resultMessage)) == {Literal("too few", lang="en"), Literal("zu wenige", lang="de")}


def test_qualified_counts_are_attributed_by_result_component() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:qualifiedValueShape [ sh:class ex:Dog ] ;
          sh:qualifiedMinCount 2 {| sh:severity sh:Info |} ;
          sh:qualifiedMaxCount 0 {| sh:severity sh:Warning |} .
    """
    result = _run(shapes)
    graph = result.report_graph
    seen = {
        graph.value(r, SH.sourceConstraintComponent): graph.value(r, SH.resultSeverity)
        for r in graph.subjects(RDF.type, SH.ValidationResult)
    }
    assert seen == {
        SH.QualifiedMinCountConstraintComponent: SH.Info,
        SH.QualifiedMaxCountConstraintComponent: SH.Warning,
    }


def test_user_defined_sparql_component_parameter_annotation() -> None:
    shapes = PREFIXES + """
        ex:MinC a sh:ConstraintComponent ;
          sh:parameter [ sh:path ex:minc ] ;
          sh:propertyValidator [ a sh:SPARQLSelectValidator ;
            sh:message "default" ;
            sh:select \"\"\"SELECT $this ?value WHERE { $this $PATH ?value . FILTER (?value = "text") }\"\"\" ] .
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          ex:minc 1 {| sh:severity sh:Warning ; sh:message "custom" |} .
    """
    result = _run(shapes)
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Warning}
    assert set(_values(result, SH.resultMessage)) == {Literal("custom")}


FIXTURES = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite" / "tests" / "core" / "misc"


def _fixture_result(name: str) -> Any:
    graph = StarLayerGraph()
    graph.parse(FIXTURES / f"{name}.ttl", format="turtle12")
    return StarShaclSchema(shacl_graph=graph).validate(data_graph=graph, meta_shacl=False)


def test_w3c_severity_003() -> None:
    result = _fixture_result("severity-003")
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Warning}


def test_w3c_message_002() -> None:
    result = _fixture_result("message-002")
    assert result.conforms is False
    assert set(_values(result, SH.resultMessage)) == {Literal("Test message", lang="en")}
    assert set(_values(result, SH.resultSeverity)) == {SH.Violation}


def test_w3c_deactivated_003() -> None:
    assert _fixture_result("deactivated-003").conforms is True
