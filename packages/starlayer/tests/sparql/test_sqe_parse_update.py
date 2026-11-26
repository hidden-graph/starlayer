"""``sparql_to_tree`` reads SPARQL Update with the owned parser (the switch branch and the Update branch, joined)."""

from __future__ import annotations

import pytest
from starlayer.errors import FormatError
from starlayer.sparql import sparql_to_tree, tree_to_sparql

SQE = "https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#"

UPDATES = [
    "PREFIX ex: <http://e/> INSERT DATA { ex:a ex:p 1 }",
    "DELETE { ?s ?p ?o } INSERT { ?s ?p 2 } WHERE { ?s ?p ?o }",
    "WITH <http://e/g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "DELETE WHERE { ?s ?p ?o }",
    "DROP SILENT GRAPH <http://e/g> ; CLEAR ALL",
    "LOAD SILENT <http://e/data.ttl> INTO GRAPH <http://e/g>",
    "COPY DEFAULT TO <http://e/g>",
]


@pytest.mark.parametrize("text", UPDATES)
def test_update_text_round_trips_through_the_tree(text: str) -> None:
    graph, root = sparql_to_tree(text)
    rendered = tree_to_sparql(graph, root)
    graph2, root2 = sparql_to_tree(rendered)
    assert tree_to_sparql(graph2, root2) == rendered  # text fixpoint


def test_the_root_of_an_update_tree_is_an_update_request() -> None:
    from tests.support.terms import RDF, NamedNode

    graph, root = sparql_to_tree("CLEAR ALL")
    assert (root, RDF.type, NamedNode(SQE + "UpdateRequest")) in graph


def test_a_query_still_gives_a_query_tree() -> None:
    from tests.support.terms import RDF, NamedNode

    graph, root = sparql_to_tree("SELECT * { ?s ?p ?o }")
    assert (root, RDF.type, NamedNode(SQE + "UpdateRequest")) not in graph
    assert "SELECT" in tree_to_sparql(graph, root)


def test_static_update_rules_still_apply() -> None:
    with pytest.raises(FormatError, match="variables are not allowed"):
        sparql_to_tree("INSERT DATA { ?x <http://e/p> 1 }")


@pytest.mark.parametrize(
    "text,written",
    [
        ("# Empty\n", ""),
        ("BASE <http://example/>\n# Otherwise empty\n", "BASE <http://example/>"),
        ("PREFIX : <http://example/>\n# Otherwise empty\n", "PREFIX : <http://example/>"),
        ("PREFIX : <http://e/> BASE <http://f/>", "PREFIX : <http://e/>\nBASE <http://f/>"),
        ("", ""),
    ],
)
def test_a_prologue_only_text_is_an_empty_update_request(text: str, written: str) -> None:
    from starlayer.sparql import validate_sparql_tree
    from tests.support.terms import RDF, NamedNode

    graph, root = sparql_to_tree(text)
    assert (root, RDF.type, NamedNode(SQE + "UpdateRequest")) in graph
    assert validate_sparql_tree(graph).conforms
    assert tree_to_sparql(graph, root) == written
    assert tree_to_sparql(*sparql_to_tree(written)) == written  # and it loads again as the same empty request


@pytest.mark.parametrize("text", ["foo bar", "PREFIX : <http://e/> foo", "PREFIX : <http://e/> ;"])
def test_text_that_is_not_a_prologue_still_raises_a_sparql_format_error(text: str) -> None:
    with pytest.raises(FormatError) as error:
        sparql_to_tree(text)
    assert error.value.kind == "sparql"
