"""The SalG constraint components on the native engine agree with the pySHACL-backed validator on the same data."""

from __future__ import annotations

from collections import Counter

import pytest
import starlayer.sparql
from rdflib import Graph
from rdflib.namespace import SH
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.components.registry import REGISTRY
from starlayer.sparql import salg

QUERIES = [
    "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> }",
    "SELECT ?x WHERE { ?x a <http://example.org/Foo> }",
    "SELECT ?x ?z WHERE { ?x <http://example.org/p> ?y OPTIONAL { ?x <http://example.org/q> ?z } }",
    "SELECT ?x ?w WHERE { ?x <http://example.org/p> ?y BIND(1 AS ?w) }",
    "SELECT ?x ?v WHERE { VALUES ?v { 1 2 } ?x <http://example.org/p> ?v }",
    "SELECT * WHERE { ?x <http://example.org/p> ?y }",
]


def _graph(text: str) -> Graph:
    graph, _root = starlayer.sparql.query_to_rdf(starlayer.sparql.prepare_query_12(text))
    return graph


def _results(report: Graph) -> Counter:
    """Component, value and severity of each result. The focus node is left out: both reports name the same blank node
    but describe it with different inferred rdfs:Resource typings of its list nodes, which is not what is compared."""
    return Counter(
        (
            next(report.objects(r, SH.sourceConstraintComponent), None),
            str(next(report.objects(r, SH.value), "")),
            next(report.objects(r, SH.resultSeverity), None),
        )
        for r in report.objects(None, SH.result)
    )


def _new(graph: Graph):
    return validate(graph, salg.shapes_graph(), ont_graph=salg.ontology_graph(), inference=ENTAILMENT.RDFS)


@pytest.mark.parametrize("query", QUERIES)
def test_old_and_new_agree(query):
    graph = _graph(query)
    old_conforms, old_report, _ = salg.validate_query(_graph(query))
    new = _new(graph)
    assert new.conforms == old_conforms
    assert _results(new.report_graph) == _results(old_report)


def test_unbound_variable_is_reported_with_the_salg_component():
    new = _new(_graph(QUERIES[0]))
    assert not new.conforms
    components = set(new.report_graph.objects(None, SH.sourceConstraintComponent))
    assert starlayer.sparql.SALG.NoUnboundProjectedVariablesConstraintComponent in components
    assert "y" in {str(v) for v in new.report_graph.objects(None, SH.value)}


def test_component_is_registered_without_importing_salg_in_the_engine():
    assert starlayer.sparql.SALG.NoUnboundProjectedVariablesConstraintComponent in REGISTRY


def test_register_is_idempotent_and_installs_the_real_function():
    from starlayer.sparql.salg import engine_components

    engine_components.register()
    engine_components.register()
    iri = starlayer.sparql.SALG.NoUnboundProjectedVariablesConstraintComponent
    assert REGISTRY[iri].fn is engine_components.no_unbound_projected_variables


def test_non_boolean_marker_is_a_shape_error():
    from starlayer.shacl_engine.plan import ShapeError

    shapes = StarLayerGraph()
    shapes.parse(
        data="""@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix salg: <https://github.com/hidden-graph/starlayer/ns/sparql/algebra#> .
        <urn:S> a sh:NodeShape ; sh:targetClass salg:Project ; salg:noUnboundProjectedVariables "yes" .""",
        format="turtle",
    )
    with pytest.raises(ShapeError):
        validate(_graph(QUERIES[0]), shapes)
