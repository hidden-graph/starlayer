"""``derive_shape``: infer one SHACL node shape from the data of a graph (a StarLayer feature; SHACL itself has no such operation).

The shape describes either every instance of a class (``cls=``, ``sh:targetClass``) or one node (``node=``, ``sh:targetNode``), never
a heuristic clustering of nodes, and is optionally reconciled with a template shape. Native over pyoxigraph terms and the wrapper API
(no rdflib). It lives in ``starlayer.shacl`` and not in ``starlayer.graph`` because it validates its result, and the graph package
does not depend on the SHACL one.

Two phases:

- Phase A (fresh derivation) is the whole algorithm without a template: pure graph analysis, then a self-check.
- Phase B (template merge) copies the one template shape that targets the same class or node (and what it references), validates
  it against the data once and dispatches each violation by its ``sh:sourceConstraintComponent``: components with a principled
  data-driven fix are recomputed from the true current data (``_RECOMPUTE_COMPONENTS``); every other violated constraint
  (``sh:pattern``, cross-property comparisons, ``sh:hasValue``, ``sh:sparql``, custom components) is deactivated with a
  reifier on its own triple, ``{| sh:deactivated true |}``, so it keeps its value and the engine skips it. Everything that
  changed is listed in one ``rdfs:comment`` on the node shape.

Value kinds are Literal, IRI, BlankNode and TripleTerm (SHACL 1.2's ``sh:nodeKind sh:TripleTerm``, list-valued when mixed), so a
triple-term-valued property is never silently dropped. Both phases end by validating the result against the same data, restricted
to the shape's own targets, and both results must conform.

The output has no randomness: every blank node it makes (property shapes, list cells, an unnamed shape) gets an identifier computed
from the target and the order of creation, and everything is visited in sorted order, so the same input gives the same graph, triple
for triple.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pyoxigraph as ox

from starlayer.graph import terms
from starlayer.graph.namespaces import DCTERMS, RDFS, SH
from starlayer.shacl.engine import xsd_values
from starlayer.shacl.engine.plan import ExecutionError
from starlayer.shacl.engine.terms import engine_view, to_engine
from starlayer.shacl.normalization import normalize_to_starlayer_graph
from starlayer.shacl.shapes_graphs import referenced_shapes
from starlayer.shacl.validator import validate

_XSD = "http://www.w3.org/2001/XMLSchema#"
_SH_NS = "http://www.w3.org/ns/shacl#"

RDF_TYPE, RDF_FIRST, RDF_REST, RDF_NIL = terms.RDF_TYPE, terms.RDF_FIRST, terms.RDF_REST, terms.RDF_NIL
_XSD_INTEGER = ox.NamedNode(_XSD + "integer")
_XSD_DOUBLE = ox.NamedNode(_XSD + "double")
_XSD_BOOLEAN = ox.NamedNode(_XSD + "boolean")
_TRUE = ox.Literal("true", datatype=_XSD_BOOLEAN)
_RDFS_SUBCLASS = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")

# rdf:type is not exempt from sh:closed's check, so it is always in sh:ignoredProperties (never opted out of).
_ALWAYS_IGNORED = frozenset({RDF_TYPE})

# Opt-outable bookkeeping predicates: non-structural metadata.
DEFAULT_IGNORED_PROPERTIES = frozenset({RDFS.label, RDFS.comment, DCTERMS.created, DCTERMS.modified})

_NODE_KIND_TERM = {"Literal": SH.Literal, "IRI": SH.IRI, "BlankNode": SH.BlankNode, "TripleTerm": SH.TripleTerm}

# Components with a principled data-driven relax: recomputed fully from the true current data, not patched from one value.
_RECOMPUTE_COMPONENTS = frozenset({
    SH.MinCountConstraintComponent, SH.MaxCountConstraintComponent, SH.DatatypeConstraintComponent,
    SH.ClassConstraintComponent, SH.NodeKindConstraintComponent,
    SH.MinInclusiveConstraintComponent, SH.MaxInclusiveConstraintComponent,
    SH.MinExclusiveConstraintComponent, SH.MaxExclusiveConstraintComponent,
    SH.MinLengthConstraintComponent, SH.MaxLengthConstraintComponent,
    SH.LanguageInConstraintComponent, SH.InConstraintComponent,
})

_RECOMPUTE_PREDICATES = {
    SH.MinCountConstraintComponent: (SH.minCount,), SH.MaxCountConstraintComponent: (SH.maxCount,),
    SH.DatatypeConstraintComponent: (SH.datatype,), SH.ClassConstraintComponent: (SH["class"],),
    SH.NodeKindConstraintComponent: (SH.nodeKind,),
    SH.MinInclusiveConstraintComponent: (SH.minInclusive,), SH.MaxInclusiveConstraintComponent: (SH.maxInclusive,),
    SH.MinExclusiveConstraintComponent: (SH.minExclusive,), SH.MaxExclusiveConstraintComponent: (SH.maxExclusive,),
    SH.MinLengthConstraintComponent: (SH.minLength,), SH.MaxLengthConstraintComponent: (SH.maxLength,),
    SH.LanguageInConstraintComponent: (SH.languageIn,), SH.InConstraintComponent: (SH["in"],),
}

# Why a recomputed constraint changed, for the comment on the shape.
_RECOMPUTE_REASON = {
    SH.MinCountConstraintComponent: "some node has fewer values",
    SH.MaxCountConstraintComponent: "some node has more values",
    SH.DatatypeConstraintComponent: "the values do not have this datatype",
    SH.ClassConstraintComponent: "the values are not all of this class",
    SH.NodeKindConstraintComponent: "a value is of another kind",
    SH.MinInclusiveConstraintComponent: "a value is below it",
    SH.MaxInclusiveConstraintComponent: "a value is above it",
    SH.MinExclusiveConstraintComponent: "a value is not above it",
    SH.MaxExclusiveConstraintComponent: "a value is not below it",
    SH.MinLengthConstraintComponent: "a value is shorter",
    SH.MaxLengthConstraintComponent: "a value is longer",
    SH.LanguageInConstraintComponent: "a value has another language or none",
    SH.InConstraintComponent: "a value is not in the list",
}

_COMMENT_HEADER = "derive_shape() changed this shape to fit the data:"
_RDF_REIFIES = terms.RDF_REIFIES

_INCLUSIVE_EXCLUSIVE_PREDICATE = {
    SH.MinInclusiveConstraintComponent: SH.minInclusive,
    SH.MaxInclusiveConstraintComponent: SH.maxInclusive,
    SH.MinExclusiveConstraintComponent: SH.minExclusive,
    SH.MaxExclusiveConstraintComponent: SH.maxExclusive,
}


# ---- terms and rdf:List helpers ------------------------------------------------------------------------------------------

def _int(n: int) -> ox.Literal:
    return ox.Literal(str(n), datatype=_XSD_INTEGER)


def _number(n: int | float) -> ox.Literal:
    return _int(n) if isinstance(n, int) else ox.Literal(str(n), datatype=_XSD_DOUBLE)


def _text(term: Any) -> str:
    """A term's lexical form: the IRI, the literal's lexical form, the blank node label."""
    return term.value if hasattr(term, "value") else str(term)


def _sort_key(term: Any) -> tuple[str, str]:
    return type(term).__name__, str(term)


_SHACL_KIND = {"iri": "IRI", "blank": "BlankNode", "literal": "Literal", "triple": "TripleTerm"}


def _term_kind(v: Any) -> str:
    """The ``sh:nodeKind`` name of a term's kind (``IRI``, ``BlankNode``, ``Literal``, ``TripleTerm``)."""
    return _SHACL_KIND[terms.term_kind(v)]


