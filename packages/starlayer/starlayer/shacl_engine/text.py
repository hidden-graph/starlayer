"""Human-readable report text and run diagnostics for an engine run.

``report_text`` reproduces the layout the old ``ValidationResult.report_text`` carries (the pySHACL listing, which the old
validator then extended with a provenance appendix): the same header, the same per-result block, results sorted by their
block text, then the ``Provenance:`` appendix. Natively written: nothing here imports pyshacl or the old validator.

Known differences from the old text: a result's *generic* message (the ``Less than 1 values on ex:a->ex:p`` lines pySHACL
adds when a shape has no ``sh:message``) is only present when the engine component produced one; a SPARQL-based
component names itself ``ConstraintComponent`` in pySHACL and by its own IRI local name here.
"""

# str-ok-file: renders the boundary results: every term in this module is an rdflib / StarLayer term (from_engine output)

from __future__ import annotations

from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF

from starlayer.graph.model.triple import TripleTerm
from starlayer.shacl_engine.executor import Result
from starlayer.shacl_engine.plan import Path

SH = Namespace("http://www.w3.org/ns/shacl#")  # rdflib terms: the text is rendered from the boundary results
_MAX_DEPTH = 12


def _n3(graph: Any, term: Any) -> str:
    try:
        return term.n3(namespace_manager=graph.namespace_manager)
    except Exception:
        return str(term)


def stringify_node(graph: Any, node: Any, depth: int = 0) -> str:
    """A node as text, in the form the old report text uses: prefixed names, ``Literal("x", lang=..., datatype=...)``,
    blank nodes as ``[ p o ; ... ]``, lists as ``( a b )``, triple terms as ``<<( s p o )>>``."""
    if isinstance(node, TripleTerm):
        return "<<( {} {} {} )>>".format(*(stringify_node(graph, t, depth + 1) for t in tuple(node)))
    if isinstance(node, Literal):
        return _literal(graph, node)
    if isinstance(node, BNode):
        return _blank(graph, node, depth + 1)
    if isinstance(node, URIRef):
        return _n3(graph, node)
    return str(node)


def _literal(graph: Any, node: Literal) -> str:
    lex = str(node)
    value = None if node.value is None else str(node.value)
    if value is not None and (i := value.find(" object at 0x")) > 0:
        value = value[:i]
    val = f'"{lex}" = {value}' if value is not None and value != lex else f'"{lex}"'
    lang = f", lang={node.language}" if node.language else ""
    datatype = f", datatype={stringify_node(graph, node.datatype)}" if node.datatype else ""
    return f"Literal({val}{lang}{datatype})"


def _blank(graph: Any, node: BNode, depth: int) -> str:
    if depth >= _MAX_DEPTH:
        return "<http://recursion.too.deep>"
    predicates = list(dict.fromkeys(graph.predicates(node)))
    if not predicates:
        return "[ ]"
    if RDF.first in predicates:
        return "( {} )".format(" ".join(stringify_node(graph, i, depth + 1) for i in graph.items(node)))
    rendered: dict[str, str] = {}
    for p in predicates:
        objs = list(graph.objects(node, p))
        if not objs:
            continue
        texts = ["<self>" if o is node else stringify_node(graph, o, depth + 1) for o in objs]
        rendered[_n3(graph, p)] = ", ".join(sorted(texts)) if len(texts) > 1 else texts[0]
    return "[ {} ]".format(" ; ".join(f"{p} {o}" for p, o in sorted(rendered.items())))


def _params(shapes: Any, r: Result, predicate: Any) -> list[Any]:
    return list(shapes.objects(r.shape, predicate))


def _list_items(shapes: Any, head: Any) -> list[Any]:
    try:
        return list(shapes.items(head))
    except Exception:
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


