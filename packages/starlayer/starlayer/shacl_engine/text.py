"""Human-readable report text and run diagnostics for an engine run.

``report_text`` reproduces the layout the old ``ValidationResult.report_text`` carries (the pySHACL listing, which the old
validator then extended with a provenance appendix): the same header, the same per-result block, results sorted by their
block text, then the ``Provenance:`` appendix. Natively written: nothing here imports pyshacl or the old validator.

Everything here works on engine (pyoxigraph) terms; a graph is any engine-term graph (``StarLayerGraph``, an overlay), and its
prefixes are those it binds (``namespaces()``), when it has any.

Known differences from the old text: the default result messages are the engine's own wording (``Needs at least 1 value for
ex:p``), not pySHACL's (``Less than 1 values on ex:a->ex:p``); a SPARQL-based component names itself ``ConstraintComponent``
in pySHACL and by its own IRI local name here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

import pyoxigraph as ox

from starlayer.shacl_engine import terms as T
from starlayer.shacl_engine import xsd_values as xv
from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import Path
from starlayer.shacl_engine.terms import DCTERMS, RDF, SH

_MAX_DEPTH = 12


def _prefixes(graph: Any) -> dict[str, str]:
    try:
        return {prefix: ns for prefix, ns in graph.namespaces()}  # noqa: C416
    except (AttributeError, TypeError):
        return {}


def _n3(graph: Any, term: Any) -> str:
    """``term`` with the prefixes ``graph`` binds (an IRI none fits stays ``<iri>``)."""
    from starlayer.graph.oxgraph.helpers import qnames

    try:
        return qnames.n3(_prefixes(graph), term)
    except Exception:  # noqa: BLE001  (a rendering is never worth failing for)
        return T.n3(term)


def _predicates(graph: Any, node: Any) -> list[Any]:
    return list(dict.fromkeys(p for _s, p, _o in graph.triples((node, None, None))))


def _items(graph: Any, head: Any) -> list[Any]:
    out: list[Any] = []
    seen: set = set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = next(iter(graph.objects(head, RDF.first)), None)
        if first is None:
            break
        out.append(first)
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return out


def _python_value(node: ox.Literal) -> str | None:
    """The text of the Python value of a numeric or boolean literal (what ``Literal.value`` held in the old text), else ``None``."""
    value = xv.parse(node)
    if value is None or value.kind not in (xv.NUMERIC, xv.BOOLEAN):
        return None
    if isinstance(value.value, bool):
        return repr(value.value)
    try:
        return f"{value.value}"
    except ValueError:  # an integer over CPython's 4300-digit str limit: the report shows the lexical form only
        return None


def stringify_node(graph: Any, node: Any, depth: int = 0) -> str:
    """A node as text, in the form the old report text uses: prefixed names, ``Literal("x", lang=..., datatype=...)``,
    blank nodes as ``[ p o ; ... ]``, lists as ``( a b )``, triple terms as ``<<( s p o )>>``."""
    if isinstance(node, ox.Triple):
        return "<<( {} {} {} )>>".format(  # str-ok: stringify_node returns text
            *(stringify_node(graph, t, depth + 1) for t in (node.subject, node.predicate, node.object))
        )
    if isinstance(node, ox.Literal):
        return _literal(graph, node)
    if isinstance(node, ox.BlankNode):
        return _blank(graph, node, depth + 1)
    if isinstance(node, ox.NamedNode):
        return _n3(graph, node)
    return f"{node}"  # str-ok: a plain value (a Python str or number), not a term


def _literal(graph: Any, node: ox.Literal) -> str:
    lex = node.value
    value = _python_value(node)
    val = f'"{lex}" = {value}' if value is not None and value != lex else f'"{lex}"'  # str-ok: python value text
    lang = f", lang={node.language}" if node.language else ""
    plain = node.language is not None or node.datatype == T.XSD.string
    datatype = "" if plain else f", datatype={stringify_node(graph, node.datatype)}"
    return f"Literal({val}{lang}{datatype})"  # str-ok: rendered text


def _blank(graph: Any, node: ox.BlankNode, depth: int) -> str:
    if depth >= _MAX_DEPTH:
        return "<http://recursion.too.deep>"
    predicates = _predicates(graph, node)
    if not predicates:
        return "[ ]"
    if RDF.first in predicates:
        return "( {} )".format(" ".join(stringify_node(graph, i, depth + 1) for i in _items(graph, node)))
    rendered: dict[str, str] = {}
    for p in predicates:
        objs = list(graph.objects(node, p))
        if not objs:
            continue
        texts = ["<self>" if o == node else stringify_node(graph, o, depth + 1) for o in objs]
        rendered[_n3(graph, p)] = ", ".join(sorted(texts)) if len(texts) > 1 else texts[0]
    return "[ {} ]".format(" ; ".join(f"{p} {o}" for p, o in sorted(rendered.items())))  # str-ok: rendered text


def _params(shapes: Any, r: Result, predicate: Any) -> list[Any]:
    return list(shapes.objects(r.shape, predicate))


def _list_items(shapes: Any, head: Any) -> list[Any]:
    try:
        return _items(shapes, head)
    except Exception:  # noqa: BLE001
        return []


def _component_name(component: Any) -> str:
    return T.iri_text(component).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


_NODE_KINDS = {
    "IRI": "an IRI",
    "BlankNode": "a blank node",
    "Literal": "a literal",
    "BlankNodeOrIRI": "an IRI or a blank node",
    "IRIOrLiteral": "an IRI or a literal",
    "BlankNodeOrLiteral": "a blank node or a literal",
}
_RANGE_WORDS = {
    "MinExclusiveConstraintComponent": ("minExclusive", "greater than"),
    "MinInclusiveConstraintComponent": ("minInclusive", "at least"),
    "MaxExclusiveConstraintComponent": ("maxExclusive", "less than"),
    "MaxInclusiveConstraintComponent": ("maxInclusive", "at most"),
}
_PAIR_WORDS = {
    "EqualsConstraintComponent": (SH.equals, "should also be a value of {q}"),
    "DisjointConstraintComponent": (SH.disjoint, "should not also be a value of {q}"),
    "LessThanConstraintComponent": (SH.lessThan, "should be less than every value of {q}"),
    "LessThanOrEqualsConstraintComponent": (SH.lessThanOrEquals, "should be at most every value of {q}"),
}
_SHAPE_LISTS = {
    "AndConstraintComponent": ("and", "all of"),
    "OrConstraintComponent": ("or", "at least one of"),
    "XoneConstraintComponent": ("xone", "exactly one of"),
}


def plain_term(graph: Any, node: Any) -> str:
    """A term as a UI reads it: prefixed IRIs, a literal as its quoted text (bare for numbers and booleans, with its
    language tag or prefixed datatype otherwise), a blank node as ``_:label``."""
    if isinstance(node, ox.Literal):
        if node.language:
            return f'"{node.value}"@{node.language}'
        if node.datatype == T.XSD.string:
            return f'"{node.value}"'
        if isinstance(node.datatype, ox.NamedNode) and node.datatype.value.startswith(T._INVALID_LANG_PREFIX):  # lenient mode: a malformed tag
            return f'"{node.value}"@{unquote(node.datatype.value[len(T._INVALID_LANG_PREFIX):], errors="surrogatepass")}'  # str-ok: text
        if node.datatype in (T.XSD.integer, T.XSD.decimal, T.XSD.double, T.XSD.boolean):
            return node.value
        return f'"{node.value}"^^{_n3(graph, node.datatype)}'
    if isinstance(node, ox.BlankNode):
        return f"_:{node.value}"
    return stringify_node(graph, node)


def _count(n: Any, noun: str) -> str:
    """``1 value`` / ``2 values``: the singular only for exactly one."""
    text = (_python_value(n) if isinstance(n, ox.Literal) else None) or getattr(n, "value", f"{n}")  # str-ok: text
    return f"{text} {noun}" if text == "1" else f"{text} {noun}s"  # str-ok: text


def generic_message(r: Result, shapes: Any, data: Any) -> str | None:
    """The default result message for a constraint component of one parameter value, built from the result's structured
    fields (component, path, value) and the shape's parameter value, so it names the path, the offending value and the
    expected value or limit; ``None`` where the component's own message is kept. Conventions: ``shacl/CLAUDE.md``."""
    name = _component_name(r.component)
    sn = lambda node: plain_term(shapes, node)  # noqa: E731
    dn = lambda node: plain_term(data, node)  # noqa: E731
    path = r.path.node if r.path is not None and r.path.node is not None else None
    on_path = f" for {sn(path)}" if path is not None else ""
    # a blank node's label means nothing to a reader (and differs between runs), so it is not printed
    subject = ("A blank node value" if isinstance(r.value, ox.BlankNode) else f"Value {dn(r.value)}") if r.has_value else "Value"

    def one(predicate: Any) -> Any:
        vals = _params(shapes, r, predicate)
        return vals[0] if len(vals) == 1 else None

    if name == "MinCountConstraintComponent" and isinstance(n := one(SH.minCount), ox.Literal):
        return f"Needs at least {_count(n, 'value')}{on_path}"  # str-ok: text
    if name == "MaxCountConstraintComponent" and isinstance(n := one(SH.maxCount), ox.Literal):
        return f"Allows at most {_count(n, 'value')}{on_path}"  # str-ok: text
    if name == "ClassConstraintComponent":
        vals = _params(shapes, r, SH["class"])
        if len(vals) == 1:
            return f"{subject} should be an instance of {sn(vals[0])}"  # str-ok: text
        return f"{subject} should be an instance of all of {', '.join(sn(c) for c in vals)}" if vals else None  # str-ok: text
    if name == "DatatypeConstraintComponent" and (v := one(SH.datatype)) is not None:
        return f"{subject} should have the datatype {sn(v)}"  # str-ok: text
    if name == "NodeKindConstraintComponent" and (v := one(SH.nodeKind)) is not None:
        kind = _NODE_KINDS.get(T.iri_text(v).rsplit("#", 1)[-1]) if isinstance(v, ox.NamedNode) else None
        return f"{subject} should be {kind or sn(v)}"  # str-ok: text
    if name in ("MinLengthConstraintComponent", "MaxLengthConstraintComponent"):
        low = name.startswith("Min")
        if (v := one(SH.minLength if low else SH.maxLength)) is not None:
            return f"{subject} should have {'at least' if low else 'at most'} {_count(v, 'character')}"  # str-ok: text
    if name in _RANGE_WORDS and (v := one(SH[_RANGE_WORDS[name][0]])) is not None:
        return f"{subject} should be {_RANGE_WORDS[name][1]} {sn(v)}"  # str-ok: text
    if name == "PatternConstraintComponent" and isinstance(v := one(SH.pattern), ox.Literal):
        return f"{subject} should match the pattern '{v.value}'"  # str-ok: text
    if name == "LanguageInConstraintComponent" and (heads := _params(shapes, r, SH.languageIn)):
        return f"{subject} should have a language tag in {', '.join(sn(i) for i in _list_items(shapes, heads[0]))}"  # str-ok: text
    if name == "UniqueLangConstraintComponent":
        return f"Values{on_path} should not share a language tag"  # str-ok: text
    if name in _PAIR_WORDS:
        pred, words = _PAIR_WORDS[name]
        if (v := one(pred)) is not None and r.has_value:
            return f"{subject} {words.format(q=sn(v))}"  # str-ok: text
    if name == "NotConstraintComponent" and (v := one(SH["not"])) is not None and r.has_value:
        return f"{subject} should not conform to the shape {sn(v)}"  # str-ok: text
    if name == "NodeConstraintComponent" and (v := one(SH.node)) is not None and r.has_value:
        return f"{subject} should conform to the shape {sn(v)}"  # str-ok: text
    if name in _SHAPE_LISTS and r.has_value:
        pred, words = _SHAPE_LISTS[name]
        heads = _params(shapes, r, SH[pred])
        if not heads:
            return None
        listed = lambda head: ", ".join(sn(i) for i in _list_items(shapes, head))  # noqa: E731
        body = listed(heads[0]) if len(heads) < 2 else " and ".join(f"({listed(h)})" for h in heads)  # str-ok: text
        return f"{subject} should conform to {words} the shapes {body}"  # str-ok: text
    if name == "InConstraintComponent" and (heads := _params(shapes, r, SH["in"])) and r.has_value:
        return f"{subject} should be one of {', '.join(dn(i) for i in _list_items(shapes, heads[0]))}"  # str-ok: text
    if name == "ClosedConstraintComponent" and r.has_value and path is not None:
        return f"The property {sn(path)} is not allowed here, because the shape is closed"
    return None