class _Minter:
    """Blank nodes with identifiers computed from the target and a counter, so a derivation is the same graph every time (a random
    ``BlankNode()`` is not)."""

    def __init__(self, seed: str) -> None:
        self._seed = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
        self._n = 0

    def node(self, g: Any) -> ox.BlankNode:
        while True:
            self._n += 1
            bnode = ox.BlankNode(f"d{self._seed}x{self._n}")
            if not any(True for _ in g.triples((bnode, None, None))) and not any(True for _ in g.triples((None, None, bnode))):
                return bnode

    def rdf_list(self, g: Any, items: Iterable[Any]) -> Any:
        items = list(items)
        if not items:
            return RDF_NIL
        cells = [self.node(g) for _ in items]
        for cell, item, nxt in zip(cells, items, [*cells[1:], RDF_NIL], strict=True):
            g.add((cell, RDF_FIRST, item))
            g.add((cell, RDF_REST, nxt))
        return cells[0]


def _literal_datatype_bucket(lit: ox.Literal) -> ox.NamedNode | None:
    """None for a language-tagged literal (no fixed datatype) and for an ill-formed one (SHACL's ``sh:datatype`` rejects it, so
    the datatype cannot be claimed), else its datatype (xsd:string for a plain one)."""
    if lit.language:
        return None
    return lit.datatype if xsd_values.well_formed(lit) else None


def _list_items(g: Any, head: Any) -> list[Any]:
    """The members of the list at ``head``; a malformed or cyclic list yields what could be read."""
    out, seen = [], set()
    while head is not None and head != RDF_NIL and head not in seen:
        seen.add(head)
        first = g.value(head, RDF_FIRST)
        if first is not None:
            out.append(first)
        head = g.value(head, RDF_REST)
    return out


def _remove_rdf_list(g: Any, node: Any) -> None:
    """Remove the cells of the list at ``node``, stopping at a cell that something other than the previous cell still points to
    (the triple that pointed at the head is already removed): a list can be shared by two property shapes."""
    seen = set()
    referrer: tuple[Any, Any] | None = None
    while node is not None and node != RDF_NIL and node not in seen:
        seen.add(node)
        if any((s, p) != referrer for s, p, _ in g.triples((None, None, node))):
            return
        nxt = g.value(node, RDF_REST)
        g.remove((node, None, None))
        referrer = (node, RDF_REST)
        node = nxt


def _clear_list_valued(g: Any, node: Any, pred: Any) -> None:
    """Remove ``pred``'s value from ``node``, freeing its list nodes too when it is list-valued and nothing else uses them."""
    old = g.value(node, pred)
    if old is None:
        return
    g.remove((node, pred, old))
    if isinstance(old, ox.BlankNode) and (old, RDF_FIRST, None) in g:
        _remove_rdf_list(g, old)


