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

- **Ordered children are ``tree:ord`` ordinals, not ``rdf:List``** (2026-11-25, ``graph/ordinals.py``, shapes in ``starontology/tree/``): a
  parent holds each child under the property and the child carries ``tree:ord n``; a blank node child carries it itself and has one
  parent, a variable, IRI or literal child (and a named node shared by several queries) sits in a ``tree:Item`` with ``tree:value``.
  The ordered properties are ``ORDERED_PROPERTIES`` below. An empty sequence is no triple. A nested sequence is a node of its own:
  a UNION alternative is a ``sqe:GroupGraphPattern`` holding its elements in ``sqe:where``, a VALUES row is a ``sqe:Row`` holding its
  terms in ``sqe:cells``.
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
  separately**, under ``sqe:``'s own ``sqe:base``/``sqe:prefixDecl``/
  ``sqe:PrefixDecl``/``sqe:prefixLabel``/``sqe:namespace`` terms.
  ``prefixLabel``'s own bare-string value is tagged with ``spexpr:PlainString`` (``vocab.PY_STR_DATATYPE``).
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

Added with the StarLayer-owned parser (``parse_sparql.py``), additively:
``DESCRIBE`` (``sqe:DescribeQuery``, ``sqe:describe``/``sqe:describeAll``),
``FROM``/``FROM NAMED`` (``sqe:dataset`` -> ``sqe:DatasetClause`` with
``sqe:source``/``sqe:named``), ``SERVICE [SILENT]`` (``sqe:Service``,
``sqe:service``, ``sqe:silent``), ``VERSION`` (``sqe:version``), and solution
modifiers on ``ASK``/``CONSTRUCT``/``DESCRIBE`` (the 1.2 grammar allows them).
Trees of queries that use none of these are unchanged.

Update (``parse_sparql.parse_sparql_update``), additively: ``sqe:UpdateRequest`` (``sqe:operations``, the ordered
``sqe:InsertData``/``DeleteData``/``DeleteWhere`` (``sqe:quads``: ``sqe:TriplePattern`` and ``sqe:QuadGraph`` in written
order), ``sqe:Modify`` (``sqe:with``, ``sqe:delete``, ``sqe:insert``, ``sqe:using``, ``sqe:where``), ``sqe:Load``
(``sqe:loadFrom``, ``sqe:into``), ``sqe:Clear``/``Drop``/``Create`` (``sqe:target``), ``sqe:Add``/``Move``/``Copy``
(``sqe:from``, ``sqe:to``), ``sqe:silent``; graph references ``sqe:GraphRef`` (``sqe:graphIri``), ``sqe:DefaultGraph``,
``sqe:NamedGraphs``, ``sqe:AllGraphs``). Each operation carries the prologue written in front of it.

