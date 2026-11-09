"""
starlayer.graph.serializers.manchester

Serialize RDF (a StarLayerGraph) to OWL 2 Manchester Syntax -
the reverse of starlayer.graph.parsers.manchester_parser. A genuinely
different, harder kind of problem than parsing: parsing is deterministic
(one syntax, one RDF shape); serializing is *pattern recognition* over a
flat, unordered triple set - recognizing which blank-node chains are
rdf:Lists, which bnodes are owl:Restrictions vs. ordinary structure,
which triples came from an owl:Axiom reification block and should become
an inline `Annotations:` prefix, and which frame type each subject
belongs under (from its rdf:type triples).

Even OWL API's own ManchesterOWLSyntaxRenderer doesn't attempt this from
raw triples - it renders from its already-parsed, typed OWLOntology
object model. This module follows the same shape: reconstruct the AST
manchester_parser.py already defines internally (see that module's
"Class-expression AST" / "Data ranges" sections - the tags used below are
exactly its tags, walked outside-in instead of built inside-out), then
render *that* to text.

Entry point: serialize_manchester(graph) -> str

Scope and known limitations (see docs/manchester_syntax_gap_analysis.md
for the parser's own equivalent table - this module targets the same
construct coverage in reverse):

  - The primary, tested correctness bar is round-tripping this project's
    own parse_manchester() output - the one shape guaranteed well-formed
    by construction. Arbitrary foreign RDF (hand-written Turtle, Protege
    output, ...) is a best-effort target, not a guarantee: a blank node
    this module can't recognize any pattern for raises ValueError rather
    than being silently dropped or mis-rendered (matching every other
    serializer in this package - see rdfxml12.py).
  - `SuperClassOf:`/`SuperPropertyOf:` are surface sugar with no RDF-level
    trace (they produce the exact same triple as the reversed
    `SubClassOf:`/`SubPropertyOf:` spelling) - this module always emits
    the `SubClassOf:`/`SubPropertyOf:` direction, never the "Super" one.
  - `onlysome` is also pure surface sugar (expands to `(p some C) and
    (p only C)`, an ordinary intersectionOf of two ordinary restrictions
    at the RDF level) - this module always renders the expanded and/some/
    only form, never reconstructs `onlysome`. Both are valid Manchester
    syntax with identical RDF meaning.
  - `EquivalentClasses:`/`SameIndividual:`/binary (2-member)
    `DisjointClasses:`/`DisjointProperties:`/`DifferentIndividuals:` Misc
    axioms are RDF-indistinguishable from the same triples split across
    each entity's own frame (owl:equivalentClass and friends look
    identical either way) - this module renders via the per-subject
    frame clause when the subject has a frame, and as a two-member Misc
    axiom (a `SuperClassOf:` clause for a subclass axiom whose subject
    is a class expression) when it has none, e.g. a name the parser never
    declared. The >2-member `AllDisjointClasses`/`AllDisjointProperties`/
    `AllDifferent` shape *is* unambiguous (only a Misc axiom produces it)
    and is reconstructed, with its `Annotations:`.
  - A blank node that is the subject of a triple and part of no class
    expression, data range, list or reification block is an anonymous
    individual (`Individual: _:b`).
  - Not representable, so a ValueError rather than a rewritten term: a
    literal with a base direction, a triple term, a version IRI on an
    anonymous ontology, a subclass axiom with a class expression on both
    sides.

A note on validating this against the oracle (the same OWL API jar used
throughout this parser/serializer effort - see manchester_parser.py's own
docstring): round-tripping *this module's own* output back through
parse_manchester() has been isomorphic in every construct tested, and the
oracle's real parser accepts this module's output without a syntax error
in every case tried too - but comparing the oracle's *resulting RDF* back
against the original graph isn't always a clean isomorphism, for reasons
that trace to the oracle's own harness rather than this module: a
negative `Facts:` item combined with enough other content in the same
document was observed to make the oracle emit *two* structurally-
identical `owl:NegativePropertyAssertion` blocks for one axiom - not
reproducible in a smaller document, and consistent with OWL API's lenient
"auto-declare missing entities" two-pass parsing double-counting an
anonymous (blank-node) axiom rather than deduplicating it. Don't read an
oracle round-trip mismatch alone as proof of a bug here without checking
which side it traces to first.
"""

from __future__ import annotations

from collections import defaultdict

from starlayer.graph.parsers._ox_terms import (
    OWL,
    RDF,
    RDFS,
    XSD,
    BNode,
    Literal,
    URIRef,
    lexical,
)

_CHARACTERISTIC_KEYWORDS = {
    OWL.FunctionalProperty: 'Functional',
    OWL.InverseFunctionalProperty: 'InverseFunctional',
    OWL.TransitiveProperty: 'Transitive',
    OWL.SymmetricProperty: 'Symmetric',
    OWL.AsymmetricProperty: 'Asymmetric',
    OWL.ReflexiveProperty: 'Reflexive',
    OWL.IrreflexiveProperty: 'Irreflexive',
}

_DATA_FACET_KEYWORDS = {
    XSD.minInclusive: '>=', XSD.maxInclusive: '<=',
    XSD.minExclusive: '>', XSD.maxExclusive: '<',
    XSD.length: 'length', XSD.minLength: 'minLength', XSD.maxLength: 'maxLength',
    XSD.pattern: 'pattern',
    RDF.langRange: 'langRange',
}

