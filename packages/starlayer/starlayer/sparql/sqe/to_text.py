"""Render ``sqe:`` RDF back into literal SPARQL query text, using the
original ``PREFIX``/``BASE`` declarations preserved on the root node to
re-abbreviate terms - the one place this project deliberately does *not*
reuse ``translateAlgebra`` for text output.

**Why a bespoke renderer, not the existing ``translateAlgebra``/
``serialize12`` pipeline** (confirmed against the real code, not assumed):
``rdflib.plugins.sparql.algebra.translateAlgebra`` never reads
``query.prologue`` at all - already a documented rdflib limitation in this
project's own ``CLAUDE.md``, and ``ssyn_to_text.py`` already accepted the
same limit ("full IRIs only, no prefixes"). Going through that pipeline
for text output would silently discard every prefix ``to_rdf.py`` took
care to preserve. Execution doesn't need any of this - ``from_rdf.py``'s
``sqe_tree_to_query`` + rdflib's own unmodified ``translateQuery`` handles
that unaffected by anything in this module.

Expression text comes from ``expr_text.py``, which renders straight from the
sqe tree (aggregates, EXISTS bodies, triple terms and the SPARQL 1.2 builtins
included), and prefix-aware term rendering lives here. An IRI inside an
expression is abbreviated with the preserved prefixes too.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF

from ..from_rdf import _decode
from ..vocab import VARIABLE_DATATYPE
from .expr_text import expr_text
from .vocab import (
    ALIAS,
    ASK_QUERY,
    BIND,
    BIND_VAR,
    CONSTRUCT_QUERY,
    DISTINCT,
    EXPR,
    FILTER,
    GRAPH_PATTERN,
    GRAPH_TERM,
    GROUP_BY,
    HAVING,
    LIMIT,
    MINUS,
    OFFSET,
    OPTIONAL,
    ORDER_BY,
    ORDER_DESCENDING,
    PREFIX_LABEL,
    PREFIX_NAMESPACE,
    PROJECTION,
    PROLOGUE_BASE,
    PROLOGUE_PREFIX,
    QUERY_VALUES,
    REDUCED,
    SELECT_ALL,
    SELECT_QUERY,
    SUB_SELECT,
    TEMPLATE,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    TRIPLE_TERM,
    UNION,
    UNION_ALTERNATIVES,
    VALUES,
    VALUES_ROWS,
    VALUES_UNDEF,
    VALUES_VARS,
    WHERE,
)

_KEYWORD_BY_ROOT_TYPE = {
    SELECT_QUERY: "SELECT",
    ASK_QUERY: "ASK",
    CONSTRUCT_QUERY: "CONSTRUCT",
}


def sqe_tree_to_text(graph: Graph, root) -> str:
    """Render ``root`` (as produced by ``to_rdf.sqe_parse_to_tree``) back
    into SPARQL query text, re-abbreviating terms using the ``PREFIX``
    declarations preserved on ``root`` wherever one matches.

    Args:
        graph: The ``sqe:`` RDF graph containing ``root``.
        root: The query root node to render.

    Returns:
        The rendered SPARQL query text.
    """
    prefixes = _prefix_map(graph, root)
    lines = [f"PREFIX {label}: <{ns}>" for label, ns in sorted(prefixes.items())]

    base = graph.value(root, PROLOGUE_BASE)
    if base is not None:
        lines.append(f"BASE <{base}>")

    lines.extend(_query_lines(graph, root, prefixes))
    return "\n".join(lines)


def _query_lines(graph: Graph, root, prefixes: dict) -> list:
    """The SELECT/CONSTRUCT/ASK clause, WHERE and solution modifiers of a query
    root or a sub-select."""
    keyword = _keyword_for_root(graph, root)
    lines: list = []
    if keyword == "SELECT":
        modifier = (
            "DISTINCT " if graph.value(root, DISTINCT) is not None
            else "REDUCED " if graph.value(root, REDUCED) is not None
            else ""
        )
        if graph.value(root, SELECT_ALL) is not None:
            lines.append(f"SELECT {modifier}*")
        else:
            items = [_alias_or_var_text(v, graph, prefixes) for v in Collection(graph, graph.value(root, PROJECTION))]
            lines.append(f"SELECT {modifier}{' '.join(items)}")
    elif keyword == "CONSTRUCT":
        template_list = graph.value(root, TEMPLATE)
        template_nodes = list(Collection(graph, template_list)) if template_list is not None else []
        template_text = " . ".join(_triple_pattern_text(n, graph, prefixes) for n in template_nodes)
        lines.append(f"CONSTRUCT {{ {template_text} }}")
    else:  # ASK
        lines.append("ASK")

    lines.append(f"WHERE {_where_group_text(graph.value(root, WHERE), graph, prefixes)}")
    lines.extend(_solution_modifier_lines(graph, root, prefixes))
    values_node = graph.value(root, QUERY_VALUES)
    if values_node is not None:
        lines.append(_values_text(values_node, graph, prefixes))
    return lines


def _values_text(node, graph: Graph, prefixes: dict) -> str:
    variables = ["?" + str(v) for v in Collection(graph, graph.value(node, VALUES_VARS))]
    rows = []
    for row_node in Collection(graph, graph.value(node, VALUES_ROWS)):
        cells = ["UNDEF" if cell == VALUES_UNDEF else expr_text(cell, graph, prefixes) for cell in Collection(graph, row_node)]
        rows.append(cells[0] if len(variables) == 1 else "(" + " ".join(cells) + ")")
    head = variables[0] if len(variables) == 1 else "(" + " ".join(variables) + ")"
    return f"VALUES {head} {{ {' '.join(rows)} }}"


def _alias_or_var_text(item, graph: Graph, prefixes: dict) -> str:
    if (item, RDF.type, ALIAS) in graph:
        return f"({expr_text(graph.value(item, EXPR), graph, prefixes)} AS ?{graph.value(item, BIND_VAR)})"
    if isinstance(item, Literal):
        return "?" + str(item)
    return f"({expr_text(item, graph, prefixes)})"


def _solution_modifier_lines(graph: Graph, root, prefixes: dict) -> list:
    lines = []
    group_list = graph.value(root, GROUP_BY)
    if group_list is not None:
        lines.append("GROUP BY " + " ".join(_alias_or_var_text(i, graph, prefixes) for i in Collection(graph, group_list)))
    having_list = graph.value(root, HAVING)
    if having_list is not None:
        lines.append("HAVING " + " ".join(f"({expr_text(c, graph, prefixes)})" for c in Collection(graph, having_list)))
    order_list = graph.value(root, ORDER_BY)
    if order_list is not None:
        parts = []
        for node in Collection(graph, order_list):
            expr_node = graph.value(node, EXPR)
            text = expr_text(expr_node, graph, prefixes)
            if graph.value(node, ORDER_DESCENDING) is not None:
                parts.append(f"DESC({text})")
            elif isinstance(expr_node, Literal):
                parts.append(text)
            else:
                parts.append(f"ASC({text})")
        lines.append("ORDER BY " + " ".join(parts))
    limit, offset = graph.value(root, LIMIT), graph.value(root, OFFSET)
    if limit is not None:
        lines.append(f"LIMIT {int(limit)}")
    if offset is not None:
        lines.append(f"OFFSET {int(offset)}")
    return lines


def _keyword_for_root(graph: Graph, root) -> str:
    for root_type, keyword in _KEYWORD_BY_ROOT_TYPE.items():
        if (root, RDF.type, root_type) in graph:
            return keyword
    raise NotImplementedError(f"starlayer.sparql.sqe: {root!r} has no recognized sqe: query-form type")


def _prefix_map(graph: Graph, root) -> dict:
    prefixes = {}
    for binding in graph.objects(root, PROLOGUE_PREFIX):
        label = str(graph.value(binding, PREFIX_LABEL))
        namespace = str(graph.value(binding, PREFIX_NAMESPACE))
        prefixes[label] = namespace
    return prefixes


def _where_group_text(list_node, graph: Graph, prefixes: dict) -> str:
    nodes = list(Collection(graph, list_node)) if list_node is not None else []
    parts = [_where_element_text(node, graph, prefixes) for node in nodes]
    return "{ " + " ".join(parts) + " }"


def _where_element_text(node, graph: Graph, prefixes: dict) -> str:
    if (node, RDF.type, TRIPLE_PATTERN) in graph:
        return _triple_pattern_text(node, graph, prefixes) + " ."
    if (node, RDF.type, OPTIONAL) in graph:
        inner = _where_group_text(graph.value(node, WHERE), graph, prefixes)
        return f"OPTIONAL {inner}"
    if (node, RDF.type, FILTER) in graph:
        return f"FILTER({expr_text(graph.value(node, EXPR), graph, prefixes)})"
    if (node, RDF.type, BIND) in graph:
        var = str(graph.value(node, BIND_VAR))
        return f"BIND({expr_text(graph.value(node, EXPR), graph, prefixes)} AS ?{var})"
    if (node, RDF.type, MINUS) in graph:
        return f"MINUS {_where_group_text(graph.value(node, WHERE), graph, prefixes)}"
    if (node, RDF.type, GRAPH_PATTERN) in graph:
        term = expr_text(graph.value(node, GRAPH_TERM), graph, prefixes)
        return f"GRAPH {term} {_where_group_text(graph.value(node, WHERE), graph, prefixes)}"
    if (node, RDF.type, VALUES) in graph:
        return _values_text(node, graph, prefixes)
    if (node, RDF.type, SUB_SELECT) in graph:
        return "{ " + " ".join(_query_lines(graph, node, prefixes)) + " }"
    if (node, RDF.type, UNION) in graph:
        alt_list = graph.value(node, UNION_ALTERNATIVES)
        alts = [_where_group_text(alt, graph, prefixes) for alt in Collection(graph, alt_list)]
        return " UNION ".join(alts)
    raise NotImplementedError(
        f"starlayer.sparql.sqe: cannot render WHERE-clause element {node!r} - "
        "not a recognized sqe: node type"
    )


def _triple_pattern_text(node, graph: Graph, prefixes: dict) -> str:
    s = _term_text(graph.value(node, TRIPLE_PATTERN_SUBJECT), prefixes, graph)
    p = _predicate_text(graph.value(node, TRIPLE_PATTERN_PREDICATE), graph, prefixes)
    o = _term_text(graph.value(node, TRIPLE_PATTERN_OBJECT), prefixes, graph)
    return f"{s} {p} {o}"


def _predicate_text(node, graph: Graph, prefixes: dict) -> str:
    """A predicate position may be a genuine property path (encoded via
    the existing ``salg:`` path vocabulary, a nested `BNode` structure -
    see ``to_rdf.py``'s own ``_encode_predicate``), not just a plain term
    - decode it first (``..from_rdf._decode`` already reconstructs a real
    ``rdflib.paths.Path`` for one) and render via `Path.n3()`, which
    already understands a `NamespaceManager`'s prefix bindings, rather
    than falling through `_term_text`'s generic `BNode` branch (which
    would render the path's own internal encoding node, not the path)."""
    from rdflib.paths import Path

    decoded = _decode(node, graph)
    if isinstance(decoded, Path):
        return decoded.n3(_namespace_manager_for(prefixes))
    return _term_text(node, prefixes)


def _term_text(value, prefixes: dict, graph: Graph | None = None) -> str:
    if graph is not None and (value, RDF.type, TRIPLE_TERM) in graph:
        return "<<( " + _triple_pattern_text(value, graph, prefixes) + " )>>"
    if isinstance(value, Literal) and value.datatype == VARIABLE_DATATYPE:
        return "?" + str(value)
    if isinstance(value, URIRef):
        return _abbreviate(str(value), prefixes)
    if isinstance(value, Literal):
        return _literal_text(value)
    if isinstance(value, BNode):
        return value.n3()
    raise NotImplementedError(f"starlayer.sparql.sqe: cannot render term {value!r} as text")


def _literal_text(value: Literal) -> str:
    """A literal as query text: a base-direction string back in ``"x"@en--ltr`` form (it is stored with an internal
    datatype) and control characters escaped, as ``\\r`` and ``\\n`` already are."""
    from ..serialize12 import _dirlang_n3

    dirlang = _dirlang_n3(value)
    if dirlang is not None:
        return dirlang
    return value.n3().replace("\t", "\\t")


def _namespace_manager_for(prefixes: dict):
    from rdflib.namespace import NamespaceManager

    nm = NamespaceManager(Graph(), bind_namespaces="none")
    for label, namespace in prefixes.items():
        nm.bind(label, namespace)
    return nm


def _abbreviate(iri: str, prefixes: dict) -> str:
    from ...graph.serializers.turtle12 import _PN_LOCAL

    for label, namespace in prefixes.items():
        if iri.startswith(namespace) and iri != namespace:
            local = iri[len(namespace):]
            # SPARQL's PN_LOCAL, like Turtle's, has no '/' or '#': such an IRI is written in full (GitHub issue #81)
            if _PN_LOCAL.fullmatch(local):
                return f"{label}:{local}"
    return f"<{iri}>"
