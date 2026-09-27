"""
starlayergraph.ontology.to_ast_rdf

Encode/decode an OWL Manchester Syntax document's own internal AST (frames,
clauses, class/property expressions, data ranges) as RDF, using the
``manch:`` vocabulary in ``manchester-ast-ontology.ttl`` - mirroring the
sibling ``starsparql`` package's ``salg:``/``to_rdf.py``/``from_rdf.py``
design for SPARQL query algebra (see that package's own module docstrings
for the design principles this deliberately follows: one dispatch
superclass per family, no ``rdfs:domain``/``range`` on properties reused
across heterogeneous node types, ``rdf:List`` structural checks via a
single ``sh:sparql`` constraint rather than a recursive ``NodeShape`` - see
``manchester_shapes.py``/``.ttl`` for where those apply here).

Three entry points:

- ``parse_manchester_ast(text, base=None) -> (Graph, root)`` - parse
  Manchester text straight to its ``manch:``-encoded AST, reusing
  ``manchester_parser.py``'s own tokenizer/frame/clause/expression-parsing
  functions completely unchanged (via a ``_Cursor`` subclass overriding its
  no-op AST-capture hooks - see that module's own comments on
  ``_Cursor.record_frame``/``record_clause``/etc, and its module docstring's
  own note that this is a genuinely additive refactor, verified by the
  existing ``test_manchester_parser.py`` suite passing unmodified).
- ``rdf_ast_to_manchester_ast(graph, root) -> Document`` - decode a
  ``manch:``-shaped RDF graph back into a real ``Document`` object (the
  same tagged-tuple AST ``manchester_parser.py``'s own ``And``/``Or``/
  ``Some``/... functions already build for expressions/data ranges, plus
  lightweight ``Frame``/``Clause``/``ClauseItem`` namedtuples for the
  frame/clause half, which has no such tuple form today).
- ``manchester_ast_to_text(document) -> str`` - render a ``Document`` back
  to real Manchester Syntax text. Genuinely new code, not adapted from
  ``serializers/manchester.py`` - that module decodes the *final OWL
  semantic RDF* (confirmed lossy and the wrong input for this purpose: it
  can't recover ``onlysome``/``SuperClassOf:`` spelling/list order, none of
  which survives into OWL RDF-mapping triples) - only its *style*
  (priority-ordered predicate dispatch, recurse) carries over as a pattern.

**Fidelity scope, confirmed with the user before building this**: matches
``manchester_parser.py``'s own internal AST exactly - ``onlysome``/``that``/
``SuperClassOf:`` spelling are not recoverable (already desugared before
this module ever sees them), the same bar ``salg:`` itself holds for SPARQL
(it doesn't preserve original whitespace/query text either).
"""

from __future__ import annotations

from collections import namedtuple

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, XSD

from starlayergraph.parsers.manchester_parser import (
    _Cursor,
    _parse_misc,
    _tokenize,
    _CHARACTERISTICS,
    _DATA_FACETS,
)

MANCH = Namespace("https://github.com/hidden-graph/starlayergraph/ns/manchester-ast#")

# ---------------------------------------------------------------------------
# Frame/clause/misc dispatch tables - the one place a new frame/clause type
# needs registering for both encode and decode (the decode side is built by
# inverting these, not maintained separately - see _build_reverse_maps()).
# ---------------------------------------------------------------------------

_FRAME_CLASS = {
    'Class': MANCH.ClassFrame,
    'ObjectProperty': MANCH.ObjectPropertyFrame,
    'DataProperty': MANCH.DataPropertyFrame,
    'AnnotationProperty': MANCH.AnnotationPropertyFrame,
    'Individual': MANCH.IndividualFrame,
    'Datatype': MANCH.DatatypeFrame,
}