_WELL_KNOWN_ANNOTATION_PROPS = {
    RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.isDefinedBy,
    OWL.versionInfo, OWL.deprecated, OWL.priorVersion,
    OWL.backwardCompatibleWith, OWL.incompatibleWith,
}

# Predicates every frame-body renderer treats as structural (already
# accounted for by frame typing / the class-expression-tree walk / the
# reification pass) rather than as a candidate Annotations: pair.
_STRUCTURAL_CLASS_PREDS = {
    RDF.type, RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith,
    OWL.disjointUnionOf, OWL.hasKey,
}
_STRUCTURAL_PROPERTY_PREDS = {
    RDF.type, RDFS.domain, RDFS.range, RDFS.subPropertyOf,
    OWL.equivalentProperty, OWL.propertyDisjointWith, OWL.inverseOf,
    OWL.propertyChainAxiom,
}
_STRUCTURAL_ANNPROP_PREDS = {RDF.type, RDFS.domain, RDFS.range, RDFS.subPropertyOf}
_STRUCTURAL_INDIVIDUAL_PREDS = {RDF.type, OWL.sameAs, OWL.differentFrom}
_STRUCTURAL_DATATYPE_PREDS = {RDF.type, OWL.equivalentClass}

_STRUCTURAL_BY_FRAME = {
    'Class:': _STRUCTURAL_CLASS_PREDS,
    'ObjectProperty:': _STRUCTURAL_PROPERTY_PREDS,
    'DataProperty:': _STRUCTURAL_PROPERTY_PREDS,
    'AnnotationProperty:': _STRUCTURAL_ANNPROP_PREDS,
    'Individual:': _STRUCTURAL_INDIVIDUAL_PREDS,
    'Datatype:': _STRUCTURAL_DATATYPE_PREDS,
}

# A blank node carrying one of these predicates or types is part of a larger structure (a class expression,
# a data range, a list cell, a reification block, a Misc axiom node), never an anonymous individual.
_STRUCTURAL_BNODE_PREDS = {
    OWL.intersectionOf, OWL.unionOf, OWL.complementOf, OWL.oneOf, OWL.onProperty, OWL.onDatatype,
    OWL.datatypeComplementOf, OWL.withRestrictions, OWL.inverseOf, OWL.members, OWL.distinctMembers,
    RDF.first, RDF.rest, OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget,
    OWL.sourceIndividual, OWL.assertionProperty, OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue,
    OWL.onClass, OWL.onDataRange,
}
_STRUCTURAL_BNODE_TYPES = {
    OWL.Restriction, OWL.Class, OWL.Axiom, OWL.Annotation, OWL.AllDisjointClasses, OWL.AllDisjointProperties,
    OWL.AllDifferent, OWL.NegativePropertyAssertion, OWL.Ontology, RDFS.Datatype,
    OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
}
_REIFICATION_PREDS = {OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget}

_ENTITY_TYPES = {
    OWL.Class: 'Class:', OWL.ObjectProperty: 'ObjectProperty:',
    OWL.DatatypeProperty: 'DataProperty:', OWL.AnnotationProperty: 'AnnotationProperty:',
    OWL.NamedIndividual: 'Individual:', RDFS.Datatype: 'Datatype:',
}


# ---------------------------------------------------------------------------
# Context: one pass over the graph building every lookup table the
# recognizers/renderers below need.
# ---------------------------------------------------------------------------

def _namespace_pairs(graph):
    """``(namespace IRI, prefix)`` for the graph's bound prefixes, plus ``owl``, ``rdf``, ``rdfs`` and ``xsd`` unless the graph
    binds those prefixes or namespaces itself (the parser declares them by default, so the output reads back)."""
    bound = [(str(ns), prefix) for prefix, ns in graph.namespaces()]
    have_ns = {ns for ns, _ in bound}
    have_prefix = {prefix for _, prefix in bound}
    for prefix, vocab in (('owl', OWL), ('rdf', RDF), ('rdfs', RDFS), ('xsd', XSD)):
        if prefix not in have_prefix and str(vocab) not in have_ns:
            bound.append((str(vocab), prefix))
    return bound


