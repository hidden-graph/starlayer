"""The syntax-tree function names (maintainer decision 2026-11-26).

SPARQL, SPARQL Update and SRL share ``sparql_to_tree`` / ``tree_to_sparql`` / ``validate_sparql_tree`` (``starlayer.sparql``); Manchester has
``manchester_to_tree`` / ``tree_to_manchester`` / ``tree_to_owl`` / ``validate_manchester_tree``. The old per-language names are removed
with no alias, so none may appear in the package, the tests or the tools.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph
from starlayer.sparql import sparql_to_tree, tree_to_sparql, validate_sparql_tree
from starlayer.sparql import srl as srl_module
from starlayer.starontology import manchester
from starlayer.starontology.manchester import (
    manchester_to_tree,
    tree_to_manchester,
    tree_to_owl,
    validate_manchester_tree,
)

ROOT = Path(__file__).resolve().parents[2]  # packages/starlayer
TOOLS = ROOT.parents[1] / "tools"

REMOVED = (
    "sqe_parse_to_tree",
    "sqe_tree_to_text",
    "sqe_validate",
    "srl_parse_to_tree",
    "srl_tree_to_text",
    "srl_validate",
    "manchester_parse_to_tree",
    "manchester_tree_to_text",
    "manchester_tree_to_owl",
    "manchester_validate",
    "sparql_update_to_tree",
)
_PATTERN = re.compile(r"\b(" + "|".join(REMOVED) + r")\b")


def _files():
    for base in (ROOT / "starlayer", ROOT / "tests", TOOLS):
        for path in base.rglob("*"):
            if path.suffix in {".py", ".md", ".ttl"} and "__pycache__" not in path.parts and path != Path(__file__).resolve():
                yield path


def test_no_removed_function_name_is_left_in_the_package_the_tests_or_the_tools():
    found = {str(path.relative_to(ROOT.parents[1])): sorted(set(_PATTERN.findall(path.read_text()))) for path in _files()}
    found = {path: names for path, names in found.items() if names}
    assert not found, found


def test_the_removed_names_are_not_attributes_of_the_modules_that_had_them():
    from starlayer.sparql import parse_sparql, sqe

    for module in (sqe, srl_module, manchester, parse_sparql):
        for name in REMOVED:
            assert not hasattr(module, name), (module.__name__, name)


# ---------------------------------------------------------------------------------------------------------------------
# SPARQL, Update and SRL

SELECT = "SELECT ?s WHERE { ?s ?p ?o }"
ASK = "ASK { ?s ?p ?o }"
CONSTRUCT = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
UPDATE = "INSERT DATA { <http://e/a> <http://e/b> <http://e/c> }"
RULES = "PREFIX : <http://e/>\nRULE { ?x :anc ?y } WHERE { ?x :parent ?y }\nRULE { ?x :anc ?z } WHERE { ?x :anc ?y . ?y :parent ?z }"
DATA = "PREFIX : <http://e/>\nDATA { :a :parent :b }"
SQE_TYPE = "https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#"
SRL_TYPE = "https://github.com/hidden-graph/starlayer/ns/sparql/srl#"


def _types(graph, root):
    from pyoxigraph import NamedNode

    return {str(o.value) for o in graph.objects(root, NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"))}


@pytest.mark.parametrize(
    ("text", "type_iri"),
    [
        (SELECT, SQE_TYPE + "SelectQuery"),
        (ASK, SQE_TYPE + "AskQuery"),
        (CONSTRUCT, SQE_TYPE + "ConstructQuery"),
        (UPDATE, SQE_TYPE + "UpdateRequest"),
        ("", SQE_TYPE + "UpdateRequest"),
        ("PREFIX : <http://e/>\n# nothing else", SQE_TYPE + "UpdateRequest"),
        (RULES, SRL_TYPE + "RuleSet"),
        (DATA, SRL_TYPE + "RuleSet"),
    ],
)
def test_sparql_to_tree_finds_the_kind_and_the_tree_writes_back_and_validates(text, type_iri):
    graph, root = sparql_to_tree(text)
    assert isinstance(graph, StarLayerGraph)
    assert type_iri in _types(graph, root)
    assert validate_sparql_tree(graph).conforms
    written = tree_to_sparql(graph, root)
    again_graph, again_root = sparql_to_tree(written)
    assert tree_to_sparql(again_graph, again_root) == written
    assert tree_to_sparql(graph) == written  # the one root, left out


def test_text_that_is_neither_is_a_sparql_format_error_with_a_position():
    with pytest.raises(FormatError) as caught:
        sparql_to_tree("hello world")
    assert caught.value.kind == "sparql"
    assert caught.value.line == 1


def test_a_broken_rule_set_reports_the_srl_grammar_and_a_broken_update_the_update_grammar():
    with pytest.raises(FormatError) as rule:
        sparql_to_tree("RULE { ?x <http://e/p> ?y } WHERE { ?x <http://e/q> ?y")
    assert rule.value.kind == "srl"
    with pytest.raises(FormatError) as update:
        sparql_to_tree("INSERT DATA {")
    assert update.value.kind == "sparql"
    assert update.value.col > 1


def test_two_queries_in_one_graph_are_told_apart_by_their_roots():
    from pyoxigraph import NamedNode

    graph = StarLayerGraph()
    first, second = NamedNode("http://e/q1"), NamedNode("http://e/q2")
    sparql_to_tree(SELECT, graph, first)
    sparql_to_tree(ASK, graph, second)
    assert tree_to_sparql(graph, first).startswith("SELECT")
    assert tree_to_sparql(graph, second).startswith("ASK")
    with pytest.raises(ValueError, match="pass root="):
        tree_to_sparql(graph)
    with pytest.raises(ValueError, match="no root"):
        tree_to_sparql(StarLayerGraph())


def test_a_rule_set_and_a_query_share_a_graph_and_take_a_root():
    from pyoxigraph import NamedNode

    graph = StarLayerGraph()
    query_root, rules_root = NamedNode("http://e/q"), NamedNode("http://e/r")
    sparql_to_tree(SELECT, graph, query_root)
    sparql_to_tree(RULES, graph, rules_root)
    assert "RULE" in tree_to_sparql(graph, rules_root)
    assert tree_to_sparql(graph, query_root).startswith("SELECT")
    assert validate_sparql_tree(graph).conforms  # a mixed graph is checked as both and gives one report


def test_the_base_resolves_relative_iris_in_every_kind_of_text():
    for text in (SELECT.replace("?p", "<p>"), "INSERT DATA { <a> <b> <c> }", "RULE { ?x <p> ?y } WHERE { ?x <q> ?y }"):
        graph, root = sparql_to_tree(text, base="http://e/")
        assert "http://e/" in tree_to_sparql(graph, root)


def test_an_unbound_projected_variable_is_reported_by_the_sqe_shapes():
    graph, _ = sparql_to_tree("SELECT ?x WHERE { ?s ?p ?o }")
    report = validate_sparql_tree(graph)
    assert not report.conforms
    assert "never bound" in report.report_text


def test_an_unbound_head_variable_is_reported_by_the_srl_shapes():
    graph, _ = sparql_to_tree("RULE { ?x <http://e/p> ?z } WHERE { ?x <http://e/q> ?y }")
    assert not validate_sparql_tree(graph).conforms


def test_a_mixed_graph_with_a_problem_in_each_kind_reports_both_in_one_report():
    graph = StarLayerGraph()
    sparql_to_tree("SELECT ?x WHERE { ?s ?p ?o }", graph)
    sparql_to_tree("RULE { ?x <http://e/p> ?z } WHERE { ?x <http://e/q> ?y }", graph)
    report = validate_sparql_tree(graph)
    assert not report.conforms
    assert "SelectQueryShape" in report.report_text
    assert "UnboundHeadVariableShape" in report.report_text


def test_a_rule_set_that_cannot_be_ordered_is_a_violation():
    graph, _ = sparql_to_tree("RULE { ?x <http://e/p> ?y } WHERE { ?x <http://e/q> ?y NOT { ?x <http://e/p> ?y } }")
    report = validate_sparql_tree(graph)
    assert not report.conforms


def test_the_tree_graph_and_root_keywords_and_the_old_graph_keyword():
    target = StarLayerGraph()
    graph, root = sparql_to_tree(SELECT, tree_graph=target)
    assert graph is target
    assert tree_to_sparql(tree_graph=graph, root=root).startswith("SELECT")
    with pytest.raises(TypeError):
        sparql_to_tree(SELECT, graph=StarLayerGraph())  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        sparql_to_tree(SELECT, root="not a node")


# ---------------------------------------------------------------------------------------------------------------------
# Manchester (the example of guide 06.05)

MANCHESTER = """Prefix: : <http://example.org/vehicles#>

