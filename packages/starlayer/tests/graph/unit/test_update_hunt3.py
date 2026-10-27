"""SPARQL Update fixes from the third bug hunt (GitHub issue #135).

Expected results are SPARQL 1.1 Update 3.1 and 3.2; pyoxigraph (the in-process native store) is the oracle.
"""

import subprocess
import sys
import textwrap
import warnings

import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph

warnings.simplefilter("ignore")
P = "PREFIX : <http://e/> "
DEFAULT = "urn:x-rdflib:default"


def _dataset(kind, default_union):
    if kind == "mem":
        return StarLayerDataset(default_union=default_union)
    oxrdflib = pytest.importorskip("oxrdflib")
    return StarLayerDataset(store=oxrdflib.OxigraphStore(), backend="rdf-1.2", default_union=default_union)


def _quads(ds):
    return sorted(
        (str(g.identifier if hasattr(g, "identifier") else g).removeprefix("http://e/"),
         str(s).removeprefix("http://e/"), str(o).removeprefix("http://e/"))
        for s, _p, o, g in ds.quads((None, None, None, None))
    )


def _run(kind, default_union, setup, *updates):
    ds = _dataset(kind, default_union)
    ds.update(P + setup)
    for u in updates:
        ds.update(P + u)
    return _quads(ds)


STORES = pytest.mark.parametrize("kind", ["mem", "ox"])
UNION = pytest.mark.parametrize("default_union", [False, True])

BOTH = "INSERT DATA { :a :p :b . GRAPH :g2 { :a :p :b } }"


@STORES
@UNION
@pytest.mark.parametrize(
    "delete",
    [
        "DELETE DATA { :a :p :b }",
        "DELETE WHERE { :a :p ?o }",
        "DELETE { ?s :p ?o } WHERE { ?s :p ?o }",
        "DELETE { :a :p :b } WHERE {}",
    ],
)
def test_deleting_from_the_default_graph_leaves_the_named_graphs(kind, default_union, delete):
    assert _run(kind, default_union, BOTH, delete) == [("g2", "a", "b")]


@STORES
@UNION
def test_delete_and_insert_of_the_same_template_never_removes_named_graph_data(kind, default_union):
    setup = "INSERT DATA { :a :p :b . GRAPH :g1 { :x :p :y } }"
    before = _run(kind, default_union, setup)
    after = _run(kind, default_union, setup, "DELETE { ?s :p ?o } INSERT { ?s :p ?o } WHERE { ?s :p ?o }")
    assert set(before) <= set(after)
    if not default_union:
        assert after == before  # with the union the insert also copies the named-graph triples into the default graph


def test_deleting_from_a_named_graph_still_works():
    state = _run("mem", True, BOTH, "DELETE DATA { GRAPH :g2 { :a :p :b } }")
    assert [q[0] for q in state] == [DEFAULT]
    state = _run("mem", False, BOTH, "WITH :g2 DELETE { ?s :p ?o } WHERE { ?s :p ?o }")
    assert [q[0] for q in state] == [DEFAULT]


SETUP2 = "INSERT DATA { :a :p :b . GRAPH :g1 { :x :p :y } GRAPH :g2 { :m :p :n } }"


@STORES
@UNION
def test_using_named_restricts_graph_variable_and_empties_the_default_graph(kind, default_union):
    state = _run(kind, default_union, SETUP2, "INSERT { ?s :r ?g } USING NAMED :g1 WHERE { GRAPH ?g { ?s :p ?o } }")
    assert (DEFAULT, "x", "g1") in state
    assert (DEFAULT, "m", "g2") not in state
    state = _run(kind, default_union, SETUP2, "INSERT { :x :y ?s } USING NAMED :g1 WHERE { ?s :p ?o }")
    assert len(state) == 3


@STORES
@UNION
def test_delete_using_graph_writes_to_the_default_graph_not_the_using_graph(kind, default_union):
    before = _run(kind, default_union, SETUP2)
    assert _run(kind, default_union, SETUP2, "DELETE { ?s :p ?o } USING :g1 WHERE { ?s :p ?o }") == before


@STORES
@UNION
def test_using_named_in_a_delete_only_reaches_listed_graphs(kind, default_union):
    setup = "INSERT DATA { :a :p 1 . GRAPH :g1 { :a :p 10 } GRAPH :g2 { :b :p 20 } }"
    state = _run(kind, default_union, setup, "DELETE { GRAPH ?g { ?s :p ?o } } USING NAMED :g2 WHERE { GRAPH ?g { ?s :p ?o } }")
    assert ("g1", "a", "10") in state
    assert not any(q[0] == "g2" for q in state)


@STORES
def test_templates_that_are_not_valid_triples_are_skipped(kind):
    setup = "INSERT DATA { :a :p 1 }"
    before = _run(kind, False, setup)
    for update in [
        "INSERT { ?o :u ?s } WHERE { ?s :p ?o }",
        "INSERT { ?s ?o ?s } WHERE { ?s :p ?o }",
        "INSERT { GRAPH ?z { ?s :u ?s } } WHERE { ?s :p ?o }",
        "INSERT { GRAPH ?o { ?s :u ?s } } WHERE { ?s :p ?o }",
        "DELETE { ?o :u ?s } WHERE { ?s :p ?o }",
    ]:
        assert _run(kind, False, setup, update) == before, update


def test_a_valid_template_next_to_an_invalid_one_is_still_applied():
    state = _run("mem", False, "INSERT DATA { :a :p 1 }", "INSERT { ?s :ok ?o . ?o :bad ?s } WHERE { ?s :p ?o }")
    assert (DEFAULT, "a", "1") in state
    assert len(state) == 2