class _Ctx:
    """Holds the lookup tables - entity sets by frame keyword, the
    prefix index, and the axiom/negative-fact reification indexes - that
    the recognizers and renderers below need, built in one pass over the
    graph."""

    def __init__(self, graph):
        self.graph = graph
        self.used_prefixes = {}  # prefix -> namespace IRI, populated as names render
        self._ns_by_length = sorted(
            _namespace_pairs(graph),
            key=lambda pair: -len(pair[0]),
        )

        self.object_props, self.data_props, self.ann_props = set(), set(), set()
        self.entities = defaultdict(set)  # frame keyword -> {subject, ...}
        self.ontology = None
        for s, _p, o in graph.triples((None, RDF.type, None)):
            if o == OWL.Ontology:
                if self.ontology is None or isinstance(s, URIRef):
                    self.ontology = s  # an anonymous ontology is a blank node
            elif not isinstance(s, URIRef):
                continue
            elif o in _ENTITY_TYPES:
                self.entities[_ENTITY_TYPES[o]].add(s)
                if o == OWL.ObjectProperty:
                    self.object_props.add(s)
                elif o == OWL.DatatypeProperty:
                    self.data_props.add(s)
                elif o == OWL.AnnotationProperty:
                    self.ann_props.add(s)

        # owl:Annotation blocks (annotations of an annotation, the ontology, a Misc axiom node or a negative
        # fact), indexed by the (source, property, target) they annotate - the reverse of
        # _annotation_triples() in manchester_parser.py.
        self._annotation_nodes = defaultdict(list)
        for an in graph.subjects(RDF.type, OWL.Annotation):
            src = graph.value(an, OWL.annotatedSource)
            prop = graph.value(an, OWL.annotatedProperty)
            tgt = graph.value(an, OWL.annotatedTarget)
            if src is not None and prop is not None and tgt is not None:
                self._annotation_nodes[(src, prop, tgt)].append(an)

        # owl:Axiom reification blocks, indexed by the (s, p, o) they annotate - the reverse of
        # _maybe_reify() in manchester_parser.py. One axiom can have several blocks (the parser writes one
        # per annotated item), each with its own annotations.
        self.axiom_annotations = defaultdict(list)
        for ax in graph.subjects(RDF.type, OWL.Axiom):
            src = graph.value(ax, OWL.annotatedSource)
            prop = graph.value(ax, OWL.annotatedProperty)
            tgt = graph.value(ax, OWL.annotatedTarget)
            if src is None or prop is None or tgt is None:
                continue
            anns = self.annotations_of(ax, _REIFICATION_PREDS | {RDF.type})
            if anns:
                self.axiom_annotations[(src, prop, tgt)].append(anns)

        # owl:NegativePropertyAssertion bnodes, indexed by the asserting
        # individual - the reverse of the negative-Facts: branch in
        # manchester_parser.py's _parse_individual_frame.
        self.negative_facts = defaultdict(list)
        for na in graph.subjects(RDF.type, OWL.NegativePropertyAssertion):
            src = graph.value(na, OWL.sourceIndividual)
            prop = graph.value(na, OWL.assertionProperty)
            tgt = graph.value(na, OWL.targetIndividual)
            if tgt is None:
                tgt = graph.value(na, OWL.targetValue)
            if src is None or prop is None or tgt is None:
                continue
            skip = {RDF.type, OWL.sourceIndividual, OWL.assertionProperty,
                    OWL.targetIndividual, OWL.targetValue}
            self.negative_facts[src].append((prop, tgt, self.annotations_of(na, skip)))

        # Anonymous individuals (`Individual: _:b`): a blank node that is the subject of a triple and not
        # part of a class expression, a data range, a list, a reification block or a Misc axiom node.
        structural = set()
        subjects = set()
        for s, p, o in graph.triples((None, None, None)):
            if not isinstance(s, BNode):
                continue
            subjects.add(s)
            if p in _STRUCTURAL_BNODE_PREDS or p in _DATA_FACET_KEYWORDS or (
                p == RDF.type and o in _STRUCTURAL_BNODE_TYPES
            ):
                structural.add(s)
        for src in self.negative_facts:
            if isinstance(src, BNode):
                subjects.add(src)
        self.entities['Individual:'] |= subjects - structural

    def annotations_of(self, node, skip, _seen=frozenset()):
        """The annotations hanging off ``node`` (every predicate not in ``skip``) as ``(property, value,
        nested)`` triples; ``nested`` is the annotations of that annotation, from the owl:Annotation blocks
        that point at it (empty when there are none)."""
        result = []
        seen = _seen | {node}
        for p, o in self.graph.predicate_objects(node):
            if p in skip:
                continue
            nested = []
            for inner in self._annotation_nodes.get((node, p, o), ()):
                if inner not in seen:
                    nested += self.annotations_of(inner, _REIFICATION_PREDS | {RDF.type}, seen)
            result.append((p, o, nested))
        return result

    def frame_kinds(self, subject):
        """The frame keywords ``subject`` has a frame under (more than one when an IRI is punned)."""
        return {kind for kind, subjects in self.entities.items() if subject in subjects}

    def annotated_items(self, s, p, o, text):
        """``text`` once per owl:Axiom block annotating ``(s, p, o)`` (each with its own ``Annotations:``
        prefix), or alone when the axiom is not annotated."""
        blocks = self.axiom_annotations.get((s, p, o))
        if not blocks:
            return [text]
        return [_annotations_prefix(self, block) + text for block in blocks]

    def is_annotation_prop(self, pred):
        return pred in self.ann_props or pred in _WELL_KNOWN_ANNOTATION_PROPS


# ---------------------------------------------------------------------------
# Names and literals
# ---------------------------------------------------------------------------

def _render_name(ctx, node):
    if isinstance(node, BNode):
        raise ValueError(
            f'cannot render blank node {node!r} as a Manchester name - it '
            f'matched no recognizable class-expression/data-range/property '
            f'pattern (see this module\'s docstring for what is recognized)'
        )
    if not isinstance(node, URIRef):
        raise ValueError(f'cannot render {node!r} as a Manchester name - Manchester syntax has no form for a {type(node).__name__} term')
    iri = node.value
    for ns_iri, prefix in ctx._ns_by_length:
        if iri.startswith(ns_iri) and ns_iri:
            local = iri[len(ns_iri):]
            if local and _is_safe_local_name(local):
                ctx.used_prefixes[prefix] = ns_iri
                return f'{prefix}:{local}' if prefix else f':{local}'
    return f'<{iri}>'


def _iri_key(node):
    return node.value


