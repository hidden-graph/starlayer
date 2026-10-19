"""The code-KG query library: structure, validity, and results against the committed code knowledge graph.

The first group needs only the stored library (``curated/query-library.ttl``) and is fast; it runs with the
ordinary tests. The tests marked ``codekg_queries`` re-parse every query and run them against ``codekg.trig``
(loading that graph takes about 15 seconds): opt in with ``pytest --codekg-queries``. Every query is also
validated against the sqe shapes when ``scripts/build_query_library.py`` builds the library.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from starlayer.codekg import CODEKG_NS, queries

CODEKG_DIR = Path(queries.__file__).parent
SHAPES_TTL = CODEKG_DIR / "query-library-shapes.ttl"
LIBRARY_TTL = CODEKG_DIR / "curated" / "query-library.ttl"
QUERY_NAMES = sorted(q.name for q in queries.list_queries())


# ---------------------------------------------------------------------------
# the stored library (no code KG needed)


def test_the_library_is_valid():
    """The stored library is the source of the queries: its shapes, and every sqe tree, must hold."""
    assert queries.validate_library() == []
    assert len(QUERY_NAMES) >= 20


def test_validate_library_notices_a_damaged_tree():
    """A tree the sqe shapes reject must be reported, not passed over."""
    from starlayer.sparql.sqe import vocab

    library = Graph()
    for triple in queries._library():
        library.add(triple)
    root = library.value(next(n for n in library.subjects(RDF.type, CODEKG_NS.NamedQuery) if str(n).endswith("#callers-of")), CODEKG_NS.queryRoot)
    library.remove((root, RDF.type, None))
    library.add((root, RDF.type, vocab.SQE.Query))
    original = queries._library
    queries._library = lambda: library
    try:
        problems = queries.validate_library()
    finally:
        queries._library = original
    assert any("callers-of" in p for p in problems)


def test_the_stored_library_is_the_only_source():
    """No build step writes the library, so no generator header may claim otherwise."""
    assert "Do not edit" not in LIBRARY_TTL.read_text(encoding="utf-8")
    assert not (CODEKG_DIR / "query-library").exists()


@pytest.mark.codekg_queries
@pytest.mark.parametrize("name", QUERY_NAMES)
def test_query_text_round_trips_and_follows_the_parameter_rules(name):
    from starlayer.sparql.sqe import sqe_parse_to_tree

    text = queries.query_text(name)
    sqe_parse_to_tree(text)  # the rendered text parses and validates again

    described = queries.get_query(name)
    select = re.search(r"SELECT(.*?)WHERE", text, re.S).group(1)
    for param in described.parameters:
        assert f"?{param.name}" in text, f"{name}: parameter {param.name} is not used in the query"
        assert f"?{param.name}" not in select, f"{name}: parameter {param.name} must not be in the SELECT list"
        if not param.required:
            assert f"VALUES ?{param.name} {{ UNDEF }}" in text, f"{name}: optional parameter {param.name} is not declared"


def test_every_query_has_a_known_topic_and_topics_resolve():
    topic_ids = set(queries.topics())
    assert {q.topic for q in queries.list_queries()} <= topic_ids
    for topic in topic_ids:
        queries.queries_for_topic(topic)


def test_queries_can_be_found_by_topic_id_label_and_iri():
    by_id = {q.name for q in queries.queries_for_topic("call-graph")}
    assert by_id and by_id == {q.name for q in queries.queries_for_topic("Relationships and the call graph")}
    library = queries._library()
    iri = next(t for t in library.subjects(RDF.type, CODEKG_NS.Topic) if str(t).endswith("topic-call-graph"))
    assert {q.name for q in queries.queries_for_topic(str(iri))} == by_id


def test_unknown_names_suggest_a_close_match():
    with pytest.raises(KeyError, match="callers-of"):
        queries.get_query("caller-of")
    with pytest.raises(KeyError):
        queries.list_queries(topic="no-such-topic")


def test_run_query_checks_its_arguments_before_touching_the_graph():
    with pytest.raises(ValueError, match="missing required parameter"):
        queries.run_query("callers-of")
    with pytest.raises(ValueError, match="unknown parameter"):
        queries.run_query("callers-of", symbol="x", nonsense=1)


def test_competency_questions_carry_their_status():
    questions = queries.competency_questions()
    assert len(questions) >= 20
    assert {q.status for q in questions} <= {"answerable", "roadmap", "curated", "out-of-scope"}
    answered = [q for q in questions if q.answered_by]
    assert answered and all(q.status == "answerable" for q in answered)
    assert queries.competency_questions(unanswered=True)
    with pytest.raises(ValueError):
        queries.competency_questions(status="bogus")


def test_usage_is_a_ready_to_copy_call():
    assert queries.get_query("callers-of").usage().startswith("run_query('callers-of', symbol=")


# ---------------------------------------------------------------------------
# against the committed code knowledge graph (loaded once)


@pytest.fixture(scope="module")
def kg():
    return queries._kg()


# a query whose honest answer on this graph is no rows goes here, with the reason
MAY_BE_EMPTY: dict[str, str] = {}


@pytest.mark.codekg_queries
@pytest.mark.parametrize("name", QUERY_NAMES)
def test_query_runs_with_its_examples_and_is_bounded(name, kg):
    described = queries.get_query(name)
    params = {p.name: p.example for p in described.parameters if p.required}
    result = queries.run_query(name, limit=5, **params)
    assert result.columns and len(result.rows) <= 5
    if name not in MAY_BE_EMPTY:
        assert result.total > 0, f"{name} returns nothing for its own example {params}"
    optional = {p.name: p.example for p in described.parameters if not p.required}
    if optional:
        narrowed = queries.run_query(name, limit=5, **params, **optional)
        assert 0 < narrowed.total <= queries.run_query(name, limit=500, **params).total


@pytest.mark.codekg_queries
def test_paging_and_the_footer(kg):
    first = queries.run_query("find-symbol", text="a", limit=3)
    second = queries.run_query("find-symbol", text="a", limit=3, offset=3)
    assert first.truncated and len(first.rows) == 3
    assert first.rows != second.rows
    assert "offset=3" in str(first)
    assert "can lag the source" in str(first)
    with pytest.raises(ValueError, match="limit"):
        queries.run_query("find-symbol", text="a", limit=0)


@pytest.mark.codekg_queries
def test_rows_show_repository_relative_paths_not_machine_paths(kg):
    row = queries.run_query("symbol-info", symbol="starlayer.graph.model.encoding.tt_hash").as_dicts()[0]
    assert row["kind"] == "function"
    assert row["file"].startswith("packages/starlayer/starlayer/") and not row["file"].startswith("/")


@pytest.mark.codekg_queries
def test_a_known_call_edge_is_found(kg):
    callers = queries.run_query("callers-of", symbol="starlayer.graph.model.encoding.tt_hash", limit=500).as_dicts()
    assert any("starlayer_graph" in r["caller"] for r in callers)


@pytest.mark.codekg_queries
def test_free_form_sparql_is_bounded_and_refuses_what_could_return_everything(kg):
    result = queries.run_sparql("SELECT ?s WHERE { ?s a slkg:Function }", limit=4)
    assert len(result.rows) == 4 and result.total > 4
    assert any("no LIMIT" in w for w in result.warnings)
    assert queries.run_sparql("ASK { ?s a slkg:Function }").rows == [("true",)]
    with pytest.raises(ValueError, match="SELECT and ASK"):
        queries.run_sparql("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    with pytest.raises(ValueError, match="SELECT and ASK"):
        queries.run_sparql("DESCRIBE <http://example/x>")
    assert any("SELECT *" in w for w in queries.run_sparql("SELECT * WHERE { ?s a slkg:Class }", limit=2).warnings)


@pytest.mark.codekg_queries
def test_command_line(kg, capsys):
    assert queries.main(["list", "--topic", "testing"]) == 0
    assert "tests-of" in capsys.readouterr().out
    assert queries.main(["run", "callers-of", "symbol=starlayer.graph.model.encoding.tt_hash", "--limit", "2"]) == 0
    assert "rows 1-2 of" in capsys.readouterr().out
    assert queries.main(["run", "no-such-query"]) == 2


def _shapes_conform(library: Graph) -> bool:
    import starlayer.shacl

    shapes = Graph().parse(SHAPES_TTL, format="turtle")
    return starlayer.shacl.validate(library, shacl_graph=shapes).conforms


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda g, q: g.remove((q, RDFS.label, None)),
        lambda g, q: g.remove((q, CODEKG_NS.aboutTopic, None)),
        lambda g, q: g.remove((q, CODEKG_NS.queryRoot, None)),
        lambda g, q: g.set((q, CODEKG_NS.queryRoot, Literal("not a tree"))),
        lambda g, q: g.set((q, CODEKG_NS.aboutTopic, URIRef("http://example/no-such-topic"))),
        lambda g, q: g.set((next(g.objects(q, CODEKG_NS.queryParameter)), CODEKG_NS.paramName, Literal("1 bad name"))),
        lambda g, q: g.remove((next(g.objects(q, CODEKG_NS.queryParameter)), CODEKG_NS.paramRequired, None)),
    ],
    ids=["no-label", "no-topic", "no-root", "root-not-a-tree", "unknown-topic", "bad-param-name", "no-required-flag"],
)
def test_the_shapes_notice_a_corrupted_library(corrupt):
    """The shapes check must actually reject a broken library, not only pass the good one."""
    library = Graph()
    for triple in queries._library():
        library.add(triple)
    node = next(n for n in library.subjects(RDF.type, CODEKG_NS.NamedQuery) if str(n).endswith("#callers-of"))
    assert _shapes_conform(library)
    corrupt(library, node)
    assert not _shapes_conform(library)


def test_a_table_keeps_identifiers_whole_and_cuts_long_prose():
    long_id = "starlayer." + ".".join(["segment"] * 12)
    prose = "word " * 40
    table = str(queries.QueryResult("t", ["symbol", "summary"], [(long_id, prose)], 1))
    assert long_id in table
    assert prose.strip() not in table and "…" in table


@pytest.mark.codekg_queries
def test_members_of_class_lists_named_tuple_and_dataclass_fields(kg):
    fields = [r["member"] for r in queries.run_query("members-of-class", symbol="starlayer.starontology.manchester.Clause").as_dicts()]
    assert fields == ["clause_kind", "items", "annotations"] or set(fields) == {"clause_kind", "items", "annotations"}


@pytest.mark.codekg_queries
def test_results_say_how_old_the_kg_is(kg):
    sentence = queries.kg_status()
    assert sentence.startswith("KG built 20") and "commit" in sentence
    assert sentence in str(queries.run_query("find-symbol", text="tt_hash", limit=2))
    assert queries.main(["status"]) == 0
