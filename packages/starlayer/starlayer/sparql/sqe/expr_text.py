"""Render an sqe expression (any node reachable from ``sqe:expr``) to SPARQL
text, working straight from the RDF tree.

The tree is read through the graph methods ``predicate_objects``, ``objects``, ``value``, ``items`` and ``in``, so the graph is
a ``StarLayerGraph`` or a ``TreeIndex``; terms are pyoxigraph terms. The earlier route through rdflib's ``translateAlgebra``
had no rendering for aggregates, EXISTS bodies, the SPARQL 1.2 builtins or unary operators.
"""

from __future__ import annotations

import pyoxigraph as ox

from .. import _oxterms as T
from .._oxterms import RDF
from ..vocab import PY_STR_DATATYPE, VARIABLE_DATATYPE
from .vocab import NEGATED, TRIPLE_TERM, WHERE
from .vocab import TRIPLE_PATTERN_OBJECT as SQE_OBJECT
from .vocab import TRIPLE_PATTERN_PREDICATE as SQE_PREDICATE
from .vocab import TRIPLE_PATTERN_SUBJECT as SQE_SUBJECT

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
    s = uri.value
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
    return list(graph.items(node))


def _is_plain_string(value) -> bool:
    return isinstance(value, ox.Literal) and value.datatype == PY_STR_DATATYPE


def _abbreviate(iri: str, prefixes: dict) -> str:
    from ...graph.oxgraph.pretty import _PN_LOCAL

    for label, namespace in prefixes.items():
        if iri.startswith(namespace) and iri != namespace:
            local = iri[len(namespace):]
            # SPARQL's PN_LOCAL, like Turtle's, has no '/' or '#': such an IRI is written in full (GitHub issue #81)
            if _PN_LOCAL.fullmatch(local):
                return f"{label}:{local}"
    return f"<{iri}>"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _literal_text(value: ox.Literal) -> str:
    """A literal as query text: ``"x"``, ``"x"@en``, ``"x"@en--ltr`` or ``"x"^^<datatype>``."""
    quoted = f'"{_escape(value.value)}"'
    tag = T.language_of(value)
    if tag is not None:
        return f"{quoted}@{tag}"
    if value.datatype == T.XSD.string:
        return quoted
    return f"{quoted}^^<{T.iri_text(value.datatype)}>"


def _is_literal_triple_term(node, graph) -> bool:
    """True when the triple-term node can be written as ``<<( s p o )>>`` in an expression: the subject a variable or
    IRI, the predicate a variable or IRI, the object a variable, IRI, literal or (recursively) such a triple term."""

    def simple(term) -> bool:
        return isinstance(term, ox.NamedNode) or (isinstance(term, ox.Literal) and term.datatype == VARIABLE_DATATYPE)

    def ok(n) -> bool:
        s, p, o = (graph.value(n, v) for v in (SQE_SUBJECT, SQE_PREDICATE, SQE_OBJECT))
        if not (simple(s) and simple(p)):
            return False
        if isinstance(o, (ox.Literal, ox.NamedNode)):
            return True
        return isinstance(o, ox.BlankNode) and (o, RDF.type, TRIPLE_TERM) in graph and ok(o)

    return ok(node)


def term_text(node, graph, prefixes: dict) -> str:
    """A pattern/expression term: variable, IRI, literal, blank node or triple term."""
    return expr_text(node, graph, prefixes)


def _wrapped(node, graph, prefixes) -> str:
    text = expr_text(node, graph, prefixes)
    if isinstance(node, ox.BlankNode) and _type_names(node, graph) & _COMPOUND:
        return f"({text})"
    return text


def _call(name: str, args: list) -> str:
    return f"{name}({', '.join(a for a in args if a is not None)})"


