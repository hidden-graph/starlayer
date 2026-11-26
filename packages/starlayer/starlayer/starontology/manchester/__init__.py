"""starontology.manchester

Everything about managing an OWL 2 Manchester Syntax document as its own
syntax tree, independent of the compiled OWL semantics it maps to - and the
ontology/SHACL-shapes files that tree representation is validated against.
This lives here, not in starlayer.ontology.to_ast_rdf/manchester_shapes,
on the reasoning that Manchester-tree editing is an *ontology-management*
concern (same bucket as starontology itself), not a starlayer.graph concern -
the OWL-compiling parser/serializer pair (StarLayerGraph.parse()/.serialize()
format='manchester') stays in starlayer.graph; only the tree layer and its
own validation live here.

Four entry points:

- ``manchester_to_tree(text, base=None) -> StarLayerGraph`` - parse Manchester text
  straight to its ``manch:``-encoded syntax tree, reusing
  ``starlayer.graph.manchester.parser``'s own tokenizer/frame/
  clause/expression-parsing functions completely unchanged (via a
  ``_Cursor`` subclass overriding its no-op syntax-tree-capture hooks - see that
  module's own comments on ``_Cursor.record_frame``/``record_clause``/etc).
  Returns just the graph, not a ``(graph, root)`` tuple (changed
  2026-10-03) - every graph this produces holds exactly one
  ``manch:OntologyDocument`` node (there's no ``graph=`` parameter to merge
  several into one shared graph, unlike ``srl.ruleset_to_tree()``'s real
  ``salg:QueryCollection``-style use case), so ``_find_root()`` locates it
  internally wherever it's needed instead of making every caller carry it
  around separately.
- ``tree_to_manchester(tree_graph) -> str`` - the inverse: render ``manch:`` tree-RDF
  back to real Manchester Syntax text.
- ``tree_to_owl(tree_graph) -> StarLayerGraph`` - the tree's compiled OWL
  content, as a real graph (not a bare ``list[tuple]``, changed
  2026-10-03) - by composing ``tree_to_manchester()`` with
  ``manchester_parser.parse_manchester()`` (the real, trusted OWL compiler)
  and adding the result into a fresh ``StarLayerGraph``, the same way
  ``StarLayerGraph.parse(format='manchester')`` already populates one.
  Going through text here is safe, not a shortcut-that-loses-fidelity:
  ``tree_to_manchester()`` is a fully faithful renderer of everything this module
  captures, so nothing is lost before the OWL compiler sees it.
- ``validate_manchester_tree(tree_graph)``, which returns a ``ValidationReport``, -
  structural SHACL validation of a ``manch:`` graph (e.g. straight out of
  ``manchester_to_tree()``, or LLM-authored, not yet decoded) against the shapes
  in ``manchester_shapes.ttl``. Only needs the tree being checked - which
  shapes to check it against is this module's own, fixed concern.

**Ordered children are ordinals, not an ``rdf:List``.** Prefixes, frames, clauses, a clause's entries, class and data-range operands,
enumerations, facets, imports, annotations and misc axioms are written with the shared ``tree:`` vocabulary (``graph/ordinals.py``):
a blank node child (a frame, clause, entry, expression) carries ``tree:ord`` itself and so has one parent; an IRI or literal member
sits in a ``tree:Item`` (``tree:value``) and may be shared. An empty sequence is an absent property. The three single-axiom clauses
(``DisjointUnionOf:``, ``HasKey:``, ``SubPropertyChain:``) have one ``manch:ClauseItem`` that holds its members as ordered
``manch:values`` (where ``manch:value`` was a nested list). ``graph.ordinals.append`` / ``insert_at`` / ``remove_at`` / ``replace_at``
edit a sequence and ``renumber_dense`` closes gaps (run it before hashing). The decoders raise ``FormatError`` (kind ``"rdf"``) for a
tie or a missing or non-integer ordinal; ``validate_manchester_tree`` reports the same as shape violations. The errors of the Manchester
parser are ``FormatError`` (kind ``"manchester"``) too, with ``why``, ``line`` and a position; a class expression nested too deeply to parse or
render is an ``ExecutionError`` (kind ``"nesting"``), and a node of the tree that no ``manch:`` type describes is a ``FormatError`` (kind
``"manchester"``, context ``manch: tree``). ``ValueError`` stays for a graph argument that holds no ``manch:OntologyDocument``, or already holds
one.

**Editing is meant to happen on the tree-RDF itself (plain graph surgery -
``graph.add()``/``.remove()``), not on a Python object.** ``_tree_to_document()``/
``_document_to_text()`` (private - were public until 2026-10-03) decode/render
through an intermediate ``Document`` namedtuple-of-namedtuples; ``tree_to_manchester()``
still composes them internally; since there's exactly one way into this
module (``manchester_to_tree``) and one way out (``tree_to_manchester``/``tree_to_owl``),
there's no legitimate public use for a bare ``Document`` object in between -
unlike SRL's ``RuleSet`` (see ``starlayer.sparql.srl``'s own docstring),
which is a real, independently-useful object other code consumes directly,
``Document`` only ever existed as a decode artifact of this module's own
text renderer.

**No public ``ontology_graph()``/``shapes_graph()`` here** (removed
2026-10-03, matching the same decision for ``srl:``) - a caller who wants
the raw ``manch:`` ontology/shapes graphs themselves can already get them
from ``starontology`` directly instead: ``get_ontology_graph(
"manchester_owl")`` / ``get_ontology_graph("manchester_shacl")``.
``validate_manchester_tree()`` calls ``get_ontology_graph()`` directly inline - unlike
``validate_sparql_tree()``, there's no combining-with-another-vocabulary's-shapes
logic for ``manch:`` to even privately wrap.

**Why this module imports other parts of ``starlayer`` at all, despite
starontology's own general "pure data, no logic" design (see
``starlayer.starontology/__init__.py``'s own docstring)**: that principle
covers the *shared loader* (``get_ontology_graph()`` etc, which stays
data-only), not every submodule under it - Manchester genuinely needs real
logic (a parser/renderer/validator), and a home outside ``starlayer.graph``
(the triplestore core, which shouldn't carry per-vocabulary parse/validate
logic) and ``starlayer.sparql`` (unrelated machinery) - ``starontology`` was
the agreed home for it instead (see the design discussion this followed).
``srl:`` is expected to join it here eventually, once the sibling
``starlayer.sparql`` module (where it currently lives, interleaved with
``salg:``/``sast:``'s shared internals) gets its own pass.

**Why the ``starlayer.graph`` imports below are all deferred inside function
bodies, never at this module's own top level**: a top-level
``from starlayer.graph... import ...`` here would trigger ``starlayer``'s
own ``__init__.py`` import chain first (Python always fully runs a parent
package's ``__init__.py`` before any of its submodules, including this
one) - by the time this module's own code runs, ``starlayer.graph``/
``.shacl`` are already loaded, so the historical circular-import deadlock
this once guarded against (from when ``starontology`` was a separately-
installed package with no guaranteed load order relative to ``starlayer``
at all) is now structurally impossible, not just avoided by convention.
Staying deferred here costs nothing and keeps this module consistent with
``starontology/__init__.py``'s own ``_load()``, so
it's kept anyway - just no longer load-bearing. This is also why
``_SyntaxTreeCursor`` (which needs ``_Cursor`` as a base class at
class-definition time) is defined *inside* ``manchester_to_tree()`` rather than
at module scope, and why the characteristic/data-facet reverse-lookup maps
are built lazily on first use rather than at import time.

**Fidelity scope**: matches
``manchester_parser.py``'s own internal AST exactly - ``onlysome``/``that``/
``SuperClassOf:`` spelling are not recoverable (already desugared before
this module ever sees them), the same bar ``salg:`` itself holds for SPARQL
(it doesn't preserve original whitespace/query text either).
"""

