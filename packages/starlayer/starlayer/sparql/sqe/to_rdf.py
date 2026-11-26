"""Encode SPARQL query (or Update) text as ``sqe:`` RDF - see ``vocab.py``'s module docstring for the design.

The text is parsed by StarLayer's own SPARQL 1.2 parser (``sparql/parse_sparql.py``, a hand-written recursive-descent parser
whose syntax tree is made of pyoxigraph terms) and the syntax tree is written out as the ``sqe:`` tree, a ``StarLayerGraph``
of pyoxigraph terms (``parse_sparql._Encoder``). Nothing here needs rdflib. The query's own ``PREFIX`` / ``BASE`` /
``VERSION`` declarations are kept on the root (``sqe:prefixDecl`` / ``sqe:base`` / ``sqe:version``) so
``sqe_tree_to_text`` can write the text with the prefixes the author used.
"""

from __future__ import annotations

import re
from typing import Any

import pyoxigraph as ox

from starlayer.errors import FormatError

_UPDATE_START = re.compile(
    r"(?is)\A(?:\s+|#[^\n]*|(?:PREFIX\s+[^\s:]*:\s*<[^>]*>)|(?:BASE\s*<[^>]*>)|(?:VERSION\s+(?:'[^']*'|\"[^\"]*\")))*"
    r"(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|WITH)\b"
)
# text with a prologue and nothing else (PREFIX / BASE / VERSION lines, comments, blanks, or no text at all): an update request with no operation
_PROLOGUE_ONLY = re.compile(
    r"(?is)\A(?:\s+|#[^\n]*|(?:PREFIX\s+[^\s:]*:\s*<[^>]*>)|(?:BASE\s*<[^>]*>)|(?:VERSION\s+(?:'[^']*'|\"[^\"]*\")))*\Z"
)


def sqe_parse_to_tree(
    text: str,
    tree_graph: Any = None,
    root: Any = None,
) -> tuple[Any, Any]:
    """Encode SPARQL ``SELECT``/``ASK``/``CONSTRUCT``/``DESCRIBE`` query text (or SPARQL Update text) as
    ``sqe:`` RDF. The one public encoding entry
    point - parses ``text`` with StarLayer's own SPARQL 1.2 parser
    (``sparql.parse_sparql``: every query form, FROM / FROM NAMED, SERVICE,
    VERSION, and Update).

    Any text the parser understands gives a tree, even a query that breaks the ``sqe:`` shapes (an unbound projected variable, say):
    nothing is validated here, so a query with errors can still be loaded and fixed. Call :func:`sqe_validate` on the tree to
    report those problems; run it again after editing a tree directly.

    A query may hold IRIs that are not absolute (``<s>`` with no ``BASE``) or other text an RDF term cannot be: the tree
    keeps each as an opaque stand-in IRI (``urn:starlayer:invalid-iri:...``) that ``sqe_tree_to_text`` turns back into the
    original text. A store rewrites some literal lexical forms (``"007"^^xsd:integer`` becomes ``"7"``).

    Args:
        text: The SPARQL query text to encode.
        tree_graph: The graph to add the ``sqe:`` RDF to: a ``StarLayerGraph`` (pyoxigraph terms), or an rdflib graph (filled with
            rdflib terms; rdflib is then needed). Defaults to a fresh ``StarLayerGraph``.
        root: The node to use as the query's own root - any ``NamedNode``/
            ``BlankNode``. Defaults to a fresh blank node. Give a real
            IRI to make the query findable by that identity later
            (e.g. ``graph.value(my_iri, RDF.type, SQE.Query)``), rather
            than only via the ``root`` value this function itself
            returns - useful once a graph accumulates more than one
            encoded query (via repeated calls sharing one ``tree_graph=``),
            where a bare `?s a sqe:Query` lookup can no longer tell them
            apart on its own.

    Returns:
        A ``(tree_graph, root)`` tuple, not checked against the shapes; with no ``tree_graph`` given, a ``StarLayerGraph`` and a pyoxigraph ``root``.

    Raises:
        FormatError: (kind "sparql") For text outside the SPARQL 1.2 query and update grammars, with ``line`` / ``col``. Text that holds
            only a prologue (``PREFIX``, ``BASE``, ``VERSION``, comments) is an update request with no operation: it loads as an
            empty ``sqe:UpdateRequest`` and ``sqe_tree_to_text`` writes back its prologue (or an empty string for comments only or no text, which loads again as the same empty request).
        ExecutionError: (kind "nesting") The query is nested too deeply for Python's stack.
    """
    from ..parse_sparql import ast_to_triples, parse_sparql

    try:
        ast = parse_sparql(text)
    except FormatError:
        if not (_UPDATE_START.match(text) or _PROLOGUE_ONLY.match(text)):
            raise
        from ..parse_sparql import parse_sparql_update

        ast = parse_sparql_update(text)  # Update text: the same encoder, a tree rooted at sqe:UpdateRequest
    if root is not None:
        from starlayer.shacl.engine.terms import to_engine

        root = to_engine(root)
        if not isinstance(root, (ox.NamedNode, ox.BlankNode)):
            raise TypeError(f"root must be an IRI or a blank node, not {type(root).__name__}")
    triples, root = ast_to_triples(ast, root)
    from starlayer.graph.core import StarLayerGraph

    tree = StarLayerGraph(prefixes={}) if tree_graph is None else tree_graph
    tree.extend(triples)
    return tree, root