# (frame_kind, clause_kind) -> class. SuperClassOf:/SuperPropertyOf: fold
# into their Sub* counterpart's own class (see manchester-ast-ontology.ttl's
# own comment on manch:Clause) - the direction swap already happened at
# capture time in manchester_parser.py, so the *class* is identical either
# way; only the canonical clause_kind used on decode (always the Sub* form)
# differs from what might have been written.
_CLAUSE_CLASS = {
    ('Class', 'SubClassOf:'): MANCH.ClassSubClassOfClause,
    ('Class', 'SuperClassOf:'): MANCH.ClassSubClassOfClause,
    ('Class', 'EquivalentTo:'): MANCH.ClassEquivalentToClause,
    ('Class', 'DisjointWith:'): MANCH.ClassDisjointWithClause,
    ('Class', 'DisjointUnionOf:'): MANCH.ClassDisjointUnionOfClause,
    ('Class', 'HasKey:'): MANCH.ClassHasKeyClause,
    ('Class', 'Annotations:'): MANCH.ClassAnnotationsClause,

    ('ObjectProperty', 'Domain:'): MANCH.ObjPropDomainClause,
    ('ObjectProperty', 'Range:'): MANCH.ObjPropRangeClause,
    ('ObjectProperty', 'SubPropertyOf:'): MANCH.ObjPropSubPropertyOfClause,
    ('ObjectProperty', 'SuperPropertyOf:'): MANCH.ObjPropSubPropertyOfClause,
    ('ObjectProperty', 'EquivalentTo:'): MANCH.ObjPropEquivalentToClause,
    ('ObjectProperty', 'DisjointWith:'): MANCH.ObjPropDisjointWithClause,
    ('ObjectProperty', 'InverseOf:'): MANCH.ObjPropInverseOfClause,
    ('ObjectProperty', 'Characteristics:'): MANCH.ObjPropCharacteristicsClause,
    ('ObjectProperty', 'SubPropertyChain:'): MANCH.ObjPropSubPropertyChainClause,
    ('ObjectProperty', 'Annotations:'): MANCH.ObjPropAnnotationsClause,

    ('DataProperty', 'Domain:'): MANCH.DataPropDomainClause,
    ('DataProperty', 'Range:'): MANCH.DataPropRangeClause,
    ('DataProperty', 'SubPropertyOf:'): MANCH.DataPropSubPropertyOfClause,
    ('DataProperty', 'SuperPropertyOf:'): MANCH.DataPropSubPropertyOfClause,
    ('DataProperty', 'EquivalentTo:'): MANCH.DataPropEquivalentToClause,
    ('DataProperty', 'DisjointWith:'): MANCH.DataPropDisjointWithClause,
    ('DataProperty', 'Characteristics:'): MANCH.DataPropCharacteristicsClause,
    ('DataProperty', 'Annotations:'): MANCH.DataPropAnnotationsClause,

    ('AnnotationProperty', 'Domain:'): MANCH.AnnPropDomainClause,
    ('AnnotationProperty', 'Range:'): MANCH.AnnPropRangeClause,
    ('AnnotationProperty', 'SubPropertyOf:'): MANCH.AnnPropSubPropertyOfClause,
    ('AnnotationProperty', 'Annotations:'): MANCH.AnnPropAnnotationsClause,

    ('Individual', 'Types:'): MANCH.IndividualTypesClause,
    ('Individual', 'Facts:'): MANCH.IndividualFactsClause,
    ('Individual', 'SameAs:'): MANCH.IndividualSameAsClause,
    ('Individual', 'DifferentFrom:'): MANCH.IndividualDifferentFromClause,
    ('Individual', 'Annotations:'): MANCH.IndividualAnnotationsClause,

    ('Datatype', 'EquivalentTo:'): MANCH.DatatypeEquivalentToClause,
    ('Datatype', 'Annotations:'): MANCH.DatatypeAnnotationsClause,
}

# SuperClassOf:/SuperPropertyOf: fold into the same clause class as their
# Sub* counterpart (see _CLAUSE_CLASS above) - but unlike other spelling
# variants, this pair isn't cosmetic: it flips which side of the compiled
# rdfs:subClassOf/subPropertyOf triple the frame's own subject lands on, and
# manch:items alone can't tell the two apart (identical item shape either
# way). record_clause tags the clause node with manch:reversed so decode can
# restore the correct keyword - without it, decoding a Super* clause and
# re-rendering it as Sub* would silently reverse the compiled OWL semantics
# (a real bug, caught by test_manchester_ast.py's round-trip check).
_REVERSED_CLAUSE_KEYWORDS = {'SuperClassOf:', 'SuperPropertyOf:'}

# Single-axiom clauses: record_clause's own items list is a 1-element list
# `[(anns, value)]` (the whole comma-list/chain is one axiom, annotated once)
# rather than one entry per comma-item - see manchester_parser.py's own
# DisjointUnionOf:/HasKey:/SubPropertyChain: handling.
_SINGLE_AXIOM_CLAUSES = {'DisjointUnionOf:', 'HasKey:', 'SubPropertyChain:'}

_MISC_CLASS = {
    'EquivalentClasses:': MANCH.MiscEquivalentClassesAxiom,
    'DisjointClasses:': MANCH.MiscDisjointClassesAxiom,
    'EquivalentProperties:': MANCH.MiscEquivalentPropertiesAxiom,
    'DisjointProperties:': MANCH.MiscDisjointPropertiesAxiom,
    'SameIndividual:': MANCH.MiscSameIndividualAxiom,
    'DifferentIndividuals:': MANCH.MiscDifferentIndividualsAxiom,
}

# Canonical clause_kind to render on decode/serialize for each clause class -
# built from _CLAUSE_CLASS by keeping the *first* (frame_kind, clause_kind)
# pair seen per class, which is always the Sub*/non-Super* spelling since
# that's listed first above.
def _build_reverse_maps():
    frame_class_to_kind = {v: k for k, v in _FRAME_CLASS.items()}
    clause_class_to_kind = {}
    for (frame_kind, clause_kind), cls in _CLAUSE_CLASS.items():
        clause_class_to_kind.setdefault(cls, (frame_kind, clause_kind))
    misc_class_to_keyword = {v: k for k, v in _MISC_CLASS.items()}
    return frame_class_to_kind, clause_class_to_kind, misc_class_to_keyword


_FRAME_CLASS_TO_KIND, _CLAUSE_CLASS_TO_KIND, _MISC_CLASS_TO_KEYWORD = _build_reverse_maps()

_CHARACTERISTICS_INV = {v: k for k, v in _CHARACTERISTICS.items()}
_DATA_FACETS_INV = {v: k for k, v in _DATA_FACETS.items()}


# ---------------------------------------------------------------------------
# rdf:List helpers
# ---------------------------------------------------------------------------

def _build_rdf_list(g, items):
    if not items:
        return RDF.nil
    head, prev = None, None
    for item in items:
        node = BNode()
        if prev is not None:
            g.add((prev, RDF.rest, node))
        else:
            head = node
        g.add((node, RDF.first, item))
        prev = node
    g.add((prev, RDF.rest, RDF.nil))
    return head


def _read_rdf_list(g, node):
    if node is None or node == RDF.nil:
        return []
    return list(Collection(g, node))


# ---------------------------------------------------------------------------
# Class-expression / property-expression / data-range encode
# (mirrors manchester_parser.py's own _expr_node/_prop_node/_data_range_node
# shape exactly - same tags, same arity, manch: predicates instead of the
# OWL 2 RDF Mapping's own)
# ---------------------------------------------------------------------------

