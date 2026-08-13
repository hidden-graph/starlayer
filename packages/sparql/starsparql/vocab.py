"""The RDF vocabulary this project encodes SPARQL algebra into.

Design: rdflib's own SPARQL algebra (``rdflib.plugins.sparql.algebra``) is
already a tree of ``CompValue``/``Expr`` nodes — each just an
``OrderedDict`` with a ``name`` (e.g. ``"BGP"``, ``"Filter"``, ``"LeftJoin"``,
``"RelationalExpression"``) and a handful of typed keys (``p``, ``p1``,
``expr``, ``var`` ...). That shape maps onto RDF almost mechanically:

- ``node.name``            -> ``rdf:type SALG[node.name]``
- each ``key: value`` pair -> ``SALG[key]`` predicate, value encoded
  recursively (nested node -> nested resource, list -> ``rdf:List``,
  RDF term -> itself)

There is deliberately **one** encoder/decoder pair for every operator and
every expression function (``to_rdf.py`` / ``from_rdf.py``) rather than one
function per operator name — the vocabulary is a direct, mechanical mirror
of whatever CompValue names rdflib itself uses, so it never needs to be
extended by hand when rdflib adds a new algebra operator or builtin.

Two shapes need a convention beyond that generic rule:

- **Triple patterns.** ``BGP.triples`` is a plain list of ``(s, p, o)``
  Python tuples, not ``CompValue`` nodes. Each is encoded as a
  ``salg:TriplePattern`` resource with ``salg:subject``/``salg:predicate``/
  ``salg:object``. This deliberately reuses the same three predicate names
  as a SPARQL 1.2 triple *term*'s component triples (below) — a triple
  *pattern* and a triple *term* are structurally the same thing (three term
  slots), just used in a pattern vs. a value position.

- **Triple terms (SPARQL 1.2).** A ``<<( s p o )>>``/``TRIPLE(s, p, o)``
  triple term is ``starsparql.triple_term.TripleTermNode`` at the
  algebra layer — a ``CompValue`` subclass (name ``"TripleTerm"``, keys
  ``subject``/``predicate``/``object``) built directly by this project's own
  grammar extension (``grammar12.py``, which splices new pyparsing
  productions into rdflib's real ``GraphTerm``/``VarOrTerm``/``GraphNode``/
  ``GraphNodePath`` grammar rules in place, rather than depending on any
  text-rewrite/lowering pipeline). Because it *is* a ``CompValue``, the
  generic node encoder (``to_rdf._encode``) needs zero special-casing for
  it — same ``rdf:type salg:TripleTerm`` + ``salg:subject``/``predicate``/
  ``object`` shape as any other CompValue, and the same predicate names as
  ``TriplePattern`` above, since they're structurally identical. Decoding is
  the one place this needs a real special case (``from_rdf._decode_comp_value``,
  keyed on ``name == "TripleTerm"``): a plain reconstructed ``CompValue``
  would be unhashable and crash ``algebra.reorderTriples``/``_knownTerms``
  when ``rdf_to_query`` recomputes ``_vars``/``analyse`` bookkeeping after
  decoding (see ``TripleTermNode``'s own docstring for the full empirical
  finding — a non-``CompValue`` hashable proxy isn't sufficient either, since
  rdflib's variable-discovery walk only recurses into ``CompValue``/
  ``list``/``tuple``/``ParseResults``, nothing else, so a variable nested
  inside a pattern-with-variables triple term would otherwise be silently
  invisible to ``_addVars``).

- **Variables.** A SPARQL ``Variable`` is not a native RDF term. It is
  encoded as ``Literal(name, datatype=SALG.Variable)`` — a plain literal
  tagged with a reserved datatype, the same trick starlayergraph itself
  uses for ``DirLangString`` base-direction literals and content-addressed
  triple-term URIs (``starlayergraph.model.encoding``, ``starlayergraph.model.dirlangstring``).
  This keeps a variable a first-class RDF term (usable directly as a
  ``salg:subject``/``PV`` member/etc.) without inventing a blank-node
  indirection for something that is, in the end, just a name.

- **Property paths.** A path expression (`?s :knows+ ?o`, `?s (:a|:b)/^:c ?o`,
  ...) sits in a triple pattern's predicate slot as an
  ``rdflib.paths.Path`` instance (``InvPath``, ``SequencePath``,
  ``AlternativePath``, ``MulPath``, ``NegatedPath``) once the query reaches
  the algebra layer — not a ``CompValue``, so it isn't covered by the
  generic rule either. Each gets its own ``salg:`` class mirroring its
  constructor arguments 1:1 (``salg:InvPath salg:arg``,
  ``salg:SequencePath``/``salg:AlternativePath salg:args`` as an
  ``rdf:List``, ``salg:MulPath salg:path salg:mod`` — ``mod`` a plain
  ``"*"``/``"+"``/``"?"`` literal — ``salg:NegatedPath salg:args`` as an
  ``rdf:List``), following the same "mirror the real rdflib shape" rule as
  everything else in this vocabulary, just applied to a Python class
  hierarchy instead of a CompValue name.

- **Binding rows.** A ``VALUES`` clause's algebra (``Values.res``) is a
  ``List[Dict[Variable, term]]`` — one dict per row, every row-variable
  present as a key in every row (rdflib represents ``UNDEF`` as the bare
  *string* ``"UNDEF"``, not Python ``None`` — see "Bare Python strings"
  below for why that matters). A raw Python ``dict`` has no term-shaped
  encoding, so each row is encoded as an ``rdf:List`` of ``salg:Binding``
  nodes (``salg:var``/``salg:val``, ``salg:val`` omitted for ``UNDEF``)
  rather than reusing the generic ``CompValue`` encoding (there is no
  CompValue here to mirror — this is the one node shape in the vocabulary
  that doesn't correspond to an rdflib CompValue name).

- **Bare Python strings.** Not every value living inside an algebra tree is
  RDF data — some are rdflib's own internal bookkeeping: an operator symbol
  (``RelationalExpression.op``, e.g. ``"="``), a modifier keyword
  (``OrderCondition.order``: ``"ASC"``/``"DESC"``), or a SPARQL grammar
  keyword token that a bare ``pyparsing.Keyword`` match yields as plain text
  rather than as a real term (``VALUES``' ``"UNDEF"``, Update's
  ``GraphRefAll``: ``"DEFAULT"``/``"NAMED"``/``"ALL"``, ``SILENT``). These
  are always genuine Python ``str`` instances in the live algebra tree,
  never ``rdflib.Literal`` — confirmed directly: ``rdflib.Literal("=") ==
  "="`` is **False** and the two hash differently, so a plain-Literal
  round-trip of one of these would silently produce a value that fails
  every comparison/dict-lookup rdflib's own evaluator makes against the
  literal string it expects, without raising anywhere. Rather than track
  down and enumerate every key name this can happen under (an open-ended,
  easy-to-miss list), every bare Python ``str`` value (``type(v) is str``,
  which a real RDF term or a ``Variable`` never is by the time it reaches
  the encoder) is tagged with the reserved datatype ``SALG.PyStr`` and
  decoded back to a bare ``str`` — universally, by value shape, not by key
  name, so a future rdflib grammar keyword this project hasn't been taught
  about yet still round-trips correctly. A handful of keys additionally
  need ``int``/``bool`` recovered as genuine Python types rather than left
  as an ``rdflib.Literal`` (``Slice.start``/``.length`` are passed straight
  to ``itertools.islice``, which requires real ``int``; a boolean
  ``Literal`` is always truthy in a plain Python ``if``, since it's a
  non-empty string either way) — those few are still enumerated by name
  (``from_rdf._PLAIN_VALUE_KEYS``), since unlike ``str`` there is no
  equality/hash surprise for ``int``/``bool`` to detect generically.

- **Prologue (BASE/PREFIX).** A query or update's ``Prologue`` (the
  ``BASE``/``PREFIX`` declarations from the source text) is not part of the
  algebra tree at all — it's a sibling object (``query.prologue`` /
  ``update.prologue``) holding a base IRI and a prefix->namespace map. It's
  attached directly to the encoded query/update's root node: ``salg:base``
  (the base IRI, if any) and one ``salg:prologuePrefix`` triple per binding,
  each pointing to a ``salg:PrefixBinding`` node with ``salg:prefixLabel``
  (the bare prefix string, e.g. ``"foaf"``, ``""`` for the default ``:``
  prefix — encoded via the bare-Python-string convention above) and
  ``salg:namespace`` (the bound URIRef). Order doesn't matter for prefix
  bindings (unlike triples/PV/etc.), so this is plain repeated triples, not
  an ``rdf:List``.

  This is round-tripped for a real reason, not cosmetic completeness:
  confirmed empirically that ``BASE``-relative IRI resolution at *evaluation*
  time (the ``IRI()``/``URI()`` builtins, via ``ctx.prologue.absolutize()``)
  silently produces a different, wrong, unresolved result when the
  reconstructed ``Query`` carries an empty ``Prologue`` instead of the
  original ``base``. It does *not*, however, change what
  ``rdflib.plugins.sparql.algebra.translateAlgebra`` prints — confirmed
  separately that its output is byte-identical regardless of prologue
  content, since ``_AlgebraTranslator`` never reads ``query.prologue`` at
  all and calls bare ``.n3()`` (no namespace manager) throughout. That's a
  real limitation in rdflib itself, not something round-tripping the
  prologue can work around — so don't expect prefixed names to reappear in
  regenerated query text even after this.

- **Update quads-by-graph maps.** A SPARQL Update operation's ``quads``
  field (``InsertData``/``DeleteData``/``DeleteWhere`` directly;
  ``Modify.delete``/``Modify.insert`` nested one level) is a
  ``Dict[graph-term, List[triple]]`` — a different shape from a VALUES row
  (keyed by graph term, not ``Variable``; for ``Modify`` the key can itself
  *be* a ``Variable``, e.g. ``DELETE { GRAPH ?g {...} }``, so key type alone
  can't distinguish the two shapes the way it might seem to). Handled by
  name, not generically: wherever a CompValue has a key literally named
  ``"quads"``, it is encoded as an ``rdf:List`` of ``salg:QuadsForGraph``
  nodes (``salg:graph``, ``salg:triples`` as an ``rdf:List`` of
  ``salg:TriplePattern`` — reusing the triple-pattern encoding above)
  instead of going through the generic dict-as-binding-row path.
"""

