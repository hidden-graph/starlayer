# starsparql

Translate SPARQL 1.2 queries into and out of an RDF representation of their
algebra, so a query can be stored, versioned, annotated, and queried about at
the same granularity as any other RDF data — and eventually, so a query can
be *produced* as structured RDF (e.g. by an LLM) rather than as an opaque
string.

Uses [starlayergraph](https://github.com/hidden-graph/starlayergraph) as
a reference/dependency for RDF 1.2 (triple-term/reification) support.

## Design

rdflib's own SPARQL algebra (`rdflib.plugins.sparql.algebra`) is already a
tree of `CompValue`/`Expr` nodes — each just a named dict (`name` +
typed keys, e.g. `BGP(triples=...)`, `Filter(expr=..., p=...)`,
`LeftJoin(p1=..., p2=..., expr=...)`). That shape maps onto RDF almost
mechanically:

- `node.name` -> `rdf:type salg:<name>`
- each `key: value` -> `salg:<key>` predicate, value encoded recursively
  (nested node -> nested resource, list -> `rdf:List`, RDF term -> itself)

See `starsparql/vocab.py` for the full encoding rules, including the
handful of shapes that need their own convention beyond the generic rule:
triple patterns, SPARQL variables, property paths (`rdflib.paths.Path` —
not a CompValue), `VALUES`-row bindings, bare-Python-string bookkeeping
values (grammar keyword tokens like `UNDEF`/`DEFAULT`/`SILENT` that rdflib
represents as plain `str`, never as a real RDF term), and Update's
quads-by-graph maps.

This is deliberately **one generic recursive encoder/decoder**
(`to_rdf.py` / `from_rdf.py`), not one function per algebra operator — it
mirrors whatever operator/expression names rdflib's own grammar and algebra
module actually define, including by *introspecting* rdflib's live parser
grammar at import time to rebuild the expression-name -> eval-function table
(see `from_rdf._discover_expr_evalfns`), rather than hand-transcribing it.
That means it doesn't need to be extended by hand when rdflib adds a new
algebra operator or expression builtin. In practice this made most of
Phase 2 (CONSTRUCT/ASK/DESCRIBE, MINUS, SERVICE, aggregates/GROUP BY/HAVING,
ORDER BY/LIMIT, subqueries) work correctly with zero new code — the only
things that actually needed dedicated handling were shapes that aren't
CompValue nodes at all (property paths) or aren't uniquely identifiable by
shape alone (VALUES rows, Update's quads maps, bare-str bookkeeping values).

## Status: Phase 1 + Phase 2 complete

Round-tripped at the **algebra layer** (post `translateQuery`/
`translateUpdate`, i.e. semantically canonical — prefixes resolved to full
IRIs, `OPTIONAL` already a `LeftJoin`, etc.), verified by *executing* both
the original and the round-tripped query/update and comparing results —
not by comparing regenerated query text, since text form isn't stable
(rdflib's own `algebra.translateAlgebra` always emits full IRIs, never
prefixed names, and has at least one known pre-existing bug of its own,
unrelated to this project: it drops a `FILTER` nested inside `OPTIONAL`).

Covered: `SELECT`/`ASK`/`CONSTRUCT`/`DESCRIBE`, `BGP`, `FILTER`, `OPTIONAL`,
`UNION`, `MINUS`, `SERVICE` (structural round-trip only — not executed in
tests, since that would require a live network call), property paths (all
five `rdflib.paths.Path` forms), aggregates/`GROUP BY`/`HAVING`,
`ORDER BY`/`LIMIT`/`OFFSET`, subqueries, `VALUES` (including `UNDEF`), and
SPARQL Update (`INSERT`/`DELETE DATA`, `DELETE WHERE`, `Modify`
DELETE/INSERT/WHERE, `LOAD`/`CLEAR`/`DROP`/`CREATE`/`ADD`/`MOVE`/`COPY`,
graph-qualified forms).

## Status: Phase 3 — RDF 1.2 (finding, not new code)

An RDF 1.2 SPARQL 1.2 query prepared via starlayergraph's own
`starlayergraph.query.sparql_api.prepareQuery` **already round-trips through
Phase 1/2 unchanged** — triple-term patterns (`<<( s p o )>>`,
`rdf:reifies`, `SUBJECT`/`PREDICATE`/`OBJECT`, `isTRIPLE`) and
base-direction literal functions (`LANGDIR`/`hasLANGDIR`/`STRLANGDIR`) all
compile down, at the algebra layer, to plain `Extend`/`Function`/`BGP`/
`Join` — the same shapes Phase 1/2 already cover — because starlayergraph
rewrites SPARQL 1.2 syntax to its internal SPARQL-1.1-compatible encoding
*before* calling rdflib's real `translateQuery`. See
`tests/test_phase3_rdf12.py`.

A more ambitious alternative was tried and doesn't work: encoding the
*surface* `<<( )>>` syntax directly as a `salg:TripleTerm` node in the
algebra, instead of starlayergraph's lowered encoding, so the RDF representation
of a query would read as `<<( ?s :p ?o )>>` rather than a
content-addressed-hash BIND. This requires feeding starlayergraph's
`parseQuery()` (which restores `TripleTerm` CompValue nodes, but only in
the pre-algebra parse tree) into rdflib's own `algebra.translateQuery()` —
which crashes (`TypeError: cannot use 'CompValue' as a set element`):
rdflib's algebra translator assumes every triple-pattern term is a hashable
RDF identifier, not an arbitrary CompValue. This is a real limitation in
rdflib's own algebra machinery, not an oversight in starlayergraph — it's
exactly why starlayergraph lowers to SPARQL 1.1 before calling `translateQuery`
at all. Patching rdflib itself to lift that assumption is out of scope.

## Status: Phase 4 — Prologue (BASE/PREFIX) round-trip

`query.prologue`/`update.prologue` (the `BASE`/`PREFIX` declarations from
the source text — not part of the algebra tree at all) are now round-tripped
too: `salg:base` and `salg:prologuePrefix` (`salg:PrefixBinding`:
`salg:prefixLabel`/`salg:namespace`) attached to the query/update root node.

This is a real correctness fix, not cosmetic: confirmed empirically that a
reconstructed `Query` with an *empty* `Prologue` gives a **wrong** answer
for `BASE`-relative `IRI()`/`URI()` builtin resolution (`Builtin_IRI` calls
`ctx.prologue.absolutize()` at evaluation time) — `IRI("foo")` under
`BASE <http://example.org/base/>` resolved to bare `foo` instead of
`http://example.org/base/foo` before this fix. It does *not*, however, make
`algebra.translateAlgebra` emit prefixed names in regenerated query text:
confirmed separately that its output is byte-identical regardless of
prologue content (`_AlgebraTranslator` never reads `query.prologue` at all).
That's a real limitation in rdflib itself this project can't work around
without patching rdflib — see `tests/test_phase4_prologue.py`.

Later phases (see project history for the full plan): SHACL shapes over
the vocabulary (for validating LLM-authored query graphs before
translation), and — as a stretch goal — porting starlayergraph's regex-
based `sparql12_to_11.py` rewriter onto this IR.

## Status: Phase 5 (started) — SHACL shapes over the vocabulary

Structural validation for an algebra graph — LLM-authored or
hand-authored — *before* attempting `rdf_to_query`/`rdf_to_update`, using
[pyshacl](https://github.com/RDFLib/pySHACL). Scope so far: Phase 1's core
graph-pattern operators (`BGP`/`Filter`/`LeftJoin`/`Union`) plus the
`TriplePattern`/`Variable` conventions and the `SELECT` query wrapper
(`Project`/`SelectQuery`), extended in a second pass to `VALUES` and
subqueries (`Join`, `ToMultiSet`, the `values`/`Binding` VALUES-row shapes,
and the `Slice`/`Distinct`/`Reduced`/`OrderBy`/`OrderCondition` query-
modifier shapes). See `starsparql/shapes.py` and
`tests/test_shacl_shapes.py`.

The VALUES/subquery pass also found and fixed a real bug in the first
pass, not just added coverage: the original `SelectQueryShape` hard-required
the query's top-level pattern (`salg:p`) to be exactly a `Project` node,
which would have rejected any top-level query using `LIMIT`/`ORDER BY`/
`DISTINCT`/`REDUCED` (each wraps `Project` in another operator —
confirmed empirically by walking real algebra output). Undetected by the
Phase 1 test suite because none of those queries use those modifiers at
the top level, only inside `OPTIONAL`/subqueries. Fixed by introducing a
shared `SubSelectShape` used at both the top-level-query position and the
subquery-embedding position, since the two are structurally identical
minus the outer query wrapper.

Not yet covered: property paths, aggregates/`GROUP BY`/`HAVING`, Update,
`MINUS`/`SERVICE`, `CONSTRUCT`/`ASK`/`DESCRIBE`-specific shapes, and real
expression-tree validation (`Filter`/`LeftJoin`/`OrderCondition`'s `expr`
is currently checked for cardinality only, not shape).

Building this surfaced a real pyshacl limitation worth knowing about:
SHACL Core doesn't require conformant processors to support recursive
shapes, and a query pattern is naturally recursive (an `OPTIONAL`/`UNION`
can nest another one inside it to arbitrary depth). A naive
recursively-self-referential shape for `rdf:List` traversal (`BGP.triples`)
blew straight past pyshacl's `max_validation_depth` guard on anything but
a trivial BGP — fixed by validating the list with a single `sh:sparql`
constraint instead of a self-referential `NodeShape` (constant path depth
regardless of list length). The *graph-pattern* recursion
(`Filter`/`LeftJoin`/`Union` each nesting another one) is genuine and has
no such rewrite: pyshacl's actual behavior there is to silently stop
validating and treat a branch as conformant after ~3 revisits of the same
shape, which is a false-negative risk (a deeply nested malformed pattern
might not get caught), not a false-positive one. See finding #9 in
`CLAUDE.md` for the full detail.

## Status: Phase 6 (started) — native SPARQL 1.2 algebra

Phase 3 confirmed a SPARQL 1.2 query round-trips through the Phase 1/2
encoder unchanged — but only because starlayergraph's `prepareQuery` *lowers*
`<<( s p o )>>` triple terms to plain SPARQL-1.1-shaped algebra before this
project ever sees them. The RDF produced for a 1.2 query has therefore never
actually represented SPARQL 1.2 — only its 1.1-equivalent shape. Phase 6
fixes that: a genuine `TripleTerm` node, first-class in the algebra tree
this project encodes, not lowered away upstream.

Ingestion goes through this project's own
`starsparql.parse12.prepare_query_12`/`prepare_update_12` — **not**
starlayergraph's `prepareQuery`, and not starlayergraph's text-rewrite pipeline
(`sparql12_to_11.py`) at all. Instead, `starsparql/grammar12.py`
extends rdflib's own real SPARQL grammar in place: the term-position rules a
triple term needs (`GraphTerm`/`VarOrTerm`/`GraphNode`/`GraphNodePath`) are
plain `pyparsing.MatchFirst` objects with a public `.append()` method, and
pyparsing composes grammar rules by reference — so appending new
`<<( s p o )>>`/`TRIPLE(s, p, o)` productions is visible to every rule built
on top of them, without forking rdflib's grammar module. A parse action on
the new production builds the algebra node directly during parsing, the
same way rdflib's own grammar works everywhere else — no
text-rewrite-then-reparse-then-reverse-engineer-the-structure round trip.

The algebra node itself, `starsparql.triple_term.TripleTermNode`, is a
`CompValue` *subclass* (not a substitute/proxy object) with `__hash__`/
`__eq__`/`__lt__` added — confirmed necessary and sufficient, empirically,
for a real `TripleTerm` to survive rdflib's completely unmodified
`translateQuery`/`translateUpdate`: `reorderTriples`/`_knownTerms` (BGP
join-order optimization) need every triple-pattern term hashable *and*
orderable, and rdflib's `_addVars` bookkeeping pass only recurses into
`CompValue`/`list`/`tuple`/`ParseResults` when discovering variables — a
non-`CompValue` substitute silently loses any variable nested inside a
pattern-with-variables triple term, confirmed as a real, reproducible defect
during development, not just a theoretical risk. Subclassing `CompValue`
avoids this for free, since rdflib's own generic recursion already knows how
to walk one.

RDF encoding needed almost nothing new: `to_rdf.py` is completely unchanged
(the generic `CompValue` branch already produces the right shape), and
`from_rdf.py` needed exactly one named special case (the same pattern as the
existing `TrueFilter` case) to reconstruct a `TripleTermNode` specifically,
rather than a plain `CompValue`, on decode.

Structural verification (encode → decode → compare tree shape and `_vars`
bookkeeping) was the initial correctness bar — a `TripleTermNode`-bearing
tree can't be executed in-process (rdflib's evaluator has no notion of
matching one against real stored data; confirmed it just silently returns
no matches rather than raising). `starsparql/serialize12.py` closes
that gap a different way: it extends rdflib's own
`algebra.translateAlgebra`/`_AlgebraTranslator` to regenerate real SPARQL
1.2 text (`<<( s p o )>>` syntax) from the decoded tree, and both the
original and round-tripped text are then executed against a real
`StarLayerGraph.query(text)` — letting starlayergraph's own internal 1.1-lowering
handle execution as a black box, exactly as intended. Verified with real,
non-empty result rows for ground/pattern-with-variables/nested/`TRIPLE()`
triple terms — see `tests/test_phase6_serialize12.py`.

Two more capabilities were added in the same phase, past the original
minimal scope:

- **Expression-position usage** — `isTRIPLE(expr)`/`SUBJECT(expr)`/
  `PREDICATE(expr)`/`OBJECT(expr)` as new SPARQL 1.2 builtins, and a triple
  term usable directly as a value (`BIND(<<( ... )>> AS ?x)`), via
  `grammar12.py`'s second extension point (`PrimaryExpression`/
  `BuiltInCall`, confirmed mutable the same way the term-position grammar
  objects were). Building the serializer side of this found a real,
  non-obvious rdflib behavior: `algebra._traverse` stops recursing into a
  node's *children* the instant its visitor callback returns non-`None` —
  a builtin's own argument can itself be an unresolved `TripleTermNode`
  placeholder, and returning early (mirroring the term-position branches'
  own convention) silently skipped the later visit needed to resolve it.
- **`CONSTRUCT` query serialization** — confirmed empirically that plain,
  unmodified rdflib has *no* `ConstructQuery` handling in
  `_AlgebraTranslator` at all (not "less tested" — genuinely absent;
  `translateAlgebra` returns `""` for any CONSTRUCT query, triple terms or
  not, since its output buffer is only ever seeded by the `SelectQuery`
  branch). This is a real, new capability added on top of rdflib, not a
  patch to something that already mostly worked — and needed two more
  fixes only discoverable by testing against real `StarLayerGraph`
  execution rather than by reading `algebra.py`'s source: `Project.PV`
  means something different for `CONSTRUCT` than for `SELECT` (bookkeeping,
  not a variable list to print — the base class's `Project` branch doesn't
  know that and printed a stray `?x` into invalid syntax), and starlayergraph's
  own regex-based `sparql12_to_11.py` rewriter turned out to require the
  literal `WHERE` keyword for `CONSTRUCT` specifically, even though it's
  optional per the SPARQL grammar itself and this project's `SELECT`
  serialization has always omitted it without issue.

Still deliberately deferred: a genuinely in-process-executable
`TripleTermNode`-bearing tree with no text round-trip at all (the intended
eventual direction is a tree-level 1.2-algebra→1.1-algebra translator this
project would write itself); Update serialization back to text (never
attempted by this project even for plain 1.1); `ASK`/`DESCRIBE`
serialization (same "no branch exists" gap `CONSTRUCT` had, not pursued);
and a real Oxigraph backend as a second execution leg.

## Status: Phase 7 (started) — W3C SPARQL 1.2 test suite + annotation syntax

A real W3C SPARQL 1.2 conformance test suite (`w3c/rdf-tests`'s
`sparql/sparql12/`) is now fetched and run against this project's own
pipeline end to end — parse via `parse12.py` → encode → decode →
regenerate text via `serialize12.py` → execute via a real `StarLayerGraph`
→ compare against the suite's own official expected results, not just
self-consistency (see `tests/test_w3c_sparql12.py`,
`tests/w3c_sparql12/`). Running it against real conformance data (rather
than hand-written cases) drove real scope growth:

**Annotation/reification-shorthand syntax** (`<<s p o>>`, `<<s p o ~
reifier>>`, `s p o ~ r`, `s p o {| ap av ; ... |}`) — previously out of
scope — is now built. It needed a different grammar mechanism than
`<<( s p o )>>`/`TRIPLE()`: those are self-contained term productions (one
algebra node, no side effect); these four each expand to *multiple*
sibling triples (component `rdf:subject`/`predicate`/`object` triples + an
`rdf:reifies` triple, and for two of the four forms the base triple too)
that must land in the enclosing `BGP`, not wrapped in a single new node.
The mechanism: rdflib's own `expandTriples` (already bound to
`TriplesSameSubjectPath`/`TriplesSameSubject`) flattens whatever a matched
statement produces into a list, later regrouped into triples three at a
time — the same mechanism that already expands `s p1 o1 ; p2 o2` shorthand
— so a new alternative whose parse action returns a flat term list rides
that mechanism for free. A real bug surfaced building it: appending the
new alternatives (mirroring how the term-position productions were
installed) silently broke *every* ordinary triple pattern, because
`TriplesSameSubjectPath`'s existing alternative greedily matches `s p o`
and wins first (pyparsing's `MatchFirst` is first-match, not
longest-match) — fixed by inserting the new alternatives at the front
instead of the back, so they're tried before the ordinary one.