def _iri_text(node):
    return node.value if hasattr(node, 'value') else str(node)


def _is_safe_local_name(local):
    return not any(c.isspace() or c in '<>"(){}[],' for c in local)


def _render_literal(ctx, lit):
    text = lit.value.replace('\\', '\\\\').replace('"', '\\"')
    if getattr(lit, 'direction', None) is not None:
        raise ValueError(
            f'cannot render {lit!r}: Manchester syntax has no base direction for a language-tagged literal'
        )
    if lit.language:
        return f'"{text}"@{lit.language}'
    if lit.datatype and lit.datatype != XSD.string:  # a plain literal is xsd:string in RDF 1.1 / 1.2
        return f'"{text}"^^{_render_name(ctx, lit.datatype)}'
    return f'"{text}"'


def _render_individual(ctx, node):
    """An individual: a name, or a ``_:label`` nodeID for an anonymous one (the note's ``individual ::=
    individualIRI | nodeID``)."""
    if isinstance(node, BNode):
        return f'_:{node.value}'
    return _render_name(ctx, node)


def _render_value(ctx, value):
    if isinstance(value, Literal):
        return _render_literal(ctx, value)
    return _render_individual(ctx, value)


# ---------------------------------------------------------------------------
# rdf:List walking
# ---------------------------------------------------------------------------

def _read_list(graph, node):
    items = []
    seen = set()
    while node is not None and node != RDF.nil:
        if node in seen:
            raise ValueError(f'cyclic rdf:List at {node!r}')
        seen.add(node)
        first = graph.value(node, RDF.first)
        if first is None:
            raise ValueError(f'malformed rdf:List at {node!r} - missing rdf:first')
        items.append(first)
        node = graph.value(node, RDF.rest)
    return items


# ---------------------------------------------------------------------------
# RDF -> class-expression AST (the reverse of _expr_node/_prop_node in
# manchester_parser.py)
# ---------------------------------------------------------------------------

def _node_to_prop_expr(ctx, node):
    if isinstance(node, URIRef):
        return node
    inv = ctx.graph.value(node, OWL.inverseOf)
    if inv is not None and isinstance(inv, URIRef):
        return ('Inverse', inv)
    raise ValueError(f'cannot recognize {node!r} as a property expression')


def _node_to_class_expr(ctx, node):
    if isinstance(node, URIRef):
        return node
    g = ctx.graph

    lst = g.value(node, OWL.intersectionOf)
    if lst is not None:
        return ('And', [_node_to_class_expr(ctx, e) for e in _read_list(g, lst)])
    lst = g.value(node, OWL.unionOf)
    if lst is not None:
        return ('Or', [_node_to_class_expr(ctx, e) for e in _read_list(g, lst)])
    comp = g.value(node, OWL.complementOf)
    if comp is not None:
        return ('Not', _node_to_class_expr(ctx, comp))
    lst = g.value(node, OWL.oneOf)
    if lst is not None:
        members = _read_list(g, lst)
        if members and all(isinstance(m, Literal) for m in members):
            return ('DOneOf', members)  # an enumeration of literals is a data range, not of individuals
        return ('OneOf', members)

    if (node, RDF.type, OWL.Restriction) in g:
        prop_node = g.value(node, OWL.onProperty)
        if prop_node is None:
            raise ValueError(f'owl:Restriction {node!r} has no owl:onProperty')
        prop = _node_to_prop_expr(ctx, prop_node)

        some = g.value(node, OWL.someValuesFrom)
        if some is not None:
            return ('Some', prop, _node_to_filler(ctx, some))
        only = g.value(node, OWL.allValuesFrom)
        if only is not None:
            return ('Only', prop, _node_to_filler(ctx, only))
        val = g.value(node, OWL.hasValue)
        if val is not None:
            return ('Value', prop, val)
        if (node, OWL.hasSelf, lexical(True)) in g:
            return ('SelfR', prop)

        for tag, unq_pred, q_pred in (
            ('Min', OWL.minCardinality, OWL.minQualifiedCardinality),
            ('Max', OWL.maxCardinality, OWL.maxQualifiedCardinality),
            ('Exact', OWL.cardinality, OWL.qualifiedCardinality),
        ):
            n = g.value(node, unq_pred)
            if n is not None:
                return (tag, int(n.value), prop, None)
            n = g.value(node, q_pred)
            if n is not None:
                on_class = g.value(node, OWL.onClass)
                if on_class is None:
                    on_range = g.value(node, OWL.onDataRange)
                    if on_range is None:
                        raise ValueError(f'qualified cardinality {node!r} has no owl:onClass or owl:onDataRange')
                    return (tag, int(n.value), prop, _node_to_data_range(ctx, on_range))
                return (tag, int(n.value), prop, _node_to_class_expr(ctx, on_class))
        raise ValueError(f'owl:Restriction {node!r} matched no known restriction shape')

    raise ValueError(
        f'cannot recognize blank node {node!r} as a class expression - no '
        f'intersectionOf/unionOf/complementOf/oneOf/Restriction shape found'
    )


# ---------------------------------------------------------------------------
# RDF -> data-range AST (the reverse of _data_range_node)
# ---------------------------------------------------------------------------