def _shared_rdf_type(data: Any, values: Iterable[Any]) -> Any:
    """The one rdf:type every value shares, or None if any has no type or the shared set is not exactly one."""
    per_value = []
    for v in values:
        types = set(data.objects(v, RDF_TYPE))
        if not types:
            return None
        per_value.append(types)
    common = set.intersection(*per_value) if per_value else set()
    return next(iter(common)) if len(common) == 1 else None


def _number_of(v: Any) -> int | float | None:
    """The int or float of a well-formed numeric literal (``xsd:decimal`` and booleans excluded, as in the old module)."""
    n = xsd_values.numeric(v)
    return None if isinstance(n, Decimal) else n


# ---- the target: a class or a node ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Target:
    """What the shape describes: ``cls`` (``sh:targetClass``) or ``node`` (``sh:targetNode``)."""

    kind: str
    term: Any
    include_subclasses: bool

    @property
    def predicate(self) -> Any:
        return SH.targetClass if self.kind == "cls" else SH.targetNode

    def instances(self, data: Any) -> set[Any]:
        return _instances_of(data, self.term, self.include_subclasses) if self.kind == "cls" else {self.term}


def _instances_of(data: Any, cls: Any, include_subclasses: bool) -> set[Any]:
    """The nodes typed ``cls`` and, with ``include_subclasses``, those typed by a (transitive) ``rdfs:subClassOf`` subclass of it in
    the data graph: what ``sh:targetClass cls`` selects."""
    classes, todo = {cls}, [cls]
    while include_subclasses and todo:
        for sub in data.subjects(_RDFS_SUBCLASS, todo.pop()):
            if sub not in classes:
                classes.add(sub)
                todo.append(sub)
    return {s for c in classes for s in data.subjects(RDF_TYPE, c)}


def _shape_instances(shapes: Any, data: Any, shape_node: Any, include_subclasses: bool) -> set[Any] | None:
    """The nodes the node shape that owns ``shape_node`` (or ``shape_node`` itself) targets by ``sh:targetClass`` or
    ``sh:targetNode``; None when it has neither (a nested ``sh:node`` shape, say), so there is no data to recompute from."""
    found: set[Any] | None = None
    for ns in [*shapes.subjects(SH.property, shape_node), shape_node]:
        for cls in shapes.objects(ns, SH.targetClass):
            found = (found or set()) | _instances_of(data, cls, include_subclasses)
        for node in shapes.objects(ns, SH.targetNode):
            found = (found or set()) | {node}
    return found


# ---- value kinds -> sh:datatype / sh:class / sh:nodeKind / sh:languageIn -------------------------------------------------

def _set_node_kind_constraints(g: Any, data: Any, prop_node: Any, values: set[Any], mint: _Minter) -> None:
    if not values:
        return
    kinds = {_term_kind(v) for v in values}

    if kinds == {"Literal"}:
        buckets = {_literal_datatype_bucket(v) for v in values}
        if len(buckets) == 1 and None not in buckets:
            g.add((prop_node, SH.datatype, next(iter(buckets))))
            return
        g.add((prop_node, SH.nodeKind, SH.Literal))
        if all(v.language for v in values):
            langs = sorted({v.language for v in values})
            g.add((prop_node, SH.languageIn, mint.rdf_list(g, [ox.Literal(lang) for lang in langs])))
        return

    if len(kinds) == 1 and kinds <= {"IRI", "BlankNode"}:
        shared_class = _shared_rdf_type(data, values)
        if shared_class is not None:
            g.add((prop_node, SH["class"], shared_class))
            return
        g.add((prop_node, SH.nodeKind, _NODE_KIND_TERM[next(iter(kinds))]))
        return

    if kinds == {"TripleTerm"}:
        g.add((prop_node, SH.nodeKind, SH.TripleTerm))
        return

    if len(kinds) == 4:
        return  # every kind present at once is vacuous: omit sh:nodeKind

    # Genuinely mixed (2-3 kinds): SHACL 1.2's list-valued sh:nodeKind names exactly what was observed.
    kind_terms = sorted((_NODE_KIND_TERM[k] for k in kinds), key=_text)
    g.add((prop_node, SH.nodeKind, mint.rdf_list(g, kind_terms)))


# ---- Phase A: fresh derivation -------------------------------------------------------------------------------------------

def _counts_and_values(data: Any, instances: Iterable[Any], predicate: Any) -> tuple[list[int], set[Any]]:
    counts, values = [], set()
    for inst in instances:
        vs = list(data.objects(inst, predicate))
        counts.append(len(vs))
        values.update(vs)
    return counts, values


def _derive_property_shape(g: Any, data: Any, instances: Iterable[Any], predicate: Any, mint: _Minter) -> ox.BlankNode:
    counts, values = _counts_and_values(data, instances, predicate)
    prop_node = mint.node(g)
    g.add((prop_node, RDF_TYPE, SH.PropertyShape))
    g.add((prop_node, SH.path, predicate))
    if (min_count := min(counts, default=0)) > 0:
        g.add((prop_node, SH.minCount, _int(min_count)))
    g.add((prop_node, SH.maxCount, _int(max(counts, default=0))))
    _set_node_kind_constraints(g, data, prop_node, values, mint)
    return prop_node