**A real, unresolved bug was found and explicitly not fixed this
session:** a cross-test state-corruption issue where certain earlier test
runs cause an otherwise independently-verified-correct query to fail
parsing afterward, with an error pointing at a character offset that
doesn't match its own text. Confirmed *not* a translation bug (the exact
query parses fine in isolation, and after manually replaying the same
operation sequence outside pytest) but reproduces reliably through the
actual test function. Many plausible causes were ruled out with real
evidence (test/import order, `starlayergraph` import timing, data loading,
function scope, decorators, caching, pytest's assertion rewriting, the
`hypothesis` plugin) without finding the actual root cause — so the
harness's current pass/fail counts (105/218 in the last standalone run)
aren't fully trustworthy: some failures may be this bug rather than the
specific error each one reports. See CLAUDE.md's Phase 7 finding for the
full investigation trail, and the "Not started" list for the real,
separately-confirmed gaps (an oversimplified annotation-value grammar that
doesn't accept a blank-node property list as a value, `VALUES` not
extended to accept a triple-term value the way ordinary term positions
were, and starlayergraph's own Turtle parser rejecting some deeply-nested test
fixtures — not fixable from this project's side).

## Setup

Not published to PyPI. From a checkout next to `starlayergraph`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ../starlayergraph
pip install -e ".[test]"   # includes pyshacl, for shapes.py
pytest
```