def _node_to_filler(ctx, node):
    """A ``some``/``only`` filler: a class expression, or a data range when the node is one (a blank
    node typed ``rdfs:Datatype`` or built from the data-range vocabulary)."""
    g = ctx.graph
    if isinstance(node, BNode) and (
        (node, RDF.type, RDFS.Datatype) in g
        or g.value(node, OWL.onDatatype) is not None
        or g.value(node, OWL.datatypeComplementOf) is not None
    ):
        return _node_to_data_range(ctx, node)
    return _node_to_class_expr(ctx, node)


def _node_to_data_range(ctx, node):
    if isinstance(node, URIRef):
        return node
    g = ctx.graph

    lst = g.value(node, OWL.intersectionOf)
    if lst is not None:
        return ('DAnd', [_node_to_data_range(ctx, e) for e in _read_list(g, lst)])
    lst = g.value(node, OWL.unionOf)
    if lst is not None:
        return ('DOr', [_node_to_data_range(ctx, e) for e in _read_list(g, lst)])
    comp = g.value(node, OWL.datatypeComplementOf)
    if comp is not None:
        return ('DNot', _node_to_data_range(ctx, comp))
    lst = g.value(node, OWL.oneOf)
    if lst is not None:
        return ('DOneOf', _read_list(g, lst))
    datatype = g.value(node, OWL.onDatatype)
    if datatype is not None:
        facet_list = g.value(node, OWL.withRestrictions)
        facets = []
        for fn in (_read_list(g, facet_list) if facet_list is not None else []):
            pairs = [(p, o) for p, o in g.predicate_objects(fn) if p in _DATA_FACET_KEYWORDS]
            if not pairs:
                raise ValueError(f'facet node {fn!r} has no recognized xsd: facet predicate')
            facets.append(pairs[0])
        return ('DRestriction', datatype, facets)

    raise ValueError(
        f'cannot recognize blank node {node!r} as a data range - no '
        f'intersectionOf/unionOf/datatypeComplementOf/oneOf/onDatatype shape found'
    )


# ---------------------------------------------------------------------------
# AST -> text, with precedence-aware parenthesization. `context` is one of
# 'or' (top level), 'and' (inside an And's operand list), or 'primary'
# (a not/restriction-filler/cardinality-filler position) - mirrors
# _parse_description/_parse_conjunction/_parse_primary's precedence
# levels in manchester_parser.py, in reverse.
# ---------------------------------------------------------------------------

def _render_prop_expr(ctx, expr):
    if isinstance(expr, URIRef):
        return _render_name(ctx, expr)
    return f'inverse {_render_name(ctx, expr[1])}'


def _needs_parens(context, tag, and_tag, or_tag):
    """Whether an operand needs parentheses: an ``or`` inside an ``and``, either operator in a primary
    position, and an operator inside the same operator - ``A and (B and C)`` parses to a nested
    intersection, so the written form must keep the parentheses to read back to the same structure."""
    return (
        (context == 'and' and tag in (and_tag, or_tag))
        or (context == 'or_operand' and tag == or_tag)
        or (context == 'primary' and tag in (and_tag, or_tag))
    )


def _render_class_expr(ctx, expr, context='or'):
    if not isinstance(expr, URIRef) and expr[0].startswith('D'):
        return _render_data_range(ctx, expr, context)  # a data-range filler of a data restriction
    text, tag = _render_class_expr_bare(ctx, expr)
    return f'({text})' if _needs_parens(context, tag, 'And', 'Or') else text


def _render_class_expr_bare(ctx, expr):
    if isinstance(expr, URIRef):
        return _render_name(ctx, expr), None
    tag = expr[0]
    if tag == 'And':
        return ' and '.join(_render_class_expr(ctx, e, 'and') for e in expr[1]), 'And'
    if tag == 'Or':
        return ' or '.join(_render_class_expr(ctx, e, 'or_operand') for e in expr[1]), 'Or'
    if tag == 'Not':
        return f'not {_render_class_expr(ctx, expr[1], "primary")}', 'Not'
    if tag == 'OneOf':
        return '{' + ', '.join(_render_individual(ctx, i) for i in expr[1]) + '}', 'OneOf'
    if tag in ('Some', 'Only'):
        _, prop, filler = expr
        kw = 'some' if tag == 'Some' else 'only'
        return f'{_render_prop_expr(ctx, prop)} {kw} {_render_class_expr(ctx, filler, "primary")}', tag
    if tag == 'Value':
        _, prop, value = expr
        return f'{_render_prop_expr(ctx, prop)} value {_render_value(ctx, value)}', tag
    if tag == 'SelfR':
        return f'{_render_prop_expr(ctx, expr[1])} Self', tag
    if tag in ('Min', 'Max', 'Exact'):
        _, n, prop, filler = expr
        kw = {'Min': 'min', 'Max': 'max', 'Exact': 'exactly'}[tag]
        text = f'{_render_prop_expr(ctx, prop)} {kw} {n}'
        if filler is not None:
            text += f' {_render_class_expr(ctx, filler, "primary")}'
        return text, tag
    raise AssertionError(f'unhandled class-expression tag {tag!r}')


def _render_data_range(ctx, dr, context='or'):
    text, tag = _render_data_range_bare(ctx, dr)
    return f'({text})' if _needs_parens(context, tag, 'DAnd', 'DOr') else text


