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
    ADD,
    ALIAS,
    ALL_GRAPHS,
    ASK_QUERY,
    BIND,
    BIND_VAR,
    CLEAR,
    CONSTRUCT_QUERY,
    COPY,
    CREATE,
    DATASET,
    DATASET_NAMED,
    DATASET_SOURCE,
    DEFAULT_GRAPH,
    DELETE_DATA,
    DELETE_WHERE,
    DESCRIBE,
    DESCRIBE_ALL,
    DESCRIBE_QUERY,
    DISTINCT,
    DROP,
    EXPR,
    FILTER,
    GRAPH_PATTERN,
    GRAPH_REF,
    GRAPH_REF_IRI,
    GRAPH_TARGET,
    GRAPH_TERM,
    GROUP_BY,
    HAVING,
    INSERT_DATA,
    LIMIT,
    LOAD,
    LOAD_FROM,
    LOAD_INTO,
    MINUS,
    MODIFY,
    MODIFY_DELETE,
    MODIFY_INSERT,
    MODIFY_USING,
    MODIFY_WITH,
    MOVE,
    NAMED_GRAPHS,
    OFFSET,
    OPERATIONS,
    OPTIONAL,
    ORDER_BY,
    ORDER_DESCENDING,
    PREFIX_LABEL,
    PREFIX_NAMESPACE,
    PROJECTION,
    PROLOGUE_BASE,
    PROLOGUE_PREFIX,
    QUAD_GRAPH,
    QUAD_GRAPH_NAME,
    QUAD_TRIPLES,
    QUADS,
    QUERY_VALUES,
    REDUCED,
    SELECT_ALL,
    SELECT_QUERY,
    SERVICE,
    SERVICE_SILENT,
    SERVICE_TERM,
    SUB_SELECT,
    TEMPLATE,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    TRIPLE_TERM,
    UNION,
    UNION_ALTERNATIVES,
    UPDATE_FROM,
    UPDATE_REQUEST,
    UPDATE_TO,
    VALUES,
    VALUES_ROWS,
    VALUES_UNDEF,
    VALUES_VARS,
    VERSION,
    WHERE,
)

