"""``owl:imports sh:`` (the import Core recommends for a graph that uses ``sh:ShapeClass``) needs no loader: the engine has the vocabulary."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"


def _graph(turtle: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=PFX + turtle, format="turtle")


SHAPES = "ex:Shapes a owl:Ontology ; owl:imports sh: . ex:Person a sh:ShapeClass ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
DATA = "ex:alice a ex:Person ."


def test_the_import_of_the_shacl_vocabulary_is_satisfied_without_a_loader():
    result = StarShaclProcessor(shacl_graph=_graph(SHAPES)).validate(data_graph=_graph(DATA))
    assert result.conforms is False  # alice has no name: the shape ran, and no error about the import was raised


def test_the_loader_is_not_asked_for_the_shacl_vocabulary():
    asked = []
    StarShaclProcessor(shacl_graph=_graph(SHAPES), imports_loader=lambda iri: asked.append(iri.value)).validate(data_graph=_graph(DATA))
    assert asked == []


def test_another_import_that_nothing_supplies_still_raises():
    shapes = _graph("ex:Shapes a owl:Ontology ; owl:imports sh:, <http://example.org/other> . ex:S a sh:NodeShape .")
    with pytest.raises(ExecutionError, match="http://example.org/other") as e:
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_graph(DATA))
    assert e.value.kind == "import"
    assert [i.value for i in e.value.unresolved] == ["http://example.org/other"]  # the built-in sh: is not named


# --- every ontology StarLayer has built in (the starontology registry), not only sh: ---

from starlayer.shacl.engine.imports import (  # noqa: E402
    builtin_import_keys,
    is_builtin_import,
)
from starlayer.starontology import get_ontology_graph, get_ontology_list  # noqa: E402

OWL_ONTOLOGY = "http://www.w3.org/2002/07/owl#Ontology"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _declared_ontology_iris() -> set[str]:
    return {
        s.value
        for info in get_ontology_list()
        for s, p, o in get_ontology_graph(info.name).triples((None, None, None))
        if p.value == RDF_TYPE and getattr(o, "value", None) == OWL_ONTOLOGY and type(s).__name__ == "NamedNode"
    }


BUILT_IN = sorted(
    _declared_ontology_iris()
    | {"http://www.w3.org/ns/shacl", "http://www.w3.org/ns/shacl-ui", "http://www.w3.org/ns/shacl-ui/", "http://www.w3.org/ns/shacl#"}
)


def _importing(iri: str) -> StarLayerGraph:
    return _graph(f"ex:Shapes a owl:Ontology ; owl:imports <{iri}> . ex:Person a sh:ShapeClass ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")


def test_the_built_in_set_is_the_registry_with_no_hand_kept_list():
    declared = _declared_ontology_iris()
    assert {"http://www.w3.org/ns/shacl#", "http://www.w3.org/ns/shacl-ui/", "http://www.w3.org/ns/shacl-shacl#", "http://www.w3.org/2004/02/skos/core"} <= declared
    assert all(is_builtin_import(ox.NamedNode(iri)) for iri in declared)
    assert builtin_import_keys() == {i.rstrip("#/") for i in declared} | {"http://www.w3.org/ns/shacl"}


@pytest.mark.parametrize("iri", BUILT_IN)
def test_a_built_in_import_needs_no_loader(iri):
    result = StarShaclProcessor(shacl_graph=_importing(iri)).validate(data_graph=_graph(DATA))
    assert result.conforms is False  # the shape ran, no import error


@pytest.mark.parametrize("iri", BUILT_IN)
def test_a_loader_is_not_asked_for_a_built_in_import(iri):
    asked = []
    shapes = _importing(iri)
    result = StarShaclProcessor(shacl_graph=shapes, imports_loader=lambda i: asked.append(i.value)).validate(data_graph=_graph(DATA))
    assert asked == []
    assert result.conforms is False
    assert len(shapes) == len(_importing(iri))  # nothing merged into the caller's graph


def test_an_unregistered_import_raises_at_the_first_validate():
    iri = "http://example.org/not-registered"
    with pytest.raises(ExecutionError, match=r"owl:imports <http://example.org/not-registered> is not resolved") as e:
        StarShaclProcessor(shacl_graph=_importing(iri)).validate(data_graph=_graph(DATA))
    assert "ignore_imports=True" in str(e.value)


def test_ignore_imports_is_unchanged():
    result = StarShaclProcessor(shacl_graph=_importing("http://example.org/not-registered"), ignore_imports=True).validate(data_graph=_graph(DATA))
    assert result.conforms is False
