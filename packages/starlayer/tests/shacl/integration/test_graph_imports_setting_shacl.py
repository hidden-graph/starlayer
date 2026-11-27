"""SHACL consumers read ``owl:imports`` from the graph (maintainer decision 2026-11-26): the loader and flag a graph carries
(``StarLayerGraph(imports_loader=..., ignore_imports=...)``) decide for the data, shapes and ontology graphs of ``validate()`` and of the
other readers of the shapes graph; ``imports_loader=`` / ``ignore_imports=`` on a call override them."""

from __future__ import annotations

import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import ENTAILMENT, StarLayerGraph
from starlayer.shacl import (
    StarShaclProcessor,
    close_shape,
    derive_shape,
    evaluate,
    extract_subgraph,
    select_widgets,
    target_nodes,
    target_shapes,
    validate,
)
from tests.support.terms import NamedNode, Namespace

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
LIB = NamedNode("http://example.org/lib")
PREFIXES = """
@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def graph(text: str, **kw) -> StarLayerGraph:
    g = StarLayerGraph(**kw)
    g.parse(data=PREFIXES + text, format="turtle")
    return g


class Loader:
    def __init__(self, graphs: dict) -> None:
        self.graphs, self.calls = graphs, []

    def __call__(self, iri):
        self.calls.append(iri)
        return self.graphs.get(iri)


def lib_shapes() -> Loader:
    """A module that holds the shape of ``ex:Person`` (``ex:name`` is required)."""
    return Loader({LIB: graph("""<http://example.org/lib> a owl:Ontology .
        ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .""")})


def shapes_importing(**kw) -> StarLayerGraph:
    return graph("<http://example.org/shapes> a owl:Ontology ; owl:imports <http://example.org/lib> .", **kw)


def data(**kw) -> StarLayerGraph:
    return graph("ex:alice a ex:Person .", **kw)  # no ex:name: the imported shape is violated


def test_imports_loader_on_the_graph_is_used():
    loader = lib_shapes()
    report = validate(data(), shapes_importing(imports_loader=loader))
    assert not report.conforms and loader.calls == [LIB]


def test_shapes_graph_without_loader_raises_and_flag_skips():
    with pytest.raises(ExecutionError) as e:
        validate(data(), shapes_importing())
    assert e.value.kind == "import" and e.value.unresolved == (LIB,)
    assert validate(data(), shapes_importing(ignore_imports=True)).conforms  # nothing imported: no shape applies


def test_call_overrides_the_graph_setting():
    own, other = lib_shapes(), lib_shapes()
    shapes = shapes_importing(imports_loader=own)
    assert not validate(data(), shapes, imports_loader=other).conforms
    assert other.calls == [LIB] and own.calls == []
    assert validate(data(), shapes, ignore_imports=True).conforms  # the call's flag beats a graph with a loader
    skipping = shapes_importing(ignore_imports=True, imports_loader=own)
    assert not validate(data(), skipping, ignore_imports=False).conforms  # and the other way


def test_data_graph_is_resolved_too():
    d = graph("<http://example.org/data> owl:imports <http://example.org/missing> . ex:alice a ex:Person ; ex:name 'A' .")
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:Person .")
    with pytest.raises(ExecutionError) as e:
        validate(d, shapes)
    assert e.value.kind == "import" and e.value.unresolved == (NamedNode("http://example.org/missing"),)
    d.ignore_imports = True
    assert validate(d, shapes).conforms


def test_data_graph_imports_feed_entailment_not_the_data():
    ont = Loader({LIB: graph("<http://example.org/lib> a owl:Ontology . ex:Student rdfs:subClassOf ex:Person .")})
    d = graph("<http://example.org/data> owl:imports <http://example.org/lib> . ex:bob a ex:Student .", imports_loader=ont)
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    assert validate(d, shapes).conforms  # without a regime bob is not a Person: no focus node
    report = validate(d, shapes, inference=ENTAILMENT.RDFS)
    assert not report.conforms  # with it the imported subclass axiom makes bob a Person
    assert len(d) == 2  # the data graph did not gain the imported triples


def test_ont_graph_is_resolved_from_its_own_loader():
    ont = graph("<http://example.org/ont> owl:imports <http://example.org/lib> .", imports_loader=Loader(
        {LIB: graph("<http://example.org/lib> a owl:Ontology . ex:Student rdfs:subClassOf ex:Person .")}))
    d = graph("ex:bob a ex:Student .")
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    assert not validate(d, shapes, ont, inference=ENTAILMENT.RDFS).conforms
    bare = graph("<http://example.org/ont> owl:imports <http://example.org/lib> .")
    with pytest.raises(ExecutionError):
        validate(d, shapes, bare, inference=ENTAILMENT.RDFS)


def test_processor_uses_the_graph_setting_and_constructor_and_call_override():
    loader = lib_shapes()
    processor = StarShaclProcessor(shapes_importing(imports_loader=loader))
    assert not processor.validate(data()).conforms
    bare = shapes_importing()
    p2 = StarShaclProcessor(bare)  # built without a loader: a call may still bring one (as before)
    assert not p2.validate(data(), imports_loader=lib_shapes()).conforms
    p3 = StarShaclProcessor(bare, imports_loader=lib_shapes())
    assert not p3.validate(data()).conforms
    assert p3.validate(data(), ignore_imports=True).conforms


# ---- the six readers of the shapes graph --------------------------------------------------------------------------

def test_target_nodes_and_target_shapes_resolve_the_shapes_graph():
    shapes = shapes_importing(imports_loader=lib_shapes())
    assert target_nodes(data_graph=data(), shacl_graph=shapes, shape_node=EX.PersonShape) == (EX.alice,)
    assert target_shapes(data_graph=data(), shacl_graph=shapes, node=EX.alice) == (EX.PersonShape,)
    with pytest.raises(ExecutionError):
        target_nodes(data_graph=data(), shacl_graph=shapes_importing(), shape_node=EX.PersonShape)
    got = target_nodes(data_graph=data(), shacl_graph=shapes_importing(), shape_node=EX.PersonShape, imports_loader=lib_shapes())
    assert got == (EX.alice,)
    # with the imports ignored the shape is not in the graph: it has no focus nodes
    assert target_nodes(data_graph=data(), shacl_graph=shapes_importing(), shape_node=EX.PersonShape, ignore_imports=True) == ()


def test_evaluate_resolves_the_shapes_graph():
    lib = Loader({LIB: graph("""<http://example.org/lib> a owl:Ontology .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:label ; sh:defaultValue "anon" ] .""")})
    out = evaluate(data(), shapes_importing(imports_loader=lib))
    assert (EX.alice, EX.label) in {(s, p) for s, p, _ in out.triples((None, None, None))}
    with pytest.raises(ExecutionError):
        evaluate(data(), shapes_importing())
    assert not list(evaluate(data(), shapes_importing(), ignore_imports=True).triples((None, None, None)))
    assert list(evaluate(data(), shapes_importing(), imports_loader=lib).triples((None, None, None)))


