"""More regression tests from the SHACL API bug hunt (meta_shacl prefixes, apply_rules options, modules, reports)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph.core import StarLayerGraph
from starlayer.shacl import validate

pytestmark = pytest.mark.filterwarnings("ignore")

PFX = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://e/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .\n"
)


def g(text, identifier=None):
    x = StarLayerGraph(identifier=identifier) if identifier is not None else StarLayerGraph()
    x.parse(data=PFX + text, format="turtle12")
    return x


_XA = '"http://ex/"^^xsd:anyURI'


def test_meta_shacl_prefix_through_owl_imports():
    sg = g(
        f"""<http://ex/Main> a owl:Ontology ; owl:imports <http://ex/Lib> ; sh:declare [ sh:prefix "a" ; sh:namespace {_XA} ] .
<http://ex/Lib> a owl:Ontology ; sh:declare [ sh:prefix "lib" ; sh:namespace "http://lib/"^^xsd:anyURI ] .
<http://ex/S> a sh:NodeShape ; sh:targetNode <http://ex/n> ;
  sh:sparql [ sh:prefixes <http://ex/Main> ; sh:select "SELECT $this WHERE {{ $this lib:p ?x }}" ; sh:message "m" ] .""",
        ox.NamedNode("http://ex/g"),
    )
    d = g("<http://ex/n> <http://lib/p> 1 .")
    assert validate(d, sg, ignore_imports=True, meta_shacl=True).conforms is False


def test_meta_shacl_prefix_from_shapes_graph_declare_without_sh_prefixes():
    sg = g(
        f"""<http://ex/G> a sh:ShapesGraph ; sh:declare [ sh:prefix "zz" ; sh:namespace {_XA} ] .
<http://ex/S> a sh:NodeShape ; sh:targetNode <http://ex/n> ;
  sh:sparql [ sh:select "SELECT $this WHERE {{ $this zz:p ?x }}" ; sh:message "m" ] .""",
        ox.NamedNode("http://ex/g"),
    )
    d = g("<http://ex/n> <http://ex/p> 1 .")
    assert validate(d, sg, meta_shacl=True).conforms is False


# --- imports and the shapes graph's identity


def test_validate_without_shapes_graph_resolves_imports_with_loader():
    imported = "ex:T a sh:NodeShape ; sh:targetNode ex:a ; sh:nodeKind sh:Literal ."
    data = g("ex:a ex:p 1 . <http://e/onto> a owl:Ontology ; owl:imports <http://e/imp> .")
    loader = lambda iri: g(imported)  # noqa: E731
    assert validate(data, shapes_graph_loader=loader).conforms is False
    assert validate(data, data, shapes_graph_loader=loader).conforms is False


def test_validate_without_shapes_graph_unresolved_import_raises():
    data = g("ex:a ex:p 1 . <http://e/onto> a owl:Ontology ; owl:imports <http://e/imp> .")
    with pytest.raises(ValueError):
        validate(data)


def test_used_shapes_graph_kept_when_imports_resolved_with_loader():
    shapes = g(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:class ex:C . <http://e/shapesG> owl:imports <http://e/imp> .",
        ox.NamedNode("http://e/shapesG"),
    )
    loader = lambda iri: g("ex:T a sh:NodeShape ; sh:targetNode ex:a ; sh:minCount 1 .")  # noqa: E731
    data = g("ex:a ex:p 1 .")
    used = ox.NamedNode("http://www.w3.org/ns/shacl#usedShapesGraph")
    r = validate(data, shapes, shapes_graph_loader=loader)
    assert [o for _, _, o in r.report_graph.triples((None, used, None))] == [ox.NamedNode("http://e/shapesG")]


# --- apply_rules takes validate()'s options


