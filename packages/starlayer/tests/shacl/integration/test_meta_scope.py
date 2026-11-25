"""The public scoped meta check: ``meta_validate(shapes, add=, remove=, full=)`` checks a proposed edit before it is made, narrowly
when the edit is local and in full when it is risky; ``full=True`` forces the whole graph. The machinery behind it (``nodes=``,
``with_dependents=``) is internal and tested in ``tests/shacl/engine/test_meta_scope_engine.py``."""

import dataclasses
import time

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaScope, MetaShaclError, meta_scope, meta_validate
from starlayer.shacl.engine.terms import SH, to_engine

SHNS = str(SH)
EX = "http://example.org/"
XSD = "http://www.w3.org/2001/XMLSchema#"
PREFIX = (f"@prefix sh: <{SHNS}> . @prefix ex: <{EX}> . @prefix xsd: <{XSD}> . "
          "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n")
RDFTYPE = to_engine(ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"))


def iri(name):
    return ox.NamedNode(EX + name)


def lit(text):
    return ox.Literal(text)


def graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=PREFIX + ttl, format="turtle")
    return g


def generated(n: int, extra: str = "") -> Graph:
    lines = [
        f"ex:S{i} a sh:NodeShape ; sh:targetClass ex:T{i} ; sh:property "
        "[ sh:path ex:a ; sh:datatype xsd:string ; sh:minCount 1 ] , [ sh:path ex:b ; sh:datatype xsd:integer ; sh:maxCount 2 ] ."
        for i in range(n)
    ]
    return graph("\n".join(lines) + extra)


def refused(g, **kwargs) -> MetaShaclError:
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(g, **kwargs)
    return raised.value


def snapshot(g):
    return set(g.triples((None, None, None)))


def _time(call):
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def _new_shape_edit():
    new, p1 = iri("New"), ox.BlankNode()
    return [
        (new, RDFTYPE, to_engine(SH.NodeShape)), (new, to_engine(SH.targetClass), iri("NewClass")),
        (new, to_engine(SH.property), p1), (p1, to_engine(SH.path), iri("a")),
        (p1, to_engine(SH.datatype), ox.NamedNode(XSD + "string")),
    ]


PREFIXED = """
ex:Prefixes a owl:Ontology ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
ex:Query a sh:NodeShape ; sh:targetClass ex:Q ; sh:sparql [ sh:select "SELECT $this WHERE { $this a ex:Q }" ; sh:prefixes ex:Prefixes ] .
"""

DEFECT = "ex:Dup a sh:NodeShape ; sh:targetClass ex:Dup ; sh:property [ sh:path ex:a ; sh:datatype xsd:string , xsd:integer ] ."


def test_the_signatures_have_add_remove_full_and_meta_shapes_extra_only():
    g = generated(3)
    assert meta_validate(g).conforms and meta_validate(g, add=(), remove=(), full=False, meta_shapes_extra=()).conforms
    meta_scope(g, add=(), remove=(), full=False)
    for keyword in ({"nodes": [iri("S1")]}, {"with_dependents": False}, {"allow_warnings": True}):
        with pytest.raises(TypeError):
            meta_validate(g, **keyword)
    for keyword in ({"nodes": [iri("S1")]}, {"with_dependents": False}):
        with pytest.raises(TypeError):
            meta_scope(g, **keyword)


def test_meta_scope_and_the_scope_of_an_error_stay_public():
    g = generated(10, DEFECT)
    assert dataclasses.is_dataclass(MetaScope) and {"full", "nodes", "reasons"} <= {f.name for f in dataclasses.fields(MetaScope)}
    name = [(iri("S3"), to_engine(SH.name), lit("three"))]
    narrow = meta_scope(g, add=name)
    assert isinstance(narrow, MetaScope) and not narrow.full and iri("S3") in narrow.nodes
    forced = meta_scope(g, add=name, full=True)
    assert forced.full and forced.nodes == () and forced.reasons == ("full check: requested",)
    assert meta_scope(g).full and meta_scope(g, full=True).full
    assert meta_scope(g, add=name) == meta_scope(g, add=name)
    # a valid narrow edit returns only the report; meta_scope is how a caller learns what it covered
    ok = meta_validate(generated(10), add=name)
    assert ok.conforms is True
    error = refused(g, add=name, full=True)
    assert error.scope == forced
    assert refused(g, add=[(iri("S3"), to_engine(SH.pattern), lit("[unclosed"))]).scope == meta_scope(
        g, add=[(iri("S3"), to_engine(SH.pattern), lit("[unclosed"))])


def test_a_failing_check_carries_the_report_the_problems_and_the_scope():
    error = refused(graph(DEFECT))
    assert error.scope.full and error.problems and error.report_text.startswith("Validation Report") and error.report_graph is not None
    assert str(error).startswith("The shapes graph is not valid SHACL")