from __future__ import annotations

from collections import namedtuple
from typing import TYPE_CHECKING, Any

from starlayer.errors import ExecutionError, FormatError
from starlayer.graph.manchester._ox_terms import (
    OWL,
    RDF,
    RDFS,
    XSD,
    BNode,
    Literal,
    URIRef,
    Vocab,
    lexical,
)

from .. import get_ontology_graph

if TYPE_CHECKING:
    from starlayer.shacl.results import ValidationReport

Graph = Any  # a StarLayerGraph (pyoxigraph terms)

MANCH = Vocab("https://github.com/hidden-graph/starlayer/ns/graph/manchester-ast#")

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

    ('ObjectProperty', 'Domain:'): MANCH.ObjectPropertyDomainClause,
    ('ObjectProperty', 'Range:'): MANCH.ObjectPropertyRangeClause,
    ('ObjectProperty', 'SubPropertyOf:'): MANCH.ObjectPropertySubPropertyOfClause,
    ('ObjectProperty', 'SuperPropertyOf:'): MANCH.ObjectPropertySubPropertyOfClause,
    ('ObjectProperty', 'EquivalentTo:'): MANCH.ObjectPropertyEquivalentToClause,
    ('ObjectProperty', 'DisjointWith:'): MANCH.ObjectPropertyDisjointWithClause,
    ('ObjectProperty', 'InverseOf:'): MANCH.ObjectPropertyInverseOfClause,
    ('ObjectProperty', 'Characteristics:'): MANCH.ObjectPropertyCharacteristicsClause,
    ('ObjectProperty', 'SubPropertyChain:'): MANCH.ObjectPropertySubPropertyChainClause,
    ('ObjectProperty', 'Annotations:'): MANCH.ObjectPropertyAnnotationsClause,

    ('DataProperty', 'Domain:'): MANCH.DataPropertyDomainClause,
    ('DataProperty', 'Range:'): MANCH.DataPropertyRangeClause,
    ('DataProperty', 'SubPropertyOf:'): MANCH.DataPropertySubPropertyOfClause,
    ('DataProperty', 'SuperPropertyOf:'): MANCH.DataPropertySubPropertyOfClause,
    ('DataProperty', 'EquivalentTo:'): MANCH.DataPropertyEquivalentToClause,
    ('DataProperty', 'DisjointWith:'): MANCH.DataPropertyDisjointWithClause,
    ('DataProperty', 'Characteristics:'): MANCH.DataPropertyCharacteristicsClause,
    ('DataProperty', 'Annotations:'): MANCH.DataPropertyAnnotationsClause,

    ('AnnotationProperty', 'Domain:'): MANCH.AnnotationPropertyDomainClause,
    ('AnnotationProperty', 'Range:'): MANCH.AnnotationPropertyRangeClause,
    ('AnnotationProperty', 'SubPropertyOf:'): MANCH.AnnotationPropertySubPropertyOfClause,
    ('AnnotationProperty', 'Annotations:'): MANCH.AnnotationPropertyAnnotationsClause,

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

# Built lazily on first use (_inverse_characteristic_maps()), not here at
# import time - these come from starlayer.graph.manchester.parser,
# and this module's cross-package imports all stay deferred; see the module
# docstring's own explanation.
_characteristics_inv: dict | None = None
_data_facets_inv: dict | None = None


def _inverse_characteristic_maps():
    global _characteristics_inv, _data_facets_inv
    if _characteristics_inv is None:
        from starlayer.graph.manchester.parser import (
            _CHARACTERISTICS,
            _DATA_FACETS,
        )
        _characteristics_inv = {v: k for k, v in _CHARACTERISTICS.items()}
        _data_facets_inv = {v: k for k, v in _DATA_FACETS.items()}
    return _characteristics_inv, _data_facets_inv


# ---------------------------------------------------------------------------
# Ordered children (tree: ordinals, graph/ordinals.py)
# ---------------------------------------------------------------------------

def _write_seq(g, parent, prop, members):
    """The ordered children of ``parent`` for ``prop``: a blank node member carries ``tree:ord`` itself, an IRI or literal sits in a
    ``tree:Item``. Nothing is written for no members (an absent property is the empty sequence)."""
    from starlayer.graph import ordinals

    ordinals.write_ordered(g, parent, prop, members)


def _read_seq(g, parent, prop):
    """The members ``parent`` holds for ``prop``, in ordinal order; ``FormatError`` (kind ``"rdf"``) on a tie or a missing or
    non-integer ordinal."""
    from starlayer.graph import ordinals

    return ordinals.ordered_items(g, parent, prop)


# ---------------------------------------------------------------------------
# Class-expression / property-expression / data-range encode
# (mirrors manchester_parser.py's own _expr_node/_prop_node/_data_range_node
# shape exactly - same tags, same arity, manch: predicates instead of the
# OWL 2 RDF Mapping's own)
# ---------------------------------------------------------------------------

# A nodeID (``_:label``) is a BNode in the parser's OWL-semantic output, but this tree uses blank nodes
# for its own structure, so a nodeID is stored as a reserved IRI carrying the label. That keeps every
# "name is an IRI" shape valid, survives graph copying and serialization, and lets the rendered label
# be read back so the text round-trips.
_NODEID_PREFIX = 'urn:starlayer:manchester:nodeid:'

# The parser's own AST tags (graph/manchester/parser.py) are shorter than the manch: class names for the keywords it
# abbreviates: the tag 'Exact' is the class manch:Exactly, 'SelfR' is manch:Self, and a data variant's 'D' is 'Data'.
_CLASS_OF_TAG = {'Exact': 'Exactly', 'SelfR': 'Self', 'DSome': 'DataSome', 'DOnly': 'DataOnly', 'DMin': 'DataMin',
                 'DMax': 'DataMax', 'DExact': 'DataExactly', 'DAnd': 'DataAnd', 'DOr': 'DataOr', 'DNot': 'DataNot',
                 'DOneOf': 'DataOneOf', 'DRestriction': 'DatatypeRestriction'}