def _class_predicates(data: Any, instances: Iterable[Any], ignored: set[Any]) -> list[Any]:
    predicates: set[Any] = set()
    for inst in instances:
        predicates.update(p for p in data.predicates(inst, None) if p != RDF_TYPE and p not in ignored)
    return sorted(predicates, key=_sort_key)


def _close_shape(result: Any, shape_node: Any, ignored: set[Any], mint: _Minter) -> None:
    """Set ``sh:closed true`` and ``sh:ignoredProperties`` directly. Not ``StarShaclProcessor.close_shape()``: its value is walking
    ``sh:node`` / logical nesting, and derived output never has any, so there is nothing for that walk to find."""
    _clear_list_valued(result, shape_node, SH.ignoredProperties)
    result.remove((shape_node, SH.closed, None))
    result.add((shape_node, SH.closed, _TRUE))
    result.add((shape_node, SH.ignoredProperties, mint.rdf_list(result, sorted(ignored, key=_text))))


def _check_view(shapes: Any, data: Any, shape_node: Any, target: _Target) -> Any:
    """The shapes graph to validate: ``shapes`` itself, except that with ``include_subclasses=False`` the shape's class targets are
    replaced by its direct instances. ``sh:targetClass`` always reaches the subclass instances too, and a shape derived from the
    direct ones need not hold for them."""
    if target.kind != "cls" or target.include_subclasses:
        return shapes
    view = shapes.empty_like() if hasattr(shapes, "empty_like") else type(shapes)()
    view.extend(shapes.triples((None, None, None)))
    for cls in list(view.objects(shape_node, SH.targetClass)):
        view.remove((shape_node, SH.targetClass, cls))
        for inst in sorted(_instances_of(data, cls, False), key=_sort_key):
            view.add((shape_node, SH.targetNode, inst))
    return view


def _self_check(data: Any, shapes: Any, shape_node: Any, target: _Target) -> None:
    result = validate(data, shacl_graph=_check_view(shapes, data, shape_node, target))
    if result.conforms:
        return
    raise ExecutionError(
        "starlayer.shacl.derive_shape() produced a shape that does not conform against the data it was derived from - "
        f"this is a bug in the shape derivation, not expected behavior; please report it.\n{result.report_text}",
        kind="internal",
    )


def _derive_fresh(data: Any, target: _Target, shape_node: Any, ignored: set[Any], out: Any, mint: _Minter) -> Any:
    instances = sorted(target.instances(data), key=_sort_key)
    out.add((shape_node, RDF_TYPE, SH.NodeShape))
    out.add((shape_node, target.predicate, target.term))
    for pred in _class_predicates(data, instances, ignored):
        out.add((shape_node, SH.property, _derive_property_shape(out, data, instances, pred, mint)))
    _close_shape(out, shape_node, ignored, mint)
    _self_check(data, out, shape_node, target)
    return out


# ---- Phase B: template merge ---------------------------------------------------------------------------------------------

def _iter_violations(report_graph: Any) -> Iterable[dict[str, Any]]:
    for node in report_graph.subjects(RDF_TYPE, SH.ValidationResult):
        yield {
            "component": report_graph.value(node, SH.sourceConstraintComponent),
            "source_shape": report_graph.value(node, SH.sourceShape),
            "path": report_graph.value(node, SH.resultPath),
        }


