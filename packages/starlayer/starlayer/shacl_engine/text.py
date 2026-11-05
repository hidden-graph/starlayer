"""Human-readable report text and run diagnostics for an engine run.

``report_text`` reproduces the layout the old ``ValidationResult.report_text`` carries (the pySHACL listing, which the old
validator then extended with a provenance appendix): the same header, the same per-result block, results sorted by their
block text, then the ``Provenance:`` appendix. Natively written: nothing here imports pyshacl or the old validator.

Everything here works on engine (pyoxigraph) terms; a graph is any engine-term graph (``StarLayerGraph``, an overlay), and its
prefixes are those it binds (``namespaces()``), when it has any.

Known differences from the old text: a result's *generic* message (the ``Less than 1 values on ex:a->ex:p`` lines pySHACL
adds when a shape has no ``sh:message``) is only present when the engine component produced one; a SPARQL-based
component names itself ``ConstraintComponent`` in pySHACL and by its own IRI local name here.
"""

from __future__ import annotations

from typing import Any

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
    return repr(value.value) if isinstance(value.value, bool) else f"{value.value}"


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


_RANGE = {
    "MinExclusiveConstraintComponent": (SH.minExclusive, ">"),
    "MinInclusiveConstraintComponent": (SH.minInclusive, ">="),
    "MaxExclusiveConstraintComponent": (SH.maxExclusive, "<"),
    "MaxInclusiveConstraintComponent": (SH.maxInclusive, "<="),
}
_PAIR = {
    "EqualsConstraintComponent": (SH.equals, "!="),
    "DisjointConstraintComponent": (SH.disjoint, "=="),
    "LessThanConstraintComponent": (SH.lessThan, "<="),
    "LessThanOrEqualsConstraintComponent": (SH.lessThanOrEquals, "<"),
}


def _component_name(component: Any) -> str:
    return T.iri_text(component).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def generic_message(r: Result, shapes: Any, data: Any) -> str | None:
    """The generic result message the old validator (pySHACL) writes for a result of a shape without ``sh:message``, for
    the constraint components where it is a fixed template of one parameter value; ``None`` otherwise (the engine's own
    message is then kept)."""
    name = _component_name(r.component)
    sn = lambda node: stringify_node(shapes, node)  # noqa: E731
    dn = lambda node: stringify_node(data, node)  # noqa: E731
    path = r.path.node if r.path is not None and r.path.node is not None else None

    def one(predicate: Any) -> Any:
        vals = _params(shapes, r, predicate)
        return vals[0] if len(vals) == 1 else None

    if name in ("MinCountConstraintComponent", "MaxCountConstraintComponent"):
        n = one(SH.minCount if name.startswith("Min") else SH.maxCount)
        if not isinstance(n, ox.Literal):
            return None
        word = "Less than" if name.startswith("Min") else "More than"
        return f"{word} {_python_value(n) or n.value} values on {dn(r.focus)}" + (f"->{sn(path)}" if path is not None else "")  # str-ok: text
    if name == "ClassConstraintComponent":
        vals = _params(shapes, r, SH["class"])
        if len(vals) == 1:
            return f"Value does not have class {sn(vals[0])}"
        return f"Value class is not in classes ({', '.join(sn(c) for c in vals)})" if vals else None
    if name == "DatatypeConstraintComponent" and (v := one(SH.datatype)) is not None:
        return f"Value is not Literal with datatype {sn(v)}"
    if name == "NodeKindConstraintComponent" and (v := one(SH.nodeKind)) is not None:
        return f"Value is not of Node Kind {sn(v)}"
    if name == "MinLengthConstraintComponent" and (v := one(SH.minLength)) is not None:
        return f"String length not >= {dn(v)}"
    if name == "MaxLengthConstraintComponent" and (v := one(SH.maxLength)) is not None:
        return f"String length not <= {dn(v)}"
    if name in _RANGE and (v := one(_RANGE[name][0])) is not None:
        return f"Value is not {_RANGE[name][1]} {sn(v)}"
    if name == "PatternConstraintComponent" and isinstance(v := one(SH.pattern), ox.Literal):
        return f"Value does not match pattern '{v.value}'"
    if name == "LanguageInConstraintComponent" and (v := one(SH.languageIn)) is not None:
        return f"String language is not in {sn(v)}"
    if name == "UniqueLangConstraintComponent":
        return "More than one String shares the same Language"
    if name in _PAIR and (v := one(_PAIR[name][0])) is not None and r.has_value:
        return f"Value of {dn(r.focus)}->{sn(v)} {_PAIR[name][1]} {dn(r.value)}"
    if name == "NotConstraintComponent" and (v := one(SH["not"])) is not None and r.has_value:
        return f"Node {dn(r.value)} must not conform to shape {sn(v)}"
    if name in ("AndConstraintComponent", "OrConstraintComponent", "XoneConstraintComponent") and r.has_value:
        pred, tail = {
            "AndConstraintComponent": (SH["and"], "must conform to all shapes in"),
            "OrConstraintComponent": (SH["or"], "must conform to one or more shapes in"),
            "XoneConstraintComponent": (SH.xone, "must conform to exactly one shape in"),
        }[name]
        heads = _params(shapes, r, pred)
        if not heads:
            return None
        text = lambda head: " , ".join(sn(i) for i in _list_items(shapes, head))  # noqa: E731
        body = text(heads[0]) if len(heads) < 2 else " and ".join(f"({text(h)})" for h in heads)
        return f"Node {dn(r.value)} {tail} {body}"
    if name == "InConstraintComponent" and (heads := _params(shapes, r, SH["in"])) and r.has_value:
        return f"Value {dn(r.value)} not in list {[sn(i) for i in _list_items(shapes, heads[0])]}"  # str-ok: rendered text
    if name == "ClosedConstraintComponent" and r.has_value:
        return f"Node {dn(r.focus)} is closed. It cannot have value: {dn(r.value)}"
    return None


def result_messages(r: Result, shapes: Any, data: Any) -> list:
    """The messages of a result (engine terms): the shape's own ``sh:message`` as is; otherwise the old (pySHACL) generic
    wording where it is known, else what the engine component wrote."""
    own = set(shapes.objects(r.shape, SH.message))
    messages = list(r.messages)
    if not own.intersection(messages):
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
