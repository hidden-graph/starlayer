import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# Mirrors the SHACL 1.2 Core spec's own examples for sh:memberShape,
# sh:minListLength, sh:maxListLength, and sh:uniqueMembers.


def _shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_list_constraints.ttl"), format="turtle")
    return shapes


def _violation_components(result) -> set:
    return {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))}


def test_member_shape_conforms_when_all_members_match() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:agenda1 a ex:Agenda ; ex:speakerOrder ( ex:Alice ex:Bob ex:Charlie ) .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is True


def test_member_shape_violates_when_a_member_does_not_conform() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:agenda2 a ex:Agenda ; ex:speakerOrder ( ex:Alice ex:Bob "Charlie" ) .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is False
    assert SH.MemberShapeConstraintComponent in _violation_components(result)


def test_list_length_and_uniqueness_conform() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:person1 a ex:Person ;
              ex:skills ( "coding" ) ;
              ex:hobbies ( "reading" "writing" ) ;
              ex:preferences ( "coffee" "tea" ) .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is True


def test_list_length_and_uniqueness_all_violate_independently() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:person2 a ex:Person ;
              ex:skills () ;
              ex:hobbies ( "reading" "writing" "swimming" ) ;
              ex:preferences ( "coffee" "tea" "coffee" ) .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is False
    components = _violation_components(result)
    assert SH.MinListLengthConstraintComponent in components
    assert SH.MaxListLengthConstraintComponent in components
    assert SH.UniqueMembersConstraintComponent in components


def test_non_list_value_violates_each_active_sub_constraint() -> None:
    # ex:skills only has sh:minListLength configured, so a non-list value
    # there produces exactly one violation (that component's own), per the
    # spec's "if v is not a SHACL list there is a validation result" text
    # appearing independently in each constraint component's definition.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:person3 a ex:Person ;
              ex:skills "not-a-list" ;
              ex:hobbies ( "x" ) ;
              ex:preferences ( "y" ) .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is False
    assert _violation_components(result) == {SH.MinListLengthConstraintComponent}


def test_unique_members_string_literal_false_is_rejected_not_silently_enabled() -> None:
    """Found 2026-07-20 via the same audit that caught the analogous
    sh:closed "false" bug (see tests/integration/test_closed_by_types.py):
    UniqueMembersConstraintComponent.__init__ used bare bool(value) instead
    of checking the literal's datatype - bool("false") is True in Python
    regardless of the string's content, so sh:uniqueMembers "false" was
    silently *enabling* the check instead of disabling it. Now raises a
    clean ValueError instead.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:property [ sh:path ex:tags ; sh:uniqueMembers "false" ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:t1 a ex:Thing ; ex:tags ( "a" "a" ) .
        """,
        format="turtle",
    )

    with pytest.raises(ValueError, match="xsd:boolean literal"):
        StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)


def test_unique_members_alternate_boolean_lexical_form_leaves_constraint_inactive() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's uniqueLang-002
    fixture (same underlying bug, different predicate) - see
    tests/integration/test_single_line_and_some_value.py's identical test
    for sh:singleLine for the full reasoning. bool(value.value) accepts
    "1"^^xsd:boolean as true (XSD value-space conversion); the spec only
    ever mentions "true" for this family of on/off boolean parameters, so
    "1"^^xsd:boolean must leave the constraint inactive. Needs
    format="turtle12" specifically - see the sh:singleLine test's docstring
    for why plain "turtle" parsing can't exercise this at all (rdflib's own
    Literal() constructor already normalizes "1" to "true" before
    starshacl ever sees it).
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:property [ sh:path ex:tags ; sh:uniqueMembers "1"^^xsd:boolean ] .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:t1 a ex:Thing ; ex:tags ( "a" "a" ) .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