def _encode_prop_expr(g, prop_expr):
    if isinstance(prop_expr, URIRef):
        return prop_expr
    node = BNode()
    g.add((node, RDF.type, MANCH.Inverse))
    g.add((node, MANCH.operand, prop_expr[1]))
    return node


def _encode_class_expr(g, expr):
    if isinstance(expr, URIRef):
        return expr
    tag = expr[0]
    if tag in ('And', 'Or'):
        node = BNode()
        g.add((node, RDF.type, MANCH[tag]))
        items = [_encode_class_expr(g, e) for e in expr[1]]
        g.add((node, MANCH.operands, _build_rdf_list(g, items)))
        return node
    if tag == 'Not':
        node = BNode()
        g.add((node, RDF.type, MANCH.Not))
        g.add((node, MANCH.operand, _encode_class_expr(g, expr[1])))
        return node
    if tag == 'OneOf':
        node = BNode()
        g.add((node, RDF.type, MANCH.OneOf))
        g.add((node, MANCH.individuals, _build_rdf_list(g, expr[1])))
        return node
    if tag in ('Some', 'Only'):
        _, prop_expr, filler = expr
        node = BNode()
        g.add((node, RDF.type, MANCH[tag]))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        g.add((node, MANCH.filler, _encode_class_expr(g, filler)))
        return node
    if tag == 'Value':
        _, prop_expr, value = expr
        node = BNode()
        g.add((node, RDF.type, MANCH.Value))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        g.add((node, MANCH.filler, value))
        return node
    if tag == 'SelfR':
        _, prop_expr = expr
        node = BNode()
        g.add((node, RDF.type, MANCH.SelfR))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        return node
    if tag in ('Min', 'Max', 'Exact'):
        _, n, prop_expr, filler = expr
        node = BNode()
        g.add((node, RDF.type, MANCH[tag]))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        g.add((node, MANCH.cardinality, Literal(n, datatype=XSD.nonNegativeInteger)))
        if filler is not None:
            g.add((node, MANCH.filler, _encode_class_expr(g, filler)))
        return node
    raise AssertionError(f'unhandled class-expression tag {tag!r}')


def _encode_data_range(g, dr):
    if isinstance(dr, URIRef):
        return dr
    tag = dr[0]
    if tag in ('DAnd', 'DOr'):
        node = BNode()
        g.add((node, RDF.type, MANCH[tag]))
        items = [_encode_data_range(g, e) for e in dr[1]]
        g.add((node, MANCH.operands, _build_rdf_list(g, items)))
        return node
    if tag == 'DNot':
        node = BNode()
        g.add((node, RDF.type, MANCH.DNot))
        g.add((node, MANCH.operand, _encode_data_range(g, dr[1])))
        return node
    if tag == 'DOneOf':
        node = BNode()
        g.add((node, RDF.type, MANCH.DOneOf))
        g.add((node, MANCH.literals, _build_rdf_list(g, dr[1])))
        return node
    if tag == 'DRestriction':
        _, datatype, facets = dr
        node = BNode()
        g.add((node, RDF.type, MANCH.DRestriction))
        g.add((node, MANCH.onDatatype, datatype))
        facet_nodes = []
        for facet_uri, lit in facets:
            fn = BNode()
            g.add((fn, RDF.type, MANCH.FacetRestriction))
            g.add((fn, MANCH.facetPredicate, facet_uri))
            g.add((fn, MANCH.facetValue, lit))
            facet_nodes.append(fn)
        g.add((node, MANCH.facets, _build_rdf_list(g, facet_nodes)))
        return node
    raise AssertionError(f'unhandled data-range tag {dr[0]!r}')


# Which encoder a clause's own item values need, keyed by the clause class -
# 'class' -> _encode_class_expr, 'prop' -> _encode_prop_expr,
# 'data' -> _encode_data_range, 'name' -> bare URIRef (no encoding needed),
# 'characteristic' -> already-resolved URIRef (no encoding needed, same as
# 'name'), 'fact' -> handled specially by _encode_fact_item.
_CLAUSE_VALUE_KIND = {
    MANCH.ClassSubClassOfClause: 'class',
    MANCH.ClassEquivalentToClause: 'class',
    MANCH.ClassDisjointWithClause: 'class',
    MANCH.ClassDisjointUnionOfClause: 'class_list',
    MANCH.ClassHasKeyClause: 'prop_list',
    MANCH.ObjPropDomainClause: 'class',
    MANCH.ObjPropRangeClause: 'class',
    MANCH.ObjPropSubPropertyOfClause: 'prop',
    MANCH.ObjPropEquivalentToClause: 'prop',
    MANCH.ObjPropDisjointWithClause: 'prop',
    MANCH.ObjPropInverseOfClause: 'prop',
    MANCH.ObjPropCharacteristicsClause: 'characteristic',
    MANCH.ObjPropSubPropertyChainClause: 'prop_list',
    MANCH.DataPropDomainClause: 'class',
    MANCH.DataPropRangeClause: 'data',
    MANCH.DataPropSubPropertyOfClause: 'prop',
    MANCH.DataPropEquivalentToClause: 'prop',
    MANCH.DataPropDisjointWithClause: 'prop',
    MANCH.DataPropCharacteristicsClause: 'characteristic',
    MANCH.AnnPropDomainClause: 'name',
    MANCH.AnnPropRangeClause: 'name',
    MANCH.AnnPropSubPropertyOfClause: 'name',
    MANCH.IndividualTypesClause: 'class',
    MANCH.IndividualSameAsClause: 'name',
    MANCH.IndividualDifferentFromClause: 'name',
    MANCH.DatatypeEquivalentToClause: 'data',
}