def result_messages(r: Result, shapes: Any, data: Any) -> list:
    """The messages of a result (engine terms): the shape's own ``sh:message`` as is; otherwise the old (pySHACL) generic
    wording where it is known, else what the engine component wrote."""
    own = set(shapes.objects(r.shape, SH.message))
    messages = list(r.messages)
    if not r.messages_stated and not own.intersection(messages):
        try:
            generic = generic_message(r, shapes, data)
        except Exception:  # noqa: BLE001  (a message is never worth failing a validation for)
            generic = None
        if generic is not None:
            return [ox.Literal(T.unmask(generic))]
    return [_unmasked(m) for m in messages]


def _unmasked(m: Any) -> Any:
    """A message with the lenient-mode stand-in IRIs in its text mapped back to the original terms (``terms.unmask``)."""
    if isinstance(m, str):
        return T.unmask(m)
    if isinstance(m, ox.Literal) and T._INVALID_IRI_PREFIX in m.value:
        text = T.unmask(m.value)
        if m.language:
            return ox.Literal(text, language=m.language, direction=m.direction)
        return ox.Literal(text, datatype=m.datatype)
    return m


def _message_text(m: Any) -> str:
    return T.text(m) if isinstance(m, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)) else f"{m}"  # str-ok: a plain str


def _result_block(r: Result, shapes: Any, data: Any) -> str:
    name = _component_name(r.component)
    kind = "Constraint Violation" if r.severity == SH.Violation else "Validation Result"
    text = (
        f"{kind} in {name} ({T.text(r.component)}):\n\tSeverity: {stringify_node(shapes, r.severity)}"
        f"\n\tSource Shape: {stringify_node(shapes, r.shape)}\n\tFocus Node: {stringify_node(data, r.focus)}\n"
    )
    if r.has_value:
        text += f"\tValue Node: {stringify_node(data, r.value)}\n"
    path: Path | None = r.path
    if path is not None and path.node is not None:
        text += f"\tResult Path: {stringify_node(shapes, path.node)}\n"
    if r.source_constraint is not None:
        text += f"\tSource Constraint: {stringify_node(shapes, r.source_constraint)}\n"
    for m in sorted(result_messages(r, shapes, data), key=_message_text):
        text += f"\tMessage: {_message_text(m)}\n"  # str-ok: message text
    for detail in r.details:  # sh:detail: the nested result, indented under the result it explains
        nested = _result_block(detail, shapes, data)
        text += "\tDetail:\n" + "".join(f"\t\t{line}\n" for line in nested.splitlines())
    return text


