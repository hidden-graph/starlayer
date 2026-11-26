"""SPARQL errors are classified by cause (step A, stage 2): text that is not SPARQL is a ``FormatError`` of kind ``"sparql"`` from the
parser, from the sqe: encoder, from a ``VERSION`` check and from Oxigraph; a query nested deeper than Python's stack is an
``ExecutionError`` of kind ``"nesting"``; the engine failing to evaluate is an ``ExecutionError`` of kind ``"query"``."""

from __future__ import annotations

import random
import string

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError, FormatError, StarLayerError
from starlayer.graph import StarLayerGraph
from starlayer.sparql import check, sparql_to_tree, tree_to_sparql, validate_sparql_tree
from starlayer.sparql.parse_sparql import parse_sparql, parse_sparql_update

DEEP = "SELECT * WHERE " + "{ " * 20000 + "?s ?p ?o" + " }" * 20000
DEEP_UPDATE = "DELETE { ?s ?p ?o } WHERE " + "{ " * 20000 + "?s ?p ?o" + " }" * 20000


def _random_texts(n: int = 40) -> list[str]:
    rng = random.Random(20261125)  # fixed seed: the same texts every run
    alphabet = string.ascii_letters + string.digits + " {}()<>?$\"'.;,:#"
    return ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60))) for _ in range(n)]


@pytest.mark.parametrize("text", _random_texts())
def test_random_text_is_a_sparql_format_error_from_the_parser(text):
    with pytest.raises(FormatError) as caught:
        parse_sparql(text)
    error = caught.value
    assert error.kind == "sparql" and isinstance(error, StarLayerError) and not isinstance(error, (ValueError, SyntaxError))
    assert error.line is not None and error.col is not None and error.pos is not None and error.why


def test_a_parse_error_carries_its_position_and_reason():
    text = "SELECT *\nWHERE { ?s ?p }"
    with pytest.raises(FormatError) as caught:
        parse_sparql(text)
    error = caught.value
    assert error.pos == text.index("}") and (error.line, error.col) == (2, text.index("}") - text.index("\n"))
    assert str(error) == f"SPARQL syntax error at line {error.line}, column {error.col}: {error.why}"


def test_an_update_parse_error_is_a_sparql_format_error():
    with pytest.raises(FormatError) as caught:
        parse_sparql_update("INSERT DATA { ?x <urn:p> 1 }")
    assert caught.value.kind == "sparql"


@pytest.mark.parametrize(("parse", "text"), [(parse_sparql, DEEP), (parse_sparql_update, DEEP_UPDATE)])
def test_deep_nesting_is_an_execution_error_of_kind_nesting(parse, text):
    with pytest.raises(ExecutionError) as caught:
        parse(text)
    assert caught.value.kind == "nesting" and caught.value.context and "nested too deeply" in str(caught.value)
    assert not isinstance(caught.value, FormatError)


def test_sparql_to_tree_reports_both_causes_by_class():
    with pytest.raises(FormatError) as syntax:
        sparql_to_tree("SELECT WHERE {")
    assert syntax.value.kind == "sparql"
    with pytest.raises(ExecutionError) as deep:
        sparql_to_tree(DEEP)
    assert deep.value.kind == "nesting"


def test_a_query_that_breaks_the_sqe_shapes_loads_and_validate_sparql_tree_reports_it():
    text = "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o }"  # ?z is projected and never bound
    tree, root = sparql_to_tree(text)  # no error: any text the parser understands gives a tree
    outcome = validate_sparql_tree(tree)
    assert not outcome.conforms and "variable z " in outcome.report_text
    rendered = tree_to_sparql(tree, root)  # the tree still renders back
    assert "?z" in rendered and "knows" in rendered
    assert sparql_to_tree(rendered)[0] is not None


# --- the Oxigraph boundary ---------------------------------------------------------------------------------------------

def test_an_oxigraph_syntax_rejection_through_query_is_a_format_error():
    # the text must get past the wrapper's own checks, so the failure is Oxigraph's
    with pytest.raises(FormatError) as caught:
        StarLayerGraph().query("SELEC * WHERE { ?s ?p ?o }")
    error = caught.value
    assert error.kind == "sparql" and error.context == "Oxigraph query" and "error at" in str(error)
    assert isinstance(error.__cause__, SyntaxError)
    assert (error.line, error.col, error.pos) == (None, None, None)  # never parsed out of the engine's message


def test_an_oxigraph_syntax_rejection_through_update_is_a_format_error():
    from starlayer.graph.execution import run

    with pytest.raises(FormatError) as caught:
        run.update(ox.Store(), "INSERT DATA { x }", prefixes=None)
    assert caught.value.kind == "sparql" and caught.value.context == "Oxigraph update"
    with pytest.raises(FormatError) as through_the_graph:
        StarLayerGraph().update("INSERT DATA { x }")
    assert through_the_graph.value.kind == "sparql"


def test_an_oxigraph_runtime_failure_is_an_execution_error_of_kind_query():
    with pytest.raises(ExecutionError) as caught:
        StarLayerGraph().query("SELECT ?x WHERE { ?x <urn:p> ?y } ORDER BY <urn:nope>(?y)")
    error = caught.value
    assert error.kind == "query" and error.context == "Oxigraph query"
    assert "The custom function <urn:nope> is not supported" in str(error)
    assert isinstance(error.__cause__, RuntimeError)


def test_an_oxigraph_runtime_failure_through_update_is_an_execution_error_of_kind_query():
    with pytest.raises(ExecutionError) as caught:
        StarLayerGraph().update("INSERT { ?s <urn:q> ?o } WHERE { ?s <urn:p> ?o FILTER(<urn:nope>(?o)) }")
    assert caught.value.kind == "query" and caught.value.context == "Oxigraph update"


def test_the_projection_fallback_for_init_bindings_still_works():
    graph = StarLayerGraph()
    graph.update("INSERT DATA { <urn:a> <urn:p> <urn:b> . <urn:c> <urn:p> <urn:d> }")
    rows = list(graph.query("SELECT ?o WHERE { ?s <urn:p> ?o }", initBindings={"s": ox.NamedNode("urn:a")}))
    assert len(rows) == 1


def test_a_version_mismatch_is_a_sparql_format_error_with_the_version_context():
    with pytest.raises(FormatError) as caught:
        StarLayerGraph().query('VERSION "9.9" SELECT * WHERE { ?s ?p ?o }')
    assert caught.value.kind == "sparql" and caught.value.context == "VERSION"


# --- check.py reports the same problems --------------------------------------------------------------------------------

def test_check_query_reports_a_syntax_problem_with_its_line_and_column():
    result = check.check_query("SELECT *\nWHERE { ?s ?p }")
    (problem,) = result.errors
    assert (problem.kind, problem.line, problem.column) == ("syntax", 2, 15)


def test_check_query_reports_a_query_nested_too_deeply_as_a_syntax_problem():
    (problem,) = check.check_query(DEEP).errors
    assert problem.kind == "syntax" and "nested too deeply" in problem.message and (problem.line, problem.column) == (1, 1)


def test_check_query_reports_a_version_problem_once():
    result = check.check_query('VERSION "9.9" SELECT * WHERE { ?s ?p ?o }')
    assert [p.kind for p in result.errors] == ["version"]
