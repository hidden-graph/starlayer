"""
starlayergraph.graph.shape_derivation

``StarLayerGraph.derive()`` - infer a SHACL shape from a graph's own data:
one ``sh:NodeShape`` per distinct ``rdf:type`` found (never per-node or
heuristic clustering - the simplest option, per the design this follows),
optionally reconciled against an existing template shape. See the approved
plan (`future_enhancements.md`'s shape-derivation SUGGESTION item) for the
full design rationale - summarized here, not re-derived.

**Always goes through ``starshacl``, never bare ``pyshacl``.** The data or a
template shape may be genuine RDF 1.2 content (triple terms) that only
``starshacl`` understands - this is why `packages/graph` depends on
`packages/shacl` at all (an intentional circular dependency with
`starsparql`'s own `graph`<->`sparql` cycle as direct precedent, not a
layering mistake). The actual ``import starshacl`` stays lazy, inside the
functions that need it, to avoid a circular *Python* import at interpreter
load time now that the package dependency graph has a real cycle - the same
"import order matters" caution `starsparql`'s own `CLAUDE.md` documents for
its existing cycle with `starlayergraph`.

Two phases:

- **Phase A (fresh derivation)** - always runs; the whole algorithm when no
  template is given. Pure RDF graph analysis, no SHACL validation needed at
  all (only a final self-check, see below).
- **Phase B (template merge)** - only when a template shape is given. Runs
  ``starshacl.validate()`` once to detect every violation, then dispatches
  each one by its ``sh:sourceConstraintComponent``: constraint types with a
  principled data-driven fix get recomputed from the *true* current data
  (not just patched around the one violating value); constraint types with
  no generic fix (``sh:pattern``, cross-property comparisons, opaque
  ``sh:sparql``/custom components) are either dropped-with-a-comment or, for
  the opaque case, left untouched-with-a-comment - see
  ``_RECOMPUTE_COMPONENTS``/``_DROP_COMPONENTS`` below for the exact table.

Value-kind analysis (Phase A step 3, reused by Phase B's recompute/extend
paths) recognizes four first-class kinds, not three: ``Literal``,
``URIRef``, ``BNode``, and **``TripleTerm``** - SHACL 1.2 has a real,
already-implemented node kind for this (``sh:nodeKind sh:TripleTerm``,
list-valued too, e.g. ``sh:nodeKind ( sh:IRI sh:TripleTerm )`` for a
mixed-kind property - see ``starshacl/native_components.py``'s
``_build_node_kind_component()``), so a triple-term-valued property must
never be silently dropped from the derived shape.

Both phases end with a **self-check**: run the derived/merged shape back
through ``starshacl.validate()`` against the same data. Phase A's result
must conform unconditionally - if it doesn't, that's a bug in this module,
not an expected outcome. Phase B's result must conform except at whatever
opaque (``sh:sparql``/custom-component) violations were deliberately left
untouched - anything else still failing is likewise a bug here.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS

from starlayergraph.model import TripleTerm

try:
    from rdflib.namespace import DCTERMS
except ImportError:  # pragma: no cover - present in every rdflib this project targets
    DCTERMS = Namespace("http://purl.org/dc/terms/")

# A plain Namespace, not rdflib.namespace.SH (a DefinedNamespace with a
# closed, SHACL-1.0/1.1-era term list) - sh:TripleTerm and other SHACL 1.2
# additions aren't in it and would raise AttributeError. Matches every
# SHACL-touching module in the sibling starshacl package (see e.g.
# starshacl/native_components.py) - not a project-local convention invented
# here.
SH = Namespace("http://www.w3.org/ns/shacl#")

# rdf:type is *not* automatically exempt from sh:closed's check (confirmed
# by reading pyshacl's own ClosedConstraintComponent: its ALWAYS_IGNORE set
# only covers the RDFS-entailment artifact (rdf:type, rdfs:Resource), not
# rdf:type in general) - so it must always be in sh:ignoredProperties for a
# derived closed shape to conform against its own targeted instances,
# unconditionally, never opted out of the way the bookkeeping list below is.
_ALWAYS_IGNORED = frozenset({RDF.type})

# Opt-outable (use_default_ignored_properties=False) default bookkeeping
# predicates - the one concrete example found in this repo's own SHACL
# docs/fixtures for "commonly ignored" is dcterms:created; rdfs:label/
# comment and dcterms:modified are the same class of non-structural
# metadata, added by direct analogy.
DEFAULT_IGNORED_PROPERTIES = frozenset({RDFS.label, RDFS.comment, DCTERMS.created, DCTERMS.modified})

_NODE_KIND_TERM = {
    'Literal': SH.Literal,
    'IRI': SH.IRI,
    'BlankNode': SH.BlankNode,
    'TripleTerm': SH.TripleTerm,
}

# Constraint components with a principled, data-driven "relax" - recompute
# fully from the true current data, not incrementally patched from the one
# violating value (see _recompute_component).
_RECOMPUTE_COMPONENTS = frozenset({
    SH.MinCountConstraintComponent, SH.MaxCountConstraintComponent,
    SH.DatatypeConstraintComponent, SH['ClassConstraintComponent'],
    SH.NodeKindConstraintComponent,
    SH.MinInclusiveConstraintComponent, SH.MaxInclusiveConstraintComponent,
    SH.MinExclusiveConstraintComponent, SH.MaxExclusiveConstraintComponent,
    SH.MinLengthConstraintComponent, SH.MaxLengthConstraintComponent,
    SH.LanguageInConstraintComponent, SH.InConstraintComponent,
})

# Constraint components with no generic, principled auto-fix - dropped
# outright (with an rdfs:comment note) rather than left silently failing.
_DROP_COMPONENTS = frozenset({
    SH.PatternConstraintComponent, SH.HasValueConstraintComponent,
    SH.EqualsConstraintComponent, SH.DisjointConstraintComponent,
    SH.LessThanConstraintComponent, SH.LessThanOrEqualsConstraintComponent,
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


# ---------------------------------------------------------------------------
# Term-kind / rdf:List helpers
# ---------------------------------------------------------------------------

def _term_kind(v) -> str:
    if isinstance(v, TripleTerm):
        return 'TripleTerm'
    if isinstance(v, Literal):
        return 'Literal'
    if isinstance(v, BNode):
        return 'BlankNode'
    if isinstance(v, URIRef):
        return 'IRI'
    raise TypeError(f'unrecognized RDF term for shape derivation: {v!r}')


def _literal_datatype_bucket(lit: Literal):
    """None for a language-tagged literal (not a fixed datatype); otherwise
    the literal's own datatype, or xsd:string for a plain untyped literal -
    RDF 1.1's own simple-literal/xsd:string equivalence, so a mix of the two
    spellings doesn't spuriously look like "different datatypes"."""
    if lit.language:
        return None
    from rdflib.namespace import XSD
    return lit.datatype or XSD.string


