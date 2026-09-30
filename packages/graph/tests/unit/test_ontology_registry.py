"""Tests for starlayergraph.ontology.registry - the "list/get an ontology"
catalog spanning manch:/skos:/salg: (from starlayergraph and the sibling
starsparql) and the SHACL 1.2 meta-shapes themselves (starshacl). Each
OWL ontology and SHACL shapes file is its own independent registry entry
(e.g. `manchester_owl`/`manchester_shacl`), never bundled as a pair.
"""

import pytest
from rdflib import RDF, Graph, Literal
from rdflib.namespace import SKOS

from starlayergraph import Namespace, StarLayerGraph
from starlayergraph.ontology import Ontology, get_ontology, list_ontologies

EX = Namespace('http://example.org/')

ALL_NAMES = {
    'manchester_owl', 'manchester_shacl',
    'skos_owl', 'skos_shacl',
    'sparql_owl', 'sparql_shacl',
    'srl_owl', 'srl_shacl',
    'shacl_meta',
}
OWL_NAMES = ['manchester_owl', 'skos_owl', 'sparql_owl', 'srl_owl']
SHACL_NAMES = ['manchester_shacl', 'skos_shacl', 'sparql_shacl', 'srl_shacl', 'shacl_meta']


def test_list_ontologies_includes_every_concretely_shipped_entry():
    names = list_ontologies()
    assert names == tuple(sorted(names))  # sorted, stable order
    assert set(names) == ALL_NAMES


def test_generic_rdf_and_owl_rdf_are_not_registered_yet():
    # Explicitly not yet built (generic RDF) or not a concrete artifact
    # anywhere in this codebase (OWL RDF) - see registry.py's own docstring.
    names = list_ontologies()
    assert 'generic' not in names
    assert 'generic-rdf' not in names
    assert 'owl' not in names
    assert 'owl-rdf' not in names


def test_get_unknown_ontology_raises_keyerror_naming_the_choices():
    with pytest.raises(KeyError, match='not a registered ontology'):
        get_ontology('nope')


@pytest.mark.parametrize('name', OWL_NAMES)
def test_owl_entries_have_kind_owl_and_no_validate(name):
    ont = get_ontology(name)
    assert ont.kind == 'owl'
    assert ont.validate is None


@pytest.mark.parametrize('name', SHACL_NAMES)
def test_shacl_entries_have_kind_shacl_and_a_validate(name):
    ont = get_ontology(name)
    assert ont.kind == 'shacl'
    assert ont.validate is not None


@pytest.mark.parametrize('name', sorted(ALL_NAMES))
def test_every_entry_loads_a_nonempty_graph(name):
    ont = get_ontology(name)
    graph = ont.graph()
    assert isinstance(graph, Graph)
    assert len(graph) > 0


@pytest.mark.parametrize('name', sorted(ALL_NAMES))
def test_every_entry_declares_a_namespace(name):
    ont = get_ontology(name)
    assert isinstance(ont.namespace, str)
    assert ont.namespace.startswith('http')


def test_skos_shacl_validate_conforms_for_a_valid_thesaurus():
    ont = get_ontology('skos_shacl')
    g = StarLayerGraph()
    g.add((EX.scheme, RDF.type, SKOS.ConceptScheme))
    g.add((EX.cat, RDF.type, SKOS.Concept))
    g.add((EX.cat, SKOS.inScheme, EX.scheme))
    g.add((EX.cat, SKOS.prefLabel, Literal('Cat', lang='en')))
    conforms, _report_graph, _report_text = ont.validate(g)
    assert conforms


def test_shacl_meta_validate_checks_a_shapes_graph_not_data():
    # shacl_meta's own validate() has a different meaning from every other
    # entry's - it checks a *shapes* graph's own well-formedness
    # (meta-validation), not data against shapes.
    meta = get_ontology('shacl_meta')
    skos_shapes = get_ontology('skos_shacl').graph()
    conforms, _report_graph, _report_text = meta.validate(skos_shapes)
    assert conforms


def test_get_ontology_returns_the_same_dataclass_type():
    for name in list_ontologies():
        assert isinstance(get_ontology(name), Ontology)
