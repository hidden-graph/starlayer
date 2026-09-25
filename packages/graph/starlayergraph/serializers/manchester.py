"""
starlayergraph.serializers.manchester

Serialize RDF (an rdflib-compatible Graph) to OWL 2 Manchester Syntax -
the reverse of starlayergraph.parsers.manchester_parser. A genuinely
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
    serializer in this package - see rdfxml12.py/jsonld12.py).
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
    identical either way) - this module always renders via the
    per-subject frame clause, never reconstructs an n-ary Misc axiom for
    these. The >2-member `AllDisjointClasses`/`AllDisjointProperties`/
    `AllDifferent` shape *is* unambiguous (only a Misc axiom produces it)
    and *is* reconstructed, as the one Misc-axiom case that's actually
    recoverable.
  - Inline per-axiom `Annotations:` on the six top-level Misc axioms was
    never supported by the parser either (see its own docstring), so
    there is nothing to round-trip there.

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

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

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

_ENTITY_TYPES = {
    OWL.Class: 'Class:', OWL.ObjectProperty: 'ObjectProperty:',
    OWL.DatatypeProperty: 'DataProperty:', OWL.AnnotationProperty: 'AnnotationProperty:',
    OWL.NamedIndividual: 'Individual:', RDFS.Datatype: 'Datatype:',
}


# ---------------------------------------------------------------------------
# Context: one pass over the graph building every lookup table the
# recognizers/renderers below need.
# ---------------------------------------------------------------------------

class _Ctx:
    def __init__(self, graph):
        self.graph = graph
        self.used_prefixes = {}  # prefix -> namespace IRI, populated as names render
        self._ns_by_length = sorted(
            ((str(ns), prefix) for prefix, ns in graph.namespaces()),
            key=lambda pair: -len(pair[0]),
        )

        self.object_props, self.data_props, self.ann_props = set(), set(), set()
        self.entities = defaultdict(set)  # frame keyword -> {subject, ...}
        self.ontology = None
        for s, p, o in graph.triples((None, RDF.type, None)):
            if not isinstance(s, URIRef):
                continue
            if o == OWL.Ontology:
                self.ontology = s
            elif o in _ENTITY_TYPES:
                self.entities[_ENTITY_TYPES[o]].add(s)
                if o == OWL.ObjectProperty:
                    self.object_props.add(s)
                elif o == OWL.DatatypeProperty:
                    self.data_props.add(s)
                elif o == OWL.AnnotationProperty:
                    self.ann_props.add(s)

        # owl:Axiom reification blocks, indexed by the (s, p, o) they
        # annotate - the reverse of _maybe_reify() in manchester_parser.py.
        self.axiom_annotations = {}
        for ax in graph.subjects(RDF.type, OWL.Axiom):
            src = graph.value(ax, OWL.annotatedSource)
            prop = graph.value(ax, OWL.annotatedProperty)
            tgt = graph.value(ax, OWL.annotatedTarget)
            if src is None or prop is None or tgt is None:
                continue
            skip = {RDF.type, OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget}
            anns = [(p2, o2) for p2, o2 in graph.predicate_objects(ax) if p2 not in skip]
            self.axiom_annotations.setdefault((src, prop, tgt), anns)

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
            anns = [(p2, o2) for p2, o2 in graph.predicate_objects(na) if p2 not in skip]
            self.negative_facts[src].append((prop, tgt, anns))

    def is_annotation_prop(self, pred):
        return pred in self.ann_props or pred in _WELL_KNOWN_ANNOTATION_PROPS

    def annotations_for(self, s, p, o):
        return self.axiom_annotations.get((s, p, o))


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
    iri = str(node)
    for ns_iri, prefix in ctx._ns_by_length:
        if iri.startswith(ns_iri) and ns_iri:
            local = iri[len(ns_iri):]
            if local and _is_safe_local_name(local):
                ctx.used_prefixes[prefix] = ns_iri
                return f'{prefix}:{local}' if prefix else f':{local}'
    return f'<{iri}>'


def _is_safe_local_name(local):
    return not any(c.isspace() or c in '<>"(){}[],' for c in local)


def _render_literal(ctx, lit):
    text = str(lit).replace('\\', '\\\\').replace('"', '\\"')
    if lit.language:
        return f'"{text}"@{lit.language}'
    if lit.datatype:
        return f'"{text}"^^{_render_name(ctx, lit.datatype)}'
    return f'"{text}"'


def _render_value(ctx, value):
    if isinstance(value, Literal):
        return _render_literal(ctx, value)
    return _render_name(ctx, value)


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
        return ('OneOf', _read_list(g, lst))

    if (node, RDF.type, OWL.Restriction) in g:
        prop_node = g.value(node, OWL.onProperty)
        if prop_node is None:
            raise ValueError(f'owl:Restriction {node!r} has no owl:onProperty')
        prop = _node_to_prop_expr(ctx, prop_node)

        some = g.value(node, OWL.someValuesFrom)
        if some is not None:
            return ('Some', prop, _node_to_class_expr(ctx, some))
        only = g.value(node, OWL.allValuesFrom)
        if only is not None:
            return ('Only', prop, _node_to_class_expr(ctx, only))
        val = g.value(node, OWL.hasValue)
        if val is not None:
            return ('Value', prop, val)
        if (node, OWL.hasSelf, Literal(True)) in g:
            return ('SelfR', prop)

        for tag, unq_pred, q_pred in (
            ('Min', OWL.minCardinality, OWL.minQualifiedCardinality),
            ('Max', OWL.maxCardinality, OWL.maxQualifiedCardinality),
            ('Exact', OWL.cardinality, OWL.qualifiedCardinality),
        ):
            n = g.value(node, unq_pred)
            if n is not None:
                return (tag, int(n), prop, None)
            n = g.value(node, q_pred)
            if n is not None:
                on_class = g.value(node, OWL.onClass)
                if on_class is None:
                    raise ValueError(f'qualified cardinality {node!r} has no owl:onClass')
                return (tag, int(n), prop, _node_to_class_expr(ctx, on_class))
        raise ValueError(f'owl:Restriction {node!r} matched no known restriction shape')

    raise ValueError(
        f'cannot recognize blank node {node!r} as a class expression - no '
        f'intersectionOf/unionOf/complementOf/oneOf/Restriction shape found'
    )


# ---------------------------------------------------------------------------
# RDF -> data-range AST (the reverse of _data_range_node)
# ---------------------------------------------------------------------------

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


def _render_class_expr(ctx, expr, context='or'):
    text, tag = _render_class_expr_bare(ctx, expr)
    needs_parens = (context == 'and' and tag == 'Or') or (context == 'primary' and tag in ('And', 'Or'))
    return f'({text})' if needs_parens else text


def _render_class_expr_bare(ctx, expr):
    if isinstance(expr, URIRef):
        return _render_name(ctx, expr), None
    tag = expr[0]
    if tag == 'And':
        return ' and '.join(_render_class_expr(ctx, e, 'and') for e in expr[1]), 'And'
    if tag == 'Or':
        return ' or '.join(_render_class_expr(ctx, e, 'or') for e in expr[1]), 'Or'
    if tag == 'Not':
        return f'not {_render_class_expr(ctx, expr[1], "primary")}', 'Not'
    if tag == 'OneOf':
        return '{' + ', '.join(_render_name(ctx, i) for i in expr[1]) + '}', 'OneOf'
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
    needs_parens = (context == 'and' and tag == 'DOr') or (context == 'primary' and tag in ('DAnd', 'DOr'))
    return f'({text})' if needs_parens else text


def _render_data_range_bare(ctx, dr):
    if isinstance(dr, URIRef):
        return _render_name(ctx, dr), None
    tag = dr[0]
    if tag == 'DAnd':
        return ' and '.join(_render_data_range(ctx, e, 'and') for e in dr[1]), tag
    if tag == 'DOr':
        return ' or '.join(_render_data_range(ctx, e, 'or') for e in dr[1]), tag
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
    if anns is None:
        return ''
    rendered = ', '.join(f'{_render_name(ctx, p)} {_render_value(ctx, v)}' for p, v in anns)
    return f'Annotations: {rendered} '


# ---------------------------------------------------------------------------
# Frame bodies
# ---------------------------------------------------------------------------

def _clause_lines(items, keyword, indent='    '):
    if not items:
        return []
    return [f'{indent}{keyword}: ' + ', '.join(items)]


def _render_class_frame(ctx, subject):
    g = ctx.graph
    lines = [f'Class: {_render_name(ctx, subject)}']

    for pred, keyword in ((RDFS.subClassOf, 'SubClassOf'), (OWL.equivalentClass, 'EquivalentTo'),
                           (OWL.disjointWith, 'DisjointWith')):
        items = []
        for o in g.objects(subject, pred):
            expr = _node_to_class_expr(ctx, o)
            rendered = _render_class_expr(ctx, expr)
            anns = ctx.annotations_for(subject, pred, o)
            items.append(_annotations_prefix(ctx, anns) + rendered)
        lines += _clause_lines(items, keyword)

    for o in g.objects(subject, OWL.disjointUnionOf):
        members = [_render_class_expr(ctx, _node_to_class_expr(ctx, m)) for m in _read_list(g, o)]
        anns = ctx.annotations_for(subject, OWL.disjointUnionOf, o)
        lines += _clause_lines([_annotations_prefix(ctx, anns) + ', '.join(members)], 'DisjointUnionOf')

    for o in g.objects(subject, OWL.hasKey):
        members = [_render_prop_expr(ctx, _node_to_prop_expr(ctx, m)) for m in _read_list(g, o)]
        anns = ctx.annotations_for(subject, OWL.hasKey, o)
        lines += _clause_lines([_annotations_prefix(ctx, anns) + ', '.join(members)], 'HasKey')

    lines += _render_frame_annotations(ctx, subject, _STRUCTURAL_CLASS_PREDS)
    return lines


def _render_property_frame(ctx, subject, frame_keyword, range_is_class_expr):
    g = ctx.graph
    lines = [f'{frame_keyword} {_render_name(ctx, subject)}']

    for pred, keyword in ((RDFS.domain, 'Domain'),):
        items = []
        for o in g.objects(subject, pred):
            expr = _node_to_class_expr(ctx, o)
            anns = ctx.annotations_for(subject, pred, o)
            items.append(_annotations_prefix(ctx, anns) + _render_class_expr(ctx, expr))
        lines += _clause_lines(items, keyword)

    items = []
    for o in g.objects(subject, RDFS.range):
        anns = ctx.annotations_for(subject, RDFS.range, o)
        if range_is_class_expr:
            rendered = _render_class_expr(ctx, _node_to_class_expr(ctx, o))
        else:
            rendered = _render_data_range(ctx, _node_to_data_range(ctx, o))
        items.append(_annotations_prefix(ctx, anns) + rendered)
    lines += _clause_lines(items, 'Range')

    for pred, keyword in ((RDFS.subPropertyOf, 'SubPropertyOf'), (OWL.equivalentProperty, 'EquivalentTo'),
                           (OWL.propertyDisjointWith, 'DisjointWith'), (OWL.inverseOf, 'InverseOf')):
        items = []
        for o in g.objects(subject, pred):
            expr = _node_to_prop_expr(ctx, o)
            anns = ctx.annotations_for(subject, pred, o)
            items.append(_annotations_prefix(ctx, anns) + _render_prop_expr(ctx, expr))
        lines += _clause_lines(items, keyword)

    for o in g.objects(subject, OWL.propertyChainAxiom):
        chain = [_render_prop_expr(ctx, _node_to_prop_expr(ctx, m)) for m in _read_list(g, o)]
        anns = ctx.annotations_for(subject, OWL.propertyChainAxiom, o)
        lines += _clause_lines([_annotations_prefix(ctx, anns) + ' o '.join(chain)], 'SubPropertyChain')

    chars = []
    for o in g.objects(subject, RDF.type):
        if o in _CHARACTERISTIC_KEYWORDS:
            anns = ctx.annotations_for(subject, RDF.type, o)
            chars.append(_annotations_prefix(ctx, anns) + _CHARACTERISTIC_KEYWORDS[o])
    lines += _clause_lines(chars, 'Characteristics')

    lines += _render_frame_annotations(ctx, subject, _STRUCTURAL_PROPERTY_PREDS)
    return lines


def _render_annotation_property_frame(ctx, subject):
    g = ctx.graph
    lines = [f'AnnotationProperty: {_render_name(ctx, subject)}']
    for pred, keyword in ((RDFS.domain, 'Domain'), (RDFS.range, 'Range'), (RDFS.subPropertyOf, 'SubPropertyOf')):
        items = []
        for o in g.objects(subject, pred):
            anns = ctx.annotations_for(subject, pred, o)
            items.append(_annotations_prefix(ctx, anns) + _render_name(ctx, o))
        lines += _clause_lines(items, keyword)
    lines += _render_frame_annotations(ctx, subject, _STRUCTURAL_ANNPROP_PREDS)
    return lines


def _render_individual_frame(ctx, subject):
    g = ctx.graph
    lines = [f'Individual: {_render_name(ctx, subject)}']

    types = []
    for o in g.objects(subject, RDF.type):
        if o == OWL.NamedIndividual:
            continue
        expr = _node_to_class_expr(ctx, o)
        anns = ctx.annotations_for(subject, RDF.type, o)
        types.append(_annotations_prefix(ctx, anns) + _render_class_expr(ctx, expr))
    lines += _clause_lines(types, 'Types')

    facts = []
    for p, o in g.predicate_objects(subject):
        if p in _STRUCTURAL_INDIVIDUAL_PREDS or ctx.is_annotation_prop(p):
            continue
        anns = ctx.annotations_for(subject, p, o)
        facts.append(_annotations_prefix(ctx, anns) + f'{_render_name(ctx, p)} {_render_value(ctx, o)}')
    for prop, value, anns in ctx.negative_facts.get(subject, []):
        prefix = _annotations_prefix(ctx, anns if anns else None)
        facts.append(f'{prefix}not {_render_name(ctx, prop)} {_render_value(ctx, value)}')
    lines += _clause_lines(facts, 'Facts')

    for pred, keyword in ((OWL.sameAs, 'SameAs'), (OWL.differentFrom, 'DifferentFrom')):
        items = []
        for o in g.objects(subject, pred):
            anns = ctx.annotations_for(subject, pred, o)
            items.append(_annotations_prefix(ctx, anns) + _render_name(ctx, o))
        lines += _clause_lines(items, keyword)

    lines += _render_frame_annotations(ctx, subject, _STRUCTURAL_INDIVIDUAL_PREDS, extra_skip=ctx.is_annotation_prop)
    return lines


def _render_datatype_frame(ctx, subject):
    g = ctx.graph
    lines = [f'Datatype: {_render_name(ctx, subject)}']
    items = []
    for o in g.objects(subject, OWL.equivalentClass):
        dr = _node_to_data_range(ctx, o)
        anns = ctx.annotations_for(subject, OWL.equivalentClass, o)
        items.append(_annotations_prefix(ctx, anns) + _render_data_range(ctx, dr))
    lines += _clause_lines(items, 'EquivalentTo')
    lines += _render_frame_annotations(ctx, subject, _STRUCTURAL_DATATYPE_PREDS)
    return lines


def _render_frame_annotations(ctx, subject, structural_preds, extra_skip=None):
    """Any remaining (subject, pred, value) pair not already consumed by a
    known clause is a frame-level Annotations: pair - the same "whatever's
    left is an annotation" rule _handle_frame_annotations()'s forward
    direction implies, generalized here since there's no explicit
    Annotations: keyword left in the RDF to key off of."""
    items = []
    for p, o in ctx.graph.predicate_objects(subject):
        if p in structural_preds:
            continue
        if extra_skip is not None and not extra_skip(p):
            # Individual frame: Facts: already claimed every non-annotation,
            # non-structural predicate above - only genuine annotation
            # properties are left to collect here.
            continue
        items.append(f'{_render_name(ctx, p)} {_render_value(ctx, o)}')
    return _clause_lines(items, 'Annotations')


# ---------------------------------------------------------------------------
# Misc axioms (only the unambiguous >2-member AllDisjoint*/AllDifferent
# shape - see module docstring for why the rest aren't reconstructed)
# ---------------------------------------------------------------------------

def _render_misc(ctx):
    g = ctx.graph
    lines = []
    for rdf_type, keyword, member_render in (
        (OWL.AllDisjointClasses, 'DisjointClasses', lambda m: _render_class_expr(ctx, _node_to_class_expr(ctx, m))),
        (OWL.AllDisjointProperties, 'DisjointProperties', lambda m: _render_prop_expr(ctx, _node_to_prop_expr(ctx, m))),
        (OWL.AllDifferent, 'DifferentIndividuals', lambda m: _render_name(ctx, m)),
    ):
        for node in g.subjects(RDF.type, rdf_type):
            members_list = g.value(node, OWL.members)
            if members_list is None:
                continue
            members = [member_render(m) for m in _read_list(g, members_list)]
            lines.append(f'{keyword}: ' + ', '.join(members))
    return lines


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def serialize_manchester(graph) -> str:
    """Serialize an rdflib-compatible Graph to OWL 2 Manchester Syntax.
    See this module's docstring for scope and known limitations."""
    ctx = _Ctx(graph)

    body_lines = []
    if ctx.ontology is not None:
        body_lines.append(f'Ontology: <{ctx.ontology}>')
        for imported in graph.objects(ctx.ontology, OWL.imports):
            body_lines.append(f'    Import: <{imported}>')
        body_lines.append('')

    for subject in sorted(ctx.entities['Class:'], key=str):
        body_lines += _render_class_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['ObjectProperty:'], key=str):
        body_lines += _render_property_frame(ctx, subject, 'ObjectProperty:', range_is_class_expr=True)
        body_lines.append('')
    for subject in sorted(ctx.entities['DataProperty:'], key=str):
        body_lines += _render_property_frame(ctx, subject, 'DataProperty:', range_is_class_expr=False)
        body_lines.append('')
    for subject in sorted(ctx.entities['AnnotationProperty:'], key=str):
        body_lines += _render_annotation_property_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['Datatype:'], key=str):
        body_lines += _render_datatype_frame(ctx, subject)
        body_lines.append('')
    for subject in sorted(ctx.entities['Individual:'], key=str):
        body_lines += _render_individual_frame(ctx, subject)
        body_lines.append('')

    body_lines += _render_misc(ctx)

    # Prefix: lines only for namespaces actually used above (populated by
    # _render_name as a side effect) - rendering the body first, then the
    # header, is what makes that possible from a single top-to-bottom pass.
    header_lines = [f'Prefix: {p}: <{iri}>' for p, iri in sorted(ctx.used_prefixes.items())]

    return '\n'.join(header_lines + [''] + body_lines).rstrip() + '\n'