def _recompute_component(
    working: Any, data: Any, shape_node: Any, instances: set[Any], path: Any, component: Any, mint: _Minter,
) -> bool:
    """Recompute ``component`` on ``shape_node`` from the true current data of the ``instances`` / ``path``. False when there is
    nothing to recompute from (no numeric values for a range component), so the caller drops and annotates instead."""
    counts, values = _counts_and_values(data, instances, path)

    if component == SH.MinCountConstraintComponent:
        working.remove((shape_node, SH.minCount, None))
        if (m := min(counts, default=0)) > 0:
            working.add((shape_node, SH.minCount, _int(m)))
        return True

    if component == SH.MaxCountConstraintComponent:
        working.remove((shape_node, SH.maxCount, None))
        working.add((shape_node, SH.maxCount, _int(max(counts, default=0))))
        return True

    if component == SH.DatatypeConstraintComponent:
        working.remove((shape_node, SH.datatype, None))
        if values and all(isinstance(v, ox.Literal) for v in values):
            buckets = {_literal_datatype_bucket(v) for v in values}
            if len(buckets) == 1 and None not in buckets:
                working.add((shape_node, SH.datatype, next(iter(buckets))))
        return True

    if component == SH.ClassConstraintComponent:
        working.remove((shape_node, SH["class"], None))
        shared = _shared_rdf_type(data, values)
        if shared is not None:
            working.add((shape_node, SH["class"], shared))
        return True

    if component == SH.NodeKindConstraintComponent:
        _clear_list_valued(working, shape_node, SH.nodeKind)
        _set_node_kind_constraints(working, data, shape_node, values, mint)
        return True

    if component in _INCLUSIVE_EXCLUSIVE_PREDICATE:
        nums = [n for v in values if (n := _number_of(v)) is not None]
        if not nums:
            return False
        pred = _INCLUSIVE_EXCLUSIVE_PREDICATE[component]
        working.remove((shape_node, pred, None))
        is_min = component in (SH.MinInclusiveConstraintComponent, SH.MinExclusiveConstraintComponent)
        bound = min(nums) if is_min else max(nums)
        if component in (SH.MinExclusiveConstraintComponent, SH.MaxExclusiveConstraintComponent):
            # an exclusive bound equal to the extreme value would reject it: step one past it
            bound = bound + (-1 if is_min else 1) if isinstance(bound, int) else math.nextafter(bound, -math.inf if is_min else math.inf)
        working.add((shape_node, pred, _number(bound)))
        return True

    if component in (SH.MinLengthConstraintComponent, SH.MaxLengthConstraintComponent):
        if not values:
            return False
        lengths = [len(_text(v)) for v in values]
        is_min = component == SH.MinLengthConstraintComponent
        pred = SH.minLength if is_min else SH.maxLength
        working.remove((shape_node, pred, None))
        working.add((shape_node, pred, _int(min(lengths) if is_min else max(lengths))))
        return True

    if component == SH.LanguageInConstraintComponent:
        _clear_list_valued(working, shape_node, SH.languageIn)
        langs = sorted({v.language for v in values if isinstance(v, ox.Literal) and v.language})
        # a value without a language tag fails sh:languageIn, so the constraint can only stay when every value is tagged
        if langs and all(isinstance(v, ox.Literal) and v.language for v in values):
            working.add((shape_node, SH.languageIn, mint.rdf_list(working, [ox.Literal(lang) for lang in langs])))
        return True

    if component == SH.InConstraintComponent:
        old = working.value(shape_node, SH["in"])
        existing = _list_items(working, old) if old is not None else []
        merged = existing + sorted((v for v in values if v not in existing), key=_sort_key)
        _clear_list_valued(working, shape_node, SH["in"])
        working.add((shape_node, SH["in"], mint.rdf_list(working, merged)))
        return True

    return False


class _Changes:
    """What the derivation changed in the template shape, for the one comment on the node shape. ``text()`` lists them in a fixed
    order (added, loosened, deactivated; then by property, then by constraint), so the comment is the same every run."""

    def __init__(self) -> None:
        self.added: list[tuple[str, str]] = []
        self.loosened: list[tuple[str, str, str]] = []
        self.deactivated: list[tuple[str, str, str]] = []

    def __bool__(self) -> bool:
        return bool(self.added or self.loosened or self.deactivated)

    def text(self) -> str:
        lines = [_COMMENT_HEADER]
        lines += [f"Added property {where}: {why}." for where, why in sorted(self.added)]
        lines += [f"Loosened {where} {what}: {why}." for where, what, why in sorted(self.loosened)]
        lines += [f"Deactivated {where} {what}: {why}." for where, what, why in sorted(self.deactivated)]
        return "\n".join(lines)


_BARE = frozenset(_XSD + n for n in ("integer", "decimal", "double", "boolean"))


def _show(g: Any, term: Any) -> str:
    """A term as Turtle for the comment; a number or boolean is bare (``2``, not ``"2"^^xsd:integer``)."""
    if isinstance(term, ox.Literal) and term.datatype.value in _BARE:
        return term.value
    return g.qname_term(term)


def _show_values(g: Any, node: Any, predicates: Iterable[Any]) -> str:
    """The values of ``predicates`` on ``node`` as Turtle, lists in parentheses; empty when there are none."""
    parts = []
    for pred in predicates:
        for v in sorted(g.objects(node, pred), key=_sort_key):
            if isinstance(v, ox.BlankNode) and (v, RDF_FIRST, None) in g:
                parts.append("(" + " ".join(_show(g, i) for i in _list_items(g, v)) + ")")
            else:
                parts.append(_show(g, v))
    return " ".join(parts)


def _shown_constraint(g: Any, node: Any, pred: Any, values: list[Any]) -> str:
    """``sh:pattern "^[a-z]+$"``: the predicate and its value; a blank node value (an ``sh:sparql`` constraint) is left out."""
    shown = [_show(g, v) for v in sorted(values, key=_sort_key) if not isinstance(v, ox.BlankNode)]
    return " ".join([g.qname_term(pred), *shown])


def _where(g: Any, shape: Any, main: Any) -> str:
    """Where a constraint sits, for the comment: the property's path, or the shape itself when it has no simple path."""
    paths = list(g.objects(shape, SH.path))
    if len(paths) == 1 and isinstance(paths[0], ox.NamedNode):
        return g.qname_term(paths[0])
    if paths:
        return "a property with a complex path"
    if shape == main:
        return "the shape"
    return f"shape {g.qname_term(shape)}" if isinstance(shape, ox.NamedNode) else "a nested shape"