def test_extract_subgraph_resolves_the_shapes_graph():
    d = graph("ex:alice a ex:Person ; ex:name 'A' ; ex:other 'x' .")
    shapes = shapes_importing(imports_loader=lib_shapes())
    assert len(extract_subgraph(d, shapes)) > 0
    with pytest.raises(ExecutionError):
        extract_subgraph(d, shapes_importing())
    assert len(extract_subgraph(d, shapes_importing(), imports_loader=lib_shapes())) > 0
    assert len(extract_subgraph(d, shapes_importing(), ignore_imports=True)) == 0


def test_close_shape_resolves_the_shapes_graph_and_holds_the_imported_shapes():
    closed = close_shape(shapes_importing(imports_loader=lib_shapes()), EX.PersonShape)
    assert (EX.PersonShape, SH.closed, None) in closed or any(True for _ in closed.triples((EX.PersonShape, SH.closed, None)))
    with pytest.raises(ExecutionError):
        close_shape(shapes_importing(), EX.PersonShape)
    assert any(True for _ in close_shape(shapes_importing(), EX.PersonShape, imports_loader=lib_shapes()).triples((EX.PersonShape, SH.closed, None)))
    processor = StarShaclProcessor(shapes_importing(imports_loader=lib_shapes()))
    assert any(True for _ in processor.close_shape(EX.PersonShape).triples((EX.PersonShape, SH.closed, None)))


def test_select_widgets_resolves_the_shapes_graph():
    lib = Loader({LIB: graph("""<http://example.org/lib> a owl:Ontology .
        ex:S a sh:NodeShape ; sh:property ex:p1 . ex:p1 sh:path ex:name .""")})
    shapes = shapes_importing(imports_loader=lib)
    assert set(select_widgets(shape_node=EX.S, shapes_graph=shapes, role="editor")) == {EX.p1}
    with pytest.raises(ExecutionError):
        select_widgets(shape_node=EX.S, shapes_graph=shapes_importing(), role="editor")
    got = select_widgets(shape_node=EX.S, shapes_graph=shapes_importing(), role="editor", imports_loader=lib)
    assert set(got) == {EX.p1}
    processor = StarShaclProcessor(shapes_importing(imports_loader=lib))
    assert set(processor.select_widgets(shape_node=EX.S, role="editor")) == {EX.p1}


def test_derive_shape_resolves_the_data_and_template_graphs():
    d = graph("ex:alice a ex:Person ; ex:name 'A' .")
    template = shapes_importing(imports_loader=lib_shapes())
    assert derive_shape(d, shape=EX.PersonShape, template_graph=template) is not None
    with pytest.raises(ExecutionError):
        derive_shape(d, shape=EX.PersonShape, template_graph=shapes_importing())
    bare = graph("<http://example.org/data> owl:imports <http://example.org/missing> . ex:alice a ex:Person ; ex:name 'A' .")
    with pytest.raises(ExecutionError):
        derive_shape(bare, cls=EX.Person)
    assert derive_shape(bare, cls=EX.Person, ignore_imports=True) is not None