def test_apply_rules_meta_shacl_checks_sparql_text_like_validate():
    from starlayer.shacl import ShapeError, apply_rules

    def shapes():
        return g(
            """ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this ?y WHERE { $this ex:p ?x }" ;
              sh:prefixes ex:Pf ; sh:message "m" ] .
            ex:Pf sh:declare [ sh:prefix "ex" ; sh:namespace "http://e/"^^xsd:anyURI ] .""",
            ox.NamedNode("http://e/g"),
        )

    d = g("ex:a ex:p 1 .")
    with pytest.raises(ShapeError):
        validate(d, shapes(), meta_shacl=True)
    with pytest.raises(ShapeError):
        apply_rules(d, shapes(), meta_shacl=True)


_RULE = (
    "ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:made ; "
    "sh:object 1 ] ; sh:property [ sh:path ex:made ; sh:minCount 1 ] ."
)


def test_apply_rules_runs_rules_of_imported_shapes():
    from starlayer.shacl import apply_rules

    main = g("<http://e/main> a owl:Ontology ; owl:imports <http://e/lib> .")
    d = g("ex:n a ex:C .")
    r = apply_rules(d, main, shapes_graph_loader=lambda iri: g(_RULE))
    assert len(r.inferred_graph) == 1
    assert r.validation.conforms is True


def test_apply_rules_validation_records_used_data_graph_identity():
    from starlayer.shacl import apply_rules

    d = g("ex:a ex:q 1 .", ox.NamedNode("http://e/data"))
    s = g("ex:S a sh:NodeShape ; sh:targetNode ex:a .", ox.NamedNode("http://e/shapes"))
    used = ox.NamedNode("http://www.w3.org/ns/shacl#usedDataGraph")
    assert [o for _, _, o in apply_rules(d, s).validation.report_graph.triples((None, used, None))] == [
        ox.NamedNode("http://e/data")
    ]


# --- extract_shapes_graph(include_referenced=True) copies every shape the members name


def _focus_nodes(report):
    focus = ox.NamedNode("http://www.w3.org/ns/shacl#focusNode")
    return sorted(str(o) for _, _, o in report.report_graph.triples((None, focus, None)))


def test_extract_shapes_graph_copies_shape_named_in_node_expression():
    from starlayer.shacl import StarShaclSchema

    shapes = g("""ex:M a sh:ShapesGraph ; rdfs:member ex:S .
      ex:S a sh:NodeShape ; sh:targetClass ex:P ;
        sh:deactivated [ shnex:exists [ shnex:filterShape ex:Legacy ; shnex:nodes [ shnex:var "focusNode" ] ] ] ;
        sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
      ex:Legacy a sh:NodeShape ; sh:property [ sh:path ex:legacy ; sh:hasValue true ] .""")
    data = g("ex:alice a ex:P ; ex:age 12 ; ex:legacy true . ex:dave a ex:P ; ex:age 12 ; ex:legacy false .")
    ext = StarShaclSchema(shapes).extract_shapes_graph(ox.NamedNode("http://e/M"), include_referenced=True)
    assert _focus_nodes(validate(data, shapes)) == _focus_nodes(validate(data, ext)) == ["<http://e/dave>"]


def test_extract_shapes_graph_copies_target_where_and_rule_condition_shapes():
    from starlayer.shacl import StarShaclSchema, apply_rules, target_nodes

    m = ox.NamedNode("http://e/M")
    s = ox.NamedNode("http://e/S")
    data = g("ex:a ex:p 1 . ex:c ex:r 1 .")
    shapes = g("""ex:M a sh:ShapesGraph ; rdfs:member ex:S . ex:S a sh:NodeShape ; sh:targetWhere ex:W ; sh:nodeKind sh:Literal .
      ex:W a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .""")
    ext = StarShaclSchema(shapes).extract_shapes_graph(m, include_referenced=True)
    assert set(target_nodes(data_graph=data, shacl_graph=ext, shape_node=s)) == set(
        target_nodes(data_graph=data, shacl_graph=shapes, shape_node=s)
    )
    shapes = g("""ex:M a sh:ShapesGraph ; rdfs:member ex:S . ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:c ;
      sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var 'focusNode' ] ; sh:predicate ex:q ; sh:object 5 ; sh:condition ex:W ] .
      ex:W a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .""")
    ext = StarShaclSchema(shapes).extract_shapes_graph(m, include_referenced=True)
    assert len(apply_rules(data, ext).inferred_graph) == len(apply_rules(data, shapes).inferred_graph) == 1


