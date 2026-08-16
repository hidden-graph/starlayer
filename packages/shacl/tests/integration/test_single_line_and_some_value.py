import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# Mirrors the SHACL 1.2 Core spec's own examples for sh:singleLine and
# sh:someValue.


def _violation_components(result) -> set:
    return {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))}


def test_single_line_conforms_and_allows_explicit_multiline_opt_out() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_single_line.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:t1 a ex:Thing ; rdfs:label "hello" ; rdfs:comment "line1\\nline2" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_single_line_violates_when_value_contains_line_break() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_single_line.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:t2 a ex:Thing ; rdfs:label "hello\\nworld" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.SingleLineConstraintComponent in _violation_components(result)


def test_single_line_string_literal_false_is_rejected_not_silently_enabled() -> None:
    """Found 2026-07-20 via the same audit that caught the analogous
    sh:closed "false" bug (see tests/integration/test_closed_by_types.py):
    SingleLineConstraintComponent.__init__ used bare bool(value) instead of
    checking the literal's datatype - bool("false") is True in Python
    regardless of the string's content, so sh:singleLine "false" was
    silently *enabling* the check instead of disabling it. Now raises a
    clean ValueError instead.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:property [ sh:path ex:title ; sh:singleLine "false" ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:t1 a ex:Thing ; ex:title "line1\\nline2" .
        """,
        format="turtle",
    )

    with pytest.raises(ValueError, match="xsd:boolean literal"):
        StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)


def test_single_line_alternate_boolean_lexical_form_leaves_constraint_inactive() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's uniqueLang-002
    fixture (same underlying bug, different predicate): the datatype guard
    above only checks *that* the value is xsd:boolean, then converted it via
    bool(value.value) - XSD's value-space conversion, which also accepts
    "1"^^xsd:boolean as true, alongside the canonical "true". The spec only
    ever mentions "true" for this family of on/off boolean parameters, so
    "1"^^xsd:boolean (a distinct term, even though value-equal) must leave
    the constraint inactive, not silently enable it - now compared via exact
    lexical form instead. Needs format="turtle12" specifically: plain
    "turtle" parsing already normalizes "1"^^xsd:boolean to "true" before
    starshacl ever sees the literal (rdflib's own Literal()
    constructor default), so only an RDF-1.2 ("turtle12") document, whose
    parser deliberately preserves the non-canonical lexical form (see
    docs/starlayergraph-upstream-change-log.md's 2026-07-31 entry), can actually
    exercise this distinction - matching how the real W3C fixture is loaded.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;
              sh:property [ sh:path ex:title ; sh:singleLine "1"^^xsd:boolean ] .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:t1 a ex:Thing ; ex:title "line1\\nline2" .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_some_value_conforms_when_one_value_matches() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_some_value.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:farmer1 a ex:Farmer ; ex:tendsAnimal ex:duck1, ex:cow1 .
            ex:duck1 a ex:Duck .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_some_value_violates_when_no_value_matches() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_some_value.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:farmer2 a ex:Farmer ; ex:tendsAnimal ex:cow1, ex:cow2 .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.SomeValueConstraintComponent in _violation_components(result)