def _class_name(tag):
    return _CLASS_OF_TAG.get(tag, tag)



def _enc_term(term):
    return URIRef(_NODEID_PREFIX + term.value) if isinstance(term, BNode) else term


def _dec_term(term):
    if isinstance(term, URIRef) and term.value.startswith(_NODEID_PREFIX):
        return BNode(term.value[len(_NODEID_PREFIX):])
    return term


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
        g.add((node, RDF.type, MANCH[_class_name(tag)]))
        _write_seq(g, node, MANCH.operands, [_encode_class_expr(g, e) for e in expr[1]])
        return node
    if tag == 'Not':
        node = BNode()
        g.add((node, RDF.type, MANCH.Not))
        g.add((node, MANCH.operand, _encode_class_expr(g, expr[1])))
        return node
    if tag == 'OneOf':
        node = BNode()
        g.add((node, RDF.type, MANCH.OneOf))
        _write_seq(g, node, MANCH.individuals, [_enc_term(i) for i in expr[1]])
        return node
    if tag in ('Some', 'Only', 'DSome', 'DOnly'):
        _, prop_expr, filler = expr
        node = BNode()
        g.add((node, RDF.type, MANCH[_class_name(tag)]))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        # D-tags are restrictions on a data property: their filler is a data range, not a class.
        encode_filler = _encode_data_range if tag.startswith('D') else _encode_class_expr
        g.add((node, MANCH.filler, encode_filler(g, filler)))
        return node
    if tag == 'Value':
        _, prop_expr, value = expr
        node = BNode()
        g.add((node, RDF.type, MANCH.Value))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        g.add((node, MANCH.filler, _enc_term(value)))
        return node
    if tag == 'SelfR':
        _, prop_expr = expr
        node = BNode()
        g.add((node, RDF.type, MANCH.Self))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        return node
    if tag in ('Min', 'Max', 'Exact', 'DMin', 'DMax', 'DExact'):
        _, n, prop_expr, filler = expr
        node = BNode()
        g.add((node, RDF.type, MANCH[_class_name(tag)]))
        g.add((node, MANCH.onProperty, _encode_prop_expr(g, prop_expr)))
        g.add((node, MANCH.cardinality, lexical(n, XSD.nonNegativeInteger)))
        if filler is not None:
            encode_filler = _encode_data_range if tag.startswith('D') else _encode_class_expr
            g.add((node, MANCH.filler, encode_filler(g, filler)))
        return node
    raise ExecutionError(f'unhandled class-expression tag {tag!r}', kind="internal")


def _encode_data_range(g, dr):
    if isinstance(dr, URIRef):
        return dr
    tag = dr[0]
    if tag in ('DAnd', 'DOr'):
        node = BNode()
        g.add((node, RDF.type, MANCH[_class_name(tag)]))
        _write_seq(g, node, MANCH.operands, [_encode_data_range(g, e) for e in dr[1]])
        return node
    if tag == 'DNot':
        node = BNode()
        g.add((node, RDF.type, MANCH.DataNot))
        g.add((node, MANCH.operand, _encode_data_range(g, dr[1])))
        return node
    if tag == 'DOneOf':
        node = BNode()
        g.add((node, RDF.type, MANCH.DataOneOf))
        _write_seq(g, node, MANCH.literals, dr[1])
        return node
    if tag == 'DRestriction':
        _, datatype, facets = dr
        node = BNode()
        g.add((node, RDF.type, MANCH.DatatypeRestriction))
        g.add((node, MANCH.datatype, datatype))
        facet_nodes = []
        for facet_uri, lit in facets:
            fn = BNode()
            g.add((fn, RDF.type, MANCH.FacetRestriction))
            g.add((fn, MANCH.facet, facet_uri))
            g.add((fn, MANCH.restrictionValue, lit))
            facet_nodes.append(fn)
        _write_seq(g, node, MANCH.facets, facet_nodes)
        return node
    raise ExecutionError(f'unhandled data-range tag {dr[0]!r}', kind="internal")


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
    MANCH.ObjectPropertyDomainClause: 'class',
    MANCH.ObjectPropertyRangeClause: 'class',
    MANCH.ObjectPropertySubPropertyOfClause: 'prop',
    MANCH.ObjectPropertyEquivalentToClause: 'prop',
    MANCH.ObjectPropertyDisjointWithClause: 'prop',
    MANCH.ObjectPropertyInverseOfClause: 'prop',
    MANCH.ObjectPropertyCharacteristicsClause: 'characteristic',
    MANCH.ObjectPropertySubPropertyChainClause: 'prop_list',
    MANCH.DataPropertyDomainClause: 'class',
    MANCH.DataPropertyRangeClause: 'data',
    MANCH.DataPropertySubPropertyOfClause: 'prop',
    MANCH.DataPropertyEquivalentToClause: 'prop',
    MANCH.DataPropertyDisjointWithClause: 'prop',
    MANCH.DataPropertyCharacteristicsClause: 'characteristic',
    MANCH.AnnotationPropertyDomainClause: 'name',
    MANCH.AnnotationPropertyRangeClause: 'name',
    MANCH.AnnotationPropertySubPropertyOfClause: 'name',
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
        return _enc_term(value)
    raise ExecutionError(f'unhandled value kind {kind!r}', kind="internal")


def _encode_annotation(g, ann):
    """One manch:Annotation node; an annotation that is itself annotated carries manch:annotations."""
    prop, value = ann
    node = BNode()
    g.add((node, RDF.type, MANCH.Annotation))
    g.add((node, MANCH.annotationProperty, prop))
    g.add((node, MANCH.annotationTarget, _enc_term(value)))
    _encode_annotations(g, node, getattr(ann, 'nested', None))
    return node


def _encode_annotations(g, owner, anns):
    """The ordered ``manch:annotations`` of ``owner``; nothing is written for none."""
    if anns:
        _write_seq(g, owner, MANCH.annotations, [_encode_annotation(g, a) for a in anns])


def _encode_clause_item(g, kind, anns, value):
    node = BNode()
    g.add((node, RDF.type, MANCH.ClauseItem))
    if kind in ('class_list', 'prop_list'):
        # A single-axiom clause (DisjointUnionOf:, HasKey:, SubPropertyChain:): the one entry holds its members as ordered manch:values.
        inner_kind = 'class' if kind == 'class_list' else 'prop'
        _write_seq(g, node, MANCH.values, [_encode_value(g, inner_kind, v) for v in value])
    else:
        g.add((node, MANCH.value, _encode_value(g, kind, value)))
    _encode_annotations(g, node, anns)
    return node


def _encode_fact_item(g, anns, fact):
    negative, prop, value = fact
    node = BNode()
    g.add((node, RDF.type, MANCH.Fact))
    g.add((node, MANCH.negative, lexical(negative)))
    g.add((node, MANCH.property, prop))
    g.add((node, MANCH.value, _enc_term(value)))
    _encode_annotations(g, node, anns)
    return node


