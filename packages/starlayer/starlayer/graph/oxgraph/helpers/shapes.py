"""``derive_shape``: infer a SHACL shapes graph from the data of an ``StarLayerGraph`` / ``StarLayerDataset``.

One ``sh:NodeShape`` per distinct ``rdf:type`` found (never per-node or heuristic clustering), optionally reconciled against
a template shape. Native over pyoxigraph terms and the wrapper API (no rdflib). The rdflib module
``graph/graph/shape_derivation.py`` is no longer called by the library (it is kept only for its ``DEFAULT_IGNORED_PROPERTIES``
constant that a test reads; D4 backlog).

Two phases:

- Phase A (fresh derivation) is the whole algorithm without a template: pure graph analysis, then a self-check.
- Phase B (template merge) validates the template against the data once and dispatches each violation by its
  ``sh:sourceConstraintComponent``: components with a principled data-driven fix are recomputed from the true current data
  (``_RECOMPUTE_COMPONENTS``); those with none (``sh:pattern``, cross-property comparisons) are dropped with an
  ``rdfs:comment`` (``_DROP_COMPONENTS``); an opaque one (``sh:sparql``, custom) is left with a comment.

Value kinds are Literal, IRI, BlankNode and TripleTerm (SHACL 1.2's ``sh:nodeKind sh:TripleTerm``, list-valued when mixed), so a
triple-term-valued property is never silently dropped. Both phases end by validating the result against the same data through
``starlayer.shacl`` (imported lazily; it imports this package): Phase A's result must conform; Phase B's must conform except
at the opaque violations deliberately left alone.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms
from starlayer.shacl_engine.terms import NS

SH = NS("http://www.w3.org/ns/shacl#")
RDFS = NS("http://www.w3.org/2000/01/rdf-schema#")
DCTERMS = NS("http://purl.org/dc/terms/")
_XSD = "http://www.w3.org/2001/XMLSchema#"
_SH_NS = "http://www.w3.org/ns/shacl#"

RDF_TYPE, RDF_FIRST, RDF_REST, RDF_NIL = terms.RDF_TYPE, terms.RDF_FIRST, terms.RDF_REST, terms.RDF_NIL
_XSD_INTEGER = ox.NamedNode(_XSD + "integer")
_XSD_DOUBLE = ox.NamedNode(_XSD + "double")
_XSD_BOOLEAN = ox.NamedNode(_XSD + "boolean")
_TRUE = ox.Literal("true", datatype=_XSD_BOOLEAN)

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

# Components with no generic auto-fix: dropped outright, with an rdfs:comment note.
_DROP_COMPONENTS = frozenset({
    SH.PatternConstraintComponent, SH.HasValueConstraintComponent, SH.EqualsConstraintComponent,
    SH.DisjointConstraintComponent, SH.LessThanConstraintComponent, SH.LessThanOrEqualsConstraintComponent,
})

_COMPONENT_TO_PREDICATES = {
    SH.PatternConstraintComponent: (SH.pattern, SH.flags),
    SH.HasValueConstraintComponent: (SH.hasValue,),
    SH.EqualsConstraintComponent: (SH.equals,),
    SH.DisjointConstraintComponent: (SH.disjoint,),
    SH.LessThanConstraintComponent: (SH.lessThan,),
    SH.LessThanOrEqualsConstraintComponent: (SH.lessThanOrEquals,),
}

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


def _term_kind(v: Any) -> str:
    if isinstance(v, ox.Triple):
        return "TripleTerm"
    if isinstance(v, ox.Literal):
        return "Literal"
    if isinstance(v, ox.BlankNode):
        return "BlankNode"
    if isinstance(v, ox.NamedNode):
        return "IRI"
    raise TypeError(f"unrecognized RDF term for shape derivation: {v!r}")


def _literal_datatype_bucket(lit: ox.Literal) -> ox.NamedNode | None:
    """None for a language-tagged literal (no fixed datatype), else its datatype (xsd:string for a plain one)."""
    return None if lit.language else lit.datatype


def _build_rdf_list(g: Any, items: Iterable[Any]) -> Any:
    items = list(items)
    if not items:
        return RDF_NIL
    cells = [ox.BlankNode() for _ in items]
    for cell, item, nxt in zip(cells, items, [*cells[1:], RDF_NIL], strict=True):
        g.add((cell, RDF_FIRST, item))
        g.add((cell, RDF_REST, nxt))
    return cells[0]


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
    seen = set()
    while node is not None and node != RDF_NIL and node not in seen:
        seen.add(node)
        nxt = g.value(node, RDF_REST)
        g.remove((node, None, None))
        node = nxt


def _clear_list_valued(g: Any, node: Any, pred: Any) -> None:
    """Remove ``pred``'s value from ``node``, freeing its list cells too when it is list-valued."""
    old = g.value(node, pred)
    if old is None:
        return
    if isinstance(old, ox.BlankNode) and (old, RDF_FIRST, None) in g:
        _remove_rdf_list(g, old)
    g.remove((node, pred, old))


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
    from starlayer.shacl_engine import xsd_values

    n = xsd_values.numeric(v)
    return None if isinstance(n, Decimal) else n


