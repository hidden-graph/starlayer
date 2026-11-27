"""SHACL 1.2 Core value-type, cardinality, value-range and enumeration components.

Class, datatype, nodeKind, minCount/maxCount, min/max Exclusive/Inclusive, hasValue, in. Each function is called once
per (shape, focus node) and yields one ``Violation`` per offending (value node, parameter value).
"""

from __future__ import annotations

import operator
from collections.abc import Iterator
from typing import Any

from starlayer.errors import ShapeError
from starlayer.shacl.engine import xsd_values as xv
from starlayer.shacl.engine.components.registry import Violation, component, words
from starlayer.shacl.engine.naming import short
from starlayer.shacl.engine.plan import SH
from starlayer.shacl.engine.terms import (
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
            raise ShapeError(f"{what}: malformed list {term!r}", kind="compile")
        return members
    return [term]


def _single_int(params: dict, pred: NamedNode) -> int:
    (v,) = params[pred] if len(params[pred]) == 1 else (None,)
    value = xv.numeric(v)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShapeError(f"{short(pred)} needs exactly one non-negative xsd:integer, got {[text(x) for x in params[pred]]!r}", kind="compile")  # str-ok: short() returns text
    return value


# --- sh:class ---------------------------------------------------------------------------------------------------


def _is_instance(data: Any, node: Any, cls: Any, superclasses_of: Any = None) -> bool:
    """``rdf:type`` is read from ``data``; ``rdfs:subClassOf`` from ``superclasses_of`` (``Context.superclasses_of``) or ``data``."""
    if superclasses_of is None:
        def superclasses_of(c: Any) -> Any:
            return data.objects(c, RDFS.subClassOf)
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
            todo.extend(superclasses_of(c))
    return False


def _classes(shapes: Any, param: Any) -> list[Any]:
    classes = alternatives(shapes, param, "sh:class")
    if any(is_literal(c) or is_triple_term(c) for c in classes):
        raise ShapeError(f"sh:class needs IRIs or blank nodes, got {param!r}", kind="compile")
    return classes


def _check_class(shapes, shape, params) -> None:
    for param in params[SH["class"]]:
        _classes(shapes, param)


@component(SH.ClassConstraintComponent, SH["class"], check=_check_class)
def class_(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:class: every value node must be an instance of the class (or one in a list), via rdf:type and rdfs:subClassOf in the data."""
    wd = words(ctx)
    for param in params[SH["class"]]:
        classes = _classes(ctx.shapes, param)
        for v in values:
            if not any(_is_instance(ctx.data, v, c, ctx.superclasses_of) for c in classes):
                yield Violation(value=v, message=f"{wd.subject(v)} should {wd.expectation('ClassConstraintComponent', param)}")  # str-ok: text


# --- sh:datatype ------------------------------------------------------------------------------------------------


def _has_datatype(v: Any, datatypes: list[Any]) -> bool:
    if not is_literal(v):
        return False
    if literal_datatype(v) not in datatypes:
        return False
    return xv.well_formed(v)  # well-formed per the datatype's lexical space (value logic: xsd_values)


def _datatypes(shapes: Any, dt: Any) -> list[Any]:
    allowed = alternatives(shapes, dt, "sh:datatype")  # a list of datatype IRIs is a union
    if not all(isinstance(a, NamedNode) for a in allowed):
        raise ShapeError(f"sh:datatype needs an IRI or a list of IRIs, got {dt!r}", kind="compile")
    return allowed


def _check_datatype(shapes, shape, params) -> None:
    for dt in params[SH.datatype]:
        _datatypes(shapes, dt)


@component(SH.DatatypeConstraintComponent, SH.datatype, check=_check_datatype)
def datatype(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:datatype: every value node must be a well-formed literal of the datatype (or of one in a list of datatypes)."""
    wd = words(ctx)
    for dt in params[SH.datatype]:
        allowed = _datatypes(ctx.shapes, dt)
        for v in values:
            if not _has_datatype(v, allowed):
                yield Violation(value=v, message=f"{wd.subject(v)} should {wd.expectation('DatatypeConstraintComponent', dt)}")  # str-ok: text


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


def _kinds(shapes: Any, nk: Any) -> list[Any]:
    kinds = alternatives(shapes, nk, "sh:nodeKind")
    if not all(k in _KINDS for k in kinds):
        raise ShapeError(f"sh:nodeKind needs sh: node kinds, got {nk!r}", kind="compile")
    return kinds


def _check_node_kind(shapes, shape, params) -> None:
    for nk in params[SH.nodeKind]:
        _kinds(shapes, nk)


@component(SH.NodeKindConstraintComponent, SH.nodeKind, check=_check_node_kind)
def node_kind(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:nodeKind: every value node must be of the given node kind (or of one in a list of node kinds)."""
    wd = words(ctx)
    for nk in params[SH.nodeKind]:
        kinds = _kinds(ctx.shapes, nk)
        allowed = set().union(*(_KINDS[k] for k in kinds))
        for v in values:
            if _kind(v) not in allowed:
                yield Violation(value=v, message=f"{wd.subject(v)} should {wd.expectation('NodeKindConstraintComponent', nk)}")  # str-ok: text


# --- sh:minCount / sh:maxCount ----------------------------------------------------------------------------------


def _check_count(pred: NamedNode):
    def check(shapes, shape, params) -> None:
        _single_int(params, pred)

    return check


@component(SH.MinCountConstraintComponent, SH.minCount, check=_check_count(SH.minCount))
def min_count(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:minCount: the focus node must have at least n value nodes, where n is the sh:minCount integer."""
    n = _single_int(params, SH.minCount)
    if len(values) < n:
        yield Violation(message=f"Needs at least {n} value{'' if n == 1 else 's'}, found {len(values)}")  # str-ok: n is an int


@component(SH.MaxCountConstraintComponent, SH.maxCount, check=_check_count(SH.maxCount))
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
    def check_params(shapes, shape, params) -> None:
        for bound in params[pred]:
            if not isinstance(bound, Literal):
                raise ShapeError(f"{text(pred)} needs a literal, got {bound!r}", kind="compile")

    def check(ctx, shape, params, focus, values) -> Iterator[Violation]:
        check_params(ctx.shapes, shape, params)
        for bound in params[pred]:
            for v in values:
                if not _compare(op, v, bound):
                    yield Violation(value=v, message=f"Value {text(v)} should be {_RANGE_WORD[pred.value.split('#')[-1]]} {text(bound)}")

    return check, check_params


for _iri, _pred, _op in (
    (SH.MinExclusiveConstraintComponent, SH.minExclusive, operator.gt),
    (SH.MinInclusiveConstraintComponent, SH.minInclusive, operator.ge),
    (SH.MaxExclusiveConstraintComponent, SH.maxExclusive, operator.lt),
    (SH.MaxInclusiveConstraintComponent, SH.maxInclusive, operator.le),
):
    _fn, _check = _range_component(_pred, _op)
    component(_iri, _pred, check=_check)(_fn)


# --- sh:hasValue / sh:in ----------------------------------------------------------------------------------------


@component(SH.HasValueConstraintComponent, SH.hasValue)
def has_value(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:hasValue: the value nodes must include each given term."""
    wd = words(ctx)
    for want in params[SH.hasValue]:
        if want not in values:
            yield Violation(message=f"Needs the value {wd.shape(want)}{wd.on(shape.path.node if shape.path is not None else None)}")  # str-ok: text


def _in_members(shapes: Any, head: Any) -> list[Any]:
    members = rdf_list(shapes, head) if not isinstance(head, Literal) else None
    if members is None:
        raise ShapeError(f"sh:in needs an rdf:list, got {head!r}", kind="compile")
    return members


def _check_in(shapes, shape, params) -> None:
    for head in params[SH["in"]]:
        _in_members(shapes, head)


@component(SH.InConstraintComponent, SH["in"], check=_check_in)
def in_(ctx, shape, params, focus, values) -> Iterator[Violation]:
    """sh:in: every value node must be a member of the given rdf:list in the shapes graph."""
    for head in params[SH["in"]]:
        members = _in_members(ctx.shapes, head)
        for v in values:
            if v not in members:
                yield Violation(value=v, message=f"Value {text(v)} should be one of the allowed values")