def _encode_clause_items(g, clause_class, frame_kind, clause_kind, items):
    if clause_kind == 'Annotations:':
        # Frame-level Annotations: - bare manch:Annotation items, no
        # ClauseItem wrapper, no per-item annotations slot.
        return [_encode_annotation(g, a) for a in items]
    if clause_kind == 'Facts:':
        return [_encode_fact_item(g, anns, fact) for anns, fact in items]
    value_kind = _CLAUSE_VALUE_KIND[clause_class]
    if value_kind in ('class_list', 'prop_list'):
        # Single-axiom clause: items is [(anns, [values...])].
        (anns, values), = items
        return [_encode_clause_item(g, value_kind, anns, values)]
    return [_encode_clause_item(g, value_kind, anns, value) for anns, value in items]


# ---------------------------------------------------------------------------
# Encode - manchester_to_tree() + a _Cursor subclass overriding the
# syntax-tree-capture hooks. The subclass is defined inside manchester_to_tree() itself,
# not at module scope, since its base class (_Cursor) is only available
# once starlayer.graph.manchester.parser is imported - deferred
# here for the circular-import reason this module's own docstring explains.
# ---------------------------------------------------------------------------

def _find_root(graph: Graph) -> BNode:
    """The ``manch:OntologyDocument`` node in ``graph`` - every graph this module
    produces (``manchester_to_tree()`` always builds a fresh ``Graph()``, never
    merges into a caller-supplied one) holds exactly one, so callers never
    need to track it separately themselves."""
    root = next(graph.subjects(RDF.type, MANCH.OntologyDocument), None)
    if root is None:
        raise ValueError('the graph holds no manch:OntologyDocument node, so there is no Manchester syntax tree in it')
    return root


def manchester_to_tree(text: str, base: str | None = None, tree_graph: Any = None) -> Any:
    """Parse Manchester Syntax text straight to its ``manch:``-encoded
    syntax tree.

    Reuses ``manchester_parser.py``'s own tokenizer, frame/clause dispatch,
    and expression/data-range grammar completely unchanged - only the
    (already no-op-by-default) syntax-tree-capture hooks are overridden. See this
    module's own docstring for the exact fidelity scope (matches the
    parser's existing internal AST, not raw text).

    Args:
        text: The Manchester Syntax document text to parse.
        base: Base IRI for resolving relative IRIs, if any.
        tree_graph: Write the tree into this graph instead of a fresh one - an ``StarLayerGraph`` (or ``StarLayerDataset`` / ``pyoxigraph.Store``)
            gets pyoxigraph terms and the ``manch:`` prefix. ``None`` (the default) builds a fresh ``StarLayerGraph``.

    Returns:
        ``tree_graph`` if given, otherwise a fresh ``StarLayerGraph``, holding exactly one ``manch:OntologyDocument`` tree.
    """
    if tree_graph is None:
        from starlayer.graph.core import StarLayerGraph

        tree_graph = StarLayerGraph()
    tree = _manchester_to_tree_graph(text, base)
    if _holds_document(tree_graph):
        raise ValueError("the graph already holds a manch:OntologyDocument: a graph holds one Manchester syntax tree, parse into a fresh graph")
    tree_graph.bind("manch", str(MANCH))
    tree_graph.bind("tree", "https://github.com/hidden-graph/starlayer/ns/tree#")
    tree_graph.extend(list(tree))  # triples only: no prefixes are copied
    return tree_graph


def _holds_document(graph: Any) -> bool:
    """True if ``graph`` (a ``StarLayerGraph``, ``StarLayerDataset`` or ``pyoxigraph.Store``) has a ``manch:OntologyDocument``."""
    from starlayer.graph.core import as_store
    from starlayer.graph.inputs import is_oxigraph_dataset, is_oxigraph_input

    if is_oxigraph_dataset(graph):
        return any(True for _ in as_store(graph).quads_for_pattern(
            None, RDF.type, MANCH.OntologyDocument, None))
    if is_oxigraph_input(graph):
        return next(iter(graph.subjects(RDF.type, MANCH.OntologyDocument)), None) is not None
    raise TypeError(f"expected a StarLayerGraph, StarLayerDataset or pyoxigraph Store, not {type(graph).__name__}")


def _manchester_to_tree_graph(text: str, base: str | None) -> Graph:
    from starlayer.graph.core import StarLayerGraph
    from starlayer.graph.manchester.parser import (
        _Cursor,
        _tokenize,
        run_guarded,
    )

    class _SyntaxTreeCursor(_Cursor):
        def __init__(self, tokens, base):
            super().__init__(tokens, base)
            self.syntax_tree_graph = StarLayerGraph()
            self.syntax_tree_graph.bind('manch', str(MANCH))
            self._prefix_nodes = []
            self._header_node = None
            self._frame_nodes = []
            self._misc_nodes = []
            self._current_frame_node = None
            self._current_frame_class = None
            self._current_frame_clause_nodes = None

        def record_prefix(self, prefix, iri):
            g = self.syntax_tree_graph
            node = BNode()
            g.add((node, RDF.type, MANCH.PrefixDeclaration))
            g.add((node, MANCH.prefixName, Literal(prefix, datatype=MANCH.PlainString)))
            g.add((node, MANCH.namespace, Literal(iri)))
            self._prefix_nodes.append(node)

        def record_ontology_header(self, iri, imports):
            g = self.syntax_tree_graph
            node = BNode()
            g.add((node, RDF.type, MANCH.OntologyHeader))
            if iri is not None:
                g.add((node, MANCH.ontologyIRI, iri))
            _write_seq(g, node, MANCH.imports, list(imports))
            self._header_node = node

        def record_ontology_extras(self, version_iri, annotations):
            g = self.syntax_tree_graph
            if version_iri is not None:
                g.add((self._header_node, MANCH.versionIRI, version_iri))
            _encode_annotations(g, self._header_node, annotations)

        def record_frame(self, kind, subject):
            g = self.syntax_tree_graph
            node = BNode()
            frame_class = _FRAME_CLASS[kind]
            g.add((node, RDF.type, frame_class))
            g.add((node, MANCH.subject, _enc_term(subject)))
            self._current_frame_node = node
            self._current_frame_class = frame_class
            self._current_frame_clause_nodes = []
            self._frame_nodes.append(node)

        def record_clause(self, frame_kind, clause_kind, items):
            g = self.syntax_tree_graph
            clause_class = _CLAUSE_CLASS[(frame_kind, clause_kind)]
            node = BNode()
            g.add((node, RDF.type, clause_class))
            item_nodes = _encode_clause_items(g, clause_class, frame_kind, clause_kind, items)
            _write_seq(g, node, MANCH.items, item_nodes)
            if clause_kind in _REVERSED_CLAUSE_KEYWORDS:
                g.add((node, MANCH.reversed, lexical(True)))
            self._current_frame_clause_nodes.append(node)

        def record_frame_end(self):
            g = self.syntax_tree_graph
            _write_seq(g, self._current_frame_node, MANCH.clauses, self._current_frame_clause_nodes)
            self._current_frame_node = None
            self._current_frame_clause_nodes = None

        def record_misc(self, keyword, items):
            g = self.syntax_tree_graph
            misc_class = _MISC_CLASS[keyword]
            node = BNode()
            g.add((node, RDF.type, misc_class))
            value_kind = _MISC_VALUE_KIND[misc_class]
            item_nodes = [_encode_value(g, value_kind, v) for v in items]
            _write_seq(g, node, MANCH.items, item_nodes)
            self._misc_nodes.append(node)

        def record_misc_annotations(self, annotations):
            g = self.syntax_tree_graph
            _encode_annotations(g, self._misc_nodes[-1], annotations)

    cur = _SyntaxTreeCursor(_tokenize(text), base)
    run_guarded(_run_top_level, cur)

    g = cur.syntax_tree_graph
    root = BNode()
    g.add((root, RDF.type, MANCH.OntologyDocument))
    _write_seq(g, root, MANCH.prefixes, cur._prefix_nodes)
    if cur._header_node is not None:
        g.add((root, MANCH.header, cur._header_node))
    _write_seq(g, root, MANCH.frames, cur._frame_nodes)
    _write_seq(g, root, MANCH.misc, cur._misc_nodes)
    return g


