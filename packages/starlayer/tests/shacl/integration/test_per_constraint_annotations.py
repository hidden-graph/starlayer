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
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
@prefix sparql: <http://www.w3.org/ns/sparql#> .
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
    "expression": ('sh:expression [ sparql:equals ( [ shnex:var "value" ] 42 ) ] {A}', "", PS),
    "nodeByExpression": ("sh:nodeByExpression ex:CatShape {A}", "", PS),
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


@pytest.mark.parametrize(
    "case", ["class", "minCount", "pattern", "node", "qualifiedMinCount", "sparql", "closed", "expression", "nodeByExpression"]
)
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


# --- GitHub issue #201 follow-ups -------------------------------------------------------------------------------

def _rows(result: Any) -> list[tuple[str, str, str, str]]:
    """``(component, severity, message, value)`` of each result, sorted."""
    graph = result.report_graph
    local = lambda term: str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]  # noqa: E731
    return sorted(
        (
            local(graph.value(r, SH.sourceConstraintComponent)),
            local(graph.value(r, SH.resultSeverity)),
            str(graph.value(r, SH.resultMessage)),
            local(graph.value(r, SH.value)),
        )
        for r in graph.subjects(RDF.type, SH.ValidationResult)
    )


# 1. a user-defined SPARQL-based component with one parameter: each value is its own constraint.

USER_ONE_PARAM = PREFIXES + """
ex:Differs a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:differs ] ;
  sh:propertyValidator [ a sh:SPARQLSelectValidator ;
    sh:message "differs {$differs}" ;
    sh:select \"\"\"SELECT $this ?value WHERE { $this $PATH ?value . FILTER (str(?value) != str($differs)) }\"\"\" ] .
ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
ex:PS a sh:PropertyShape ; sh:path ex:v ;
"""


def _user_rows(values: str, data_extra: str = "") -> list[tuple[str, str, str, str]]:
    return _rows(_run(USER_ONE_PARAM + values + " .", extra_data=data_extra))


def test_user_defined_one_parameter_values_with_different_severities() -> None:
    rows = _user_rows('ex:differs "text" {| sh:severity sh:Info |} , "x" {| sh:severity sh:Warning |}')
    assert rows == [
        ("Differs", "Info", "differs text", "other"),
        ("Differs", "Warning", "differs x", "other"),
        ("Differs", "Warning", "differs x", "text"),
    ]


def test_user_defined_one_parameter_one_value_deactivated_other_runs() -> None:
    rows = _user_rows('ex:differs "text" {| sh:severity sh:Info |} , "x" {| sh:deactivated true |}')
    assert rows == [("Differs", "Info", "differs text", "other")]


def test_user_defined_one_parameter_annotated_and_plain_value() -> None:
    rows = _user_rows('ex:differs "text" {| sh:message "own" |} , "x"')
    assert rows == [
        ("Differs", "Violation", "differs x", "other"),
        ("Differs", "Violation", "differs x", "text"),
        ("Differs", "Violation", "own", "other"),
    ]


def test_user_defined_one_parameter_equal_annotations_run_as_one_group() -> None:
    rows = _user_rows('ex:differs "text" {| sh:severity sh:Info |} , "x" {| sh:severity sh:Info |}')
    assert {r[1] for r in rows} == {"Info"}
    assert rows  # not silently skipped


def test_user_defined_one_parameter_single_value_unchanged() -> None:
    rows = _user_rows('ex:differs "x" {| sh:severity sh:Info |}')
    assert rows == [("Differs", "Info", "differs x", "other"), ("Differs", "Info", "differs x", "text")]


# 2. the annotation may sit on any triple of a multi-parameter constraint.

def _ps(body: str, data_extra: str = "") -> Any:
    return _run(
        PREFIXES + COMMON_SHAPES + f"ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .\nex:PS a sh:PropertyShape ; sh:path ex:v ; {body} .",
        extra_data=data_extra,
    )