@UNION
def test_native_default_union_reaches_update_where(default_union):
    mem = _run("mem", default_union, SETUP2, "INSERT { ?s :r ?o } WHERE { ?s :p ?o }")
    ox = _run("ox", default_union, SETUP2, "INSERT { ?s :r ?o } WHERE { ?s :p ?o }")
    assert ox == mem
    mem = _run("mem", default_union, SETUP2, "DELETE { ?s :p ?o } WHERE { ?s :p ?o }")
    ox = _run("ox", default_union, SETUP2, "DELETE { ?s :p ?o } WHERE { ?s :p ?o }")
    assert ox == mem


def test_native_default_union_update_with_a_triple_term_is_refused_not_silently_wrong():
    ds = _dataset("ox", True)
    ds.update(P + SETUP2)
    with pytest.raises(NotImplementedError):
        ds.update(P + "INSERT { ?s :r <<( :a :p :b )>> } WHERE { ?s :p ?o }")


@pytest.mark.parametrize(
    ("kind", "update"),
    [
        (kind, update)
        for kind in ("mem", "ox")
        for update in ("CLEAR GRAPH :nope", "DROP GRAPH :nope", "MOVE :nope TO :g1")
    ]
    # pyoxigraph copies and adds a missing graph as empty without an error, against the spec; the in-memory store follows it
    + [("mem", "COPY :nope TO :g1"), ("mem", "ADD :nope TO :g1")],
)
def test_graph_management_of_a_missing_graph_is_an_error_without_silent(kind, update):
    ds = _dataset(kind, False)
    ds.update(P + "INSERT DATA { GRAPH :g1 { :a :p :b } }")
    with pytest.raises(Exception, match="does not exist"):
        ds.update(P + update)
    verb, rest = update.split(" ", 1)
    ds.update(P + f"{verb} SILENT {rest}")
    if kind == "mem":  # pyoxigraph empties the target of MOVE SILENT from a missing graph
        assert _quads(ds) == [("g1", "a", "b")]


def test_clearing_an_existing_empty_graph_is_not_an_error():
    ds = StarLayerDataset()
    ds.update(P + "INSERT DATA { GRAPH :g1 { :a :p :b } }")
    ds.update(P + "CLEAR GRAPH :g1")
    ds.update(P + "CLEAR GRAPH :g1")


@pytest.mark.parametrize("text", ["", "   ", "# nothing", "PREFIX : <http://e/>"])
@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_an_empty_update_does_nothing(make, text):
    obj = make()
    assert obj.update(text) is None
    assert len(obj) == 0


@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_update_and_query_of_none_raise_type_error(make):
    obj = make()
    with pytest.raises(TypeError):
        obj.update(None)
    with pytest.raises(TypeError):
        obj.query(None)


@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_one_blank_node_label_in_two_operations_is_rejected(make):
    with pytest.raises(ValueError, match="more than one operation"):
        make().update("INSERT DATA { _:a <http://e/p> 1 } ; INSERT DATA { _:a <http://e/p> 3 }")
    # different labels, and one label repeated inside one operation, are fine
    g = make()
    g.update("INSERT DATA { _:a <http://e/p> 1 . _:a <http://e/q> 2 } ; INSERT DATA { _:b <http://e/p> 3 }")
    assert len(set(g.subjects())) == 2


@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
@pytest.mark.parametrize("text", ["DELETE WHERE { _:a <http://e/p> ?o }", "DELETE DATA { _:a <http://e/p> 1 }", "DELETE { _:a <http://e/p> ?o } WHERE { ?s <http://e/p> ?o }"])
def test_blank_nodes_in_a_delete_are_rejected(make, text):
    with pytest.raises(ValueError, match="blank node"):
        make().update(text)


_RACE = textwrap.dedent(
    """
    import concurrent.futures as cf, sys
    from starlayer.graph import StarLayerGraph
    from starlayer.sparql import srl

    def update(i):
        g = StarLayerGraph()
        g.update("DELETE { ?s <urn:p> ?o } INSERT { ?s <urn:q> ?o } WHERE { ?s <urn:p> ?o FILTER(?o > 0) OPTIONAL { ?s <urn:r> ?x } }")

    def rules(i):
        srl.parse_ruleset("PREFIX : <http://e/> RULE { ?s :q ?o } WHERE { ?s :p ?o }")

    fn = {"update": update, "srl": rules}[sys.argv[1]]
    with cf.ThreadPoolExecutor(16) as pool:
        for future in [pool.submit(fn, i) for i in range(48)]:
            future.result()
    """
)


@pytest.mark.parametrize("which", ["update", "srl"])
def test_the_first_parse_in_a_thread_pool_does_not_fail(which):
    for _ in range(3):  # the race is in a fresh process's first parses
        done = subprocess.run([sys.executable, "-c", _RACE, which], capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stderr[-800:]


@pytest.mark.parametrize("bad", [5, 1.5, b"ASK {}", ["ASK {}"], object()])
@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_update_and_query_of_a_non_string_raise_type_error_naming_the_type(make, bad):
    # Was AttributeError: object has no attribute algebra (issue #139).
    obj = make()
    with pytest.raises(TypeError, match=type(bad).__name__):
        obj.update(bad)
    with pytest.raises(TypeError, match=type(bad).__name__):
        obj.query(bad)


@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_a_prepared_query_is_still_accepted(make):
    from rdflib.plugins.sparql import prepareQuery
    assert make().query(prepareQuery("ASK { ?s ?p ?o }")).askAnswer is False
