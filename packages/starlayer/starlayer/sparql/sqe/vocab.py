"""The RDF vocabulary for ``sqe:`` — a human-readable, editable SPARQL
query tree meant to be paired with its own SHACL shapes to drive a UI
editor (see ``shapes.py``), not a general-purpose query-as-RDF encoding.

Built from the *raw parse tree* (``rdflib.plugins.sparql.parser
.parseQuery()``'s output, before ``translateQuery`` runs), the same input
``ssyn:``/``sast:`` already take — not from ``salg:`` (the algebra).
``translateQuery`` is exactly the step that turns a flat
``WHERE { a OPTIONAL { b } }`` into a nested ``LeftJoin(BGP(a), BGP(b))``
operator tree and resolves prefixed names away — the normalization that
makes algebra correct to execute is precisely what makes it a bad
substrate to hand-edit. Skipping it keeps the parse tree's own already-flat
``WHERE``-clause shape intact.

Design choices, each reusing an existing, already-proven convention rather
than inventing a new one:

- **Flat, ordered ``WHERE``-clause list** (``sqe:where``), not nested
  operators — mirrors the raw parse tree's own
  ``GroupGraphPatternSub.part`` shape directly, the same technique
  ``ssyn:`` already established (see ``to_ssyn_rdf.py``'s module
  docstring). A ``TriplesBlock`` sibling splices in one node per real
  triple (via ``algebra.triples``' own grouping), not one BGP-shaped
  wrapper, for the same "no more verbose than the text" reason.
- **Variables reuse ``salg:Variable`` directly**, not a separately-minted
  ``sqe:Variable`` — confirmed this is also what ``srl:`` already does
  (encodes `Variable` terms by delegating straight to ``to_rdf._encode``).
  Minting a second reserved datatype for the same concept would make the
  *same* SPARQL variable decode to two unequal RDF terms (`Literal`
  equality includes datatype) depending on whether it was written by this
  layer's own encoder or by the ``salg:`` expression fallback below —
  breaking shared variable identity across that boundary (e.g. a
  ``WHERE``-clause variable also referenced inside a ``FILTER``'s
  ``salg:``-encoded expression). Same reasoning ``ssyn_vocab.py``/
  ``ast_vocab.py`` already recorded for this exact choice.
- **Predicates/terms are real, resolved `URIRef`s** (via
  ``algebra.translatePName``, reused directly in ``to_rdf.py``) — a
  real IRI can always be re-abbreviated by any Turtle/display layer with
  its own prefix map, so this isn't a readability loss.
- **The query's own original `PREFIX`/`BASE` declarations are preserved
  separately**, reusing ``to_rdf.py``'s own existing ``salg:base``/
  ``salg:prologuePrefix`` convention verbatim (``_encode_prologue``) rather
  than minting ``sqe:`` duplicates for the same concept - a query's
  prologue means the same thing regardless of which projection vocabulary
  is describing it. This is for direct, prefix-aware rendering (see
  ``to_text.py``) and for the UI's own display purposes - **not** for
  execution, which never needs prefixes at all once every term is already
  a resolved `URIRef`, and **not** via ``translateAlgebra``, which never
  reads ``query.prologue`` in the first place (a documented rdflib
  limitation - see ``to_text.py``'s own module docstring).
- **Expressions reuse the existing `salg:` expression vocabulary as-is**
  (``sqe:Filter``/``sqe:Bind``'s ``sqe:expr`` falls back to `salg:
  Expression`) — the same boundary choice ``ssyn:``/``srl:`` already
  made. Expressions are inherently tree-shaped even in the surface syntax
  (``?age > 18``), so there's no flattening benefit to chase here, and
  `salg:`'s expression coverage (~63 builtins, generated from
  ``expr_families.py``) is already complete and tested.

**Deliberate v1 scope reduction, not an oversight** (mirroring
``srl_grammar.py``'s own documented precedent for the same discipline):
covers `SELECT`/`ASK`/`CONSTRUCT` only (no `DESCRIBE`); `WHERE`-clause
elements limited to triple patterns, `OPTIONAL`, `UNION`, `FILTER`,
`BIND` (property paths in predicate position, e.g. `foaf:knows+`, *are*
covered — inherited for free from reusing `to_ssyn_rdf.py`'s own
`translatePath`/`to_rdf._encode_path` technique, confirmed via direct
testing, not just assumed from the code it was copied from). Explicitly
**not yet** covered: aggregates/`GROUP BY`/`HAVING`, subqueries, `VALUES`,
and SPARQL Update entirely — see `packages/starlayer/docs/future_enhancements.md`
for the plan to widen this deliberately, later.
"""

from __future__ import annotations

from rdflib import Namespace

from ..vocab import SALG, VARIABLE_DATATYPE  # noqa: F401 - reused as-is, not re-minted

SQE = Namespace("https://github.com/hidden-graph/starsparql/ns/query-edit#")

# Root query-form types, each also typed sqe:Query (see salg:Query's own
# identical convention) so a store holding many encoded queries can find
# them all via a single `?q a sqe:Query` pattern regardless of form.
# AskQuery has no projection; ConstructQuery adds a template (the
# CONSTRUCT {} pattern, same flat-triple-list shape as `where`).
QUERY = SQE.Query
SELECT_QUERY = SQE.SelectQuery
ASK_QUERY = SQE.AskQuery
CONSTRUCT_QUERY = SQE.ConstructQuery

PROJECTION = SQE.projection  # SelectQuery only - rdf:List of sqe:Variable-tagged Literals
TEMPLATE = SQE.template  # ConstructQuery only - flat rdf:List of TriplePattern nodes
WHERE = SQE.where  # flat, ordered rdf:List of pattern elements

TRIPLE_PATTERN = SQE.TriplePattern
TRIPLE_PATTERN_SUBJECT = SQE.subject
TRIPLE_PATTERN_PREDICATE = SQE.predicate
TRIPLE_PATTERN_OBJECT = SQE.object

OPTIONAL = SQE.Optional  # .where -> nested flat list

FILTER = SQE.Filter  # .expr -> salg: expression (fallback boundary)
BIND = SQE.Bind  # .expr -> salg: expression (fallback boundary), .var
BIND_VAR = SQE.var

UNION = SQE.Union  # .alternatives -> rdf:List of nested flat lists
UNION_ALTERNATIVES = SQE.alternatives

EXPR = SQE.expr  # the salg:-boundary property shared by Filter/Bind

# Prologue predicates are *not* re-minted here - reused verbatim from
# vocab.py (SALG.base / SALG.prologuePrefix / SALG.PrefixBinding /
# SALG.prefixLabel / SALG.namespace), via to_rdf._encode_prologue. See this
# module's own docstring for why.