Class: Vehicle
Class: Car
    SubClassOf: Vehicle

ObjectProperty: hasWheelCount
"""


def test_manchester_text_to_tree_back_to_text_to_owl_and_validated():
    tree = manchester_to_tree(MANCHESTER, tree_graph=StarLayerGraph())
    assert validate_manchester_tree(tree).conforms
    text = tree_to_manchester(tree)
    assert "SubClassOf: <http://example.org/vehicles#Vehicle>" in text
    again = manchester_to_tree(text)
    assert tree_to_manchester(again) == text
    owl = tree_to_owl(tree)
    assert len(owl) > 0
    assert manchester_to_tree(MANCHESTER, base="http://example.org/") is not tree


def test_a_second_document_in_one_graph_and_a_graph_without_one_are_refused():
    tree = manchester_to_tree(MANCHESTER)
    with pytest.raises(ValueError):
        manchester_to_tree(MANCHESTER, tree_graph=tree)
    with pytest.raises(ValueError):
        tree_to_manchester(StarLayerGraph())


def test_a_manchester_tree_that_breaks_the_shapes_is_reported():
    from pyoxigraph import BlankNode

    tree = manchester_to_tree(MANCHESTER)
    frame = next(tree.subjects(manchester.MANCH.frames, None))
    assert validate_manchester_tree(tree).conforms
    tree.add((frame, manchester.MANCH.frames, BlankNode()))  # a child with no type and no ordinal
    assert not validate_manchester_tree(tree).conforms
