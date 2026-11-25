"""``check_query()``: is this text a SPARQL 1.2 query or update, and what is wrong or doubtful about it."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from starlayer.errors import ExecutionError, FormatError, only_kind

__all__ = ["QueryCheck", "QueryProblem", "check_query"]

_FORMS = {
    "SelectQuery": "SELECT",
    "AskQuery": "ASK",
    "ConstructQuery": "CONSTRUCT",
    "DescribeQuery": "DESCRIBE",
    "UpdateRequest": "UPDATE",
}
_SHACL_RESULT_MESSAGE = "http://www.w3.org/ns/shacl#resultMessage"


@dataclass(frozen=True)
class QueryProblem:
    """One finding about a query text.

    ``kind`` is ``"syntax"`` (outside the grammar), ``"prefix"`` (a prefix the text does not declare: a warning when no ``prefixes`` were given, else an error), ``"version"`` (a ``VERSION``
    directive the text contradicts, or an unknown one), ``"engine"`` (Oxigraph rejected it) or ``"shape"``
    (a finding of the ``sqe:`` shapes, such as a variable that is never bound). ``severity`` is ``"error"`` or ``"warning"``: a
    warning is legal SPARQL that is probably a mistake. ``line`` and ``column`` (1-based) are known for syntax and prefix findings.
    """

    kind: str
    severity: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class QueryCheck:
    """What ``check_query`` found: the query ``form`` (``None`` when the text does not parse) and every ``problems`` entry."""

    form: str | None
    problems: tuple[QueryProblem, ...] = ()

    @property
    def errors(self) -> tuple[QueryProblem, ...]:
        """The problems that make the text wrong."""
        return tuple(p for p in self.problems if p.severity == "error")

    @property
    def warnings(self) -> tuple[QueryProblem, ...]:
        """The problems that leave the text legal."""
        return tuple(p for p in self.problems if p.severity == "warning")

    @property
    def ok(self) -> bool:
        """True when there is no error; warnings do not count."""
        return not self.errors


_UNDECLARED_PREFIX = re.compile(r"undeclared prefix '([^']*)'")


def _parse_once(text: str, prefixes: Mapping[str, str]) -> tuple[Any, QueryProblem | None]:
    """The AST of a query, else of an update, else the problem the better-matching grammar found."""
    from starlayer.sparql.parse_sparql import (
        parse_sparql,
        parse_sparql_update,
    )

    try:
        return parse_sparql(text, prefixes=dict(prefixes) or None), None
    except ExecutionError as error:  # nested too deeply to parse: a problem of the text, at its start
        only_kind(error, "nesting")
        return None, QueryProblem("syntax", "error", str(error), 1, 1)
    except FormatError as query_error:
        # the update parser takes no prefixes, so they go in front as PREFIX lines
        head = "".join(f"PREFIX {prefix}: <{iri}>\n" for prefix, iri in prefixes.items())
        try:
            return parse_sparql_update(head + text), None
        except ExecutionError as error:
            only_kind(error, "nesting")
            return None, QueryProblem("syntax", "error", str(error), 1, 1)
        except FormatError as update_error:
            # the text is meant as whichever grammar read further before failing: a query typo is far in, a non-query fails at the start
            if update_error.pos - len(head) > query_error.pos:
                error, line = update_error, update_error.line - head.count("\n")
            else:
                error, line = query_error, query_error.line
            kind = "prefix" if error.why.startswith("undeclared prefix") else "syntax"
            return None, QueryProblem(kind, "error", error.why, line, error.col)


def _parse(text: str, prefixes: Mapping[str, str] | None) -> tuple[Any, list[QueryProblem], QueryProblem | None]:
    """The AST, the undeclared prefixes found on the way as warnings, and the error that stopped the parse, if any.

    Without ``prefixes`` the graph the text will run against may declare them, so an undeclared prefix is a warning: it gets a
    placeholder namespace and the parse goes on, so the rest of the text is still checked.
    """
    declared = dict(prefixes or {})
    found: list[QueryProblem] = []
    while True:
        ast, error = _parse_once(text, declared)
        if error is None:
            return ast, found, None
        match = _UNDECLARED_PREFIX.match(error.message)
        if match is None or prefixes is not None or match[1] in declared:
            return None, found, error
        found.append(QueryProblem("prefix", "warning", error.message, error.line, error.column))
        declared[match[1]] = f"urn:starlayer:undeclared-prefix:{match[1]}/"


def _has_service(x: Any) -> bool:
    """Whether the tree has a ``SERVICE`` pattern: preparing such a query would send the request."""
    if hasattr(x, "kind") and hasattr(x, "f"):
        return x.kind == "Service" or any(_has_service(v) for v in x.f.values())
    if isinstance(x, (list, tuple)):
        return any(_has_service(v) for v in x)
    return False


def _version_problem(text: str) -> QueryProblem | None:
    """The error ``query()`` would raise for the ``VERSION`` directive of ``text``."""
    from starlayer.graph.execution.sparql_text import check_native_version_conformance

    try:
        check_native_version_conformance(text)
    except FormatError as error:
        return QueryProblem("version", "error", " ".join(str(error).split()))
    return None


def _engine_problem(text: str, prefixes: Mapping[str, str] | None, functions: dict[str, Any]) -> QueryProblem | None:
    """What Oxigraph says about a query run on an empty graph. Oxigraph has no prepare-only call."""
    from starlayer.graph import StarLayerGraph

    try:
        StarLayerGraph(prefixes=dict(prefixes or {})).query(text, **functions)
    except FormatError as error:
        if error.context == "VERSION":
            return None  # reported as a version problem
        return QueryProblem("engine", "error", " ".join(str(error).split()))
    except ExecutionError as error:  # the engine's RuntimeError, wrapped at the boundary; any other kind is not a problem of the query
        only_kind(error, "query")
        return QueryProblem("engine", "error", " ".join(str(error).split()))
    except (ValueError, NotImplementedError) as error:  # what the wrapper reports
        return QueryProblem("engine", "error", " ".join(str(error).split()))
    return None


def _shape_problems(ast: Any) -> list[QueryProblem]:
    """The findings of the ``sqe:`` shapes on the query tree, as warnings."""
    import warnings

    from starlayer.graph import StarLayerGraph
    from starlayer.shacl.engine.terms import StarLayerFidelityWarning
    from starlayer.sparql.parse_sparql import ast_to_triples
    from starlayer.sparql.sqe.shapes import _validate_shapes

    triples, _ = ast_to_triples(ast)
    tree = StarLayerGraph(prefixes={})
    tree.extend(triples)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        report = _validate_shapes(tree)
    if report.conforms:
        return []
    messages = {row.message.value for row in report.report_graph.query(f"SELECT ?message WHERE {{ ?result <{_SHACL_RESULT_MESSAGE}> ?message }}")}
    return [QueryProblem("shape", "warning", message) for message in sorted(messages)]


def check_query(
    text: str,
    prefixes: Mapping[str, str] | None = None,
    *,
    custom_functions: Mapping[Any, Any] | None = None,
    custom_aggregate_functions: Mapping[Any, Any] | None = None,
) -> QueryCheck:
    """Check ``text`` as a SPARQL 1.2 query or update: the grammar, its ``VERSION`` directive, the ``sqe:`` shapes and, for a query,
    Oxigraph, which has the last word on what it accepts.

    ``prefixes`` (prefix to namespace, such as ``graph.prefixes``) are taken as declared before the text. Without them an undeclared
    prefix is a warning, since the graph the text runs against may declare it; with them it is an error. Oxigraph runs the query on an
    empty graph, so ``custom_functions`` and ``custom_aggregate_functions`` (as for ``query()``) must name the functions the text calls.
    An update, a query with a ``SERVICE`` clause (which would send the request) and a text with an undeclared prefix are not run.
    """
    ast, problems, error = _parse(text, prefixes)
    if error is not None:
        return QueryCheck(None, (*problems, error))
    form = _FORMS.get(ast.kind)
    undeclared = bool(problems)
    version = _version_problem(text)
    if version is not None:
        problems.append(version)
    if form != "UPDATE" and not undeclared and not _has_service(ast):
        functions = {"custom_functions": custom_functions, "custom_aggregate_functions": custom_aggregate_functions}
        engine = _engine_problem(text, prefixes, {name: value for name, value in functions.items() if value})
        if engine is not None:
            problems.append(engine)
    problems.extend(_shape_problems(ast))
    return QueryCheck(form, tuple(problems))
