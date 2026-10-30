"""SHACL 1.2 Core value-type, cardinality, value-range and enumeration components.

Class, datatype, nodeKind, minCount/maxCount, min/max Exclusive/Inclusive, hasValue, in. Each function is called once
per (shape, focus node) and yields one ``Violation`` per offending (value node, parameter value).
"""

from __future__ import annotations

import operator
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from starlayer.graph.model import TripleTerm
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import SH, ShapeError

RDF_DIR_LANG_STRING = URIRef(str(RDF) + "dirLangString")

_NUMERIC = {
    XSD.integer, XSD.decimal, XSD.float, XSD.double, XSD.int, XSD.long, XSD.short, XSD.byte,
    XSD.nonNegativeInteger, XSD.positiveInteger, XSD.nonPositiveInteger, XSD.negativeInteger,
    XSD.unsignedInt, XSD.unsignedLong, XSD.unsignedShort, XSD.unsignedByte,
}  # fmt: skip
_ORDERED = {XSD.string, XSD.boolean, XSD.date, XSD.dateTime, XSD.time, XSD.gYear, XSD.gYearMonth}


# --- term helpers -----------------------------------------------------------------------------------------------


def is_literal(t: Any) -> bool:
    return isinstance(t, (Literal, DirLangString))


def is_triple_term(t: Any) -> bool:
    return isinstance(t, TripleTerm)


def literal_datatype(t: Any) -> URIRef | None:
    """The RDF datatype IRI of a literal (``rdf:langString`` / ``rdf:dirLangString`` for tagged strings)."""
    if isinstance(t, DirLangString):
        return RDF_DIR_LANG_STRING
    if isinstance(t, Literal):
        if t.datatype is not None:
            return t.datatype
        return RDF.langString if t.language else XSD.string
    return None


def rdf_list(graph: Any, head: Any) -> list[Any] | None:
    """Members of the rdf:list at ``head``, or None if it is not a well-formed list."""
    members, seen = [], set()
    while head != RDF.nil:
        if head in seen:
            return None
        seen.add(head)
        first, rest = list(graph.objects(head, RDF.first)), list(graph.objects(head, RDF.rest))
        if len(first) != 1 or len(rest) != 1:
            return None
        members.append(first[0])
        head = rest[0]
    return members


def alternatives(graph: Any, term: Any, what: str) -> list[Any]:
    """A parameter value that is either a single term or an rdf:list of terms (a union, SHACL 1.2)."""
    if isinstance(term, BNode) and (term, RDF.first, None) in graph:
        members = rdf_list(graph, term)
        if not members:
            raise ShapeError(f"{what}: malformed list {term!r}")
        return members
    return [term]


def _single_int(params: dict, pred: URIRef) -> int:
    (v,) = params[pred] if len(params[pred]) == 1 else (None,)
    value = v.value if isinstance(v, Literal) and v.datatype in _NUMERIC else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShapeError(f"{pred} needs exactly one non-negative xsd:integer, got {list(params[pred])!r}")
    return value


# --- sh:class ---------------------------------------------------------------------------------------------------


def _is_instance(data: Any, node: Any, cls: Any) -> bool:
    if is_literal(node) or is_triple_term(node):
        return False
    seen: set = set()
    todo = list(data.objects(node, RDF.type))
    while todo:
        c = todo.pop()
        if c == cls:
            return True
        if c not in seen:
            seen.add(c)
            todo.extend(data.objects(c, RDFS.subClassOf))
    return False


@component(SH.ClassConstraintComponent, SH["class"])
def class_(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SH["class"]]:
        classes = alternatives(ctx.shapes, param, "sh:class")
        if any(is_literal(c) or is_triple_term(c) for c in classes):
            raise ShapeError(f"sh:class needs IRIs or blank nodes, got {param!r}")
        for v in values:
            if not any(_is_instance(ctx.data, v, c) for c in classes):
                yield Violation(value=v, message=f"Value {v} is not an instance of {param}")


# --- sh:datatype ------------------------------------------------------------------------------------------------


def _has_datatype(v: Any, datatypes: list[Any]) -> bool:
    if not is_literal(v):
        return False
    if literal_datatype(v) not in datatypes:
        return False
    return not (isinstance(v, Literal) and v.ill_typed is True)  # well-formed per the datatype's lexical space


