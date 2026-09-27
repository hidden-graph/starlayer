"""Tests for StarLayerGraph.derive() / starlayergraph.graph.shape_derivation.

Two phases exercised: fresh derivation (no template - Phase A) and
template-merge (Phase B's per-constraint-component relax table). Every
positive case is checked the same way this project checks any derived
artifact for real correctness: run it back through starshacl.validate()
against the exact data involved, not just "some Graph came back".
"""

import re

from rdflib import RDF, BNode, Graph, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDFS

import starshacl
from starlayergraph import Namespace, StarLayerGraph
from starlayergraph.graph.shape_derivation import DEFAULT_IGNORED_PROPERTIES
from starlayergraph.model import TripleTerm

EX = Namespace('http://example.org/')
# A plain Namespace, not rdflib.namespace.SH - sh:TripleTerm and SHACL 1.2's
# list-valued sh:nodeKind aren't in rdflib's own closed term list. Matches
# shape_derivation.py's own SH import.
SH = Namespace('http://www.w3.org/ns/shacl#')


def _conforms(data, shapes):
    return starshacl.validate(data, shacl_graph=shapes).conforms


def _make_people_graph():
    g = StarLayerGraph()
    g.bind('ex', EX)
    g.add((EX.alice, RDF.type, EX.Person))
    g.add((EX.alice, EX.name, Literal('Alice')))
    g.add((EX.alice, EX.age, Literal(30)))
    g.add((EX.alice, EX.knows, EX.bob))
    g.add((EX.bob, RDF.type, EX.Person))
    g.add((EX.bob, EX.name, Literal('Bob')))
    g.add((EX.bob, EX.age, Literal(25)))
    return g


class TestFreshDerivation:
    def test_derived_shape_conforms_against_its_own_source_data(self):
        g = _make_people_graph()
        shape = g.derive()
        assert _conforms(g, shape)

    def test_one_node_shape_per_class(self):
        g = _make_people_graph()
        g.add((EX.acme, RDF.type, EX.Organization))
        g.add((EX.acme, EX.name, Literal('Acme')))
        shape = g.derive()
        node_shapes = set(shape.subjects(RDF.type, SH.NodeShape))
        target_classes = {c for ns in node_shapes for c in shape.objects(ns, SH.targetClass)}
        assert target_classes == {EX.Person, EX.Organization}

    def test_shared_related_class_becomes_sh_class_not_sh_node(self):
        g = _make_people_graph()
        shape = g.derive()
        knows_prop = next(
            p for p in shape.objects(None, SH.property)
            if EX.knows in set(shape.objects(p, SH.path))
        )
        assert (knows_prop, SH['class'], EX.Person) in shape
        assert (knows_prop, SH.node, None) not in shape

    def test_triple_term_valued_property_gets_triple_term_node_kind(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.claim1, RDF.type, EX.Claim))
        g.add((EX.claim1, EX.asserts, TripleTerm(EX.alice, EX.age, Literal(30))))
        g.add((EX.claim2, RDF.type, EX.Claim))
        g.add((EX.claim2, EX.asserts, TripleTerm(EX.bob, EX.age, Literal(25))))
        shape = g.derive()
        assert _conforms(g, shape)
        prop = next(shape.objects(None, SH.property))
        assert (prop, SH.nodeKind, SH.TripleTerm) in shape

    def test_mixed_node_kinds_produce_list_valued_node_kind(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.claim1, RDF.type, EX.Claim))
        g.add((EX.claim1, EX.asserts, TripleTerm(EX.alice, EX.age, Literal(30))))
        g.add((EX.claim2, RDF.type, EX.Claim))
        g.add((EX.claim2, EX.asserts, EX.someResource))
        shape = g.derive()
        assert _conforms(g, shape)
        prop = next(shape.objects(None, SH.property))
        node_kind_value = shape.value(prop, SH.nodeKind)
        assert isinstance(node_kind_value, BNode)
        kinds = set(Collection(shape, node_kind_value))
        assert kinds == {SH.IRI, SH.TripleTerm}

    def test_omitted_min_count_when_some_instances_lack_the_property(self):
        g = _make_people_graph()
        shape = g.derive()
        knows_prop = next(
            p for p in shape.objects(None, SH.property)
            if EX.knows in set(shape.objects(p, SH.path))
        )
        # bob has no ex:knows - observed min is 0, so sh:minCount is omitted.
        assert (knows_prop, SH.minCount, None) not in shape
        assert (knows_prop, SH.maxCount, Literal(1)) in shape

    def test_shape_is_closed_with_rdf_type_always_ignored(self):
        g = _make_people_graph()
        shape = g.derive()
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        assert shape.value(node_shape, SH.closed) == Literal(True)
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        assert RDF.type in set(Collection(shape, ignored_list))

    def test_default_ignored_properties_excluded_from_candidate_properties(self):
        g = _make_people_graph()
        g.add((EX.alice, RDFS.label, Literal('Alice the person')))
        shape = g.derive()
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        assert RDFS.label not in paths
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        assert DEFAULT_IGNORED_PROPERTIES <= set(Collection(shape, ignored_list))

    def test_use_default_ignored_properties_false_opt_out(self):
        g = _make_people_graph()
        g.add((EX.alice, RDFS.label, Literal('Alice the person')))
        g.add((EX.bob, RDFS.label, Literal('Bob the person')))
        shape = g.derive(use_default_ignored_properties=False)
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        # rdfs:label is no longer in the (opt-outable) default ignore list,
        # so it now shows up as a real candidate property instead.
        assert RDFS.label in paths
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        ignored = set(Collection(shape, ignored_list))
        assert ignored == {RDF.type}

    def test_explicit_ignored_properties_still_excluded(self):
        g = _make_people_graph()
        shape = g.derive(ignored_properties=[EX.age])
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        assert EX.age not in paths