@pytest.mark.parametrize(
    "body",
    [
        'sh:pattern "^[0-9]+$" {| sh:severity sh:Info |} ; sh:flags "i"',
        'sh:pattern "^[0-9]+$" ; sh:flags "i" {| sh:severity sh:Info |}',
    ],
)
def test_pattern_annotation_on_pattern_or_flags_triple(body: str) -> None:
    result = _ps(body)
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}


@pytest.mark.parametrize(
    "body",
    [
        'sh:pattern "^[0-9]+$" {| sh:deactivated true |} ; sh:flags "i"',
        'sh:pattern "^[0-9]+$" ; sh:flags "i" {| sh:deactivated true |}',
    ],
)
def test_pattern_deactivated_on_pattern_or_flags_triple(body: str) -> None:
    assert _ps(body).conforms is True


def test_pattern_message_on_flags_triple() -> None:
    result = _ps('sh:pattern "^[0-9]+$" ; sh:flags "i" {| sh:message "flags note" |}')
    assert set(_values(result, SH.resultMessage)) == {Literal("flags note")}


QUALIFIED = "sh:qualifiedValueShape [ sh:class ex:Dog ] ; "


def test_qualified_annotation_on_value_shape_triple_applies_to_min_and_max() -> None:
    result = _ps("sh:qualifiedValueShape [ sh:class ex:Dog ] {| sh:severity sh:Info |} ; sh:qualifiedMinCount 2 ; sh:qualifiedMaxCount 0")
    assert {r[0]: r[1] for r in _rows(result)} == {
        "QualifiedMinCountConstraintComponent": "Info",
        "QualifiedMaxCountConstraintComponent": "Info",
    }


def test_qualified_annotation_on_disjoint_triple_applies_to_min_and_max() -> None:
    result = _ps(QUALIFIED + "sh:qualifiedValueShapesDisjoint true {| sh:severity sh:Info |} ; sh:qualifiedMinCount 2 ; sh:qualifiedMaxCount 0")
    assert {r[0]: r[1] for r in _rows(result)} == {
        "QualifiedMinCountConstraintComponent": "Info",
        "QualifiedMaxCountConstraintComponent": "Info",
    }


def test_qualified_deactivated_on_disjoint_triple_deactivates_both() -> None:
    result = _ps(QUALIFIED + "sh:qualifiedValueShapesDisjoint true {| sh:deactivated true |} ; sh:qualifiedMinCount 2 ; sh:qualifiedMaxCount 0")
    assert result.conforms is True


def test_qualified_own_count_annotation_wins_over_shared_triples() -> None:
    result = _ps(
        QUALIFIED
        + "sh:qualifiedValueShapesDisjoint true {| sh:severity sh:Warning |} ; "
        + "sh:qualifiedMinCount 2 {| sh:severity sh:Info |} ; sh:qualifiedMaxCount 0"
    )
    assert {r[0]: r[1] for r in _rows(result)} == {
        "QualifiedMinCountConstraintComponent": "Info",
        "QualifiedMaxCountConstraintComponent": "Warning",
    }


def test_qualified_deactivated_on_max_count_leaves_min_count() -> None:
    result = _ps(QUALIFIED + "sh:qualifiedMinCount 2 ; sh:qualifiedMaxCount 0 {| sh:deactivated true |}")
    assert [r[0] for r in _rows(result)] == ["QualifiedMinCountConstraintComponent"]


def test_closed_annotation_on_ignored_properties_triple() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS ;
          sh:closed true ; sh:ignoredProperties ( rdf:type ) {| sh:severity sh:Info ; sh:message "closed note" |} .
        ex:PS a sh:PropertyShape ; sh:path ex:other2 .
    """
    result = _run(shapes)
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}
    assert set(_values(result, SH.resultMessage)) == {Literal("closed note")}


def test_closed_deactivated_on_ignored_properties_triple() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ;
          sh:closed true ; sh:ignoredProperties ( rdf:type ) {| sh:deactivated true |} .
    """
    assert _run(shapes).conforms is True


