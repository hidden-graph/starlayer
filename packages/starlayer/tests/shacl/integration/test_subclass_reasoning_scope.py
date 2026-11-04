from rdflib import RDFS, Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

# The SHACL 1.2 draft reads rdfs:subClassOf from the DATA graph only. A
# subclass assertion in the shapes graph is ignored (the old opt-in option
# rdfs_subclass_reasoning_includes_shapes_graph no longer exists), and the
# same assertion in the data graph is honored.


def _shapes_with_root_class_and_shapes_graph_subclass_assertion() -> OxGraph:
    shapes = OxGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            # This rdfs:subClassOf assertion lives only in the SHAPES graph.
            ex:Lion rdfs:subClassOf ex:Animal .

            ex:S a sh:NodeShape ;
              sh:targetNode ex:Zoo ;
              sh:property [
                sh:path ex:holds ;
                sh:rootClass ex:Animal ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _data_zoo_holds_lion() -> OxGraph:
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Zoo ex:holds ex:Lion .
        """,
        format="turtle",
    )
    return data


def test_root_class_ignores_shapes_graph_subclass_assertion_by_default() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes_with_root_class_and_shapes_graph_subclass_assertion())
    result = validator.validate(
        data_graph=_data_zoo_holds_lion(),
        meta_shacl=False,
    )

    assert result.conforms is False


def test_root_class_honors_data_graph_subclass_assertion() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes_with_root_class_and_shapes_graph_subclass_assertion())
    data = _data_zoo_holds_lion()
    data.add((EX.Lion, RDFS.subClassOf, EX.Animal))
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def _shapes_with_list_valued_class_and_shapes_graph_subclass_assertion() -> OxGraph:
    shapes = OxGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            # This rdfs:subClassOf assertion lives only in the SHAPES graph.
            ex:Tiger rdfs:subClassOf ex:Cat .

            ex:S a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [
                sh:path ex:pet ;
                sh:class ( ex:Cat ex:Dog ) ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _data_alice_has_tiger() -> OxGraph:
    data = OxGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Tiggy a ex:Tiger .
            ex:Alice a ex:Person ; ex:pet ex:Tiggy .
        """,
        format="turtle",
    )
    return data


def test_list_valued_class_ignores_shapes_graph_subclass_assertion_by_default() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes_with_list_valued_class_and_shapes_graph_subclass_assertion())
    result = validator.validate(
        data_graph=_data_alice_has_tiger(),
        meta_shacl=False,
    )

    assert result.conforms is False


def test_list_valued_class_honors_data_graph_subclass_assertion() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes_with_list_valued_class_and_shapes_graph_subclass_assertion())
    data = _data_alice_has_tiger()
    data.add((EX.Tiger, RDFS.subClassOf, EX.Cat))
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True
