"""StarLayerDataset fixes from the third hunt (GitHub issue #99)."""

import warnings

import pytest
from rdflib import URIRef
from starlayer.graph import StarLayerDataset, TripleTerm

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731
TRIX = (
    '<?xml version="1.0"?><TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/"><graph><uri>http://e/g</uri>'
    "<triple><uri>http://e/a</uri><uri>http://e/p</uri><uri>http://e/b</uri></triple></graph></TriX>"
)


def _with_graph():
    ds = StarLayerDataset()
    ds.graph(E("g")).add((E("a"), E("p"), E("b")))
    return ds


def _graph_rows(ds):
    return len(list(ds.query("SELECT * { GRAPH ?g { ?s ?p ?o } }")))


def test_remove_graph_is_seen_by_the_next_query():
    ds = _with_graph()
    assert _graph_rows(ds) == 1  # fills the cached execution graph
    ds.remove_graph(ds.graph(E("g")))
    assert _graph_rows(ds) == 0
    assert len(ds) == 0


def test_a_removed_graph_can_be_recreated():
    ds = _with_graph()
    _graph_rows(ds)
    ds.remove_graph(ds.graph(E("g")))
    ds.graph(E("g")).add((E("x"), E("p"), E("y")))
    assert _graph_rows(ds) == 1


@pytest.mark.parametrize(
    ("fmt", "data"),
    [
        ("trig", "GRAPH <http://e/g> { <http://e/a> <http://e/p> <http://e/b> }"),
        ("nquads", "<http://e/a> <http://e/p> <http://e/b> <http://e/g> ."),
        ("nq", "<http://e/a> <http://e/p> <http://e/b> <http://e/g> ."),
        ("trix", TRIX),
    ],
)
def test_rdflib_names_of_the_multi_graph_formats_parse(fmt, data):
    ds = StarLayerDataset()
    ds.parse(data=data, format=fmt)
    assert (E("a"), E("p"), E("b")) in ds.graph(E("g"))
    assert _graph_rows(ds) == 1


def test_contains_for_triples_and_quads():
    ds = _with_graph()
    assert (E("a"), E("p"), E("b"), E("g")) in ds
    assert (E("a"), E("p"), E("b"), E("other")) not in ds
    assert (E("a"), E("p"), E("b")) not in ds  # default_union is off: only the default graph is searched
    union = StarLayerDataset(default_union=True)
    union.graph(E("g")).add((E("a"), E("p"), E("b")))
    assert (E("a"), E("p"), E("b")) in union


def test_len_does_not_count_the_triple_term_encoding():
    ds = StarLayerDataset()
    ds.graph(E("g")).add((E("a"), E("p"), TripleTerm(E("x"), E("y"), E("z"))))
    assert len(ds) == 1
    ds.graph(E("h")).add((E("a"), E("q"), E("b")))
    assert len(ds) == 2


def test_add_and_remove_take_quads():
    ds = StarLayerDataset()
    ds.add((E("s"), E("p"), E("o"), E("h")))
    assert (E("s"), E("p"), E("o")) in ds.graph(E("h"))
    assert len(ds) == 1
    ds.remove((E("s"), E("p"), E("o"), E("h")))
    assert len(ds) == 0


def test_remove_of_a_triple_follows_default_union():
    union = StarLayerDataset(default_union=True)
    union.graph(E("g")).add((E("a"), E("p"), E("b")))
    union.add((E("a"), E("p"), E("b")))
    union.remove((E("a"), E("p"), E("b")))
    assert len(union) == 0
    isolated = StarLayerDataset()
    isolated.graph(E("g")).add((E("a"), E("p"), E("b")))
    isolated.remove((E("a"), E("p"), E("b")))
    assert len(isolated) == 1  # the default graph only


@pytest.mark.parametrize("fmt", ["trig12", "nq12", "trix12"])
def test_default_graph_is_written_without_a_name_and_read_back_as_default(fmt):
    ds = StarLayerDataset()
    ds.add((E("a"), E("p"), E("b")))
    ds.graph(E("g")).add((E("c"), E("p"), E("d")))
    text = ds.serialize(format=fmt)
    assert "urn:x-rdflib:default" not in text
    again = StarLayerDataset()
    again.parse(data=text, format=fmt)
    assert (E("a"), E("p"), E("b")) in again.default_graph
    assert (E("c"), E("p"), E("d")) in again.graph(E("g"))
    assert len(again) == 2
