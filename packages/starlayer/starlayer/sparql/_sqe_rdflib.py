"""The rdflib-term forms of two ``sqe:`` helpers that SRL (``srl.py``) still uses on its rdflib ``srl:`` trees: ``expr_text``
(an expression node to SPARQL text) and ``_encode_expr`` (an rdflib algebra expression to an ``sqe:``-typed expression node).
``sqe/expr_text.py`` and ``sqe/to_rdf.py`` are the pyoxigraph versions; delete this module when SRL moves to pyoxigraph terms.
``EXISTS`` has no meaning in an SRL rule, so it is not rendered here."""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF

from ._vocab_rdflib import PY_STR_DATATYPE, SPEXPR, VARIABLE_DATATYPE
from .serialize12 import _dirlang_n3
from .spexpr_codec import _NS_OVERRIDES
from .spexpr_codec import _encode as _encode_algebra
from .sqe._vocab_rdflib import SQE, TRIPLE_TERM
from .sqe._vocab_rdflib import TRIPLE_PATTERN_OBJECT as SQE_OBJECT
from .sqe._vocab_rdflib import TRIPLE_PATTERN_PREDICATE as SQE_PREDICATE
from .sqe._vocab_rdflib import TRIPLE_PATTERN_SUBJECT as SQE_SUBJECT

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
    from ..graph.oxgraph.pretty import _PN_LOCAL

    for label, namespace in prefixes.items():
        if iri.startswith(namespace) and iri != namespace:
            local = iri[len(namespace):]
            if _PN_LOCAL.fullmatch(local):
                return f"{label}:{local}"
    return f"<{iri}>"


def _is_literal_triple_term(node, graph) -> bool:
    """True when the triple-term node can be written as ``<<( s p o )>>`` in an expression: the subject a variable or
    IRI, the predicate a variable or IRI, the object a variable, IRI, literal or (recursively) such a triple term."""

    def simple(term) -> bool:
        return isinstance(term, URIRef) or (isinstance(term, Literal) and term.datatype == VARIABLE_DATATYPE)

    def ok(n) -> bool:
        s, p, o = (graph.value(n, v) for v in (SQE_SUBJECT, SQE_PREDICATE, SQE_OBJECT))
        if not (simple(s) and simple(p)):
            return False
        if isinstance(o, Literal) or isinstance(o, URIRef):
            return True
        return isinstance(o, BNode) and (o, RDF.type, TRIPLE_TERM) in graph and ok(o)

    return ok(node)


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
        computed = not _is_literal_triple_term(node, graph)
        # TRIPLE() takes arbitrary expressions; the tree node is the same as for a literal term, so the renderer picks
        # the literal form only when every component is writable in it (ExprTripleTerm: no literal subject or
        # predicate, no nested triple term as subject)
        if computed:
            return "TRIPLE(" + ", ".join(parts) + ")"
        return "<<( " + " ".join(parts) + " )>>"

    if "Exists" in names:
        raise NotImplementedError("EXISTS is not part of SRL")

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
        # '!' takes a UnaryExpression, so a chain '!!!x' needs no parentheses (they would double the nesting depth);
        # the chain is walked in a loop so its length costs no stack
        bangs, operand = "!", props["expr"]
        while isinstance(operand, BNode) and "UnaryNot" in _type_names(operand, graph):
            bangs += "!"
            operand = _props(operand, graph)["expr"]
        if isinstance(operand, BNode) and _type_names(operand, graph) & {"UnaryMinus", "UnaryPlus"}:
            return bangs + expr_text(operand, graph, prefixes)
        return bangs + _wrapped(operand, graph, prefixes)
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


_AGGREGATE_NAMES = (
    "Aggregate_Count", "Aggregate_Sum", "Aggregate_Min", "Aggregate_Max",
    "Aggregate_Avg", "Aggregate_Sample", "Aggregate_GroupConcat",
)


def _encode_expr(value, graph):
    """Encode an expression (or any term that may contain a triple term) with the shared encoder, typing triple terms,
    aggregates and EXISTS blocks with sqe:/spexpr: terms rather than salg: ones."""
    overrides = {"TripleTerm": SQE, **{name: SPEXPR for name in _AGGREGATE_NAMES}}
    ns_token = _NS_OVERRIDES.set(overrides)
    try:
        return _encode_algebra(value, graph)
    finally:
        _NS_OVERRIDES.reset(ns_token)