USER_TWO_PARAMS = PREFIXES + """
ex:Between a sh:ConstraintComponent ;
  sh:parameter [ sh:path ex:lo ] , [ sh:path ex:hi ] ;
  sh:propertyValidator [ a sh:SPARQLSelectValidator ;
    sh:message "outside" ;
    sh:select \"\"\"SELECT $this ?value WHERE { $this $PATH ?value . FILTER (!isLiteral(?value) || ?value < $lo || ?value > $hi) }\"\"\" ] .
ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
ex:PS a sh:PropertyShape ; sh:path ex:v ;
"""


@pytest.mark.parametrize("triple", ["lo", "hi"])
def test_user_defined_multi_parameter_annotation_on_any_parameter_triple(triple: str) -> None:
    lo = "ex:lo 10 {| sh:severity sh:Info |}" if triple == "lo" else "ex:lo 10"
    hi = "ex:hi 20 {| sh:severity sh:Info |}" if triple == "hi" else "ex:hi 20"
    result = _run(USER_TWO_PARAMS + f"{lo} ; {hi} .")
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}


def test_user_defined_multi_parameter_deactivated_on_either_triple() -> None:
    assert _run(USER_TWO_PARAMS + "ex:lo 10 ; ex:hi 20 {| sh:deactivated true |} .").conforms is True


def test_user_defined_multi_parameter_messages_are_united() -> None:
    result = _run(USER_TWO_PARAMS + 'ex:lo 10 {| sh:message "from lo" |} ; ex:hi 20 {| sh:message "from hi" |} .')
    assert set(_values(result, SH.resultMessage)) == {Literal("from lo"), Literal("from hi")}


@pytest.mark.parametrize(
    ("first", "second"), [("sh:Info", "sh:Warning"), ("sh:Warning", "sh:Info"), ("sh:Info", "sh:Violation")]
)
def test_conflicting_severities_in_one_constraint_pick_the_most_severe(first: str, second: str) -> None:
    """Ill-formed (at most one severity is allowed): the most severe wins, whichever triple states it, and nothing crashes."""
    result = _run(USER_TWO_PARAMS + f"ex:lo 10 {{| sh:severity {first} |}} ; ex:hi 20 {{| sh:severity {second} |}} .")
    expected = min((first, second), key=["sh:Violation", "sh:Warning", "sh:Info"].index)
    assert set(_values(result, SH.resultSeverity)) == {SH[expected[3:]]}


def test_conflicting_severities_on_pattern_and_flags_do_not_crash() -> None:
    result = _ps('sh:pattern "^[0-9]+$" {| sh:severity sh:Info |} ; sh:flags "i" {| sh:severity sh:Warning |}')
    assert set(_values(result, SH.resultSeverity)) == {SH.Info}  # the pattern triple's own value wins over its flags


def test_two_reifiers_of_one_triple_with_different_severities() -> None:
    result = _ps("sh:minCount 3 {| sh:severity sh:Info |} {| sh:severity sh:Warning |}")
    assert set(_values(result, SH.resultSeverity)) == {SH.Warning}


# 3. sh:deactivated is a node expression.

EXPR_ONE_ONE = "sparql:equals ( 1 1 )"
EXPR_ONE_TWO = "sparql:equals ( 1 2 )"


@pytest.mark.parametrize("case", ["class", "minCount", "pattern", "node", "qualifiedMinCount", "sparql", "closed", "expression"])
def test_deactivated_expression_true_skips_the_constraint(case: str) -> None:
    assert _case_run(case, f"{{| sh:deactivated [ {EXPR_ONE_ONE} ] |}}").conforms is True


@pytest.mark.parametrize("case", ["class", "minCount", "pattern", "node", "qualifiedMinCount", "sparql", "closed", "expression"])
def test_deactivated_expression_false_runs_the_constraint(case: str) -> None:
    result = _case_run(case, f"{{| sh:deactivated [ {EXPR_ONE_TWO} ] |}}")
    assert result.conforms is False
    assert set(_values(result, SH.resultSeverity)) == {SH.Violation}


