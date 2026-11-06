"""Regression tests from the bug hunt: SHACL engine paths, targets, SPARQL constraints, rules, expressions, subgraphs."""

from __future__ import annotations

import warnings

from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.subgraph import extract_subgraph

warnings.simplefilter("ignore")

P = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
)


def G(text: str) -> StarLayerGraph:
    return StarLayerGraph().parse(data=P + text, format="turtle")


def _fragment_conforms(shapes: str, data: str) -> None:
    s, d = G(shapes), G(data)
    assert validate(d, s).conforms, "premise: the data conforms"
    frag = extract_subgraph(d, s)
    assert validate(frag, s).conforms, "the fragment of conforming data must conform"


def test_subgraph_negated_closed_keeps_extra_triples():
    _fragment_conforms(
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:not [ sh:closed true ; sh:ignoredProperties ( rdf:type ) ] .",
        'ex:n a ex:T ; ex:p "extra" .',
    )


def test_subgraph_node_shape_equals_keeps_second_path():
    _fragment_conforms("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:equals ex:self .", "ex:a ex:self ex:a .")