_MISC_VALUE_KIND = {
    MANCH.MiscEquivalentClassesAxiom: 'class',
    MANCH.MiscDisjointClassesAxiom: 'class',
    MANCH.MiscEquivalentPropertiesAxiom: 'prop',
    MANCH.MiscDisjointPropertiesAxiom: 'prop',
    MANCH.MiscSameIndividualAxiom: 'name',
    MANCH.MiscDifferentIndividualsAxiom: 'name',
}


def _encode_value(g, kind, value):
    if kind == 'class':
        return _encode_class_expr(g, value)
    if kind == 'prop':
        return _encode_prop_expr(g, value)
    if kind == 'data':
        return _encode_data_range(g, value)
    if kind in ('name', 'characteristic'):
        return value
    raise AssertionError(f'unhandled value kind {kind!r}')


def _encode_annotations(g, anns):
    if not anns:
        return None
    nodes = []
    for prop, value in anns:
        node = BNode()
        g.add((node, RDF.type, MANCH.AnnotationAssertion))
        g.add((node, MANCH.annotationProperty, prop))
        g.add((node, MANCH.annotationValue, value))
        nodes.append(node)
    return _build_rdf_list(g, nodes)


def _encode_clause_item(g, kind, anns, value):
    node = BNode()
    g.add((node, RDF.type, MANCH.ClauseItem))
    g.add((node, MANCH.value, _encode_value(g, kind, value)))
    ann_list = _encode_annotations(g, anns)
    if ann_list is not None:
        g.add((node, MANCH.annotations, ann_list))
    return node


def _encode_fact_item(g, anns, fact):
    negative, prop, value = fact
    node = BNode()
    g.add((node, RDF.type, MANCH.FactItem))
    g.add((node, MANCH.negative, Literal(negative)))
    g.add((node, MANCH.property, prop))
    g.add((node, MANCH.value, value))
    ann_list = _encode_annotations(g, anns)
    if ann_list is not None:
        g.add((node, MANCH.annotations, ann_list))
    return node


def _encode_clause_items(g, clause_class, frame_kind, clause_kind, items):
    if clause_kind == 'Annotations:':
        # Frame-level Annotations: - bare AnnotationAssertion items, no
        # ClauseItem wrapper, no per-item annotations slot.
        nodes = []
        for prop, value in items:
            node = BNode()
            g.add((node, RDF.type, MANCH.AnnotationAssertion))
            g.add((node, MANCH.annotationProperty, prop))
            g.add((node, MANCH.annotationValue, value))
            nodes.append(node)
        return nodes
    if clause_kind == 'Facts:':
        return [_encode_fact_item(g, anns, fact) for anns, fact in items]
    value_kind = _CLAUSE_VALUE_KIND[clause_class]
    if value_kind in ('class_list', 'prop_list'):
        # Single-axiom clause: items is [(anns, [values...])].
        (anns, values), = items
        inner_kind = 'class' if value_kind == 'class_list' else 'prop'
        encoded = _build_rdf_list(g, [_encode_value(g, inner_kind, v) for v in values])
        return [_encode_clause_item(g, 'name', anns, encoded)]
    return [_encode_clause_item(g, value_kind, anns, value) for anns, value in items]


# ---------------------------------------------------------------------------
# Encode - _Cursor subclass overriding the AST-capture hooks
# ---------------------------------------------------------------------------

class _AstCursor(_Cursor):
    def __init__(self, tokens, base):
        super().__init__(tokens, base)
        self.ast_graph = Graph()
        self.ast_graph.bind('manch', MANCH)
        self._prefix_nodes = []
        self._header_node = None
        self._frame_nodes = []
        self._misc_nodes = []
        self._current_frame_node = None
        self._current_frame_class = None
        self._current_frame_clause_nodes = None

    def record_prefix(self, prefix, iri):
        g = self.ast_graph
        node = BNode()
        g.add((node, RDF.type, MANCH.PrefixDecl))
        g.add((node, MANCH.prefixLabel, Literal(prefix, datatype=MANCH.PyStr)))
        g.add((node, MANCH.prefixIri, Literal(iri)))
        self._prefix_nodes.append(node)

    def record_ontology_header(self, iri, imports):
        g = self.ast_graph
        node = BNode()
        g.add((node, RDF.type, MANCH.OntologyHeader))
        if iri is not None:
            g.add((node, MANCH.ontologyIri, iri))
        g.add((node, MANCH.imports, _build_rdf_list(g, list(imports))))
        self._header_node = node

    def record_frame(self, kind, subject):
        g = self.ast_graph
        node = BNode()
        frame_class = _FRAME_CLASS[kind]
        g.add((node, RDF.type, frame_class))
        g.add((node, MANCH.subject, subject))
        self._current_frame_node = node
        self._current_frame_class = frame_class
        self._current_frame_clause_nodes = []
        self._frame_nodes.append(node)

    def record_clause(self, frame_kind, clause_kind, items):
        g = self.ast_graph
        clause_class = _CLAUSE_CLASS[(frame_kind, clause_kind)]
        node = BNode()
        g.add((node, RDF.type, clause_class))
        item_nodes = _encode_clause_items(g, clause_class, frame_kind, clause_kind, items)
        g.add((node, MANCH.items, _build_rdf_list(g, item_nodes)))
        if clause_kind in _REVERSED_CLAUSE_KEYWORDS:
            g.add((node, MANCH.reversed, Literal(True)))
        self._current_frame_clause_nodes.append(node)

    def record_frame_end(self):
        g = self.ast_graph
        g.add((self._current_frame_node, MANCH.clauses,
                _build_rdf_list(g, self._current_frame_clause_nodes)))
        self._current_frame_node = None
        self._current_frame_clause_nodes = None

    def record_misc(self, keyword, items):
        g = self.ast_graph
        misc_class = _MISC_CLASS[keyword]
        node = BNode()
        g.add((node, RDF.type, misc_class))
        value_kind = _MISC_VALUE_KIND[misc_class]
        item_nodes = [_encode_value(g, value_kind, v) for v in items]
        g.add((node, MANCH.items, _build_rdf_list(g, item_nodes)))
        self._misc_nodes.append(node)


