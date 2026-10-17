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

import functools

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.paths import Path
from rdflib.plugins.sparql.algebra import (
    simplifyFilters,
    translatePath,
    translatePName,
    translatePrologue,
    traverse,
)
from rdflib.plugins.sparql.algebra import triples as group_triples
from rdflib.plugins.sparql.parserutils import CompValue, ParseResults
from rdflib.term import IdentifiedNode

from ..to_rdf import _encode as _encode_algebra
from ..to_rdf import _encode_path, _new_starlayer_graph
from .vocab import (
    ASK_QUERY,
    BIND,
    BIND_VAR,
    CONSTRUCT_QUERY,
    EXPR,
    FILTER,
    OPTIONAL,
    PREFIX_BINDING,
    PREFIX_LABEL,
    PREFIX_NAMESPACE,
    PROJECTION,
    PROLOGUE_BASE,
    PROLOGUE_PREFIX,
    PY_STR_DATATYPE,
    QUERY,
    SELECT_QUERY,
    TEMPLATE,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    UNION,
    UNION_ALTERNATIVES,
    VARIABLE_DATATYPE,
    WHERE,
)

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


def sqe_parse_to_tree(
    text: str, graph: Graph | None = None, root: IdentifiedNode | None = None
) -> tuple[Graph, IdentifiedNode]:
    """Encode SPARQL ``SELECT``/``ASK``/``CONSTRUCT`` query text as
    ``sqe:`` RDF, and validate the result. The one public encoding entry
    point - parses ``text`` with the same ``parseQuery`` every other
    SPARQL 1.2 entry point in this package uses, delegates to
    ``_query_to_sqe_rdf`` below, then validates via :func:`sqe_validate`
    before returning - a caller only ever gets back a tree already
    confirmed to satisfy ``sqe:``'s own shapes (including the
    unbound-projected-variable check), never one silently known to fail.

    Validation only runs here, at creation time - it has no way to see,
    and does not re-run for, any edit made to the tree afterward (see
    the guide notebook's own section on this). Call :func:`sqe_validate`
    yourself again after editing a tree directly.

    Args:
        text: The SPARQL query text to encode.
        graph: The graph to add the ``sqe:`` RDF to. Defaults to a
            fresh ``StarLayerGraph`` (see ``to_rdf._new_starlayer_graph``).
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
        A ``(graph, root)`` tuple.

    Raises:
        NotImplementedError: For anything outside v1's scope
            (``DESCRIBE``; aggregates/``GROUP BY``/``HAVING``,
            subqueries, ``VALUES``, or any ``WHERE``-clause element
            besides a triple pattern/``OPTIONAL``/``UNION``/``FILTER``/
            ``BIND``) rather than silently mis-encoding - see
            ``vocab.py``'s module docstring and `future_enhancements.md`
            for the deliberate scope reduction this mirrors from SRL.
        SQEValidationError: If the text parses fine but the encoded tree
            fails ``sqe:``'s own SHACL shapes.
    """
    from rdflib.plugins.sparql.parser import parseQuery

    # Lazy: sqe_validate() needs pyshacl, which the rest of this module
    # doesn't - see sqe/__init__.py's own try/except around importing it,
    # for the identical reason. pyshacl is a core starlayer dependency in
    # practice (see pyproject.toml), but this keeps to_rdf.py itself
    # importable without it regardless, same as every other lazy import
    # already in this file.
    from .shapes import sqe_validate

    encoded_graph, encoded_root = _query_to_sqe_rdf(parseQuery(text), graph, root)
    conforms, report_graph, report_text = sqe_validate(encoded_graph)
    if not conforms:
        raise SQEValidationError(report_text, report_graph)
    return encoded_graph, encoded_root


def _query_to_sqe_rdf(
    parse_result: ParseResults, graph: Graph | None = None, root: IdentifiedNode | None = None
) -> tuple[Graph, IdentifiedNode]:
    """Encode a ``SELECT``/``ASK``/``CONSTRUCT`` query's raw parse tree
    (``parseQuery(text)``'s output — ``[prologue, query]``) as ``sqe:``
    RDF.

    Private: ``sqe_parse_to_tree`` above is the public entry point. Taking
    an already-``parseQuery()``'d tree directly (rather than text) is a
    low-level, non-obvious input shape for a public API to expose, and
    nothing in this package currently needs that flexibility - kept as a
    separate function purely so the actual encoding logic stays testable/
    reusable without forcing a real parse through ``sqe_parse_to_tree`` on
    every call.

    Args:
        parse_result: ``parseQuery(text)``'s raw ``[prologue, query]``
            output.
        graph: The graph to add the ``sqe:`` RDF to. Defaults to a
            fresh ``StarLayerGraph``.
        root: The node to use as the query's own root. Defaults to a
            fresh ``BNode()`` - see ``sqe_parse_to_tree``'s own docstring
            for why a caller would give a real ``URIRef`` instead.

    Returns:
        A ``(graph, root)`` tuple.
    """
    prologue_list, query = parse_result[0], parse_result[1]
    root_type = _ROOT_TYPE_BY_QUERY_NAME.get(query.name)
    if root_type is None:
        raise NotImplementedError(
            f"starlayer.sparql.sqe: only SELECT/ASK/CONSTRUCT are modeled yet, got {query.name!r}"
        )

    # Same two-pass resolution translateQuery itself does, just without the
    # rest of that function - see to_ssyn_rdf.py's module docstring for why
    # translatePath must run before any TriplesBlock grouping below.
    prologue = translatePrologue(prologue_list, base=None)
    query = traverse(query, visitPost=functools.partial(translatePName, prologue=prologue))
    query.where = traverse(query.where, visitPost=translatePath)
    if root_type is CONSTRUCT_QUERY:
        query.template = traverse(query.template, visitPost=translatePath)

    if graph is None:
        graph = _new_starlayer_graph()
    if root is None:
        root = BNode()
    graph.add((root, RDF.type, root_type))
    graph.add((root, RDF.type, QUERY))
    if root_type is SELECT_QUERY:
        graph.add((root, PROJECTION, _encode_var_list(query.projection, graph)))
    elif root_type is CONSTRUCT_QUERY:
        template_nodes = [
            _encode_triple_pattern(s, p, o, graph) for s, p, o in query.template
        ]
        graph.add((root, TEMPLATE, _build_rdf_list(template_nodes, graph)))
    graph.add((root, WHERE, _encode_where_group(query.where, graph)))
    _encode_raw_prologue(prologue_list, root, graph)
    return graph, root


