"""Encode a `SELECT`/`ASK`/`CONSTRUCT` query's raw parse tree
(``parseQuery()``'s output, same input ``to_ast_rdf.query_ast_to_rdf``/
``to_ssyn_rdf.query_to_ssyn_rdf`` already take) as ``sqe:`` RDF — see
``vocab.py``'s module docstring for the design.

Everything that collapses the parse tree's native verbosity is a real,
existing rdflib function, reused directly (same technique
``to_ssyn_rdf.py`` already established, not reimplemented):

- ``algebra.translatePName`` (via ``traverse(..., visitPost=...)``)
  resolves prefixed names to real absolute IRIs.
- ``algebra.triples`` groups a ``TriplesBlock``'s flat, ungrouped run of
  terms into real ``(s, p, o)`` tuples.
- ``algebra.translatePath`` collapses a trivial single-element path chain
  down to the bare predicate term, or builds a real ``rdflib.paths.Path``
  for a genuine path (falls back to ``to_rdf._encode_path``, unchanged).
- ``algebra.simplifyFilters`` collapses a precedence chain down to
  whatever real expression is actually present.

Unlike ``to_ssyn_rdf.py``, the query's own original ``PREFIX``/``BASE``
declarations are also preserved, under ``sqe:``'s own
``sqe:base``/``sqe:prologuePrefix``/``sqe:PrefixBinding`` terms (a real,
independent duplicate of ``salg:``'s identically-shaped terms, not a
reuse - see ``vocab.py``'s own docstring for why) - and **not** via
``to_rdf.py``'s own ``_encode_prologue`` function. That function
operates on the *already-translated* ``Prologue`` object
(``translatePrologue``'s own output), whose ``namespace_manager`` is
pre-seeded with rdflib's ~29 built-in default prefix bindings
(``rdf``/``rdfs``/``foaf``/``skos``/...) regardless of what the query
itself declared - encoding straight from that object pulls in all ~29
defaults alongside the one real `PREFIX` the user wrote.
``_encode_raw_prologue`` below instead walks the *raw* ``prologue_list``
(``parseQuery()``'s own ``q[0]`` - a flat sequence of ``PrefixDecl``/
``Base`` ``CompValue``s: exactly and only what the query text itself
declared, no pollution) - needed for ``to_text.py``'s prefix-aware
rendering to show only the user's own prefixes, not rdflib's entire
default set.
"""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
import re

from rdflib import Graph
from rdflib.term import IdentifiedNode

from ..spexpr_codec import _NS_OVERRIDES
from ..spexpr_codec import _encode as _encode_algebra
from ..vocab import SPEXPR
from .vocab import (
    ASK_QUERY,
    CONSTRUCT_QUERY,
    SELECT_QUERY,
    SQE,
)

_AGGREGATE_NAMES = (
    "Aggregate_Count", "Aggregate_Sum", "Aggregate_Min", "Aggregate_Max",
    "Aggregate_Avg", "Aggregate_Sample", "Aggregate_GroupConcat",
)


def _encode_expr(value, graph: Graph):
    """Encode an expression (or any term that may contain a triple term) with
    the shared encoder, typing triple terms, aggregates and EXISTS blocks with
    sqe:/spexpr: terms rather than salg: ones."""
    overrides = {"TripleTerm": SQE, **{name: SPEXPR for name in _AGGREGATE_NAMES}}
    ns_token = _NS_OVERRIDES.set(overrides)
    try:
        return _encode_algebra(value, graph)
    finally:
        _NS_OVERRIDES.reset(ns_token)


_ROOT_TYPE_BY_QUERY_NAME = {
    "SelectQuery": SELECT_QUERY,
    "AskQuery": ASK_QUERY,
    "ConstructQuery": CONSTRUCT_QUERY,
}


class SQEError(ValueError):
    """Base class for every ``sqe:``-specific exception
    (``SQEValidationError`` here) - gives a caller two real catch
    granularities, "this specific failure" vs. "any ``sqe:`` failure",
    the same two-tier shape ``srl.py``'s own ``SRLError``/
    ``SRLParseError`` already established for the identical reason."""


