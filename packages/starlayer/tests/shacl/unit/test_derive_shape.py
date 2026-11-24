"""Tests for starlayer.shacl.derive_shape() (moved from tests/graph/unit/test_shape_derivation.py, where it was a StarLayerGraph method).

Two phases exercised: fresh derivation (no template - Phase A) and
template-merge (Phase B's per-constraint-component relax table). Every
positive case is checked the same way this project checks any derived
artifact for real correctness: run it back through starlayer.shacl.validate()
against the exact data involved, not just "some Graph came back".
"""

import re

import pyoxigraph as ox
import pytest
import starlayer.shacl
from starlayer.graph import StarLayerGraph
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import derive_shape
from starlayer.shacl.derive import DEFAULT_IGNORED_PROPERTIES
from tests.support.terms import (
    RDF,
    RDFS,
    BlankNode,
    Namespace,
    list_items,
    lit,
    rdf_list,
    text,
)

EX = Namespace('http://example.org/')
# A plain Namespace, not rdflib.namespace.SH - sh:TripleTerm and SHACL 1.2's
# list-valued sh:nodeKind aren't in rdflib's own closed term list.
SH = Namespace('http://www.w3.org/ns/shacl#')


def _conforms(data, shapes):
    return starlayer.shacl.validate(data, shacl_graph=shapes).conforms


def _make_people_graph():
    g = StarLayerGraph()
    g.bind('ex', EX)
    g.add((EX.alice, RDF.type, EX.Person))
    g.add((EX.alice, EX.name, lit('Alice')))
    g.add((EX.alice, EX.age, lit(30)))
    g.add((EX.alice, EX.knows, EX.bob))
    g.add((EX.bob, RDF.type, EX.Person))
    g.add((EX.bob, EX.name, lit('Bob')))
    g.add((EX.bob, EX.age, lit(25)))
    return g


