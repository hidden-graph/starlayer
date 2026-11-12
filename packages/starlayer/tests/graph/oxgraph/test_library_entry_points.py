"""The library entry points that run on rdflib code accept an ``StarLayerGraph`` / ``StarLayerDataset`` / bare ``pyoxigraph.Store``.

SHACL (``validate``, ``StarShaclSchema``, ``apply_rules``, ``extract_subgraph``, ``select_widgets``, ``derive_conforms_to``), SQE and
SRL (tree encode / decode, ``RuleSet.infer`` / ``query``), ``rdfc10_hash`` and ``isomorphic``. Each takes a snapshot at the
boundary, so the answers must equal the ones for the same data held in a plain rdflib graph.
"""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

EX = "http://example.org/"
SHAPES = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property ex:NameProp .
ex:NameProp sh:path ex:name ; sh:minCount 1 .
"""
DATA = """
@prefix ex: <http://example.org/> .
ex:alice a ex:Person ; ex:name "Alice" .
ex:bob a ex:Person .
"""
FIXED_DATA = DATA.replace("ex:bob a ex:Person .", 'ex:bob a ex:Person ; ex:name "Bob" .')


def _ox(cls, text):
    g = cls()
    g.parse(data=text, format="turtle")
    return g


def _rdflib(text):
    from rdflib import Graph

    g = Graph()
    g.parse(data=text, format="turtle")
    return g


def _store(text):
    store = ox.Store()
    store.load(text.encode(), format=ox.RdfFormat.TURTLE)
    return store


KINDS = {"StarLayerGraph": lambda t: _ox(StarLayerGraph, t), "StarLayerDataset": lambda t: _ox(StarLayerDataset, t), "Store": _store}


@pytest.fixture(params=sorted(KINDS))
def kind(request):
    return KINDS[request.param]


# ---------------------------------------------------------------------------------------------------------------------
# SHACL


def test_validate_takes_oxigraph_graphs(kind):
    from starlayer.shacl import validate

    bad = validate(kind(DATA), shacl_graph=_ox(StarLayerGraph, SHAPES))
    good = validate(kind(FIXED_DATA), shacl_graph=_ox(StarLayerGraph, SHAPES))
    assert bad.conforms is False
    assert good.conforms is True
    assert bad.conforms == validate(_rdflib(DATA), shacl_graph=_rdflib(SHAPES)).conforms


def test_validate_takes_oxigraph_shapes_and_ontology(kind):
    from starlayer.shacl import validate

    onto = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . ex:Student rdfs:subClassOf ex:Person .")
    data = kind(DATA.replace("ex:bob a ex:Person", "ex:bob a ex:Student"))
    result = validate(data, shacl_graph=kind(SHAPES), ont_graph=onto, inference=ENTAILMENT.RDFS)
    assert result.conforms is False


def test_validate_inplace_writes_back_to_the_oxigraph_graph():
    from starlayer.shacl import validate

    data = _ox(StarLayerGraph, DATA.replace("ex:bob a ex:Person", "ex:bob a ex:Student"))
    onto = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . ex:Student rdfs:subClassOf ex:Person .")
    before = len(data)
    result = validate(data, shacl_graph=_ox(StarLayerGraph, SHAPES), ont_graph=onto, inference=ENTAILMENT.RDFS, inplace=True)
    assert result.data_graph is data
    assert len(data) > before


def test_schema_methods_take_oxigraph_graphs(kind):
    from starlayer.shacl import StarShaclSchema

    schema = StarShaclSchema(shacl_graph=_ox(StarLayerGraph, SHAPES))
    assert schema.validate(kind(DATA)).conforms is False
    assert schema.apply_rules(kind(DATA)).validation.conforms is False
    assert schema.evaluate(kind(DATA)) is not None


def test_schema_bound_oxigraph_graphs():
    from starlayer.shacl import StarShaclSchema

    schema = StarShaclSchema(shacl_graph=_ox(StarLayerDataset, SHAPES), data_graph=_ox(StarLayerDataset, DATA))
    assert schema.validate().conforms is False


def test_apply_rules_takes_oxigraph_graphs(kind):
    from starlayer.shacl import apply_rules

    rules = """
    @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
    ex:R a sh:NodeShape ; sh:targetClass ex:Person ;
        sh:rule [ a sh:TripleRule ; sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:kind ; sh:object ex:Human ] .
    """
    result = apply_rules(kind(DATA), shacl_graph=_ox(StarLayerGraph, rules))
    assert len(result.inferred_graph) >= 2


def test_validate_each_takes_oxigraph_graphs():
    from starlayer.shacl import validate_each

    results = validate_each([_ox(StarLayerGraph, DATA), _ox(StarLayerDataset, FIXED_DATA)], shacl_graph=_ox(StarLayerGraph, SHAPES))
    assert {k: r.conforms for k, r in results.items()} == {0: False, 1: True}


def test_extract_subgraph_takes_one_graph_and_refuses_a_dataset(kind):
    from starlayer.shacl import extract_subgraph

    want = extract_subgraph(_rdflib(FIXED_DATA), _rdflib(SHAPES))
    if kind is KINDS["StarLayerGraph"]:
        assert len(extract_subgraph(kind(FIXED_DATA), kind(SHAPES))) == len(want) > 0
    else:  # a StarLayerDataset, or a bare pyoxigraph Store (which is read as one): a fragment would not say which graph a triple is from
        with pytest.raises(TypeError, match="not a dataset"):
            extract_subgraph(kind(FIXED_DATA), kind(SHAPES))


def test_extract_subgraph_with_pyoxigraph_shape_and_focus_node():
    from starlayer.shacl import extract_subgraph

    got = extract_subgraph(
        _ox(StarLayerGraph, FIXED_DATA),
        _ox(StarLayerGraph, SHAPES),
        shape=ox.NamedNode(EX + "PersonShape"),
        focus_node=ox.NamedNode(EX + "alice"),
    )
    assert isinstance(got, StarLayerGraph)
    assert (ox.NamedNode(EX + "alice"), ox.NamedNode(EX + "name"), ox.Literal("Alice")) in got


def test_normalize_to_starlayer_graph_keeps_oxigraph_input_and_wraps_a_store(kind):
    from starlayer.shacl import normalize_to_starlayer_graph

    graph = normalize_to_starlayer_graph(kind(DATA), name="data_graph")
    assert isinstance(graph, (StarLayerGraph, StarLayerDataset))
    assert len(graph) == 3


def test_normalize_to_starlayer_graph_converts_an_old_style_graph_to_an_oxgraph():
    from starlayer.shacl import normalize_to_starlayer_graph

    graph = normalize_to_starlayer_graph(_rdflib(DATA), name="data_graph")
    assert isinstance(graph, StarLayerGraph)
    assert len(graph) == 3


def test_normalize_keeps_a_named_graph_identifier():
    from starlayer.shacl import normalize_to_starlayer_graph

    ds = _ox(StarLayerDataset, "")
    named = ds.graph(ox.NamedNode(EX + "g"))
    named.parse(data=DATA, format="turtle")
    graph = normalize_to_starlayer_graph(named, name="data_graph")
    assert graph.identifier == ox.NamedNode(EX + "g")


def test_unsupported_input_still_names_the_argument():
    from starlayer.shacl import validate

    with pytest.raises(TypeError, match="data_graph must be"):
        validate(42, shacl_graph=_rdflib(SHAPES))


def test_select_widgets_with_oxigraph_graphs():
    from rdflib import URIRef
    from starlayer.shacl.ui_widget_selection import select_widgets

    shapes = """
    @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix shui: <http://www.w3.org/ns/shacl-ui/> .
    ex:PersonShape a sh:NodeShape ; sh:property ex:NameProp .
    ex:NameProp sh:path ex:name ; shui:editor shui:TextFieldEditor .
    """
    g = _ox(StarLayerGraph, shapes)
    rdflib_style = select_widgets(shape_node=URIRef(EX + "PersonShape"), shapes_graph=g, role="editor")
    assert list(rdflib_style) == [URIRef(EX + "NameProp")]
    ox_style = select_widgets(shape_node=ox.NamedNode(EX + "PersonShape"), shapes_graph=g, role="editor")
    assert list(ox_style) == [ox.NamedNode(EX + "NameProp")]
    assert str(next(iter(ox_style.values())).value).endswith("TextFieldEditor")


def test_derive_conforms_to_takes_oxigraph_reports():
    from starlayer.shacl import validate
    from starlayer.shacl.profiling import derive_conforms_to

    result = validate(_ox(StarLayerGraph, FIXED_DATA), shacl_graph=_ox(StarLayerGraph, SHAPES), data_graph_iri=EX + "data", shapes_graph_iri=EX + "shapes")
    report = _ox(StarLayerGraph, "")
    report.extend(list(result.report_graph))
    derived = derive_conforms_to(report, conforms_only=True)
    assert len(derived) == 1


# ---------------------------------------------------------------------------------------------------------------------
# SQE


QUERY = "PREFIX ex: <http://example.org/> SELECT ?s WHERE { ?s ex:p ?o FILTER(?o > 1) }"


@pytest.mark.parametrize("cls", [StarLayerGraph, StarLayerDataset])
def test_sqe_round_trip_in_an_oxigraph_graph(cls):
    from starlayer.sparql import sqe

    tree = cls()
    graph, root = sqe.sqe_parse_to_tree(QUERY, tree)
    assert graph is tree and len(tree) > 0
    assert isinstance(root, (ox.BlankNode, ox.NamedNode))
    assert sqe.sqe_tree_to_text(tree, root) == sqe.sqe_tree_to_text(*sqe.sqe_parse_to_tree(QUERY))


def test_sqe_given_root_and_shared_graph():
    from starlayer.sparql import sqe

    tree = StarLayerGraph()
    r1 = ox.NamedNode(EX + "q1")
    r2 = ox.NamedNode(EX + "q2")
    _, got1 = sqe.sqe_parse_to_tree(QUERY, tree, r1)
    _, got2 = sqe.sqe_parse_to_tree(QUERY.replace("> 1", "> 2"), tree, r2)
    assert (got1, got2) == (r1, r2)
    assert "> 2" in sqe.sqe_tree_to_text(tree, r2) and "> 1" in sqe.sqe_tree_to_text(tree, r1)


def test_sqe_validate_takes_an_oxigraph_tree():
    from starlayer.sparql import sqe
    from starlayer.sparql.sqe.shapes import sqe_validate

    tree, _root = sqe.sqe_parse_to_tree(QUERY, StarLayerGraph())
    conforms, _report, _text = sqe_validate(tree)
    assert conforms is True


def test_sqe_root_may_be_given_as_an_rdflib_term():
    from rdflib import URIRef
    from starlayer.sparql import sqe

    tree = StarLayerGraph()
    _, root = sqe.sqe_parse_to_tree(QUERY, tree, URIRef(EX + "q"))
    assert root == ox.NamedNode(EX + "q")
    assert "SELECT" in sqe.sqe_tree_to_text(tree, URIRef(EX + "q"))


# ---------------------------------------------------------------------------------------------------------------------
# SRL

RULES = "PREFIX ex: <http://example.org/>\nRULE { ?x ex:q ?y } WHERE { ?x ex:p ?y }"
BASE = "@prefix ex: <http://example.org/> . ex:a ex:p ex:b . ex:b ex:p ex:c ."


@pytest.mark.parametrize("cls", [StarLayerGraph, StarLayerDataset])
def test_srl_infer_and_query_on_oxigraph(cls):
    from rdflib import URIRef, Variable
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(RULES)
    inferred = ruleset.infer(_ox(cls, BASE))
    assert isinstance(inferred, StarLayerGraph)
    assert set(inferred) == {
        (ox.NamedNode(EX + "a"), ox.NamedNode(EX + "q"), ox.NamedNode(EX + "b")),
        (ox.NamedNode(EX + "b"), ox.NamedNode(EX + "q"), ox.NamedNode(EX + "c")),
    }
    goal = srl.TriplePattern(subject=Variable("x"), predicate=URIRef(EX + "q"), object=Variable("y"))
    rows = ruleset.query(_ox(cls, BASE), goal)
    assert len(rows) == 2
    assert all(isinstance(v, ox.NamedNode) for row in rows for v in row.values())


def test_srl_tree_round_trip_in_an_oxigraph_graph():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(RULES)
    tree, root = srl.ruleset_to_tree(ruleset, StarLayerGraph())
    assert isinstance(tree, StarLayerGraph) and len(tree) > 0
    assert srl.ruleset_to_text(srl.tree_to_ruleset(tree, root)) == srl.ruleset_to_text(ruleset)
    assert srl.srl_tree_to_text(tree, root) == srl.srl_tree_to_text(*srl.srl_parse_to_tree(RULES))


def test_srl_infer_with_a_schema_on_oxigraph():
    from starlayer.sparql import srl

    schema = _ox(StarLayerGraph, SHAPES)
    result = srl.parse_ruleset(RULES).infer(_ox(StarLayerGraph, BASE), schema=schema)
    assert isinstance(result.inferred_graph, StarLayerGraph)
    assert result.validation.conforms is True


# ---------------------------------------------------------------------------------------------------------------------
# RDFC and isomorphism


def test_rdfc10_hash_of_oxigraph_matches_the_old_class(kind):
    from starlayer.graph.rdfc import rdfc10_hash, to_canonical_nquads

    text = '@prefix ex: <http://example.org/> . ex:a ex:p [ ex:q "x" ] . _:z ex:p [ ex:q "y" ] .'
    assert rdfc10_hash(kind(text)) == rdfc10_hash(_rdflib(text))
    assert to_canonical_nquads(kind(text)) == to_canonical_nquads(_rdflib(text))


def test_rdfc10_hash_ignores_blank_node_labels():
    from starlayer.graph.rdfc import rdfc10_hash

    a = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . _:one ex:p _:two . _:two ex:p 1 .")
    b = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . _:x ex:p _:y . _:y ex:p 1 .")
    assert rdfc10_hash(a) == rdfc10_hash(b)


def test_rdfc10_hash_of_a_dataset_counts_graph_names():
    from starlayer.graph.rdfc import rdfc10_hash

    a, b = StarLayerDataset(), StarLayerDataset()
    quad_text = "<http://example.org/s> <http://example.org/p> <http://example.org/o> <http://example.org/%s> ."
    a.parse(data=quad_text % "g1", format="nquads")
    b.parse(data=quad_text % "g2", format="nquads")
    assert rdfc10_hash(a) != rdfc10_hash(b)
    assert rdfc10_hash(a) == rdfc10_hash(_ox_nquads(quad_text % "g1"))


def _ox_nquads(text):
    ds = StarLayerDataset()
    ds.parse(data=text, format="nquads")
    return ds


def test_isomorphic_across_graph_classes():
    from starlayer.graph.compare import isomorphic

    a = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . ex:s ex:p [ ex:q 1 ] .")
    b = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . ex:s ex:p [ ex:q 1 ] .")
    c = _ox(StarLayerGraph, "@prefix ex: <http://example.org/> . ex:s ex:p [ ex:q 2 ] .")
    assert isomorphic(a, b)
    assert not isomorphic(a, c)
    assert isomorphic(a, _rdflib("@prefix ex: <http://example.org/> . ex:s ex:p [ ex:q 1 ] ."))


def test_isomorphic_with_a_triple_term():
    from starlayer.graph.compare import isomorphic

    text = "@prefix ex: <http://example.org/> . ex:s ex:says <<( ex:a ex:p ex:b )>> ."
    assert isomorphic(_ox(StarLayerGraph, text), _ox(StarLayerGraph, text))
    assert not isomorphic(_ox(StarLayerGraph, text), _ox(StarLayerGraph, text.replace("ex:b", "ex:c")))


def test_ruleset_to_text_takes_prefixes_from_an_oxigraph_graph():
    from starlayer.sparql import srl

    ruleset = srl.parse_ruleset(RULES)
    graph = _ox(StarLayerGraph, BASE)
    assert "ex:q" in srl.ruleset_to_text(ruleset, namespace_manager=graph)
    assert "ex:q" in srl.ruleset_to_text(ruleset, namespace_manager={"ex": EX})
    assert "ex:q" not in srl.ruleset_to_text(ruleset)
