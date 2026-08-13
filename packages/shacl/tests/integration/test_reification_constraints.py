import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# Mirrors the SHACL 1.2 Core spec's own worked example for
# sh:reifierShape / sh:reificationRequired (both used together on one
# property shape): an ex:Person's ex:age must be reified with a reifier
# that itself conforms to ex:ProvenanceShape (has an ex:date and ex:author).


def _shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("rdf12_reification_person_age.ttl"), format="turtle")
    return shapes


def test_conforms_when_reifier_has_full_provenance() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:Bob a ex:Person ;
              ex:age 23 {|
                ex:date "2019-12-05"^^xsd:date ;
                ex:author ex:Claire
              |} .
        """,
        format="turtle12",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is True


def test_violates_when_no_reifier_present() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ;
              ex:age 23 .
        """,
        format="turtle12",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_violates_when_reifier_missing_required_provenance_property() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:Bob a ex:Person ;
              ex:age 23 {|
                ex:date "2019-12-05"^^xsd:date
              |} .
        """,
        format="turtle12",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_shapes(), meta_shacl=False)

    assert result.conforms is False


def test_reification_required_string_literal_false_is_rejected_not_silently_enabled() -> None:
    """Found 2026-07-20 via the same audit that caught the analogous
    sh:closed "false" bug (see tests/integration/test_closed_by_types.py):
    ReifierShapeConstraintComponent.__init__ used bare bool(value) for
    sh:reificationRequired instead of checking the literal's datatype -
    bool("false") is True in Python regardless of the string's content, so
    sh:reificationRequired "false" was silently *enabling* the check
    instead of disabling it. Now raises a clean ValueError instead.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:age ; sh:reificationRequired "false" ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ; ex:age 23 .
        """,
        format="turtle",
    )

    with pytest.raises(ValueError, match="xsd:boolean literal"):
        StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)


def test_reification_required_alternate_boolean_lexical_form_leaves_constraint_inactive() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's uniqueLang-002
    fixture (same underlying bug, different predicate) - see
    tests/integration/test_single_line_and_some_value.py's identical test
    for sh:singleLine for the full reasoning. bool(value.value) accepts
    "1"^^xsd:boolean as true (XSD value-space conversion); the spec only
    ever mentions "true" for this family of on/off boolean parameters, so
    "1"^^xsd:boolean must leave the constraint inactive - here, a focus node
    with no reifier at all must still conform. Needs format="turtle12"
    specifically - see the sh:singleLine test's docstring for why plain
    "turtle" parsing can't exercise this at all (rdflib's own Literal()
    constructor already normalizes "1" to "true" before starshacl
    ever sees it).
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:age ; sh:reificationRequired "1"^^xsd:boolean ] .
        """,
        format="turtle12",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ; ex:age 23 .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
