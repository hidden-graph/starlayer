import pytest
from rdflib import Literal, Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")


try:
    import pyshacl as _pyshacl  # noqa: F401
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"pyshacl import unavailable: {exc}", allow_module_level=True)


def _ill_formed_case() -> tuple[StarLayerGraph, StarLayerGraph]:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, Literal(30)))

    # Intentionally ill-formed: property shape is missing required sh:path.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            ex:BrokenShape a sh:NodeShape ;
                sh:targetNode ex:alice ;
                sh:property [
                    sh:minCount 1 ;
                    sh:datatype xsd:integer
                ] .
        """,
        format="turtle",
    )

    return data, shapes


def test_meta_shacl_rejects_ill_formed_shapes_graph() -> None:
    data, shapes = _ill_formed_case()

    validator = StarShaclValidator()

    with pytest.raises(Exception) as exc_info:
        validator.validate(data_graph=data, shacl_graph=shapes)

    message = str(exc_info.value)
    assert "metashacl" in message.lower() or "meta-shacl" in message.lower()


def test_meta_shacl_override_false_skips_preflight_but_still_errors_on_bad_shape_load() -> None:
    data, shapes = _ill_formed_case()

    validator = StarShaclValidator()

    with pytest.raises(Exception) as exc_info:
        validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    message = str(exc_info.value)
    assert "well-formed shacl propertyshape" in message.lower()
    assert "metashacl" not in message.lower()