def _encode_raw_prologue(prologue_list, root, graph: Graph) -> None:
    """Encode exactly the query's own ``PREFIX``/``BASE`` declarations
    (``parseQuery()``'s raw ``q[0]``) onto ``root`` - see this module's own
    docstring for why this walks the raw list rather than reusing
    ``to_rdf._encode_prologue``."""
    for decl in prologue_list:
        if decl.name == "Base":
            graph.add((root, PROLOGUE_BASE, decl.iri))
        elif decl.name == "PrefixDecl":
            # A bare `PREFIX :` (the default/no-label prefix) parses with
            # decl.prefix set to Python None, not an empty string.
            # Literal(None, ...) would stringify to the text "None",
            # silently corrupting the rendered PREFIX declaration -
            # encode the real empty string instead.
            label = decl.prefix if decl.prefix is not None else ""
            binding = BNode()
            graph.add((binding, RDF.type, PREFIX_BINDING))
            graph.add((binding, PREFIX_LABEL, Literal(label, datatype=PY_STR_DATATYPE)))
            graph.add((binding, PREFIX_NAMESPACE, decl.iri))
            graph.add((root, PROLOGUE_PREFIX, binding))


def _encode_var_list(projection, graph: Graph):
    variables = [v.var for v in projection]
    return _build_rdf_list([_encode_variable(v) for v in variables], graph)


def _encode_where_group(group: CompValue, graph: Graph):
    """``GroupGraphPatternSub`` -> a flat, ordered rdf:List of sibling
    pattern elements - its ``.part`` is already exactly this shape in the
    raw parse tree. See ``to_ssyn_rdf.py``'s own docstring for the full
    rationale (identical technique, reused directly)."""
    nodes: list = []
    for part in group.part or []:
        if part.name == "TriplesBlock":
            for s, p, o in group_triples(part.triples):
                nodes.append(_encode_triple_pattern(s, p, o, graph))
        else:
            nodes.append(_encode_where_element(part, graph))
    return _build_rdf_list(nodes, graph)


def _encode_where_element(part: CompValue, graph: Graph) -> BNode:
    if part.name == "OptionalGraphPattern":
        node = BNode()
        graph.add((node, RDF.type, OPTIONAL))
        graph.add((node, WHERE, _encode_where_group(part.graph, graph)))
        return node
    if part.name == "Filter":
        node = BNode()
        graph.add((node, RDF.type, FILTER))
        graph.add((node, EXPR, _encode_algebra(simplifyFilters(part.expr), graph)))
        return node
    if part.name == "Bind":
        node = BNode()
        graph.add((node, RDF.type, BIND))
        graph.add((node, EXPR, _encode_algebra(simplifyFilters(part.expr), graph)))
        graph.add((node, BIND_VAR, _encode_variable(part.var)))
        return node
    if part.name == "GroupOrUnionGraphPattern":
        node = BNode()
        graph.add((node, RDF.type, UNION))
        alts = _build_rdf_list([_encode_where_group(alt, graph) for alt in part.graph], graph)
        graph.add((node, UNION_ALTERNATIVES, alts))
        return node
    raise NotImplementedError(
        f"starlayer.sparql.sqe: WHERE-clause element {part.name!r} not modeled yet - "
        "v1's deliberate scope reduction, see vocab.py's module docstring"
    )


def _encode_triple_pattern(s, p, o, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, TRIPLE_PATTERN))
    graph.add((node, TRIPLE_PATTERN_SUBJECT, _encode_term(s, graph)))
    graph.add((node, TRIPLE_PATTERN_PREDICATE, _encode_predicate(p, graph)))
    graph.add((node, TRIPLE_PATTERN_OBJECT, _encode_term(o, graph)))
    return node


def _encode_predicate(p, graph: Graph):
    """A predicate position may be a genuine property path - collapse the
    trivial (non-path) case down to a bare term via rdflib's own
    translatePath, and fall back to the existing salg: path encoding
    (to_rdf._encode_path, unchanged) only for a real path."""
    translated = translatePath(p) if isinstance(p, CompValue) else p
    if isinstance(translated, Path):
        return _encode_path(translated, graph)
    return _encode_term(translated, graph)


def _encode_term(value, graph: Graph):
    if isinstance(value, Variable):
        return _encode_variable(value)
    return value  # a real, already-resolved RDF term (URIRef/BNode/Literal)


def _encode_variable(value: Variable) -> Literal:
    return Literal(str(value), datatype=VARIABLE_DATATYPE)


def _build_rdf_list(nodes: list, graph: Graph) -> BNode | URIRef:
    if not nodes:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, nodes)
    return list_node