_KEYWORD_BY_ROOT_TYPE = {
    SELECT_QUERY: "SELECT",
    ASK_QUERY: "ASK",
    CONSTRUCT_QUERY: "CONSTRUCT",
    DESCRIBE_QUERY: "DESCRIBE",
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
    if (root, RDF.type, UPDATE_REQUEST) in graph:
        return _update_text(graph, root)
    prefixes = _prefix_map(graph, root)
    lines = [f'VERSION "{_escape_string(str(v))}"' for v in sorted(graph.objects(root, VERSION), key=str)]
    lines += [f"PREFIX {label}: <{ns}>" for label, ns in sorted(prefixes.items())]

    base = graph.value(root, PROLOGUE_BASE)
    if base is not None:
        lines.append(f"BASE <{base}>")

    lines.extend(_query_lines(graph, root, prefixes))
    return "\n".join(lines)


def _prologue_lines(graph: Graph, node, prefixes: dict) -> list:
    """The ``VERSION``, ``PREFIX`` and ``BASE`` declarations stored on ``node`` (``prefixes``: the ones it declares)."""
    lines = [f'VERSION "{_escape_string(str(v))}"' for v in sorted(graph.objects(node, VERSION), key=str)]
    lines += [f"PREFIX {label}: <{ns}>" for label, ns in sorted(prefixes.items())]
    base = graph.value(node, PROLOGUE_BASE)
    if base is not None:
        lines.append(f"BASE <{base}>")
    return lines


def _update_text(graph: Graph, root) -> str:
    """Render an ``sqe:UpdateRequest``: the operations in order, separated by `` ;``. Each operation writes the prologue
    it carries; the prefixes declared by earlier operations stay in force for the terms of later ones."""
    in_force: dict = {}
    chunks: list = []
    for op in Collection(graph, graph.value(root, OPERATIONS)):
        own = _prefix_map(graph, op)
        in_force.update(own)
        chunks.append("\n".join([*_prologue_lines(graph, op, own), _operation_text(graph, op, in_force)]))
    own = _prefix_map(graph, root)
    trailing = _prologue_lines(graph, root, own)
    text = " ;\n".join(chunks)
    if trailing:
        text += (" ;\n" if chunks else "") + "\n".join(trailing)
    return text


def _graph_ref_text(node, graph: Graph, prefixes: dict) -> str:
    if (node, RDF.type, GRAPH_REF) in graph:
        return "GRAPH " + _term_text(graph.value(node, GRAPH_REF_IRI), prefixes)
    for kind, word in ((DEFAULT_GRAPH, "DEFAULT"), (NAMED_GRAPHS, "NAMED"), (ALL_GRAPHS, "ALL")):
        if (node, RDF.type, kind) in graph:
            return word
    raise NotImplementedError(f"starlayer.sparql.sqe: {node!r} is not a recognized graph reference")


def _quads_text(list_node, graph: Graph, prefixes: dict) -> str:
    parts = []
    for item in Collection(graph, list_node) if list_node is not None else []:
        if (item, RDF.type, QUAD_GRAPH) in graph:
            name = _term_text(graph.value(item, QUAD_GRAPH_NAME), prefixes)
            triples = [_triple_pattern_text(t, graph, prefixes) + " ." for t in Collection(graph, graph.value(item, QUAD_TRIPLES))]
            parts.append(f"GRAPH {name} {{ {' '.join(triples)} }}" if triples else f"GRAPH {name} {{ }}")
        else:
            parts.append(_triple_pattern_text(item, graph, prefixes) + " .")
    return "{ " + " ".join(parts) + " }" if parts else "{ }"


def _operation_text(graph: Graph, op, prefixes: dict) -> str:
    silent = " SILENT" if graph.value(op, SERVICE_SILENT) is not None else ""
    ref = lambda p: _graph_ref_text(graph.value(op, p), graph, prefixes)  # noqa: E731
    if (op, RDF.type, INSERT_DATA) in graph:
        return "INSERT DATA " + _quads_text(graph.value(op, QUADS), graph, prefixes)
    if (op, RDF.type, DELETE_DATA) in graph:
        return "DELETE DATA " + _quads_text(graph.value(op, QUADS), graph, prefixes)
    if (op, RDF.type, DELETE_WHERE) in graph:
        return "DELETE WHERE " + _quads_text(graph.value(op, QUADS), graph, prefixes)
    if (op, RDF.type, MODIFY) in graph:
        lines = []
        with_ = graph.value(op, MODIFY_WITH)
        if with_ is not None:
            lines.append("WITH " + _term_text(with_, prefixes))
        for pred, word in ((MODIFY_DELETE, "DELETE"), (MODIFY_INSERT, "INSERT")):
            if (op, pred, None) in graph:
                lines.append(f"{word} " + _quads_text(graph.value(op, pred), graph, prefixes))
        using = graph.value(op, MODIFY_USING)
        for clause in Collection(graph, using) if using is not None else []:
            named = "NAMED " if graph.value(clause, DATASET_NAMED) is not None else ""
            lines.append(f"USING {named}{_term_text(graph.value(clause, DATASET_SOURCE), prefixes)}")
        lines.append(f"WHERE {_where_group_text(graph.value(op, WHERE), graph, prefixes)}")
        return "\n".join(lines)
    if (op, RDF.type, LOAD) in graph:
        into = graph.value(op, LOAD_INTO)
        tail = f" INTO {_graph_ref_text(into, graph, prefixes)}" if into is not None else ""
        return f"LOAD{silent} {_term_text(graph.value(op, LOAD_FROM), prefixes)}{tail}"
    if (op, RDF.type, CLEAR) in graph:
        return f"CLEAR{silent} {ref(GRAPH_TARGET)}"
    if (op, RDF.type, DROP) in graph:
        return f"DROP{silent} {ref(GRAPH_TARGET)}"
    if (op, RDF.type, CREATE) in graph:
        return f"CREATE{silent} {ref(GRAPH_TARGET)}"
    for kind, word in ((ADD, "ADD"), (MOVE, "MOVE"), (COPY, "COPY")):
        if (op, RDF.type, kind) in graph:
            return f"{word}{silent} {ref(UPDATE_FROM)} TO {ref(UPDATE_TO)}"
    raise NotImplementedError(f"starlayer.sparql.sqe: {op!r} is not a recognized update operation")


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
    elif keyword == "DESCRIBE":
        if graph.value(root, DESCRIBE_ALL) is not None:
            lines.append("DESCRIBE *")
        else:
            targets = [_term_text(t, prefixes) for t in Collection(graph, graph.value(root, DESCRIBE))]
            lines.append("DESCRIBE " + " ".join(targets))
    else:  # ASK
        lines.append("ASK")

    dataset = graph.value(root, DATASET)
    if dataset is not None:
        for clause in Collection(graph, dataset):
            named = "NAMED " if graph.value(clause, DATASET_NAMED) is not None else ""
            lines.append(f"FROM {named}{_term_text(graph.value(clause, DATASET_SOURCE), prefixes)}")

    where = graph.value(root, WHERE)
    if where is not None or keyword != "DESCRIBE":
        lines.append(f"WHERE {_where_group_text(where, graph, prefixes)}")
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


def _escape_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


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
    if (node, RDF.type, SERVICE) in graph:
        silent = "SILENT " if graph.value(node, SERVICE_SILENT) is not None else ""
        term = _term_text(graph.value(node, SERVICE_TERM), prefixes)
        return f"SERVICE {silent}{term} {_where_group_text(graph.value(node, WHERE), graph, prefixes)}"
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
        return _path_text(decoded, _namespace_manager_for(prefixes))
    return _term_text(node, prefixes)


def _is_multi(path) -> bool:
    from rdflib.paths import AlternativePath, SequencePath

    return isinstance(path, (SequencePath, AlternativePath)) and len(path.args) > 1


def _path_text(path, nm) -> str:
    """`Path.n3()` with the parentheses SPARQL needs: a path element takes
    one modifier (grammar [91]), so a modified or inverse path under a
    modifier, and an inverse under an inverse, is parenthesised (rdflib
    writes ``p*?`` and ``^^p``, which do not parse or mean something else)."""
    from rdflib.paths import AlternativePath, InvPath, MulPath, SequencePath

    if isinstance(path, MulPath):
        inner = _path_text(path.path, nm)
        if isinstance(path.path, (MulPath, InvPath)) or _is_multi(path.path):
            inner = f"({inner})"
        return f"{inner}{path.mod}"
    if isinstance(path, InvPath):
        inner = _path_text(path.arg, nm)
        if isinstance(path.arg, InvPath) or _is_multi(path.arg):
            inner = f"({inner})"
        return f"^{inner}"
    if isinstance(path, (SequencePath, AlternativePath)):
        sep = "/" if isinstance(path, SequencePath) else "|"
        parts = []
        for arg in path.args:
            text = _path_text(arg, nm)
            if _is_multi(arg):
                text = f"({text})"
            parts.append(text)
        return sep.join(parts)
    return path.n3(nm)


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
