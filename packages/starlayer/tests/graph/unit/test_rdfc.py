"""starlayer.graph.rdfc: the public canonical N-Quads / hash entry points over Oxigraph's RDFC-1.0 (the W3C suite runs in
``test_rdfc_native.py``)."""

from __future__ import annotations

import hashlib

import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.rdfc import (
    CanonicalizationComplexityError,
    rdfc10_hash,
    to_canonical_nquads,
)

EX = "@prefix ex: <http://example.org/> . "


def _graph(text: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=EX + text, format="turtle")
    return g


def test_blank_nodes_get_canonical_labels_and_the_text_is_sorted():
    g = _graph('ex:a ex:p _:x . _:x ex:q "v" .')
    text = to_canonical_nquads(g)
    assert text == '<http://example.org/a> <http://example.org/p> _:c14n0 .\n_:c14n0 <http://example.org/q> "v" .\n'


def test_hash_is_sha256_of_the_canonical_text_and_ignores_labels():
    a, b = _graph("ex:a ex:p _:one . _:one ex:p 1 ."), _graph("ex:a ex:p _:two . _:two ex:p 1 .")
    assert rdfc10_hash(a) == rdfc10_hash(b) == hashlib.sha256(to_canonical_nquads(a).encode()).hexdigest()


def test_sha384_and_unsupported_algorithms():
    g = _graph("ex:a ex:p _:b .")
    assert len(rdfc10_hash(g, hash_algorithm="sha384")) == 96
    assert rdfc10_hash(g, hash_algorithm="sha256") != rdfc10_hash(g, hash_algorithm="sha384")
    with pytest.raises(ValueError):
        rdfc10_hash(g, hash_algorithm="md5")


def test_a_dataset_hash_counts_graph_names():
    a, b = StarLayerDataset(), StarLayerDataset()
    line = "<http://example.org/s> <http://example.org/p> <http://example.org/o> <http://example.org/%s> ."
    a.parse(data=line % "g1", format="nquads")
    b.parse(data=line % "g2", format="nquads")
    assert rdfc10_hash(a) != rdfc10_hash(b)


def test_an_rdflib_graph_gives_the_same_text():
    import rdflib

    g = rdflib.Graph()
    g.parse(data=EX + 'ex:a ex:p [ ex:q "x" ] .', format="turtle")
    assert to_canonical_nquads(g) == to_canonical_nquads(_graph('ex:a ex:p [ ex:q "x" ] .'))


def test_a_symmetric_blank_node_graph_raises_the_complexity_error():
    ring = "".join(f"_:b{i} ex:p _:b{j} . " for i in range(10) for j in range(10) if i != j)
    g = _graph(ring)
    with pytest.raises(CanonicalizationComplexityError):
        to_canonical_nquads(g)
    with pytest.raises(CanonicalizationComplexityError):
        rdfc10_hash(g)