# ---- value kinds -> sh:datatype / sh:class / sh:nodeKind / sh:languageIn -------------------------------------------------

def _set_node_kind_constraints(g: Any, data: Any, prop_node: Any, values: set[Any]) -> None:
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
            g.add((prop_node, SH.languageIn, _build_rdf_list(g, [ox.Literal(lang) for lang in langs])))
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
    g.add((prop_node, SH.nodeKind, _build_rdf_list(g, kind_terms)))


# ---- Phase A: fresh derivation -------------------------------------------------------------------------------------------

def _counts_and_values(data: Any, instances: Iterable[Any], predicate: Any) -> tuple[list[int], set[Any]]:
    counts, values = [], set()
    for inst in instances:
        vs = list(data.objects(inst, predicate))
        counts.append(len(vs))
        values.update(vs)
    return counts, values


def _derive_property_shape(g: Any, data: Any, instances: Iterable[Any], predicate: Any) -> ox.BlankNode:
    counts, values = _counts_and_values(data, instances, predicate)
    prop_node = ox.BlankNode()
    g.add((prop_node, RDF_TYPE, SH.PropertyShape))
    g.add((prop_node, SH.path, predicate))
    if (min_count := min(counts, default=0)) > 0:
        g.add((prop_node, SH.minCount, _int(min_count)))
    g.add((prop_node, SH.maxCount, _int(max(counts, default=0))))
    _set_node_kind_constraints(g, data, prop_node, values)
    return prop_node


def _class_predicates(data: Any, instances: Iterable[Any], ignored: set[Any]) -> set[Any]:
    predicates: set[Any] = set()
    for inst in instances:
        predicates.update(p for p in data.predicates(inst, None) if p != RDF_TYPE and p not in ignored)
    return predicates


def _derive_class_shape(result: Any, data: Any, cls: Any, ignored: set[Any]) -> ox.BlankNode:
    instances = set(data.subjects(RDF_TYPE, cls))
    shape_node = ox.BlankNode()
    result.add((shape_node, RDF_TYPE, SH.NodeShape))
    result.add((shape_node, SH.targetClass, cls))
    for pred in _class_predicates(data, instances, ignored):
        result.add((shape_node, SH.property, _derive_property_shape(result, data, instances, pred)))
    _close_shape(result, shape_node, ignored)
    return shape_node


def _close_shape(result: Any, shape_node: Any, ignored: set[Any]) -> None:
    """Set ``sh:closed true`` and ``sh:ignoredProperties`` directly. Not ``starlayer.shacl.close_shape()``: its value is walking
    ``sh:node`` / logical nesting, and derived output never has any, so there is nothing for that walk to find."""
    _clear_list_valued(result, shape_node, SH.ignoredProperties)
    result.remove((shape_node, SH.closed, None))
    result.add((shape_node, SH.closed, _TRUE))
    result.add((shape_node, SH.ignoredProperties, _build_rdf_list(result, sorted(ignored, key=_text))))