def _build_rdf_list(g: Graph, items):
    if not items:
        return RDF.nil
    node = BNode()
    Collection(g, node, list(items))
    return node


def _remove_rdf_list(g: Graph, list_node) -> None:
    while list_node is not None and list_node != RDF.nil:
        next_node = next(g.objects(list_node, RDF.rest), None)
        for p, o in list(g.predicate_objects(list_node)):
            g.remove((list_node, p, o))
        list_node = next_node


def _clear_list_valued(g: Graph, node, pred) -> None:
    """Remove pred's current value from node, freeing its rdf:List cells
    too if it's list-valued (vs. a bare scalar term)."""
    old = g.value(node, pred)
    if old is None:
        return
    if isinstance(old, BNode) and (old, RDF.first, None) in g:
        _remove_rdf_list(g, old)
    g.remove((node, pred, old))


def _shared_rdf_type(data, values):
    """The one rdf:type every value in `values` shares, or None if any
    value has no type at all, or the shared-type set isn't exactly one."""
    per_value_types = []
    for v in values:
        types = set(data.objects(v, RDF.type))
        if not types:
            return None
        per_value_types.append(types)
    common = set.intersection(*per_value_types) if per_value_types else set()
    return next(iter(common)) if len(common) == 1 else None


# ---------------------------------------------------------------------------
# Value-kind -> sh:datatype/sh:class/sh:nodeKind/sh:languageIn
# ---------------------------------------------------------------------------

