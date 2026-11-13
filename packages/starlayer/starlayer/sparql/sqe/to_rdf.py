"""Encode SPARQL query (or Update) text as ``sqe:`` RDF - see ``vocab.py``'s module docstring for the design.

The text is parsed by StarLayer's own SPARQL 1.2 parser (``sparql/parse_sparql.py``, a hand-written recursive-descent parser
whose syntax tree is made of pyoxigraph terms) and the syntax tree is written out as the ``sqe:`` tree, a ``StarLayerGraph``
of pyoxigraph terms (``parse_sparql._Encoder``). Nothing here needs rdflib. The query's own ``PREFIX`` / ``BASE`` /
``VERSION`` declarations are kept on the root (``sqe:prologuePrefix`` / ``sqe:base`` / ``sqe:version``) so
``sqe_tree_to_text`` can write the text with the prefixes the author used.
"""

from __future__ import annotations

import re
from typing import Any

import pyoxigraph as ox


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

    def __init__(self, report_text: str, report_graph: Any) -> None:
        """Carry the SHACL report as text (in the message and report_text) and as a graph (report_graph)."""
        super().__init__(f"sqe: parsed query fails SHACL validation:\n{report_text}")
        self.report_text = report_text
        self.report_graph = report_graph


_UPDATE_START = re.compile(
    r"(?is)\A(?:\s+|#[^\n]*|(?:PREFIX\s+[^\s:]*:\s*<[^>]*>)|(?:BASE\s*<[^>]*>)|(?:VERSION\s+(?:'[^']*'|\"[^\"]*\")))*"
    r"(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|WITH)\b"
)


def sqe_parse_to_tree(
    text: str,
    graph: Any = None,
    root: Any = None,
) -> tuple[Any, Any]:
    """Encode SPARQL ``SELECT``/``ASK``/``CONSTRUCT``/``DESCRIBE`` query text (or SPARQL Update text) as
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

    A query may hold IRIs that are not absolute (``<s>`` with no ``BASE``) or other text an RDF term cannot be: the tree
    keeps each as an opaque stand-in IRI (``urn:starlayer:invalid-iri:...``) that ``sqe_tree_to_text`` turns back into the
    original text. A store rewrites some literal lexical forms (``"007"^^xsd:integer`` becomes ``"7"``).

    Args:
        text: The SPARQL query text to encode.
        graph: The graph to add the ``sqe:`` RDF to: a ``StarLayerGraph`` (pyoxigraph terms), or an rdflib graph (filled with
            rdflib terms; rdflib is then needed). Defaults to a fresh ``StarLayerGraph``.
        root: The node to use as the query's own root - any ``NamedNode``/
            ``BlankNode``. Defaults to a fresh blank node. Give a real
            IRI to make the query findable by that identity later
            (e.g. ``graph.value(my_iri, RDF.type, SQE.Query)``), rather
            than only via the ``root`` value this function itself
            returns - useful once a graph accumulates more than one
            encoded query (via repeated calls sharing one ``graph=``),
            where a bare `?s a sqe:Query` lookup can no longer tell them
            apart on its own.

    Returns:
        A ``(graph, root)`` tuple; with no ``graph`` given, a ``StarLayerGraph`` and a pyoxigraph ``root``.

    Raises:
        SparqlSyntaxError: For text outside the SPARQL 1.2 query
            grammar; it is a ``ValueError`` with ``line``/``col``.
        SQEValidationError: If the text parses fine but the encoded tree
            fails ``sqe:``'s own SHACL shapes.
    """
    from ..parse_sparql import SparqlSyntaxError, ast_to_triples, parse_sparql
    from .shapes import sqe_validate

    try:
        ast = parse_sparql(text)
    except SparqlSyntaxError:
        if not _UPDATE_START.match(text):
            raise
        from ..parse_sparql import parse_sparql_update

        ast = parse_sparql_update(text)  # Update text: the same encoder, a tree rooted at sqe:UpdateRequest
    if root is not None:
        from starlayer.shacl_engine.terms import to_engine

        root = to_engine(root)  # an rdflib term is converted (rdflib installed); a pyoxigraph term passes
        if not isinstance(root, (ox.NamedNode, ox.BlankNode)):
            raise TypeError(f"root must be an IRI or a blank node, not {type(root).__name__}")
    triples, root = ast_to_triples(ast, root)
    from starlayer.graph.oxgraph.core import StarLayerGraph

    foreign = graph if graph is not None and not getattr(graph, "engine_terms", False) else None
    tree = StarLayerGraph(prefixes={}) if graph is None or foreign is not None else graph
    tree.extend(triples)
    conforms, report_graph, report_text = sqe_validate(tree)
    if not conforms:
        raise SQEValidationError(report_text, report_graph)
    if foreign is not None:  # an rdflib graph is filled with the tree (needs rdflib, which it already is)
        from ._memtree import fill_foreign

        fill_foreign(foreign, tree)
        from starlayer.shacl_engine.terms import from_engine

        return foreign, from_engine(root)
    return tree, root
