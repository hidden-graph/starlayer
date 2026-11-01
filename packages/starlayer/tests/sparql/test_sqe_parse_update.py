"""``sqe_parse_to_tree`` reads SPARQL Update with the owned parser (the switch branch and the Update branch, joined)."""

from __future__ import annotations

import pytest
from starlayer.sparql.parse_sparql import SparqlSyntaxError
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text

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
    graph, root = sqe_parse_to_tree(text)
    rendered = sqe_tree_to_text(graph, root)
    graph2, root2 = sqe_parse_to_tree(rendered)
    assert sqe_tree_to_text(graph2, root2) == rendered  # text fixpoint


def test_the_root_of_an_update_tree_is_an_update_request() -> None:
    from rdflib import RDF, URIRef

    graph, root = sqe_parse_to_tree("CLEAR ALL")
    assert (root, RDF.type, URIRef(SQE + "UpdateRequest")) in graph


def test_a_query_still_gives_a_query_tree() -> None:
    from rdflib import RDF, URIRef

    graph, root = sqe_parse_to_tree("SELECT * { ?s ?p ?o }")
    assert (root, RDF.type, URIRef(SQE + "UpdateRequest")) not in graph
    assert "SELECT" in sqe_tree_to_text(graph, root)


def test_static_update_rules_still_apply() -> None:
    with pytest.raises(SparqlSyntaxError, match="variables are not allowed"):
        sqe_parse_to_tree("INSERT DATA { ?x <http://e/p> 1 }")
