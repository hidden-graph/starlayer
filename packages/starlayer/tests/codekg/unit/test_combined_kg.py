"""``starlayer-kg.trig``: the whole KG in one TriG file that an agent loads with StarLayerDataset and queries.

The comparison tests are the point: queries read out of the graph and run with ``kg.query`` must give the answers
StarLayer's own query tool gives. Only StarLayer's classes are used here, never rdflib directly.
"""

from __future__ import annotations

import build_kg  # scripts/ is on the test path (pyproject: pythonpath)
import pytest
from starlayer import StarLayerDataset
from starlayer.codekg import (
    BUILD_GRAPH_IRI,
    CODEKG_NS,
    CURATED_GRAPH_IRI,
    DERIVED_GRAPH_IRI,
    KG_TRIG_PATH,
    ONTOLOGY_GRAPH_IRI,
    queries,
)
from starlayer.graph import RDF, BNode, Literal, URIRef

# ---------------------------------------------------------------------------
# the comparison helper (no KG needed)


def _dataset(*graphs: tuple[str, list[tuple]]) -> StarLayerDataset:
    ds = StarLayerDataset()
    for name, triples in graphs:
        g = ds.graph(URIRef(name))
        for t in triples:
            g.add(t)
    return ds


A, B = URIRef("http://e/a"), URIRef("http://e/b")


def test_the_comparison_notices_a_missing_extra_or_changed_graph():
    base = _dataset(("http://g/1", [(A, A, A)]), ("http://g/2", [(A, A, B)]))
    assert build_kg.same_dataset(base, _dataset(("http://g/1", [(A, A, A)]), ("http://g/2", [(A, A, B)]))) == []
    assert any("missing" in p for p in build_kg.same_dataset(base, _dataset(("http://g/1", [(A, A, A)]))))
    assert any("only in" in p for p in build_kg.same_dataset(_dataset(("http://g/1", [(A, A, A)])), base))
    assert any("differs" in p for p in build_kg.same_dataset(base, _dataset(("http://g/1", [(A, A, A)]), ("http://g/2", [(A, A, A)]))))


def test_the_comparison_treats_renamed_blank_nodes_as_the_same():
    one = _dataset(("http://g/1", [(A, A, BNode("x")), (BNode("x"), A, Literal("v"))]))
    two = _dataset(("http://g/1", [(A, A, BNode("y")), (BNode("y"), A, Literal("v"))]))
    assert build_kg.same_dataset(one, two) == []


# ---------------------------------------------------------------------------
# the committed file


@pytest.fixture(scope="module")
def kg() -> StarLayerDataset:
    """Loaded the way an agent would: into memory, with the graphs seen as one."""
    dataset = StarLayerDataset(default_union=True)
    dataset.parse(str(KG_TRIG_PATH), format="trig12")
    return dataset


@pytest.mark.deferred
def test_the_file_holds_every_layer(kg):
    graphs = {g.identifier for g in kg.graphs() if len(g)}
    assert {ONTOLOGY_GRAPH_IRI, CURATED_GRAPH_IRI, DERIVED_GRAPH_IRI, BUILD_GRAPH_IRI} <= graphs
    assert len(graphs) > 300, "the module graphs are there too"
    counts = {cls: len(set(kg.subjects(RDF.type, CODEKG_NS[cls]))) for cls in ("Function", "Class", "NamedQuery", "Capability", "NotebookExample", "UpstreamIssue", "KGBuild")}
    assert counts["Function"] > 2000 and counts["Class"] > 500
    assert counts["NamedQuery"] == len(queries.list_queries()) >= 24
    assert counts["Capability"] >= 49 and counts["NotebookExample"] >= 30 and counts["UpstreamIssue"] >= 25 and counts["KGBuild"] == 1


@pytest.mark.deferred
def test_an_agent_can_read_a_query_from_the_graph_and_run_it(kg):
    """The documented flow: find the query's text in the graph, bind its parameter, run it."""
    find = f"SELECT ?t WHERE {{ ?q a <{CODEKG_NS}NamedQuery> ; <{CODEKG_NS}queryText> ?t . FILTER(STRENDS(STR(?q), '#find-symbol')) }}"
    text = next(iter(kg.query(find)))[0]
    rows = list(kg.query(str(text), initBindings={"text": Literal("tt_hash")}))
    assert any("lookup_tt_hash" in str(row[0]) for row in rows)


@pytest.mark.deferred
def test_every_query_in_the_graph_gives_the_answer_the_query_tool_gives(kg):
    texts = {str(q).rsplit("#", 1)[-1]: str(t) for q, t in kg.subject_objects(CODEKG_NS.queryText)}
    assert set(texts) == {q.name for q in queries.list_queries()}
    for described in queries.list_queries():
        required = {p.name: p.example for p in described.parameters if p.required}
        optional = {p.name: p.example for p in described.parameters if not p.required}
        for given in ([required] + ([{**required, **optional}] if optional else [])):
            from_graph = list(kg.query(texts[described.name], initBindings={k: Literal(v) for k, v in given.items()}))
            from_tool = queries.run_query(described.name, limit=500, **given)
            assert len(from_graph) == from_tool.total, f"{described.name} with {sorted(given)}: {len(from_graph)} rows from the graph's text, {from_tool.total} from the tool"
            assert len(from_graph) > 0, f"{described.name} returned nothing for its own examples"