def _set_node_kind_constraints(g: Graph, data, prop_node, values) -> None:
    if not values:
        return
    kinds = {_term_kind(v) for v in values}

    if kinds == {'Literal'}:
        buckets = {_literal_datatype_bucket(v) for v in values}
        if len(buckets) == 1 and None not in buckets:
            g.add((prop_node, SH.datatype, next(iter(buckets))))
            return
        g.add((prop_node, SH.nodeKind, SH.Literal))
        if all(v.language for v in values):
            langs = sorted({v.language for v in values})
            g.add((prop_node, SH.languageIn, _build_rdf_list(g, [Literal(lang) for lang in langs])))
        return

    if len(kinds) == 1 and kinds <= {'IRI', 'BlankNode'}:
        shared_class = _shared_rdf_type(data, values)
        if shared_class is not None:
            g.add((prop_node, SH['class'], shared_class))
            return
        g.add((prop_node, SH.nodeKind, _NODE_KIND_TERM[next(iter(kinds))]))
        return

    if kinds == {'TripleTerm'}:
        g.add((prop_node, SH.nodeKind, SH.TripleTerm))
        return

    if len(kinds) == 4:
        return  # every kind present at once - vacuous, omit sh:nodeKind entirely

    # Genuinely mixed (2-3 kinds) - SHACL 1.2's list-valued sh:nodeKind
    # names exactly what was observed, a real derivation, not a fallback.
    kind_terms = sorted((_NODE_KIND_TERM[k] for k in kinds), key=str)
    g.add((prop_node, SH.nodeKind, _build_rdf_list(g, kind_terms)))


# ---------------------------------------------------------------------------
# Phase A - fresh derivation
# ---------------------------------------------------------------------------

def _derive_property_shape(g: Graph, data, instances, predicate) -> BNode:
    counts = []
    values = set()
    for inst in instances:
        vs = list(data.objects(inst, predicate))
        counts.append(len(vs))
        values.update(vs)

    prop_node = BNode()
    g.add((prop_node, RDF.type, SH.PropertyShape))
    g.add((prop_node, SH.path, predicate))

    min_count = min(counts) if counts else 0
    max_count = max(counts) if counts else 0
    if min_count > 0:
        g.add((prop_node, SH.minCount, Literal(min_count)))
    g.add((prop_node, SH.maxCount, Literal(max_count)))

    _set_node_kind_constraints(g, data, prop_node, values)
    return prop_node


def _class_predicates(data, instances, ignored):
    predicates = set()
    for inst in instances:
        predicates.update(p for p in data.predicates(inst, None) if p != RDF.type and p not in ignored)
    return predicates


def _derive_class_shape(result: Graph, data, cls, ignored) -> BNode:
    instances = set(data.subjects(RDF.type, cls))
    shape_node = BNode()
    result.add((shape_node, RDF.type, SH.NodeShape))
    result.add((shape_node, SH.targetClass, cls))
    for pred in _class_predicates(data, instances, ignored):
        prop_node = _derive_property_shape(result, data, instances, pred)
        result.add((shape_node, SH.property, prop_node))
    _close_shape(result, shape_node, ignored)
    return shape_node


def _close_shape(result: Graph, shape_node, ignored) -> None:
    """Set sh:closed true + sh:ignoredProperties directly - two triples,
    no recursive walk needed. Deliberately not starshacl.close_shape():
    that function's value is walking sh:node/sh:qualifiedValueShape/logical-
    connective nesting to find every shape that also needs closing, and
    derive()'s own output never has any (sh:class only, never sh:node -
    see module docstring) - there's nothing for that walk to find beyond
    the one flat shape being closed directly here."""
    _clear_list_valued(result, shape_node, SH.ignoredProperties)
    result.remove((shape_node, SH.closed, None))
    result.add((shape_node, SH.closed, Literal(True)))
    result.add((shape_node, SH.ignoredProperties, _build_rdf_list(result, sorted(ignored, key=str))))


def _self_check(data, shapes: Graph, *, allow_opaque_only: bool = False) -> None:
    import starshacl

    result = starshacl.validate(data, shacl_graph=shapes)
    if result.conforms:
        return
    if allow_opaque_only:
        leftover = {v['component'] for v in _iter_violations(result.report_graph)}
        # Everything remaining must be an opaque (unrecognized) component -
        # i.e. not something this module claims to know how to fix.
        if not (leftover & (_RECOMPUTE_COMPONENTS | _DROP_COMPONENTS)):
            return
    raise RuntimeError(
        'starlayergraph.derive() produced a shape that does not conform against the '
        'data it was derived from - this is a bug in shape_derivation.py, not expected '
        f'behavior.\n{result.report_text}'
    )


