"""SPARQL Update graph management on a dataset (GitHub issue #78).

Expected results are SPARQL 1.1 Update section 3: DEFAULT is the true default
graph, never the union of every graph.
"""

import pytest
from rdflib import URIRef
from starlayer.graph import StarLayerDataset

E = "http://e/"
DEFAULT = "urn:x-rdflib:default"
SETUP = f"INSERT DATA {{ <{E}a> <{E}p> <{E}b> . GRAPH <{E}g> {{ <{E}z> <{E}p> <{E}z> }} GRAPH <{E}h> {{ <{E}h1> <{E}p> <{E}h2> }} }}"


def _state(ds):
    return {
        (str(g.identifier) if str(g.identifier) != DEFAULT else None, str(s).removeprefix(E))
        for s, _p, _o, g in ds.quads((None, None, None, None))
    }


def _run(update, default_union=True):
    ds = StarLayerDataset(default_union=default_union)
    ds.update(SETUP)
    ds.update(update)
    return _state(ds)


A = (None, "a")
Z_G = (f"{E}g", "z")
H = (f"{E}h", "h1")


@pytest.mark.parametrize("default_union", [True, False])
@pytest.mark.parametrize(
    ("update", "expected"),
    [
        ("CLEAR DEFAULT", {Z_G, H}),
        ("DROP DEFAULT", {Z_G, H}),
        ("CLEAR NAMED", {A}),
        ("DROP NAMED", {A}),
        (f"CLEAR GRAPH <{E}g>", {A, H}),
        (f"DROP GRAPH <{E}g>", {A, H}),
        ("CLEAR ALL", set()),
        (f"COPY <{E}g> TO DEFAULT", {(None, "z"), Z_G, H}),
        (f"MOVE <{E}g> TO DEFAULT", {(None, "z"), H}),
        (f"ADD <{E}g> TO DEFAULT", {A, (None, "z"), Z_G, H}),
        (f"ADD DEFAULT TO <{E}g>", {A, (f"{E}g", "a"), Z_G, H}),
        (f"COPY DEFAULT TO <{E}g>", {A, (f"{E}g", "a"), H}),
        (f"MOVE DEFAULT TO <{E}g>", {(f"{E}g", "a"), H}),
        ("DELETE WHERE { GRAPH ?g { ?x ?p ?y } }", {A}),
        (f"DELETE WHERE {{ GRAPH <{E}g> {{ ?x ?p ?y }} }}", {A, H}),
        (f"CREATE GRAPH <{E}new>", {A, Z_G, H}),
    ],
)
def test_graph_management(update, expected, default_union):
    assert _run(update, default_union) == expected


def test_create_graph_twice_is_an_error_unless_silent():
    ds = StarLayerDataset()
    ds.update(SETUP)
    with pytest.raises(Exception, match="already exists"):
        ds.update(f"CREATE GRAPH <{E}g>")
    ds.update(f"CREATE SILENT GRAPH <{E}g>")
    assert _state(ds) == {A, Z_G, H}


def test_using_reads_a_graph_of_the_dataset_without_fetching_it():
    ds = StarLayerDataset()
    ds.update(SETUP)
    ds.update(f"INSERT {{ ?x <{E}u> ?y }} USING <{E}g> WHERE {{ ?x <{E}p> ?y }}")
    assert (None, "z") in _state(ds)
    assert (None, "a") in _state(ds)


def test_using_named_reads_a_graph_of_the_dataset_without_fetching_it():
    ds = StarLayerDataset()
    ds.update(SETUP)
    ds.update(f"INSERT {{ ?x <{E}u> ?y }} USING NAMED <{E}g> WHERE {{ GRAPH ?g {{ ?x <{E}p> ?y }} }}")
    assert (None, "z") in _state(ds)


def test_a_graph_created_by_an_update_is_visible_to_the_next_query():
    ds = StarLayerDataset()
    ds.update(f"INSERT DATA {{ GRAPH <{E}g1> {{ <{E}a> <{E}p> <{E}b> }} }}")
    assert len(list(ds.query(f"SELECT * {{ GRAPH <{E}g1> {{ ?s ?p ?o }} }}"))) == 1
    assert len(list(ds.query("SELECT * { GRAPH ?g { ?s ?p ?o } }"))) == 1
    assert ds.query(f"ASK {{ GRAPH <{E}g1> {{ ?s ?p ?o }} }}").askAnswer is True
    assert URIRef(f"{E}g1") in {c.identifier for c in ds.contexts()}