def _run_top_level(cur):
    """The parser's own top-level dispatch loop, driven by a recording cursor. Delegated, not copied:
    a second copy here once drifted from the parser (it kept ending silently on a stray token after the
    parser was fixed)."""
    from starlayer.graph.manchester.parser import (
        _run_top_level as _parser_run_top_level,
    )

    _parser_run_top_level(cur)


# ---------------------------------------------------------------------------
# Decode - real AST objects, mirroring manchester_parser.py's own tagged
# tuples for expressions/data ranges, plus lightweight namedtuples for the
# frame/clause half (which has no such tuple form in the parser itself).
# ---------------------------------------------------------------------------

Document = namedtuple('Document', ['prefixes', 'header', 'frames', 'misc'])
PrefixDecl = namedtuple('PrefixDecl', ['label', 'iri'])
OntologyHeader = namedtuple('OntologyHeader', ['iri', 'version', 'imports', 'annotations'])
Frame = namedtuple('Frame', ['kind', 'subject', 'clauses'])
Clause = namedtuple('Clause', ['clause_kind', 'items', 'annotations'], defaults=[None])
ClauseItem = namedtuple('ClauseItem', ['value', 'annotations'])
FactItem = namedtuple('FactItem', ['negative', 'property', 'value', 'annotations'])
AnnotationAssertion = namedtuple('AnnotationAssertion', ['property', 'value'])


def _decode_prop_expr(g, node):
    if not isinstance(node, BNode):
        return node
    if (node, RDF.type, MANCH.Inverse) in g:
        return ('Inverse', g.value(node, MANCH.operand))
    raise FormatError(f'unrecognized property-expression node {node!r}', kind='manchester', context='manch: tree')


def _node_types(g, node):
    return {o for _s, _p, o in g.triples((node, RDF.type, None))}


def _decode_class_expr(g, node):
    if not isinstance(node, BNode):
        return node
    types = _node_types(g, node)
    for tag in ('And', 'Or'):
        if MANCH[_class_name(tag)] in types:
            items = [_decode_class_expr(g, i) for i in _read_seq(g, node, MANCH.operands)]
            return (tag, items)
    if MANCH.Not in types:
        return ('Not', _decode_class_expr(g, g.value(node, MANCH.operand)))
    if MANCH.OneOf in types:
        return ('OneOf', [_dec_term(i) for i in _read_seq(g, node, MANCH.individuals)])
    for tag in ('Some', 'Only', 'DSome', 'DOnly'):
        if MANCH[_class_name(tag)] in types:
            prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
            decode_filler = _decode_data_range if tag.startswith('D') else _decode_class_expr
            return (tag, prop, decode_filler(g, g.value(node, MANCH.filler)))
    if MANCH.Value in types:
        prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
        value = _dec_term(g.value(node, MANCH.filler))
        return ('Value', prop, value)
    if MANCH.Self in types:
        return ('SelfR', _decode_prop_expr(g, g.value(node, MANCH.onProperty)))
    for tag in ('Min', 'Max', 'Exact', 'DMin', 'DMax', 'DExact'):
        if MANCH[_class_name(tag)] in types:
            prop = _decode_prop_expr(g, g.value(node, MANCH.onProperty))
            n = int(g.value(node, MANCH.cardinality).value)
            filler_node = g.value(node, MANCH.filler)
            decode_filler = _decode_data_range if tag.startswith('D') else _decode_class_expr
            return (tag, n, prop, decode_filler(g, filler_node) if filler_node is not None else None)
    raise FormatError(f'unrecognized class-expression node {node!r} (types: {types})', kind='manchester', context='manch: tree')


def _decode_data_range(g, node):
    if not isinstance(node, BNode):
        return node
    types = _node_types(g, node)
    for tag in ('DAnd', 'DOr'):
        if MANCH[_class_name(tag)] in types:
            items = [_decode_data_range(g, i) for i in _read_seq(g, node, MANCH.operands)]
            return (tag, items)
    if MANCH.DataNot in types:
        return ('DNot', _decode_data_range(g, g.value(node, MANCH.operand)))
    if MANCH.DataOneOf in types:
        return ('DOneOf', _read_seq(g, node, MANCH.literals))
    if MANCH.DatatypeRestriction in types:
        datatype = g.value(node, MANCH.datatype)
        facets = []
        for fn in _read_seq(g, node, MANCH.facets):
            facets.append((g.value(fn, MANCH.facet), g.value(fn, MANCH.restrictionValue)))
        return ('DRestriction', datatype, facets)
    raise FormatError(f'unrecognized data-range node {node!r} (types: {types})', kind='manchester', context='manch: tree')


def _decode_value(g, kind, node):
    if kind == 'class':
        return _decode_class_expr(g, node)
    if kind == 'prop':
        return _decode_prop_expr(g, node)
    if kind == 'data':
        return _decode_data_range(g, node)
    if kind in ('name', 'characteristic'):
        return _dec_term(node)
    raise ExecutionError(f'unhandled value kind {kind!r}', kind="internal")


class _Ann(tuple):
    """``(property, value)`` plus ``nested``: the annotations on this annotation, or None."""

    def __new__(cls, prop, value, nested=None):
        self = super().__new__(cls, (prop, value))
        self.nested = nested
        return self


def _decode_annotation(g, node):
    return _Ann(
        g.value(node, MANCH.annotationProperty),
        _dec_term(g.value(node, MANCH.annotationTarget)),
        _decode_annotations(g, node),
    )


def _decode_annotations(g, owner):
    """The annotations ``owner`` holds, in order, or None when it has none."""
    nodes = _read_seq(g, owner, MANCH.annotations)
    return [_decode_annotation(g, node) for node in nodes] if nodes else None