def _derive_fresh(data, ignored) -> Graph:
    result = Graph()
    for cls in set(data.objects(None, RDF.type)):
        _derive_class_shape(result, data, cls, ignored)
    _self_check(data, result)
    return result


# ---------------------------------------------------------------------------
# Phase B - template merge
# ---------------------------------------------------------------------------

def _iter_violations(report_graph):
    for result_node in report_graph.subjects(RDF.type, SH.ValidationResult):
        yield {
            'component': report_graph.value(result_node, SH.sourceConstraintComponent),
            'source_shape': report_graph.value(result_node, SH.sourceShape),
            'path': report_graph.value(result_node, SH.resultPath),
            'focus_node': report_graph.value(result_node, SH.focusNode),
            'value': report_graph.value(result_node, SH.value),
        }


def _owning_target_class(working: Graph, shape_node):
    for ns in working.subjects(SH.property, shape_node):
        cls = working.value(ns, SH.targetClass)
        if cls is not None:
            return cls
    return working.value(shape_node, SH.targetClass)


def _recompute_component(working: Graph, data, shape_node, cls, path, component) -> bool:
    """Recompute the sub-constraint `component` on `shape_node` from the
    *true* current data for `cls`/`path` (not incrementally patched from
    the single violating value). Returns False if there's nothing to
    recompute from (e.g. no numeric values at all for a numeric-range
    component) - caller falls back to drop+annotate in that case."""
    instances = set(data.subjects(RDF.type, cls))
    counts = []
    values = set()
    for inst in instances:
        vs = list(data.objects(inst, path))
        counts.append(len(vs))
        values.update(vs)

    if component == SH.MinCountConstraintComponent:
        working.remove((shape_node, SH.minCount, None))
        m = min(counts) if counts else 0
        if m > 0:
            working.add((shape_node, SH.minCount, Literal(m)))
        return True

    if component == SH.MaxCountConstraintComponent:
        working.remove((shape_node, SH.maxCount, None))
        working.add((shape_node, SH.maxCount, Literal(max(counts) if counts else 0)))
        return True

    if component == SH.DatatypeConstraintComponent:
        working.remove((shape_node, SH.datatype, None))
        literals = [v for v in values if isinstance(v, Literal)]
        if literals and len(literals) == len(values):
            buckets = {_literal_datatype_bucket(v) for v in literals}
            if len(buckets) == 1 and None not in buckets:
                working.add((shape_node, SH.datatype, next(iter(buckets))))
        return True

    if component == SH['ClassConstraintComponent']:
        working.remove((shape_node, SH['class'], None))
        shared = _shared_rdf_type(data, values)
        if shared is not None:
            working.add((shape_node, SH['class'], shared))
        return True

    if component == SH.NodeKindConstraintComponent:
        _clear_list_valued(working, shape_node, SH.nodeKind)
        _set_node_kind_constraints(working, data, shape_node, values)
        return True

    if component in _INCLUSIVE_EXCLUSIVE_PREDICATE:
        nums = []
        for v in values:
            if not isinstance(v, Literal):
                continue
            try:
                n = v.toPython()
            except Exception:
                continue
            if isinstance(n, (int, float)) and not isinstance(n, bool):
                nums.append(n)
        if not nums:
            return False
        pred = _INCLUSIVE_EXCLUSIVE_PREDICATE[component]
        working.remove((shape_node, pred, None))
        is_min = component in (SH.MinInclusiveConstraintComponent, SH.MinExclusiveConstraintComponent)
        working.add((shape_node, pred, Literal(min(nums) if is_min else max(nums))))
        return True

    if component in (SH.MinLengthConstraintComponent, SH.MaxLengthConstraintComponent):
        if not values:
            return False
        lengths = [len(str(v)) for v in values]
        pred = SH.minLength if component == SH.MinLengthConstraintComponent else SH.maxLength
        working.remove((shape_node, pred, None))
        working.add((shape_node, pred, Literal(min(lengths) if pred == SH.minLength else max(lengths))))
        return True

    if component == SH.LanguageInConstraintComponent:
        _clear_list_valued(working, shape_node, SH.languageIn)
        langs = sorted({v.language for v in values if isinstance(v, Literal) and v.language})
        if langs:
            working.add((shape_node, SH.languageIn, _build_rdf_list(working, [Literal(lang) for lang in langs])))
        return True

    if component == SH['InConstraintComponent']:
        old = working.value(shape_node, SH['in'])
        existing = list(Collection(working, old)) if old is not None else []
        merged = existing + [v for v in values if v not in existing]
        _clear_list_valued(working, shape_node, SH['in'])
        working.add((shape_node, SH['in'], _build_rdf_list(working, merged)))
        return True

    return False