def _render_data_range_bare(ctx, dr):
    if isinstance(dr, URIRef):
        return _render_name(ctx, dr), None
    tag = dr[0]
    if tag == 'DAnd':
        return ' and '.join(_render_data_range(ctx, e, 'and') for e in dr[1]), tag
    if tag == 'DOr':
        return ' or '.join(_render_data_range(ctx, e, 'or_operand') for e in dr[1]), tag
    if tag == 'DNot':
        return f'not {_render_data_range(ctx, dr[1], "primary")}', tag
    if tag == 'DOneOf':
        return '{' + ', '.join(_render_literal(ctx, lit) for lit in dr[1]) + '}', tag
    if tag == 'DRestriction':
        _, datatype, facets = dr
        parts = ', '.join(f'{_DATA_FACET_KEYWORDS[f]} {_render_literal(ctx, v)}' for f, v in facets)
        return f'{_render_name(ctx, datatype)}[{parts}]', tag
    raise AssertionError(f'unhandled data-range tag {tag!r}')


# ---------------------------------------------------------------------------
# Inline Annotations: prefix
# ---------------------------------------------------------------------------

def _annotations_prefix(ctx, anns):
    """``Annotations: p v, ...`` for ``(property, value, nested)`` annotations, where an annotation that is
    itself annotated carries its own ``Annotations:`` prefix, to any depth; ``''`` for none."""
    if not anns:
        return ''
    return f'Annotations: {_annotation_list(ctx, anns)} '


def _annotation_list(ctx, anns):
    return ', '.join(
        _annotations_prefix(ctx, nested) + f'{_render_name(ctx, p)} {_render_value(ctx, v)}'
        for p, v, nested in anns
    )


# ---------------------------------------------------------------------------
# Frame bodies
# ---------------------------------------------------------------------------

def _clause_lines(items, keyword, indent='    '):
    if not items:
        return []
    return [f'{indent}{keyword}: ' + ', '.join(items)]


def _item_clause(ctx, subject, pred, render_object):
    """The items of one clause: every ``(subject, pred, o)`` triple rendered by ``render_object``, once per
    annotated copy of the axiom."""
    items = []
    for o in ctx.graph.objects(subject, pred):
        items += ctx.annotated_items(subject, pred, o, render_object(o))
    return items


def _render_class_frame(ctx, subject):
    g = ctx.graph
    lines = [f'Class: {_render_name(ctx, subject)}']

    for pred, keyword in ((RDFS.subClassOf, 'SubClassOf'), (OWL.equivalentClass, 'EquivalentTo'),
                           (OWL.disjointWith, 'DisjointWith')):
        lines += _clause_lines(_item_clause(
            ctx, subject, pred, lambda o: _render_class_expr(ctx, _node_to_class_expr(ctx, o))), keyword)

    for o in g.objects(subject, OWL.disjointUnionOf):
        members = ', '.join(_render_class_expr(ctx, _node_to_class_expr(ctx, m)) for m in _read_list(g, o))
        lines += _clause_lines(ctx.annotated_items(subject, OWL.disjointUnionOf, o, members), 'DisjointUnionOf')

    for o in g.objects(subject, OWL.hasKey):
        members = ', '.join(_render_prop_expr(ctx, _node_to_prop_expr(ctx, m)) for m in _read_list(g, o))
        lines += _clause_lines(ctx.annotated_items(subject, OWL.hasKey, o, members), 'HasKey')

    lines += _render_frame_annotations(ctx, subject)
    return lines


def _render_property_frame(ctx, subject, frame_keyword, range_is_class_expr):
    g = ctx.graph
    lines = [f'{frame_keyword} {_render_name(ctx, subject)}']

    lines += _clause_lines(_item_clause(
        ctx, subject, RDFS.domain, lambda o: _render_class_expr(ctx, _node_to_class_expr(ctx, o))), 'Domain')

    if range_is_class_expr:
        def render_range(o):
            return _render_class_expr(ctx, _node_to_class_expr(ctx, o))
    else:
        def render_range(o):
            return _render_data_range(ctx, _node_to_data_range(ctx, o))
    lines += _clause_lines(_item_clause(ctx, subject, RDFS.range, render_range), 'Range')

    for pred, keyword in ((RDFS.subPropertyOf, 'SubPropertyOf'), (OWL.equivalentProperty, 'EquivalentTo'),
                           (OWL.propertyDisjointWith, 'DisjointWith'), (OWL.inverseOf, 'InverseOf')):
        lines += _clause_lines(_item_clause(
            ctx, subject, pred, lambda o: _render_prop_expr(ctx, _node_to_prop_expr(ctx, o))), keyword)

    for o in g.objects(subject, OWL.propertyChainAxiom):
        chain = ' o '.join(_render_prop_expr(ctx, _node_to_prop_expr(ctx, m)) for m in _read_list(g, o))
        lines += _clause_lines(ctx.annotated_items(subject, OWL.propertyChainAxiom, o, chain), 'SubPropertyChain')

    chars = []
    for o in g.objects(subject, RDF.type):
        if o in _CHARACTERISTIC_KEYWORDS:
            chars += ctx.annotated_items(subject, RDF.type, o, _CHARACTERISTIC_KEYWORDS[o])
    lines += _clause_lines(chars, 'Characteristics')

    lines += _render_frame_annotations(ctx, subject)
    return lines


