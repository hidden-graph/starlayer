"""SQE text rendering fixes from the second hunt (GitHub issue #81)."""

import warnings

import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.sparql import sqe

warnings.simplefilter("ignore")


def _text(query):
    graph, root = sqe.sqe_parse_to_tree(query)
    return sqe.sqe_tree_to_text(graph, root)


@pytest.mark.parametrize(
    ("query", "kept"),
    [
        ("PREFIX : <http://e/> SELECT ?o WHERE { :a <http://e/p#frag> ?o }", "<http://e/p#frag>"),
        ("PREFIX : <http://e/> SELECT ?o WHERE { <http://e/a/b> :p ?o }", "<http://e/a/b>"),
        ("PREFIX : <http://e/> SELECT ?o WHERE { :a :p ?o }", ":a :p ?o"),
        ("PREFIX : <http://e/> SELECT ?o WHERE { :a.b :p ?o }", ":a.b"),
    ],
)
def test_iri_that_is_not_a_valid_local_name_is_written_in_full(query, kept):
    text = _text(query)
    assert kept in text
    Graph().query(text)  # the rendered text parses


def test_rendered_iri_means_the_same_query():
    data = Graph()
    data.add((URIRef("http://e/a"), URIRef("http://e/p#frag"), Literal("x")))
    text = _text("PREFIX : <http://e/> SELECT ?o WHERE { :a <http://e/p#frag> ?o }")
    assert [str(r[0]) for r in data.query(text)] == ["x"]


def test_base_direction_string_in_a_triple_pattern_keeps_its_syntax():
    assert '"x"@en--ltr' in _text('SELECT ?s WHERE { ?s ?p "x"@en--ltr }')


def test_tab_in_a_string_literal_is_escaped_and_means_the_same():
    text = _text('SELECT * WHERE { ?s <http://e/v> "a\\tb" }')
    assert "\\t" in text
    data = Graph()
    data.add((URIRef("http://e/s"), URIRef("http://e/v"), Literal("a\tb")))
    assert len(list(data.query(text))) == 1


@pytest.mark.parametrize(
    "query",
    ["SELECT * FROM <urn:a> WHERE { ?s ?p ?o }", "SELECT * FROM NAMED <urn:b> WHERE { ?s ?p ?o }"],
)
def test_dataset_clauses_are_refused_not_dropped(query):
    with pytest.raises(NotImplementedError, match="FROM"):
        sqe.sqe_parse_to_tree(query)


@pytest.mark.parametrize(
    "path",
    ["(<urn:q>*)?", "(<urn:q>+)*", "(<urn:q>?)+", "(^<urn:q>)*", "^(<urn:q>*)", "(<urn:q>/<urn:r>)*",
     "((<urn:q>|<urn:r>)*)+", "^(^<urn:q>)", "<urn:q>/(<urn:r>*)?", "!(<urn:q>|^<urn:r>)*"],
)
def test_nested_path_modifiers_round_trip_with_the_same_meaning(path):
    """Issue #77: `p*?` and friends were written unparenthesised."""
    query = f"SELECT * WHERE {{ ?s {path} ?o }}"
    text = _text(query)
    data = Graph()
    q, r = URIRef("urn:q"), URIRef("urn:r")
    for a, p, b in [("a", q, "b"), ("b", q, "c"), ("c", r, "a"), ("b", r, "d")]:
        data.add((URIRef(f"urn:{a}"), p, URIRef(f"urn:{b}")))
    expected = sorted(map(tuple, data.query(query)))
    assert sorted(map(tuple, data.query(text))) == expected
