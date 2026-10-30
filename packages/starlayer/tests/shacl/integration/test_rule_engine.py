"""The rule execution algorithm of SHACL 1.2 Inference Rules, section 8 (``starlayer.shacl.rule_engine``).

pySHACL runs each rule to its own fixpoint, one shape after another, and adds what a rule infers before the next rule looks.
The specification has all rules of a layer take part in one iteration; rules of one ``sh:order`` read the same graph; the
rules no shape refers to (global rules, sh:SPARQLRule and sh:TripleRule) join that same iteration; the expected derived
triples of a layer are removed when the layer ends. Each test below fails with pySHACL's loop.
"""

import pytest
from rdflib import Literal, Namespace, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

pyshacl = pytest.importorskip("pyshacl")

PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def _graph(turtle: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PREFIXES + turtle, format="turtle")
    return graph


def _apply(shapes: str, data: str = "ex:n ex:marker true .", **kwargs):
    return StarShaclSchema(shacl_graph=_graph(shapes)).apply_rules(data_graph=_graph(data), meta_shacl=False, **kwargs)


def _two_rules(order_a: str, order_b: str, run_once: str) -> str:
    return f"""
        ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:A, ex:B .
        ex:A a sh:SPARQLRule ; {order_a} {run_once}
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT {{ $this ex:p ex:x . }} WHERE {{ }}" .
        ex:B a sh:SPARQLRule ; {order_b} {run_once}
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT {{ $this ex:q ?o . }} WHERE {{ $this ex:p ?o . }}" .
    """


class TestOrderGroups:
    def test_rules_of_the_same_order_do_not_see_each_others_triples_in_one_iteration(self) -> None:
        """Both are run-once, so each gets one iteration: B reads the graph as it was before A's triple was added."""
        result = _apply(_two_rules("sh:order 0 ;", "sh:order 0 ;", "sh:runOnce true ;"))

        assert (EX.n, EX.p, EX.x) in result.inferred_graph
        assert (EX.n, EX.q, EX.x) not in result.inferred_graph

    def test_a_later_order_sees_what_an_earlier_order_inferred(self) -> None:
        result = _apply(_two_rules("sh:order 0 ;", "sh:order 1 ;", "sh:runOnce true ;"))

        assert (EX.n, EX.q, EX.x) in result.inferred_graph

    def test_iterating_rules_of_the_same_order_still_reach_the_fixpoint(self) -> None:
        """Not run-once: B misses A in the first iteration and gets it in the second."""
        result = _apply(_two_rules("sh:order 0 ;", "sh:order 0 ;", ""))

        assert (EX.n, EX.q, EX.x) in result.inferred_graph

    def test_both_rules_are_credited_with_a_triple_they_inferred_in_the_same_iteration(self) -> None:
        shapes = f"""
            ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:A, ex:B .
            ex:A a sh:SPARQLRule ; sh:runOnce true ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT {{ $this ex:p ex:x . }} WHERE {{ }}" .
            ex:B a sh:SPARQLRule ; sh:runOnce true ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT {{ $this ex:p ex:x . }} WHERE {{ }}" .
        """
        result = _apply(shapes, include_source_rule_provenance=True)

        graph = result.inferred_graph
        reifiers = {s for s, _, o in graph.triples((None, REIFIES, None)) if o == (EX.n, EX.p, EX.x)}
        sources = {rule for r in reifiers for rule in graph.objects(r, SH.sourceRule)}
        assert sources == {EX.A, EX.B}


class TestLayers:
    def test_a_fractional_layer_orders_like_any_number(self) -> None:
        """The vocabulary says the layer is numeric (xsd:integer or xsd:decimal); 0.5 used to raise ValueError."""
        shapes = """
            ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:Late, ex:Early .
            ex:Late a sh:SPARQLRule ; sh:layer 1.5 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:b true . } WHERE { $this ex:a true . }" .
            ex:Early a sh:SPARQLRule ; sh:layer 0.5 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:a true . } WHERE { }" .
        """
        result = _apply(shapes)

        assert (EX.n, EX.b, Literal(True)) in result.inferred_graph

    def test_a_global_rule_in_a_lower_layer_feeds_a_shape_rule_in_a_higher_layer(self) -> None:
        """The global rule makes ex:n an ex:C; only then does the shape that targets ex:C have a focus node."""
        shapes = """
            ex:Make a sh:SPARQLRule ; sh:layer 0 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ex:n a ex:C . } WHERE { }" .
            ex:CShape a sh:NodeShape ; sh:targetClass ex:C ; sh:rule ex:Use .
            ex:Use a sh:SPARQLRule ; sh:layer 1 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:done true . } WHERE { }" .
        """
        result = _apply(shapes, data="ex:other ex:marker true .")

        assert (EX.n, EX.done, Literal(True)) in result.inferred_graph

    def test_a_shape_rule_in_a_lower_layer_feeds_a_global_rule_in_a_higher_layer(self) -> None:
        shapes = """
            ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:First .
            ex:First a sh:SPARQLRule ; sh:layer 0 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:stage1 true . } WHERE { }" .
            ex:Second a sh:SPARQLRule ; sh:layer 1 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:stage2 true . } WHERE { ?s ex:stage1 true . }" .
        """
        result = _apply(shapes)

        assert (EX.n, EX.stage2, Literal(True)) in result.inferred_graph

    def test_a_global_run_once_rule_that_mints_blank_nodes_runs_once(self) -> None:
        shapes = """
            ex:Mint a sh:SPARQLRule ; sh:runOnce true ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ex:n ex:has _:fresh . } WHERE { }" .
        """
        result = _apply(shapes)

        assert len(list(result.inferred_graph.triples((EX.n, EX.has, None)))) == 1