from __future__ import annotations

from rdflib import Namespace, URIRef

SALG = Namespace("https://github.com/hidden-graph/starsparql/ns/algebra#")

# Reserved datatype URI *namespace* used to encode a SPARQL 1.2 dirLangString
# literal ("text"@lang--dir) as a plain rdflib.Literal - rdflib.Literal(text,
# lang="en--rtl") raises outright (rdflib's own langtag validator has no
# notion of the RDF 1.2 "--dir" suffix). Same trick starlayergraph itself
# uses (starlayergraph.model.encoding.encode_dirlang_datatype) - pack (language,
# direction) into a synthetic datatype URI, its local name exactly the real
# "lang--dir" lexical suffix (RDF 1.2 Concepts sec 3.4), so decoding is a
# plain string split - but under *this project's own* namespace, not
# starlayergraph's, and deliberately so: this project's encoded queries need to
# be storable in any graph implementation, including a real StarLayerGraph -
# and StarLayerGraph.value()/.triples() unconditionally decodes any literal
# using *its own* dirlang: datatype back into a real DirLangString object,
# which this project's from_rdf.py decoder has no branch for (confirmed via
# a real crash: a query containing a dirLangString VALUES-row value,
# round-tripped through a StarLayerGraph-backed salg: encoding, came back as
# a DirLangString instead of a Literal). Reusing starlayergraph's own encoding
# functions directly, as this project used to, meant a StarLayerGraph always
# recognized the result as "mine" and silently restored it - exactly the
# failure mode ground triple terms already avoid via their own structural
# (non-native) salg: encoding. This gives dirLangString literals the same
# protection: a StarLayerGraph never recognizes this namespace as its own,
# so the literal stays an inert term in the salg: representation.
DIRLANG_NS = SALG["dirlang/"]