def test_a_prefix_edit_is_checked_in_full_automatically_and_finds_the_query_in_another_node():
    g = graph(PREFIXED)
    assert meta_validate(g).conforms
    entry = next(iter(g.objects(iri("Prefixes"), to_engine(SH.declare))))
    edit = {"remove": [(entry, to_engine(SH.prefix), lit("ex"))], "add": [(entry, to_engine(SH.prefix), lit("other"))]}
    error = refused(g, **edit)  # a risky edit: no full= needed
    assert error.scope.full and "sh:prefix" in error.scope.reasons[0]
    assert error.scope.full and "sh:prefix" in error.scope.reasons[0]
    assert any("Query" in line for line in error.problems), error.problems
    assert meta_validate(g).conforms  # the graph was not changed


def test_full_true_on_a_harmless_edit_also_reports_a_defect_elsewhere_the_default_does_not():
    g = generated(20, DEFECT)
    add = [(iri("S3"), to_engine(SH.name), lit("three"))]
    assert meta_validate(g, add=add).conforms is True  # the narrow check sees only S3 and what refers to it
    error = refused(g, add=add, full=True)
    assert any("Dup" in line for line in error.problems), error.problems
    # with no edit the default and full=True agree
    assert refused(g).problems == refused(g, full=True).problems
    assert refused(g).scope.full and refused(g, full=True).scope.full
    assert refused(g).scope.full and refused(g, full=True).scope.full
    assert meta_validate(generated(5), full=True).conforms and meta_validate(generated(5), add=add[:0], full=True).conforms


def test_full_true_checks_the_graph_as_it_would_be_after_the_edit():
    g = generated(10)
    prop = next(p for p in g.objects(iri("S3"), to_engine(SH.property)) if (p, to_engine(SH.path), iri("a")) in g)
    error = refused(g, add=[(prop, to_engine(SH.datatype), ox.NamedNode(XSD + "integer"))], full=True)
    assert error.problems
    fixed = generated(10, DEFECT)
    dup_prop = next(iter(fixed.objects(iri("Dup"), to_engine(SH.property))))
    ok = meta_validate(fixed, remove=[(dup_prop, to_engine(SH.datatype), ox.NamedNode(XSD + "integer"))], full=True)
    assert ok.conforms is True
    assert refused(fixed).problems  # the caller's graph still has the defect


def test_an_edit_adding_a_second_datatype_is_refused_before_it_is_made():
    g = generated(20)
    before = snapshot(g)
    prop = next(p for p in g.objects(iri("S3"), to_engine(SH.property)) if (p, to_engine(SH.path), iri("a")) in g)
    assert meta_validate(g).conforms
    error = refused(g, add=[(prop, to_engine(SH.datatype), ox.NamedNode(XSD + "integer"))])
    assert error.problems and all(line for line in error.problems)
    refused(g, remove=[(prop, to_engine(SH.path), iri("a"))])  # a property shape without sh:path
    refused(g, add=[(prop, to_engine(SH.pattern), lit("[unclosed"))])  # a pattern that does not compile
    assert snapshot(g) == before and meta_validate(g).conforms


def test_an_edit_that_fixes_a_defect_conforms_and_the_graph_keeps_it():
    g = generated(20, DEFECT)
    assert refused(g).problems
    prop = next(iter(g.objects(iri("Dup"), to_engine(SH.property))))
    fixed = meta_validate(g, remove=[(prop, to_engine(SH.datatype), ox.NamedNode(XSD + "integer"))])
    assert fixed.conforms is True and isinstance(fixed.report_text, str)
    assert refused(g).problems


def test_a_node_that_is_not_in_the_graph_has_nothing_to_check():
    assert meta_validate(generated(3), remove=[(iri("Gone"), to_engine(SH.name), lit("x"))]).conforms


def test_an_rdflib_graph_is_refused():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError):
        meta_validate(rdflib.Graph(), add=[(iri("S"), to_engine(SH.name), lit("x"))])


def test_a_new_node_shape_in_2000_shapes_is_fast_by_default_and_full_true_takes_the_full_time(capsys):
    g = generated(2000)
    before = len(g)
    add = _new_shape_edit()
    assert meta_validate(g, add=add).conforms  # warm
    narrow = min(_time(lambda: meta_validate(g, add=add)) for _ in range(3))
    full = min(_time(lambda: meta_validate(g, add=add, full=True)) for _ in range(2))
    with capsys.disabled():
        print(f"\nnew node shape in 2000 shapes: default {narrow:.3f} s, full=True {full:.3f} s")
    assert narrow < 0.200, narrow
    assert full > 10 * narrow, (narrow, full)
    assert len(g) == before and not list(g.triples((iri("New"), None, None)))