# --- modules keep the reifier annotation of a sh:property link


def test_module_keeps_deactivation_annotation_on_property_link():
    from starlayer.shacl import StarShaclSchema

    sg = g("""ex:M a sh:ShapesGraph ; rdfs:member ex:S .
      ex:S a sh:NodeShape ; sh:targetNode ex:n ;
        sh:property [ sh:path ex:p ; sh:minCount 1 ] {| sh:deactivated true |} .""")
    d = g("ex:n a ex:C .")
    m = ox.NamedNode("http://e/M")
    assert validate(d, sg).conforms is True
    assert validate(d, sg, shapes_graph_resource=m).conforms is True
    ext = StarShaclSchema(sg).extract_shapes_graph(m)
    assert validate(d, ext).conforms is True


def test_evaluate_ignores_property_shape_whose_link_is_deactivated():
    from starlayer.shacl import evaluate

    shapes = g(
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property ex:PS {| sh:deactivated true |} .\n"
        "ex:PS sh:path ex:echo ; sh:values [ shnex:pathValues ex:friend ] ."
    )
    out = evaluate(g("ex:alice ex:friend ex:bob ."), shapes)
    assert not list(out.triples((None, ox.NamedNode("http://e/echo"), None)))
    active = g("ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property ex:PS .\nex:PS sh:path ex:echo ; sh:values [ shnex:pathValues ex:friend ] .")
    assert list(evaluate(g("ex:alice ex:friend ex:bob ."), active).triples((None, ox.NamedNode("http://e/echo"), None)))


def test_close_shape_lets_parent_paths_through_a_shape_reused_as_node_and_or_member():
    from starlayer.shacl import StarShaclSchema, extract_subgraph

    shapes = g("""ex:Leaf a sh:NodeShape .
      ex:Root a sh:NodeShape ; sh:targetNode ex:n0 ;
        sh:property [ sh:path ex:a ; sh:node ex:Leaf ] ;
        sh:or ( ex:Leaf [ sh:property [ sh:path ex:b ; sh:minCount 1 ] ] ) .""")
    data = g("ex:n0 ex:a ex:n1 .")
    root, n0 = ox.NamedNode("http://e/Root"), ox.NamedNode("http://e/n0")
    assert validate(data, shapes).conforms
    fragment = extract_subgraph(data, shapes, shape=root, focus_node=n0)
    closed = StarShaclSchema(shapes).close_shape(root)
    assert validate(fragment, closed).conforms


def _chain(n):
    return g(
        "ex:S0 a sh:NodeShape ; sh:targetNode ex:a ; sh:node ex:S1 .\n"
        + "".join(f"ex:S{i} a sh:NodeShape ; sh:node ex:S{i + 1} .\n" for i in range(1, n))
        + f"ex:S{n} a sh:NodeShape ; sh:nodeKind sh:IRI ."
    )


def test_deep_shape_chain_is_bounded_by_max_validation_depth_not_the_interpreter():
    from starlayer.shacl import ShapeError

    data = g("ex:a ex:p 1 .")
    assert validate(data, _chain(300)).conforms is True  # under the default bound of 500
    with pytest.raises(ShapeError):
        validate(data, _chain(600))
    assert validate(data, _chain(600), max_validation_depth=None).conforms is True  # None removes the bound


def test_used_configuration_records_the_inference_regime():
    from starlayer.graph import ENTAILMENT

    shapes = g("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:nodeKind sh:IRI .")
    r = validate(g("ex:a ex:p 1 ."), shapes, inference=ENTAILMENT.RDFS, include_used_configuration=True)
    option = ox.NamedNode("urn:starlayer:shacl-engine:option:inference")
    assert [o for _, _, o in r.report_graph.triples((None, option, None))] == [ENTAILMENT.RDFS]