def parse_manchester_ast(text: str, base: str | None = None) -> tuple[Graph, BNode]:
    """Parse Manchester Syntax text straight to its ``manch:``-encoded AST.

    Reuses ``manchester_parser.py``'s own tokenizer, frame/clause dispatch,
    and expression/data-range grammar completely unchanged - only the
    (already no-op-by-default) AST-capture hooks are overridden, via
    ``_AstCursor``. See this module's own docstring for the exact fidelity
    scope (matches the parser's existing internal AST, not raw text).

    Returns ``(graph, root)`` where ``root`` is the ``manch:Document`` node.
    """
    cur = _AstCursor(_tokenize(text), base)
    _run_top_level(cur)

    g = cur.ast_graph
    root = BNode()
    g.add((root, RDF.type, MANCH.Document))
    g.add((root, MANCH.prefixes, _build_rdf_list(g, cur._prefix_nodes)))
    if cur._header_node is not None:
        g.add((root, MANCH.header, cur._header_node))
    g.add((root, MANCH.frames, _build_rdf_list(g, cur._frame_nodes)))
    g.add((root, MANCH.misc, _build_rdf_list(g, cur._misc_nodes)))
    return g, root


def _run_top_level(cur):
    """The exact same top-level dispatch loop as
    manchester_parser.parse_manchester(), reused verbatim rather than
    duplicated - it's already generic over `cur`, dispatching purely on
    frame keywords, so an _AstCursor drives it identically to a plain
    _Cursor. Kept as a local import-and-copy rather than refactoring
    parse_manchester() itself to accept a pre-built cursor, since that
    function's own signature (text, base) -> list is a stable, tested
    public entry point not worth changing shape for this."""
    from starlayergraph.parsers import manchester_parser as _mp

    while True:
        word = cur.peek_word()
        if word is None:
            break
        if word == 'Prefix:':
            cur.advance()
            name_tok = cur.advance()
            if name_tok['kind'] != 'WORD' or not name_tok['text'].endswith(':'):
                cur.error("expected a prefix name ending in ':'")
            prefix = name_tok['text'][:-1]
            iri_tok = cur.advance()
            if iri_tok['kind'] != 'IRI':
                cur.error('expected an <IRI> for the Prefix: declaration')
            cur.prefixes[prefix] = iri_tok['text']
            cur.record_prefix(prefix, iri_tok['text'])
        elif word == 'Ontology:':
            cur.advance()
            tok = cur.peek()
            ontology_iri = None
            if tok is not None and tok['kind'] == 'IRI':
                cur.advance()
                ontology_iri = cur.resolve_iri(tok['text'])
                cur.base = str(ontology_iri)
                cur.triples.append((ontology_iri, RDF.type, _mp.OWL.Ontology))
            imports = []
            while cur.peek_word() == 'Import:':
                cur.advance()
                imported = cur.read_name()
                imports.append(imported)
                if ontology_iri is not None:
                    cur.triples.append((ontology_iri, _mp.OWL.imports, imported))
            if cur.peek_word() == 'Annotations:':
                cur.error('Annotations: in the Ontology: header is not supported yet')
            cur.record_ontology_header(ontology_iri, imports)
        elif word == 'Datatype:':
            cur.advance()
            _mp._parse_datatype_frame(cur)
        elif word == 'Class:':
            cur.advance()
            _mp._parse_class_frame(cur)
        elif word == 'ObjectProperty:':
            cur.advance()
            _mp._parse_property_frame(cur, 'ObjectProperty', _mp.OWL.ObjectProperty,
                                       _mp._OBJPROP_CLAUSES, _mp._OBJPROP_DEFERRED,
                                       range_is_class_expr=True)
        elif word == 'DataProperty:':
            cur.advance()
            _mp._parse_property_frame(cur, 'DataProperty', _mp.OWL.DatatypeProperty,
                                       _mp._DATAPROP_CLAUSES, _mp._DATAPROP_DEFERRED,
                                       range_is_class_expr=False)
        elif word == 'AnnotationProperty:':
            cur.advance()
            _mp._parse_annotation_property_frame(cur)
        elif word == 'Individual:':
            cur.advance()
            _mp._parse_individual_frame(cur)
        elif word in ('EquivalentClasses:', 'DisjointClasses:', 'EquivalentProperties:',
                      'DisjointProperties:', 'SameIndividual:', 'DifferentIndividuals:'):
            cur.advance()
            _parse_misc(cur, word)
        else:
            cur.error(f'expected a Prefix:/Ontology:/frame/Misc-axiom keyword, got {word!r}')


# ---------------------------------------------------------------------------
# Decode - real AST objects, mirroring manchester_parser.py's own tagged
# tuples for expressions/data ranges, plus new lightweight namedtuples for
# the frame/clause half (which has no such tuple form in the parser today).
# ---------------------------------------------------------------------------

