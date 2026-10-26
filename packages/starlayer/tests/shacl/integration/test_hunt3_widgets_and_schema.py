"""Hunt 3 (GitHub issues #130 and #131): widget conditions decide on the node asked about, not on the whole graph;
a malformed score or an ``owl:imports`` in the catalog does not stop the selection; ``StarShaclSchema`` sees edits
made to the graphs it was given."""

from rdflib import RDF, XSD, Graph, Literal, Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema, validate
from starlayer.shacl.ui_widget_selection import SHUI, select_widget, select_widgets

EX = Namespace("http://ex/")
SH = Namespace("http://www.w3.org/ns/shacl#")
PRE = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
)


def graph(text):
    g = StarLayerGraph()
    g.parse(data=PRE + text, format="turtle")
    return g


TWO_PROPS = """ex:S a sh:NodeShape ; sh:property ex:p1, ex:p2 .
ex:p1 a sh:PropertyShape ; sh:path ex:a ; sh:datatype xsd:integer .
ex:p2 a sh:PropertyShape ; sh:path ex:b ; sh:datatype xsd:string ."""


def test_shape_condition_ignores_other_targeted_nodes_violating_it():
    """A condition shape with its own targets: p2 violating it says nothing about p1 (single and batch agree)."""
    shapes = graph(TWO_PROPS)
    scoring = graph(
        """ex:s1 a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        ex:s2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 5 ; shui:shapesGraphShape ex:Q .
        ex:Q a sh:NodeShape ; sh:targetClass sh:PropertyShape ;
            sh:property [ sh:path sh:datatype ; sh:hasValue xsd:integer ] ."""
    )
    kw = {"shapes_graph": shapes, "scoring_graph": scoring, "role": "editor"}
    assert select_widget(shape_node=EX.p1, **kw) == SHUI.NumberFieldEditor
    assert select_widget(shape_node=EX.p2, **kw) == SHUI.TextFieldEditor
    batch = select_widgets(shape_node=EX.S, **kw)
    assert batch == {EX.p1: SHUI.NumberFieldEditor, EX.p2: SHUI.TextFieldEditor}


def test_catalog_rule_violated_by_other_node_does_not_veto_single_path():
    shapes = graph(TWO_PROPS)
    scoring = graph(
        """ex:s1 a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        ex:s2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 50 ; shui:shapesGraphShape ex:IsInt .
        ex:IsInt a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:integer ] .
        ex:Rule sh:targetClass sh:PropertyShape ; sh:property [ sh:path sh:path ; sh:hasValue ex:a ] ."""
    )
    kw = {"shapes_graph": shapes, "scoring_graph": scoring, "role": "editor"}
    assert select_widget(shape_node=EX.p1, **kw) == SHUI.NumberFieldEditor
    assert select_widgets(shape_node=EX.S, **kw)[EX.p1] == SHUI.NumberFieldEditor
    assert select_widgets(shape_node=EX.S, per="shape", **kw)[EX.p1].widget_without_data == SHUI.NumberFieldEditor


def test_data_condition_ignores_unrelated_shapes_and_nonconforming_data():
    shapes = graph(
        """ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        ex:pa a sh:PropertyShape ; sh:path ex:age ; sh:datatype xsd:integer ."""
    )
    scoring = graph(
        """ex:s1 a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        ex:s2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 50 ; shui:dataGraphShape ex:IsPerson .
        ex:IsPerson a sh:NodeShape ; sh:class ex:Person ."""
    )
    data = graph("ex:bob a ex:Person ; ex:age 5 .")  # no ex:name, so the data does not validate
    kw = {"shape_node": EX.pa, "shapes_graph": shapes, "scoring_graph": scoring, "role": "editor"}
    assert select_widget(focus_node=EX.bob, data_graph=data, **kw) == SHUI.NumberFieldEditor
    shapes.add((EX.PersonShape, SH.property, EX.pa))
    choice = select_widgets(shape_node=EX.PersonShape, per="shape", shapes_graph=shapes, scoring_graph=scoring, role="editor")
    assert choice[EX.pa].resolve(EX.bob, data) == SHUI.NumberFieldEditor
    other = graph("ex:rob a ex:Robot .")
    assert select_widget(focus_node=EX.rob, data_graph=other, **kw) == SHUI.TextFieldEditor