def encode_dirlang_datatype(language: str, direction: str) -> URIRef:
    """This project's own internal datatype URIRef encoding of
    (language, direction) - see DIRLANG_NS above for why this isn't
    starlayergraph's own encode_dirlang_datatype, despite doing the same thing
    the same way."""
    return URIRef(f"{DIRLANG_NS}{language}--{direction}")


def decode_dirlang_datatype(datatype) -> tuple[str, str] | None:
    """Return (language, direction) if datatype is this project's own
    dirlang encoding (see DIRLANG_NS above). None for any other datatype -
    including starlayergraph's own dirlang: encoding, or plain rdf:langString."""
    s = str(datatype)
    if not s.startswith(DIRLANG_NS):
        return None
    suffix = s[len(DIRLANG_NS):]
    language, sep, direction = suffix.rpartition("--")
    if not sep:
        return None
    return language, direction

# Reserved datatype URI used to encode a SPARQL Variable as an RDF Literal.
# See the module docstring's "Variables" section above.
VARIABLE_DATATYPE = SALG.Variable

# Reserved datatype URI used to encode a bare Python str (not an RDF term)
# found inside an algebra tree. See the module docstring's "Bare Python
# strings" section above.
PY_STR_DATATYPE = SALG.PyStr

# Class used for the (s, p, o) triple-pattern-tuple encoding described above.
TRIPLE_PATTERN = SALG.TriplePattern
TRIPLE_PATTERN_SUBJECT = SALG.subject
TRIPLE_PATTERN_PREDICATE = SALG.predicate
TRIPLE_PATTERN_OBJECT = SALG.object

