"""SHACL 1.2 Core value-type, cardinality, value-range and enumeration components.

Class, datatype, nodeKind, minCount/maxCount, min/max Exclusive/Inclusive, hasValue, in. Each function is called once
per (shape, focus node) and yields one ``Violation`` per offending (value node, parameter value).
"""

from __future__ import annotations

import operator
from collections.abc import Iterator
from typing import Any

from starlayer.shacl_engine import xsd_values as xv
from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import SH, ShapeError
from starlayer.shacl_engine.terms import (
    RDF,
    RDFS,
    BlankNode,
    Literal,
    NamedNode,
    Triple,
    text,
)

# --- term helpers -----------------------------------------------------------------------------------------------


def is_literal(t: Any) -> bool:
    """Whether a term is an RDF literal."""
    return isinstance(t, Literal)


def is_triple_term(t: Any) -> bool:
    """Whether a term is an RDF 1.2 triple term."""
    return isinstance(t, Triple)


def literal_datatype(t: Any) -> NamedNode | None:
    """The RDF datatype IRI of a literal (``rdf:langString`` / ``rdf:dirLangString`` for tagged strings)."""
    return t.datatype if isinstance(t, Literal) else None


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
    if isinstance(term, BlankNode) and (term, RDF.first, None) in graph:
        members = rdf_list(graph, term)
        if not members:
            raise ShapeError(f"{what}: malformed list {term!r}")
        return members
    return [term]


def _single_int(params: dict, pred: NamedNode) -> int:
    (v,) = params[pred] if len(params[pred]) == 1 else (None,)
    value = xv.numeric(v)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShapeError(f"{text(pred)} needs exactly one non-negative xsd:integer, got {[text(x) for x in params[pred]]!r}")
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
    """sh:class: every value node must be an instance of the class (or one in a list), via rdf:type and rdfs:subClassOf in the data."""
    for param in params[SH["class"]]:
        classes = alternatives(ctx.shapes, param, "sh:class")
        if any(is_literal(c) or is_triple_term(c) for c in classes):
            raise ShapeError(f"sh:class needs IRIs or blank nodes, got {param!r}")
        for v in values:
            if not any(_is_instance(ctx.data, v, c) for c in classes):
                yield Violation(value=v, message=f"Value {text(v)} should be an instance of {text(param)}")


# --- sh:datatype ------------------------------------------------------------------------------------------------


def _has_datatype(v: Any, datatypes: list[Any]) -> bool:
    if not is_literal(v):
        return False
    if literal_datatype(v) not in datatypes:
        return False
    return xv.well_formed(v)  # well-formed per the datatype's lexical space (value logic: xsd_values)


@component(SH.DatatypeConstraintComponent, SH.datatype)
def datatype(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:datatype: every value node must be a well-formed literal of the datatype (or of one in a list of datatypes)."""
    for dt in params[SH.datatype]:
        allowed = alternatives(ctx.shapes, dt, "sh:datatype")  # a list of datatype IRIs is a union
        if not all(isinstance(a, NamedNode) for a in allowed):
            raise ShapeError(f"sh:datatype needs an IRI or a list of IRIs, got {dt!r}")
        for v in values:
            if not _has_datatype(v, allowed):
                yield Violation(value=v, message=f"Value {text(v)} should have the datatype {text(dt)}")


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
    if isinstance(t, NamedNode):
        return "iri"
    if isinstance(t, BlankNode):
        return "bnode"
    if is_triple_term(t):
        return "triple"
    return "literal"


@component(SH.NodeKindConstraintComponent, SH.nodeKind)
def node_kind(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:nodeKind: every value node must be of the given node kind (or of one in a list of node kinds)."""
    for nk in params[SH.nodeKind]:
        kinds = alternatives(ctx.shapes, nk, "sh:nodeKind")
        if not all(k in _KINDS for k in kinds):
            raise ShapeError(f"sh:nodeKind needs sh: node kinds, got {nk!r}")
        allowed = set().union(*(_KINDS[k] for k in kinds))
        for v in values:
            if _kind(v) not in allowed:
                yield Violation(value=v, message=f"Value {text(v)} should have the node kind {text(nk)}")


# --- sh:minCount / sh:maxCount ----------------------------------------------------------------------------------


@component(SH.MinCountConstraintComponent, SH.minCount)
def min_count(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:minCount: the focus node must have at least n value nodes, where n is the sh:minCount integer."""
    n = _single_int(params, SH.minCount)
    if len(values) < n:
        yield Violation(message=f"Needs at least {n} value{'' if n == 1 else 's'}, found {len(values)}")  # str-ok: n is an int


@component(SH.MaxCountConstraintComponent, SH.maxCount)
def max_count(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:maxCount: the focus node must have at most n value nodes, where n is the sh:maxCount integer."""
    n = _single_int(params, SH.maxCount)
    if len(values) > n:
        yield Violation(message=f"Allows at most {n} value{'' if n == 1 else 's'}, found {len(values)}")  # str-ok: n is an int


# --- value ranges -----------------------------------------------------------------------------------------------


_RANGE_WORD = {"minExclusive": "greater than", "minInclusive": "at least", "maxExclusive": "less than", "maxInclusive": "at most"}


def _compare(op, value: Any, bound: Any) -> bool:
    """``op(value, bound)`` on the SPARQL/XSD value order; incomparable (or ill-formed) is False."""
    c = xv.compare(value, bound)
    return c is not None and bool(op(c, 0))


def _range_component(pred: NamedNode, op):
    def check(ctx, shape, params, focus, values) -> Iterator[Violation]:
        for bound in params[pred]:
            if not isinstance(bound, Literal):
                raise ShapeError(f"{text(pred)} needs a literal, got {bound!r}")
            for v in values:
                if not _compare(op, v, bound):
                    yield Violation(value=v, message=f"Value {text(v)} should be {_RANGE_WORD[pred.value.split('#')[-1]]} {text(bound)}")

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
    """sh:hasValue: the value nodes must include each given term."""
    for want in params[SH.hasValue]:
        if want not in values:
            yield Violation(message=f"Needs the value {text(want)}")


@component(SH.InConstraintComponent, SH["in"])
def in_(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:in: every value node must be a member of the given rdf:list in the shapes graph."""
    for head in params[SH["in"]]:
        members = rdf_list(ctx.shapes, head) if not isinstance(head, Literal) else None
        if members is None:
            raise ShapeError(f"sh:in needs an rdf:list, got {head!r}")
        for v in values:
            if v not in members:
                yield Violation(value=v, message=f"Value {text(v)} should be one of the allowed values")