@component(SH.DatatypeConstraintComponent, SH.datatype)
def datatype(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for dt in params[SH.datatype]:
        allowed = alternatives(ctx.shapes, dt, "sh:datatype")  # a list of datatype IRIs is a union
        if not all(isinstance(a, URIRef) for a in allowed):
            raise ShapeError(f"sh:datatype needs an IRI or a list of IRIs, got {dt!r}")
        for v in values:
            if not _has_datatype(v, allowed):
                yield Violation(value=v, message=f"Value {v} does not have datatype {dt}")


# --- sh:nodeKind ------------------------------------------------------------------------------------------------

_KINDS = {
    SH.IRI: {"iri"},
    SH.BlankNode: {"bnode"},
    SH.Literal: {"literal"},
    SH.BlankNodeOrIRI: {"bnode", "iri"},
    SH.BlankNodeOrLiteral: {"bnode", "literal"},
    SH.IRIOrLiteral: {"iri", "literal"},
    SH.TripleTerm: {"triple"},
}


def _kind(t: Any) -> str:
    if isinstance(t, URIRef):
        return "iri"
    if isinstance(t, BNode):
        return "bnode"
    if is_triple_term(t):
        return "triple"
    return "literal"


@component(SH.NodeKindConstraintComponent, SH.nodeKind)
def node_kind(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for nk in params[SH.nodeKind]:
        kinds = alternatives(ctx.shapes, nk, "sh:nodeKind")
        if not all(k in _KINDS for k in kinds):
            raise ShapeError(f"sh:nodeKind needs sh: node kinds, got {nk!r}")
        allowed = set().union(*(_KINDS[k] for k in kinds))
        for v in values:
            if _kind(v) not in allowed:
                yield Violation(value=v, message=f"Value {v} does not have node kind {nk}")


# --- sh:minCount / sh:maxCount ----------------------------------------------------------------------------------


@component(SH.MinCountConstraintComponent, SH.minCount)
def min_count(ctx, shape, params, focus, values) -> Iterator[Violation]:
    n = _single_int(params, SH.minCount)
    if len(values) < n:
        yield Violation(message=f"Expected at least {n} value(s), found {len(values)}")


@component(SH.MaxCountConstraintComponent, SH.maxCount)
def max_count(ctx, shape, params, focus, values) -> Iterator[Violation]:
    n = _single_int(params, SH.maxCount)
    if len(values) > n:
        yield Violation(message=f"Expected at most {n} value(s), found {len(values)}")


# --- value ranges -----------------------------------------------------------------------------------------------


def _ordered_value(t: Any) -> tuple[str, Any] | None:
    """(comparison family, python value) for a literal that has a defined order, else None."""
    if not isinstance(t, Literal) or t.language or t.ill_typed is True:
        return None
    dt = literal_datatype(t)
    value = t.value
    if value is None:
        return None
    if dt in _NUMERIC:
        return ("number", value) if isinstance(value, (int, float, Decimal)) else None
    if dt in _ORDERED:
        return (str(dt), value)
    return None


def _compare(op, value: Any, bound: Any) -> bool:
    a, b = _ordered_value(value), _ordered_value(bound)
    if a is None or b is None or a[0] != b[0]:
        return False
    try:
        return bool(op(a[1], b[1]))
    except TypeError:  # e.g. timezone-aware vs naive
        return False


def _range_component(pred: URIRef, op):
    def check(ctx, shape, params, focus, values) -> Iterator[Violation]:
        for bound in params[pred]:
            if not isinstance(bound, Literal):
                raise ShapeError(f"{pred} needs a literal, got {bound!r}")
            for v in values:
                if not _compare(op, v, bound):
                    yield Violation(value=v, message=f"Value {v} fails {pred.split('#')[-1]} {bound}")

    return check


for _iri, _pred, _op in (
    (SH.MinExclusiveConstraintComponent, SH.minExclusive, operator.gt),
    (SH.MinInclusiveConstraintComponent, SH.minInclusive, operator.ge),
    (SH.MaxExclusiveConstraintComponent, SH.maxExclusive, operator.lt),
    (SH.MaxInclusiveConstraintComponent, SH.maxInclusive, operator.le),
):
    component(_iri, _pred)(_range_component(_pred, _op))


# --- sh:hasValue / sh:in ----------------------------------------------------------------------------------------


@component(SH.HasValueConstraintComponent, SH.hasValue)
def has_value(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for want in params[SH.hasValue]:
        if want not in values:
            yield Violation(message=f"Missing required value {want}")


@component(SH.InConstraintComponent, SH["in"])
def in_(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for head in params[SH["in"]]:
        members = rdf_list(ctx.shapes, head) if not isinstance(head, Literal) else None
        if members is None:
            raise ShapeError(f"sh:in needs an rdf:list, got {head!r}")
        for v in values:
            if v not in members:
                yield Violation(value=v, message=f"Value {v} is not in the allowed list")