class SQEValidationError(SQEError):
    """Raised by :func:`sqe_parse_to_tree` when the text parses fine but
    the resulting ``sqe:`` tree fails ``sqe:``'s own SHACL shapes (most
    notably the unbound-projected-variable check) - "this text doesn't
    produce a usable ``sqe:`` tree", matching the same "succeed with a
    usable object, or raise" contract ``prepareQuery()``/
    ``srl.parse_ruleset()`` already give their own callers, rather than
    handing back a tree that's already known to be unusable and leaving
    it to the caller to remember to check.

    Carries the full validation report as attributes, not just a
    message, so a caller who wants the structured detail doesn't have to
    re-run :func:`sqe_validate` themselves to get it.

    Attributes:
        report_graph: The full ``sh:ValidationReport`` graph.
        report_text: The same report, rendered as text (this
            exception's own ``str()`` is a short prefix plus this text).
    """

    def __init__(self, report_text: str, report_graph: Graph) -> None:
        super().__init__(f"sqe: parsed query fails SHACL validation:\n{report_text}")
        self.report_text = report_text
        self.report_graph = report_graph


_UPDATE_START = re.compile(
    r"(?is)\A(?:\s+|#[^\n]*|(?:PREFIX\s+[^\s:]*:\s*<[^>]*>)|(?:BASE\s*<[^>]*>)|(?:VERSION\s+(?:'[^']*'|\"[^\"]*\")))*"
    r"(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|WITH)\b"
)


def sqe_parse_to_tree(
    text: str,
    graph: Graph | None = None,
    root: IdentifiedNode | None = None,
) -> tuple[Graph, IdentifiedNode]:
    """Encode SPARQL ``SELECT``/``ASK``/``CONSTRUCT`` query text as
    ``sqe:`` RDF, and validate the result. The one public encoding entry
    point - parses ``text`` with StarLayer's own SPARQL 1.2 parser
    (``sparql.parse_sparql``: every query form, FROM / FROM NAMED, SERVICE,
    VERSION, and Update), then validates via :func:`sqe_validate`
    before returning - a caller only ever gets back a tree already
    confirmed to satisfy ``sqe:``'s own shapes (including the
    unbound-projected-variable check), never one silently known to fail.

    Validation only runs here, at creation time - it has no way to see,
    and does not re-run for, any edit made to the tree afterward (see
    the guide notebook's own section on this). Call :func:`sqe_validate`
    yourself again after editing a tree directly.

    Args:
        text: The SPARQL query text to encode.
        graph: The graph to add the ``sqe:`` RDF to: an ``StarLayerGraph`` (pyoxigraph terms) or an rdflib graph (rdflib terms).
            Defaults to a fresh ``StarLayerGraph``.
        root: The node to use as the query's own root - any ``URIRef``/
            ``BNode``. Defaults to a fresh ``BNode()``. Give a real
            ``URIRef`` to make the query findable by that identity later
            (e.g. ``graph.value(my_iri, RDF.type, SQE.Query)``), rather
            than only via the ``root`` value this function itself
            returns - useful once a graph accumulates more than one
            encoded query (via repeated calls sharing one ``graph=``),
            where a bare `?s a sqe:Query` lookup can no longer tell them
            apart on its own.

    Returns:
        A ``(graph, root)`` tuple; with no ``graph`` given, an ``StarLayerGraph`` and a pyoxigraph ``root``.

    Raises:
        SparqlSyntaxError: For text outside the SPARQL 1.2 query
            grammar; it is a ``ValueError`` with ``line``/``col``.
        SQEValidationError: If the text parses fine but the encoded tree
            fails ``sqe:``'s own SHACL shapes.
    """
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    if graph is None:  # encode on a scratch rdflib graph, return a fresh StarLayerGraph
        return _ox.default_boundary(lambda g, r: _parse_to_rdflib_tree(text, g, r), root)
    if _ox.is_oxigraph_input(graph):  # an StarLayerGraph target: encode on rdflib terms, then add them to it
        return _ox.write_boundary(graph, lambda g, r: _parse_to_rdflib_tree(text, g, r), root)
    return _parse_to_rdflib_tree(text, graph, root)


def _parse_to_rdflib_tree(text: str, graph: Graph | None, root: IdentifiedNode | None) -> tuple[Graph, IdentifiedNode]:
    from ..parse_sparql import SparqlSyntaxError, _ast_to_rdflib_tree, parse_sparql
    from .shapes import sqe_validate

    try:
        ast = parse_sparql(text)
    except SparqlSyntaxError:
        if not _UPDATE_START.match(text):
            raise
        from ..parse_sparql import parse_sparql_update

        ast = parse_sparql_update(text)  # Update text: the same encoder, a tree rooted at sqe:UpdateRequest
    encoded_graph, encoded_root = _ast_to_rdflib_tree(ast, graph, root, None)
    conforms, report_graph, report_text = sqe_validate(encoded_graph)
    if not conforms:
        raise SQEValidationError(report_text, report_graph)
    return encoded_graph, encoded_root
