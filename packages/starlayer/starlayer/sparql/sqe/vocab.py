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
- **Variables reuse ``spexpr:Variable`` directly**, not a separately-minted
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
  separately**, under ``sqe:``'s own ``sqe:base``/``sqe:prologuePrefix``/
  ``sqe:PrefixBinding``/``sqe:prefixLabel``/``sqe:namespace`` terms
  (2026-10-14 - previously reused ``salg:``'s identically-shaped terms
  verbatim; moved to a real, independent ``sqe:`` duplicate instead,
  since an ``sqe:`` graph's own encoder/decoder - ``to_rdf.py``'s
  ``_encode_raw_prologue``/``to_text.py``'s ``_prefix_map`` - never
  actually called ``salg:``'s own ``_encode_prologue``/decode logic in
  the first place; they're two independently-maintained implementations
  that merely *happened* to target the same predicate names, not a real
  shared dependency - so duplicating cost nothing). ``prefixLabel``'s own
  bare-string value is tagged with ``spexpr:PlainString`` (reused directly
  from ``vocab.PY_STR_DATATYPE``, not a separate ``sqe:PyStr`` - that
  independent copy existed only because the datatype was ``salg:``-owned
  at the time; renamed and moved to ``spexpr:`` 2026-10-15, so there's no
  longer a reason to duplicate it - see ``vocab.py``'s own comment on
  ``PY_STR_DATATYPE`` for why).
  This is for direct, prefix-aware rendering (see
  ``to_text.py``) and for the UI's own display purposes - **not** for
  execution, which never needs prefixes at all once every term is already
  a resolved `URIRef`, and **not** via ``translateAlgebra``, which never
  reads ``query.prologue`` in the first place (a documented rdflib
  limitation - see ``to_text.py``'s own module docstring).
- **Expressions use the shared `spexpr:` vocabulary** (``sqe:Filter``/
  ``sqe:Bind``/``sqe:Alias``/``sqe:OrderCondition`` hold their expression in
  ``sqe:expr``), the same boundary ``ssyn:``/``srl:`` use. Expressions are
  inherently tree-shaped even in the surface syntax (``?age > 18``), so
  there is no flattening benefit to chase. An sqe tree contains **no
  ``salg:`` terms at all** (checked across the W3C corpus by the opt-in test
  set): the pieces sqe needs that are not plain expressions are sqe-native
  (``sqe:TripleTerm``, ``sqe:Exists`` with its own where-list) or sit in
  ``spexpr:`` (aggregates, the SPARQL 1.2 builtins, the direction-string
  datatype). ``salg`` may use sqe's vocabulary; sqe never uses salg's.
- **Text is rendered from the tree** by ``expr_text.py`` and ``to_text.py``,
  not through rdflib's ``translateAlgebra``.

**Coverage** (verified against the W3C SPARQL 1.2 query fixtures and a
per-feature suite, both run on a StarLayerGraph/Dataset - see
``tests/sparql/sqe_coverage``): ``SELECT`` (``*``, ``DISTINCT``/``REDUCED``,
projected ``(expr AS ?v)``), ``ASK``, ``CONSTRUCT`` (including ``CONSTRUCT
WHERE``); triple patterns, property paths, ``OPTIONAL``, ``UNION``,
``MINUS``, ``GRAPH``, ``FILTER`` (including ``EXISTS``/``NOT EXISTS``),
``BIND``, ``VALUES`` (inline and trailing), sub-selects; aggregates with
``GROUP BY``/``HAVING``; ``ORDER BY``/``LIMIT``/``OFFSET``; every expression
builtin; and the SPARQL 1.2 additions (triple terms, reified triples and
annotations, base-direction strings and their functions). Reified-triple and
annotation shorthand is stored in its expanded form (a ``rdf:reifies`` triple
plus ordinary triples), so it renders back expanded.

**Not covered:** ``DESCRIBE`` and SPARQL Update. Anything the tree cannot
represent raises ``NotImplementedError`` instead of being silently dropped.
Six W3C fixtures do not round-trip, none because of sqe: three are rejected by
the project's own parser (``!!``, codepoint escapes) and three are suite
errors (a triple term as a subject).

**Running a decoded 1.2 query:** a ``Query`` from ``sqe_tree_to_query`` for a
query that uses SPARQL 1.2 syntax cannot be executed directly by starlayer (a
prepared 1.2 ``Query`` never can); run the text from ``sqe_tree_to_text``.
"""

from __future__ import annotations

from ..vocab import (  # noqa: F401 - reused as-is, not re-minted
    PY_STR_DATATYPE,
    SQE,
    VARIABLE_DATATYPE,
)

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

# Solution modifiers (SELECT/CONSTRUCT roots; ASK has none)
SELECT_ALL = SQE.selectAll  # SELECT * - boolean true; replaces sqe:projection
DISTINCT = SQE.distinct  # boolean true on a SelectQuery
REDUCED = SQE.reduced  # boolean true on a SelectQuery
ORDER_BY = SQE.orderBy  # flat rdf:List of sqe:OrderCondition nodes
ORDER_CONDITION = SQE.OrderCondition  # .expr -> expression/variable, optional .descending
ORDER_DESCENDING = SQE.descending  # boolean true for DESC(...)
LIMIT = SQE.limit  # xsd:integer
OFFSET = SQE.offset  # xsd:integer

TRIPLE_PATTERN = SQE.TriplePattern
TRIPLE_PATTERN_SUBJECT = SQE.subject
TRIPLE_PATTERN_PREDICATE = SQE.predicate
TRIPLE_PATTERN_OBJECT = SQE.object

OPTIONAL = SQE.Optional  # .where -> nested flat list

FILTER = SQE.Filter  # .expr -> salg: expression (fallback boundary)
BIND = SQE.Bind  # .expr -> salg: expression (fallback boundary), .var
BIND_VAR = SQE.var

EXISTS = SQE.Exists  # EXISTS { ... } / NOT EXISTS { ... } inside an expression - .where, .negated
NEGATED = SQE.negated  # boolean true on a NOT EXISTS
ALIAS = SQE.Alias  # (expr AS ?var) in a projection or GROUP BY - .expr, .var
GROUP_BY = SQE.groupBy  # rdf:List of variables / expressions / sqe:Alias
HAVING = SQE.having  # rdf:List of expressions
SUB_SELECT = SQE.SubSelect  # a nested SELECT in a pattern list - same properties as sqe:SelectQuery
VALUES = SQE.Values  # VALUES block - .vars list, .rows list of lists
VALUES_VARS = SQE.vars
VALUES_ROWS = SQE.rows
VALUES_UNDEF = SQE.undef  # the UNDEF marker inside a VALUES row
QUERY_VALUES = SQE.values  # a query's trailing VALUES clause -> sqe:Values
MINUS = SQE.Minus  # MINUS { ... } - .where
GRAPH_PATTERN = SQE.Graph  # GRAPH ?g { ... } - .graph, .where
GRAPH_TERM = SQE.graph

TRIPLE_TERM = SQE.TripleTerm  # <<( s p o )>> - .subject/.predicate/.object, recursively

UNION = SQE.Union  # .alternatives -> rdf:List of nested flat lists
UNION_ALTERNATIVES = SQE.alternatives

EXPR = SQE.expr  # the salg:-boundary property shared by Filter/Bind

# Prologue predicates - a real sqe:-native duplicate of SALG's own
# identically-shaped base/prologuePrefix/PrefixBinding/prefixLabel/
# namespace terms (2026-10-14), not a reuse - see this module's own
# docstring for why duplicating was free (to_rdf.py's _encode_raw_prologue/
# to_text.py's _prefix_map never called salg:'s own _encode_prologue to
# begin with). prefixLabel's own bare-string datatype tag is PY_STR_DATATYPE
# (spexpr:PlainString, imported above) - no separate sqe:PyStr/PlainString
# of its own; that duplicate datatype was removed 2026-10-15 once the
# datatype's canonical home moved off of salg: (see vocab.py).
PROLOGUE_BASE = SQE.base
PROLOGUE_PREFIX = SQE.prologuePrefix
PREFIX_BINDING = SQE.PrefixBinding
PREFIX_LABEL = SQE.prefixLabel
PREFIX_NAMESPACE = SQE.namespace
