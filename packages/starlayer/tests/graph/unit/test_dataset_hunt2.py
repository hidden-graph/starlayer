"""StarLayerDataset fixes from the third hunt (GitHub issue #99)."""

import warnings

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerDataset

_XSD = "http://www.w3.org/2001/XMLSchema#"


def URIRef(iri):  # noqa: N802
    return ox.NamedNode(str(iri))


def BNode(label=None):  # noqa: N802
    return ox.BlankNode(label) if label else ox.BlankNode()


def Literal(value, lang=None, datatype=None):  # noqa: N802
    if lang:
        return ox.Literal(str(value), language=lang)
    if datatype is not None:
        return ox.Literal(str(value), datatype=ox.NamedNode(str(datatype)))
    if isinstance(value, bool):
        return ox.Literal("true" if value else "false", datatype=ox.NamedNode(_XSD + "boolean"))
    if isinstance(value, int):
        return ox.Literal(str(value), datatype=ox.NamedNode(_XSD + "integer"))
    if isinstance(value, float):
        return ox.Literal(repr(value), datatype=ox.NamedNode(_XSD + "double"))
    return ox.Literal(value)


def TripleTerm(s, p, o):  # noqa: N802
    return ox.Triple(s, p, o)

warnings.simplefilter("ignore")
E = lambda n: URIRef("http://e/" + n)  # noqa: E731


def _with_graph():
    ds = StarLayerDataset(default_union=False)
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
    isolated = StarLayerDataset(default_union=False)
    isolated.graph(E("g")).add((E("a"), E("p"), E("b")))
    isolated.remove((E("a"), E("p"), E("b")))
    assert len(isolated.graph(E("g"))) == 1  # only the default graph was touched (len() of a non-union dataset counts the default graph only)


@pytest.mark.parametrize("fmt", ["trig12", "nq12"])
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
