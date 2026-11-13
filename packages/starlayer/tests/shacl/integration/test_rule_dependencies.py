"""``rule_dependencies``: what a shape's rules need to run, beyond the shapes they refer to."""

from starlayer.graph import StarLayerGraph
from starlayer.shacl import referenced_shapes, rule_dependencies
from starlayer.shacl.engine.terms import NS

EX = NS("http://example.org/")
TTL = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Person a sh:NodeShape ; sh:property ex:NameShape ; sh:rule ex:Adult, ex:FromTemplate .
ex:NameShape sh:path ex:name ; sh:minCount 1 .

ex:Adult a sh:SPARQLRule ; sh:condition ( ex:OldEnough ex:Registered ) ; sh:prefixes ex:Prefixes ;
  sh:construct "CONSTRUCT { $this ex:adult true } WHERE { $this ex:age ?a }" .
ex:OldEnough a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minInclusive 18 ] .
ex:Registered a sh:NodeShape ; sh:property ex:RegShape .
ex:RegShape sh:path ex:registered ; sh:minCount 1 .
ex:Prefixes owl:imports ex:MorePrefixes ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .
ex:MorePrefixes sh:declare [ sh:prefix "more" ; sh:namespace "http://more.example/" ] .

ex:FromTemplate a ex:AgeTemplate ; ex:years 18 .
ex:AgeTemplate a sh:SPARQLRuleTemplate ; rdfs:subClassOf ex:BaseTemplate .
ex:BaseTemplate rdfs:label "base" .
ex:Unrelated a sh:NodeShape .
"""


def _graph():
    g = StarLayerGraph()
    g.parse(data=TTL, format="turtle12")
    return g


def test_the_conditions_in_a_list_the_prefix_sets_and_the_template_are_found():
    found = rule_dependencies(_graph(), [EX.Person])
    assert {EX.OldEnough, EX.Registered, EX.RegShape} <= found  # the condition list, and the shape it refers to
    assert {EX.Prefixes, EX.MorePrefixes} <= found  # prefixes, and what they import
    assert {EX.AgeTemplate, EX.BaseTemplate} <= found  # the template of a rule, and the class it specialises
    assert {EX.NameShape, EX.Adult, EX.FromTemplate} <= found  # what referenced_shapes already gives
    assert EX.Person not in found and EX.Unrelated not in found


def test_it_is_a_superset_of_referenced_shapes():
    g = _graph()
    assert referenced_shapes(g, [EX.Person]) <= rule_dependencies(g, [EX.Person])


def test_a_shape_without_rules_has_the_shapes_it_refers_to_only():
    g = _graph()
    assert rule_dependencies(g, [EX.Registered]) == {EX.RegShape}
    assert rule_dependencies(g, [EX.Unrelated]) == set()


def test_starting_points_are_not_part_of_the_result_and_a_cycle_ends():
    g = _graph()
    g.add((EX.RegShape, EX.also, EX.Registered))
    g.parse(data="@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . ex:RegShape sh:node ex:Registered .", format="turtle12")
    found = rule_dependencies(g, [EX.Registered, EX.RegShape])
    assert EX.Registered not in found and EX.RegShape not in found