# CompValue name used by starsparql.triple_term.TripleTermNode — see
# the module docstring's "Triple terms (SPARQL 1.2)" section above. Reuses
# TRIPLE_PATTERN_SUBJECT/PREDICATE/OBJECT above for its own subject/
# predicate/object, since the two shapes are structurally identical.
TRIPLE_TERM = SALG.TripleTerm

# Root marker: the resource holding the query's algebra tree is typed
# salg:Query in addition to its own CompValue name (SelectQuery/AskQuery/
# ConstructQuery/DescribeQuery), so a store holding many encoded queries can
# find them all with a single `?q a salg:Query` pattern regardless of query
# form. Also where salg:base/salg:prologuePrefix live for a query — see the
# "Prologue" section above.
QUERY = SALG.Query

# Root marker for a whole encoded Update *request* (see to_rdf.update_to_rdf)
# — a dedicated container node (not itself a CompValue) holding
# salg:operations (an rdf:List of the request's operations, in execution
# order) plus the request's shared salg:base/salg:prologuePrefix (SPARQL
# Update has one Prologue per request, not one per operation).
UPDATE = SALG.Update

# Per-operation marker, added alongside each operation's own CompValue name
# (InsertData/DeleteData/DeleteWhere/Modify/Load/Clear/Drop/Create/Add/Move/
# Copy) so a store can find every encoded update *operation* via
# `?op a salg:UpdateOperation` regardless of which one it is — the
# operation-level analogue of QUERY/UPDATE above.
UPDATE_OPERATION = SALG.UpdateOperation

# Root marker for a whole encoded *collection* of independent queries (see
# to_rdf.queries_to_collection) — a dedicated container node (not itself a
# CompValue, exactly like UPDATE above) holding salg:queries (an rdf:List of
# the collection's member salg:Query roots, in whatever order the caller
# supplied them — order isn't semantically meaningful for a collection the
# way it is for salg:operations, but is still preserved since rdf:List is
# ordered anyway). Already declared in salg-ontology.ttl; this is the first
# code that actually produces/consumes it.
QUERY_COLLECTION = SALG.QueryCollection