def _render_annotation_property_frame(ctx, subject):
    lines = [f'AnnotationProperty: {_render_name(ctx, subject)}']
    for pred, keyword in ((RDFS.domain, 'Domain'), (RDFS.range, 'Range'), (RDFS.subPropertyOf, 'SubPropertyOf')):
        lines += _clause_lines(_item_clause(ctx, subject, pred, lambda o: _render_name(ctx, o)), keyword)
    lines += _render_frame_annotations(ctx, subject)
    return lines


def _render_individual_frame(ctx, subject):
    g = ctx.graph
    lines = [f'Individual: {_render_individual(ctx, subject)}']
    skip = _frame_structural_preds(ctx, subject)

    types = []
    for o in g.objects(subject, RDF.type):
        if o == OWL.NamedIndividual or o in _ENTITY_TYPES or o in _CHARACTERISTIC_KEYWORDS:
            continue  # a punned IRI also has a Class:/property frame, which owns these
        types += ctx.annotated_items(
            subject, RDF.type, o, _render_class_expr(ctx, _node_to_class_expr(ctx, o)))
    lines += _clause_lines(types, 'Types')

    facts = []
    for p, o in g.predicate_objects(subject):
        if p in skip or ctx.is_annotation_prop(p):
            continue
        facts += ctx.annotated_items(subject, p, o, f'{_render_name(ctx, p)} {_render_value(ctx, o)}')
    for prop, value, anns in ctx.negative_facts.get(subject, []):
        prefix = _annotations_prefix(ctx, anns)
        facts.append(f'{prefix}not {_render_name(ctx, prop)} {_render_value(ctx, value)}')
    lines += _clause_lines(facts, 'Facts')

    for pred, keyword in ((OWL.sameAs, 'SameAs'), (OWL.differentFrom, 'DifferentFrom')):
        lines += _clause_lines(_item_clause(ctx, subject, pred, lambda o: _render_individual(ctx, o)), keyword)

    lines += _render_frame_annotations(ctx, subject)
    return lines


def _render_datatype_frame(ctx, subject):
    lines = [f'Datatype: {_render_name(ctx, subject)}']
    lines += _clause_lines(_item_clause(
        ctx, subject, OWL.equivalentClass,
        lambda o: _render_data_range(ctx, _node_to_data_range(ctx, o))), 'EquivalentTo')
    lines += _render_frame_annotations(ctx, subject)
    return lines


def _frame_structural_preds(ctx, subject):
    """Every predicate some frame the subject has already renders (an IRI can be punned: a class and an
    individual at once)."""
    preds = set()
    for kind in ctx.frame_kinds(subject):
        preds |= _STRUCTURAL_BY_FRAME[kind]
    return preds


def _render_frame_annotations(ctx, subject):
    """Any remaining (subject, pred, value) pair not already consumed by a
    known clause is a frame-level Annotations: pair - the same "whatever's
    left is an annotation" rule _handle_frame_annotations()'s forward
    direction implies, generalized here since there's no explicit
    Annotations: keyword left in the RDF to key off of. An annotation that is itself annotated
    is an owl:Axiom block on the pair."""
    structural = _frame_structural_preds(ctx, subject)
    only_annotation_props = 'Individual:' in ctx.frame_kinds(subject)  # Facts: claimed every other predicate
    items = []
    for p, o in ctx.graph.predicate_objects(subject):
        if p in structural:
            continue
        if only_annotation_props and not ctx.is_annotation_prop(p):
            continue
        items += ctx.annotated_items(subject, p, o, f'{_render_name(ctx, p)} {_render_value(ctx, o)}')
    return _clause_lines(items, 'Annotations')


# ---------------------------------------------------------------------------
# Misc axioms: the >2-member AllDisjoint*/AllDifferent nodes, and every pairwise axiom
# (equivalence, binary disjointness, sameAs, differentFrom) whose subject has no frame to carry it
# ---------------------------------------------------------------------------

def _render_misc(ctx):
    g = ctx.graph
    lines = []
    for rdf_type, keyword, member_render in (
        (OWL.AllDisjointClasses, 'DisjointClasses', lambda m: _render_class_expr(ctx, _node_to_class_expr(ctx, m))),
        (OWL.AllDisjointProperties, 'DisjointProperties', lambda m: _render_prop_expr(ctx, _node_to_prop_expr(ctx, m))),
        (OWL.AllDifferent, 'DifferentIndividuals', lambda m: _render_individual(ctx, m)),
    ):
        for node in g.subjects(RDF.type, rdf_type):
            members_list = g.value(node, OWL.members)
            if members_list is None and rdf_type == OWL.AllDifferent:
                members_list = g.value(node, OWL.distinctMembers)  # the OWL 1 spelling the RDF mapping still reads
            if members_list is None:
                continue
            members = [member_render(m) for m in _read_list(g, members_list)]
            anns = ctx.annotations_of(node, {RDF.type, OWL.members, OWL.distinctMembers})
            lines.append(f'{keyword}: {_annotations_prefix(ctx, anns)}' + ', '.join(members))
    lines += _render_frameless_axioms(ctx)
    return lines


def _term_key(term):
    return (type(term).__name__, getattr(term, 'value', str(term)))


def _sorted_pairs(graph, pred):
    return sorted(((s, o) for s, _p, o in graph.triples((None, pred, None))),
                  key=lambda pair: (_term_key(pair[0]), _term_key(pair[1])))