def _prefixed(term: Any, *graphs: Any) -> str:
    """``term`` with the prefixes of the first graph that binds one for it (the report graph itself binds only ``sh``)."""
    out = T.n3(term)
    for graph in graphs:
        if graph is not None:
            text = _n3(graph, term)
            if not text.startswith("<") or isinstance(term, ox.Literal):
                return text
            out = text
    return out


def provenance_text(report: Any, data_graph_iri: Any = None, *graphs: Any) -> str:
    """The ``Provenance:`` appendix: used data/shapes graph and the ``sh:conformsTo`` / ``dcterms:conformsTo`` triples on
    the data graph's identity. Empty when there is nothing to say."""
    node = next(iter(report.subjects(RDF.type, SH.ValidationReport)), None)
    if node is None:
        return ""
    lines: list[str] = []
    for label, predicate in (("Used Data Graph", SH.usedDataGraph), ("Used Shapes Graph", SH.usedShapesGraph)):
        values = list(report.objects(node, predicate))
        if values:
            lines.append(f"\t{label}: {', '.join(_prefixed(v, *graphs, report) for v in values)}")
    if data_graph_iri is not None:
        subject = data_graph_iri if isinstance(data_graph_iri, (ox.NamedNode, ox.Literal)) else ox.NamedNode(f"{data_graph_iri}")  # str-ok: an IRI given as a str
        for predicate in (SH.conformsTo, DCTERMS.conformsTo):
            lines.extend(
                f"\t{_prefixed(subject, *graphs, report)} {_prefixed(predicate, *graphs, report)} {_prefixed(o, *graphs, report)} ."
                for o in report.objects(subject, predicate)
            )
    return "\n".join(["", "Provenance:", *lines]) if lines else ""


def report_text(
    results: list[Result], conforms: bool, shapes: Any, data: Any, report: Any = None, data_graph_iri: Any = None
) -> str:
    text = f"Validation Report\nConforms: {conforms}\n"
    if results:
        text += f"Results ({len(results)}):\n"
    text += "".join(sorted(_result_block(r, shapes, data) for r in results))
    if report is not None:
        text += provenance_text(report, data_graph_iri, data, shapes)
    return T.unmask(text)