def _violated_values(
    working: Any, data: Any, shape_node: Any, target: _Target, source: Any, component: Any, pred: Any, values: list[Any],
) -> list[Any]:
    """Which of several values of one parameter the data breaks: each is validated alone. One value is the answer without a check."""
    if len(values) < 2:
        return values
    view = _check_view(working, data, shape_node, target)
    broken = []
    for keep in values:
        probe = view.empty_like() if hasattr(view, "empty_like") else type(view)()
        probe.extend(t for t in view.triples((None, None, None)) if not (t[0] == source and t[1] == pred and t[2] != keep))
        report = validate(data, shacl_graph=probe).report_graph
        if any(v["component"] == component and v["source_shape"] == source for v in _iter_violations(report)):
            broken.append(keep)
    return broken or values


def _deactivate(
    working: Any, data: Any, shape_node: Any, target: _Target, source: Any, component: Any, specs: list, mint: _Minter,
    changes: _Changes,
) -> None:
    """Switch off the constraint the data breaks with ``{| sh:deactivated true |}`` on its own triple. A component of several
    parameters is one constraint and any of its triples switches it off, so the first parameter present carries it (the engine skips the whole constraint, so with several values of that parameter, such as two
    ``sh:pattern``, all are switched off and listed)."""
    spec = next((sp for sp in specs if sp.iri == component), None)
    if spec is None:
        return  # unknown component: the final check reports it
    for pred in spec.predicates:
        values = sorted(working.objects(source, pred), key=_sort_key)
        if not values:
            continue
        if len(spec.predicates) == 1:
            values = _violated_values(working, data, shape_node, target, source, component, pred, values)
        for value in values:
            reifier = mint.node(working)
            working.add((reifier, _RDF_REIFIES, ox.Triple(source, pred, value)))
            working.add((reifier, SH.deactivated, _TRUE))
        what = _shown_constraint(working, source, pred, values)
        if component == SH.SPARQLConstraintComponent or not _text(component).startswith(_SH_NS):
            why = "the data breaks it and it cannot be checked or recomputed (an opaque constraint)"
        else:
            why = "the data breaks it and it cannot be recomputed from the data"
        changes.deactivated.append((_where(working, source, shape_node), what, why))
        return


def _extend_new_properties(
    working: Any, data: Any, shape_node: Any, target: _Target, ignored: set[Any], mint: _Minter, changes: _Changes,
) -> None:
    """Add a property shape for each predicate the target's instances use that the template shape does not cover."""
    instances = sorted(_shape_instances(working, data, shape_node, target.include_subclasses) or target.instances(data), key=_sort_key)
    existing = {p for prop in working.objects(shape_node, SH.property) for p in working.objects(prop, SH.path)}
    for pred in _class_predicates(data, instances, ignored):
        if pred not in existing:
            working.add((shape_node, SH.property, _derive_property_shape(working, data, instances, pred, mint)))
            changes.added.append((working.qname_term(pred), "the data has it and the template shape does not"))


def _carry_forward_ignored_properties(working: Any, shape_node: Any, ignored: set[Any], mint: _Minter) -> None:
    old = working.value(shape_node, SH.ignoredProperties)
    existing = _list_items(working, old) if old is not None else []
    merged = sorted(set(existing) | ignored, key=_text)
    _clear_list_valued(working, shape_node, SH.ignoredProperties)
    working.add((shape_node, SH.ignoredProperties, mint.rdf_list(working, merged)))


def _copy_scoped_template(template: Any, target: _Target, shape: Any, working: Any) -> Any:
    """Copy into ``working`` the one template shape that targets ``target`` and what it references; return its node."""
    candidates = sorted(set(template.subjects(target.predicate, target.term)), key=_sort_key)
    label = "class" if target.kind == "cls" else "node"
    if not candidates:
        raise ValueError(f"template_graph has no shape with {target.predicate.value.rsplit('#', 1)[-1]} {target.term} (the {label} to derive for)")
    if len(candidates) > 1:
        if shape not in candidates:
            raise ValueError(
                f"template_graph has {len(candidates)} shapes for the {label} {target.term}: "
                f"{', '.join(str(c) for c in candidates)}; name the one to use with shape="
            )
        candidates = [shape]
    main = candidates[0]
    for node in [main, *sorted(referenced_shapes(template, [main]), key=_sort_key)]:
        template.cbd(node, target_graph=working)
    _copy_declarations(template, working)
    return main


def _copy_declarations(template: Any, working: Any) -> None:
    """Copy what the copied shapes need to be read: the declaration of each custom ``sh:ConstraintComponent`` one of them uses a
    parameter of (without it the parameter is an ordinary triple and the constraint silently checks nothing), and the
    ``sh:prefixes`` declarations of their SPARQL text."""
    used = {p for _s, p, _o in working.triples((None, None, None))}
    for comp in sorted(template.subjects(RDF_TYPE, SH.ConstraintComponent), key=_sort_key):
        params = {path for par in template.objects(comp, SH.parameter) for path in template.objects(par, SH.path)}
        if params & used:
            template.cbd(comp, target_graph=working)
            for pred in (SH.validator, SH.nodeValidator, SH.propertyValidator):
                for validator in template.objects(comp, pred):
                    template.cbd(validator, target_graph=working)
    for _s, _p, decl in list(working.triples((None, SH.prefixes, None))):
        template.cbd(decl, target_graph=working)
        for entry in template.objects(decl, SH.declare):
            template.cbd(entry, target_graph=working)


