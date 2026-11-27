"""SHACL validation for ``sqe:`` graphs - a thin wrapper combining this
vocabulary's own hand-authored shapes (``sqe_shapes.ttl``) with the shared
expression shapes and ontology (``spexpr:``, from ``..expr_validation``),
since ``sqe:Filter``/``sqe:Bind`` reference ``spexpr:ExpressionShape`` by name
(``sh:node``) - that shape's own *definition* has to be present in the shapes
graph being validated against, not just its ontology class for RDFS reasoning.
Nothing here imports or loads ``salg``.

No public ``ontology_graph()``/``shapes_graph()`` of its own - same choice
``srl.py`` already made ("to avoid two paths to the same two graphs"; see
that module's own comment) and the same reason Manchester doesn't have
them either (`starontology.get_ontology_graph("sqe_owl")`/`"sqe_shacl"`
is the one real path to those graphs). The shapes for the ordered children (``tree:ord``) are the shared ``tree:`` ones, merged in by
``..expr_validation``. ``validate_sqe_tree()`` combines them
privately below, then adds the engine check: each query in a conforming tree must also be accepted by Oxigraph.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from starlayer import starontology
from starlayer.errors import ExecutionError, FormatError, reraise_unless

from .._oxterms import RDF
from ..expr_validation import rdfs_entailed_copy, rdfs_schema

if TYPE_CHECKING:
    from starlayer.shacl.results import ValidationReport

RDF_TYPE = RDF.type
SHAPES_TURTLE = starontology.get_ontology_graph("sqe_shacl").serialize(format="turtle12")


def _merge_into(dst, src):
    """``dst += src``."""
    dst.extend(src)


@functools.lru_cache(maxsize=1)
def _schema() -> tuple[dict, dict, dict, dict]:
    """The closed schema maps of the ``sqe:`` + ``spexpr:`` ontology (see ``expr_validation.rdfs_schema``)."""
    return rdfs_schema(_ontology_graph())


def _entailed_copy(data_graph: Any) -> Any:
    """``data_graph`` closed under the RDFS rules the ``sqe:`` shapes rely on (see ``expr_validation.rdfs_entailed_copy``)."""
    return rdfs_entailed_copy(data_graph, _schema())


@functools.lru_cache(maxsize=1)
def _shapes_graph() -> Any:
    """The ``StarLayerGraph`` combining ``sqe:``'s own shapes with the shared expression shapes (``spexpr:``; see
    ``..expr_validation``), built once: validation never changes its shapes graph. Nothing here comes from ``salg:``."""
    from ..expr_validation import shapes_graph as spexpr_shapes_graph

    g = spexpr_shapes_graph()
    g.parse(data=SHAPES_TURTLE, format="turtle")
    return g


_PLANS: dict = {}  # the parsed Plan of ``_shapes_graph()``, kept across calls (see ``shacl._adapter.shared_plans``)


def _ontology_graph() -> Any:
    """A fresh ``StarLayerGraph`` combining ``sqe:``'s own RDFS ontology with the shared ``spexpr:`` one, which
    the RDFS-subclass entailment behind ``sh:node spexpr:ExpressionShape`` depends on."""
    from ..expr_validation import ontology_graph as spexpr_ontology_graph

    g = spexpr_ontology_graph()
    _merge_into(g, starontology.get_ontology_graph("sqe_owl"))
    return g


def _validate_shapes(tree_graph: Any) -> ValidationReport:
    """Only the ``sqe:`` shapes: the report ``validate_sqe_tree`` starts from. ``check_query`` uses it and runs the engine itself."""

    from starlayer.shacl._adapter import (  # lazy: avoids a circular-import deadlock at module load time
        shared_plans,
        validate_bounded,
    )

    from ._memtree import as_engine_graph

    tree_graph, _ = as_engine_graph(tree_graph)
    with shared_plans(_PLANS):
        result = validate_bounded(_entailed_copy(tree_graph), _shapes_graph(), max_validation_depth=100)
    return result


def _engine_problems(tree_graph: Any) -> list[tuple[Any, str]]:
    """``(query root, message)`` for each query in ``tree_graph`` that its own rendered text shows to be wrong: not in the grammar, a
    ``VERSION`` it contradicts, or refused by Oxigraph (``check_query``'s rules: updates and queries with ``SERVICE`` are not run)."""
    from starlayer.sparql.check import (
        _engine_problem,
        _has_service,
        _parse,
        _version_problem,
    )

    from ._memtree import as_engine_graph
    from .to_text import render_sqe_tree
    from .vocab import QUERY

    graph, _ = as_engine_graph(tree_graph)
    found = []
    for root in sorted(set(graph.subjects(RDF_TYPE, QUERY)), key=str):
        try:
            text = render_sqe_tree(graph, root)
        except (ValueError, FormatError) as error:
            found.append((root, f"The query cannot be written out as SPARQL text: {' '.join(str(error).split())}"))
            continue
        except ExecutionError as error:  # nested too deeply, or a node with no text form; any other kind is a real failure
            reraise_unless(error, "limit", "unsupported")
            found.append((root, f"The query cannot be written out as SPARQL text: {' '.join(str(error).split())}"))
            continue
        ast, _, error = _parse(text, None)
        problem = error or _version_problem(text)
        if problem is None and not _has_service(ast):
            problem = _engine_problem(text, None, {})
        if problem is not None:
            who = {"syntax": "The rendered text is not SPARQL 1.2", "version": "The rendered text contradicts its VERSION", "engine": "Oxigraph rejects the rendered query"}
            found.append((root, f"{who.get(problem.kind, 'The rendered query is wrong')}: {problem.message}"))
    return found


def validate_sqe_tree(tree_graph: Any) -> ValidationReport:
    """Validate ``tree_graph`` (e.g. from ``sparql_to_tree``, or
    an LLM-/UI-authored ``sqe:`` graph not yet decoded) against the shapes
    above, and check that Oxigraph accepts each query in it.

    Goes through ``starlayer.shacl`` (the native SHACL 1.2 engine): a ``sqe:`` graph may embed
    genuine RDF 1.2 content (a triple term).

    Only when the shapes conform, each query root (every ``sqe:Query`` in the graph, which may hold several) is rendered with
    ``render_sqe_tree`` and checked as ``check_query`` does: the text must be in the grammar, agree with its ``VERSION``
    and run on an empty graph in Oxigraph, which has the last word on what it accepts. A query with a ``SERVICE`` pattern
    (which would send the request) and an update are not run. A structurally broken tree may not render, so it is left to the shapes.
    A rejection is an ``sh:ValidationResult`` (severity ``sh:Violation``, focus node the query's root, readable ``sh:resultMessage``)
    in the report, which then does not conform. Oxigraph runs the query without any custom function, so a query that calls
    an extension function is rejected here; ``check_query`` takes ``custom_functions`` for that.

    Args:
        tree_graph: The ``sqe:`` RDF graph (a ``StarLayerGraph``) to validate.

    Returns:
        The ``ValidationReport`` ``starlayer.shacl.validate()`` gives, with any Oxigraph rejection added; it is
        not iterable, so read ``conforms``, ``report_text`` and the rest by name.
    """
    report = _validate_shapes(tree_graph)
    if not report.conforms:
        return report
    problems = _engine_problems(tree_graph)
    if not problems:
        return report
    return _with_violations(report, problems)


def _with_violations(report: ValidationReport, problems: list[tuple[Any, str]], *, severity: str = "Violation") -> ValidationReport:
    """``report`` with one result of ``severity`` (``"Violation"``, or ``"Warning"``) added per ``(focus node, message)`` of
    ``problems``, for a finding a check outside the shapes makes (Oxigraph's rejection of a query, an SRL ordering problem). A
    ``Violation`` makes the report non-conforming; a ``Warning`` does not. The report's own results and text are kept."""
    import pyoxigraph as ox

    from starlayer.shacl.engine.terms import SH
    from starlayer.shacl.results import ValidationReport

    graph = report.report_graph
    top = next(iter(graph.subjects(SH.conforms, None)))
    kind = SH.Violation if severity == "Violation" else SH.Warning
    conforms = report.conforms and severity != "Violation"
    if report.conforms != conforms:
        graph.remove((top, SH.conforms, None))
        graph.add((top, SH.conforms, ox.Literal("false", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))))
    blocks = []
    for root, message in problems:
        result = ox.BlankNode()
        graph.extend(
            [
                (top, SH.result, result),
                (result, RDF_TYPE, SH.ValidationResult),
                (result, SH.focusNode, root),
                (result, SH.resultSeverity, kind),
                (result, SH.sourceConstraintComponent, SH.SPARQLConstraintComponent),
                (result, SH.resultMessage, ox.Literal(message)),
            ]
        )
        label = "Constraint Violation" if severity == "Violation" else "Validation Result"
        blocks.append(f"{label} in the engine check:\n\tSeverity: sh:{severity}\n\tFocus Node: {root}\n\tMessage: {message}")
    earlier = report.report_text.split("\n")
    kept = earlier[3:] if len(earlier) > 3 and earlier[2].startswith("Results (") else []  # the report's own result blocks
    total = len(list(graph.objects(top, SH.result)))
    text = "\n".join(["Validation Report", f"Conforms: {conforms}", f"Results ({total}):", *kept, *blocks])
    return ValidationReport(conforms, graph, text, diagnostics=report.diagnostics)
