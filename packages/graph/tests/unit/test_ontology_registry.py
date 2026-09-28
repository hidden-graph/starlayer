"""Tests for starlayergraph.ontology.registry - the "list/get a SHACL
library" catalog spanning manch:/skos:/salg: (from starlayergraph and the
sibling starsparql) and the SHACL 1.2 meta-shapes themselves (starshacl).
"""

import pytest
from rdflib import RDF, Graph, Literal
from rdflib.namespace import SKOS

from starlayergraph import Namespace, StarLayerGraph
from starlayergraph.ontology import ShaclLibrary, get_shacl_library, list_shacl_libraries

EX = Namespace('http://example.org/')


def test_list_shacl_libraries_includes_every_concretely_shipped_library():
    names = list_shacl_libraries()
    assert names == tuple(sorted(names))  # sorted, stable order
    assert set(names) == {'manchester', 'skos', 'sparql', 'shacl'}


def test_generic_rdf_and_owl_rdf_are_not_registered_yet():
    # Explicitly not yet built (generic RDF) or not a concrete artifact
    # anywhere in this codebase (OWL RDF) - see registry.py's own docstring.
    names = list_shacl_libraries()
    assert 'generic' not in names
    assert 'generic-rdf' not in names
    assert 'owl' not in names
    assert 'owl-rdf' not in names


def test_get_unknown_library_raises_keyerror_naming_the_choices():
    with pytest.raises(KeyError, match='not a registered SHACL library'):
        get_shacl_library('nope')


@pytest.mark.parametrize('name', ['manchester', 'skos', 'sparql'])
def test_libraries_with_an_ontology_load_a_nonempty_graph(name):
    lib = get_shacl_library(name)
    assert lib.ontology_graph is not None
    graph = lib.ontology_graph()
    assert isinstance(graph, Graph)
    assert len(graph) > 0


def test_shacl_library_has_no_separate_ontology():
    lib = get_shacl_library('shacl')
    assert lib.ontology_graph is None


@pytest.mark.parametrize('name', ['manchester', 'skos', 'sparql', 'shacl'])
def test_every_library_has_a_nonempty_shapes_graph(name):
    lib = get_shacl_library(name)
    assert lib.shapes_graph is not None
    graph = lib.shapes_graph()
    assert isinstance(graph, Graph)
    assert len(graph) > 0


@pytest.mark.parametrize('name', ['manchester', 'skos', 'sparql', 'shacl'])
def test_every_library_declares_a_namespace(name):
    lib = get_shacl_library(name)
    assert isinstance(lib.namespace, str)
    assert lib.namespace.startswith('http')


def test_skos_library_validate_conforms_for_a_valid_thesaurus():
    lib = get_shacl_library('skos')
    g = StarLayerGraph()
    g.add((EX.scheme, RDF.type, SKOS.ConceptScheme))
    g.add((EX.cat, RDF.type, SKOS.Concept))
    g.add((EX.cat, SKOS.inScheme, EX.scheme))
    g.add((EX.cat, SKOS.prefLabel, Literal('Cat', lang='en')))
    conforms, _report_graph, _report_text = lib.validate(g)
    assert conforms


def test_shacl_library_validate_checks_a_shapes_graph_not_data():
    # The "shacl" library's own validate() has a different meaning from
    # every other library's - it checks a *shapes* graph's own
    # well-formedness (meta-validation), not data against shapes.
    lib = get_shacl_library('shacl')
    skos_shapes = get_shacl_library('skos').shapes_graph()
    conforms, _report_graph, _report_text = lib.validate(skos_shapes)
    assert conforms


def test_get_shacl_library_returns_the_same_dataclass_type():
    for name in list_shacl_libraries():
        assert isinstance(get_shacl_library(name), ShaclLibrary)
