import pytest
from rdflib import Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import StarShaclSchema

from ._rdflib_view import rd
from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
# Mirrors the SHACL 1.2 Core spec's own examples for sh:memberShape,
# sh:minListLength, sh:maxListLength, and sh:uniqueMembers.


def _shapes() -> OxGraph:
    shapes = OxGraph()
    shapes.parse(data=load_shape("shacl12_list_constraints.ttl"), format="turtle")
    return shapes


def _violation_components(result) -> set:
    return {o for _, _, o in rd(result.report_graph).triples((None, SH.sourceConstraintComponent, None))}


def test_member_shape_conforms_when_all_members_match() -> None:
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:agenda1 a ex:Agenda ; ex:speakerOrder ( ex:Alice ex:Bob ex:Charlie ) .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_member_shape_violates_when_a_member_does_not_conform() -> None:
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:agenda2 a ex:Agenda ; ex:speakerOrder ( ex:Alice ex:Bob "Charlie" ) .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert SH.MemberShapeConstraintComponent in _violation_components(result)


def test_list_length_and_uniqueness_conform() -> None:
    data = OxGraph()
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

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_list_length_and_uniqueness_all_violate_independently() -> None:
    data = OxGraph()
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

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

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
    data = OxGraph()
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

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

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
    shapes = OxGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:property [ sh:path ex:tags ; sh:uniqueMembers "false" ] .
        """,
        format="turtle",
    )
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:t1 a ex:Thing ; ex:tags ( "a" "a" ) .
        """,
        format="turtle",
    )

    with pytest.raises(ValueError, match="xsd:boolean literal"):
        StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
