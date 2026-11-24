import pyoxigraph as ox
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor
from tests.support.terms import Namespace

from ._shape_loader import load_shape

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
def test_report_decodes_triple_term_value_node() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("report_says_nodekind_literal.ttl"), format="turtle")

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(data_graph=data)

    assert result.conforms is False
    assert (EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)) in data
    assert any(o == EX.alice for _, _, o in result.report_graph.triples((None, SH.focusNode, None)))
    assert any(o == ox.Triple(EX.bob, EX.knows, EX.carol) for _, _, o in result.report_graph.triples((None, SH.value, None)))


def test_report_preserves_path_and_constraint_component() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("report_says_in.ttl"), format="turtle")

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(data_graph=data)

    assert result.conforms is False
    assert any(o == ox.Triple(EX.bob, EX.knows, EX.carol) for _, _, o in result.report_graph.triples((None, SH.value, None)))
    assert any(o == EX.says for _, _, o in result.report_graph.triples((None, SH.resultPath, None)))
    assert any(
        o == SH.InConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_report_text_humanizes_triple_term_value_node() -> None:
    # sh:sparql constraints run through pySHACL's own report-text builder
    # (create_validation_report), which stamps encoded URIs into the text
    # before starShacl ever sees it - unlike report_graph, there is no
    # structured graph to decode, so this must resolve them via the
    # adapter's registry instead.
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.likes, EX.dave)))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .

            ex:AlwaysFailsShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:sparql [
                a sh:SPARQLConstraint ;
                sh:message "always fails" ;
                sh:select \"\"\"
                    PREFIX ex: <http://example.org/>
                    SELECT $this $value WHERE { $this ex:says $value }
                \"\"\" ;
              ] .
        """,
        format="turtle12",
    )

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert "urn:starlayer:tt:" not in result.report_text
    assert "<<( ex:bob ex:likes ex:dave )>>" in result.report_text  # the shapes graph binds ex, the data graph does not


def test_report_decodes_result_node_for_nodekind_constraint() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.says, (EX.bob, EX.knows, EX.carol)))

    shapes = StarLayerGraph()
    shapes.parse(data=load_shape("report_says_nodekind_blanknode.ttl"), format="turtle")

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(data_graph=data)

    assert result.conforms is False
    assert any(o == EX.alice for _, _, o in result.report_graph.triples((None, SH.focusNode, None)))
    assert any(o == ox.Triple(EX.bob, EX.knows, EX.carol) for _, _, o in result.report_graph.triples((None, SH.value, None)))
    assert any(
        o == SH.NodeKindConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