def _render_frameless_axioms(ctx):
    """A pairwise axiom is written in its subject's frame when the subject has one. The parser declares no
    entity for a name used only in a top-level ``EquivalentClasses:`` and the like, and an axiom whose
    subject is a class expression (``Class: A SuperClassOf: p some B``) has no frame at all, so each of
    those is written as a Misc axiom (or ``SuperClassOf:``) instead of being dropped."""
    g = ctx.graph
    lines = []

    def class_expr(n):
        return _render_class_expr(ctx, _node_to_class_expr(ctx, n))

    def prop_expr(n):
        return _render_prop_expr(ctx, _node_to_prop_expr(ctx, n))

    def individual(n):
        return _render_individual(ctx, n)

    props = ('ObjectProperty:', 'DataProperty:')
    for pred, keyword, render, frames in (
        (OWL.equivalentClass, 'EquivalentClasses', class_expr, ('Class:', 'Datatype:')),
        (OWL.disjointWith, 'DisjointClasses', class_expr, ('Class:',)),
        (OWL.equivalentProperty, 'EquivalentProperties', prop_expr, props),
        (OWL.propertyDisjointWith, 'DisjointProperties', prop_expr, props),
        (OWL.sameAs, 'SameIndividual', individual, ('Individual:',)),
        (OWL.differentFrom, 'DifferentIndividuals', individual, ('Individual:',)),
    ):
        for s, o in _sorted_pairs(g, pred):
            if any(s in ctx.entities[kind] for kind in frames):
                continue
            for item in ctx.annotated_items(s, pred, o, f'{render(s)}, {render(o)}'):
                lines.append(f'{keyword}: {item}')

    # A subclass axiom whose subject has no Class: frame: a class expression (a GCI), or an undeclared name.
    for s, o in _sorted_pairs(g, RDFS.subClassOf):
        if s in ctx.entities['Class:'] or (isinstance(s, URIRef) and ctx.frame_kinds(s)):
            continue
        if isinstance(o, URIRef):
            head, clause, text = o, 'SuperClassOf', class_expr(s)
        elif isinstance(s, URIRef):
            head, clause, text = s, 'SubClassOf', class_expr(o)
        else:
            raise ValueError(
                f'cannot write the subclass axiom between {s!r} and {o!r}: Manchester syntax needs a named class '
                f'on one side'
            )
        for item in ctx.annotated_items(s, RDFS.subClassOf, o, text):
            lines += [f'Class: {_render_name(ctx, head)}', f'    {clause}: {item}']
    return lines


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def _render_ontology_header(ctx):
    """``Ontology: [<iri> [<versionIRI>]]``, its imports and its annotations. An ontology without an IRI is a
    blank node and gets the bare ``Ontology:`` header."""
    g = ctx.graph
    node = ctx.ontology
    version = g.value(node, OWL.versionIRI)
    if isinstance(node, URIRef):
        head = f'Ontology: <{node.value}>'
        if version is not None:
            head += f' <{_iri_text(version)}>'
    elif version is not None:
        raise ValueError(f'cannot write a version IRI for the anonymous ontology {node!r}: Manchester syntax needs an ontology IRI')
    else:
        head = 'Ontology:'
    lines = [head]
    for imported in g.objects(node, OWL.imports):
        lines.append(f'    Import: <{_iri_text(imported)}>')
    anns = ctx.annotations_of(node, {RDF.type, OWL.imports, OWL.versionIRI})
    if anns:
        lines.append(f'    Annotations: {_annotation_list(ctx, anns)}')
    return lines


def serialize_manchester(graph) -> str:
    """Serialize a StarLayerGraph to OWL 2 Manchester Syntax.
    See this module's docstring for scope and known limitations.

    Args:
        graph: The StarLayerGraph to serialize.

    Returns:
        The Manchester Syntax serialization of graph.
    """
    from starlayer.graph.oxgraph import _rdflib_bridge

    graph = _rdflib_bridge.to_oxgraph(graph)  # an rdflib graph is converted (imports rdflib); an Oxigraph one is read as it is
    if hasattr(graph, 'to_graph'):
        graph = graph.to_graph()
    ctx = _Ctx(graph)

    body_lines = []
    if ctx.ontology is not None:
        body_lines += _render_ontology_header(ctx)
        body_lines.append('')

    for subject in sorted(ctx.entities['Class:'], key=_iri_key):
        body_lines += _render_class_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['ObjectProperty:'], key=_iri_key):
        body_lines += _render_property_frame(ctx, subject, 'ObjectProperty:', range_is_class_expr=True)
        body_lines.append('')
    for subject in sorted(ctx.entities['DataProperty:'], key=_iri_key):
        body_lines += _render_property_frame(ctx, subject, 'DataProperty:', range_is_class_expr=False)
        body_lines.append('')
    for subject in sorted(ctx.entities['AnnotationProperty:'], key=_iri_key):
        body_lines += _render_annotation_property_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['Datatype:'], key=_iri_key):
        body_lines += _render_datatype_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['Individual:'], key=_iri_key):
        body_lines += _render_individual_frame(ctx, subject)
        body_lines.append('')

    body_lines += _render_misc(ctx)

    # Prefix: lines only for namespaces actually used above (populated by
    # _render_name as a side effect) - rendering the body first, then the
    # header, is what makes that possible from a single top-to-bottom pass.
    header_lines = [f'Prefix: {p}: <{iri}>' for p, iri in sorted(ctx.used_prefixes.items())]

    return '\n'.join(header_lines + [''] + body_lines).rstrip() + '\n'
