"""TriG 1.2 output must round-trip literal values exactly (multi-line strings were re-indented on every save).

Regression tests for the trig12 serializer indenting the continuation lines of triple-quoted literals.
"""

import pytest
from starlayer import StarLayerDataset
from starlayer.graph import Literal, URIRef

A, P = URIRef("http://e/a"), URIRef("http://e/p")
G1, G2 = URIRef("http://e/g1"), URIRef("http://e/g2")

VALUES = {
    "indented lines": "first line\n\n    indented four\n        indented eight",
    "blank lines and trailing space": "one  \n\n\ntwo\n",
    "embedded triple quotes": 'He said """hi""" and left\n    then "quoted"',
    "ends with a quote": 'multi\nline "',
    "tabs": "a\n\tb\n\t\tc",
    "single line": "no newline at all",
}


def _round_trip(dataset: StarLayerDataset) -> StarLayerDataset:
    back = StarLayerDataset()
    back.parse(data=dataset.serialize(format="trig12"), format="trig12")
    return back


def _values(dataset: StarLayerDataset) -> dict[str, set[str]]:
    return {str(c.identifier): {str(o) for _s, _p, o in c} for c in dataset.contexts() if len(c)}


@pytest.mark.parametrize("name", VALUES)
def test_a_multi_line_literal_survives_a_trig12_round_trip(name):
    dataset = StarLayerDataset()
    dataset.graph(G1).add((A, P, Literal(VALUES[name])))
    assert _values(_round_trip(dataset)) == {str(G1): {VALUES[name]}}


def test_a_second_round_trip_changes_nothing():
    dataset = StarLayerDataset()
    dataset.graph(G1).add((A, P, Literal(VALUES["indented lines"])))
    dataset.graph(G2).add((A, P, Literal(VALUES["blank lines and trailing space"])))
    once = _round_trip(dataset)
    twice = _round_trip(once)
    assert _values(once) == _values(dataset) == _values(twice)
    assert once.serialize(format="trig12") == twice.serialize(format="trig12")


def test_graph_blocks_are_still_indented_outside_string_literals():
    dataset = StarLayerDataset()
    dataset.graph(G1).add((A, P, Literal("x\n    y")))
    text = dataset.serialize(format="trig12")
    assert "GRAPH <http://e/g1> {\n    " in text, "the statement itself is still indented"
    assert "\n    y" in text and "\n        y" not in text, "the string's own continuation line is left alone"


@pytest.mark.parametrize("fmt", ["trig12", "nq12", "trix12"])
def test_graphs_are_written_in_a_fixed_order_whatever_order_they_were_added_in(fmt):
    # contexts() follows the store's hash order (PYTHONHASHSEED), so a round trip used to reorder the graphs.
    forward, backward = StarLayerDataset(), StarLayerDataset()
    for dataset, graphs in ((forward, (G1, G2)), (backward, (G2, G1))):
        for g in graphs:
            dataset.graph(g).add((A, P, Literal(str(g))))
    text = forward.serialize(format=fmt)
    assert text == backward.serialize(format=fmt)
    assert text.index(str(G1)) < text.index(str(G2))
