"""`FILTER(isTRIPLE(?x))` over a pattern that binds ?x is answered as a join with
the pattern `?x rdf:type rdf:PropositionForm` (see
starlayer.sparql.lower_rdf11._filter_is_triple_as_join). Each query must return
exactly what the general lowering (a string test on every row) returns."""

import pytest
from rdflib.namespace import RDF
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.model.encoding import TT_CLASS
from starlayer.sparql import lower_rdf11

DATA = """PREFIX ex: <http://ex/>
ex:alice ex:believes <<( ex:carol ex:age 30 )>> .
ex:josh  ex:believes <<( ex:carol ex:age 30 )>> .
ex:jane  ex:believes <<( ex:bob ex:said <<( ex:carol ex:age 30 )>> )>> .
ex:bob   ex:knows ex:carol .
ex:bob   ex:name "Bob" .
ex:r ex:about ex:alice .
"""

QUERIES = {
    "object": "SELECT ?s ?o WHERE { ?s ?p ?o . FILTER(isTRIPLE(?o)) }",
    "known predicate": "PREFIX ex: <http://ex/> SELECT ?s ?o WHERE { ?s ex:believes ?o . FILTER(isTRIPLE(?o)) }",
    "extra conjunct": "PREFIX ex: <http://ex/> SELECT ?s ?o WHERE { ?s ?p ?o . FILTER(isTRIPLE(?o) && ?s != ex:josh) }",
    "negated": "SELECT ?s ?o WHERE { ?s ?p ?o . FILTER(!isTRIPLE(?o)) }",
    "or": "PREFIX ex: <http://ex/> SELECT ?s ?o WHERE { ?s ?p ?o . FILTER(isTRIPLE(?o) || ?s = ex:bob) }",
    "unbound variable": "SELECT ?s WHERE { ?s ?p ?o . FILTER(isTRIPLE(?x)) }",
    "subject position": "SELECT ?s WHERE { ?s ?p ?o . FILTER(isTRIPLE(?s)) }",
    "computed by BIND": (
        "PREFIX ex: <http://ex/> SELECT ?t WHERE { BIND(<<( ex:a ex:b ex:c )>> AS ?t) FILTER(isTRIPLE(?t)) }"
    ),
    "two variables": (
        "PREFIX ex: <http://ex/> SELECT ?s ?o ?v WHERE { ?s ex:believes ?o . ?o ?q ?v . "
        "FILTER(isTRIPLE(?o) && isTRIPLE(?v)) }"
    ),
    "optional": (
        "PREFIX ex: <http://ex/> SELECT ?s ?o ?k WHERE { ?s ex:believes ?o . FILTER(isTRIPLE(?o)) "
        "OPTIONAL { ?s ex:knows ?k } }"
    ),
    "union": (
        "PREFIX ex: <http://ex/> SELECT ?s ?o WHERE { { ?s ex:believes ?o . FILTER(isTRIPLE(?o)) } "
        "UNION { ?s ex:knows ?o } }"
    ),
}


def _rows(result):
    return sorted(tuple(str(v) for v in row) for row in result)


@pytest.fixture
def graph():
    g = StarLayerGraph()
    g.parse(data=DATA, format="turtle12")
    return g


@pytest.fixture
def run(monkeypatch):
    """Run a query with the join rewrite on or off. A trailing comment keeps the
    two forms apart in the prepared-query cache."""

    def _run(target, query, rewrite):
        monkeypatch.setattr(lower_rdf11, "_REWRITE_IS_TRIPLE_FILTERS", rewrite)
        return _rows(target.query(query + ("\n# join" if rewrite else "\n# string test")))

    return _run


@pytest.mark.parametrize("name", list(QUERIES))
def test_the_join_gives_the_same_rows_as_the_string_test(graph, run, name):
    assert run(graph, QUERIES[name], True) == run(graph, QUERIES[name], False)


def test_the_basic_query_returns_the_triple_terms(graph, run):
    rows = run(graph, QUERIES["object"], True)
    assert len(rows) == 3
    assert {r[0] for r in rows} == {"http://ex/alice", "http://ex/josh", "http://ex/jane"}


def test_a_query_over_a_named_graph_gives_the_same_rows(run):
    ds = StarLayerDataset()
    ds.parse(
        data=("PREFIX ex: <http://ex/>\nGRAPH ex:g1 { ex:a ex:believes <<( ex:x ex:p ex:y )>> . ex:a ex:n 1 }\n"
              "GRAPH ex:g2 { ex:b ex:believes <<( ex:x ex:p ex:z )>> }"),
        format="trig12",
    )
    query = "PREFIX ex: <http://ex/> SELECT ?g ?s ?o WHERE { GRAPH ?g { ?s ?p ?o . FILTER(isTRIPLE(?o)) } }"
    on, off = run(ds, query, True), run(ds, query, False)
    assert on == off and len(on) == 2


def test_the_rewrite_is_applied_only_where_it_is_exact(monkeypatch):
    from starlayer.sparql.parse12 import prepare_query_12

    def lowered_has_type_pattern(query):
        lowered = lower_rdf11.lower_algebra_to_rdf11(prepare_query_12(query).algebra)
        return (TT_CLASS in repr(lowered)) and (str(RDF.type) in repr(lowered))

    monkeypatch.setattr(lower_rdf11, "_REWRITE_IS_TRIPLE_FILTERS", True)
    assert lowered_has_type_pattern(QUERIES["object"])
    assert lowered_has_type_pattern(QUERIES["extra conjunct"])
    assert not lowered_has_type_pattern(QUERIES["negated"])
    assert not lowered_has_type_pattern(QUERIES["or"])
    assert not lowered_has_type_pattern(QUERIES["computed by BIND"])
    assert not lowered_has_type_pattern(QUERIES["unbound variable"])
    monkeypatch.setattr(lower_rdf11, "_REWRITE_IS_TRIPLE_FILTERS", False)
    assert not lowered_has_type_pattern(QUERIES["object"])
