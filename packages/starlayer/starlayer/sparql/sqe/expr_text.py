"""Render an sqe expression (any node reachable from ``sqe:expr``) to SPARQL
text, working straight from the RDF tree.

Replaces the earlier route through rdflib's ``translateAlgebra`` placeholder
translator, which has no rendering for aggregates, EXISTS bodies, the SPARQL 1.2
builtins or unary operators, and cannot print an sqe where-list at all.
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF

from ..serialize12 import _dirlang_n3
from ..vocab import PY_STR_DATATYPE, VARIABLE_DATATYPE
from .vocab import NEGATED, TRIPLE_TERM, WHERE

_COMPOUND = {
    "ConditionalOrExpression",
    "ConditionalAndExpression",
    "RelationalExpression",
    "AdditiveExpression",
    "MultiplicativeExpression",
    "UnaryNot",
    "UnaryMinus",
    "UnaryPlus",
}

_ZERO_ARG = {"NOW", "UUID", "STRUUID", "RAND"}
_TWO_ARG = {"STRSTARTS", "STRENDS", "CONTAINS", "STRBEFORE", "STRAFTER", "STRLANG", "STRDT", "sameTerm", "LANGMATCHES"}
_LIST_ARG = {"CONCAT", "COALESCE"}
_AGGREGATES = {
    "Count": "COUNT",
    "Sum": "SUM",
    "Min": "MIN",
    "Max": "MAX",
    "Avg": "AVG",
    "Sample": "SAMPLE",
    "GroupConcat": "GROUP_CONCAT",
}


def _local(uri) -> str:
    s = str(uri)
    for sep in ("#", "/"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s


def _props(node, graph) -> dict:
    """The node's properties keyed by predicate local name (rdf:type excluded)."""
    return {_local(p): o for p, o in graph.predicate_objects(node) if p != RDF.type}


def _type_names(node, graph) -> set:
    return {_local(t) for t in graph.objects(node, RDF.type)}


def _list_items(node, graph) -> list:
    if node is None or node == RDF.nil:
        return []
    return list(Collection(graph, node))


def _is_plain_string(value) -> bool:
    return isinstance(value, Literal) and value.datatype == PY_STR_DATATYPE


def _abbreviate(iri: str, prefixes: dict) -> str:
    for label, namespace in prefixes.items():
        if iri.startswith(namespace) and iri != namespace:
            local = iri[len(namespace):]
            if local and all(c.isalnum() or c in "_-" for c in local):
                return f"{label}:{local}"
    return f"<{iri}>"


def term_text(node, graph, prefixes: dict) -> str:
    """A pattern/expression term: variable, IRI, literal, blank node or triple term."""
    return expr_text(node, graph, prefixes)


def _wrapped(node, graph, prefixes) -> str:
    text = expr_text(node, graph, prefixes)
    if isinstance(node, BNode) and _type_names(node, graph) & _COMPOUND:
        return f"({text})"
    return text


def _call(name: str, args: list) -> str:
    return f"{name}({', '.join(a for a in args if a is not None)})"