**Running a tree:** run the text from ``sqe_tree_to_text`` with ``StarLayerGraph.query()`` / ``update()``. Anything the tree
cannot represent raises ``NotImplementedError`` instead of being silently dropped. ``sqe_parse_to_tree`` reads queries and
updates with the StarLayer-owned parser.
"""

from __future__ import annotations

from ..vocab import (  # noqa: F401 - reused as-is, not re-minted
    PY_STR_DATATYPE,
    SPEXPR,
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
DESCRIBE_QUERY = SQE.DescribeQuery  # added with the owned parser: DESCRIBE (targets or *), optional WHERE

PROJECTION = SQE.projection  # SelectQuery only - ordered: variables (in a tree:Item) and sqe:Alias nodes
TEMPLATE = SQE.template  # ConstructQuery only - ordered TriplePattern nodes
WHERE = SQE.where  # the flat, ordered pattern elements of a group (tree:ord on each child)

# Solution modifiers (SELECT/CONSTRUCT roots; ASK has none)
SELECT_ALL = SQE.selectAll  # SELECT * - boolean true; replaces sqe:projection
DISTINCT = SQE.distinct  # boolean true on a SelectQuery
REDUCED = SQE.reduced  # boolean true on a SelectQuery
ORDER_BY = SQE.orderBy  # ordered sqe:OrderCondition nodes
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

EXISTS = SQE.Exists  # EXISTS { ... } inside an expression - .where
NOT_EXISTS = SQE.NotExists  # NOT EXISTS { ... } inside an expression - .where
ALIAS = SQE.Alias  # (expr AS ?var) in a projection or GROUP BY - .expr, .var
GROUP_BY = SQE.groupBy  # ordered: variables, expressions and sqe:Alias nodes
HAVING = SQE.having  # ordered expressions
SUB_SELECT = SQE.SubSelect  # a nested SELECT in a pattern list - same properties as sqe:SelectQuery
VALUES = SQE.Values  # VALUES block - .vars (ordered variables), .rows (ordered sqe:Row nodes)
VALUES_VARS = SQE.vars
VALUES_ROWS = SQE.rows
VALUES_ROW = SQE.Row  # one row of a VALUES block: .cells, the terms of the row in order
ROW_CELLS = SQE.cells
VALUES_UNDEF = SQE.undef  # the UNDEF marker: a cell value of a VALUES row
QUERY_VALUES = SQE.values  # a query's trailing VALUES clause -> sqe:Values
MINUS = SQE.Minus  # MINUS { ... } - .where
GRAPH_PATTERN = SQE.Graph  # GRAPH ?g { ... } - .graph, .where
GRAPH_TERM = SQE.graph

# --- Added with the StarLayer-owned parser (parse_sparql.py): additive, existing trees are unchanged ------------
DESCRIBE = SQE.describe  # DescribeQuery: ordered IRIs / variables
DESCRIBE_ALL = SQE.describeAll  # DescribeQuery: boolean true for DESCRIBE *
DATASET = SQE.dataset  # any query form: ordered sqe:DatasetClause nodes, in source order (FROM / FROM NAMED)
DATASET_CLAUSE = SQE.DatasetClause  # .source the graph IRI, optional .named true for FROM NAMED
DATASET_SOURCE = SQE.source
DATASET_NAMED = SQE.named
SERVICE = SQE.Service  # SERVICE [SILENT] <iri>|?v { ... } - .service the endpoint, optional .silent true, .where
SERVICE_TERM = SQE.service
SERVICE_SILENT = SQE.silent
VERSION = SQE.version  # a VERSION "x" declaration on the query root (a plain string; may repeat)

TRIPLE_TERM = SQE.TripleTerm  # <<( s p o )>> - .subject/.predicate/.object, recursively

UNION = SQE.Union  # .alternatives -> ordered sqe:GroupGraphPattern nodes, one per alternative
UNION_ALTERNATIVES = SQE.alternatives
GROUP_GRAPH_PATTERN = SQE.GroupGraphPattern  # one alternative of a UNION: its pattern elements are .where

EXPR = SQE.expr  # the salg:-boundary property shared by Filter/Bind

# Prologue terms: the query's own PREFIX / BASE declarations, kept so the text can be written with the author's prefixes.
# prefixLabel's bare-string value is tagged PY_STR_DATATYPE (spexpr:PlainString, imported above).
PROLOGUE_BASE = SQE.base
PROLOGUE_PREFIX = SQE.prefixDecl
PREFIX_DECL = SQE.PrefixDecl
PREFIX_LABEL = SQE.prefixLabel
PREFIX_NAMESPACE = SQE.namespace

# --- SPARQL Update (parse_sparql.parse_sparql_update): additive; no query tree changes ------------------------
UPDATE_REQUEST = SQE.UpdateRequest  # root of an update request: .operations, plus any trailing prologue
UPDATE_OPERATION = SQE.UpdateOperation  # superclass of the operation classes below
OPERATIONS = SQE.operations  # ordered operations, in source order (the ';'-separated sequence)
INSERT_DATA = SQE.InsertData  # INSERT DATA { quads }
DELETE_DATA = SQE.DeleteData  # DELETE DATA { quads }
DELETE_WHERE = SQE.DeleteWhere  # DELETE WHERE { quads }
MODIFY = SQE.Modify  # [WITH iri] [DELETE {..}] [INSERT {..}] [USING ..]* WHERE {..}
LOAD = SQE.Load  # LOAD [SILENT] <iri> [INTO GRAPH <iri>]
CLEAR = SQE.Clear
DROP = SQE.Drop
CREATE = SQE.Create
ADD = SQE.Add
MOVE = SQE.Move
COPY = SQE.Copy
QUADS = SQE.quads  # ordered sqe:TriplePattern (default graph) and sqe:QuadGraph nodes, in written order
QUAD_GRAPH = SQE.QuadGraph  # GRAPH <iri>|?v { triples } inside a quad list
QUAD_GRAPH_NAME = SQE.graphName
QUAD_TRIPLES = SQE.triples  # ordered sqe:TriplePattern nodes (none for an empty block)
MODIFY_WITH = SQE["with"]  # the WITH graph IRI of a Modify
MODIFY_DELETE = SQE.delete  # ordered quads (a DELETE template); none for an empty one
MODIFY_INSERT = SQE.insert  # ordered quads (an INSERT template); none for an empty one
MODIFY_USING = SQE.using  # ordered sqe:DatasetClause nodes (USING / USING NAMED)
LOAD_FROM = SQE.loadFrom  # the IRI a LOAD reads
LOAD_INTO = SQE.into  # the sqe:GraphRef a LOAD writes to (absent: the default graph)
GRAPH_TARGET = SQE.target  # CLEAR / DROP / CREATE: a graph reference
UPDATE_FROM = SQE["from"]  # ADD / MOVE / COPY source
UPDATE_TO = SQE.to  # ADD / MOVE / COPY destination
GRAPH_REF = SQE.GraphRef  # GRAPH <iri>: .graphIri
GRAPH_REF_IRI = SQE.graphIri
DEFAULT_GRAPH = SQE.DefaultGraph  # DEFAULT
NAMED_GRAPHS = SQE.NamedGraphs  # NAMED (every named graph)
ALL_GRAPHS = SQE.AllGraphs  # ALL
# SILENT reuses SERVICE_SILENT (sqe:silent), NAMED in USING NAMED reuses DATASET_NAMED

# Every property whose children are ordered (a ``tree:ord`` ordinal on each child, see ``graph/ordinals.py``): the ``sqe:`` ones and the
# ``spexpr:`` operand / argument ones. Everything else holds one value.
ORDERED_PROPERTIES = frozenset(
    {
        WHERE, UNION_ALTERNATIVES, PROJECTION, TEMPLATE, DESCRIBE, DATASET, GROUP_BY, HAVING, ORDER_BY, VALUES_VARS, VALUES_ROWS, ROW_CELLS,
        OPERATIONS, QUADS, QUAD_TRIPLES, MODIFY_DELETE, MODIFY_INSERT, MODIFY_USING,
        SPEXPR.args, SPEXPR.other, SPEXPR.op,
    }
)  # fmt: skip