class TestFreshDerivation:
    def test_derived_shape_conforms_against_its_own_source_data(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
        assert _conforms(g, shape)

    def test_derive_shape_returns_a_starlayer_graph(self):
        """Matches every other graph-returning method on this class -
        added 2026-10-04, this used to return a plain rdflib.Graph."""
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
        assert isinstance(shape, StarLayerGraph)

    def test_one_shape_for_the_requested_class_only(self):
        g = _make_people_graph()
        g.add((EX.acme, RDF.type, EX.Organization))
        g.add((EX.acme, EX.name, lit('Acme')))
        shape = derive_shape(g, cls=EX.Person)
        node_shapes = set(shape.subjects(RDF.type, SH.NodeShape))
        assert node_shapes == {EX.PersonShape}
        assert set(shape.objects(EX.PersonShape, SH.targetClass)) == {EX.Person}

    def test_shared_related_class_becomes_sh_class_not_sh_node(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
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
        g.add((EX.claim1, EX.asserts, ox.Triple(EX.alice, EX.age, lit(30))))
        g.add((EX.claim2, RDF.type, EX.Claim))
        g.add((EX.claim2, EX.asserts, ox.Triple(EX.bob, EX.age, lit(25))))
        shape = derive_shape(g, cls=EX.Claim)
        assert _conforms(g, shape)
        prop = next(shape.objects(None, SH.property))
        assert (prop, SH.nodeKind, SH.TripleTerm) in shape

    def test_mixed_node_kinds_produce_list_valued_node_kind(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.claim1, RDF.type, EX.Claim))
        g.add((EX.claim1, EX.asserts, ox.Triple(EX.alice, EX.age, lit(30))))
        g.add((EX.claim2, RDF.type, EX.Claim))
        g.add((EX.claim2, EX.asserts, EX.someResource))
        shape = derive_shape(g, cls=EX.Claim)
        assert _conforms(g, shape)
        prop = next(shape.objects(None, SH.property))
        node_kind_value = shape.value(prop, SH.nodeKind)
        assert isinstance(node_kind_value, BlankNode)
        kinds = set(list_items(shape, node_kind_value))
        assert kinds == {SH.IRI, SH.TripleTerm}

    def test_omitted_min_count_when_some_instances_lack_the_property(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
        knows_prop = next(
            p for p in shape.objects(None, SH.property)
            if EX.knows in set(shape.objects(p, SH.path))
        )
        # bob has no ex:knows - observed min is 0, so sh:minCount is omitted.
        assert (knows_prop, SH.minCount, None) not in shape
        assert (knows_prop, SH.maxCount, lit(1)) in shape

    def test_shape_is_closed_with_rdf_type_always_ignored(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        assert shape.value(node_shape, SH.closed) == lit(True)
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        assert RDF.type in set(list_items(shape, ignored_list))

    def test_default_ignored_properties_excluded_from_candidate_properties(self):
        g = _make_people_graph()
        g.add((EX.alice, RDFS.label, lit('Alice the person')))
        shape = derive_shape(g, cls=EX.Person)
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        assert RDFS.label not in paths
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        assert {p.value for p in DEFAULT_IGNORED_PROPERTIES} <= {x.value for x in list_items(shape, ignored_list)}

    def test_use_default_ignored_properties_false_opt_out(self):
        g = _make_people_graph()
        g.add((EX.alice, RDFS.label, lit('Alice the person')))
        g.add((EX.bob, RDFS.label, lit('Bob the person')))
        shape = derive_shape(g, cls=EX.Person, use_default_ignored_properties=False)
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        # rdfs:label is no longer in the (opt-outable) default ignore list,
        # so it now shows up as a real candidate property instead.
        assert RDFS.label in paths
        ignored_list = shape.value(node_shape, SH.ignoredProperties)
        ignored = set(list_items(shape, ignored_list))
        assert ignored == {RDF.type}

    def test_explicit_ignored_properties_still_excluded(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person, ignored_properties=[EX.age])
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in shape.objects(node_shape, SH.property) for p in shape.objects(prop, SH.path)}
        assert EX.age not in paths


def _template_person_shape(*, min_count=None, pattern=None, in_values=None, datatype=None):
    template = Graph()
    shape_node = BlankNode()
    prop_node = BlankNode()
    template.add((shape_node, RDF.type, SH.NodeShape))
    template.add((shape_node, SH.targetClass, EX.Person))
    template.add((shape_node, SH.property, prop_node))
    template.add((prop_node, SH.path, EX.name))
    if min_count is not None:
        template.add((prop_node, SH.minCount, lit(min_count)))
    if pattern is not None:
        template.add((prop_node, SH.pattern, lit(pattern)))
    if datatype is not None:
        template.add((prop_node, SH.datatype, datatype))
    if in_values is not None:
        template.add((prop_node, SH['in'], rdf_list(template, in_values)))
    template.add((shape_node, SH.closed, lit(True)))
    return template, shape_node, prop_node


class TestTemplateMerge:
    def test_min_count_too_high_is_lowered_to_true_observed_minimum(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, lit('Bob')))
        g.add((EX.bob, EX.name, lit('Bobby')))
        template, _shape_node, _prop_node = _template_person_shape(min_count=2)

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert result.value(prop, SH.minCount) == lit(1)

    def test_wrong_datatype_is_corrected(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, lit('Bob')))
        from tests.support.terms import XSD
        template, _shape_node, _prop_node = _template_person_shape(datatype=XSD.integer)

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert result.value(prop, SH.datatype) == XSD.string

    def test_violated_pattern_is_dropped_with_a_comment(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        template, _shape_node, _prop_node = _template_person_shape(pattern='^Z')

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        assert (prop, SH.pattern, None) not in result
        comments = list(result.objects(prop, RDFS.comment))
        assert any('PatternConstraintComponent' in text(c) for c in comments)

    def test_in_enumeration_is_widened_not_replaced(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        g.add((EX.bob, RDF.type, EX.Person))
        g.add((EX.bob, EX.name, lit('Zed')))
        template, _shape_node, _prop_node = _template_person_shape(in_values=[lit('Alice')])

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        prop = next(result.objects(None, SH.property))
        in_list = result.value(prop, SH['in'])
        values = set(list_items(result, in_list))
        assert values == {lit('Alice'), lit('Zed')}

    def test_opaque_sparql_constraint_is_left_untouched_and_annotated(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))

        template = Graph()
        shape_node = BlankNode()
        template.add((shape_node, RDF.type, SH.NodeShape))
        template.add((shape_node, SH.targetClass, EX.Person))
        sparql_node = BlankNode()
        template.add((shape_node, SH.sparql, sparql_node))
        template.add((sparql_node, RDF.type, SH.SPARQLConstraint))
        template.add((sparql_node, SH.message, lit('always fails')))
        template.add((sparql_node, SH.select, lit(
            'PREFIX ex: <http://example.org/> '
            'SELECT $this WHERE { FILTER(true) }'
        )))
        template.add((shape_node, SH.closed, lit(True)))

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        # The opaque sh:sparql constraint is expected to still be present
        # and still failing - derive_shape() must not have silently dropped it.
        assert (shape_node, SH.sparql, sparql_node) in result
        comments = list(result.objects(shape_node, RDFS.comment))
        assert any('could not be automatically' in text(c) for c in comments)

    def test_new_property_not_in_template_is_added(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        g.add((EX.alice, EX.age, lit(30)))
        template, _shape_node, _prop_node = _template_person_shape()

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        node_shape = next(result.subjects(RDF.type, SH.NodeShape))
        paths = {p for prop in result.objects(node_shape, SH.property) for p in result.objects(prop, SH.path)}
        assert EX.age in paths

    def test_templates_own_ignored_properties_are_carried_forward(self):
        g = StarLayerGraph()
        g.bind('ex', EX)
        g.add((EX.alice, RDF.type, EX.Person))
        g.add((EX.alice, EX.name, lit('Alice')))
        g.add((EX.alice, EX.secret, lit('shh')))
        template, shape_node, _prop_node = _template_person_shape()
        ignored_list = rdf_list(template, [EX.secret])
        template.add((shape_node, SH.ignoredProperties, ignored_list))

        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert _conforms(g, result)
        result_ignored_list = result.value(shape_node, SH.ignoredProperties)
        result_ignored = set(list_items(result, result_ignored_list))
        assert EX.secret in result_ignored
        assert RDF.type in result_ignored


def test_derive_never_imports_pyshacl_directly():
    import inspect

    import starlayer.shacl.derive as mod
    source = inspect.getsource(mod)
    assert not re.search(r'^\s*(import pyshacl|from pyshacl)', source, re.MULTILINE)


# ---- the new API: cls / node, naming, scoping, errors ------------------------------------------------------------------

def _people_with_subclass():
    g = _make_people_graph()
    g.add((EX.Student, RDFS.subClassOf, EX.Person))
    g.add((EX.carol, RDF.type, EX.Student))
    g.add((EX.carol, EX.name, lit('Carol')))
    g.add((EX.carol, EX.school, lit('MIT')))
    return g


class TestTargets:
    def test_class_shape_targets_the_class_and_node_shape_the_node(self):
        g = _make_people_graph()
        by_class = derive_shape(g, cls=EX.Person)
        by_node = derive_shape(g, node=EX.alice)
        assert (EX.PersonShape, SH.targetClass, EX.Person) in by_class
        assert (EX.PersonShape, SH.targetNode, None) not in by_class
        assert (EX.AliceShape, SH.targetNode, EX.alice) in by_node
        assert (EX.AliceShape, SH.targetClass, None) not in by_node

    def test_node_counts_reflect_that_node_only(self):
        g = _make_people_graph()
        g.add((EX.alice, EX.name, lit('Ally')))
        shape = derive_shape(g, node=EX.alice)
        name = next(p for p in shape.objects(None, SH.property) if EX.name in set(shape.objects(p, SH.path)))
        assert shape.value(name, SH.minCount) == lit(2)
        assert shape.value(name, SH.maxCount) == lit(2)
        assert _conforms(g, shape)

    def test_class_shape_with_subclasses_includes_their_instances(self):
        g = _people_with_subclass()
        shape = derive_shape(g, cls=EX.Person)
        paths = {p for prop in shape.objects(None, SH.property) for p in shape.objects(prop, SH.path)}
        assert EX.school in paths
        assert _conforms(g, shape)

    def test_class_shape_without_subclasses_is_direct_instances_only(self):
        g = _people_with_subclass()
        shape = derive_shape(g, cls=EX.Person, include_subclasses=False)
        paths = {p for prop in shape.objects(None, SH.property) for p in shape.objects(prop, SH.path)}
        assert EX.school not in paths
        # the self-check ran on the direct instances: no RuntimeError although carol would break the closed shape

    def test_node_shape_for_a_blank_node(self):
        g = StarLayerGraph()
        b = BlankNode()
        g.add((b, EX.p, lit(1)))
        shape = derive_shape(g, node=b)
        node_shape = next(shape.subjects(RDF.type, SH.NodeShape))
        assert isinstance(node_shape, BlankNode)
        assert (node_shape, SH.targetNode, b) in shape

    def test_iri_strings_are_accepted(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person.value, shape=EX.MyShape.value)
        assert (EX.MyShape, SH.targetClass, EX.Person) in shape


class TestNaming:
    def test_class_and_node_names(self):
        g = _make_people_graph()
        assert (EX.PersonShape, RDF.type, SH.NodeShape) in derive_shape(g, cls=EX.Person)
        assert (EX.AliceShape, RDF.type, SH.NodeShape) in derive_shape(g, node=EX.alice)

    def test_hash_iri(self):
        g = StarLayerGraph()
        h = Namespace('http://example.org/vocab#')
        g.add((h.thing, RDF.type, h.widget))
        shape = derive_shape(g, cls=h.widget)
        assert (h.WidgetShape, RDF.type, SH.NodeShape) in shape

    def test_no_local_name_gives_a_blank_node_shape(self):
        g = StarLayerGraph()
        top = ox.NamedNode('http://example.org/')
        g.add((EX.x, RDF.type, top))
        shape = derive_shape(g, cls=top)
        assert isinstance(next(shape.subjects(RDF.type, SH.NodeShape)), BlankNode)

    def test_explicit_shape_name_wins(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person, shape=EX.Mine)
        assert set(shape.subjects(RDF.type, SH.NodeShape)) == {EX.Mine}

    def test_prefixes_of_the_data_graph_and_sh(self):
        g = _make_people_graph()
        shape = derive_shape(g, cls=EX.Person)
        assert shape.prefixes['ex'] == str(EX.Person.value).rsplit('/', 1)[0] + '/'
        assert shape.prefixes['sh'] == 'http://www.w3.org/ns/shacl#'


class TestErrors:
    def test_exactly_one_of_cls_and_node(self):
        g = _make_people_graph()
        with pytest.raises(ValueError, match='neither'):
            derive_shape(g)
        with pytest.raises(ValueError, match='both'):
            derive_shape(g, cls=EX.Person, node=EX.alice)

    def test_no_instances(self):
        with pytest.raises(ValueError, match='no instances'):
            derive_shape(_make_people_graph(), cls=EX.Nothing)

    def test_subclass_instances_do_not_count_without_include_subclasses(self):
        g = StarLayerGraph()
        g.add((EX.Student, RDFS.subClassOf, EX.Person))
        g.add((EX.carol, RDF.type, EX.Student))
        assert derive_shape(g, cls=EX.Person)
        with pytest.raises(ValueError, match='no instances'):
            derive_shape(g, cls=EX.Person, include_subclasses=False)

    def test_node_without_triples(self):
        with pytest.raises(ValueError, match='no triples'):
            derive_shape(_make_people_graph(), node=EX.nobody)

    def test_a_node_that_is_only_an_object_has_no_triples(self):
        g = _make_people_graph()
        with pytest.raises(ValueError, match='no triples'):
            derive_shape(g, node=ox.NamedNode('http://example.org/zzz'))

    def test_rdflib_terms_are_refused(self):
        rdflib = pytest.importorskip('rdflib')
        with pytest.raises(TypeError, match='rdflib'):
            derive_shape(_make_people_graph(), cls=rdflib.URIRef(EX.Person.value))

    def test_a_literal_is_not_a_class(self):
        with pytest.raises(TypeError):
            derive_shape(_make_people_graph(), cls=lit('x'))

    def test_the_old_method_is_gone(self):
        assert not hasattr(StarLayerGraph, 'derive_shape')
        assert not hasattr(_make_people_graph(), 'derive_shape')


class TestResult:
    def test_result_is_checked_against_the_data(self):
        g = _people_with_subclass()
        for kwargs in ({'cls': EX.Person}, {'node': EX.alice}, {'node': EX.carol}):
            assert _conforms(g, derive_shape(g, **kwargs))

    def test_result_does_not_change_the_data(self):
        g = _make_people_graph()
        before = set(g.triples((None, None, None)))
        derive_shape(g, cls=EX.Person)
        assert set(g.triples((None, None, None))) == before

    def test_same_input_twice_gives_the_same_graph_triple_for_triple(self):
        g = _people_with_subclass()
        for kwargs in ({'cls': EX.Person}, {'node': EX.alice}):
            a = derive_shape(g, **kwargs)
            b = derive_shape(g, **kwargs)
            assert sorted(map(str, a.triples((None, None, None)))) == sorted(map(str, b.triples((None, None, None))))

    def test_a_dataset_is_seen_as_its_union(self):
        from starlayer.graph import StarLayerDataset
        ds = StarLayerDataset()
        ds.update("INSERT DATA { GRAPH <http://example.org/g1> { <http://example.org/a> a <http://example.org/C> ; <http://example.org/p> 1 } }")
        shape = derive_shape(ds, cls=EX.C)
        assert (EX.CShape, SH.targetClass, EX.C) in shape


class TestTemplateScoping:
    def _two_shape_template(self):
        template, shape_node, prop_node = _template_person_shape()
        other = EX.OrgShape
        template.add((other, RDF.type, SH.NodeShape))
        template.add((other, SH.targetClass, EX.Organization))
        template.add((other, SH.closed, lit(True)))
        return template, shape_node

    def test_other_template_shapes_are_not_copied(self):
        g = _make_people_graph()
        g.add((EX.acme, RDF.type, EX.Organization))
        g.add((EX.acme, EX.name, lit('Acme')))
        template, shape_node = self._two_shape_template()
        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert set(result.subjects(RDF.type, SH.NodeShape)) == {shape_node}
        assert (EX.OrgShape, None, None) not in result

    def test_the_template_shape_for_a_node(self):
        g = _make_people_graph()
        template = Graph()
        template.add((EX.AliceShape, RDF.type, SH.NodeShape))
        template.add((EX.AliceShape, SH.targetNode, EX.alice))
        template.add((EX.OtherShape, SH.targetNode, EX.bob))
        result = derive_shape(g, node=EX.alice, template_shape=template)
        assert _conforms(g, result)
        assert (EX.OtherShape, None, None) not in result
        assert {p for prop in result.objects(EX.AliceShape, SH.property) for p in result.objects(prop, SH.path)} == {EX.name, EX.age, EX.knows}

    def test_no_template_shape_for_the_target_raises(self):
        g = _make_people_graph()
        template, _ = self._two_shape_template()
        with pytest.raises(ValueError, match='no shape'):
            derive_shape(g, cls=EX.Person, template_shape=Graph())
        with pytest.raises(ValueError, match='no shape'):
            derive_shape(g, node=EX.alice, template_shape=template)

    def test_two_template_shapes_for_one_target_need_shape(self):
        g = _make_people_graph()
        template, _ = self._two_shape_template()
        template.add((EX.Second, SH.targetClass, EX.Person))
        with pytest.raises(ValueError, match='shape='):
            derive_shape(g, cls=EX.Person, template_shape=template)
        result = derive_shape(g, cls=EX.Person, shape=EX.Second, template_shape=template)
        assert (EX.Second, SH.targetClass, EX.Person) in result

    def test_shape_renames_the_template_shape(self):
        g = _make_people_graph()
        template, shape_node = self._two_shape_template()
        result = derive_shape(g, cls=EX.Person, shape=EX.Renamed, template_shape=template)
        assert (EX.Renamed, SH.targetClass, EX.Person) in result
        assert (shape_node, None, None) not in result

    def test_referenced_named_shapes_are_copied(self):
        g = _make_people_graph()
        template, shape_node, prop_node = _template_person_shape()
        template.add((prop_node, SH.node, EX.NameShape))
        template.add((EX.NameShape, RDF.type, SH.NodeShape))
        template.add((EX.NameShape, SH.nodeKind, SH.Literal))
        result = derive_shape(g, cls=EX.Person, template_shape=template)
        assert (EX.NameShape, SH.nodeKind, SH.Literal) in result