def _self_check(data: Any, shapes: Any, *, allow_opaque_only: bool = False) -> None:
    import starlayer.shacl

    result = starlayer.shacl.validate(data, shacl_graph=shapes)
    if result.conforms:
        return
    if allow_opaque_only:
        leftover = {v["component"] for v in _iter_violations(result.report_graph)}
        if not (leftover & (_RECOMPUTE_COMPONENTS | _DROP_COMPONENTS)):  # only opaque components remain
            return
    raise RuntimeError(
        "starlayer.graph.derive_shape() produced a shape that does not conform against the data it was derived from - "
        f"this is a bug in the shape derivation, not expected behavior.\n{result.report_text}"
    )


def _derive_fresh(data: Any, ignored: set[Any], out: Any) -> Any:
    for cls in set(data.objects(None, RDF_TYPE)):
        _derive_class_shape(out, data, cls, ignored)
    _self_check(data, out)
    return out


# ---- Phase B: template merge ---------------------------------------------------------------------------------------------

def _iter_violations(report_graph: Any) -> Iterable[dict[str, Any]]:
    for node in report_graph.subjects(RDF_TYPE, SH.ValidationResult):
        yield {
            "component": report_graph.value(node, SH.sourceConstraintComponent),
            "source_shape": report_graph.value(node, SH.sourceShape),
            "path": report_graph.value(node, SH.resultPath),
        }


def _owning_target_class(working: Any, shape_node: Any) -> Any:
    for ns in working.subjects(SH.property, shape_node):
        cls = working.value(ns, SH.targetClass)
        if cls is not None:
            return cls
    return working.value(shape_node, SH.targetClass)


def _recompute_component(working: Any, data: Any, shape_node: Any, cls: Any, path: Any, component: Any) -> bool:
    """Recompute ``component`` on ``shape_node`` from the true current data for ``cls`` / ``path``. False when there is nothing
    to recompute from (no numeric values for a range component), so the caller drops and annotates instead."""
    counts, values = _counts_and_values(data, set(data.subjects(RDF_TYPE, cls)), path)

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
        _set_node_kind_constraints(working, data, shape_node, values)
        return True

    if component in _INCLUSIVE_EXCLUSIVE_PREDICATE:
        nums = [n for v in values if (n := _number_of(v)) is not None]
        if not nums:
            return False
        pred = _INCLUSIVE_EXCLUSIVE_PREDICATE[component]
        working.remove((shape_node, pred, None))
        is_min = component in (SH.MinInclusiveConstraintComponent, SH.MinExclusiveConstraintComponent)
        working.add((shape_node, pred, _number(min(nums) if is_min else max(nums))))
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
        if langs:
            working.add((shape_node, SH.languageIn, _build_rdf_list(working, [ox.Literal(lang) for lang in langs])))
        return True

    if component == SH.InConstraintComponent:
        old = working.value(shape_node, SH["in"])
        existing = _list_items(working, old) if old is not None else []
        merged = existing + [v for v in values if v not in existing]
        _clear_list_valued(working, shape_node, SH["in"])
        working.add((shape_node, SH["in"], _build_rdf_list(working, merged)))
        return True

    return False


def _component_name(component: Any) -> str:
    return _text(component).rsplit("#", 1)[-1] if component else "unknown constraint"


def _drop_and_annotate(working: Any, shape_node: Any, component: Any) -> None:
    for pred in _COMPONENT_TO_PREDICATES.get(component, ()):
        working.remove((shape_node, pred, None))
    working.add((shape_node, RDFS.comment, ox.Literal(
        f"derive_shape(): {_component_name(component)} no longer holds for the current data and has no principled "
        "auto-fix - dropped."
    )))


def _annotate_opaque(working: Any, shape_node: Any, component: Any) -> None:
    working.add((shape_node, RDFS.comment, ox.Literal(
        f"derive_shape(): {_component_name(component)} could not be automatically verified or fixed (an opaque "
        "constraint, e.g. sh:sparql or a custom component) - left as-is; the derived shape may not conform on this point."
    )))


