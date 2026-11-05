"""Meta-validation (SHACL-SHACL run by the engine) and ``owl:imports`` resolution."""

from __future__ import annotations

import pytest
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine.imports import declared_imports, resolve_imports
from starlayer.shacl_engine.meta import META_ERROR_PREFIX, MetaShaclError, meta_validate
from starlayer.shacl_engine.terms import OWL, RDF

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"


def _g(ttl: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + ttl, format="turtle")


GOOD = [
    "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:datatype xsd:string ] .",
    "ex:S a sh:NodeShape ; sh:closed sh:ByTypes .",
    "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:disjoint ( ex:q ex:r ) ] .",
    "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:lessThan ( ex:q ex:r ) ] .",
    "ex:S a sh:NodeShape ; sh:class ( ex:A ex:B ) .",
]
BAD = [
    "ex:S a sh:NodeShape ; sh:property [ sh:minCount 1 ; sh:datatype xsd:integer ] .",  # no sh:path
    "ex:S a sh:NodeShape ; sh:uniqueValuesFor \"not a property\" .",
    "ex:S a sh:NodeShape ; sh:in () ; sh:xone () .",
    "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount \"x\" ] .",
]


@pytest.mark.parametrize("ttl", GOOD)
def test_well_formed_shapes_graph_conforms(ttl):
    result = meta_validate(_g(ttl))
    assert result.conforms, result.report_text
    result.raise_if_invalid()


@pytest.mark.parametrize("ttl", BAD)
def test_ill_formed_shapes_graph_raises_with_the_old_message(ttl):
    result = meta_validate(_g(ttl))
    assert not result.conforms
    with pytest.raises(MetaShaclError, match="MetaSHACL") as exc:
        result.raise_if_invalid()
    assert str(exc.value).startswith(META_ERROR_PREFIX)


def test_meta_validate_does_not_modify_the_shapes_graph():
    g = _g(BAD[0])
    before = set(g)
    meta_validate(g)
    assert set(g) == before


def test_extra_meta_shapes_are_added():
    g = _g("ex:S a sh:NodeShape ; ex:flag true .")
    assert meta_validate(g).conforms
    extra = _g(
        "ex:Extra a sh:NodeShape ; sh:targetClass sh:NodeShape ; "
        "sh:property [ sh:path ex:flag ; sh:datatype xsd:string ] ."
    )
    assert not meta_validate(g, extra=(extra,)).conforms


def test_engine_validate_is_injectable():
    calls = []

    class Out:
        conforms = True
        report_graph = None
        results: list = []

    def fake(data, shapes, **kw):
        calls.append((data, shapes, kw))
        return Out()

    g = _g(GOOD[0])
    assert meta_validate(g, engine_validate=fake).conforms
    assert calls and calls[0][0] is g


# ---------------------------------------------------------------- imports

APP, V2, COMPANY, BASE = (URIRef(f"http://example.com/shapes/{n}") for n in ("myapp", "company/v2", "company", "base"))


def _app() -> StarLayerGraph:
    return _g("<http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/company/v2> . ex:A a sh:NodeShape .")


def _graphs():
    return {
        V2: _g("<http://example.com/shapes/company> owl:versionIRI <http://example.com/shapes/company/v2> ; "
               "owl:imports <http://example.com/shapes/base> . ex:CompanyShape a sh:NodeShape ."),
        BASE: _g("ex:BaseShape a sh:NodeShape ."),
    }


def test_no_loader_unresolved_import_raises_unless_ignored():
    g = _app()
    with pytest.raises(ValueError, match="owl:imports"):
        resolve_imports(g)
    assert resolve_imports(g, ignore_imports=True) is g


def test_locally_satisfied_import_needs_no_loader():
    g = _g("ex:M1 owl:imports ex:M2 . ex:M2 a sh:ShapesGraph .")
    assert resolve_imports(g) is g


def test_transitive_closure_with_version_iri_and_no_mutation():
    g = _app()
    before = set(g)
    result = resolve_imports(g, _graphs().get)
    assert set(g) == before
    assert result is not g
    assert (URIRef("http://example.org/CompanyShape"), RDF.type, URIRef("http://www.w3.org/ns/shacl#NodeShape")) in result
    assert (URIRef("http://example.org/BaseShape"), RDF.type, URIRef("http://www.w3.org/ns/shacl#NodeShape")) in result
    assert len(result) == len(before) + 4


def test_unresolvable_import_with_loader_is_skipped():
    g = _app()
    assert resolve_imports(g, lambda iri: None) is g


def test_self_import_cycle_terminates_and_loader_called_once():
    g = _g("<http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/myapp> . ex:A a sh:NodeShape .")
    # the graph already has triples with the import IRI as subject: satisfied locally, loader never called
    seen = []
    assert resolve_imports(g, lambda iri: seen.append(iri)) is g
    assert seen == []
    h = _g("<http://example.com/shapes/other> owl:imports <http://example.com/shapes/other> .")
    h.remove((URIRef("http://example.com/shapes/other"), None, None))
    h.add((URIRef("http://example.com/shapes/x"), OWL.imports, URIRef("http://example.com/shapes/y")))
    calls = []

    def loader(iri):
        calls.append(iri)
        return _g("<http://example.com/shapes/y> owl:imports <http://example.com/shapes/y> .") if False else _g(
            "<http://example.com/shapes/z> owl:imports <http://example.com/shapes/y> .")

    result = resolve_imports(h, loader)
    assert calls == [URIRef("http://example.com/shapes/y")]
    assert len(result) == 2


def test_multi_hop_without_version_iri():
    mid = URIRef("http://example.com/shapes/mid")
    g = _g("<http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/mid> .")
    graphs = {
        mid: _g("<http://example.com/shapes/mid> owl:imports <http://example.com/shapes/base> . ex:M a sh:NodeShape ."),
        BASE: _g("ex:BaseShape a sh:NodeShape ."),
    }
    result = resolve_imports(g, graphs.get)
    assert (URIRef("http://example.org/BaseShape"), RDF.type, URIRef("http://www.w3.org/ns/shacl#NodeShape")) in result


def test_declared_imports_dedups_in_order():
    g = _g("ex:a owl:imports ex:x , ex:y . ex:b owl:imports ex:x .")
    assert declared_imports(g) == (URIRef("http://example.org/x"), URIRef("http://example.org/y"))