Document = namedtuple('Document', ['prefixes', 'header', 'frames', 'misc'])
PrefixDecl = namedtuple('PrefixDecl', ['label', 'iri'])
OntologyHeader = namedtuple('OntologyHeader', ['iri', 'imports'])
Frame = namedtuple('Frame', ['kind', 'subject', 'clauses'])
Clause = namedtuple('Clause', ['clause_kind', 'items'])
ClauseItem = namedtuple('ClauseItem', ['value', 'annotations'])
FactItem = namedtuple('FactItem', ['negative', 'property', 'value', 'annotations'])
AnnotationAssertion = namedtuple('AnnotationAssertion', ['property', 'value'])


def _decode_prop_expr(g, node):
    if not isinstance(node, BNode):
        return node
    if (node, RDF.type, MANCH.Inverse) in g:
        return ('Inverse', g.value(node, MANCH.operand))
    raise ValueError(f'unrecognized property-expression node {node!r}')


def _node_types(g, node):
    return {o for _s, _p, o in g.triples((node, RDF.type, None))}


def _decode_class_expr(g, node):
    if not isinstance(node, BNode):
        return node
    types = _node_types(g, node)
    for tag in ('And', 'Or'):
        if MANCH[tag] in types:
            items = [_decode_class_expr(g, i) for i in _read_rdf_list(g, g.value(node, MANCH.operands))]
            return (tag, items)
    if MANCH.Not in types:
        return ('Not', _decode_class_expr(g, g.value(node, MANCH.operand)))
    if MANCH.OneOf in types:
        return ('OneOf', _read_rdf_list(g, g.value(node, MANCH.individuals)))
    for tag in ('Some', 'Only'):
        if MANCH[tag] in types:
            prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
            filler = _decode_class_expr(g, g.value(node, MANCH.filler))
            return (tag, prop, filler)
    if MANCH.Value in types:
        prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
        value = g.value(node, MANCH.filler)
        return ('Value', prop, value)
    if MANCH.SelfR in types:
        return ('SelfR', _decode_prop_expr(g, g.value(node, MANCH.onProperty)))
    for tag in ('Min', 'Max', 'Exact'):
        if MANCH[tag] in types:
            prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
            n = int(g.value(node, MANCH.cardinality))
            filler_node = g.value(node, MANCH.filler)
            filler = _decode_class_expr(g, filler_node) if filler_node is not None else None
            return (tag, n, prop, filler)
    raise ValueError(f'unrecognized class-expression node {node!r} (types: {types})')


def _decode_data_range(g, node):
    if not isinstance(node, BNode):
        return node
    types = _node_types(g, node)
    for tag in ('DAnd', 'DOr'):
        if MANCH[tag] in types:
            items = [_decode_data_range(g, i) for i in _read_rdf_list(g, g.value(node, MANCH.operands))]
            return (tag, items)
    if MANCH.DNot in types:
        return ('DNot', _decode_data_range(g, g.value(node, MANCH.operand)))
    if MANCH.DOneOf in types:
        return ('DOneOf', _read_rdf_list(g, g.value(node, MANCH.literals)))
    if MANCH.DRestriction in types:
        datatype = g.value(node, MANCH.onDatatype)
        facets = []
        for fn in _read_rdf_list(g, g.value(node, MANCH.facets)):
            facets.append((g.value(fn, MANCH.facetPredicate), g.value(fn, MANCH.facetValue)))
        return ('DRestriction', datatype, facets)
    raise ValueError(f'unrecognized data-range node {node!r} (types: {types})')


def _decode_value(g, kind, node):
    if kind == 'class':
        return _decode_class_expr(g, node)
    if kind == 'prop':
        return _decode_prop_expr(g, node)
    if kind == 'data':
        return _decode_data_range(g, node)
    if kind in ('name', 'characteristic'):
        return node
    raise AssertionError(f'unhandled value kind {kind!r}')


def _decode_annotations(g, ann_list_node):
    if ann_list_node is None:
        return None
    result = []
    for node in _read_rdf_list(g, ann_list_node):
        result.append((g.value(node, MANCH.annotationProperty), g.value(node, MANCH.annotationValue)))
    return result


def _decode_clause(g, node):
    types = _node_types(g, node)
    clause_class = next(t for t in types if t in _CLAUSE_CLASS_TO_KIND)
    _frame_kind, clause_kind = _CLAUSE_CLASS_TO_KIND[clause_class]
    if bool(g.value(node, MANCH.reversed)):
        clause_kind = {'SubClassOf:': 'SuperClassOf:', 'SubPropertyOf:': 'SuperPropertyOf:'}[clause_kind]
    item_nodes = _read_rdf_list(g, g.value(node, MANCH.items))

    if clause_kind == 'Annotations:':
        items = [AnnotationAssertion(g.value(n, MANCH.annotationProperty),
                                      g.value(n, MANCH.annotationValue)) for n in item_nodes]
        return Clause(clause_kind, items)

    if clause_kind == 'Facts:':
        items = []
        for n in item_nodes:
            negative = bool(g.value(n, MANCH.negative))
            prop = g.value(n, MANCH.property)
            value = g.value(n, MANCH.value)
            anns = _decode_annotations(g, g.value(n, MANCH.annotations))
            items.append(FactItem(negative, prop, value, anns))
        return Clause(clause_kind, items)

    value_kind = _CLAUSE_VALUE_KIND[clause_class]
    if value_kind in ('class_list', 'prop_list'):
        (item_node,) = item_nodes
        inner_kind = 'class' if value_kind == 'class_list' else 'prop'
        encoded_list = g.value(item_node, MANCH.value)
        values = [_decode_value(g, inner_kind, v) for v in _read_rdf_list(g, encoded_list)]
        anns = _decode_annotations(g, g.value(item_node, MANCH.annotations))
        return Clause(clause_kind, [ClauseItem(values, anns)])

    items = []
    for n in item_nodes:
        value = _decode_value(g, value_kind, g.value(n, MANCH.value))
        anns = _decode_annotations(g, g.value(n, MANCH.annotations))
        items.append(ClauseItem(value, anns))
    return Clause(clause_kind, items)