def _rename(g: Any, old: Any, new: Any) -> None:
    for s, p, o in list(g.triples((old, None, None))):
        g.remove((s, p, o))
        g.add((new, p, o))
    for s, p, o in list(g.triples((None, None, old))):
        g.remove((s, p, o))
        g.add((s, p, new))


def _derive_with_template(
    data: Any, template: Any, target: _Target, shape: Any, ignored: set[Any], working: Any, mint: _Minter,
) -> Any:
    shape_node = _copy_scoped_template(template, target, shape, working)
    if shape is not None and shape != shape_node:
        _rename(working, shape_node, shape)
        shape_node = shape

    from starlayer.shacl.engine.plan import Plan

    specs = Plan(working).components()
    changes = _Changes()
    detect = validate(data, shacl_graph=_check_view(working, data, shape_node, target))
    seen: set[tuple[Any, Any]] = set()
    violations = sorted(
        (v for v in _iter_violations(detect.report_graph) if v["source_shape"] is not None and v["component"] is not None),
        key=lambda v: (_sort_key(v["source_shape"]), _sort_key(v["component"]), _sort_key(v["path"]) if v["path"] is not None else ("", "")),
    )
    for violation in violations:
        component, source = violation["component"], violation["source_shape"]
        if component == SH.ClosedConstraintComponent or (component, source) in seen:
            # _extend_new_properties finds every uncovered predicate straight from the data, so the closed-shape violation
            # this situation also produces needs no reaction of its own.
            continue
        seen.add((component, source))
        if (source, None, None) not in working:
            continue  # the shape was renamed or is not in the copy: nothing to change
        if component in _RECOMPUTE_COMPONENTS:
            focus, path = _shape_instances(working, data, source, target.include_subclasses), violation["path"]
            preds = _RECOMPUTE_PREDICATES[component]
            before = _show_values(working, source, preds)
            if (
                focus is not None and path is not None
                and _recompute_component(working, data, source, focus, path, component, mint)
            ):
                after = _show_values(working, source, preds)
                if before != after:
                    changes.loosened.append((
                        _where(working, source, shape_node), f"{working.qname_term(preds[0])} from {before} to {after or 'no constraint'}",
                        _RECOMPUTE_REASON[component],
                    ))
                continue
        _deactivate(working, data, shape_node, target, source, component, specs, mint, changes)

    _extend_new_properties(working, data, shape_node, target, ignored, mint, changes)
    _carry_forward_ignored_properties(working, shape_node, ignored, mint)
    working.remove((shape_node, SH.closed, None))
    working.add((shape_node, SH.closed, _TRUE))
    if changes:
        for old in list(working.objects(shape_node, RDFS.comment)):  # the comment of an earlier derivation is replaced, not stacked
            if isinstance(old, ox.Literal) and old.value.startswith(_COMMENT_HEADER):
                working.remove((shape_node, RDFS.comment, old))
        working.add((shape_node, RDFS.comment, ox.Literal(changes.text())))
    _self_check(data, working, shape_node, target)
    return working


# ---- public entry point --------------------------------------------------------------------------------------------------

def _as_term(value: Any, name: str, *, allowed: tuple[type, ...]) -> Any:
    """``value`` as a pyoxigraph term; a ``str`` is an IRI. An rdflib term is a ``TypeError`` (``to_engine``)."""
    term = ox.NamedNode(value) if type(value) is str else to_engine(value)
    if not isinstance(term, allowed):
        wanted = " or ".join(t.__name__ for t in allowed)
        raise TypeError(f"{name} must be a {wanted} (or an IRI string), not {type(term).__name__}: {term!r}")
    return term


def _auto_shape_name(target: Any) -> ox.NamedNode | None:
    """``ex:Person`` -> ``ex:PersonShape``: the target's namespace and local name (after the last ``#`` or ``/``) with the first
    letter upper-cased, plus ``Shape``. None for a blank node or an empty local name."""
    if not isinstance(target, ox.NamedNode):
        return None
    iri = target.value
    cut = max(iri.rfind("#"), iri.rfind("/")) + 1
    local = iri[cut:]
    if not cut or not local:
        return None
    return ox.NamedNode(iri[:cut] + local[0].upper() + local[1:] + "Shape")