def _template_person_shape(*, min_count=None, pattern=None, in_values=None, datatype=None):
    template = Graph()
    shape_node = BNode()
    prop_node = BNode()
    template.add((shape_node, RDF.type, SH.NodeShape))
    template.add((shape_node, SH.targetClass, EX.Person))
    template.add((shape_node, SH.property, prop_node))
    template.add((prop_node, SH.path, EX.name))
    if min_count is not None:
        template.add((prop_node, SH.minCount, Literal(min_count)))
    if pattern is not None:
        template.add((prop_node, SH.pattern, Literal(pattern)))
    if datatype is not None:
        template.add((prop_node, SH.datatype, datatype))
    if in_values is not None:
        template.add((prop_node, SH['in'], Collection(template, BNode(), in_values).uri))
    template.add((shape_node, SH.closed, Literal(True)))
    return template, shape_node, prop_node


class TestTemplateMerge:
    def test_min_count_too_high_is_lowered_to_true_observed_minimum(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, Literal('Bob')))
        g.add((EX.bob, EX.name, Literal('Bobby')))
        template, _shape_node, _prop_node = _template_person_shape(min_count=2)

        result = g.derive(template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert result.value(prop, SH.minCount) == Literal(1)

    def test_wrong_datatype_is_corrected(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, Literal('Bob')))
        from rdflib.namespace import XSD
        template, _shape_node, _prop_node = _template_person_shape(datatype=XSD.integer)

        result = g.derive(template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert result.value(prop, SH.datatype) == XSD.string

    def test_violated_pattern_is_dropped_with_a_comment(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        template, _shape_node, _prop_node = _template_person_shape(pattern='^Z')

        result = g.derive(template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert (prop, SH.pattern, None) not in result
        comments = list(result.objects(prop, RDFS.comment))
        assert any('PatternConstraintComponent' in str(c) for c in comments)

    def test_in_enumeration_is_widened_not_replaced(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, Literal('Zed')))
        template, _shape_node, _prop_node = _template_person_shape(in_values=[Literal('Alice')])

        result = g.derive(template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        in_list = result.value(prop, SH['in'])
        values = set(Collection(result, in_list))
        assert values == {Literal('Alice'), Literal('Zed')}

    def test_opaque_sparql_constraint_is_left_untouched_and_annotated(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))

        template = Graph()
        shape_node = BNode()
        template.add((shape_node, RDF.type, SH.NodeShape))
        template.add((shape_node, SH.targetClass, EX.Person))
        sparql_node = BNode()
        template.add((shape_node, SH.sparql, sparql_node))
        template.add((sparql_node, RDF.type, SH.SPARQLConstraint))
        template.add((sparql_node, SH.message, Literal('always fails')))
        template.add((sparql_node, SH.select, Literal(
            'PREFIX ex: <http://example.org/> '
            'SELECT $this WHERE { FILTER(true) }'
        )))
        template.add((shape_node, SH.closed, Literal(True)))

        result = g.derive(template)
        # The opaque sh:sparql constraint is expected to still be present
        # and still failing - derive() must not have silently dropped it.
        assert (shape_node, SH.sparql, sparql_node) in result
        comments = list(result.objects(shape_node, RDFS.comment))
        assert any('could not be automatically' in str(c) for c in comments)

    def test_new_property_not_in_template_is_added(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.alice, EX.age, Literal(30)))
        template, _shape_node, _prop_node = _template_person_shape()

        result = g.derive(template)
        assert _conforms(g, result)
        node_shape = next(result.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in result.objects(node_shape, SH.property) for p in result.objects(prop, SH.path)}
        assert EX.age in paths

    def test_new_class_not_in_template_gets_a_fresh_shape(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.acme, RDF.type, EX.Organization))
        g.add((EX.acme, EX.name, Literal('Acme')))
        template, _shape_node, _prop_node = _template_person_shape()

        result = g.derive(template)
        assert _conforms(g, result)
        target_classes = {c for ns in result.subjects(RDF.type, SH.NodeShape) for c in result.objects(ns, SH.targetClass)}
        assert EX.Organization in target_classes

    def test_templates_own_ignored_properties_are_carried_forward(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, Literal('Alice')))
        g.add((EX.alice, EX.secret, Literal('shh')))
        template, shape_node, _prop_node = _template_person_shape()
        ignored_list = Collection(template, BNode(), [EX.secret]).uri
        template.add((shape_node, SH.ignoredProperties, ignored_list))

        result = g.derive(template)
        assert _conforms(g, result)
        result_ignored_list = result.value(shape_node, SH.ignoredProperties)
        result_ignored = set(Collection(result, result_ignored_list))
        assert EX.secret in result_ignored
        assert RDF.type in result_ignored


def test_derive_never_imports_pyshacl_directly():
    import starlayergraph.graph.shape_derivation as mod
    import inspect
    source = inspect.getsource(mod)
    assert not re.search(r'^\s*(import pyshacl|from pyshacl)', source, re.MULTILINE)