def _decode_frame(g, node):
    types = _node_types(g, node)
    frame_class = next(t for t in types if t in _FRAME_CLASS_TO_KIND)
    kind = _FRAME_CLASS_TO_KIND[frame_class]
    subject = g.value(node, MANCH.subject)
    clauses = [_decode_clause(g, n) for n in _read_rdf_list(g, g.value(node, MANCH.clauses))]
    return Frame(kind, subject, clauses)


def _decode_misc(g, node):
    types = _node_types(g, node)
    misc_class = next(t for t in types if t in _MISC_CLASS_TO_KEYWORD)
    keyword = _MISC_CLASS_TO_KEYWORD[misc_class]
    value_kind = _MISC_VALUE_KIND[misc_class]
    items = [_decode_value(g, value_kind, n) for n in _read_rdf_list(g, g.value(node, MANCH.items))]
    return Clause(keyword, items)


def rdf_ast_to_manchester_ast(graph: Graph, root) -> Document:
    """Decode a ``manch:``-shaped RDF graph back into a real ``Document``
    object. ``root`` must be the ``manch:Document`` node, as returned by
    ``parse_manchester_ast``."""
    prefixes = [PrefixDecl(str(graph.value(n, MANCH.prefixLabel)), str(graph.value(n, MANCH.prefixIri)))
                for n in _read_rdf_list(graph, graph.value(root, MANCH.prefixes))]
    header_node = graph.value(root, MANCH.header)
    header = None
    if header_node is not None:
        iri = graph.value(header_node, MANCH.ontologyIri)
        imports = _read_rdf_list(graph, graph.value(header_node, MANCH.imports))
        header = OntologyHeader(iri, imports)
    frames = [_decode_frame(graph, n) for n in _read_rdf_list(graph, graph.value(root, MANCH.frames))]
    misc = [_decode_misc(graph, n) for n in _read_rdf_list(graph, graph.value(root, MANCH.misc))]
    return Document(prefixes, header, frames, misc)


# ---------------------------------------------------------------------------
# Document -> Manchester Syntax text (new, from-scratch serializer - the
# literal inverse of manchester_parser.py's own tuple vocabulary, not
# adapted from serializers/manchester.py - see this module's own docstring)
# ---------------------------------------------------------------------------

def _render_name(node) -> str:
    return f'<{node}>'


def _render_literal(lit: Literal) -> str:
    if lit.language:
        return f'"{lit}"@{lit.language}'
    if lit.datatype:
        return f'"{lit}"^^<{lit.datatype}>'
    return f'"{lit}"'


def _render_value(v) -> str:
    if isinstance(v, Literal):
        return _render_literal(v)
    return _render_name(v)


def _render_prop_expr(expr) -> str:
    if isinstance(expr, URIRef):
        return _render_name(expr)
    tag, uri = expr
    assert tag == 'Inverse'
    return f'inverse {_render_name(uri)}'


def _paren(text: str, needed: bool) -> str:
    return f'({text})' if needed else text


def _render_class_expr(expr, top: bool = True) -> str:
    if isinstance(expr, URIRef):
        return _render_name(expr)
    tag = expr[0]
    if tag == 'And':
        inner = ' and '.join(_render_class_expr(e, top=False) for e in expr[1])
        return _paren(inner, not top)
    if tag == 'Or':
        inner = ' or '.join(_render_class_expr(e, top=False) for e in expr[1])
        return _paren(inner, not top)
    if tag == 'Not':
        return _paren(f'not {_render_class_expr(expr[1], top=False)}', not top)
    if tag == 'OneOf':
        return '{' + ', '.join(_render_name(u) for u in expr[1]) + '}'
    if tag in ('Some', 'Only'):
        _, prop, filler = expr
        kw = 'some' if tag == 'Some' else 'only'
        inner = f'{_render_prop_expr(prop)} {kw} {_render_class_expr(filler, top=False)}'
        return _paren(inner, not top)
    if tag == 'Value':
        _, prop, value = expr
        return _paren(f'{_render_prop_expr(prop)} value {_render_value(value)}', not top)
    if tag == 'SelfR':
        _, prop = expr
        return _paren(f'{_render_prop_expr(prop)} Self', not top)
    if tag in ('Min', 'Max', 'Exact'):
        _, n, prop, filler = expr
        kw = {'Min': 'min', 'Max': 'max', 'Exact': 'exactly'}[tag]
        inner = f'{_render_prop_expr(prop)} {kw} {n}'
        if filler is not None:
            inner += f' {_render_class_expr(filler, top=False)}'
        return _paren(inner, not top)
    raise AssertionError(f'unhandled class-expression tag {tag!r}')


def _render_data_range(dr, top: bool = True) -> str:
    if isinstance(dr, URIRef):
        return _render_name(dr)
    tag = dr[0]
    if tag == 'DAnd':
        inner = ' and '.join(_render_data_range(e, top=False) for e in dr[1])
        return _paren(inner, not top)
    if tag == 'DOr':
        inner = ' or '.join(_render_data_range(e, top=False) for e in dr[1])
        return _paren(inner, not top)
    if tag == 'DNot':
        return _paren(f'not {_render_data_range(dr[1], top=False)}', not top)
    if tag == 'DOneOf':
        return '{' + ', '.join(_render_value(lit) for lit in dr[1]) + '}'
    if tag == 'DRestriction':
        _, datatype, facets = dr
        facet_strs = [f'{_DATA_FACETS_INV[facet_uri]} {_render_value(lit)}' for facet_uri, lit in facets]
        return f'{_render_name(datatype)}[' + ', '.join(facet_strs) + ']'
    raise AssertionError(f'unhandled data-range tag {tag!r}')