class TestGlobalTripleRule:
    def test_a_triple_rule_no_shape_refers_to_infers_its_triple(self) -> None:
        """Section 8: a global rule runs with no focus node; section 11.2 evaluates its terms for it."""
        shapes = "ex:R a sh:TripleRule ; sh:subject ex:a ; sh:predicate ex:p ; sh:object ex:b ."

        result = _apply(shapes)

        assert (EX.a, EX.p, EX.b) in result.inferred_graph

    def test_a_missing_term_is_the_focus_node_and_a_global_rule_has_none(self) -> None:
        shapes = "ex:R a sh:TripleRule ; sh:predicate ex:p ; sh:object ex:b ."

        result = _apply(shapes)

        assert not list(result.inferred_graph.triples((None, EX.p, None)))

    def test_a_deactivated_global_triple_rule_is_ignored(self) -> None:
        shapes = "ex:R a sh:TripleRule ; sh:deactivated true ; sh:subject ex:a ; sh:predicate ex:p ; sh:object ex:b ."

        result = _apply(shapes)

        assert (EX.a, EX.p, EX.b) not in result.inferred_graph

    def test_a_global_triple_rule_joins_the_layers(self) -> None:
        shapes = """
            ex:R a sh:TripleRule ; sh:layer 0 ; sh:subject ex:n ; sh:predicate ex:stage1 ; sh:object true .
            ex:Second a sh:SPARQLRule ; sh:layer 1 ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:stage2 true . } WHERE { ?s ex:stage1 true . }" .
        """
        result = _apply(shapes)

        assert (EX.n, EX.stage2, Literal(True)) in result.inferred_graph

    def test_rule_sets_select_global_triple_rules_too(self) -> None:
        shapes = """
            ex:Set a sh:RuleSet ; sh:hasRule ex:In .
            ex:In a sh:TripleRule ; sh:subject ex:a ; sh:predicate ex:p ; sh:object ex:b .
            ex:Out a sh:TripleRule ; sh:subject ex:a ; sh:predicate ex:p ; sh:object ex:c .
        """
        result = _apply(shapes, rule_set=EX.Set)

        assert (EX.a, EX.p, EX.b) in result.inferred_graph
        assert (EX.a, EX.p, EX.c) not in result.inferred_graph


class TestDerivedTriplesPerLayer:
    SHAPES = """
        ex:RectangleShape a sh:NodeShape ; sh:targetClass ex:Rectangle ;
          sh:property [ sh:path ex:area ; sh:defaultValue 1 ] ;
          sh:rule ex:Layer0, ex:Layer2Without, ex:Layer1With .
        ex:Layer0 a sh:SPARQLRule ; sh:layer 0 ; sh:expectedPredicate ex:area ;
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:small0 true . } WHERE { $this ex:area ?a . }" .
        ex:Layer2Without a sh:SPARQLRule ; sh:layer 2 ;
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:small1 true . } WHERE { $this ex:area ?a . }" .
        ex:Layer1With a sh:SPARQLRule ; sh:layer 1 ; sh:expectedPredicate ex:area ;
          sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:small2 true . } WHERE { $this ex:area ?a . }" .
    """

    def test_derived_triples_are_computed_for_each_layer_and_removed_when_it_ends(self) -> None:
        result = _apply(self.SHAPES, data="ex:r a ex:Rectangle .")

        graph = result.inferred_graph
        assert (EX.r, EX.small0, Literal(True)) in graph, "layer 0 saw the derived area"
        assert (EX.r, EX.small2, Literal(True)) in graph, "a layer-1 rule that expects the predicate gets it again"
        assert (EX.r, EX.small1, Literal(True)) not in graph, "the area was removed when layer 1 ended"
        assert (EX.r, EX.area, Literal(1)) not in graph

    def test_a_derived_triple_a_rule_also_inferred_is_kept(self) -> None:
        shapes = """
            ex:RectangleShape a sh:NodeShape ; sh:targetClass ex:Rectangle ;
              sh:property [ sh:path ex:area ; sh:defaultValue 1 ] ; sh:rule ex:Same .
            ex:Same a sh:SPARQLRule ; sh:expectedPredicate ex:area ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:area 1 . } WHERE { }" .
        """
        result = _apply(shapes, data="ex:r a ex:Rectangle .")

        assert (EX.r, EX.area, Literal(1)) in result.inferred_graph


class TestRunOnceAcrossShapes:
    def test_a_run_once_rule_two_shapes_refer_to_runs_once_per_focus_node(self) -> None:
        shapes = """
            ex:S1 a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:Mint .
            ex:S2 a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:Mint .
            ex:Mint a sh:SPARQLRule ; sh:runOnce true ;
              sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:has _:fresh . } WHERE { }" .
        """
        result = _apply(shapes)

        assert len(list(result.inferred_graph.triples((EX.n, EX.has, None)))) == 1


def test_a_rule_that_is_neither_a_triple_rule_nor_a_sparql_rule_is_a_failure() -> None:
    from pyshacl.errors import RuleLoadError

    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:rule ex:Weird . ex:Weird a ex:Other ."

    with pytest.raises(RuleLoadError):
        _apply(shapes)
