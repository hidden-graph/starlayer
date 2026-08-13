import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from ._shape_loader import load_shape


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# pySHACL 0.40 outright crashes (AssertionError) given sh:closed sh:ByTypes -
# it only accepts a boolean literal - so these confirm both that the crash is
# avoided and that the by-types property collection algorithm is correct,
# not just that something silently passes.


def _violation_components(result) -> list:
    return [o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))]


def test_conforms_with_only_own_and_superclass_properties() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_closed_by_types.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:dog1 a ex:Dog ; ex:name "Rex" ; ex:barks true .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_violates_with_a_property_from_neither_shape() -> None:
    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("shacl12_closed_by_types.ttl"), format="turtle")

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:dog1 a ex:Dog ; ex:name "Rex" ; ex:barks true ; ex:meows false .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.ClosedConstraintComponent in _violation_components(result)


def test_sibling_shape_reached_via_target_class_extends_allowed_properties() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:Dog a rdfs:Class, sh:NodeShape ;
              sh:closed sh:ByTypes ;
              sh:property [ sh:path ex:barks ] .

            ex:DogExtras a sh:NodeShape ;
              sh:targetClass ex:Dog ;
              sh:property [ sh:path ex:breed ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:dog1 a ex:Dog ; ex:barks true ; ex:breed "Labrador" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


class TestClosedMalformedValueRejectedCleanly:
    """A non-boolean sh:closed value must raise a clean ValueError, not crash
    unpredictably or - the more dangerous case - be silently misinterpreted.
    Found 2026-07-20 while investigating a matching pySHACL bug (see
    docs/pyshacl-upstream-issues.md, Issue 3): starShacl's own
    ClosedConstraintComponent shadow already rejected a non-Literal value
    (e.g. an IRI) cleanly, but a string literal like "false" was still
    silently coerced to closed=True - bool("false") is True in Python
    regardless of the string's content - the opposite of what "false" reads
    as. Checking the literal's actual xsd:boolean datatype (not just
    isinstance(..., Literal)) closes this.
    """

    def _shape(self, closed_value_ttl: str) -> str:
        return f"""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Dog a sh:NodeShape ;
              sh:targetClass ex:Dog ;
              sh:closed {closed_value_ttl} ;
              sh:property [ sh:path ex:barks ] .
        """

    def _data(self) -> str:
        return """
            @prefix ex: <http://example.org/> .
            ex:dog1 a ex:Dog ; ex:barks true .
        """

    def test_string_literal_false_is_rejected_not_silently_coerced_to_true(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._shape('"false"'), format="turtle")
        data = StarLayerGraph()
        data.parse(data=self._data(), format="turtle")

        with pytest.raises(ValueError, match="xsd:boolean literal or sh:ByTypes"):
            StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    def test_iri_value_is_still_rejected_cleanly(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._shape("ex:NotEvenARealValue"), format="turtle")
        data = StarLayerGraph()
        data.parse(data=self._data(), format="turtle")

        with pytest.raises(ValueError, match="xsd:boolean literal or sh:ByTypes"):
            StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    def test_real_boolean_true_still_works(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._shape("true"), format="turtle")
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:dog1 a ex:Dog ; ex:barks true ; ex:extra "unexpected" .
            """,
            format="turtle",
        )

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is False
        assert SH.ClosedConstraintComponent in _violation_components(result)

    def test_real_boolean_false_still_works(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(data=self._shape("false"), format="turtle")
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                ex:dog1 a ex:Dog ; ex:barks true ; ex:extra "unexpected" .
            """,
            format="turtle",
        )

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
        assert result.conforms is True


def test_linked_shape_via_sh_node_extends_allowed_properties() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:Extra a sh:NodeShape ;
              sh:property [ sh:path ex:extraProp ] .

            ex:Main a rdfs:Class, sh:NodeShape ;
              sh:closed sh:ByTypes ;
              sh:node ex:Extra ;
              sh:property [ sh:path ex:mainProp ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:thing1 a ex:Main ; ex:mainProp "a" ; ex:extraProp "b" .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True