def derive_shape(
    graph: Any,
    *,
    cls: Any = None,
    node: Any = None,
    shape: Any = None,
    template_graph: Any = None,
    ignored_properties: Any = None,
    use_default_ignored_properties: bool = True,
    include_subclasses: bool = True,
) -> Any:
    """Derive one closed ``sh:NodeShape`` from the data: a StarLayer feature, not part of SHACL. It exists so that a shape can be
    started from the data that is already there and then edited, instead of written from nothing. Returns a new
    ``StarLayerGraph`` with ``graph``'s prefixes plus ``sh`` and nothing but that shape (and its property shapes); ``graph`` is
    never changed.

    Give exactly one of ``cls`` and ``node``. With ``cls`` the shape has ``sh:targetClass`` and describes all instances of the
    class: the nodes typed with it and, unless ``include_subclasses`` is False, those typed with an ``rdfs:subClassOf`` subclass of
    it in the data graph (SHACL's own reading of ``sh:targetClass``). With ``node`` it has ``sh:targetNode`` and describes that one
    node from its own triples, so its counts are what that node has; a blank node is allowed. For each predicate the instances use
    there is a property shape with the observed ``sh:minCount`` and ``sh:maxCount`` (the minimum is omitted when it is 0), and with
    ``sh:datatype``, ``sh:class`` (when every value shares one ``rdf:type``), ``sh:nodeKind`` (a list when the kinds are mixed;
    triple terms included) or ``sh:languageIn``, whichever the values support. The shape is ``sh:closed`` and ignores ``rdf:type``
    and, unless ``use_default_ignored_properties`` is False, ``rdfs:label``, ``rdfs:comment``, ``dcterms:created`` and
    ``dcterms:modified``, plus ``ignored_properties``. Those are left out of the property shapes.

    The shape is named by ``shape`` (an IRI). Without it, the shape gets an IRI in the target's namespace: its local name (after the
    last ``#`` or ``/``) with the first letter upper-cased, plus ``Shape``, so ``ex:Person`` gives ``ex:PersonShape`` and
    ``ex:alice`` gives ``ex:AliceShape``. A blank node target, or an IRI without a local name, gives a blank node shape.

    ``template_graph`` is a graph, not a node: a StarLayer graph that holds an earlier version of the shape to keep up to date. The
    shape in it is found by its target, not named: the one that targets the same class (``sh:targetClass``) or node
    (``sh:targetNode``) is used, together with what it references (its property shapes, lists, ``sh:node`` and logical shapes); the
    other shapes of the template graph are not copied. When it holds several shapes for that target, ``shape`` names the one to use;
    when it holds one, ``shape`` renames the result, which otherwise keeps the template shape's identity.

    The template is brought up to date by loosening, never tightening: a constraint the data satisfies stays exactly as it is,
    and so does a property the data lacks. A constraint the data breaks is recomputed from the data when there is a principled way
    (counts, datatype, class, node kind, ranges, lengths, languages, ``sh:in`` widened). When there is none (``sh:pattern``,
    ``sh:hasValue``, pair comparisons) or it cannot be checked at all (``sh:sparql``, custom components) it is deactivated, not
    dropped, with a reifier on that one triple (``{| sh:deactivated true |}``), so a reader still sees what was switched off and
    the engine still skips it. Predicates the template does not cover are added, and its ignored properties are kept. Only the
    main shape is closed, not shapes it merely references. The declarations of the custom constraint components the shape uses
    are copied along, or the parameter would be an ordinary triple that checks nothing.

    Every change is written in one ``rdfs:comment`` on the node shape, one line each in a fixed order (properties added,
    constraints loosened, constraints deactivated); no comment when nothing changed. A comment of an earlier derivation is
    replaced, not added to.

    The result is validated against ``graph``, for the shape's own targets only, before it is returned. With
    ``include_subclasses=False`` the shape still targets subclass instances under SHACL's rules, so validating it by hand reports
    those that have other properties.

    Raises:
        ValueError: neither or both of ``cls`` and ``node`` are given; the class has no instances, or the node no triples as
            subject; the template has no shape for the target, or several (and none is ``shape``).
        TypeError: a term is an rdflib term or of a kind the argument does not take, or a graph is not a StarLayer graph.
    """
    if (cls is None) == (node is None):
        raise ValueError("derive_shape() needs exactly one of cls= and node=" + (" (got both)" if cls is not None else " (got neither)"))
    data = engine_view(normalize_to_starlayer_graph(graph, name="graph"), "graph")
    if cls is not None:
        target = _Target("cls", _as_term(cls, "cls", allowed=(ox.NamedNode,)), include_subclasses)
    else:
        target = _Target("node", _as_term(node, "node", allowed=(ox.NamedNode, ox.BlankNode)), include_subclasses)
    shape_term = None if shape is None else _as_term(shape, "shape", allowed=(ox.NamedNode,))
    ignored: set[Any] = set(_ALWAYS_IGNORED)
    if use_default_ignored_properties:
        ignored |= DEFAULT_IGNORED_PROPERTIES
    ignored |= {_as_term(p, "ignored_properties", allowed=(ox.NamedNode,)) for p in ignored_properties or ()}

    if target.kind == "cls":
        if not target.instances(data):
            raise ValueError(f"no instances of {target.term} in the graph (include_subclasses={include_subclasses})")
    elif not any(True for _ in data.triples((target.term, None, None))):
        raise ValueError(f"no triples with {target.term} as subject in the graph")

    from starlayer.graph.core import StarLayerGraph

    out = StarLayerGraph(prefixes=dict(graph.prefixes))
    out.prefixes.setdefault("sh", _SH_NS)
    mint = _Minter(f"{target.kind}|{target.term}")
    if template_graph is not None:
        template = engine_view(normalize_to_starlayer_graph(template_graph, name="template_graph"), "template_graph")
        return _derive_with_template(data, template, target, shape_term, ignored, out, mint)
    shape_node = shape_term or _auto_shape_name(target.term) or mint.node(out)
    return _derive_fresh(data, target, shape_node, ignored, out, mint)