def _is_true(term):
    """A boolean literal's value (``bool(Literal)`` is True for any literal, ``"false"`` included)."""
    return term is not None and term.value in ('true', '1')


def _decode_clause(g, node):
    types = _node_types(g, node)
    clause_class = next(t for t in types if t in _CLAUSE_CLASS_TO_KIND)
    _frame_kind, clause_kind = _CLAUSE_CLASS_TO_KIND[clause_class]
    if _is_true(g.value(node, MANCH.reversed)):
        clause_kind = {'SubClassOf:': 'SuperClassOf:', 'SubPropertyOf:': 'SuperPropertyOf:'}[clause_kind]
    item_nodes = _read_seq(g, node, MANCH.items)

    if clause_kind == 'Annotations:':
        return Clause(clause_kind, [_decode_annotation(g, n) for n in item_nodes])

    if clause_kind == 'Facts:':
        items = []
        for n in item_nodes:
            negative = _is_true(g.value(n, MANCH.negative))
            prop = g.value(n, MANCH.property)
            value = _dec_term(g.value(n, MANCH.value))
            anns = _decode_annotations(g, n)
            items.append(FactItem(negative, prop, value, anns))
        return Clause(clause_kind, items)

    value_kind = _CLAUSE_VALUE_KIND[clause_class]
    if value_kind in ('class_list', 'prop_list'):
        (item_node,) = item_nodes
        inner_kind = 'class' if value_kind == 'class_list' else 'prop'
        values = [_decode_value(g, inner_kind, v) for v in _read_seq(g, item_node, MANCH.values)]
        anns = _decode_annotations(g, item_node)
        return Clause(clause_kind, [ClauseItem(values, anns)])

    items = []
    for n in item_nodes:
        value = _decode_value(g, value_kind, g.value(n, MANCH.value))
        anns = _decode_annotations(g, n)
        items.append(ClauseItem(value, anns))
    return Clause(clause_kind, items)


def _decode_frame(g, node):
    types = _node_types(g, node)
    frame_class = next(t for t in types if t in _FRAME_CLASS_TO_KIND)
    kind = _FRAME_CLASS_TO_KIND[frame_class]
    subject = _dec_term(g.value(node, MANCH.subject))
    clauses = [_decode_clause(g, n) for n in _read_seq(g, node, MANCH.clauses)]
    return Frame(kind, subject, clauses)


def _decode_misc(g, node):
    types = _node_types(g, node)
    misc_class = next(t for t in types if t in _MISC_CLASS_TO_KEYWORD)
    keyword = _MISC_CLASS_TO_KEYWORD[misc_class]
    value_kind = _MISC_VALUE_KIND[misc_class]
    items = [_decode_value(g, value_kind, n) for n in _read_seq(g, node, MANCH.items)]
    return Clause(keyword, items, _decode_annotations(g, node))


def _tree_to_document(graph: Graph, root) -> Document:
    """Decode a ``manch:``-shaped RDF graph back into a real ``Document``
    object. ``root`` must be the ``manch:OntologyDocument`` node, as returned by
    ``manchester_to_tree``."""
    prefixes = [PrefixDecl(graph.value(n, MANCH.prefixName).value, graph.value(n, MANCH.namespace).value)
                for n in _read_seq(graph, root, MANCH.prefixes)]
    header_node = graph.value(root, MANCH.header)
    header = None
    if header_node is not None:
        iri = graph.value(header_node, MANCH.ontologyIRI)
        version = graph.value(header_node, MANCH.versionIRI)
        imports = _read_seq(graph, header_node, MANCH.imports)
        annotations = _decode_annotations(graph, header_node)
        header = OntologyHeader(iri, version, imports, annotations)
    frames = [_decode_frame(graph, n) for n in _read_seq(graph, root, MANCH.frames)]
    misc = [_decode_misc(graph, n) for n in _read_seq(graph, root, MANCH.misc)]
    return Document(prefixes, header, frames, misc)


# ---------------------------------------------------------------------------
# Document -> Manchester Syntax text (from-scratch serializer - the literal
# inverse of manchester_parser.py's own tuple vocabulary, not adapted from
# starlayer.graph.manchester.serializer - see this module's own docstring)
# ---------------------------------------------------------------------------

def _render_name(node) -> str:
    if isinstance(node, BNode):
        return f'_:{node.value}'
    return f'<{node.value}>'


def _render_literal(lit: Literal) -> str:
    # The note's quotedString escapes exactly two characters: the double quote and the backslash.
    text = lit.value.replace('\\', '\\\\').replace('"', '\\"')
    if lit.language:
        return f'"{text}"@{lit.language}'
    if lit.datatype and lit.datatype != XSD.string:  # a plain literal is xsd:string in RDF 1.1 / 1.2
        return f'"{text}"^^<{lit.datatype.value}>'
    return f'"{text}"'


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
    if tag in ('Some', 'Only', 'DSome', 'DOnly'):
        _, prop, filler = expr
        kw = 'some' if tag in ('Some', 'DSome') else 'only'
        render_filler = _render_data_range if tag.startswith('D') else _render_class_expr
        inner = f'{_render_prop_expr(prop)} {kw} {render_filler(filler, top=False)}'
        return _paren(inner, not top)
    if tag == 'Value':
        _, prop, value = expr
        return _paren(f'{_render_prop_expr(prop)} value {_render_value(value)}', not top)
    if tag == 'SelfR':
        _, prop = expr
        return _paren(f'{_render_prop_expr(prop)} Self', not top)
    if tag in ('Min', 'Max', 'Exact', 'DMin', 'DMax', 'DExact'):
        _, n, prop, filler = expr
        kw = {'Min': 'min', 'Max': 'max', 'Exact': 'exactly'}[tag.removeprefix('D')]
        inner = f'{_render_prop_expr(prop)} {kw} {n}'
        if filler is not None:
            render_filler = _render_data_range if tag.startswith('D') else _render_class_expr
            inner += f' {render_filler(filler, top=False)}'
        return _paren(inner, not top)
    raise ExecutionError(f'unhandled class-expression tag {tag!r}', kind="internal")


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
        _, data_facets_inv = _inverse_characteristic_maps()
        facet_strs = [f'{data_facets_inv[facet_uri]} {_render_value(lit)}' for facet_uri, lit in facets]
        return f'{_render_name(datatype)}[' + ', '.join(facet_strs) + ']'
    raise ExecutionError(f'unhandled data-range tag {tag!r}', kind="internal")


def _render_annotation_list(anns) -> str:
    """``prop value, prop value`` - an annotation that is itself annotated is preceded by its own
    ``Annotations: ...`` (the note's ``annotationAnnotatedList``)."""
    parts = []
    for ann in anns:
        prop, value = ann
        nested = getattr(ann, 'nested', None)
        parts.append(f'{_render_annotations_prefix(nested)}{_render_name(prop)} {_render_value(value)}')
    return ', '.join(parts)