def expr_text(node, graph, prefixes: dict | None = None) -> str:
    """The SPARQL text of the expression (or term) rooted at ``node``."""
    prefixes = prefixes or {}
    if isinstance(node, Literal):
        if node.datatype == VARIABLE_DATATYPE:
            return "?" + str(node)
        if _is_plain_string(node):
            return str(node)
        dirlang = _dirlang_n3(node)
        if dirlang:
            return dirlang
        datatype = str(node.datatype) if node.datatype else ""
        lexical = str(node)
        if datatype.endswith("#integer") and lexical.lstrip("+-").isdigit():
            return lexical
        if datatype.endswith("#boolean") and lexical in ("true", "false"):
            return lexical
        if datatype.endswith("#decimal") and "." in lexical and lexical.replace(".", "", 1).lstrip("+-").isdigit():
            return lexical
        return node.n3()
    if isinstance(node, URIRef):
        return _abbreviate(str(node), prefixes)
    if not isinstance(node, BNode):
        raise NotImplementedError(f"sqe: cannot render expression node {node!r}")

    props = _props(node, graph)
    names = _type_names(node, graph)

    def sub(key):
        return _wrapped(props[key], graph, prefixes)

    def opt(key):
        return sub(key) if key in props else None

    if (node, RDF.type, TRIPLE_TERM) in graph:
        parts = [expr_text(props[k], graph, prefixes) for k in ("subject", "predicate", "object")]
        computed = any(
            isinstance(props[k], BNode) and _type_names(props[k], graph) - {"Resource", "TripleTerm"}
            for k in ("subject", "predicate", "object")
        )
        if computed:  # a component is an expression, so this is the TRIPLE() function, not a literal term
            return "TRIPLE(" + ", ".join(parts) + ")"
        return "<<( " + " ".join(parts) + " )>>"

    if "Exists" in names:
        from .to_text import _where_group_text

        keyword = "NOT EXISTS" if (node, NEGATED, None) in graph else "EXISTS"
        return f"{keyword} {_where_group_text(graph.value(node, WHERE), graph, prefixes)}"

    # a blank node used directly as a term (no recognized expression type)
    if not names or names <= {"Resource"}:
        return node.n3()

    if "ConditionalOrExpression" in names or "ConditionalAndExpression" in names:
        joiner = " || " if "ConditionalOrExpression" in names else " && "
        return joiner.join([sub("expr")] + [_wrapped(o, graph, prefixes) for o in _list_items(props.get("other"), graph)])
    if "RelationalExpression" in names:
        op = str(props["op"])
        if op in ("IN", "NOT IN"):
            right = "(" + ", ".join(expr_text(o, graph, prefixes) for o in _list_items(props.get("other"), graph)) + ")"
        else:
            right = sub("other")
        return f"{sub('expr')} {op} {right}"
    if "AdditiveExpression" in names or "MultiplicativeExpression" in names:
        text = sub("expr")
        ops = _list_items(props.get("op"), graph)
        others = _list_items(props.get("other"), graph)
        for op, other in zip(ops, others, strict=False):
            text += f" {op} {_wrapped(other, graph, prefixes)}"
        return text
    if "UnaryNot" in names:
        return "!" + sub("expr")
    if "UnaryMinus" in names:
        return "-" + sub("expr")
    if "UnaryPlus" in names:
        return "+" + sub("expr")

    if "Function" in names:
        distinct = "DISTINCT " if "distinct" in props and _is_plain_string(props["distinct"]) else ""
        args = ", ".join(expr_text(a, graph, prefixes) for a in _list_items(props.get("expr"), graph))
        return f"{_abbreviate(str(props['iri']), prefixes)}({distinct}{args})"

    for name in names:
        if name.startswith("Aggregate_"):
            keyword = _AGGREGATES[name[len("Aggregate_"):]]
            distinct = "DISTINCT " if "distinct" in props and _is_plain_string(props["distinct"]) else ""
            inner = expr_text(props["vars"], graph, prefixes)
            separator = ""
            if "separator" in props:
                separator = f"; SEPARATOR={props['separator'].n3()}"
            return f"{keyword}({distinct}{inner}{separator})"

    for name in names:
        if not name.startswith("Builtin_"):
            continue
        base = name[len("Builtin_"):]
        if base == "NOTEXISTS" or base == "EXISTS":
            raise NotImplementedError("sqe: EXISTS must be an sqe:Exists node")  # pragma: no cover
        if base in _ZERO_ARG:
            return f"{base}()"
        if base == "BNODE":
            return _call("BNODE", [opt("arg")])
        if base in _LIST_ARG:
            return _call(base, [expr_text(a, graph, prefixes) for a in _list_items(props.get("arg"), graph)])
        if base in _TWO_ARG:
            return _call(base, [sub("arg1"), sub("arg2")])
        if base == "IF":
            return _call("IF", [sub("arg1"), sub("arg2"), sub("arg3")])
        if base == "REGEX":
            return _call("REGEX", [sub("text"), sub("pattern"), opt("flags")])
        if base == "REPLACE":
            return _call("REPLACE", [sub("arg"), sub("pattern"), sub("replacement"), opt("flags")])
        if base == "SUBSTR":
            return _call("SUBSTR", [sub("arg"), sub("start"), opt("length")])
        if base == "STRLANGDIR":
            return _call("STRLANGDIR", [sub("lex"), sub("lang"), sub("direction")])
        return _call(base, [sub("arg")])

    raise NotImplementedError(f"sqe: cannot render expression node of type {sorted(names)}")