def _render_annotations_prefix(anns) -> str:
    if not anns:
        return ''
    parts = ', '.join(f'{_render_name(p)} {_render_value(v)}' for p, v in anns)
    return f'Annotations: {parts} '


def _render_one(clause_class, value) -> str:
    """Render a single clause item's own value, dispatching on what kind of
    grammar this clause's items hold - class expression, property
    expression, data range, or a bare name/URIRef/Literal needing no
    further rendering. Takes the resolved clause *class* directly (not a
    bare clause_kind string) - several clause keywords (Domain:/Range:/
    EquivalentTo:/DisjointWith:/Annotations:/SubPropertyOf:) are shared
    across multiple frame kinds mapping to genuinely different classes
    (e.g. ObjPropRangeClause's items are a ClassExpression, but
    DataPropRangeClause's are a DataRange) - resolving from the keyword
    string alone, ignoring which frame it's in, would silently render the
    wrong grammar for whichever one isn't first in _CLAUSE_CLASS."""
    value_kind = _CLAUSE_VALUE_KIND.get(clause_class) or _MISC_VALUE_KIND.get(clause_class)
    if value_kind == 'class':
        return _render_class_expr(value)
    if value_kind == 'prop':
        return _render_prop_expr(value)
    if value_kind == 'data':
        return _render_data_range(value)
    if value_kind == 'characteristic':
        return _CHARACTERISTICS_INV[value]
    return _render_value(value) if isinstance(value, Literal) else _render_name(value)


def _render_clause(clause: Clause, frame_kind: str) -> str:
    kind = clause.clause_kind
    if kind == 'Annotations:':
        items = ', '.join(f'{_render_name(a.property)} {_render_value(a.value)}' for a in clause.items)
        return f'Annotations: {items}'
    if kind == 'Facts:':
        parts = []
        for item in clause.items:
            prefix = _render_annotations_prefix(item.annotations)
            neg = 'not ' if item.negative else ''
            parts.append(f'{prefix}{neg}{_render_name(item.property)} {_render_value(item.value)}')
        return f'Facts: {", ".join(parts)}'
    clause_class = _CLAUSE_CLASS[(frame_kind, kind)]
    if kind in ('DisjointUnionOf:', 'HasKey:', 'SubPropertyChain:'):
        (item,) = clause.items
        prefix = _render_annotations_prefix(item.annotations)
        value_kind = _CLAUSE_VALUE_KIND[clause_class]
        inner_kind = 'class' if value_kind == 'class_list' else 'prop'
        if kind == 'SubPropertyChain:':
            rendered = ' o '.join(_render_prop_expr(v) for v in item.value)
        else:
            renderer = _render_class_expr if inner_kind == 'class' else _render_prop_expr
            rendered = ', '.join(renderer(v) for v in item.value)
        return f'{kind} {prefix}{rendered}'
    # Ordinary per-item-annotatable clause.
    parts = []
    for item in clause.items:
        prefix = _render_annotations_prefix(item.annotations)
        parts.append(f'{prefix}{_render_one(clause_class, item.value)}')
    return f'{kind} {", ".join(parts)}'


def _render_misc(clause: Clause) -> str:
    # Misc keywords are globally unique (no frame-kind ambiguity - each of
    # the 6 maps to exactly one class in _MISC_CLASS).
    misc_class = _MISC_CLASS[clause.clause_kind]
    rendered = ', '.join(_render_one(misc_class, v) for v in clause.items)
    return f'{clause.clause_kind} {rendered}'


_FRAME_KEYWORD = {
    'Class': 'Class:', 'ObjectProperty': 'ObjectProperty:', 'DataProperty': 'DataProperty:',
    'AnnotationProperty': 'AnnotationProperty:', 'Individual': 'Individual:', 'Datatype': 'Datatype:',
}


def _render_frame(frame: Frame) -> str:
    lines = [f'{_FRAME_KEYWORD[frame.kind]} {_render_name(frame.subject)}']
    for clause in frame.clauses:
        lines.append('    ' + _render_clause(clause, frame.kind))
    return '\n'.join(lines)


def manchester_ast_to_text(document: Document) -> str:
    """Render a ``Document`` (as returned by ``rdf_ast_to_manchester_ast``)
    back to real Manchester Syntax text."""
    lines = []
    for p in document.prefixes:
        label = p.label if p.label else ''
        lines.append(f'Prefix: {label}: <{p.iri}>')
    if document.header is not None:
        h = document.header
        header_line = 'Ontology:' if h.iri is None else f'Ontology: <{h.iri}>'
        lines.append(header_line)
        for imp in h.imports:
            lines.append(f'Import: {_render_name(imp)}')
    if lines:
        lines.append('')
    for frame in document.frames:
        lines.append(_render_frame(frame))
        lines.append('')
    for misc in document.misc:
        lines.append(_render_misc(misc))
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def rdf_ast_to_text(graph: Graph, root) -> str:
    """Thin wrapper composing ``rdf_ast_to_manchester_ast`` +
    ``manchester_ast_to_text`` for a caller who just wants text back."""
    return manchester_ast_to_text(rdf_ast_to_manchester_ast(graph, root))
