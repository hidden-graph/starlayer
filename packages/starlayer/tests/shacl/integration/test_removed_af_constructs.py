"""SHACL 1.2 SPARQL-Related Features, Appendix F: SPARQL-based targets (``sh:target`` with ``sh:SPARQLTarget`` /
``sh:SPARQLTargetType``) are no longer defined and ``sh:SPARQLFunction`` is replaced. A shapes graph that uses them is a
``ShapeError`` in every entry point; before, the target was silently ignored and the shape validated nothing (``conforms``)."""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl import ShapeError, evaluate, extract_subgraph, validate

PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
DATA = PREFIXES + "ex:a a ex:P ; ex:v 1 . ex:b a ex:Q ."

CASES = {
    "sparql target": 'ex:S a sh:NodeShape ; sh:target [ a sh:SPARQLTarget ; sh:select "SELECT ?this WHERE { ?this a ex:P }" ] .',
    "target of any kind": "ex:S a sh:NodeShape ; sh:target ex:SomeTarget .",
    "sparql target type": 'ex:T a sh:SPARQLTargetType ; sh:parameter [ sh:path ex:cls ] ; sh:select "SELECT ?this WHERE { ?this a $cls }" .',
    "sparql function": 'ex:f a sh:SPARQLFunction ; sh:parameter [ sh:path ex:x ] ; sh:select "SELECT ?r WHERE { BIND($x AS ?r) }" .',
}


def _g(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl if "@prefix" not in ttl else ttl, format="turtle12")
    return g


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("entry", ["validate", "evaluate", "extract_subgraph"])
def test_a_removed_construct_is_a_shape_error_naming_the_replacement(case: str, entry: str) -> None:
    shapes = _g(CASES[case])
    call = {"validate": lambda: validate(_g(DATA), shapes, meta_shacl=False), "evaluate": lambda: evaluate(_g(DATA), shapes),
            "extract_subgraph": lambda: extract_subgraph(_g(DATA), shapes)}[entry]
    with pytest.raises(ShapeError, match="no longer defines") as excinfo:
        call()
    assert "sh:targetNode" in str(excinfo.value) and "Appendix F" in str(excinfo.value)


def test_a_node_expression_target_is_the_replacement_and_works() -> None:
    shapes = _g(
        'ex:S a sh:NodeShape ; sh:targetNode [ sh:select "SELECT ?n WHERE { ?n a <http://example.org/P> }" ] ; '
        "sh:property [ sh:path ex:w ; sh:minCount 1 ] ."
    )
    result = validate(_g(DATA), shapes, meta_shacl=False)
    assert not result.conforms  # ex:a is targeted and has no ex:w; the shape does check something


def test_the_vocabulary_that_still_lists_the_terms_is_not_refused() -> None:
    from starlayer.starontology import get_ontology_graph

    vocabulary = get_ontology_graph("shacl_vocabulary")
    assert validate(_g(DATA), vocabulary, meta_shacl=False).conforms  # the terms are declared there, not used


@pytest.mark.parametrize("case", CASES)
def test_the_meta_shapes_reject_a_removed_construct(case: str) -> None:
    from starlayer.shacl import MetaShaclError

    with pytest.raises(MetaShaclError, match="SHACL 1.2 does not define"):
        validate(_g(DATA), _g(CASES[case]), meta_shacl=True)


def test_the_meta_shapes_still_accept_a_valid_shape() -> None:
    shapes = _g('ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:v ; sh:minCount 1 ] .')
    assert validate(_g(DATA), shapes, meta_shacl=True).conforms
