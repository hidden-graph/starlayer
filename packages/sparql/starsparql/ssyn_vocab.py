"""The RDF vocabulary for the *readable* syntax-level SPARQL representation
— no more verbose than the SPARQL text itself, built by simplifying the raw
parse tree (``sast:``/``parseQuery()`` output) using rdflib's own real
simplification functions (``algebra.simplifyFilters``, ``algebra
.translatePath``, ``algebra.triples``, ``algebra.translatePName``) — never a
second, hand-rolled text parser. See ``to_ssyn_rdf.py``'s module docstring
for exactly which real rdflib functions do the work.

Design differs from both existing layers on purpose:

- Unlike ``salg:`` (the algebra), a ``WHERE`` clause here is a flat,
  *ordered* list of sibling elements (triple patterns, ``ssyn:Optional``,
  ``ssyn:Filter``, ``ssyn:Bind``, ``ssyn:Union``) in original textual
  order — mirroring ``GroupGraphPatternSub.part``'s own shape in the raw
  parse tree, which is already exactly this, and is *less* nested than the
  algebra's ``LeftJoin``/``Filter`` wrapping (which restructures scope, not
  just relabels it). This is why the projection is built from ``sast:``
  (the parse tree) rather than from ``salg:`` (the algebra) — the flat
  shape is a genuine, mechanical feature of the grammar, not something we
  additionally invent.
- Unlike ``sast:`` (the raw parse tree), path/expression precedence chains
  are pre-collapsed (``algebra.translatePath``/``algebra.simplifyFilters``)
  and prefixed names are pre-resolved to real IRIs
  (``algebra.translatePName``) before encoding — all three reused directly
  from rdflib, not reimplemented.
- Expression trees (``ssyn:Filter``/``ssyn:Bind``'s ``ssyn:expr``) and
  non-trivial property paths (a ``ssyn:TriplePattern``'s ``ssyn:predicate``,
  when it's a real path, not a plain IRI) fall back to the *existing*,
  already-shaped ``salg:`` vocabulary — same boundary principle the earlier
  ``ssyn:`` prototype established: a property points at ``ssyn:`` or
  ``salg:`` depending on how deep this layer models a given position, with
  no new code needed at the boundary (``to_rdf._encode``/``from_rdf
  ._decode``/``to_rdf._encode_path``/``from_rdf._decode_path`` reused
  as-is). Expression names are already close to spec syntax
  (``RelationalExpression``, ``Builtin_STRSTARTS``) and already have full
  SHACL shape coverage, so there is little to gain by re-modeling them here
  too.
"""

from __future__ import annotations

from rdflib import Namespace

from .vocab import VARIABLE_DATATYPE  # noqa: F401 - reused as-is, not re-minted, see below

SSYN = Namespace("https://github.com/hidden-graph/starsparql/ns/readable-syntax#")

# RDF/Turtle has no native "SPARQL variable" term, so one is tagged via
# reserved datatype — but unlike every other name in this file, reused
# directly from vocab.py (salg:Variable) rather than minted as ssyn:Variable.
# Tried minting a separate one first; it made the *same* SPARQL variable
# decode to two unequal RDF terms (Literal equality includes datatype)
# depending on whether it was written by this layer's own encoder or by the
# salg: expression fallback (to_rdf._encode) — breaking exactly the thing a
# shared variable identity is for: matching "the same ?x" across the
# ssyn:/salg: boundary, e.g. a WHERE-clause variable also referenced inside
# a FILTER's salg:-encoded expression. See ast_vocab.py's own comment for
# the fuller version of this reasoning (found there first).

SELECT_QUERY = SSYN.SelectQuery
SELECT = SSYN.select  # projected-variables list (rdf:List)
WHERE = SSYN.where  # flat, ordered rdf:List of pattern elements

TRIPLE_PATTERN = SSYN.TriplePattern
TRIPLE_PATTERN_SUBJECT = SSYN.subject
TRIPLE_PATTERN_PREDICATE = SSYN.predicate
TRIPLE_PATTERN_OBJECT = SSYN.object

OPTIONAL = SSYN.Optional  # .where -> nested flat list

FILTER = SSYN.Filter  # .expr -> salg: expression (fallback boundary)
BIND = SSYN.Bind  # .expr -> salg: expression (fallback boundary), .var
BIND_VAR = SSYN.var

UNION = SSYN.Union  # .alternatives -> rdf:List of nested flat lists
UNION_ALTERNATIVES = SSYN.alternatives

EXPR = SSYN.expr  # the salg:-boundary property shared by Filter/Bind