def expr_text(node, graph, prefixes: dict | None = None) -> str:
    """The SPARQL text of the expression (or term) rooted at ``node``."""
    prefixes = prefixes or {}
    if isinstance(node, ox.Literal):
        if node.datatype == VARIABLE_DATATYPE:
            return "?" + node.value
        if _is_plain_string(node):
            return node.value
        if T.language_of(node) is not None:
            return _literal_text(node)
        datatype = node.datatype.value
        lexical = node.value
        if datatype.endswith("#integer") and lexical.lstrip("+-").isdigit():
            return lexical
        if datatype.endswith("#boolean") and lexical in ("true", "false"):
            return lexical
        if datatype.endswith("#decimal") and "." in lexical and lexical.replace(".", "", 1).lstrip("+-").isdigit():
            return lexical
        return _literal_text(node)
    if isinstance(node, ox.NamedNode):
        return _abbreviate(T.iri_text(node), prefixes)
    if not isinstance(node, ox.BlankNode):
        raise NotImplementedError(f"sqe: cannot render expression node {node!r}")

    props = _props(node, graph)
    names = _type_names(node, graph)

    def sub(key):
        return _wrapped(props[key], graph, prefixes)

    def opt(key):
        return sub(key) if key in props else None

    if (node, RDF.type, TRIPLE_TERM) in graph:
        parts = [expr_text(props[k], graph, prefixes) for k in ("subject", "predicate", "object")]
        computed = not _is_literal_triple_term(node, graph)
        # TRIPLE() takes arbitrary expressions; the tree node is the same as for a literal term, so the renderer picks
        # the literal form only when every component is writable in it (ExprTripleTerm: no literal subject or
        # predicate, no nested triple term as subject)
        if computed:
            return "TRIPLE(" + ", ".join(parts) + ")"
        return "<<( " + " ".join(parts) + " )>>"

    if "Exists" in names:
        from .to_text import _where_group_text

        keyword = "NOT EXISTS" if (node, NEGATED, None) in graph else "EXISTS"
        return f"{keyword} {_where_group_text(graph.value(node, WHERE), graph, prefixes)}"

    # a blank node used directly as a term (no recognized expression type)
    if not names or names <= {"Resource"}:
        return "_:" + T.bnode_label(node)

    if "ConditionalOrExpression" in names or "ConditionalAndExpression" in names:
        joiner = " || " if "ConditionalOrExpression" in names else " && "
        return joiner.join([sub("expr")] + [_wrapped(o, graph, prefixes) for o in _list_items(props.get("other"), graph)])
    if "RelationalExpression" in names:
        op = props["op"].value
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
            text += f" {op.value} {_wrapped(other, graph, prefixes)}"
        return text
    if "UnaryNot" in names:
        # '!' takes a UnaryExpression, so a chain '!!!x' needs no parentheses (they would double the nesting depth);
        # the chain is walked in a loop so its length costs no stack
        bangs, operand = "!", props["expr"]
        while isinstance(operand, ox.BlankNode) and "UnaryNot" in _type_names(operand, graph):
            bangs += "!"
            operand = _props(operand, graph)["expr"]
        if isinstance(operand, ox.BlankNode) and _type_names(operand, graph) & {"UnaryMinus", "UnaryPlus"}:
            return bangs + expr_text(operand, graph, prefixes)
        return bangs + _wrapped(operand, graph, prefixes)
    if "UnaryMinus" in names:
        return "-" + sub("expr")
    if "UnaryPlus" in names:
        return "+" + sub("expr")

    if "Function" in names:
        distinct = "DISTINCT " if "distinct" in props and _is_plain_string(props["distinct"]) else ""
        args = ", ".join(expr_text(a, graph, prefixes) for a in _list_items(props.get("expr"), graph))
        return f"{_abbreviate(T.iri_text(props['iri']), prefixes)}({distinct}{args})"

    for name in names:
        if name.startswith("Aggregate_"):
            keyword = _AGGREGATES[name[len("Aggregate_"):]]
            distinct = "DISTINCT " if "distinct" in props and _is_plain_string(props["distinct"]) else ""
            inner = expr_text(props["vars"], graph, prefixes)
            separator = ""
            if "separator" in props:
                separator = f"; SEPARATOR={_literal_text(props['separator'])}"
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