def _render_annotations_prefix(anns) -> str:
    if not anns:
        return ''
    return f'Annotations: {_render_annotation_list(anns)} '


def _render_one(clause_class, value) -> str:
    """Render a single clause item's own value, dispatching on what kind of
    grammar this clause's items hold - class expression, property
    expression, data range, or a bare name/URIRef/Literal needing no
    further rendering. Takes the resolved clause *class* directly (not a
    bare clause_kind string) - several clause keywords (Domain:/Range:/
    EquivalentTo:/DisjointWith:/Annotations:/SubPropertyOf:) are shared
    across multiple frame kinds mapping to genuinely different classes
    (e.g. ObjectPropertyRangeClause's items are a ClassExpression, but
    DataPropertyRangeClause's are a DataRange) - resolving from the keyword
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
        characteristics_inv, _ = _inverse_characteristic_maps()
        return characteristics_inv[value]
    return _render_value(value) if isinstance(value, Literal) else _render_name(value)


def _render_clause(clause: Clause, frame_kind: str) -> str:
    kind = clause.clause_kind
    if kind == 'Annotations:':
        return f'Annotations: {_render_annotation_list(clause.items)}'
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
    return f'{clause.clause_kind} {_render_annotations_prefix(clause.annotations)}{rendered}'


_FRAME_KEYWORD = {
    'Class': 'Class:', 'ObjectProperty': 'ObjectProperty:', 'DataProperty': 'DataProperty:',
    'AnnotationProperty': 'AnnotationProperty:', 'Individual': 'Individual:', 'Datatype': 'Datatype:',
}


def _render_frame(frame: Frame) -> str:
    lines = [f'{_FRAME_KEYWORD[frame.kind]} {_render_name(frame.subject)}']
    for clause in frame.clauses:
        lines.append('    ' + _render_clause(clause, frame.kind))
    return '\n'.join(lines)


def _document_to_text(document: Document) -> str:
    """Render a ``Document`` (as returned by ``_tree_to_document``) back to
    real Manchester Syntax text."""
    lines = []
    for p in document.prefixes:
        label = p.label if p.label else ''
        lines.append(f'Prefix: {label}: <{p.iri}>')
    if document.header is not None:
        h = document.header
        header_line = 'Ontology:' if h.iri is None else f'Ontology: <{h.iri.value}>'
        if h.version is not None:
            header_line += f' <{h.version.value}>'
        lines.append(header_line)
        for imp in h.imports:
            lines.append(f'Import: {_render_name(imp)}')
        if h.annotations:
            lines.append(_render_annotations_prefix(h.annotations).rstrip())
    if lines:
        lines.append('')
    for frame in document.frames:
        lines.append(_render_frame(frame))
        lines.append('')
    for misc in document.misc:
        lines.append(_render_misc(misc))
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def tree_to_manchester(tree_graph: Graph) -> str:
    """Thin wrapper composing ``_tree_to_document`` + ``_document_to_text``
    for a caller who just wants text back. ``tree_graph`` may be an ``StarLayerGraph`` (read as a snapshot)."""
    graph = _as_graph(tree_graph)
    root = _find_root(graph)
    try:
        return _document_to_text(_tree_to_document(graph, root))
    except RecursionError:
        raise ExecutionError('class expression nested too deeply to render', kind='nesting', context='Manchester syntax render') from None


def tree_to_owl(tree_graph: Any) -> Any:
    """The tree's compiled OWL triples, as an ``StarLayerGraph`` -
    renders the tree to Manchester text via ``tree_to_manchester()``,
    then compiles that text the same way any other caller would:
    ``StarLayerGraph.parse(format='manchester')`` (which is itself backed
    by ``manchester_parser.parse_manchester()``, the real, trusted OWL
    compiler) - rather than reaching past that public entry point to call
    the lower-level parser function directly.

    Going through text here is not a fidelity-losing shortcut:
    ``tree_to_manchester()`` is a fully faithful renderer of everything this
    module's ``manch:`` encoding captures, so nothing this tree holds is
    lost before the OWL compiler sees it - see this module's own docstring.

    Args:
        tree_graph: A ``manch:`` syntax tree, e.g. from ``manchester_to_tree()``.

    Returns:
        The compiled OWL content as a fresh ``StarLayerGraph``.
    """
    from starlayer.graph.core import StarLayerGraph

    owl_graph = StarLayerGraph()
    owl_graph.parse(data=tree_to_manchester(tree_graph), format='manchester')
    return owl_graph


def _as_graph(graph: Any) -> Any:
    """A ``StarLayerGraph`` for any graph a caller may pass (a dataset gives its default graph; an rdflib graph is a ``TypeError``)."""
    from starlayer.graph.inputs import as_oxigraph

    graph = as_oxigraph(graph)
    return graph.to_graph() if hasattr(graph, "to_graph") else graph


def _vocabulary_snapshot() -> Any:
    """The ``manch:`` OWL vocabulary, as the ``StarLayerGraph`` ``get_ontology_graph`` returns."""
    return get_ontology_graph("manchester_owl")


def _concrete_classes() -> frozenset:
    """The ``manch:`` classes that have no subclass: the only types a tree node may be *asserted* with
    (abstract ones such as ``manch:Frame`` exist to dispatch shapes, and are inferred)."""
    onto = _vocabulary_snapshot()
    classes = {
        c for c in set(onto.subjects(RDF.type, RDFS.Class)) | set(onto.subjects(RDF.type, OWL.Class))
        | set(onto.subjects(RDFS.subClassOf)) | set(onto.objects(None, RDFS.subClassOf))
        if isinstance(c, URIRef) and c in MANCH
    }
    with_subclasses = {
        o for s_, o in onto.subject_objects(RDFS.subClassOf) if s_ != o and isinstance(o, URIRef)
    }
    return frozenset(classes - with_subclasses)


def _preflight(data_graph: Graph) -> list[tuple]:
    """Structural problems visible only in the *asserted* graph, as ``(focus_node, message)`` pairs.

    ``validate_manchester_tree`` runs SHACL with RDFS inference, and several ``manch:`` properties declare an
    ``rdfs:domain`` - so a node whose ``rdf:type`` was deleted gets a type inferred back from its
    properties and looks fine to every shape, while the decoder, which reads the asserted types, cannot
    handle it. This check looks before inference does:

    - exactly one ``manch:OntologyDocument``;
    - every node that has a ``manch:`` property is asserted with a concrete ``manch:`` type;
    - every asserted ``manch:`` type is a class of the vocabulary;
    - every node with a ``tree:value`` is asserted as a ``tree:Item`` (the same domain inference would hide it).

    (There was a third check, that no ``rdf:List`` loops back on itself, because the engine raised on a cyclic list before any shape
    ran. Ordered children are ``tree:ord`` ordinals now, so a loop in a sequence cannot be written; ties, missing or non-integer
    ordinals and a blank child under two parents are findings of the shared ``tree:`` shapes.)
    """
    concrete = _concrete_classes()
    known = _known_classes()
    problems: list[tuple] = []

    documents = list(data_graph.subjects(RDF.type, MANCH.OntologyDocument))
    if len(documents) != 1:
        problems.append((documents[0] if documents else None,
                         f"expected exactly one manch:OntologyDocument, found {len(documents)}"))

    # A tree:Item that lost its rdf:type would get it back from the domain of tree:value, and the decoder (which reads asserted types)
    # would then take the wrapper for the member itself.
    from starlayer.graph import ordinals

    for wrapper in {s_ for s_ in data_graph.subjects(ordinals.VALUE, None)}:
        if (wrapper, RDF.type, ordinals.ITEM) not in data_graph:
            problems.append((wrapper, "node has tree:value but is not asserted as a tree:Item"))

    has_manch_property: dict = {}
    for s_, p_, o_ in data_graph:
        if isinstance(p_, URIRef) and p_ in MANCH and p_ != MANCH.negative:
            has_manch_property.setdefault(s_, set()).add(p_)
        if p_ == RDF.type and isinstance(o_, URIRef) and o_ in MANCH and o_ not in known:
            problems.append((s_, f"{o_.value} is not a class of the manch: vocabulary"))
    for node, props in has_manch_property.items():
        if not (set(data_graph.objects(node, RDF.type)) & concrete):
            names = ", ".join(sorted(p_.value.rsplit("#", 1)[-1] for p_ in props))
            problems.append((node, f"node has manch:{names} but no asserted concrete manch: type"))
    return problems


def _known_classes() -> frozenset:
    onto = _vocabulary_snapshot()
    return frozenset(
        c for c in set(onto.subjects(RDF.type, RDFS.Class)) | set(onto.subjects(RDF.type, OWL.Class))
        | set(onto.subjects(RDFS.subClassOf)) | set(onto.objects(None, RDFS.subClassOf))
        if isinstance(c, URIRef) and c in MANCH
    )


def _combined(manchester_name: str, tree_name: str) -> Any:
    """A fresh graph of a ``manch:`` file with the shared ``tree:`` one added (the shapes ``owl:imports`` the tree shapes; the ordinals'
    classes are in the tree ontology)."""
    from starlayer.sparql.expr_validation import _merge_into

    graph = get_ontology_graph(manchester_name)
    _merge_into(graph, get_ontology_graph(tree_name))
    return graph


def _shapes_graph() -> Any:
    return _combined("manchester_shacl", "tree_shacl")


def _ontology_graph() -> Any:
    return _combined("manchester_owl", "tree_owl")


def validate_manchester_tree(tree_graph: Any) -> ValidationReport:
    """Validate ``tree_graph`` against the shapes in
    ``manchester_shapes.ttl``. Which shapes to check against is this
    module's own, fixed concern, not a parameter.

    Runs with RDFS reasoning enabled (``ont_graph=get_ontology_graph(
    "manchester_owl")``, ``inference=ENTAILMENT.RDFS``) - this is what lets the
    dispatch shapes (``ClassExpressionShape``/``PropertyExpressionShape``/
    ``DataRangeShape``/``FrameShape``/``ClauseShape``/``MiscAxiomShape``) be
    a single ``sh:class`` check against an abstract superclass instead of
    enumerating every concrete tag by name, the same reasoning ``salg:``'s
    own shapes use for SPARQL.

    No public ``ontology_graph()``/``shapes_graph()`` here - get those
    two graphs directly from ``starontology`` instead:
    ``get_ontology_graph("manchester_owl")`` /
    ``get_ontology_graph("manchester_shacl")``. This function needs no
    combining logic the way ``starlayer.sparql.validate_sparql_tree()`` does for
    ``srl:``+``salg:``, so there was nothing worth wrapping here even
    privately.

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` -
    this validates a caller-supplied ``tree_graph`` that may be genuine
    RDF 1.2 content, which only ``starlayer.shacl`` understands correctly.

    Before SHACL runs, a pre-flight check looks at the graph as asserted (see ``_preflight``): inference
    would otherwise repair a missing ``rdf:type`` from a property's ``rdfs:domain`` and hide a tree the
    decoder cannot read. Its findings are merged into the returned report.

    Args:
        tree_graph: The ``manch:`` syntax tree to validate - e.g. straight
            out of ``manchester_to_tree()``, or an LLM-authored
            ``manch:`` graph not yet decoded.

    Returns:
        The ``ValidationReport`` ``starlayer.shacl.validate()`` gives, with the pre-flight findings merged into its
        graph and text; it is not iterable, so read ``conforms``, ``report_text`` and the rest by name.
    """

    # lazy imports: avoid a circular-import deadlock at module load time
    from starlayer.graph.entailment.infer import ENTAILMENT
    from starlayer.shacl._adapter import validate_bounded
    from starlayer.shacl.results import ValidationReport

    problems = _preflight(_as_graph(tree_graph))

    result = validate_bounded(
        tree_graph,
        _shapes_graph(),
        ont_graph=_ontology_graph(),
        inference=ENTAILMENT.RDFS,
        max_validation_depth=100,
    )
    if not problems:
        return result

    return ValidationReport(
        False,
        _preflight_report(problems, result.report_graph),
        _preflight_text(problems, "" if result.conforms else result.report_text),
        data_graph=result.data_graph,
        diagnostics=result.diagnostics,
    )


_SH = "http://www.w3.org/ns/shacl#"


def _preflight_report(problems, report_graph):
    """``report_graph`` (or a fresh one) with the pre-flight findings added as sh:ValidationResult."""
    sh = Vocab(_SH)
    if report_graph is None:
        from starlayer.graph.core import StarLayerGraph

        report_graph = StarLayerGraph()
        report_graph.add((BNode(), RDF.type, sh.ValidationReport))
    report_node = report_graph.value(None, RDF.type, sh.ValidationReport)
    for focus, message in problems:
        res = BNode()
        report_graph.add((res, RDF.type, sh.ValidationResult))
        report_graph.add((res, sh.resultSeverity, sh.Violation))
        report_graph.add((res, sh.resultMessage, Literal(message)))
        if focus is not None:
            report_graph.add((res, sh.focusNode, focus))
        if report_node is not None:
            report_graph.add((report_node, sh.result, res))
    if report_node is not None:
        report_graph.remove((report_node, sh.conforms, None))
        report_graph.add((report_node, sh.conforms, lexical(False)))
    return report_graph


def _show(node):
    return node.value if isinstance(node, (URIRef, BNode)) else str(node)


def _preflight_text(problems, shacl_text):
    lines = "\n".join(f"  - {m}" + (f" (node {_show(f)})" if f is not None else "") for f, m in problems)
    text = (
        "Validation Report\nConforms: False\n\n"
        f"Pre-flight problems (asserted graph, checked before inference):\n{lines}\n"
    )
    return text + ("\n" + shacl_text if shacl_text else "")
