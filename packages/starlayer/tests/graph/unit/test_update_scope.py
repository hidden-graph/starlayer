"""SPARQL Update on a ``StarLayerGraph`` stays within its graph: the unqualified is aimed at it, a graph named by IRI must be it."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import NamedNode, StarLayerDataset
from starlayer.graph.execution.update_scope import scope_update

G, OTHER = NamedNode("http://e/g"), NamedNode("http://e/other")
S, P, O1, O2 = NamedNode("http://e/s"), NamedNode("http://e/p"), NamedNode("http://e/o1"), NamedNode("http://e/o2")


@pytest.fixture
def pair():
    d = StarLayerDataset()
    g, other = d.graph(G), d.graph(OTHER)
    g.add((S, P, O1))
    other.add((S, P, O2))
    return d, g, other


def objects(graph):
    return {t[2] for t in graph.triples((None, None, None))}


def call(run, graph, text):
    return graph.update(text) if run == "update" else graph.ox.update(text)


@pytest.mark.parametrize("run", ["update", "ox"])
def test_unqualified_writes_land_in_the_graph(pair, run):
    d, g, other = pair
    call(run, g, "INSERT DATA { <http://e/s> <http://e/p> <http://e/o3> }")
    assert len(d.default_graph) == 0 and NamedNode("http://e/o3") in objects(g) and NamedNode("http://e/o3") not in objects(other)


@pytest.mark.parametrize("run", ["update", "ox"])
def test_a_pattern_update_reads_and_writes_the_graph_only(pair, run):
    d, g, other = pair
    call(run, g, "DELETE { ?s ?p ?o } INSERT { ?s <http://e/q> ?o } WHERE { ?s ?p ?o }")
    assert set(g.triples((None, None, None))) == {(S, NamedNode("http://e/q"), O1)}
    assert objects(other) == {O2} and len(d.default_graph) == 0  # the other graph was not read or written
    call(run, g, "DELETE WHERE { ?s ?p ?o }")
    assert len(g) == 0 and objects(other) == {O2}


def test_graph_variable_in_where_sees_only_this_graph(pair):
    _, g, other = pair
    g.update("INSERT { <http://e/seen> <http://e/in> ?o } WHERE { GRAPH ?x { ?s ?p ?o } }")
    assert (NamedNode("http://e/seen"), NamedNode("http://e/in"), O1) in set(g.triples((None, None, None)))
    assert (NamedNode("http://e/seen"), NamedNode("http://e/in"), O2) not in set(g.triples((None, None, None)))


@pytest.mark.parametrize("run", ["update", "ox"])
@pytest.mark.parametrize("text", ["CLEAR ALL", "CLEAR NAMED", "CLEAR DEFAULT", "DROP ALL", "CLEAR GRAPH <http://e/g>", "DROP GRAPH <http://e/g>"])
def test_clear_and_drop_act_on_the_graph_only(pair, run, text):
    d, g, other = pair
    call(run, g, text)
    assert len(g) == 0 and objects(other) == {O2}


@pytest.mark.parametrize("run", ["update", "ox"])
@pytest.mark.parametrize(
    "text",
    [
        "INSERT DATA { GRAPH <http://e/other> { <http://e/s> <http://e/p> 1 } }",
        "DELETE DATA { GRAPH <http://e/other> { <http://e/s> <http://e/p> <http://e/o2> } }",
        "DELETE WHERE { GRAPH <http://e/other> { ?s ?p ?o } }",
        "WITH <http://e/other> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
        "INSERT { ?s ?p ?o } USING <http://e/other> WHERE { ?s ?p ?o }",
        "INSERT { ?s ?p ?o } USING NAMED <http://e/other> WHERE { GRAPH ?g { ?s ?p ?o } }",
        "INSERT { GRAPH <http://e/other> { ?s ?p ?o } } WHERE { ?s ?p ?o }",
        "INSERT { GRAPH ?x { ?s ?p ?o } } WHERE { GRAPH ?x { ?s ?p ?o } }",
        "INSERT { ?s ?p ?o } WHERE { GRAPH <http://e/other> { ?s ?p ?o } }",
        "CLEAR GRAPH <http://e/other>",
        "DROP SILENT GRAPH <http://e/other>",
        "CREATE GRAPH <http://e/other>",
        "LOAD <http://e/src> INTO GRAPH <http://e/other>",
        "COPY <http://e/g> TO <http://e/other>",
        "MOVE <http://e/other> TO <http://e/g>",
        "ADD DEFAULT TO <http://e/other>",
    ],
)
def test_naming_another_graph_is_refused_and_nothing_changes(pair, run, text):
    d, g, other = pair
    with pytest.raises(ValueError, match="holds graph"):
        call(run, g, text)
    assert objects(g) == {O1} and objects(other) == {O2} and len(d.default_graph) == 0


def test_the_graph_named_by_its_own_iri_is_fine(pair):
    _, g, _ = pair
    g.update("WITH <http://e/g> DELETE { ?s ?p ?o } INSERT { ?s ?p <http://e/new> } WHERE { ?s ?p ?o }")
    g.update("INSERT DATA { GRAPH <http://e/g> { <http://e/s> <http://e/p> <http://e/o9> } }")
    g.update("INSERT { ?s <http://e/q> ?o } USING <http://e/g> WHERE { ?s ?p ?o }")
    assert NamedNode("http://e/new") in objects(g) and NamedNode("http://e/o9") in objects(g)


def test_a_default_graph_stays_with_the_default_graph():
    d = StarLayerDataset()
    default, other = d.default_graph, d.graph(OTHER)
    default.add((S, P, O1))
    other.add((S, P, O2))
    default.update("INSERT DATA { <http://e/s> <http://e/p> <http://e/o3> }")
    assert len(default) == 2 and objects(other) == {O2}
    for text in ("INSERT DATA { GRAPH <http://e/other> { <http://e/s> <http://e/p> 1 } }", "CLEAR GRAPH <http://e/other>", "WITH <http://e/other> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }"):
        with pytest.raises(ValueError):
            default.update(text)
    default.update("CLEAR NAMED")  # nothing in the default graph's scope to act on
    assert len(default) == 2 and objects(other) == {O2}
    default.update("CLEAR ALL")
    assert len(default) == 0 and objects(other) == {O2}


def test_a_dataset_is_not_scoped(pair):
    d, g, other = pair
    d.update("INSERT DATA { GRAPH <http://e/other> { <http://e/s> <http://e/p> 1 } }")
    assert len(other) == 2
    d.update("CLEAR ALL")
    assert len(g) == 0 and len(other) == 0


def test_the_graphs_prefixes_and_a_syntax_error(pair):
    _, g, other = pair
    g.bind("ex", "http://e/")
    g.update("INSERT DATA { ex:s ex:p ex:o4 }")
    assert NamedNode("http://e/o4") in objects(g) and NamedNode("http://e/o4") not in objects(other)
    g.ox.update("INSERT DATA { x:s x:p x:o5 }", prefixes={"x": "http://e/"})
    assert NamedNode("http://e/o5") in objects(g)
    with pytest.raises(FormatError):
        g.update("INSERT DATA { <http://e/s> ")


def test_an_update_that_needs_no_edit_is_returned_as_written():
    text = "INSERT DATA { GRAPH <http://e/g> { <http://e/s> <http://e/p> 1 } }"
    assert scope_update(text, G) == text
    assert scope_update("INSERT DATA { <http://e/s> <http://e/p> 1 }", ox.DefaultGraph()) == "INSERT DATA { <http://e/s> <http://e/p> 1 }"
    with pytest.raises(ValueError, match="blank-node"):
        scope_update(text, ox.BlankNode())
