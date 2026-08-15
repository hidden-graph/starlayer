"""``sh:sourceRule`` (SHACL 1.2 SPARQL Extensions section 8.7): opt-in
provenance tracking linking each rule-inferred triple back to the rule that
produced it, via a reifier (``_:id rdf:reifies <<( s p o )>> . _:id
sh:sourceRule <rule> .``). Off by default - the spec says a rule engine MAY
generate these triples, and they add nothing but noise to a caller who
didn't ask for them.

Covers both rule-execution paths this codebase has: shape-attached
``sh:rule``s (executed internally by pySHACL, intercepted via
``_patch_rule_apply_for_source_rule_provenance``) and standalone/global
``sh:SPARQLRule``s with no ``sh:rule`` edge (``_global_sparql_rule_triples``,
native starshacl code) - see ``tests/integration/test_global_sparql_rules.py``
for the base behavior these build on.
"""

import pytest
from rdflib import Literal, Namespace, URIRef

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

pyshacl = pytest.importorskip("pyshacl")


def _source_rule_for(graph, triple_term) -> set:
    """Every ``sh:sourceRule`` value linked to ``triple_term`` via a reifier
    in ``graph`` - empty if none."""
    reifiers = {s for s, _, o in graph.triples((None, REIFIES, None)) if o == triple_term}
    values = set()
    for reifier in reifiers:
        values.update(graph.objects(reifier, SH.sourceRule))
    return values


def _two_rule_shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:rule ex:AgeRule, ex:NameRule .

            ex:AgeRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { $this ex:isAdult true . }
                WHERE { $this ex:age ?age . FILTER(?age >= 18) }
              \"\"\" .

            ex:NameRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { $this ex:hasName true . }
                WHERE { $this ex:name ?n . }
              \"\"\" .
        """,
        format="turtle",
    )
    return shapes


def _two_rule_data() -> StarLayerGraph:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person ; ex:age 30 ; ex:name "Alice" .
        """,
        format="turtle",
    )
    return data


def test_source_rule_provenance_off_by_default_adds_nothing() -> None:
    shapes = _two_rule_shapes()
    data = _two_rule_data()

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.Alice, EX.isAdult, Literal(True)) in result.data_graph
    assert (EX.Alice, EX.hasName, Literal(True)) in result.data_graph
    assert next(result.data_graph.triples((None, REIFIES, None)), None) is None
    assert next(result.data_graph.triples((None, SH.sourceRule, None)), None) is None


def test_source_rule_provenance_attributes_each_triple_to_its_own_rule() -> None:
    shapes = _two_rule_shapes()
    data = _two_rule_data()

    result = StarShaclValidator().apply_rules(
        data_graph=data,
        shacl_graph=shapes,
        meta_shacl=False,
        include_source_rule_provenance=True,
    )

    age_triple = TripleTerm(EX.Alice, EX.isAdult, Literal(True))
    name_triple = TripleTerm(EX.Alice, EX.hasName, Literal(True))

    assert _source_rule_for(result.data_graph, age_triple) == {EX.AgeRule}
    assert _source_rule_for(result.data_graph, name_triple) == {EX.NameRule}
    # Not swapped/merged - each triple's provenance is exclusively its own rule.
    assert EX.NameRule not in _source_rule_for(result.data_graph, age_triple)
    assert EX.AgeRule not in _source_rule_for(result.data_graph, name_triple)


def test_source_rule_provenance_covers_global_sparql_rules_too() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:SymmetricPropertyRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { ?o ?p ?s . }
                WHERE { ?p a ex:SymmetricProperty . ?s ?p ?o . }
              \"\"\" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:friend a ex:SymmetricProperty .
            ex:Bob ex:friend ex:Caren .
        """,
        format="turtle",
    )

    result = StarShaclValidator().apply_rules(
        data_graph=data,
        shacl_graph=shapes,
        meta_shacl=False,
        include_source_rule_provenance=True,
    )

    inferred = TripleTerm(EX.Caren, EX.friend, EX.Bob)
    assert (EX.Caren, EX.friend, EX.Bob) in result.data_graph
    assert _source_rule_for(result.data_graph, inferred) == {EX.SymmetricPropertyRule}


def test_source_rule_provenance_not_visible_to_executing_rules() -> None:
    """SHACL 1.2 SPARQL Extensions section 8.7: "the [provenance] triples
    MUST NOT be visible to executing rules." A second rule's own WHERE
    clause here specifically looks for any sh:sourceRule triple - if
    provenance were added mid-execution rather than deferred to the very
    end, this rule would spuriously fire and produce ex:Leak."""
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:rule ex:NameRule, ex:LeakDetectorRule .

            ex:NameRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { $this ex:hasName true . }
                WHERE { $this ex:name ?n . }
              \"\"\" .

            ex:LeakDetectorRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                PREFIX sh: <http://www.w3.org/ns/shacl#>
                CONSTRUCT { ex:Leak ex:detected true . }
                WHERE { ?r sh:sourceRule ?anyRule . }
              \"\"\" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice a ex:Person ; ex:name "Alice" .
        """,
        format="turtle",
    )

    result = StarShaclValidator().apply_rules(
        data_graph=data,
        shacl_graph=shapes,
        meta_shacl=False,
        include_source_rule_provenance=True,
    )

    assert (EX.Alice, EX.hasName, Literal(True)) in result.data_graph
    assert (EX.Leak, EX.detected, Literal(True)) not in result.data_graph
    # And provenance was still correctly added after execution finished.
    name_triple = TripleTerm(EX.Alice, EX.hasName, Literal(True))
    assert _source_rule_for(result.data_graph, name_triple) == {EX.NameRule}