def _extend_new_properties_and_classes(working: Any, data: Any, ignored: set[Any]) -> None:
    class_to_shape = {}
    for ns in set(working.subjects(RDF_TYPE, SH.NodeShape)):
        for cls in working.objects(ns, SH.targetClass):
            class_to_shape[cls] = ns

    for cls in set(data.objects(None, RDF_TYPE)):
        instances = set(data.subjects(RDF_TYPE, cls))
        if cls in class_to_shape:
            ns_node = class_to_shape[cls]
            existing = {p for prop in working.objects(ns_node, SH.property) for p in working.objects(prop, SH.path)}
            for pred in _class_predicates(data, instances, ignored) - existing:
                working.add((ns_node, SH.property, _derive_property_shape(working, data, instances, pred)))
        else:
            _derive_class_shape(working, data, cls, ignored)


def _carry_forward_ignored_properties(working: Any, ignored: set[Any]) -> None:
    for ns in set(working.subjects(RDF_TYPE, SH.NodeShape)):
        old = working.value(ns, SH.ignoredProperties)
        existing = _list_items(working, old) if old is not None else []
        merged = sorted(set(existing) | ignored, key=_text)
        _clear_list_valued(working, ns, SH.ignoredProperties)
        working.add((ns, SH.ignoredProperties, _build_rdf_list(working, merged)))


def _close_all_node_shapes(working: Any) -> None:
    for ns in set(working.subjects(RDF_TYPE, SH.NodeShape)):
        working.remove((ns, SH.closed, None))
        working.add((ns, SH.closed, _TRUE))


def _derive_with_template(data: Any, template_shape: Any, ignored: set[Any], working: Any) -> Any:
    import starlayer.shacl

    working.extend(
        (terms.term(s), terms.term(p), terms.term(o)) for s, p, o in template_shape.triples((None, None, None))
    )

    detect = starlayer.shacl.validate(data, shacl_graph=working)
    for violation in list(_iter_violations(detect.report_graph)):
        component, shape_node = violation["component"], violation["source_shape"]
        if component == SH.ClosedConstraintComponent or shape_node is None:
            # _extend_new_properties_and_classes finds every uncovered predicate straight from the data, so the closed-shape
            # violation this situation also produces needs no reaction of its own.
            continue
        if component in _RECOMPUTE_COMPONENTS:
            cls, path = _owning_target_class(working, shape_node), violation["path"]
            handled = cls is not None and path is not None and _recompute_component(working, data, shape_node, cls, path, component)
            if not handled:
                _drop_and_annotate(working, shape_node, component)
        elif component in _DROP_COMPONENTS:
            _drop_and_annotate(working, shape_node, component)
        else:
            _annotate_opaque(working, shape_node, component)

    _extend_new_properties_and_classes(working, data, ignored)
    _carry_forward_ignored_properties(working, ignored)
    _close_all_node_shapes(working)
    _self_check(data, working, allow_opaque_only=True)
    return working


# ---- public entry point --------------------------------------------------------------------------------------------------

def derive_shape(g: Any, template_shape: Any = None, *, ignored_properties: Any = None, use_default_ignored_properties: bool = True) -> Any:
    """One closed ``sh:NodeShape`` per ``rdf:type`` found in ``g``, optionally reconciled with ``template_shape`` (an
    ``StarLayerGraph`` / ``StarLayerDataset``, or an rdflib graph whose terms are converted). ``ignored_properties`` are pyoxigraph
    ``NamedNode``s (rdflib IRIs are converted). Returns a new ``StarLayerGraph`` with ``g``'s prefixes plus ``sh``."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    ignored: set[Any] = set(_ALWAYS_IGNORED)
    if use_default_ignored_properties:
        ignored |= DEFAULT_IGNORED_PROPERTIES
    ignored |= {terms.term(p) for p in ignored_properties or ()}

    out = StarLayerGraph(prefixes=dict(g.prefixes))
    out.prefixes.setdefault("sh", _SH_NS)
    if template_shape is None:
        return _derive_fresh(g, ignored, out)
    return _derive_with_template(g, template_shape, ignored, out)