def test_deactivated_expression_that_is_not_boolean_does_not_deactivate() -> None:
    result = _ps("sh:minCount 3 {| sh:deactivated [ sparql:plus ( 1 1 ) ] |}")
    assert result.conforms is False


def test_deactivated_expression_value_is_not_a_boolean_literal_keeps_working() -> None:
    assert _ps("sh:minCount 3 {| sh:deactivated true |}").conforms is True
    assert _ps('sh:minCount 3 {| sh:deactivated "true" |}').conforms is False  # a string is not the boolean true


def test_deactivated_expression_depends_on_the_focus_node() -> None:
    """Evaluated once per focus node, as for a shape: only the focus node the expression picks is skipped."""
    data = PREFIXES + "ex:a a ex:P . ex:b a ex:P ."
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:minCount 1 {| sh:deactivated [ sparql:equals ( [ shnex:var "focusNode" ] ex:a ) ] |} .
    """
    result = _run(shapes, data)
    assert {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))} == {EX.b}


def test_deactivated_expression_on_one_value_of_a_parameter() -> None:
    shapes = PREFIXES + f"""
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ;
          sh:class ex:Cat {{| sh:deactivated [ {EXPR_ONE_ONE} ] |}} , ex:Dog .
    """
    result = _run(shapes)
    assert [str(result.report_graph.value(r, SH.value)) for r in result.report_graph.subjects(RDF.type, SH.ValidationResult)] == ["text"]


def test_deactivated_expression_with_severity_on_another_constraint() -> None:
    result = _ps(f"sh:minCount 3 {{| sh:deactivated [ {EXPR_ONE_ONE} ] |}} ; sh:maxLength 2 {{| sh:severity sh:Info |}}")
    assert {r[0]: r[1] for r in _rows(result)} == {"MaxLengthConstraintComponent": "Info"}


def test_deactivated_expression_on_qualified_count_by_focus_node() -> None:
    shapes = PREFIXES + """
        ex:Shape a sh:NodeShape ; sh:targetClass ex:P ; sh:property ex:PS .
        ex:PS a sh:PropertyShape ; sh:path ex:v ; sh:qualifiedValueShape [ sh:class ex:Dog ] ;
          sh:qualifiedMinCount 2 {| sh:deactivated [ sparql:equals ( [ shnex:var "focusNode" ] ex:a ) ] |} .
    """
    result = _run(shapes, PREFIXES + "ex:a a ex:P . ex:b a ex:P .")
    assert {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))} == {EX.b}


def test_deactivated_expression_in_a_user_defined_component() -> None:
    rows = _user_rows(f'ex:differs "text" {{| sh:deactivated [ {EXPR_ONE_ONE} ] |}} , "x"')
    assert {r[2] for r in rows} == {"differs x"}


# sh:expression and sh:nodeByExpression with severity, message and deactivated (also in the matrix above).

def test_expression_annotation_severity_message_and_deactivated() -> None:
    expression = 'sh:expression [ sparql:equals ( [ shnex:var "value" ] 42 ) ]'
    result = _ps(expression + ' {| sh:severity sh:Info ; sh:message "not 42" |}')
    assert {r[1:3] for r in _rows(result)} == {("Info", "not 42")}
    assert _ps(expression + " {| sh:deactivated true |}").conforms is True


def test_node_by_expression_annotation_severity_message_and_deactivated() -> None:
    result = _ps('sh:nodeByExpression ex:CatShape {| sh:severity sh:Warning ; sh:message "not a cat" |}')
    assert {r[1:3] for r in _rows(result)} == {("Warning", "not a cat")}
    assert _ps("sh:nodeByExpression ex:CatShape {| sh:deactivated true |}").conforms is True
    assert _ps(f"sh:nodeByExpression ex:CatShape {{| sh:deactivated [ {EXPR_ONE_ONE} ] |}}").conforms is True
