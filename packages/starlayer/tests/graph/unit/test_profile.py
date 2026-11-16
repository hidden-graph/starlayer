"""``profile(graph)`` / ``graph.profile()``: classes with counts, the properties their instances use."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import (
    RDF,
    XSD,
    GraphProfile,
    Namespace,
    PropertyUse,
    StarLayerDataset,
    StarLayerGraph,
    profile,
)

EX = Namespace("http://e/")
TTL = """
@prefix ex: <http://e/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:a a ex:Person ; ex:name "Ann" ; ex:age 30 ; ex:knows ex:b, ex:c ; ex:note "x"@en .
ex:b a ex:Person, ex:Agent ; ex:name "Bob", "Robert" ; ex:knows [ ex:name "anon" ] .
ex:c a ex:Agent ; ex:claim <<( ex:a ex:age 30 )>> .
ex:d ex:name "Untyped" .
"""


def _graph(cls=StarLayerGraph):
    g = cls()
    g.parse(data=TTL, format="turtle12")
    return g


def test_classes_properties_and_types():
    p = profile(_graph())
    assert isinstance(p, GraphProfile)
    assert p.classes == {EX.Person: 2, EX.Agent: 2}
    assert p.properties[EX.name] == 5 and p.properties[RDF.type] == 4
    assert sorted(n.value for n in p.instances(EX.Person)) == ["http://e/a", "http://e/b"]
    assert p.types_of(EX.b) == {EX.Person, EX.Agent} and p.types_of(EX.d) == frozenset() and p.instances(EX.Nothing) == []


def test_subjects_include_the_untyped():
    p = profile(_graph())
    assert EX.d in p.subjects and EX.a in p.subjects and p.types_of(EX.d) == frozenset()


def test_how_the_instances_of_a_class_use_each_property():
    uses = {u.property: u for u in profile(_graph()).class_properties(EX.Person)}
    name = uses[EX.name]
    assert isinstance(name, PropertyUse) and (name.nodes, name.max_values, name.datatypes, name.kinds) == (2, 2, {XSD.string}, {"literal"})
    assert uses[EX.age] == PropertyUse(EX.age, 1, 1, frozenset({XSD.integer}), frozenset({"literal"}))
    knows = uses[EX.knows]
    assert (knows.nodes, knows.max_values, knows.kinds) == (2, 2, {"iri", "blank"}) and knows.datatypes == frozenset()
    note = uses[EX.note]
    assert note.datatypes == {ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#langString")}


def test_a_triple_term_value_is_a_kind_and_the_order_is_most_used_first():
    p = profile(_graph())
    (claim,) = [u for u in p.class_properties(EX.Agent) if u.property == EX.claim]
    assert claim.kinds == {"triple"}
    ordered = p.class_properties(EX.Person)
    assert [u.nodes for u in ordered] == sorted((u.nodes for u in ordered), reverse=True)
    assert ordered[0].property in (EX.name, RDF.type, EX.knows)


def test_properties_of_any_set_of_nodes():
    p = profile(_graph())
    uses = {u.property: u for u in p.properties_of([EX.a, EX.d])}
    assert uses[EX.name].nodes == 2 and EX.knows in uses and p.properties_of([]) == [] and p.properties_of([EX.nobody]) == []


def test_the_method_and_a_dataset():
    g = _graph()
    assert g.profile().classes == profile(g).classes
    d = StarLayerDataset(default_union=True)
    d.parse(data="<http://e/a> a <http://e/Person> .", format="turtle")
    d.update("INSERT DATA { GRAPH <urn:g> { <http://e/b> a <http://e/Person> } }")
    assert d.profile().classes == {EX.Person: 2}


def test_it_is_a_snapshot():
    g = _graph()
    p = g.profile()
    g.add((EX.z, RDF.type, EX.Person))
    assert p.classes[EX.Person] == 2 and g.profile().classes[EX.Person] == 3


# ---- a dataset's profile lists its graphs ------------------------------------------------------------------------------
def _dataset(default_union: bool):
    from starlayer.graph import RDF, StarLayerDataset

    ex = lambda name: ox.NamedNode("http://example.org/" + name)  # noqa: E731
    d = StarLayerDataset(default_union=default_union)
    d.default_graph.add((ex("d1"), RDF.type, ex("Thing")))
    d.graph(ex("g")).add((ex("a"), RDF.type, ex("Person")))
    d.graph(ex("g")).add((ex("a"), ex("name"), ex("n1")))
    d.graph(ex("h")).add((ex("b"), RDF.type, ex("Person")))
    d.graph(ex("h")).add((ex("b"), ex("age"), ex("n2")))
    d.ox.add_graph(ex("empty"))
    return d, ex


@pytest.mark.parametrize("default_union", [True, False])
def test_a_dataset_profile_has_the_profile_of_every_graph_whatever_default_union_is(default_union):
    d, ex = _dataset(default_union)
    p = d.profile()
    assert list(p.graphs) == [ox.DefaultGraph(), ex("empty"), ex("g"), ex("h")]  # the default graph first, the named graphs by name
    assert p.graphs[ex("g")].classes == {ex("Person"): 1} and p.graphs[ex("h")].classes == {ex("Person"): 1}
    assert p.graphs[ox.DefaultGraph()].classes == {ex("Thing"): 1} and p.graphs[ex("empty")].classes == {}
    assert p.graphs[ex("g")].classes == d.graph(ex("g")).profile().classes  # the same as profiling that graph alone
    # the profile itself is the union of all the graphs, whatever default_union is
    assert p.classes == {ex("Person"): 2, ex("Thing"): 1} and set(p.properties) == {ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), ex("name"), ex("age")}


def test_a_triple_held_by_several_graphs_counts_once_in_a_dataset_profile():
    from starlayer.graph import RDF, StarLayerDataset

    d = StarLayerDataset(default_union=False)
    a, thing = ox.NamedNode("http://example.org/a"), ox.NamedNode("http://example.org/Thing")
    for name in ("g", "h"):
        d.graph(ox.NamedNode("http://example.org/" + name)).add((a, RDF.type, thing))
    p = d.profile()
    assert p.classes == {thing: 1} and p.properties == {RDF.type: 1}
    assert all(gp.classes == {thing: 1} for name, gp in p.graphs.items() if name != ox.DefaultGraph())


def test_a_graph_profile_has_itself_under_its_own_name():
    from starlayer.graph import StarLayerGraph

    g = StarLayerGraph(identifier=ox.NamedNode("http://example.org/g"))
    p = g.profile()
    assert list(p.graphs) == [ox.NamedNode("http://example.org/g")] and p.graphs[ox.NamedNode("http://example.org/g")] is p
    assert list(StarLayerGraph().profile().graphs) == [ox.DefaultGraph()]