def test_data_condition_with_unrelated_violated_target_shape():
    shapes = graph(
        """ex:Other sh:targetClass ex:C ; sh:property [ sh:path ex:name ; sh:minLength 100 ] .
        ex:p1 a sh:PropertyShape ; sh:path ex:age ; sh:datatype xsd:integer ."""
    )
    scoring = graph(
        """ex:s1 a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        ex:s2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 50 ; shui:dataGraphShape ex:Big .
        ex:Big a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minInclusive 10 ] ."""
    )
    data = graph('ex:a a ex:C ; ex:age 20 ; ex:name "short" .')
    got = select_widget(
        shape_node=EX.p1, focus_node=EX.a, data_graph=data, shapes_graph=shapes, scoring_graph=scoring, role="editor"
    )
    assert got == SHUI.NumberFieldEditor


def test_catalog_with_owl_imports_does_not_crash():
    shapes = graph(TWO_PROPS)
    scoring = graph(
        """<http://ex/cat> a owl:Ontology ; owl:imports <http://ex/other> .
        ex:s1 a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 .
        ex:s2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score 5 ; shui:shapesGraphShape ex:IsInt .
        ex:IsInt a sh:NodeShape ; sh:property [ sh:path sh:datatype ; sh:hasValue xsd:integer ] ."""
    )
    kw = {"shapes_graph": shapes, "scoring_graph": scoring, "role": "editor"}
    assert select_widget(shape_node=EX.p1, **kw) == SHUI.NumberFieldEditor
    assert select_widgets(shape_node=EX.S, **kw)[EX.p1] == SHUI.NumberFieldEditor


def test_malformed_score_is_skipped():
    shapes = graph(TWO_PROPS)
    scoring = graph(
        """ex:bad1 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score "high" .
        ex:bad2 a shui:WidgetScore ; shui:widget shui:NumberFieldEditor ; shui:score ex:foo .
        ex:ok a shui:WidgetScore ; shui:widget shui:TextFieldEditor ; shui:score 1 ."""
    )
    got = select_widgets(shape_node=EX.S, shapes_graph=shapes, scoring_graph=scoring, role="editor")
    assert got == {EX.p1: SHUI.TextFieldEditor, EX.p2: SHUI.TextFieldEditor}


def _plain(text):
    g = Graph()
    g.parse(data=PRE + text, format="turtle")
    return g


def test_schema_sees_edits_to_plain_rdflib_graphs():
    sg = _plain("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P . ex:P sh:path ex:p ; sh:minCount 1 .")
    dg = _plain("ex:a a ex:C .")
    schema = StarShaclSchema(shacl_graph=sg, data_graph=dg)
    assert schema.validate().conforms is False
    dg.add((EX.a, EX.p, Literal(1)))
    assert schema.validate().conforms is True
    assert validate(dg, shacl_graph=sg).conforms is True
    dg.remove((EX.a, EX.p, None))
    sg.set((EX.P, SH.minCount, Literal(0)))
    assert schema.validate().conforms is True
    sg.set((EX.P, SH.minCount, Literal(1)))
    assert schema.validate().conforms is False


def test_schema_sees_removed_constraint():
    sg = _plain("ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property ex:P . ex:P sh:path ex:p ; sh:datatype xsd:string .")
    dg = _plain("ex:a a ex:C ; ex:p 1 .")
    schema = StarShaclSchema(sg, data_graph=dg)
    assert schema.validate().conforms is False
    sg.remove((EX.P, SH.datatype, None))
    assert schema.validate().conforms is True
    sg.add((EX.P, SH.datatype, XSD.string))
    assert schema.validate().conforms is False


def test_extract_subgraph_with_unknown_shape_is_a_value_error():
    import pytest
    from starlayer.shacl import extract_subgraph

    sg = graph("ex:S a sh:NodeShape ; sh:targetClass ex:C .")
    with pytest.raises(ValueError, match="not a shape"):
        extract_subgraph(StarLayerGraph(), sg, shape=EX.Nope, focus_node=EX.x)


def test_shacl_shacl_ui_scores_languagein_and_path_are_not_iri_editors():
    from starlayer.starontology import get_ontology_graph

    ui = get_ontology_graph("shacl_shacl_ui")
    catalog = StarLayerGraph()
    catalog += get_ontology_graph("shacl_ui_baseline")
    catalog += get_ontology_graph("shacl_shacl_ui_scores")
    chosen = {}
    for form in ui.subjects(RDF.type, SH.NodeShape):
        for prop, widget in select_widgets(shape_node=form, shapes_graph=ui, scoring_graph=catalog, role="editor").items():
            for path in ui.objects(prop, SH.path):
                chosen.setdefault(path, set()).add(widget)
    assert chosen[SH.languageIn] == {SHUI.TextFieldEditor}
    assert SHUI.IRIEditor not in chosen[SH.path]