def generic_message(r: Result, shapes: Any, data: Any) -> str | None:
    """The generic result message the old validator (pySHACL) writes for a result of a shape without ``sh:message``, for
    the constraint components where it is a fixed template of one parameter value; ``None`` otherwise (the engine's own
    message is then kept)."""
    name = str(r.component).rsplit("#", 1)[-1]
    sn = lambda node: stringify_node(shapes, node)  # noqa: E731
    dn = lambda node: stringify_node(data, node)  # noqa: E731
    path = r.path.node if r.path is not None and r.path.node is not None else None

    def one(predicate: Any) -> Any:
        vals = _params(shapes, r, predicate)
        return vals[0] if len(vals) == 1 else None

    if name in ("MinCountConstraintComponent", "MaxCountConstraintComponent"):
        n = one(SH.minCount if name.startswith("Min") else SH.maxCount)
        if not isinstance(n, Literal):
            return None
        word = "Less than" if name.startswith("Min") else "More than"
        return f"{word} {n.value} values on {dn(r.focus)}" + (f"->{sn(path)}" if path is not None else "")
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
    if name == "PatternConstraintComponent" and isinstance(v := one(SH.pattern), Literal):
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
        return f"Value {dn(r.value)} not in list {[sn(i) for i in _list_items(shapes, heads[0])]}"
    if name == "ClosedConstraintComponent" and r.has_value:
        return f"Node {dn(r.focus)} is closed. It cannot have value: {dn(r.value)}"
    return None


def result_messages(r: Result, shapes: Any, data: Any) -> list:
    """The messages of a result (boundary terms): the shape's own ``sh:message`` as is; otherwise the old (pySHACL) generic
    wording where it is known, else what the engine component wrote."""
    own = set(shapes.objects(r.shape, SH.message))
    messages = list(r.messages)
    if not own.intersection(messages):
        try:
            generic = generic_message(r, shapes, data)
        except Exception:  # noqa: BLE001  (a message is never worth failing a validation for)
            generic = None
        if generic is not None:
            return [Literal(generic)]
    return messages


def _result_block(r: Result, shapes: Any, data: Any) -> str:
    name = str(r.component).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    kind = "Constraint Violation" if r.severity == SH.Violation else "Validation Result"
    text = (
        f"{kind} in {name} ({r.component}):\n\tSeverity: {stringify_node(shapes, r.severity)}"
        f"\n\tSource Shape: {stringify_node(shapes, r.shape)}\n\tFocus Node: {stringify_node(data, r.focus)}\n"
    )
    if r.has_value:
        text += f"\tValue Node: {stringify_node(data, r.value)}\n"
    path: Path | None = r.path
    if path is not None and path.node is not None:
        text += f"\tResult Path: {stringify_node(shapes, path.node)}\n"
    if r.source_constraint is not None:
        text += f"\tSource Constraint: {stringify_node(shapes, r.source_constraint)}\n"
    for m in sorted(result_messages(r, shapes, data), key=str):
        text += f"\tMessage: {m.value if isinstance(m, Literal) else m}\n"
    return text


def _prefixed(term: Any, *graphs: Any) -> str:
    """``term`` with the prefixes of the first graph that binds one for it (the report graph itself binds only ``sh``)."""
    out = str(term) if not isinstance(term, (URIRef, Literal)) else term.n3()
    for graph in graphs:
        if graph is not None:
            text = _n3(graph, term)
            if not text.startswith("<") or term.__class__ is Literal:
                return text
            out = text
    return out


def provenance_text(report: Any, data_graph_iri: Any = None, *graphs: Any) -> str:
    """The ``Provenance:`` appendix: used data/shapes graph and the ``sh:conformsTo`` / ``dcterms:conformsTo`` triples on
    the data graph's identity. Empty when there is nothing to say."""
    node = next(report.subjects(RDF.type, SH.ValidationReport), None)
    if node is None:
        return ""
    lines: list[str] = []
    for label, predicate in (("Used Data Graph", SH.usedDataGraph), ("Used Shapes Graph", SH.usedShapesGraph)):
        values = list(report.objects(node, predicate))
        if values:
            lines.append(f"\t{label}: {', '.join(_prefixed(v, *graphs, report) for v in values)}")
    if data_graph_iri is not None:
        subject = data_graph_iri if isinstance(data_graph_iri, (URIRef, Literal)) else URIRef(str(data_graph_iri))
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
    return text