def _drop_and_annotate(working: Graph, shape_node, component) -> None:
    for pred in _COMPONENT_TO_PREDICATES.get(component, ()):
        for triple in list(working.triples((shape_node, pred, None))):
            working.remove(triple)
    name = str(component).rsplit('#', 1)[-1] if component else 'unknown constraint'
    working.add((shape_node, RDFS.comment, Literal(
        f'derive(): {name} no longer holds for the current data and has no principled '
        'auto-fix - dropped.'
    )))


def _annotate_opaque(working: Graph, shape_node, component) -> None:
    name = str(component).rsplit('#', 1)[-1] if component else 'unknown constraint'
    working.add((shape_node, RDFS.comment, Literal(
        f'derive(): {name} could not be automatically verified or fixed (an opaque '
        'constraint, e.g. sh:sparql or a custom component) - left as-is; the derived '
        'shape may not conform on this point.'
    )))


def _extend_new_properties_and_classes(working: Graph, data, ignored) -> None:
    class_to_shape = {}
    for ns in set(working.subjects(RDF.type, SH.NodeShape)):
        for cls in working.objects(ns, SH.targetClass):
            class_to_shape[cls] = ns

    for cls in set(data.objects(None, RDF.type)):
        instances = set(data.subjects(RDF.type, cls))
        if cls in class_to_shape:
            ns_node = class_to_shape[cls]
            existing_paths = {
                p for prop in working.objects(ns_node, SH.property) for p in working.objects(prop, SH.path)
            }
            for pred in _class_predicates(data, instances, ignored) - existing_paths:
                prop_node = _derive_property_shape(working, data, instances, pred)
                working.add((ns_node, SH.property, prop_node))
        else:
            _derive_class_shape(working, data, cls, ignored)


def _carry_forward_ignored_properties(working: Graph, ignored) -> None:
    for ns in set(working.subjects(RDF.type, SH.NodeShape)):
        old = working.value(ns, SH.ignoredProperties)
        existing = list(Collection(working, old)) if old is not None else []
        merged = sorted(set(existing) | ignored, key=str)
        _clear_list_valued(working, ns, SH.ignoredProperties)
        working.add((ns, SH.ignoredProperties, _build_rdf_list(working, merged)))


def _close_all_node_shapes(working: Graph) -> None:
    for ns in working.subjects(RDF.type, SH.NodeShape):
        working.remove((ns, SH.closed, None))
        working.add((ns, SH.closed, Literal(True)))


def _derive_with_template(data, template_shape, ignored) -> Graph:
    import starshacl

    working = Graph()
    for prefix, ns in template_shape.namespaces():
        working.bind(prefix, ns)
    for t in template_shape:
        working.add(t)

    detect = starshacl.validate(data, shacl_graph=working)
    for violation in list(_iter_violations(detect.report_graph)):
        component = violation['component']
        shape_node = violation['source_shape']
        if component == SH.ClosedConstraintComponent or shape_node is None:
            # Handled uniformly by _extend_new_properties_and_classes below,
            # which discovers every uncovered predicate directly from data -
            # no need to also react to the closed-shape violation this
            # exact situation independently produces.
            continue
        if component in _RECOMPUTE_COMPONENTS:
            cls = _owning_target_class(working, shape_node)
            path = violation['path']
            handled = cls is not None and path is not None and _recompute_component(
                working, data, shape_node, cls, path, component
            )
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def derive_shape(graph, template_shape=None, *, ignored_properties=None,
                  use_default_ignored_properties: bool = True) -> Graph:
    """See ``StarLayerGraph.derive()`` for the public docstring - this is
    the module `derive()` delegates to, mirroring `infer()`'s own delegation
    to `owl_dl.py`/`owl_dl_rustdl.py`."""
    ignored = set(_ALWAYS_IGNORED)
    if use_default_ignored_properties:
        ignored |= set(DEFAULT_IGNORED_PROPERTIES)
    ignored |= set(ignored_properties or ())

    if template_shape is None:
        return _derive_fresh(graph, ignored)
    return _derive_with_template(graph, template_shape, ignored)
