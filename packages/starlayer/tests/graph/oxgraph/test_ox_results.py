"""Every library function that takes a graph and returns one gives an ``StarLayerGraph`` (pyoxigraph terms), whatever class went in
(a plain rdflib graph input is converted; nothing returns an rdflib graph).

Covers every library function that takes a graph and returns one (or a result holding one): SHACL ``validate`` /
``apply_rules`` / ``evaluate`` / ``extract_subgraph`` / ``derive_conforms_to`` / ``infer_types`` / ``meta_validate``, the
SQE / SRL / Manchester tree and validate functions, and the ``starontology`` getters. The results carry the prefixes of the input and those their IRIs use, not the 29 default bindings of an rdflib graph.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from rdflib import Graph as RdflibGraph
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:NameProp .
ex:NameProp sh:path ex:name ; sh:minCount 1 .
"""
RULES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:R a sh:NodeShape ; sh:targetClass ex:Person ;
    sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:kind ; sh:object ex:Human ] .
"""
DATA = """@prefix ex: <http://example.org/> .
ex:alice a ex:Person ; ex:name "Alice" .
ex:bob a ex:Person .
"""


def _load(cls, text):
    g = cls()
    g.parse(data=text, format="turtle")
    return g


def _ox(text, cls=StarLayerGraph):
    return _load(cls, text)


def _rdflib(text):
    """The same document in a plain rdflib graph: the input a caller who has not moved to StarLayerGraph still passes."""
    return _load(RdflibGraph, text)


def assert_ox(graph, *, max_prefixes=8):
    assert isinstance(graph, StarLayerGraph), type(graph)
    assert len(graph.prefixes) <= max_prefixes, sorted(graph.prefixes)
    for s, p, o in graph:
        assert isinstance(s, (ox.NamedNode, ox.BlankNode, ox.Triple))
        assert isinstance(p, ox.NamedNode)
        assert isinstance(o, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple))


# ---------------------------------------------------------------------------------------------------------------------
# SHACL


@pytest.mark.parametrize("cls", [StarLayerGraph, StarLayerDataset])
def test_validate_report_graph(cls):
    from starlayer.shacl import validate

    result = validate(_ox(DATA, cls), shacl_graph=_ox(SHAPES))
    assert result.conforms is False
    assert_ox(result.report_graph)
    assert "sh" in result.report_graph.prefixes and "ex" in result.report_graph.prefixes
    assert ox.NamedNode("http://www.w3.org/ns/shacl#ValidationReport") in set(result.report_graph.objects())


def test_validate_with_a_bare_store():
    from starlayer.shacl import validate

    store = ox.Store()
    store.load(DATA.encode(), format=ox.RdfFormat.TURTLE)
    assert_ox(validate(store, shacl_graph=_ox(SHAPES)).report_graph)


def test_validate_old_class_in_ox_out():
    from starlayer.shacl import validate

    result = validate(_rdflib(DATA), shacl_graph=_rdflib(SHAPES))
    assert_ox(result.report_graph, max_prefixes=40)  # the old shapes graph's 29 default prefixes come along


def test_validate_inplace_keeps_the_callers_graph():
    from starlayer.shacl import validate

    data = _ox(DATA)
    result = validate(data, shacl_graph=_ox(SHAPES), inplace=True)
    assert result.data_graph is data
    assert_ox(result.report_graph)


def test_schema_validate_and_validate_each():
    from starlayer.shacl import StarShaclSchema

    schema = StarShaclSchema(shacl_graph=_ox(SHAPES))
    assert_ox(schema.validate(data_graph=_ox(DATA)).report_graph)
    assert all(isinstance(r.report_graph, StarLayerGraph) for r in schema.validate_each([_ox(DATA)]).values())


def test_schema_with_old_shapes_and_ox_data_returns_ox():
    from starlayer.shacl import StarShaclSchema

    result = StarShaclSchema(shacl_graph=_rdflib(SHAPES)).validate(data_graph=_ox(DATA))
    assert_ox(result.report_graph, max_prefixes=40)  # the old shapes graph's 29 default prefixes come along


def test_schema_old_in_ox_out():
    from starlayer.shacl import StarShaclSchema

    schema = StarShaclSchema(shacl_graph=_rdflib(SHAPES))
    assert_ox(schema.validate(data_graph=_rdflib(DATA)).report_graph, max_prefixes=40)
    assert_ox(schema.apply_rules(data_graph=_rdflib(DATA)).inferred_graph, max_prefixes=40)


@pytest.mark.parametrize("cls", [StarLayerGraph, StarLayerDataset])
def test_apply_rules_inferred_and_report_graphs(cls):
    from starlayer.shacl import StarShaclSchema, apply_rules

    for result in (
        StarShaclSchema(shacl_graph=_ox(RULES)).apply_rules(data_graph=_ox(DATA, cls)),
        apply_rules(_ox(DATA, cls), shacl_graph=_ox(RULES)),
    ):
        assert_ox(result.inferred_graph)
        assert_ox(result.validation.report_graph)
        kind = ox.NamedNode("http://example.org/kind")
        assert {t[1] for t in result.inferred_graph} >= {kind}


def test_apply_rules_accepts_a_plain_rdflib_graph_and_names_the_accepted_classes_for_anything_else():
    import rdflib
    from starlayer.shacl import apply_rules

    assert_ox(apply_rules(rdflib.Graph(), shacl_graph=_rdflib(RULES)).inferred_graph, max_prefixes=40)
    with pytest.raises(TypeError, match="StarLayerGraph"):
        apply_rules(42, shacl_graph=_rdflib(RULES))


def test_evaluate_and_close_shape():
    from starlayer.shacl import StarShaclSchema, evaluate

    shapes = _ox(SHAPES)
    assert_ox(evaluate(_ox(DATA), shapes))
    schema = StarShaclSchema(shacl_graph=shapes)
    assert_ox(schema.evaluate(_ox(DATA)))
    assert_ox(schema.close_shape(ox.NamedNode("http://example.org/PersonShape")))
    assert_ox(evaluate(_rdflib(DATA), _rdflib(SHAPES)), max_prefixes=40)


def test_extract_subgraph():
    from starlayer.shacl import extract_subgraph

    got = extract_subgraph(_ox(DATA), _ox(SHAPES))
    assert_ox(got)
    assert len(got) > 0
    assert_ox(extract_subgraph(_rdflib(DATA), _rdflib(SHAPES)), max_prefixes=40)


def test_derive_conforms_to():
    from starlayer.shacl import validate
    from starlayer.shacl.profiling import derive_conforms_to

    report = validate(_ox(DATA.replace("ex:bob a ex:Person", "ex:bob a ex:Thing")), shacl_graph=_ox(SHAPES)).report_graph
    got = derive_conforms_to(report, data_graph="http://example.org/d", shapes_graph="http://example.org/s")
    assert_ox(got)
    old = validate(_rdflib(DATA.replace("ex:bob a ex:Person", "ex:bob a ex:Thing")), shacl_graph=_rdflib(SHAPES)).report_graph
    assert_ox(derive_conforms_to(old, data_graph="http://example.org/d", shapes_graph="http://example.org/s"), max_prefixes=40)


def test_infer_types_and_meta_validate():
    from starlayer.shacl.meta_shapes import meta_validate
    from starlayer.shacl.shape_types import infer_types

    assert_ox(infer_types(_ox(SHAPES)))
    assert_ox(infer_types(_rdflib(SHAPES)), max_prefixes=40)
    conforms, report, _text = meta_validate(_ox(SHAPES))
    assert isinstance(conforms, bool)
    assert_ox(report, max_prefixes=15)  # the meta shapes graph's own prefixes come along


# ---------------------------------------------------------------------------------------------------------------------
# starontology getters (no graph input: a keyword picks the class)


def test_starontology_getters_return_oxgraphs():
    from starlayer import starontology

    graph = starontology.get_ontology_graph("shacl_shacl")
    assert_ox(graph, max_prefixes=15)
    assert len(graph) > 0
    assert_ox(starontology.get_conformance_profiles(), max_prefixes=15)


def test_declared_conformance_profile_and_expr_validation_getters():
    from starlayer.shacl.profiling import declared_conformance_profile
    from starlayer.sparql import expr_validation

    assert_ox(declared_conformance_profile(), max_prefixes=15)
    assert_ox(expr_validation.shapes_graph(), max_prefixes=15)
    assert_ox(expr_validation.ontology_graph(), max_prefixes=15)


def test_ontology_graph_validates_as_data():
    """An ontology got as an StarLayerGraph is an ordinary StarLayerGraph: it can be the data or the shapes of a validation."""
    from starlayer import starontology
    from starlayer.shacl import validate

    shapes = starontology.get_ontology_graph("shacl_shacl")
    result = validate(_ox(SHAPES), shacl_graph=shapes, ignore_imports=True)
    assert_ox(result.report_graph, max_prefixes=20)  # the shapes graph's own prefixes come along


# ---------------------------------------------------------------------------------------------------------------------
# SQE / SRL / Manchester


def test_sqe_tree_and_validate():
    from starlayer.sparql.parse_sparql import sparql_to_tree
    from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_validate

    graph, root = sqe_parse_to_tree("SELECT * WHERE { ?s ?p ?o }", StarLayerGraph())
    assert_ox(graph)
    assert isinstance(root, ox.BlankNode)
    ok, report, _text = sqe_validate(graph)
    assert ok is True
    assert_ox(report)
    graph, root = sparql_to_tree("SELECT * WHERE { ?s ?p ?o }", graph=StarLayerGraph())
    assert_ox(graph)
    assert isinstance(root, ox.BlankNode)
    default_graph, _ = sqe_parse_to_tree("SELECT * WHERE { ?s ?p ?o }")
    assert isinstance(default_graph, StarLayerGraph)  # the tree builders default to an StarLayerGraph
    rdflib_graph, _ = sqe_parse_to_tree("SELECT * WHERE { ?s ?p ?o }", graph=RdflibGraph())
    assert isinstance(rdflib_graph, RdflibGraph) and not isinstance(rdflib_graph, StarLayerGraph)  # an rdflib graph is filled as it is
    assert_ox(sqe_validate(rdflib_graph)[1], max_prefixes=40)


def test_srl_tree_and_validate():
    from starlayer.sparql.srl import srl_parse_to_tree, srl_validate

    text = "RULE { ?x <http://e/q> ?y } WHERE { ?x <http://e/p> ?y }"
    graph, root = srl_parse_to_tree(text, graph=StarLayerGraph())
    assert_ox(graph)
    assert isinstance(root, ox.BlankNode)
    ok, report, _text = srl_validate(graph)
    assert_ox(report)
    default_graph, _ = srl_parse_to_tree(text)
    assert isinstance(default_graph, RdflibGraph) and not isinstance(default_graph, StarLayerGraph)  # the default is a plain rdflib Graph
    assert_ox(srl_validate(default_graph)[1], max_prefixes=40)


def test_srl_infer_with_schema_returns_ox_parts():
    from starlayer.shacl import RulesResult
    from starlayer.sparql.srl import parse_ruleset

    rules = parse_ruleset("PREFIX ex: <http://example.org/>\nRULE { ?x ex:kind ex:Human } WHERE { ?x a ex:Person }")
    inferred = rules.infer(_ox(DATA))
    assert_ox(inferred)
    result = rules.infer(_ox(DATA), schema=_ox(SHAPES))
    assert isinstance(result, RulesResult)
    assert_ox(result.inferred_graph)
    assert_ox(result.validation.report_graph)


MANCHESTER = "Class: <http://e/A> SubClassOf: <http://e/B>"


def test_manchester_tree_functions():
    from starlayer.starontology import manchester

    tree = manchester.manchester_parse_to_tree(MANCHESTER, graph=StarLayerGraph())
    assert_ox(tree)
    assert "manch" in tree.prefixes
    owl = manchester.manchester_tree_to_owl(tree)
    assert_ox(owl)
    assert ox.NamedNode("http://e/A") in set(owl.subjects())
    ok, report, _text = manchester.manchester_validate(tree)
    assert ok is True
    assert_ox(report)
    default_tree = manchester.manchester_parse_to_tree(MANCHESTER)
    assert isinstance(default_tree, StarLayerGraph)  # the default is an StarLayerGraph
    rdflib_tree = manchester.manchester_parse_to_tree(MANCHESTER, graph=RdflibGraph())
    assert isinstance(rdflib_tree, RdflibGraph) and not isinstance(rdflib_tree, StarLayerGraph)  # an rdflib graph is filled as it is
    assert isinstance(manchester.manchester_tree_to_owl(rdflib_tree), StarLayerGraph)
    assert_ox(manchester.manchester_validate(rdflib_tree)[1], max_prefixes=40)
    assert manchester.manchester_tree_to_text(tree) == manchester.manchester_tree_to_text(rdflib_tree)
    assert manchester.manchester_tree_to_text(tree) == manchester.manchester_tree_to_text(default_tree)


def test_skos_validate():
    from starlayer.starontology import skos

    data = _ox("@prefix skos: <http://www.w3.org/2004/02/skos/core#> . <http://e/c> a skos:Concept ; skos:prefLabel 'c'@en .")
    ok, report, _text = skos.skos_validate(data)
    assert_ox(report)
    assert_ox(skos.skos_validate(RdflibGraph())[1], max_prefixes=40)


# ---------------------------------------------------------------------------------------------------------------------
# already StarLayerGraph: the graph/ helpers (guard against regressions)


def test_graph_helpers_return_ox():
    from starlayer.graph import ENTAILMENT

    g = _ox(DATA)
    assert_ox(g.infer(ENTAILMENT.RDFS))
    assert_ox(g.cbd(ox.NamedNode("http://example.org/alice")))
