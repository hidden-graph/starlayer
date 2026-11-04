import pytest
from rdflib import Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import StarShaclSchema

from ._rdflib_view import rd
from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
# Mirrors the SHACL 1.2 Core spec's own worked example for
# sh:reifierShape / sh:reificationRequired (both used together on one
# property shape): an ex:Person's ex:age must be reified with a reifier
# that itself conforms to ex:ProvenanceShape (has an ex:date and ex:author).


def _shapes() -> OxGraph:
    shapes = OxGraph()
    shapes.parse(data=load_shape("rdf12_reification_person_age.ttl"), format="turtle")
    return shapes


def test_conforms_when_reifier_has_full_provenance() -> None:
    data = OxGraph()
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

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_violates_when_no_reifier_present() -> None:
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ;
              ex:age 23 .
        """,
        format="turtle12",
    )

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert any(
        o == SH.ReifierShapeConstraintComponent
        for _, _, o in rd(result.report_graph).triples((None, SH.sourceConstraintComponent, None))
    )


def test_violates_when_reifier_missing_required_provenance_property() -> None:
    data = OxGraph()
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

    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False)

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
    shapes = OxGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:age ; sh:reificationRequired "false" ] .
        """,
        format="turtle",
    )
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Bob a ex:Person ; ex:age 23 .
        """,
        format="turtle",
    )

    with pytest.raises(ValueError, match="xsd:boolean literal"):
        StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
