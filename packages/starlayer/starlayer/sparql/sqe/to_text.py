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

Expression text reuses ``..ssyn_to_text._render_expr_text`` directly (the
same helper ``srl.py`` already depends on) - slated to move to a neutral,
shared location once the old ``ssyn:``/``sast:`` prototype layers are
retired, see `future_enhancements.md`. One known, accepted limitation
inherited from that reuse: an IRI literal *inside* an expression (e.g. a
bare ``IRI(<...>)`` builtin call) renders unprefixed, same as ``ssyn:``
already accepts - only term/predicate positions this module renders
directly get prefix-aware treatment.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF

from ..from_rdf import _decode
from ..ssyn_to_text import _render_expr_text
from ..vocab import SALG, VARIABLE_DATATYPE
from .vocab import (
    ASK_QUERY,
    BIND,
    BIND_VAR,
    CONSTRUCT_QUERY,
    EXPR,
    FILTER,
    OPTIONAL,
    PROJECTION,
    SELECT_QUERY,
    TEMPLATE,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    UNION,
    UNION_ALTERNATIVES,
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
    declarations preserved on ``root`` wherever one matches."""
    keyword = _keyword_for_root(graph, root)
    prefixes = _prefix_map(graph, root)
    lines = [f"PREFIX {label}: <{ns}>" for label, ns in sorted(prefixes.items())]

    base = graph.value(root, SALG.base)
    if base is not None:
        lines.append(f"BASE <{base}>")

    if keyword == "SELECT":
        var_names = [str(v) for v in Collection(graph, graph.value(root, PROJECTION))]
        lines.append(f"SELECT {' '.join('?' + v for v in var_names)}")
    elif keyword == "CONSTRUCT":
        template_list = graph.value(root, TEMPLATE)
        template_nodes = list(Collection(graph, template_list)) if template_list is not None else []
        template_text = " . ".join(_triple_pattern_text(n, graph, prefixes) for n in template_nodes)
        lines.append(f"CONSTRUCT {{ {template_text} }}")
    else:  # ASK
        lines.append("ASK")

    lines.append(f"WHERE {_where_group_text(graph.value(root, WHERE), graph, prefixes)}")
    return "\n".join(lines)


def _keyword_for_root(graph: Graph, root) -> str:
    for root_type, keyword in _KEYWORD_BY_ROOT_TYPE.items():
        if (root, RDF.type, root_type) in graph:
            return keyword
    raise NotImplementedError(f"starlayer.sparql.sqe: {root!r} has no recognized sqe: query-form type")


def _prefix_map(graph: Graph, root) -> dict:
    prefixes = {}
    for binding in graph.objects(root, SALG.prologuePrefix):
        label = str(graph.value(binding, SALG.prefixLabel))
        namespace = str(graph.value(binding, SALG.namespace))
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
        expr = _decode(graph.value(node, EXPR), graph)
        return f"FILTER({_render_expr_text(expr)})"
    if (node, RDF.type, BIND) in graph:
        expr = _decode(graph.value(node, EXPR), graph)
        var = str(_decode(graph.value(node, BIND_VAR), graph))
        return f"BIND({_render_expr_text(expr)} AS ?{var})"
    if (node, RDF.type, UNION) in graph:
        alt_list = graph.value(node, UNION_ALTERNATIVES)
        alts = [_where_group_text(alt, graph, prefixes) for alt in Collection(graph, alt_list)]
        return " UNION ".join(alts)
    raise NotImplementedError(
        f"starlayer.sparql.sqe: cannot render WHERE-clause element {node!r} - "
        "not a recognized sqe: node type"
    )


def _triple_pattern_text(node, graph: Graph, prefixes: dict) -> str:
    s = _term_text(graph.value(node, TRIPLE_PATTERN_SUBJECT), prefixes)
    p = _predicate_text(graph.value(node, TRIPLE_PATTERN_PREDICATE), graph, prefixes)
    o = _term_text(graph.value(node, TRIPLE_PATTERN_OBJECT), prefixes)
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


def _term_text(value, prefixes: dict) -> str:
    if isinstance(value, Literal) and value.datatype == VARIABLE_DATATYPE:
        return "?" + str(value)
    if isinstance(value, URIRef):
        return _abbreviate(str(value), prefixes)
    if isinstance(value, Literal):
        return value.n3()
    if isinstance(value, BNode):
        return value.n3()
    raise NotImplementedError(f"starlayer.sparql.sqe: cannot render term {value!r} as text")


def _namespace_manager_for(prefixes: dict):
    from rdflib.namespace import NamespaceManager

    nm = NamespaceManager(Graph(), bind_namespaces="none")
    for label, namespace in prefixes.items():
        nm.bind(label, namespace)
    return nm


def _abbreviate(iri: str, prefixes: dict) -> str:
    for label, namespace in prefixes.items():
        if iri.startswith(namespace) and iri != namespace:
            return f"{label}:{iri[len(namespace):]}"
    return f"<{iri}>"
