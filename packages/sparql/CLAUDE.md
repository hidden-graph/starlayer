# starsparql — project memory

Read this first in a new session. It captures design decisions and
empirically-confirmed findings that aren't obvious from the code alone —
several of them took real investigation (reading rdflib internals, running
experiments) to establish, and re-deriving them from scratch would be
wasted effort.

## Purpose

Translate SPARQL 1.2 queries into and out of an RDF representation of their
algebra, so a query can be stored, versioned, annotated, and queried about
at the same granularity as any other RDF data — and eventually, so a query
can be *produced* as structured RDF (e.g. by an LLM) rather than as an
opaque string. Also intended, longer-term, to let
[starlayergraph](https://github.com/hidden-graph/starlayergraph)
simplify its own SPARQL-1.2-to-1.1 rewriting by working on this project's
algebra IR instead of hand-rolled regex text passes (not started yet — see
"Not started" below).

Sibling project: `../starlayergraph` (this repo's dependency, installed
editable — see Setup). That repo's `starlayergraph/query/sparql12_to_11.py` is
the thing a future phase might eventually simplify.

## Design (read `starsparql/vocab.py`'s module docstring for the full version)

rdflib's own SPARQL algebra (`rdflib.plugins.sparql.algebra`) is already a
tree of `CompValue`/`Expr` nodes — each just a named dict (`name` + typed
keys, e.g. `BGP(triples=...)`, `Filter(expr=..., p=...)`). That maps onto
RDF almost mechanically: `node.name` → `rdf:type salg:<name>`, each
`key: value` → `salg:<key>` predicate, recursively encoded. **One generic
recursive encoder/decoder** (`to_rdf.py`/`from_rdf.py`) handles every
operator and expression builtin uniformly — not one function per operator —
including *introspecting rdflib's live parser grammar at import time* to
rebuild the expression-name → eval-function table
(`from_rdf._discover_expr_evalfns`), rather than hand-transcribing rdflib's
~60 builtins. This is why Phase 2 (CONSTRUCT/ASK/DESCRIBE, MINUS, SERVICE,
aggregates, GROUP BY/HAVING, ORDER BY/LIMIT, subqueries) worked with **zero
new code** — only shapes that aren't CompValue nodes at all, or aren't
uniquely identifiable by shape alone, needed dedicated handling.

## Status: Phases 1–4 complete, Phases 5–9 started (203 tests passing in
the core suite; Phase 7's W3C SPARQL 1.2 suite now reports **214 passed /
221 total** (4 failed, 3 skipped), run in isolation via
`pytest tests/test_w3c_sparql12.py -m w3c_sparql12` — up from 105/218 across
earlier follow-up passes, and now fully trustworthy: **a later session
root-caused and fixed the cross-test state-leak bug** this entry used to
flag as unresolved (see finding #25 — it was an import-order hazard in
this project's own `__init__.py`, not a pytest/pyparsing mystery) and
**closed the `syntax-update-anonreifier-01`/`-02` gap** (finding #26). The
4 remaining failures are all deliberate, documented divergences from the
W3C suite's own fixture labels, not gaps to close: `list-anonreifier-01`/
`list-tripleterm-01` (genuine spec ambiguity the fixtures' own text flags,
finding #24) and `compound-tripleterm-subject`/`nested-tripleterm-02`
(labeled `PositiveSyntaxTest` by the suite, but the shape they exercise —
a triple term nested in *another* triple term's own subject slot — is
invalid RDF 1.2 regardless of that label; this project now correctly
rejects it, see finding #27, which also **supersedes finding #20 below —
that finding's core conclusion was wrong**) — plus two real fixes in the
sibling `starlayergraph` repo's own Turtle parser

Round-tripped at the **algebra layer** (post `translateQuery`/
`translateUpdate`), verified by *executing* both the original and the
round-tripped query/update and comparing results — never by comparing
regenerated query text (see the `translateAlgebra` finding below).

- **Phase 1** (`29465a5`): SELECT/BGP/FILTER/OPTIONAL/UNION.
- **Phase 2** (`d19cba7`): CONSTRUCT/ASK/DESCRIBE, MINUS, SERVICE (structural
  only, never executed — would need a live network call), property paths
  (all 5 `rdflib.paths.Path` forms — needed real new code, not a CompValue),
  aggregates/GROUP BY/HAVING, ORDER BY/LIMIT/OFFSET, subqueries, VALUES
  (incl. UNDEF), full SPARQL Update (INSERT/DELETE DATA, DELETE WHERE,
  Modify, LOAD/CLEAR/DROP/CREATE/ADD/MOVE/COPY, graph-qualified forms).
- **Phase 3** (`5ba8014`): confirmed RDF 1.2 (starlayergraph) queries/updates
  round-trip through Phase 1/2 **unchanged** — no new code. See "RDF 1.2"
  finding below.
- **Phase 4** (`eb14ba1`): Prologue (BASE/PREFIX) round-trip — a real
  correctness fix, not cosmetic. See "Prologue" finding below.
- **Phase 5** (started, uncommitted): SHACL shapes over `salg:` for
  structural validation *before* `rdf_to_query`/`rdf_to_update` — the
  "validate an LLM-authored (or hand-authored) algebra graph before
  translating it" goal from the original plan. Scope so far: Phase 1's core
  graph-pattern operators (`BGP`/`Filter`/`LeftJoin`/`Union`) plus the
  `TriplePattern`/`Variable` conventions and the `SELECT` wrapper
  (`Project`/`SelectQuery`), and — extended in a second pass — `VALUES` and
  subqueries (`Join`, `ToMultiSet`, `values`/`Binding`, `Slice`/`Distinct`/
  `Reduced`/`OrderBy`/`OrderCondition`) — see `starsparql/shapes.py`
  and `tests/test_shacl_shapes.py`. Building the VALUES/subquery slice
  found and fixed a real bug in the *first* pass, not just added coverage:
  see finding #10 below (`SelectQueryShape` originally required `salg:p` to
  be a bare `Project`, which would have rejected every top-level query
  using `LIMIT`/`ORDER BY`/`DISTINCT`/`REDUCED` — untested by Phase 1's own
  query set, which never used them at the top level).

  **A later session closed the expression-tree gap and fixed the
  `GraphPatternShape` recursion issue finding #9 originally left open.**
  All 63 of rdflib's expression builtins (`from_rdf._discover_expr_evalfns`)
  now have their own shape — `salg:ExpressionShape` (the expression-tree
  analog of `GraphPatternShape`) plus `_EXPR_NODE_FAMILY`, a Python table
  grouping the 63 names by their *real* argument signature (confirmed
  directly against live rdflib algebra output for every one, not guessed —
  arity/key-names aren't predictable from a builtin's name alone, e.g.
  `Builtin_REPLACE` uses `arg`/`pattern`/`replacement`/`flags`, not
  `arg1..arg4`, and `Builtin_BNODE`'s sole argument is optional unlike
  every other 0-or-1-arg builtin). The 63 short per-name shape
  declarations are *generated* from that table at `shapes_graph()` call
  time, not hand-written — mirrors this project's own established
  preference for mechanical generation over hand-listing wherever a
  source of truth exists. `Filter`/`LeftJoin`/`Extend`/`OrderCondition`'s
  `expr` are all wired to it now (previously cardinality-only). One
  deliberate exception: `Builtin_EXISTS`/`NOTEXISTS`'s `.graph` is a raw,
  untranslated SPARQL parse-tree fragment (`GroupGraphPatternSub`/
  `TriplesBlock` — rdflib translates it lazily at evaluation time, not
  parse time), a genuinely different vocabulary from everything else this
  file targets — out of scope for this pass, cardinality-only, same as
  the still-open gaps below. Also found and fixed in the same pass: a
  real, previously-undetected gap where `Extend` (`BIND`'s algebra node)
  was missing from `GraphPatternShape`'s recognized-operator list
  entirely — see finding #9's rewrite below for how the old
  `sh:node`-based recursive dispatch was silently masking exactly this
  kind of gap, and the `sh:class`-based fix now used by both
  `GraphPatternShape` and `ExpressionShape`.

  **A real RDFS ontology for the `salg:` vocabulary now exists** —
  `starsparql/salg-ontology.ttl` (a standalone Turtle file, not a
  Python string, so it's directly usable by any RDF tool without going
  through this project's own code) plus `ontology.py` (a thin loader,
  `ontology_graph()`) and `expr_families.py` (the `{name: family}` table
  for the 63 expression builtins, factored out of `shapes.py` so
  `ontology.py` doesn't need `pyshacl` just to read it). Classes,
  subclasses, properties, subproperties, domain, range — scope matches
  `shapes.py` exactly. **Not just documentation**: `validate()` actually
  loads it as `pyshacl.validate(..., ont_graph=ontology_graph(),
  inference="rdfs")` — real RDFS reasoning runs before validation, which is
  what let `GraphPatternShape`/`ExpressionShape`/`SubSelectShape` shrink
  from enumerating every concrete class by name (`sh:or ([sh:class
  salg:BGP] [sh:class salg:Filter] ...)`, 8 or 63 alternatives) down to a
  single `sh:class salg:GraphPattern`/`salg:Expression`/`salg:SubSelect`
  check against the ontology's own superclass — RDFS subclass entailment
  does the enumeration instead.

  Wiring this up for real (not just writing the ontology and leaving it
  unused) surfaced two distinct, both-real classes of bug, both only
  detectable by actually running reasoning, not by inspecting the turtle:
  1. **Multiple `rdfs:domain` triples on one property don't mean "any of
     these."** RDFS domain entailment fires once per `rdfs:domain` triple
     independently — two declarations on one property (e.g. `salg:var`
     domain `salg:Extend` *and* `salg:Binding`, since both use that
     property name) entail the value is *both* classes *simultaneously*.
     An `Extend` node was getting falsely entailed `rdf:type
     salg:Binding` too. Fixed by omitting domain entirely wherever a
     property is shared by a small handful of otherwise-unrelated classes,
     rather than trying to express a union that RDFS domain doesn't have
     syntax for.
  2. **Domain/range entailment can silently pre-satisfy the very `sh:class`
     check it's describing, defeating validation rather than helping it.**
     Confirmed via a negative test (`test_union_p1_pointing_at_unrecognized_node_fails`)
     that stopped correctly failing the moment `salg:p1`/`salg:p2` were
     given `rdfs:range salg:GraphPattern`: a deliberately-malformed value
     with no real operator type got auto-entailed `salg:GraphPattern`
     simply for being the *object* of a `salg:p1` triple — since RDFS
     reasoning runs *before* SHACL validation, this happens regardless of
     what the value actually is, unconditionally satisfying
     `GraphPatternShape`'s own check. The mirror-image (domain-side)
     version is just as exploitable one hop removed — a fake node given a
     `salg:p1` property of its own gets falsely entailed `salg:GraphPattern`
     too, and would then pass if reused as *another* operator's `p1` (see
     `test_bogus_node_reused_as_p1_via_another_operator_still_fails`).
     Fixed by removing domain/range from every property feeding into an
     `sh:class`-checked expression/pattern position (`salg:arg`/`arg1`/
     `arg2`/`arg3`, `salg:expr`, `salg:op`, `salg:other`, `salg:p1`/`p2`,
     `salg:graph`, `salg:iri`, and several more) — see each property's own
     comment in `salg-ontology.ttl`, and `ontology.py`'s module docstring
     for the general principle. `salg:triples`' `rdfs:range rdf:List` is
     the one safe exception (`TriplePatternListShape` never checks
     `rdf:type` at all, so there's no `sh:class` check for range
     entailment to defeat) — but even that property's *domain* had a
     separate, unrelated collision: `salg:BGP` and the deliberately
     out-of-scope, raw-parse-tree `TriplesBlock` fragment (inside
     `Builtin_EXISTS`/`NOTEXISTS`) both happen to use a same-named
     `triples` key (this project's encoding is generic/key-name-based, see
     `to_rdf.py`), so `rdfs:domain salg:BGP` on `salg:triples` falsely
     typed every `TriplesBlock` node as `salg:BGP` too, and `BGPShape`'s
     own shape then wrongly fired on it.

  Property paths, aggregates/`GROUP BY`, Update, and `CONSTRUCT`/`ASK`/
  `DESCRIBE`-specific shapes are still not covered — `salg:GraphPatternShape`'s
  `sh:class` check (backed by `salg:GraphPattern`'s `rdfs:subClassOf`
  membership in `salg-ontology.ttl`) is the one place a new operator needs
  registering now — one `rdfs:subClassOf` triple in the ontology, not a
  shapes.py edit.
- **Phase 6** (started, uncommitted): a genuine, native SPARQL 1.2 algebra
  representation — real `TripleTermNode`s (`<<( s p o )>>`/`TRIPLE(s, p, o)`)
  as first-class nodes in the tree this project encodes to RDF, not
  starlayergraph's lowered SPARQL-1.1-equivalent shape (which is what Phase 3
  round-trips). Ingestion goes through this project's own
  `starsparql.parse12.prepare_query_12`/`prepare_update_12`, which
  extend rdflib's real grammar in place (`grammar12.py`) rather than
  depending on starlayergraph's SPARQL-1.2-to-1.1 text-rewrite pipeline at all —
  see findings #11/#12 below for how, and two real bugs caught while
  building it. RDF encoding needed almost nothing new: `to_rdf.py` is
  unchanged (the generic `CompValue` branch already covers
  `TripleTermNode`), `from_rdf.py` needed one named special case (mirrors
  the existing `TrueFilter` case), and `shapes.py` gained
  `salg:TripleTermShape` plus extended subject/object term-position shapes.
  See `starsparql/grammar12.py`/`triple_term.py`/`parse12.py` and
  `tests/test_phase6_rdf12_native.py`.

  Structural verification (encode → decode → compare tree shape and `_vars`
  bookkeeping) was the initial correctness bar, since making a
  `TripleTermNode`-bearing tree directly *executable* in-process isn't
  possible — rdflib's evaluator has no notion of matching a `TripleTermNode`
  pattern against real stored data (confirmed empirically: it just treats
  the node as an opaque already-bound value, matching nothing, silently —
  no exception). A second pass (same session, `starsparql/
  serialize12.py`) closed that gap a different way: **not** by making the
  tree itself executable, but by extending rdflib's own
  `algebra.translateAlgebra`/`_AlgebraTranslator` to regenerate real SPARQL
  1.2 *text* (`<<( s p o )>>` syntax) from the decoded tree, then executing
  *that text* — both the original and the round-tripped version — against a
  real `StarLayerGraph.query(text)`, letting starlayergraph's own internal
  1.1-lowering do the actual execution as a black box. See
  `tests/test_phase6_serialize12.py` for the full loop, verified with real
  non-empty result rows for ground/pattern-with-variables/nested/`TRIPLE()`
  triple terms.

  **Expression-position support was added in a follow-up pass** (same
  session): `isTRIPLE(expr)`/`SUBJECT(expr)`/`PREDICATE(expr)`/
  `OBJECT(expr)` as new SPARQL 1.2 builtins, and a triple term usable
  directly as a value (`BIND(<<( ... )>> AS ?x)`), via `grammar12.py`'s
  second extension point (`PrimaryExpression`/`BuiltInCall`, both confirmed
  mutable `MatchFirst` objects the same way `GraphTerm`/etc. already were).
  Building the serializer side of this surfaced finding #13 below — a real,
  non-obvious rdflib behavior, not something guessable from reading the
  branch code alone.

  **CONSTRUCT support was then added too** — originally scoped as "just
  investigate feasibility," it turned out tractable and is now fully
  built and execution-verified, not merely prototyped. Confirmed empirically
  that plain rdflib's `translateAlgebra` has *zero* `ConstructQuery` handling
  at all (not merely "only SELECT is well-tested" — literally no case exists,
  and `self._alg_translation` is only ever seeded by the `SelectQuery`
  branch, so a CONSTRUCT query returns `""` even with no triple terms
  involved). Building this hit two more non-obvious things, both found only
  by testing against real `StarLayerGraph` execution — see finding #14.
  `ASK`/`DESCRIBE` remain unsupported (same "no branch exists" gap,
  confirmed but not pursued — nothing in scope needs them yet).

  **Tree-level 1.2-algebra→1.1-algebra lowering is now done** (a later
  session, `starsparql/lower_rdf11.py` + `tests/test_lower_rdf11.py`)
  — `lower_algebra_to_rdf11`/`query_to_rdf11`/`rdf11_to_sparql11_text`
  transform the decoded algebra tree directly (ground triple term ->
  eagerly-computed `tt:` URIRef in term-slot position, non-ground ->
  match-decompose into `rdf:subject/predicate/object` triples, expression
  position -> inline `Function(tt:fn/hash, ...)` call, CONSTRUCT template ->
  minted `BIND`-wrapped variable + its own encoding triples, VALUES row ->
  eager hash), producing plain SPARQL 1.1 text that runs directly against
  `StarLayerGraph`'s in-memory backend with **zero** dependency on
  `starlayergraph/query/sparql12_to_11.py`'s text-based rewriter. Verified
  against all 40 W3C SELECT + 6 CONSTRUCT fixtures this project's own
  harness already checks against official ground truth (`test_lower_rdf11.py`
  reuses the same fixtures/harness as `test_w3c_sparql12.py`, comparing this
  new path's results against the same official `.srj`/`.ttl` ground truth,
  not just against the older text-rewrite path). Two real bugs were found
  and fixed while building this — worth knowing about since both were
  subtle enough to be worth not re-deriving:
  1. A ground triple term at ordinary BGP pattern position must **not** be
     lowered via `BIND`-a-fresh-variable (the natural-looking mirror of the
     CONSTRUCT-template case) — that variable is *also* bound by the BGP's
     own ordinary triple match, and rdflib's `evalExtend` does not enforce
     "BIND target must be previously unbound" at all (`c.merge(...)`
     unconditionally overwrites, no equality check) — confirmed via a real
     regression (W3C fixture `pattern-4`, "No match", silently becoming a
     false match). Fixed by computing the value eagerly in Python instead
     (same mechanism as the VALUES-row case) and substituting a literal
     term — no variable, nothing for anything to overwrite.
  2. `starlayergraph/query/sparql12_to_11.py`'s `SUBJECT`/`PREDICATE`/`OBJECT`
     accessor functions (in the sibling `starlayergraph` repo) crashed
     when called directly inside `FILTER` (as opposed to `BIND`) — masked
     as a confusing `AttributeError: ... object has no attribute
     'bindings'` (an `AttributeError` escaping a `@property` getter makes
     Python fall back to `__getattr__`, per `Result.bindings`'s own
     implementation) rather than the real cause: `evalFilter` always calls
     `.eval()` with a `FrozenBindings` (via `ctx.forget(...)`), which has
     no `.graph` of its own, only a `.ctx` attribute pointing back to the
     real `QueryContext` that does. Fixed there (not here) using the same
     `getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None),
     "graph", None)` fallback `evaluate_patches.py`'s
     `_patched_relational_expression` already established for the same
     reason — this project's own W3C fixture `expr-2` is what caught it,
     since no existing test exercised these accessors from inside a bare
     `FILTER` before.

  **Execution now skips the SPARQL 1.1 text step entirely** (same later
  session): `lower_rdf11.py` gained a fourth entry point,
  `rdf11_to_query(graph, root)` — a thin wrapper over the *already
  fully-executable* `Query` object `from_rdf.rdf_to_query` decodes
  (`_addVars`/`analyse` already rerun, `Function` nodes already promoted to
  evaluable `Expr`). `StarLayerGraph.query()`/`StarLayerDataset.query()`
  both already special-case a non-`str` `query_object` to skip their own
  text rewriting/parsing and execute it as-is — confirmed, no changes
  needed there. `rdf11_to_sparql11_text` (and its `_AlgebraTranslator11`)
  stay, for cases that genuinely need real text (debugging, external
  tools, a string-only backend) — but execution now goes
  `1.2 text -> 1.2 algebra -> 1.2 RDF -> 1.1 algebra -> 1.1 RDF -> Query
  object -> results`, with no text anywhere after the initial parse.
  Removing the round-trip through text surfaced one more real,
  previously-masked bug: `_lower_construct_query`'s minted template
  variables (e.g. the `tt:`-hash `BIND` target) were never added to the
  wrapping `Project.PV` — `evalConstructQuery` fills the template from
  `evalProject`'s *output* solutions, and `evalProject` silently drops any
  variable not listed in `PV`. Re-parsing regenerated SPARQL 1.1 text had
  been recomputing `PV` fresh from the text each time, accidentally
  masking this — direct object execution doesn't recompute anything, so
  every CONSTRUCT template triple minting a fresh triple term silently
  vanished from results until this was fixed. Exactly the kind of gap the
  user's own rationale for this change (isolating where errors occur)
  predicted it would surface.

  Also still deferred: a real Oxigraph
  backend as a second execution leg (only `StarLayerGraph`'s own execution
  has been wired up so far), and the W3C SPARQL 1.2 test suite
  (`w3c/rdf-tests`'s `sparql/sparql12/` — confirmed to exist and to be
  structured the same way as starlayergraph's own `tests/w3c/` Turtle harness,
  distinct from it) as a real conformance-test data source, both explicitly
  the next phase, not started.

  Also explicitly out of scope: Update serialization back to text (never
  attempted by this project even for 1.1 — see `test_phase2_update.py`'s
  docstring), and the `VERSION "1.2"` prologue directive. A `VALUES` row
  containing a triple-term *value* isn't handled by `serialize12.py` either
  — rdflib's own `values` branch has the same `.n3()`-crashes-on-CompValue
  issue the `BGP`/`TriplesBlock` branches had. (Annotation syntax —
  `{| ... |}`/`~reifier` forms — was listed here as out of scope; it no
  longer is, see Phase 7 below.)

- **Phase 7** (started, uncommitted): a real W3C SPARQL 1.2 test suite
  harness (`tests/test_w3c_sparql12.py`, `tests/w3c_sparql12/` — 224 test
  entries across 4 manifest categories, fetched via
  `download_w3c_sparql12_tests.py` from `w3c/rdf-tests`), run against this
  project's own translation pipeline end to end (parse via `parse12.py` →
  encode → decode → regenerate text via `serialize12.py` → execute via a
  real `StarLayerGraph`, compared against the suite's own official expected
  results — not just self-consistency). Building and running this harness
  is what drove the rest of Phase 7's real, substantial scope expansion:

  **Annotation/reification-shorthand syntax** (`<<s p o>>`, `<<s p o ~
  reifier>>`, `s p o ~ r`, `s p o {| ap av ; ... |}`) — previously listed as
  out of scope, now built (`grammar12.py`). This is architecturally
  different from `<<( s p o )>>`/`TRIPLE()`: those are self-contained
  *term* productions (one algebra node, no side effect); these four each
  expand to *multiple* sibling triples (rdf:subject/predicate/object
  component triples + an rdf:reifies triple, and for two of the four forms
  the base triple itself too) that must land in the *enclosing* BGP, not
  wrapped in a new node. See finding #15 for the mechanism (a new class of
  grammar splice point beyond the term-position one from Phase 6) and a
  real bug caught while building it (ordinary triples silently broke
  without a specific insertion-order fix). First measured against the real
  W3C suite: 105/218 tests passing (up from a 0-of-suite starting point,
  since none of Phase 6 had been tested against official conformance data
  before this).

  **A real, unresolved bug found and NOT fixed this session — flagged
  explicitly, not swept under a vague "failures remain" note:** a
  cross-test state-corruption issue where running certain earlier
  tests (in the same process) before a later, otherwise-independently-
  verified-correct query causes that later query to fail parsing with a
  `ParseException` pointing at a character offset that doesn't correspond
  to its own text. Confirmed *not* a translation-correctness bug — the
  exact same query text parses successfully in isolation, after manually
  replaying the same sequence of operations outside pytest, and after
  importing the test module without invoking anything — but reproduces
  reliably when the *actual* `test_eval_select` function is invoked (via
  pytest or by direct call) after certain other tests have run. Ruled out,
  with real evidence for each: test order specifically, module import
  order, `starlayergraph` import timing, `parse_srj`, `StarLayerGraph.parse`
  (data loading) individually, function-scope/closures, decorators,
  `.pyc`/`.pytest_cache` staleness, pytest's assertion-rewriting import
  hook, and the `hypothesis` pytest plugin. Not yet identified: the actual
  root cause. Revisit by bisecting further inside pyparsing's own internals
  (its packrat cache is confirmed disabled, so the leak is somewhere else)
  before assuming the harness's pass/fail counts are fully reliable —
  some of the 113 current failures may be this bug rather than the
  specific error message they report.

  **Resolved in a later session — root cause found, not just narrowed
  further.** See finding #25 for the full mechanism; summary here: any
  import of the bare `starsparql` package (which pulls in
  `from_rdf.py`, whose `_discover_expr_evalfns()` snapshots rdflib's live
  parser grammar *at import time*) happening *before* anything imports
  `parse12` (whose `grammar12.install()` mutates that same shared grammar
  in place) silently corrupts later query evaluation — confirmed with a
  minimal, deterministic, **non-pytest** repro (a plain Python script,
  reproducible every time, unlike the original symptom), which is what
  made this tractable where the earlier investigation wasn't. Genuinely
  predates this session: `tests/test_adversarial_roundtrip.py` (pre-existing,
  not new) imports in exactly the corrupting order
  (`from starsparql import query_to_rdf, rdf_to_query` before
  `from starsparql.parse12 import prepare_query_12`) — it just never
  fired because that file has been excluded from every run this whole
  project's life so far (needs a live Oxigraph server). A new file added
  this session (`tests/test_ast_ontology.py`, alphabetically early) tripped
  the same latent wire independent of Oxigraph, which is what surfaced it.
  Fixed structurally, not by patching around the specific symptom:
  `starsparql/__init__.py` now imports `parse12` first, before
  anything else, so `grammar12.install()` always completes before any
  other code in this project can observe the grammar — order-independent
  regardless of which test file (or external caller) happens to import
  this package first. Verified: the original symptom (`op-2` in
  `test_lower_rdf11.py` silently returning empty instead of 3 rows) and
  the general class of bug are both gone — the full suite now produces
  byte-identical pass/fail results across repeated runs, which it did not
  before.

  **Four categorized gaps found via the suite were resolved in a follow-up
  pass (105/218 → 130/218), one at a time, in the order first reported:**

  1. **Annotation-block value grammar** — `{| ap av ; ... |}`'s value slot
     was `VarOrTerm` only, rejecting a `[...]` blank-node property list as
     an annotation value (real test data:
     `{| :source [ :graph <...> ; :date "..." ] |}`). Fixed: widened to
     `GraphNode`, plus a new `_expand_value()` helper in `grammar12.py`
     handling the nested-list shape a `[...]` match produces (see finding
     #15's shared invariant).
  2. **`VALUES` didn't accept a triple-term value** — `DataBlockValue`
     (rdflib's own `VALUES`-row-value grammar) had no ground-triple-term
     alternative. Fixed: `DataBlockValue.append(TripleTermExpr)` /
     `.append(TripleTermCall)` in `install()` — a plain append, since a
     ground triple term is self-contained (no side-effect triples, unlike
     the annotation forms).
  3. **3 `NegativeSyntaxTest`s incorrectly parsed as valid** —
     `bindbnode-tripleterm` and `bnode-predicate-anonreifier` fixed via
     grammar narrowing (see finding #15's subject/predicate/object
     breakdown). The third, `syntax-update-anonreifier-02`
     (`{| |}`/annotation syntax inside `INSERT DATA`/`DELETE DATA`, which
     must reject blank nodes per the SPARQL 1.1 `QuadData` grammar note)
     was **not fixed in this pass** — confirmed that even *plain,
     unmodified* rdflib doesn't enforce this rule syntactically either
     (`INSERT DATA { _:x <p> <o> }` parses fine via bare
     `rdflib.plugins.sparql.parser.parseUpdate`), so it's a semantic-only
     spec rule neither rdflib nor this project's grammar checked at the
     time. **Resolved in a later session, see finding #26** — not via the
     grammar redesign flagged as the only option here (a structurally
     separate, ground-only `TriplesSameSubject` variant for `QuadData`
     turned out not to be needed), but via a post-translate semantic check
     instead, which turned out to be the simpler and sufficient fix.
  4. **"starlayergraph's own Turtle parser" bucket turned out to be two-thirds
     this project's own bugs, one-third genuinely external** — see
     findings #16 (a real rdflib query-*parser* whitespace/blank-node-
     adjacency bug, worked around in this project's own serializer),
     #17 (the W3C harness itself always parsed data fixtures as
     `format="turtle12"` regardless of actual file type — `.trig` content
     needs `trig12`, etc.), and #18 (the one part that's genuinely
     external: starlayergraph's Turtle parser's `~ reifier` handling, plus a
     separate dataset/`ConjunctiveGraph` harness limitation for
     named-graph fixtures).

  **A follow-up pass (130/218 → 190/218) closed the reifier-nesting gap
  finding #15 had left open, plus two real bugs found in the sibling
  `starlayergraph` repo's own Turtle parser** (fixed there, not here —
  see findings #19–#23 for the fix-by-fix breakdown):
  - `<<s p o>>`/`<<s p o ~ r>>` reifier terms can now hold *another*
    reifier term or a nested ground triple term in their own
    subject/object slots (finding #19).
  - A real bug in the ground triple term's own expression-position/
    pattern-position split, introduced by finding #15's original
    `_TripleTermSubject` fix: the "no anonymous `[]`, no nested triple
    term" restriction only actually holds in *expression* position
    (`BIND`/`FILTER`/`VALUES`), not ordinary pattern position — confirmed
    by directly contrasting positive and negative W3C tests using the
    identical shape in both positions (finding #20).
  - `TRIPLE(s, p, o)`'s three arguments are full `Expression`s per spec
    17.4.6 (`TRIPLE(?s, ?p, str(?o))`), not just terms — only the
    function-call spelling, not `<<( )>>` (finding #20).
  - A real `TripleTermNode` sort-key bug: comparing two ground triple
    terms where one has a nested-triple-term subject and the other
    doesn't produced a `tuple < str` `TypeError` during rdflib's own BGP
    reordering (finding #21).
  - The `~ r`/`{| |}` annotation-suffix forms can now combine on one
    statement (`s p o ~ r1 {| |} ~ r2 {| |}`, repeatable), and their base
    triple's own subject/object can be a nested reifier term too —
    rebuilt as one combined grammar rather than two separate ones
    (finding #22).
  - An annotation pair's predicate can be a real SPARQL property path
    (`{| :r/:q 'ABC' |}`) in ordinary WHERE-clause context — but
    deliberately *not* in CONSTRUCT-template context, where even a
    trivial single-IRI "path" broke rdflib's own template-triple
    reordering in a way ordinary WHERE-clause parsing doesn't hit
    (finding #23).

  **Two real, external bugs found and fixed in the sibling
  `starlayergraph` repo's Turtle parser** (`starlayergraph/parsers/
  turtle_parser.py`, a different codebase from this project's own
  `grammar12.py` — committed there, not here): (a) `~ reifier`-suffixed
  triples nested inside another triple term's subject/object slot crashed
  with "too many terms inside <<...>>" — `qt_to_json`'s own subject/object
  handling never checked `_has_reifier` before falling through to
  `_norm_qt`, unlike `expand_qt_in_triple` (used for ordinary triples),
  which already did. (b) A genuinely nested reifier-shorthand term as
  subject (`<< <<:s :p :o>> :p2 :o2 >>`, no `~` involved) crashed via
  `starlayergraph/model/triple.py`'s `TripleTerm.__init__`, whose "a triple
  term's subject can never be a triple term" check doesn't distinguish a
  *reifier* (an ordinary node, legal in any position) from a genuine
  nested ground triple term (illegal in subject position) — the same
  class of conflation finding #20 fixed on this project's own side.
  Fixed by extracting one shared `_resolve_qt_slot` helper (replacing four
  near-duplicate call sites across `qt_to_json`/`expand_qt_in_triple`)
  that checks reifier-shorthand forms *before* the ground-triple-term
  nesting restriction, so a reifier resolves to its node in any position
  while the nesting restriction still applies only to genuine ground
  triple terms. Verified against the sibling repo's own test suite (772
  passed, 0 regressions) before committing there.

- **Phase 8** (started, uncommitted): `salg:QueryCollection` — serializing
  a *set* of independent queries as one RDF graph/Turtle file (goal 4 from
  `todos.md`, "creates an rdf/sparql version to serialize sets of
  queries"). The vocabulary (`salg:QueryCollection`/`salg:queries`, an
  `rdf:List` of member `salg:Query` roots) already existed in
  `salg-ontology.ttl`, unused — confirmed via a research pass that neither
  this project nor the sibling `starlayergraph` repo had any prior
  reader/writer for it, or any comparable "collection of queries as RDF"
  concept at all (the closest prior art in either repo is the W3C-suite
  `download_w3c_sparql12_tests.py` scripts, which parse a real
  `manifest.ttl` via rdflib but only to *flatten* it into a local
  `index.tsv`, never round-trip it as RDF). `to_rdf.queries_to_collection`/
  `from_rdf.rdf_to_collection` (`starsparql/__init__.py`-exported)
  directly mirror `update_to_rdf`/`rdf_to_update`'s own established shape
  (a dedicated non-CompValue container `BNode`, typed, holding one
  `rdf:List`-valued property of member roots) — no new design needed,
  since the ontology had already anticipated the identical structure.
  `queries_to_collection` reuses `query_to_rdf(query, graph)` per member,
  writing all of them into one shared graph (already supported —
  `query_to_rdf`'s own docstring: "encoded queries in a larger store can
  always be found via `?q a salg:Query`"); `rdf_to_collection` reuses
  `rdf_to_query` per member (not the generic `_decode` walker an ordinary
  `rdf:List` goes through elsewhere, since each member needs
  `rdf_to_query`'s own per-query handling — recomputed `_vars`/`lazy`
  bookkeeping, its own reconstructed Prologue). `tests/
  test_query_collection.py` verifies the specific loop the user asked
  for: take this project's own existing test queries
  (`test_roundtrip.QUERIES`), encode them all as one collection,
  round-trip through real Turtle *text* (re-parsed into a fresh `Graph`,
  not just checked against the same in-memory graph the encoder built —
  the actual point of the feature is a standalone `.ttl` file), decode
  back, and confirm each decoded query still *executes* to the same
  result as the original — the same execution-based verification standard
  every other round-trip test in this project uses.

- **Phase 9** (started, uncommitted): the `shapes.py` completion pass over
  the ontology Phase 9's own predecessor built (see the "Not started"
  section's now-resolved SHACL bullet for the full ontology-side account).
  Six new areas, in priority order, each following the SAME
  ontology→shapes→tests loop already established (`pytest tests/
  test_shacl_shapes.py -q` green after each before moving on):

  1. **Update** — every operation shaped (`InsertData`/`DeleteData`/
     `DeleteWhere`/`Modify`/`DeleteClause`/`InsertClause`/`Load`/`Clear`/
     `Drop`/`Create`/`Add`/`Move`/`Copy`), plus `salg:GraphRefShape`
     (a graph term or a `PyStr`-tagged `DEFAULT`/`NAMED`/`ALL` keyword),
     `salg:GraphRefListShape` (`Add`/`Move`/`Copy`'s own exactly-2-element
     list — checked for length, not just well-formedness), and
     `salg:QuadsForGraphShape`/`QuadsForGraphListShape`. Found and fixed a
     second, real ontology gap while building this (not caught by the
     earlier ontology-only pass): `salg:QuadsForGraph` was already being
     *written* by `to_rdf._encode_quads_map` but had **no class
     declaration in the ontology at all** — added it.
  2. **CONSTRUCT/ASK/DESCRIBE** — confirmed empirically (not assumed) that
     a bare `DESCRIBE :alice` (no `WHERE` clause) produces `DescribeQuery
     {p: None, ...}` — `p` genuinely *absent*, not an empty pattern, and
     its own `PV` mixes plain IRIs with `Variable`-typed Literals
     (unproblematic — `PV` is cardinality-only everywhere in this file,
     same as `ProjectShape`/`SelectQueryShape` already treat it).
     `DescribeQueryShape.p` is `sh:maxCount 1` with no `sh:minCount`,
     unlike every other query-form shape.
  3. **Property paths** — `InvPath`/`SequencePath`/`AlternativePath`/
     `MulPath`/`NegatedPath`, a new `salg:PathShape` dispatch class
     (`sh:class`, same convention as `GraphPatternShape`/`ExpressionShape`),
     and the one genuinely *existing*-shape edit this pass made:
     `TriplePatternShape.predicate` needed widening to accept a `Path`
     (previously only `IRI`/`Variable` — a path-valued predicate had **no
     accepting shape at all** before this). Caught and avoided a real
     mistake before writing any Turtle: `salg:PredicateOrVariableShape` is
     *shared* by `TriplePatternShape` and `TripleTermShape.predicate` — a
     property path is legal in an ordinary triple pattern's predicate slot
     but **never** inside a `TripleTerm` (RDF 1.2's `tripleTerm`
     production restricts its own verb to a plain `iri`, confirmed via
     `grammar12.py`'s `_TripleTermPredicate`, built from `Var | iri` only).
     Widening the shared shape would have wrongly loosened `TripleTerm`'s
     own predicate too — fixed by adding a *new*,
     `salg:PredicateOrVariableOrPathShape`, used only by
     `TriplePatternShape`, leaving the original narrower shape
     untouched for `TripleTermShape`.
  4. **Aggregates/GROUP BY** — `GroupShape`/`AggregateJoinShape` plus all
     7 real `Aggregate_*` shapes (`Count`/`Sum`/`Min`/`Max`/`Avg`/`Sample`/
     `GroupConcat`). Confirmed empirically, not assumed: `Group.expr` is
     ***`None`*** (the bare Python value, not an empty list) for implicit
     single-group aggregation with no explicit `GROUP BY` clause at all —
     `GroupShape.expr` is optional (`sh:maxCount 1`, no `sh:minCount`),
     mirroring `DescribeQueryShape.p`'s same "confirmed-absent, not
     confirmed-empty" shape. `Aggregate_Sample` confirmed to have **no**
     `salg:distinct` property at all (unlike the other 6), needing its own
     separate body shape rather than reusing the shared one.
     **A real bug in `to_rdf.py` itself (not shapes.py or the ontology)
     was found while building this, initially flagged as deliberately
     not fixed in this pass, then traced one level deeper and closed in
     the same session.** `GROUP BY (?o+1)` (an *expression*-valued
     grouping key with no `AS ?var` alias) crashed `to_rdf.py`'s own
     encoder outright (`AssertionError: Object None must be an rdflib
     term`, inside `_build_rdf_list` — `Group.expr` is `[None]`, a
     one-element list containing bare Python `None`, when rdflib's own
     algebra restructures an un-aliased computed grouping key via an
     outer `Extend` with `var: None`). Root-caused further, not just
     patched around the symptom: reproduced the *identical* crash shape
     against **plain, unmodified rdflib** (`from rdflib import Graph;
     Graph().query("... GROUP BY (?o+1)")`, zero involvement from this
     project or `starlayergraph`) — it fails at *execution* time in
     rdflib's own `evaluate.evalAggregateJoin`
     (`Exception: Cannot eval thing: None`), confirming this is a genuine
     upstream rdflib bug, not a gap in this project's encoding. The two
     other `GROUP BY` forms — a bare variable, and an *aliased*
     expression `GROUP BY (?o+1 AS ?k)` — both confirmed to work
     correctly in plain rdflib and already encoded here with no issue
     (`test_phase2_aggregates.QUERIES`, this project's only existing
     aggregate test coverage, only ever exercised those two, which is why
     this went unnoticed until now).

     First fix (this project, same session): since the un-aliased form
     can never execute in *plain* rdflib regardless of how this project
     encodes it, `_encode_list` was given a clear, actionable
     `NotImplementedError` for a `None` list item (naming the exact
     construct and the working `AS ?var` alternative) in place of the
     confusing, unrelated-looking internal `AssertionError` from deep
     inside `rdflib.collection.Collection`.

     **Superseded the same session, per direct instruction that a
     diagnostic isn't a real fix: a genuine, functional fix now exists**
     — not in this project, but in the sibling `starlayergraph` repo,
     which turns out to be the right place, since the defect is in
     rdflib's own `algebra.translate` (parse-tree → algebra construction),
     a phase this project never touches directly. See that repo's
     `docs/rdflib-upstream-issues.md` Issue 9 and
     `starlayergraph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key`
     — it pre-processes the *parse tree* immediately before `translate()`
     runs, filling in the one piece of information the parser leaves
     missing for this construct (`GroupAs.var`) with a freshly-minted
     synthetic variable, mirroring rdflib's own `__agg_N__` convention.
     Confirmed via direct reproduction that this makes rdflib's own,
     completely unmodified `translate()` logic naturally produce a
     correctly-paired algebra tree, with the synthetic variable confirmed
     (via real execution) to never leak into the projected result. Once
     `starlayergraph` is imported (true for every real usage of this
     project, which needs a backend to execute against), the broken
     `[None]` shape never reaches `to_rdf.py` at all anymore —
     `_encode_list`'s own `NotImplementedError` check is now a pure
     defensive fallback for the (real but unusual) case where
     `starsparql` is used standalone, without `starlayergraph`
     ever imported. New regression test:
     `tests/test_phase2_aggregates.py::test_unaliased_expression_group_by_key_roundtrips`
     (needs `import starlayergraph`, unlike every other test in that file,
     specifically to exercise the patch) confirms the full round-trip —
     encode, decode, execute both, compare — works correctly, not just
     direct execution.
  5. **MINUS + SERVICE** — trivial `MinusShape` (mirrors `LeftJoinShape`
     minus `expr`); `ServiceGraphPatternShape`'s own `.graph` is
     cardinality-only, the same treatment as `Builtin_EXISTS`/
     `NOTEXISTS.graph` (confirmed empirically to be the identical kind of
     raw, untranslated parse-tree fragment).
  6. **QueryCollection** — one shape, `QueryCollectionShape`/
     `QueryListShape`, closing the one gap left over from Phase 8 (the
     ontology classes existed, nothing validated them yet).

  **Two real bugs worth remembering, both caught only by actually running
  the shapes, not by reading the Turtle:**
  - A Turtle-escaping bug in `shapes.py`'s own `SHAPES_TURTLE` Python
    string: writing `\"*\"/\"+\"/\"?\"` inside an `sh:message` (to embed
    literal quote characters in the Turtle *text*) only escapes at the
    *Python* string-literal level — the resulting Turtle source ends up
    with genuinely unescaped `"` characters mid-string, which Turtle's
    own parser then chokes on (`BadSyntax: ']' expected`). The existing
    `\"\"\"`-delimited `sh:select` blocks elsewhere in this file are a
    *different*, unaffected pattern (Python's triple-quote escape
    producing Turtle's own triple-quote long-string delimiter, not an
    embedded single quote) — don't conflate the two when adding a new
    message string with literal punctuation in it; simplest fix is to
    just avoid embedding literal quote characters in `sh:message` text
    entirely, as done here.
  - `SALG.term` (attribute access, used in a hand-written test) silently
    resolves to `rdflib.Namespace`'s own real `.term(name)` **method**
    instead of the `salg:term` `URIRef` — a genuine Python-level name
    collision, not a typo: `rdflib.Namespace` happens to define a method
    called exactly `term`, so ordinary attribute lookup finds it *before*
    `Namespace.__getattr__`'s dynamic URI-construction fallback ever runs
    (confirmed via `type(SALG.term)` → `<class 'method'>`, not `URIRef`).
    `to_rdf.py`'s own generic encoder is unaffected (`SALG[key]`, bracket
    access, always used there) — this only bites hand-written Python
    using attribute-style `SALG.term`. A negative test
    (`test_service_missing_term_fails`) silently removed *nothing* and
    "passed" as a false negative before this was caught — worth
    remembering as a reason to double-check a mutation test's own
    `graph.remove(...)` actually reduced the triple count, not just that
    `conforms` came back `False` for some other, coincidental reason.

  Verified: 114 tests in `test_shacl_shapes.py` (up from ~30 before this
  session), full project suite unaffected (203 local + 323 W3C-marked,
  same 4 pre-existing deliberate divergences, 0 new failures anywhere).

## Findings worth NOT re-deriving

These were confirmed by running real code, not by reading docs — trust them,
but if rdflib's version changes, re-verify before relying on them further.

1. **A bare Python `str` inside the algebra tree is not safe to encode as a
   plain `rdflib.Literal`.** `Literal("=") == "="` is **False** in rdflib,
   and the two hash differently — so `Literal("=")` fails a plain dict
   lookup keyed by `"="`. This is real: `RelationalExpression.op`,
   `OrderCondition.order`, VALUES' `UNDEF` sentinel, and Update's
   `GraphRefAll` keywords (`DEFAULT`/`NAMED`/`ALL`/`SILENT`) are all genuine
   bare `str` in the live algebra, never `Literal`, because they come from a
   bare `pyparsing.Keyword` match rather than a real-term grammar
   production. Fix: any bare `str` (`type(v) is str`) gets tagged with the
   reserved datatype `SALG.PyStr` on encode and decoded back to a bare
   `str` — universally, by value shape, not by an ever-growing per-key
   allowlist (that allowlist approach is what this replaced, after missing
   cases three times in a row).
2. **`int`/`bool` bookkeeping values don't have that ambiguity** (no
   equality/hash surprise), but still need `.toPython()` to become a real
   Python type for strict consumers (`Slice.start`/`.length` go straight
   into `itertools.islice`, which requires real `int`; a boolean `Literal`
   is always truthy in a plain `if`, since it's a non-empty string either
   way). These few (`start`, `length`, `lazy`) are still listed by key name
   in `from_rdf._PLAIN_VALUE_KEYS`.
3. **`rdflib.plugins.sparql.algebra.translateAlgebra` never reads
   `query.prologue` at all.** Confirmed by direct comparison: its text
   output is byte-identical whether the prologue is populated or empty.
   `_AlgebraTranslator` calls bare `.n3()` (no namespace manager)
   throughout. This means Phase 4's Prologue round-trip **cannot and does
   not** make regenerated query text use prefixed names — don't attempt
   that again without patching rdflib itself (out of scope). What Phase 4
   *does* fix is real: an empty `Prologue` on the reconstructed `Query`
   silently breaks `BASE`-relative `IRI()`/`URI()` builtin resolution at
   *evaluation* time (`Builtin_IRI` calls `ctx.prologue.absolutize()`) —
   `IRI("foo")` under `BASE <http://example.org/base/>` resolved to bare
   `"foo"` instead of the correct absolute IRI before the fix.
4. **RDF 1.2 (starlayergraph) queries need no special handling at the algebra
   layer.** starlayergraph rewrites `<<( )>>`/`isTRIPLE`/`LANGDIR`/etc. to plain
   SPARQL 1.1 text (`Extend`+custom-`Function`+`BGP`) *before* calling
   rdflib's real `translateQuery` — so `query.algebra` never contains a
   `TripleTerm` CompValue node at all. Confirmed against a real
   `StarLayerGraph` for triple-term patterns, ground triple-term values
   (the `tt:fn/hash` custom function), `isTRIPLE`, `SUBJECT`/`PREDICATE`/
   `OBJECT`, `LANGDIR`/`hasLANGDIR`, a CONSTRUCT that mints a new triple
   term, and an UPDATE with a triple-term pattern.
5. **~~The more ambitious alternative — preserving `<<( )>>` surface syntax
   directly in the algebra instead of starlayergraph's lowered form — doesn't
   work and shouldn't be retried without patching rdflib.~~ Superseded by
   Phase 6 — see finding #11: it does work, without patching rdflib.**
   Feeding starlayergraph's `parseQuery()` (which *does* restore `TripleTerm`
   CompValue nodes, but only in the pre-algebra parse tree) into rdflib's
   own `algebra.translateQuery()` crashes: `TypeError: cannot use
   'CompValue' as a set element (unhashable type)`, deep inside
   `reorderTriples`/`_knownTerms`. rdflib's algebra translator assumes every
   triple-pattern term is a hashable RDF identifier. This is exactly why
   starlayergraph lowers to SPARQL 1.1 before calling `translateQuery` in the
   first place — not an oversight on starlayergraph's part. The original
   conclusion here was right about *this specific path* (starlayergraph's
   already-lowered `parseQuery` output can't be fed to `translateQuery`
   unmodified) but wrong that the general goal was out of scope — Phase 6
   reaches it by extending rdflib's own grammar directly instead (own parse
   tree, never lowered, never crashes), not by trying to patch around the
   crash in this path.
6. **`_vars`/`lazy` bookkeeping (rdflib's own query-planning cache,
   `algebra._addVars`/`analyse`) must be recomputed after decoding a
   Query's algebra, but NOT after decoding an Update's.** `translateQuery`
   runs `_addVars`/`analyse` on the finished tree; `translateUpdate` never
   does, even for a `Modify` operation's WHERE clause (confirmed by reading
   `translateUpdate1` — it only calls `translateGroupGraphPattern`, not
   `translate`). `from_rdf.rdf_to_query` recomputes these;
   `from_rdf.rdf_to_update` correctly does not.
7. **Two Python dict shapes appear in the algebra that need different RDF
   encodings, distinguishable only by *key name*, not by shape** — a
   VALUES row (`Values.res`: `Dict[Variable, term]`) and an Update's
   `quads` field (`Dict[graph-term, List[triple]]`). For `Modify`, a quads
   key can itself be a `Variable` (`DELETE { GRAPH ?g {...} }`), so "keys
   are Variables" doesn't reliably distinguish them. Handled by checking
   for the literal key name `"quads"` in `_encode_comp_value`/
   `_decode_comp_value`, not by inspecting the dict's contents.
8. **A key literally named `base` or `prologuePrefix` written onto an
   algebra root node (for Phase 4) gets picked up by the generic CompValue
   decoder as if it were a real algebra key, unless explicitly excluded**
   (`from_rdf._PROLOGUE_KEYS`) — found this by writing a structural
   round-trip test (`test_service_structural_roundtrip`) that failed after
   adding Prologue encoding, not by reasoning about it in advance. Worth
   remembering: any *future* metadata attached to a shared root node needs
   the same exclusion treatment in `_decode_comp_value`.
9. **pyshacl does not fully support recursive SHACL shapes, and a naive
   `rdf:List`-walking shape blows past its recursion guard almost
   immediately.** SHACL Core doesn't require conformant processors to
   support shape-graph recursion at all. Confirmed two distinct failure
   modes empirically while building `shapes.py`: (a) a `NodeShape` that
   walks an `rdf:List` one `rdf:first`/`rdf:rest` hop at a time via
   self-reference (`sh:node` pointing back at the same shape) burns ~4-5
   units of "path depth" per cons cell, and pyshacl's hard
   `max_validation_depth` guard (tuned for its own `shacl.ttl` meta-shape
   test, not a real data graph) raises `ReportableRuntimeError` on any BGP
   with more than a couple of triples — fixed by rewriting list validation
   as a single `sh:sparql`/`sh:select` constraint instead (constant path
   depth regardless of list length), see `TriplePatternListShape`. (b)
   ~~`salg:GraphPatternShape`'s `sh:or` alternation between operator shapes
   (`Filter`/`LeftJoin`/`Union` each nest another `GraphPatternShape`) is
   *genuine* recursion... Not revisited further since Phase 1 core queries
   don't nest this deep in practice~~ **Superseded by a later session's
   fix — this was a real, live gap, not a deep-nesting-only theoretical
   one.** Reading pyshacl's actual source
   (`constraints/constraint_component.py::recursion_triggers`,
   `trigger_depth=3` default) showed the guard tracks *shape identity* in
   its own evaluation stack, not (shape, focus-node) pairs — it can't
   distinguish a true data cycle from a merely-deep-but-finite tree, and
   `sh:or` trying every alternative (most of which loop back to
   `GraphPatternShape` via `sh:node`) multiplies stack growth per real
   nesting level. Confirmed empirically this fires on very shallow,
   everyday queries, not just deep ones: a plain `SELECT ?x WHERE { ?s :p
   ?y . BIND(STR(?y) AS ?x) }` (4 levels of real nesting) produced a
   "14-22 levels deep" warning. This is exactly how `Extend` (`BIND`'s
   algebra node) went unnoticed as missing from `GraphPatternShape`'s
   recognized-operator list for as long as it did — the old dispatch
   silently gave up before ever checking it, so `conforms: True` for a
   query using an operator the shape graph had never even heard of.
   **Fixed**: `GraphPatternShape`'s `sh:or` alternatives are now `[ sh:class
   salg:BGP ]` etc — `sh:class` (plain type-membership check) instead of
   `sh:node salg:BGPShape` (full recursive shape-conformance, which is
   what pushes onto pyshacl's evaluation stack). Verified directly: zero
   `ShapeRecursionWarning`s for the same queries that previously produced
   dozens, and a genuinely malformed nested `Filter` (missing `salg:expr`)
   is still correctly rejected — each operator's own shape stays a real,
   independent `sh:targetClass`-driven `NodeShape`, validated by pyshacl
   on every matching node regardless of nesting; only the dispatch
   mechanism changed. `ExpressionShape` (see below) uses the same
   technique from the start. `max_validation_depth=100` and
   `ShapeRecursionWarning` suppression stay in `validate()` as
   defense-in-depth, but should no longer be load-bearing for any shape
   built this way.
10. **`SelectQuery.p` is not always a bare `Project` — top-level `LIMIT`/
    `ORDER BY`/`DISTINCT`/`REDUCED` each wrap it in another operator.**
    Confirmed empirically by walking real algebra trees: `SELECT DISTINCT
    ... ORDER BY ... LIMIT n` produces `Slice(Distinct(Project(OrderBy(
    <pattern>))))` at the top level — so `SelectQuery.p` can be `Project`,
    or `Slice`/`Distinct`/`Reduced` wrapping it (in any combination `Slice`
    is always outermost when present, per the SPARQL 1.1 algebra's
    Slice-after-Project ordering). `shapes.py`'s first `SelectQueryShape`
    draft hard-required `salg:p` to be exactly a `salg:Project`
    (`sh:class salg:Project`) — which would have rejected every top-level
    query using any of those four modifiers. Went undetected initially
    because Phase 1's own query set (`test_roundtrip.QUERIES`) never uses
    `LIMIT`/`ORDER BY`/`DISTINCT` at the top level, only inside `OPTIONAL`/
    subqueries. Fixed by introducing `salg:SubSelectShape` (`sh:or` of
    `Project`/`Slice`/`Distinct`/`Reduced`, each of the latter three
    wrapping another `SubSelectShape`) and pointing both
    `SelectQueryShape.p` *and* `ToMultiSetShape.p` (subquery embedding) at
    it — the two positions are structurally identical, since a subquery is
    just a `SelectQuery`'s tree without the outer `salg:Query`/
    `salg:SelectQuery` wrapper. Separately: `OrderBy` does **not** belong
    in this alternation — it wraps the *inner* WHERE pattern
    (`Project.p = OrderBy(p=<pattern>)`), not the `Project` itself, so it's
    registered in `salg:GraphPatternShape`'s `sh:or` instead. Worth
    remembering for any *other* top-level query modifier added later:
    check the real algebra shape empirically before assuming a bare
    operator name is the only valid value at a given position — Phase 1's
    query set alone is not enough to catch this class of gap.
11. **A genuine SPARQL 1.2 algebra tree (real `TripleTerm` nodes, not
    lowered) is achievable with zero rdflib patches — subclass `CompValue`,
    don't substitute an unrelated proxy object, and extend rdflib's own
    grammar in place instead of depending on any text-rewrite pipeline.**
    (See `starsparql/grammar12.py`/`triple_term.py`/`parse12.py`,
    Phase 6.) Three things had to be true together, each confirmed
    empirically, not assumed:
    - rdflib's real SPARQL grammar (`rdflib.plugins.sparql.parser`) is
      genuinely extensible in place: the term-position rules a triple term
      needs to join — `GraphTerm`/`VarOrTerm`/`GraphNode`/`GraphNodePath` —
      are plain `pyparsing.MatchFirst` objects with a public `.append(expr)`
      method, and pyparsing composes grammar rules by object reference, so
      appending a new alternative is visible to every rule built on top of
      it without forking rdflib's grammar module or touching the installed
      package on disk. Confirmed with a real `parseQuery()` call using a
      trivial appended alternative before building the real triple-term
      grammar on top of this assumption.
    - `reorderTriples`/`_knownTerms` (BGP join-order optimization,
      `algebra.py`) require every triple-pattern term to be hashable *and*
      orderable — not just hashable. When two triples tie on
      `_knownTerms`' sort key (common for fully-ground triples), rdflib's
      own `sorted()` call falls back to comparing the raw triples
      element-wise with `<`. A term type with only `__hash__`/`__eq__`
      trades one `TypeError` for a different one (`'<' not supported
      between instances of ...`) the first time two ground triples tie.
    - Substituting a fully-ground `TripleTerm` with some *other* hashable
      object (a proxy, or `starlayergraph.model.triple.TripleTerm` — a value
      type used elsewhere in the sibling project for a different purpose,
      representing an actual RDF *value*, not an algebra node) is **not**
      sufficient even with ordering added, and this was confirmed as a real,
      reproducible defect during development, not just a theoretical risk:
      rdflib's `_addVars`/`analyse` bookkeeping pass is driven by
      `_traverseAgg`, a generic recursive walker closed over
      `CompValue`/`list`/`tuple`/`ParseResults` — nothing else. A
      non-`CompValue` proxy standing in for a triple term makes any
      `Variable` nested *inside* a pattern-with-variables triple term
      invisible to that walk, silently under-computing `_vars` on every
      ancestor node (reproduced directly: a `BGP` containing
      `?stmt rdf:reifies <<( :bob ?p :carol )>>` came out with `_vars`
      missing `p`). Subclassing `CompValue` itself
      (`TripleTermNode(CompValue)`, adding only `__hash__`/`__eq__`/
      `__lt__`) resolves this for free through rdflib's own already-generic
      machinery — no patch needed, because `_traverseAgg` already knows how
      to recurse into a `CompValue`, and `TripleTermNode` *is* one.
    Net effect: `starsparql.parse12.prepare_query_12`/
    `prepare_update_12` call rdflib's real, completely unmodified
    `translateQuery`/`translateUpdate` and get back a real algebra tree with
    first-class `TripleTermNode`s in it, correct `_vars` included. This
    phase's scope deliberately stops there, though — see the Phase 6 status
    entry above for what's still explicitly deferred (making the tree
    directly *executable*).
12. **A triple term's subject position needs grammar rules built from
    independent primitives, not a reference to the same mutable grammar
    object the new triple-term alternative gets appended into — or nesting
    silently becomes legal where RDF 1.2 forbids it.** Found as a real bug
    during development, not anticipated in advance: an earlier version of
    `grammar12.py` defined the triple term's own subject slot as
    `_TripleTermSubject = VarOrTerm` — but `VarOrTerm` is exactly one of the
    four objects `grammar12.install()` mutates in place to add the new
    `<<( )>>`/`TRIPLE()` alternative, so once installed, a query like
    `<<( <<( :a :b :c )>> :p :o )>>` (a nested triple term used as the
    *outer* triple term's subject — illegal per RDF 1.2, which restricts
    nesting to object position only) parsed successfully instead of being
    rejected. Fixed by building the subject slot from rdflib's lower-level
    term primitives directly (`Var | iri | BlankNode`) instead of the
    mutable composite `VarOrTerm`/`GraphTerm` objects. The equivalent SHACL
    shape (`salg:TripleTermShape`'s `subject` property) had the same class
    of bug for a different reason — its `SubjectOrVariableShape` dependency
    accepted *any* blank node, which doesn't distinguish an ordinary
    blank-node term from a blank node that's structurally the root of a
    `salg:TripleTerm`; fixed by adding `sh:not [ a salg:TripleTerm ]` to
    that shape's blank-node alternative. Both were caught by writing a
    negative test *for the specific restriction* (a query/graph that should
    be rejected) rather than only positive round-trip tests — worth
    repeating as a lesson for any future position-specific restriction in
    this vocabulary: a positive round-trip test proves valid input works, it
    doesn't prove invalid input is actually rejected.
13. **rdflib's `algebra._traverse` stops recursing into a node's *children*
    the instant its `visitPre` callback returns non-`None` — a real trap
    for any new `_AlgebraTranslator` branch whose argument can itself be an
    unresolved placeholder.** Not documented anywhere in `algebra.py`
    itself; found as a genuine, reproducible bug while adding
    `serialize12.py`'s `Builtin_isTRIPLE`/`SUBJECT`/`PREDICATE`/`OBJECT`
    branches. Mirroring the `ServiceGraphPattern`/`TripleTerm`/`BGP`/
    `TriplesBlock` branches' own convention of `return node` at the end
    seemed like the obviously-consistent thing to do — but those four are
    all self-contained (they never leave a child's placeholder unresolved,
    either because they have no CompValue children at all, or because they
    explicitly re-invoke `traverse` themselves, per the `ServiceGraphPattern`
    precedent). A builtin's own argument, by contrast, can be *any*
    `Expression` — including another `TripleTermNode` (e.g.
    `PREDICATE(TRIPLE(:a,:b,:c))`) — and `convert_node_arg` inserts a bare
    `"{TripleTerm}"` placeholder for it exactly the way it does for any
    other `CompValue` argument, which needs `_traverse`'s own later
    per-child recursion to resolve, the same way the `Extend`/`Project`
    branches' own nested placeholders always have. Returning `node` early
    silently skips that later visit, leaving literal, unresolved
    `"{TripleTerm}"` text in the final output — confirmed by tracing every
    `_replace` call in sequence (`traverse(..., visitPre=<traced wrapper>)`)
    rather than guessing from re-reading the code, after the first fix
    attempt still produced broken output. Fixed by *not* returning early in
    the `Builtin_*` branch specifically — the correct convention turns out
    to be: return early (self-contained) only when the branch's own logic
    has already fully resolved every placeholder it introduced; fall
    through (implicit `None`) whenever a child might still need its own
    independent visit, matching what literally every base-class builtin
    branch already does.
14. **`_AlgebraTranslator` has zero `ConstructQuery` handling at all — not
    "less tested," genuinely absent — and building a working one surfaced
    two more non-obvious pitfalls, both found only by testing against real
    `StarLayerGraph` execution, not by reading `algebra.py`'s source.**
    Confirmed first: `self._alg_translation` (the whole mechanism's output
    buffer) is *only* ever seeded by the `SelectQuery` branch — no other
    query form gets so much as an empty-string starting template, which is
    why `translateAlgebra` silently returns `""` for a plain 1.1 CONSTRUCT
    query with zero triple terms involved. A new `ConstructQuery` branch in
    `serialize12.py` closes this (a genuinely new capability, not a patched
    existing one) — but two things had to be found by trial against a real
    engine, not guessed from the algebra shape alone: (a) `ConstructQuery.p`
    is a `Project` whose `PV` field, for CONSTRUCT specifically, means
    "variables the template needs projected out of the pattern" — internal
    bookkeeping, never meant to be printed as text — but the base class's
    own `Project` branch doesn't know that distinction and always renders
    `PV` as a SELECT-style variable list, which for CONSTRUCT produced a
    stray `?x` sitting directly between `WHERE` and `{`, invalid syntax;
    fixed by referencing `node.p.p` (the pattern *inside* `Project`)
    directly, bypassing `Project`'s own branch entirely. (b) Separately, a
    naive `"{" + node.p.p.name + "}"` (single braces) let the pattern's own
    branch consume the *literal* surrounding braces along with its
    placeholder, since a bare `"{BGP}"` is indistinguishable from the
    placeholder itself — produced `WHERE <iri> <iri> ?x.` with no braces at
    all; fixed by using `Project`'s own double-brace convention
    (`"{{" + name + "}}"`), where only the *inner* `"{Name}"` is the
    placeholder and the *outer* literal `{`/`}` survive. (c) The literal
    `WHERE` keyword, though genuinely optional per the SPARQL grammar itself
    (`WhereClause = Optional(Keyword("WHERE")) + ...`, confirmed by reading
    rdflib's parser.py, and this project's SELECT serialization has always
    omitted it without issue) turned out to be *required* for compatibility
    with *starlayergraph's* `sparql12_to_11.py` rewriter specifically — a
    regex-based, non-full-grammar-parsing tool by its own docstring,
    confirmed to fail on a WHERE-less CONSTRUCT even though plain rdflib
    re-parses that exact same text without complaint. None of (a)/(b)/(c)
    were visible from a successful `prepare_query_12(regenerated_text)`
    re-parse check alone — every one only surfaced once the regenerated
    text was actually executed against a real `StarLayerGraph`, which is
    why `test_phase6_serialize12.py`'s execution-based tests (not just the
    reparse-only ones) are load-bearing, not redundant, for this project's
    stated verification standard.
15. **Annotation/reification-shorthand syntax needs grammar splice points
    with a genuine side effect (minting extra sibling triples), not just a
    value — and the *right* splice point differs by form.**
    `s p o ~ r` and `s p o {| ... |}` are whole-*statement* forms (always
    trail a complete base-triple statement) — these two stay spliced into
    `TriplesSameSubjectPath`/`TriplesSameSubject` directly, as originally
    built. `<<s p o>>`/`<<s p o ~ r>>`, though, turned out (via real W3C
    test data — `[ ?Q <<:s ?P :o>> ] :b :c .`, `( <<?S1 :p :o1 ~ :iri>>
    ... )`, `<< ?s ?p ?o >> .` as a bare statement) to need to work as an
    ordinary *term*, usable anywhere: subject, object, inside `[...]`,
    inside `(...)`. A **first attempt** built these as whole-statement
    productions requiring `<<s p o>> pred obj` as one fixed shape — too
    narrow, since none of those real usages fit that shape. The **corrected
    design**: rdflib's `expandTriples` (the parse action already bound to
    `TriplesSameSubjectPath`/`TriplesSameSubject`) has generic
    `isinstance(t, list)` handling for exactly this "value with side-effect
    triples" case — it's what already makes `[ p o ]` (`expandBNodeTriples`)
    and `( a b c )` (`expandCollection`) work as bare statements, ordinary
    objects, *and* nested inside each other, all via ONE splice point:
    `TriplesNode`/`TriplesNodePath` (`Forward` objects wrapping a real
    `MatchFirst` at `.expr`, itself `.append()`-able) — which already sits
    under `GraphNode`/`GraphNodePath` *and* under
    `TriplesSameSubject(Path)`'s own `TriplesNode(Path) + PropertyList(Path)`
    alternative. Splicing the two `<<...>>` reifier-term productions into
    `TriplesNode.expr`/`TriplesNodePath.expr` (not `GraphTerm`/`VarOrTerm`
    directly, and not `TriplesSameSubject(Path)` directly either) gets
    "ordinary object", "bare whole-statement subject", and "nested inside
    `[...]`/`(...)`" all at once, for free, mirroring the *existing*
    mechanism instead of inventing a new one.

    **The nested-list shape has a real invariant, confirmed by tracing
    `expandTriples`'s source, not guessed:** a returned `[value, *extra]`
    must have `value` appear *only once* — as the natural first element of
    `extra`'s first embedded triple — never as a separately prepended
    duplicate. `expandBNodeTriples` achieves this by literally prepending
    the bnode as the *subject* before re-running `expandTriples` on the
    property list (`[expandTriples([BNode()] + pairs)]`), so the bnode
    doubles as both the returned value and the subject of every resulting
    triple. The reifier-term parse action does the analogous thing
    directly: `[r, RDF.reifies, tt] + _reify(tt, s, p, o)` — `r` (the
    value) is literally the subject of the first triple in the list, not a
    separate `[r] + [r, RDF.reifies, tt] + ...` duplicate. Got this wrong
    on the first attempt (duplicated `r`) and it surfaced immediately and
    concretely: `algebra.triples()` raises `Exception("these aint
    triples")` when the flat list length isn't a multiple of 3 — a
    duplicated `r` makes it 13 elements instead of 12, an unambiguous
    signal, not a silent semantic error.

    **Real bug found and fixed while building the (superseded) first
    attempt, still relevant to the two whole-statement forms that remain
    installed the original way:** appending new alternatives to
    `TriplesSameSubjectPath`/`TriplesSameSubject` (rather than inserting at
    front) silently broke *every* ordinary triple pattern, not just the new
    syntax. Confirmed why: the *existing* `VarOrTerm +
    PropertyListPathNotEmpty` alternative greedily matches just `s p o` and
    succeeds — pyparsing's `MatchFirst`/`|` is first-match-wins in listed
    order, not longest-match — so it always won before a later-listed
    alternative was ever tried, leaving a dangling `~ r`/`{| ... |}` suffix
    that then failed at the *statement* level instead of being recognized
    by the new production at all. Fixed by inserting new alternatives at
    position 0 (`.exprs.insert(0, ...)`, not `.append()` — confirmed via
    reading pyparsing's own `ParseExpression.append()` source that it's
    just `self.exprs.append()` + a `_defaultName` reset, safe to do the
    equivalent with `.insert(0, ...)` instead), so they're tried *before*
    the ordinary alternative.

    **Subject/predicate/object of a `<<...>>` reifier term have three
    *different* legal grammars, not one shared one — confirmed by real
    negative and positive W3C tests, not assumed by symmetry with the
    ground `<<( s p o )>>` term:** predicate is `Var | iri` only — same as
    the ground triple term's `_TripleTermPredicate` — confirmed by the
    negative test `bnode-predicate-anonreifier` (`<<?s [] ?o>> ?p2 ?o2 .`
    must be rejected). Subject and object, though, stay plain `VarOrTerm`
    — deliberately *more* permissive than the ground triple term's own
    `_TripleTermSubject` (which excludes anonymous `[]`, only
    `BLANK_NODE_LABEL`/`_:x` — confirmed by the negative test
    `bindbnode-tripleterm`, `BIND(<<( [] ?p ?o )>> AS ?t)` must be
    rejected) — confirmed by the *positive* test `subject-tripleterm`,
    which uses `<<[] ?R :z ~ :iri>>` (an anonymous blank-node subject) and
    regressed when `_TripleTermSubject` was tried there first. One
    open, unresolved gap surfaced by the same test family (not fixed this
    session, see "Not started"): a `<<...>>` reifier term's subject/object
    can themselves be *another* `<<...>>` reifier term or a nested ground
    triple term (`<<( <<(?S :p :o)>> :r :z )>>`) — currently unreachable,
    since the reifier term's subject/object are plain `VarOrTerm`, which
    doesn't include the `TriplesNode`-spliced forms.
16. **rdflib's own SPARQL query *parser* fails to re-parse text its own
    algebra-to-text output can produce, given a specific blank-node
    adjacency — a real, pre-existing rdflib bug, confirmed independent of
    this project's grammar work.** Minimal repro (plain rdflib, no
    `grammar12.install()` involved at all): `prepareQuery("SELECT * {_:y
    <http://ex/p1> _:x._:x <http://ex/p2> <http://ex/o2>.}")` raises
    `ParseException` at the second `_:x`; inserting a single space
    (`_:x. _:x`) fixes it. Root cause: `algebra.py`'s own `BGP` branch
    (`sparql_query_text`) joins per-triple text with `"".join(...)` and no
    separator at all — `triple[0].n3() + " " + triple[1].n3() + " " +
    triple[2].n3() + "."`, zero trailing space — so a triple ending in a
    blank-node object immediately followed by a triple starting with a
    blank-node subject collide with no whitespace between them, and
    something in `BLANK_NODE_LABEL`'s tokenization (plausibly greedy-then-
    backtrack behavior around the trailing `.`) can't recover. This
    project's `serialize12.py` had copied that same zero-separator
    convention into its own `_triples_text` helper (needed there instead of
    reusing the base class's BGP branch outright, to handle
    `TripleTermNode` rendering) — invisible in Phases 1–6's own hand-written
    test queries (rarely produce back-to-back blank-node-object/blank-node-
    subject triples), but annotation syntax's reification triples
    (`rdf:subject`/`predicate`/`object`/`reifies`, blank-node-heavy by
    construction) hit it constantly once regenerated through the W3C
    harness. **Fixed** in `_triples_text` (`serialize12.py`) by adding a
    trailing space after each triple's `"."` — a one-token change, since
    this project owns its own serializer and doesn't need to patch rdflib
    itself. Previously misdiagnosed (before finding the actual root cause)
    as "starlayergraph's own Turtle parser rejecting nested `<<...>>` data
    syntax" while triaging W3C harness failures — worth remembering that a
    failure surfacing while executing *regenerated* query text can originate
    in this project's own serializer, not just in the execution backend.
17. **The W3C harness's `test_eval_select`/`test_eval_construct` had a real
    bug of their own, separate from anything in `grammar12.py`/
    `serialize12.py`: every data fixture was parsed with a hardcoded
    `format="turtle12"`, regardless of the fixture's actual file
    extension.** `StarLayerGraph.parse`'s `format=` isn't resolved via
    rdflib's plugin registry for any RDF-1.2-aware format (confirmed:
    `'turtle12'`/`'trig12'`/etc. aren't registered `Parser` plugins at all)
    — it's a bespoke dispatch inside `StarLayerGraph.parse` itself, with a
    genuinely different parser per RDF *syntax*, and TriG's `GRAPH { }`
    blocks are not valid Turtle. Confirmed empirically: a real `.trig`
    fixture (`data-4.trig`, using `GRAPH :g { ... }`) raised a real
    `TurtleSyntaxError` ("unexpected trailing content") when parsed as
    `'turtle12'`, and parsed cleanly as `'trig12'`. **Fixed** by mapping
    file extension → format (`.ttl`→`turtle12`, `.trig`→`trig12`,
    `.nq`→`nq12`, `.nt`→`nt12`) in `test_w3c_sparql12.py`'s new
    `_data_format()` helper. This resolved some, but not all, of what had
    been bucketed under "starlayergraph's own Turtle parser rejecting nested
    syntax" when failures were first triaged — see finding #18 for the
    part of that bucket that's real.
18. **A genuinely external, confirmed-real gap: starlayergraph's own Turtle
    parser (`starlayergraph/parsers/turtle_parser.py`, the sibling
    `starlayergraph` repo — not this project) rejects the `~ reifier`
    annotation shorthand when it appears in Turtle/TriG *data*, as opposed
    to SPARQL *query* text (which goes through this project's own
    `grammar12.py`, a completely separate codebase).** Root-caused (not
    just observed) via direct reproduction:
    `StarLayerGraph().parse(data=..., format='turtle12')` on the W3C
    suite's `data-2.ttl` (used by the `pattern-1` eval test, contents
    include `<<:s :p2 :o ~ :reifier2>>`) raises `TurtleSyntaxError` from
    `turtle_parser.py`'s `_norm_qt`: `"too many terms inside
    <<...>>/<<(...)>> - expected exactly subject, predicate, object, found
    extra '~ :reifier2'"` — `_norm_qt` doesn't know about the `~ reifier`
    suffix at all, only the bare `<<( s p o )>>` ground-triple-term form.
    Out of this project's control without patching the other repo; not
    attempted here. Separately (not yet investigated as deeply, likely a
    distinct harness gap rather than a `grammar12.py`/`serialize12.py` one):
    `graphs-1`/`graphs-2` (both using `data-4.trig`, which defines named
    graphs) fail with `"You performed a query operation requiring a
    dataset (i.e. ConjunctiveGraph), but operating currently on a single
    graph"` — `StarLayerGraph()` as constructed by the harness isn't a
    multi-graph dataset, so a `GRAPH ?g { }` query pattern against
    genuinely-named-graph data can't work regardless of query-text
    correctness; the harness would need a dataset-capable construction path
    for `.trig`/`.nq` fixtures specifically.
19. **A `<<...>>` reifier term's subject/object needed to accept another
    reifier term or a nested ground triple term, closing the gap finding
    #15 left open.** `_AnnotationReifierTermAnon`/`Explicit`'s subject and
    object slots were plain `VarOrTerm` — too narrow, confirmed via
    `nested-reifier-02`/`nested-anonreifier-*` (a reifier term's *object*
    is another reifier term) and `subject-tripleterm` (a reifier term's
    *subject* is a nested ground triple term). Fixed with a new, narrowly-
    scoped `Forward` (`_ReifierTermValue <<= VarOrTerm |
    _AnnotationReifierTermExplicit | _AnnotationReifierTermAnon`) — **not**
    `GraphNode`, which was tried first and let a bare `(...)` Collection or
    `[...]` BlankNodePropertyList through too (both live on the *same*
    shared `TriplesNode.expr` object `GraphNode` pulls in), confirmed as a
    real regression via the negative tests `quoted-list-subject-*`/
    `quoted-list-object-*`/`quoted-list-predicate-*`. A match against this
    Forward comes back as either a plain term or the same nested-list shape
    a reifier term already produces — `_expand_value` (finding #15's own
    mechanism) unwraps both uniformly.
20. **The ground triple term's "no anonymous `[]`, no nested triple term"
    subject restriction (added in finding #15, following the negative
    tests `bindbnode-tripleterm`/`bnode-predicate-anonreifier`) turned out
    to hold only in *expression* position, not ordinary *pattern*
    position — a real, shipped bug in the original fix, not a hypothetical
    edge case.** Confirmed by directly contrasting: `bindbnode-tripleterm`
    (`BIND(<<( [] ?p ?o )>> AS ?t)`) and `tripleterm-subject-03`
    (`BIND( <<( <<(:s :p :o )>> :q :z )>> AS ?X )`) must both be *rejected*
    — but `bnode-tripleterm-03` (`<<([] :p [] )>> :q :z .`) and
    `nested-tripleterm-02`/`compound-tripleterm-subject` (the identical
    shapes, in ordinary triple-pattern position) are *positive* tests
    requiring exactly what the BIND versions reject. One shared grammar
    object can't enforce two different rules depending on where it's
    spliced in. Fixed by building two genuinely separate pairs of `Comp`
    objects — `TripleTermExpr`/`TripleTermCall` (pattern position,
    permissive: `Var | iri | BlankNode | TripleTermObject`) and
    `TripleTermExprValue`/`TripleTermCallValue` (expression/`VALUES`
    position, restrictive: `Var | iri | BLANK_NODE_LABEL`) — rather than
    one shared `_TripleTermSubject` installed into both extension points,
    which is what the original fix did.

    **⚠️ This finding's core conclusion — that a nested triple term is
    legal as another triple term's subject in pattern position — was
    wrong. Superseded by finding #27.** The grammar change described above
    (widening `_TripleTermSubjectPattern` to include `TripleTermObject`)
    is real and stays reverted-in-spirit-but-not-in-code: see finding #27
    for why the grammar itself was deliberately left permissive (it still
    parses `nested-tripleterm-02`/`compound-tripleterm-subject`, matching
    their `PositiveSyntaxTest` label) while a new, separate semantic check
    (`InvalidTripleTermError`) now rejects the construct at `TripleTermNode`
    construction time regardless. The specific error this finding's fix
    avoided (`bindbnode-tripleterm`/`tripleterm-subject-03` needing
    rejection) is still correctly rejected — that part was never in
    question, only the treatment of `nested-tripleterm-02`/
    `compound-tripleterm-subject` as *requiring* acceptance was wrong. Root
    cause of the original error: conflating "the W3C suite labels this
    `PositiveSyntaxTest`, so SPARQL's grammar accepts it as text" with
    "this represents a valid RDF 1.2 term" — confirmed wrong by reading
    the actual RDF 1.2 Turtle grammar directly (`ttSubject ::= iri |
    BlankNode`, no `tripleTerm` alternative, unconditionally — not scoped
    to expression position). `bnode-tripleterm-03` (also cited above as
    supporting evidence) was never actually evidence for the nested-term
    claim at all — re-reading its actual text (`<<([] :p [] )>> :q :z .`)
    shows it only exercises anonymous `[]` as `ttSubject`, which the real
    grammar already permits (`BlankNode` includes `ANON`); it doesn't
    touch nesting.

    Separately, in the same pass: `TRIPLE(s, p, o)`'s three arguments are
    full `Expression`s per spec 17.4.6, not just terms — confirmed via
    `expr-tripleterm-04` (`BIND(TRIPLE(?s, ?p, str(?o)) AS ?t2)`, a
    function-call third argument). Widened `TripleTermCallValue`'s three
    `Param`s to `Expression` (a strict superset of a plain term, so no
    regression risk) — deliberately **not** applied to `TripleTermExprValue`
    (`<<( s p o )>>`): the two spellings are described as equivalent for
    the *ground* case, but only `TRIPLE()` is unambiguously function-call/
    expression-level; no test exercises or implies a full expression
    argument for the bracket form.
21. **A real `TripleTermNode` sort-key bug, found via `compound-tripleterm-
    subject`: comparing two ground triple terms where one has a nested-
    triple-term subject and the other doesn't raised `TypeError: '<' not
    supported between instances of 'tuple' and 'str'`.** Root cause:
    `triple_term.py`'s module-level `_sort_key(value)` helper returned a
    raw nested *tuple* for a nested `TripleTermNode` value
    (`value._sort_key()`) but a plain *string* for anything else
    (`repr(value)`) — type-inconsistent depending on whether that specific
    slot happened to be nested. When rdflib's `reorderTriples`/
    `_knownTerms` tie-breaks two sibling ground triple terms by comparing
    raw triples slot-by-slot with `<`, and one triple's subject-slot key is
    a tuple while the sibling's is a string (because only one of them
    nests), the comparison itself raises. Fixed by always wrapping the
    nested case in `repr(...)` too, so every slot's key is unconditionally
    a plain string regardless of nesting depth — comparisons can no longer
    mix types.
22. **The `~ r`/`{| |}` annotation-suffix forms needed to combine on one
    statement, and repeat — not just work individually — confirmed via
    real W3C test data, not merely a generalization for its own sake.**
    `annotation-reifier-01` (`?s ?p ?o ~ :iri {| :r ?Z |} .`) requires both
    on the *same* base triple, sharing the *same* reifier (`~ :iri`
    names it; `{| |}`'s own annotation triples attach to that same named
    reifier, not a separately-minted one). The `annotation-*-multiple-*`
    family requires *repeated* suffixes too (`~ r1 {| |} ~ r2 {| |}`),
    each independently reifying the *same* underlying triple term. Rebuilt
    `AnnotationReifierBinding`/`AnnotationBlock` (two separate, mutually-
    exclusive productions) as one combined grammar, cross-checked against
    (not ported from) the sibling `starlayergraph` repo's own
    `split_obj_and_annotations` (`starlayergraph/parsers/lexer.py`), which
    already implements the identical shape for Turtle *data* — a working
    reference for the semantics (per direct instruction to check it),
    confirming e.g. that a bare `~` immediately followed by `{| |}` means
    "anonymous reifier with this annotation block", not two separate
    suffixes. Also widened the base triple's own subject/object in this
    rebuilt production from `VarOrTerm` to `_ReifierTermValue` (finding
    #19's Forward) — confirmed necessary via `annotation-anonreifier-03`
    (`:s :p <<:a :b :c>> {| ?q ?z |}`, whose base triple's *object* is
    itself a bare reifier-shorthand term).

    **A second QuadData-shaped negative test surfaced by this fix, not
    newly introduced by it:** `syntax-update-anonreifier-01`
    (`DELETE { ?s :r ?o {| :added '...' |} } WHERE {...}`) is the same
    class of gap as finding #15's `syntax-update-anonreifier-02` (a
    DELETE template minting a fresh blank-node reifier, which SPARQL
    Update forbids for DELETE templates the same way it forbids blank
    nodes in `QuadData`) — previously masked because the old, narrower
    grammar simply couldn't parse `{| :q1+ 'ABC' |}` at all (no `Path`
    support yet), so this test happened to fail for an unrelated reason
    before. Same deferred status as `-02` at the time — **both resolved in
    a later session, see finding #26**.
23. **An annotation pair's predicate needed real SPARQL property-path
    support (`{| :r/:q 'ABC' |}`, `{| :r [ :p1|:p2 'ABC'] |}`,
    `{| :q1+ 'ABC' |}`), confirmed via
    `annotation-anonreifier-06`/`-07`/`annotation-reifier-06`/`-07`/
    `update-reifier-07` — but needed it *only* in ordinary WHERE-clause
    context, not CONSTRUCT-template context, for a sharper reason than
    "the SPARQL grammar disallows paths in CONSTRUCT templates" (true,
    but not the actual failure mode hit here).** First widened uniformly
    to `Path` alone — regressed the far more common plain-variable-
    predicate case (`{| ?Y ?Z |}`) immediately, since `Path`'s own grammar
    has no `Var` alternative (rdflib's own `PropertyListPathNotEmpty`
    combines `VerbPath | VerbSimple` = `Path | Var` for exactly this
    reason — mirrored here). Even after fixing that, CONSTRUCT-template
    annotation pairs still broke — on a *trivial*, non-path predicate like
    plain `:source`, no `/`/`|` at all — with `TypeError: cannot use
    CompValue as a set element`. Root-caused (not guessed) by reading
    `translateQuery`'s own source: a trivial single-IRI match through
    `Path`'s grammar parses as a nested `PathAlternative`/`PathSequence`/
    `PathElt` CompValue chain, not a bare `URIRef` — ordinary WHERE clauses
    get this cleaned up via `traverse(q.where, visitPost=translatePath)`,
    confirmed empirically (`{| :source ?g |}` in a plain `SELECT`'s WHERE
    clause produces a bare `URIRef` predicate after `prepare_query_12`) —
    but `translateQuery`'s CONSTRUCT-template branch
    (`template = triples(q[1].template)`) builds directly from the raw
    parse tree, confirmed via reading the source to *never* run that same
    `translatePath` walk over template triples at all. Since plain rdflib
    itself never permits real path syntax in a CONSTRUCT template to begin
    with (confirmed: `CONSTRUCT { ?s :r/:q ?o } WHERE {...}` raises a
    `ParseException` in unmodified rdflib), this gap was previously
    unreachable in vanilla SPARQL — only reachable here because this
    project's own annotation-pair grammar was the first thing to ever put
    a `Path`-matched term in a CONSTRUCT template's predicate slot at all.
    Fixed by parameterizing `_build_annotation_suffixed` on the predicate
    grammar too (not just the value grammar, per finding #22): `Path | Var`
    for the WHERE-clause variant, plain `VarOrTerm` (no `Path` at all) for
    the CONSTRUCT-template variant — not a workaround, a correct
    reflection of the real, confirmed rule.
24. **Open, deliberately undecided (not a bug fix, a tracked gap): an empty
    collection `()` (`rdf:nil`) as a triple term's/reifier term's own
    *object* is accepted by this project's grammar, but the two W3C
    `NegativeSyntaxTest` fixtures that exercise it (`list-anonreifier-01`,
    `list-tripleterm-01`) expect it to be *rejected*.** Both fixtures'
    actual content is `<< _:b ex:x () >> ex:broken true .`/
    `<<( _:b ex:x () )>> ex:broken true .` - and, notably, the fixture text
    itself carries a `# TODO: See if this should be throwing an error`
    comment immediately above that line, i.e. the W3C test suite's own
    authors were not certain this should be a negative test either. This
    surfaced as a side effect of widening `_TripleTermPredicate` to accept
    `a` (finding needed for `triple-on-triple-terms`/`<<(:x a :z)>>`) -
    before that fix, both fixtures already failed to parse for an unrelated
    reason (the `a` predicate a few lines earlier in each file), so this
    specific `()`-as-object question was never actually reached. Confirmed
    current behavior directly:
    `prepare_query_12(open('.../list-anonreifier-01.rq').read())` parses
    successfully for both, when the fixture expects a parse failure.
    Deliberately not fixed: given the spec ambiguity the fixture's own
    comment documents, rejecting empty-collection-as-object risks being
    *wrong* in the other direction (over-restricting valid syntax) without
    a clearer signal from the spec or a resolved version of the W3C test
    itself - tracked here rather than guessed at.
25. **The cross-test state-leak bug flagged as unresolved in the Phase 7
    status entry above was a real, deterministic import-order hazard in
    this project's own `__init__.py` — not a pytest/pyparsing mystery, and
    not caused by anything specific to the query being evaluated.** Root
    cause: `from_rdf.py` computes `_EXPR_EVALFNS` (a snapshot of rdflib's
    live parser grammar, via `_discover_expr_evalfns()` walking
    `rdflib.plugins.sparql.parser`) **at import time**. `parse12.py` calls
    `grammar12.install()` — which mutates those same shared, global
    grammar objects in place, splicing in SPARQL 1.2 productions — **also
    at import time**. If anything imports the bare `starsparql`
    package (which pulls in `from_rdf.py`) *before* anything imports
    `parse12`, later query evaluation silently corrupts — confirmed with a
    minimal, deterministic repro **outside pytest entirely** (a plain
    Python script: `import starsparql` alone, then evaluate the W3C
    fixture `op-2` via `lower_rdf11.rdf11_to_query` — returns 0 rows
    instead of the correct 3, reproducible every single time, unlike the
    original `ParseException`-at-a-bogus-offset symptom, which never had a
    non-pytest repro). Bisection method worth remembering for a similar
    future hunt: reproduce via the real pytest CLI first (confirms it's
    real), then replay the *exact same sequence of imports/calls* in a
    bare Python script outside pytest — the first attempt at this got a
    false "it reproduces standalone" signal from a script bug (forgot to
    load the test fixture's data file, so an *unrelated* empty-graph result
    looked like the same failure) and a false "it doesn't reproduce"
    signal right after fixing that (the corrected script happened to
    import `test_lower_rdf11` *before* the code under suspicion, the
    opposite order from what pytest actually does when collecting files
    alphabetically) — both were real lessons about matching the reproduction
    script's import order exactly to pytest's collection order, not just
    matching which modules get imported. Confirmed this predates the
    session that found it: `tests/test_adversarial_roundtrip.py`
    (pre-existing, not new) imports in exactly the corrupting order
    (`from starsparql import query_to_rdf, rdf_to_query` before
    `from starsparql.parse12 import prepare_query_12`) — it simply
    never fired in practice because that file has been excluded from every
    run this project's life so far (needs a live Oxigraph server); a new
    file added the same session (`tests/test_ast_ontology.py`, alphabetically
    early, no Oxigraph dependency) tripped the same latent wire, which is
    what surfaced it. **Fixed structurally**, not by patching the specific
    symptom: `starsparql/__init__.py` now imports `parse12` first,
    before anything else in the package, so `grammar12.install()` always
    completes before any other code here can observe the grammar —
    `install()` is documented idempotent, so forcing it first is safe
    regardless of whether a caller also imports `parse12` directly later.
    Verified stable (byte-identical pass/fail results) across many repeated
    full-suite runs after the fix, which was not true before it.
26. **A blank node (explicit `_:x`, or minted implicitly by an anonymous
    `{| ... |}` annotation reifier — see finding #15's `_reify`) inside
    `DELETE DATA`'s `QuadData` or a `Modify`'s `DELETE` template needed to
    be rejected, closing `syntax-update-anonreifier-01`/`-02` (left open
    by findings #15/#22).** The grammar-redesign approach both of those
    findings flagged as the only path forward (a structurally separate,
    ground-only `TriplesSameSubject` variant just for `QuadData`) turned
    out not to be necessary — this is a *semantic* restriction (deleting
    requires matching a specific, already-existing term, and a blank node
    can never identify one), not something the context-free grammar itself
    needs to enforce. Implemented instead as a small post-`translateUpdate`
    check (`parse12._reject_blank_nodes_in_delete`/`_check_no_blank_nodes`):
    walk `DeleteData.triples`/`.quads` and, for a `Modify` operation whose
    `.delete` is not `None` (confirmed empirically `Modify.delete` is
    `None` for an INSERT-only `Modify`, via `algebra.translateUpdate1`),
    `Modify.delete.triples`/`.quads`, and raise if any term is a `BNode`.
    Confirmed both fixtures' actual triggering shape directly before
    writing the check, not assumed: `syntax-update-anonreifier-02`'s
    `DELETE DATA { :s :p :o1 {| :added 'Test' |} }` produces a real `BNode`
    in `DeleteData.triples` (the annotation's anonymous reifier);
    `syntax-update-anonreifier-01`'s
    `DELETE { ?s :r ?o {| :added '...' |} } WHERE {...}` produces the same
    shape inside `Modify.delete.triples`. `InsertData` is deliberately
    *not* checked — blank nodes are legal there per spec (scoped to the
    single request); only `DeleteData` and `Modify.delete` are restricted.
27. **Finding #20's core conclusion was wrong: a triple term is never legal
    as another triple term's own subject (or predicate), full stop — not
    just "in expression position." A real bug in this project's own
    grammar, not an Oxigraph bug, despite starting out looking like one.**
    Full chain, worth recording since every step of it was a genuine trap:

    Started by writing up what looked like a real Oxigraph bug (a query
    with a nested-subject triple term pattern, e.g. `?s ?p <<( <<( :a :b
    :c )>> :d :e )>> .`, returns `HTTP 500` from a live Oxigraph 0.5.9
    instance even when matching data has been loaded — confirmed via a
    minimal, dependency-free `curl` reproduction). The write-up leaned on
    finding #20's own claim (nested-subject is legal in pattern position)
    plus the W3C SPARQL 1.2 suite's own `PositiveSyntaxTest` label on
    `compound-tripleterm-subject`/`nested-tripleterm-02` as evidence this
    was genuinely valid RDF 1.2 that Oxigraph was incorrectly rejecting —
    distinct from an *earlier*, already-investigated-and-declined Oxigraph
    finding (recorded in the sibling `starlayergraph` repo's
    `docs/fuseki-upstream-issues.md`, Issue 1's "Status" section) that had
    been judged "a query that can never match real data either way," not
    worth reporting.

    User pushback (recalling that earlier declined finding) prompted going
    to the actual RDF 1.2 Turtle spec grammar directly
    (`https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm`)
    instead of trusting either project's notes:

    ```
    tripleTerm ::= '<<(' ttSubject verb ttObject ')>>'
    ttSubject  ::= iri | BlankNode
    ttObject   ::= iri | BlankNode | literal | tripleTerm
    ```

    `ttSubject` has no `tripleTerm` alternative at all, unconditionally —
    no carve-out for query-pattern vs. expression position. The error in
    the original write-up (and in finding #20 before it): conflating
    "SPARQL's grammar successfully parses this text" (which a
    `PositiveSyntaxTest` label most plausibly asserts) with "this
    represents a valid RDF 1.2 term" (a separate claim `ttSubject` directly
    contradicts). A pattern using this shape can never match any valid RDF
    1.2 data, since no such data could ever exist — the same reasoning the
    earlier declined Oxigraph finding already used. This collapsed into
    being the same case, not a new one — the write-up was retracted (see
    the sibling repo's `docs/oxigraph-upstream-issues.md`, Issue 1, kept
    in full with the retraction rather than deleted, specifically so this
    trap doesn't get rediscovered and re-written in a future session).

    A second, real correction happened *during* the retraction itself:
    re-citing `subject-tripleterm` (one of the fixtures finding #20 used as
    supporting evidence) without re-reading its actual text conflated two
    genuinely different constructs. Verified by reading the raw `.rq` files
    directly rather than trusting prose paraphrase (including this
    project's own): `nested-tripleterm-02`/`compound-tripleterm-subject`
    really do use the ground triple term form (`<<( s p o )>>`, with
    parens) nested inside another ground triple term's own subject slot —
    genuinely the `ttSubject` violation. `subject-tripleterm`, though, uses
    the *reifier-shorthand* form (`<<s p o>>`/`<<s p o ~ r>>`, no parens)
    throughout — a reifier resolves to an ordinary node, not a triple term
    (see finding #15's own distinction), so a nested ground triple term
    inside a *reifier* term's own s/p/o slots is a different question
    (finding #19's territory) from a ground triple term nested inside
    *another ground triple term's* `ttSubject` — conflating the two while
    citing evidence is exactly how the original, wrong widening happened in
    the first place. `bnode-tripleterm-03` (also cited by finding #20)
    turned out on direct re-reading to not even be about nesting at all —
    it only exercises anonymous `[]` as `ttSubject`, which `BlankNode`
    (including `ANON`) already legitimately permits.

    **Fixed** — deliberately *not* by tightening the grammar itself, which
    stays permissive (`_TripleTermSubjectPattern` in `grammar12.py` is
    unchanged, still includes `TripleTermObject`) so parsing still matches
    what the W3C suite's own `PositiveSyntaxTest` label implies SPARQL's
    grammar should accept as text. Instead, a real semantic backstop:
    `TripleTermNode.validate()` (`triple_term.py`), raising the new
    `InvalidTripleTermError` if a node's own `subject` or `predicate` is
    itself a `TripleTermNode` — called at every construction site
    (`grammar12.py`'s `_promote`, so it fires immediately at parse time
    regardless of pattern/expression position; `from_rdf.py`'s `TripleTerm`
    decode branch, so a hand-authored or malformed `salg:TripleTerm` RDF
    graph can't bypass it either). This is why the check belongs at
    construction, not only in the grammar: parsing alone can't distinguish
    "SPARQL accepts this text" from "this is valid RDF," but every real
    path that produces a `TripleTermNode` goes through one of these two
    call sites, so nothing can construct an invalid one and have it survive
    downstream. Confirmed via the same live Oxigraph/Fuseki instances used
    for the original investigation: `test_adversarial_roundtrip.py`'s
    `nested_depth_4` case (which had been testing exactly this invalid
    shape, not just failing against Oxigraph but *also* newly discovered to
    trip a known, already-documented Fuseki `TRIPLE()`-subject bug — see
    `docs/fuseki-upstream-issues.md` Issue 1 — via a different path) was
    rewritten to nest correctly in *object* position instead (still a real
    depth-4 stress test, now of something actually valid), plus a new,
    explicit `test_nested_subject_triple_term_is_rejected` confirming
    `InvalidTripleTermError` fires — matching this project's own repeated
    lesson (findings #12/#20) that a positive round-trip test proves valid
    input works, it doesn't prove invalid input is actually rejected.
    `compound-tripleterm-subject`/`nested-tripleterm-02` now correctly fail
    `test_syntax_positive` despite their `PositiveSyntaxTest` label — a
    deliberate, documented divergence (same treatment as finding #24's
    `list-anonreifier-01`/`list-tripleterm-01`), not a regression.
28. **A non-ground triple term used as a query/update *pattern*
    (`<<( ?s :p :o )>>`, a variable somewhere inside) never worked
    correctly — not just in the Update lowering being newly built, but in
    the *pre-existing* SELECT lowering too — and fixing it took three
    separate, genuinely distinct bugs across two repos, each confirmed by
    direct reproduction, not guessed.** Found while building Update
    lowering (`_lower_flat_triples`/`_lower_modify_clause_triples`, both
    reusing `_lower_pattern_term`): a non-ground triple term always
    silently matched **zero rows**, regardless of real matching data.

    **Bug 1 (this project, `lower_rdf11.py`) — the old decomposition
    strategy targeted a representation the store doesn't have.** The
    original `_lower_pattern_term` lowered a non-ground triple term into
    `?ttVar rdf:subject s . ?ttVar rdf:predicate p . ?ttVar rdf:object o .`
    match triples appended to the enclosing BGP — mirroring
    `sparql12_to_11.py`'s own (confirmed, via reading its source, to have
    the *identical* strategy for this case) text-rewriter. Confirmed via
    direct inspection (`for t in g: print(t)`) that `StarLayerGraph`/
    `StarLayerDataset` store a triple term as a **native Python
    `TripleTerm` object** with real `.subject`/`.predicate`/`.object`
    attributes, never as decomposed `rdf:subject`/`predicate`/`object`
    triples — so these match triples had nothing to match against, ever.
    Fixed by minting a fresh variable for the *whole* triple term (bound
    the ordinary way, via the BGP's own triple match) and pushing
    `tt:fn/subject`/`predicate`/`object` **accessor-function** constraints
    instead (`_add_component_constraints`/`_add_single_constraint` in
    `lower_rdf11.py`) — `Extend` (BIND) for a component that's a `Variable`
    not otherwise bound, `Filter` equality for a ground component or one
    already bound elsewhere (see Bug 3). A nested object (itself a
    `TripleTermNode`) recurses via a *chained* accessor call
    (`tt:fn/subject(tt:fn/object(var))`) rather than getting its own
    top-level pattern-matched variable — necessary because `StarLayerGraph`
    represents a nested triple term as a further native `TripleTerm`
    object too, even when fully ground, so there's no ordinary BGP slot to
    substitute an eager `tt:` URI into at that depth (only the *outermost*
    triple term, sitting directly in an ordinary pattern's own term slot,
    gets that treatment).

    A **second, independent bug within this same fix** surfaced via the
    W3C fixture `pattern-10` (`<<?s ?p <<( ?st ?pt ?ot )>> >>`, an outer
    triple term whose *object* is only a triple term in some data, not
    others): recursing into a nested object's own subject/predicate/object
    without first verifying the extracted value **is actually a triple
    term** let a non-matching value (e.g. plain `:o`) silently pass —
    because the accessor functions *raise* for a non-triple-term argument,
    and that raise, when it happens inside an `Extend`-classified
    component, is swallowed into "leave that one variable unbound" rather
    than rejecting the row (see Bug 3's own root cause below — the same
    swallowing mechanism, different node type). Fixed by unconditionally
    pushing an explicit `Filter(isTRIPLE(base_expr))` guard
    (`_is_triple_term_expr`) before processing any triple term's own
    components, at *every* level (not just nested recursion — the same gap
    exists at the top level too, if every one of that term's components
    happens to be `Extend`-classified). This also fixed a real,
    independent latent bug in `Builtin_isTRIPLE`'s own existing lowering
    (`_lower_expr`'s `Builtin_isTRIPLE` branch, and — confirmed via reading
    its source — `sparql12_to_11.py`'s own `isTripleTerm()`/`isTRIPLE()`
    text-rewrite target): both used `STRSTARTS(STR(x), TT_NS)` alone, which
    is **false for a native `TripleTerm` object** — confirmed empirically
    that `STR()` on one renders it as `"<<( s p o )>>"`, never
    `TT_NS`-prefixed, so `isTRIPLE(?x)` on an ordinarily-pattern-matched
    triple term always incorrectly returned false. `_is_triple_term_expr`
    fixes this project's own side by OR-ing in a second `STRSTARTS(STR(x),
    "<<")` check; the sibling repo's own `isTripleTerm()`/`isTRIPLE()`
    still has this specific gap (not fixed there this session — out of
    scope, since nothing currently routes through it with this input
    shape, but worth knowing about before relying on it for a
    pattern-matched, as opposed to freshly-constructed, triple term).

    **Bug 2 (sibling `starlayergraph` repo,
    `sparql12_to_11.py::_register_tt_accessor_functions`) — the
    `SUBJECT`/`PREDICATE`/`OBJECT` accessor functions only accepted a
    `tt:`-prefixed `URIRef` argument, unconditionally rejecting a native
    `TripleTerm` object with `SPARQLError`.** Confirmed via direct testing
    (bypassing this project's own lowering entirely — plain rdflib +
    starlayergraph): `BIND(<tt:fn/subject>(?tt) AS ?s)` against `?tt` bound via
    an ordinary `?r rdf:reifies ?tt .` match produced an *empty* binding,
    not the expected subject — because `?tt`'s actual value, per Bug 1's
    own finding, is a native `TripleTerm`, and the accessor's own
    `isinstance(uri, URIRef) and str(uri).startswith(TT_NS)` check rejects
    that outright. This is real and load-bearing for *this project's own*
    fix above (which depends on exactly this call shape) — not just a
    latent gap. Fixed (in the sibling repo, not here) by adding a
    `isinstance(uri, TripleTerm)` branch *before* the `URIRef`/`TT_NS`
    check, returning `(uri.subject, uri.predicate, uri.object)[index]`
    directly — no `lookup_tt_hash`/graph dereference needed at all, since a
    native `TripleTerm` object already carries its own answer.

    **Bug 3 (sibling `starlayergraph` repo, ``evaluate_patches.py``) — a
    second, previously-undiscovered instance of the *same* confirmed
    rdflib bug `patch_evalextend_forgotten_bind_vars` already fixes for
    `evalExtend`, this time in `evalFilter`, and traced one level deeper
    to its actual root: `_addVars` (`algebra.py`) never populates `_vars`
    for a `RelationalExpression` node at all** — confirmed via a minimal,
    standalone plain-rdflib repro with *no* starlayergraph/starsparql code
    involved: `prepareQuery("SELECT * WHERE { ?s ?p ?x FILTER(?x = ?o) }")`
    (`?o` free in the filter, absent from the wrapped BGP) — the resulting
    `RelationalExpression`'s own `_vars` is an empty `set()`, regardless of
    which side (`expr` or `other`) `?o` sits on. Surfaced by this
    project's own `_add_single_constraint`'s `Filter`-classified branch (a
    component variable already bound by a *sibling*, lazily-joined BGP —
    see the "Same variable"/`GRAPH` findings below): `evalFilter`'s
    `c.forget(ctx, _except=part._vars)` dropped the shared variable before
    the comparison ever ran, silently making the filter false for every
    row and emptying the whole result — exactly the "unbound variable
    silently swallowed, row wrongly rejected/accepted" failure class
    CLAUDE.md already documents pervasively for `evalExtend`, just reached
    through `FILTER` instead of `BIND`, and *not* covered by that patch
    (which only touches `evalExtend`). Root-caused (not just
    symptom-patched) by first discovering that the *existing*
    `_expr_free_vars` helper (which the `evalExtend` patch already relies
    on) has the identical gap baked in — it just reads `expr`'s own
    `_vars` as a shortcut, so it silently inherits `_addVars`'s own
    incompleteness for a `RelationalExpression` too. Fixed in two parts,
    both in the sibling repo: (a) rewrote `_expr_free_vars` itself from a
    `_vars`-trusting lookup into a genuine recursive structural walk
    (finds every bare `Variable` anywhere in the expression tree,
    regardless of key name) — strictly more complete for every existing
    caller, no behavior lost; (b) added a new, analogous
    `patch_evalfilter_forgotten_vars` (mirroring
    `patch_evalextend_forgotten_bind_vars`'s own shape exactly), wired
    into `starlayergraph/__init__.py` alongside it. Verified: the sibling
    repo's own full test suite (997 tests) and this project's own full
    suite (152 + 214 W3C) both still pass after both changes — no
    regressions from making `_expr_free_vars` more complete.

    **A third, structurally distinct bug was needed on top of all of the
    above, specific to the "same variable shared across sibling BGPs"
    case (the W3C fixtures `pattern-9`, "Same variable", and `graphs-1`/
    `graphs-2`, `GRAPH` + a shared variable) — plain per-BGP scoping
    of "is this variable already bound elsewhere" isn't enough.**
    `_bgp_plain_vars` (every `Variable` appearing as an *ordinary*,
    non-triple-term position within one BGP's own triples — the basis for
    choosing `Extend` vs. `Filter` per component, see
    `_add_single_constraint`'s own docstring for the `evalExtend`-overwrite
    hazard this exists to avoid) is correct for a variable reused *within
    the same BGP* (`pattern-9`'s `<<?s ?p :o>> ?p ?z`, both triples in one
    BGP) but blind to a variable shared with a **sibling** BGP joined via
    `Join`/`GRAPH` (`graphs-1`'s `:s :p ?o .` / `GRAPH ?g { <<:s :p ?o>>
    ?q ?z }`, two separate BGPs). Whether treating such a variable as
    "already bound" is even *correct* turned out to depend on **rdflib's
    own `Join.lazy` flag**, confirmed by reading `evalJoin`/`evalLazyJoin`'s
    actual source rather than assuming standard "both branches evaluate
    independently" `_join` semantics apply uniformly:
    - **`lazy=False`** (plain `Join`): `evalJoin` evaluates `p1` and `p2`
      **independently** (same starting `ctx`, no thawing) and joins the
      two *result sets* afterward by matching shared-variable equality
      (`_join`/`FrozenBindings.compatible`). A cross-BGP shared variable
      is **not actually available** inside `p2`'s own isolated evaluation
      — treating it as "already bound" and emitting a `Filter` there
      compares against a genuinely unbound variable, which fails safe but
      *too* safe: confirmed via a real regression (an earlier, wrong fix
      attempt) that this produces **zero rows** instead of the correct,
      join-restricted answer. The correct behavior for this case is
      exactly what `_bgp_plain_vars`-per-BGP already gives with no global
      pass at all — the ordinary ("independent branches, join
      afterward") join mechanism handles the equality correctly on its
      own, for free.
    - **`lazy=True`** (the case `GRAPH` actually triggers, confirmed via
      inspecting the real lowered algebra's own `Join.lazy` field for
      `graphs-1`): `evalLazyJoin` **pushes `p1`'s bindings into `p2`'s own
      evaluation context** (`c = ctx.thaw(a)`) before evaluating `p2` —
      so the shared variable genuinely *is* bound within `p2` this time.
      Treating it as *not* already bound (the `lazy=False`-correct
      behavior) is wrong here: `Extend` then unconditionally overwrites
      the pushed-in value with whatever the triple term's own component
      computes (same `evalExtend`-doesn't-check-prior-binding hazard,
      confirmed via tracing `_patched_eval_extend`'s own `c.merge(...)`),
      and `evalLazyJoin`'s own `yield b.merge(a)` — where `a`'s value wins
      for any shared key, confirmed via `FrozenBindings.merge`'s `chain`
      order — then silently discards that overwrite and restores `a`'s
      *original* value regardless, so the mismatch is never actually
      caught: the row survives with `?o` forced back to `p1`'s value but
      every *other* variable (`?q`/`?z`) still reflecting whichever
      triple term `p2` happened to match, producing an internally
      inconsistent, wrong result — not a crash, not an empty result,
      genuinely wrong data with nothing to signal it. Confirmed via
      tracing actual `a`/`b`/`compatible()` values through both
      `evalJoin` and `evalLazyJoin` directly (an early debugging attempt
      that monkey-patched `evalJoin` with `_join`-only semantics
      accidentally "fixed" the symptom by bypassing `evalLazyJoin`
      entirely — a false signal worth remembering: patching the wrong
      function in a quick repro can look like confirmation of the wrong
      theory).

    Fixed by adding a **global, tree-wide "mandatory plain vars" pre-pass**
    (`_collect_mandatory_plain_vars` — walks the *whole* pre-lowering
    algebra once per query/Modify-operation, seeded into
    `_LowerState.global_plain_vars`, unioned into every `_lower_bgp`/
    `_lower_flat_triples` call's own local `already_bound` set) — **not**
    to handle the plain-`Join` case (already correct without it, per
    above), but because `_lower_expr`'s generic recursion has no way to
    know, at the point it's lowering one particular BGP, whether the
    *specific* `Join` node above it will end up `lazy=True` (GRAPH,
    OPTIONAL, and other constructs set this) or `False` (plain BGP-BGP
    juxtaposition) — and the `lazy=True` case genuinely needs the global
    view for correctness, so the same global set is used unconditionally.
    This is safe for the `lazy=False` case too, *not* because that case
    also needs it, but because a `Filter` comparing against a variable
    that a **lazy** join or a mandatory sibling would have supplied
    correctly is nonetheless what actually gets evaluated once Bug 3's own
    fix (`patch_evalfilter_forgotten_vars`) is in place — the earlier
    "global collection causes zero rows" regression was itself caused by
    Bug 3 (the `Filter`'s own free variable getting forgotten), not by the
    global-collection *design* being wrong; once Bug 3 was fixed, global
    collection started working correctly for both join-laziness cases
    uniformly. Deliberately conservative about *what* counts as
    "mandatory": does not descend into `LeftJoin.p2` (`OPTIONAL`),
    `Union`'s branches, or `Minus.p2` — a variable bound only in one of
    those isn't safe to treat as unconditionally available (would risk
    *incorrectly rejecting* solutions via a `Filter` comparing against
    something that turns out unbound for a given row, worse than the
    `Extend` inefficiency it would otherwise avoid).

    Also closed in the same pass, since `_lower_pattern_term`'s signature
    changed for all of the above: `DeleteWhere`'s own flat triples list
    (`_lower_flat_triples`, shared with `InsertData`/`DeleteData`, which
    never hit this since SPARQL's `QuadData` grammar forbids variables
    there) has **no** `Filter`/`Extend`-wrapping capability at all —
    confirmed via reading `evalDeleteWhere`'s source: it calls `evalBGP`
    directly on the flat triples list, with no wrapping possible the way
    an ordinary WHERE clause allows. A non-ground triple term reaching
    this path originally raised `NotImplementedError` explicitly (a known,
    deliberately unhandled gap) rather than silently mismatching — **closed
    in a later session, see finding #29**, which rewrites the operation
    into an equivalent `Modify` instead, and along the way found two more
    genuinely separate, previously-undiscovered bugs in the sibling
    `starlayergraph` repo (a confirmed `evalModify` bug, and a real gap
    in `StarLayerDataset`'s own API surface) that were silently blocking
    *any* Update DELETE/INSERT of a triple-term value against a
    `StarLayerDataset` — not specific to this project's own lowering at all.
29. **Closing the `DeleteWhere` + non-ground-triple-term gap finding #28
    left open surfaced three layered bugs, each confirmed independently —
    only the first was in this project's own code.**

    **Fix 1 (this project, `lower_rdf11.py`) — `_lower_delete_where`
    rewrites `DeleteWhere` into an equivalent `Modify` whenever a
    non-ground triple term is present** (`_contains_nonground_triple_term`
    checks first; the ordinary ground/plain-variable case stays on the
    original, unchanged `_lower_flat_triples_op` path — no structural
    change for the common case). The key move making this a *reuse*, not
    just shape-mimicry: the same lowered, variable-substituted triples
    list `_lower_triples_for_pattern` produces for the WHERE side (the
    `_lower_bgp`-style `Filter`/`Extend` wrapping, factored out as a
    shared helper) is *already* exactly correct as the DELETE template
    too — by the time the template is instantiated, the fresh variable
    standing in for the triple term is bound to precisely the value the
    WHERE clause matched, so no `TT_HASH_FN`-reconstruction or extra
    `BIND` machinery is needed the way an ordinary Modify's own
    `.delete`/`.insert` clause requires (`_lower_template_term`'s
    unconditional-mint approach, which has no such existing pattern-side
    variable to reuse). Each graph's own triples (default plus each
    `.quads` entry) get their *own* separately-scoped `already_bound` set
    — deliberately **not** shared globally the way
    `_collect_mandatory_plain_vars` shares one for an ordinary WHERE
    clause: the `Join`/`Graph` nodes this rewrite builds are never marked
    `lazy=True`, and per finding #28's own conclusion, a variable shared
    only with an independently-evaluated sibling branch is safe to leave
    unbound-and-let-the-natural-join-catch-it, not something this
    function should pretend is already bound.

    **Fix 2 (sibling `starlayergraph` repo, `evaluate_patches.py`) — a
    confirmed, previously-undiscovered bug in plain rdflib's own
    `evalModify`.** After Fix 1 alone, the rewritten `Modify`'s WHERE
    clause matched the correct rows (confirmed via a monkey-patched trace)
    but **nothing was actually deleted** — no error, silent no-op.
    Root-caused to `evalModify`'s own graph-selection line: `dg = ctx.graph
    if type(ctx.graph) is Graph else ctx.dataset.default_context` — its
    own source comment even flags this as fragile ("weird type checking
    logic"). For a `StarLayerDataset`, `ctx.graph` (the real
    `StarLayerDataset` instance, with its own `TripleTerm`-aware
    `add`/`remove` — see Fix 3) and `ctx.dataset.default_context` (a
    generic `rdflib.graph.Graph` wrapper around the *same* underlying
    `Store`, confirmed via `id()` comparison to be a genuinely different
    Python object) behave identically for an *ordinary* triple (same
    `Store`, so removal reaches it either way) but not for a triple whose
    subject/object is a native `TripleTerm` — only the real
    `StarLayerDataset` object's own overridden methods correctly translate
    it. `evalDeleteWhere` (unaffected by this bug) already uses `ctx.graph`
    unconditionally, which is what gave away the fix. First attempt (using
    `ctx.graph` directly with `dg -= _fillTemplate(...)`) surfaced a
    **second**, distinct issue: `ConjunctiveGraph.__isub__`/`__iadd__`
    (which `dg` resolves to whenever it's genuinely `Dataset`-typed, not a
    bare `Graph`) expect `other` to already be *quads* (4-tuples), unlike
    `Graph.__isub__`/`__iadd__`'s own triple-based (3-tuple) contract —
    `_fillTemplate` always yields plain triples, so `-=`/`+=` against a
    true Dataset raised `ValueError: not enough values to unpack`. Fixed
    by calling `.remove()`/`.add()` explicitly in a loop instead of `-=`/
    `+=` (`patch_evalmodify_default_graph_selection`) — functionally
    identical to what `Graph.__isub__` already does internally for a plain
    `Graph`, and correct rather than crashing for a `Dataset`.

    **Fix 3 (sibling `starlayergraph` repo, `starlayergraph_dataset.py`) — a
    real, previously-undiscovered gap in `StarLayerDataset`'s own API
    surface, not a monkeypatchable rdflib bug.** Even with Fix 2's
    `ctx.graph`-selection corrected, deletion *still* silently no-op'd.
    Traced (via the most minimal repro possible — `g.remove((s, p, o))`
    with `o` the *exact* `TripleTerm` object `g.triples()` itself had just
    yielded) to: `StarLayerDataset` overrides `.triples()`/`.quads()` to
    delegate to a real per-context `StarLayerGraph` (whose own
    `add`/`remove` correctly translate a `TripleTerm` to/from this
    library's internal `tt:HASH` registry encoding) — but has **no
    override for `.add()`/`.remove()`/`.addN()` at all**, so calling any
    of them directly on a `StarLayerDataset` instance (exactly what
    `evalModify`/`evalInsertData`/etc. do for the default graph, with no
    `WITH`/`USING` clause) fell through to plain rdflib `Dataset`
    methods — which write a raw `TripleTerm` Python object straight into
    the underlying store with no translation at all, matching nothing on
    a later read or removal, silently. Fixed by adding
    `StarLayerDataset.add`/`.remove`/`.addN`, each delegating to
    `self.get_context(...)`'s real `StarLayerGraph` — mirroring
    `.triples()`/`.quads()`'s own established delegation pattern exactly.

    Also surfaced along the way (session-adjacent, deliberately **not**
    fixed, scoped as a separate, pre-existing, unrelated issue): plain
    `evalInsertData`'s own `g += u.triples` hits the *identical*
    `ConjunctiveGraph.__iadd__`-expects-quads bug Fix 2 patches for
    `evalModify` — confirmed via testing bare, unmodified rdflib +
    `StarLayerDataset` with zero triple terms involved — but
    `evalInsertData` itself is not patched (out of scope for "close the
    `DeleteWhere` gap"; `tests/test_lower_rdf11.py`'s own new Update tests
    deliberately don't exercise `INSERT DATA` against a `StarLayerDataset`
    for this reason, documented inline there).

    Verified: `starsparql`'s own full suite (155 + 214/221 W3C, same
    4 pre-existing deliberate divergences) and the sibling repo's own full
    suite (997 tests) both pass with all three fixes applied — including a
    real regression caught mid-fix (`patch_evalmodify_default_graph_selection`'s
    first version broke `default_union=True` Update tests via the
    `ConjunctiveGraph.__iadd__` quad-unpacking issue above; fixed before
    landing, not after).

30. **Architecture audit (in the sibling `starlayergraph` repo's session,
    cross-posted here per instruction): this project's dependency on
    `starlayergraph` runs backwards from what its own code claims, and
    the fix is smaller/cleaner than it first looks. Not yet implemented —
    documenting for a future pass in this repo.**

    **The claim vs. reality.** `lower_rdf11.py`'s own module comment says
    "this project's dependency direction runs starlayergraph ->
    starsparql." That's aspirational, not actual. What's really
    wired up: this project's `pyproject.toml` declares `starlayergraph`
    as a hard runtime dependency, and three production modules import
    directly from `starlayergraph.model.encoding`:
    - `grammar12.py` — `encode_dirlang_datatype` (`LangDirLiteral`'s parse
      action, ~line 277).
    - `serialize12.py` — `decode_dirlang_datatype` (`_dirlang_n3`, ~line 66).
    - `lower_rdf11.py` — `TT_NS`, `remember_tt_hash`, `term_key`, `tt_hash`
      (`_lower_ground_triple_term`, ~line 637).

    Checked the reverse direction directly: `starlayergraph` has **zero**
    real imports of `starsparql` anywhere — only comments referencing
    it by name in docstrings (`sparql12_to_11.py`, `evaluate_patches.py`,
    `algebra_translator_patches.py`). So the claimed direction was never
    actually realized; what exists today is exactly the opposite. Also
    relevant: the third sibling, `starShacl`, already depends on
    `starlayergraph` directly and does **not** depend on this project at
    all — evidence this project is meant to be independently reusable, not
    something that only makes sense bundled with one specific consumer.

    **Two distinct coupling points, not one.** User's framing (accurately):
    the SPARQL engine legitimately needs *some* RDF 1.2 triplestore to
    execute against, and today that's starlayergraph — fine to leave as-is, no
    pluggable-backend abstraction needed right now. The actual problem is
    narrower: the **1.2-algebra-to-1.1-algebra lowering** is inherently
    shaped around one specific backend's internal representation, and that
    coupling currently leaks into places that shouldn't need it.

    1. **`lower_rdf11.py` is entirely a backend adapter, not generic
       translation work.** Its own docstring says it produces an algebra
       tree "runnable against starlayergraph's in-memory backend" — and
       confirmed empirically that starlayergraph's *other* backend (`rdf-1.2`,
       native Oxigraph/Fuseki) needs **no** 1.2-to-1.1 lowering at all; it
       sends the original SPARQL 1.2 text straight through. The lowering
       exists solely because one specific backend (starlayergraph's in-memory,
       `tt:HASH`-content-addressed one) can't represent triple terms/
       dirLangString natively in vanilla rdflib's SPARQL 1.1 evaluator.
       That's 100% adapter code for one consumer, not "translate SPARQL
       1.2 algebra to/from RDF" (this project's actual stated purpose —
       see "Purpose" above).
    2. **dirLangString encoding is baked in even earlier, at *parse*
       time, and leaks into the "generic" RDF representation untouched.**
       Confirmed `to_rdf.py`/`from_rdf.py` never handle `TripleTermNode`
       by leaning on starlayergraph at all — it gets a proper structural RDF
       encoding (`salg:subject`/`salg:predicate`/`salg:object` triples),
       zero starlayergraph dependency, and the `tt:HASH` URIRef trick only
       appears right at the end, inside `lower_rdf11.py`. dirLangString
       never got the same treatment: `grammar12.py`'s `LangDirLiteral`
       builds `Literal(text, datatype=encode_dirlang_datatype(lang, dir))`
       directly at parse time, packing `(language, direction)` into a
       private, unpublished URI under
       `https://github.com/.../starlayergraph/ns/dirlang#...`. That
       Literal then flows opaquely through `to_rdf.py`'s `_LEAF_TERM_TYPES
       = (URIRef, BNode, Literal)` branch (confirmed: it treats *any*
       Literal as a leaf regardless of datatype, no dirlang-specific code
       exists there at all) straight into the `salg:` RDF representation
       of the algebra — meaning the SHACL shapes work (`shapes.py`/
       `ontology.py`) sees an opaque literal with an undocumented,
       starlayergraph-internal datatype IRI, not a real fact about a
       dirLangString, and any non-starlayergraph consumer of that RDF can't
       interpret it without importing starlayergraph just to decode one
       literal's datatype.

    **Checked starlayergraph's own `DirLangString` design before proposing a
    fix (per direct instruction) — it's sound, not the source of the
    problem.** `starlayergraph/model/dirlangstring.py`: `DirLangString` is a
    real value type (`value`/`language`/`direction`, structural equality),
    separate from its `encode_dirlangstring`/`decode_dirlangstring`
    conversion to/from a plain `rdflib.Literal` — the same split
    `TripleTerm` already gets. The datatype-URI-packing trick exists
    purely because `Literal(text, lang="en--rtl")` raises (rdflib's
    lang-tag validator has no notion of the RDF 1.2 `--dir` suffix); it
    isn't chosen for any starlayergraph-storage-specific reason. Crucially,
    this is **not** the same kind of coupling `tt_hash`/`term_key` are:
    those are genuine shared runtime state (a lowered query's computed
    hash has to match the *store's own* hash of the same triple term, or
    pattern matching silently fails to match real data) — the dirlang
    encoding has no such constraint. It's a pure convention ("pack two
    strings into a URI so `Literal()` accepts them"); starlayergraph just
    happens to also use it at its own read/write boundary. Nothing
    requires this project to use starlayergraph's *exact* URI scheme.

    **Proposed fix (not implemented this session):**
    - Give this project its own neutral encode/decode pair (own
      namespace, e.g. under `vocab.py`'s `SALG_NS`) — same trick, zero
      starlayergraph import — and have `grammar12.py`/`serialize12.py` use
      that instead of `starlayergraph.model.encoding`.
    - `to_rdf.py`/`from_rdf.py` need no changes at all — already
      datatype-agnostic, confirmed above.
    - `lower_rdf11.py`, once it's relocated into `starlayergraph` as an
      explicit backend-adapter module (the companion fix to coupling
      point #1 above — a separate, larger change spanning both repos'
      import graphs and test suites, not attempted here), becomes the one
      place that translates this project's neutral dirLangString encoding
      into starlayergraph's exact `dirlang:` scheme as part of lowering — the
      same role it already plays for ground triple terms via `tt_hash`/
      `remember_tt_hash`.
    - End state: this project has zero `starlayergraph.*` imports anywhere in
      its own package; only the (relocated) adapter module in
      `starlayergraph` knows starlayergraph's specific encodings for either
      triple terms or dirLangString.

    Both parts of this fix are cross-repo (the adapter module needs to
    exist in `starlayergraph` for `lower_rdf11.py` to move there) —
    sequencing and implementation left for a future pass in this project,
    per direct instruction.

    **Superseded, same later session, per direct instruction: `lower_rdf11.py`
    is NOT being relocated.** The two-repo circular dependency this bullet's
    first paragraph worried about is intentional and accepted — this
    project is treated as part of `starlayergraph`'s own SPARQL engine
    layer (see that repo's `todos.md`), not an independent generic library,
    and `starlayergraph` now declares a matching dependency back on this
    project (see its own `pyproject.toml`) specifically so it can consume
    `parse12`/`to_rdf`/`from_rdf`/`lower_rdf11` directly. `lower_rdf11.py`'s
    existing `starlayergraph.model.encoding`/`starlayergraph.query.
    algebra_translator_patches` imports stay exactly as they are. The
    dirLangString-neutral-encoding half of this finding (this project's own
    `vocab.py` encoding, distinct from starlayergraph's) was already completed
    in an earlier session and remains in place regardless — only the
    "relocate the module" half is what's now explicitly not happening.

31. **[RESOLVED] Running `starsparql`-based tests together with other
    tests in the *same* pytest process could corrupt this project's own
    grammar installation** (`grammar12.py`). Originally found and worked
    around from the `starlayergraph` side while building that repo's opt-in
    `sparql_pipeline='algebra_ir'` execution path; the actual root cause and
    fix were found later, while scoping that repo's full removal of its old
    hand-rolled rewriter (see that repo's `docs/testing-strategy.md` tier 5
    for the up-to-date write-up). Symptom: `TRIPLE()`-family syntax that
    parsed fine moments earlier starts raising `ParseException: Expected
    SelectQuery, found '('` with no code or data change -
    `rdflib.plugins.sparql.parser.PrimaryExpression` (the same Python object,
    confirmed via `id()` - not a duplicate import) ends up with its `.exprs`
    reset to a flattened, pristine-rdflib list missing every production
    `grammar12.install()` added.

    **Real root cause, confirmed by direct A/B testing**: this project's
    `grammar12`/`parse12` were only ever imported *lazily* - from inside
    function bodies (e.g. `StarLayerGraph.query()`), never at any test
    module's top level - so their first import happened during pytest's own
    collection/execution phase, while its assertion-rewrite import hook was
    active, which is what triggered the corruption. This had nothing to do
    with which pipeline a given test exercised, and nothing to do with
    `starsparql` vs. `starlayergraph`'s legacy pipeline coexisting -
    reproduced with a file that never touches `starsparql` at all
    (`starlayergraph`'s `test_dataset.py`), run alongside one that does.

    **The fix**: on the `starlayergraph` side, `tests/conftest.py` now
    does `from starsparql import grammar12; grammar12.install()`
    unconditionally, at module level, so it runs at collection time, before
    any test module can trigger the import lazily. Confirmed via repeated
    full-suite runs (`pytest tests/ -q`, no marker exclusions, every test
    file together) passing cleanly, where the same combination reliably
    failed before. Any project embedding `starsparql` under pytest
    should do the same - eagerly import and install the grammar from a
    `conftest.py`, not lazily from inside application code reached only once
    a test starts running.

    The two in-`grammar12.py`/`parse12.py` mitigations from the original
    investigation (state-based idempotency check in `install()`; a
    retry-with-forced-reinstall on `ParseBaseException` in `parse12.py`) are
    still real, still correct, and still kept - they're good defensive
    depth (e.g. against some *other*, still-hypothetical corruption source),
    just not what actually fixed this specific, now-resolved issue.

## File map

- `starsparql/vocab.py` — the `salg:` namespace and every encoding
  convention, with a long module docstring explaining each one and why. If
  a design question comes up ("how is X encoded?"), check here before
  re-deriving it.
- `starsparql/to_rdf.py` — `query_to_rdf`, `update_to_rdf`,
  `queries_to_collection` (Phase 8), and the generic `_encode` walker +
  special cases (triple patterns, paths, binding rows, quads maps,
  prologue).
- `starsparql/from_rdf.py` — `rdf_to_query`, `rdf_to_update`,
  `rdf_to_collection` (Phase 8), the generic `_decode` walker + special
  cases, and `_discover_expr_evalfns` (the live-grammar introspection).
- `starsparql/shapes.py` — Phase 5: hand-authored SHACL shapes over
  Phase 1's core operators (`BGP`/`Filter`/`LeftJoin`/`Union`/`Extend` +
  `TriplePattern`/`Variable`/`Project`/`SelectQuery`) plus `VALUES`/
  subqueries (`Join`/`ToMultiSet`/`values`/`Binding`/`Slice`/`Distinct`/
  `Reduced`/`OrderBy`/`OrderCondition`), (Phase 6) `TripleTerm`, (a later
  session) all 63 expression builtins, and (Phase 9) Update (all ten
  operations)/`CONSTRUCT`/`ASK`/`DESCRIBE`/property paths (5)/aggregates
  (`Group`/`AggregateJoin`/all 7 `Aggregate_*`)/`MINUS`/`SERVICE`/
  `QueryCollection` — see the Phase 9 status entry above for the two real
  bugs found while building it (a Turtle-escaping trap in this file's own
  Python-string-embedded Turtle, and a `SALG.term`-vs-`Namespace.term()`
  Python name collision) and the real, separate bug it found one layer
  down in `to_rdf.py`, traced to and genuinely fixed (not just given a
  clearer error) in the sibling `starlayergraph` repo's own
  `algebra.translate` — see finding below and that repo's
  `docs/rdflib-upstream-issues.md` Issue 9. `_encode_list`'s own
  `NotImplementedError` for an un-aliased, expression-valued `GROUP BY`
  key is now just a defensive fallback for the (unusual) case where
  `starlayergraph` isn't imported at all. `validate()` wraps
  `pyshacl.validate` — with `ont_graph=ontology_graph()`/
  `inference="rdfs"` — and the workarounds findings #9/#10 above describe.
- `starsparql/salg-ontology.ttl` / `ontology.py` — a real RDFS
  ontology (classes/subclasses, properties/subproperties, domain/range)
  for the `salg:` vocabulary, actually consulted by `shapes.py::validate()`
  for RDFS reasoning, not just documentation — see the Phase 5 status
  entry above for the design and two real entailment-vs-validation bugs
  found while wiring it up.
- `starsparql/expr_families.py` — `_EXPR_NODE_FAMILY`, the
  `{builtin name: argument-signature family}` table both `shapes.py` and
  `ontology.py` generate their per-builtin declarations from. Lives in its
  own module (not either of those) specifically so `ontology.py` never
  needs `pyshacl` (a `shapes.py`-only dependency) just to read it.
- `starsparql/grammar12.py` — Phase 6: new pyparsing productions for
  `<<( s p o )>>`/`TRIPLE(s, p, o)`, spliced into rdflib's own real grammar
  objects in place via `.append()` (`install()`) at two extension points:
  the triple-pattern-term grammar (`GraphTerm`/`VarOrTerm`/`GraphNode`/
  `GraphNodePath`) and, for expression-position usage (`isTRIPLE`/
  `SUBJECT`/`PREDICATE`/`OBJECT`, and a bare triple term as a value), the
  expression grammar (`PrimaryExpression`/`BuiltInCall`). See findings
  #11/#12.
- `starsparql/triple_term.py` — Phase 6: `TripleTermNode`, the
  `CompValue` subclass a genuine SPARQL 1.2 triple term needs to survive
  rdflib's unmodified `translateQuery`/`translateUpdate`. See finding #11.
  Also `InvalidTripleTermError`/`TripleTermNode.validate()` — the semantic
  backstop rejecting a triple term nested in another triple term's own
  subject/predicate (invalid RDF 1.2 unconditionally, not just in
  expression position — see finding #27), called from both
  `grammar12.py`'s `_promote` and `from_rdf.py`'s `TripleTerm` decode
  branch.
- `starsparql/parse12.py` — Phase 6: `parse_query_12`/
  `parse_update_12`/`prepare_query_12`/`prepare_update_12`, this project's
  own SPARQL 1.2 ingestion entry points (not starlayergraph's `prepareQuery`).
  `prepare_update_12` also runs `_reject_blank_nodes_in_delete` — a
  post-`translateUpdate` check rejecting a blank node inside `DELETE DATA`/
  a `Modify`'s `DELETE` template, per spec. See finding #26.
- `starsparql/__init__.py` — imports `parse12` first, before
  anything else in the package, specifically so `grammar12.install()`
  always runs before `from_rdf.py`'s import-time grammar snapshot can
  observe a not-yet-extended grammar. Load-bearing, not stylistic — see
  finding #25 for the real bug this prevents.
- `starsparql/serialize12.py` — Phase 6: `translate_algebra_12`,
  SPARQL 1.2 text serialization for `SELECT`/`CONSTRUCT` — extends rdflib's
  own `algebra.translateAlgebra`/`_AlgebraTranslator` (the `BGP`/
  `TriplesBlock` branches, which call `.n3()` directly on each triple term
  and would crash on a `TripleTermNode`; new `Builtin_isTRIPLE`/`SUBJECT`/
  `PREDICATE`/`OBJECT` branches; a wholly new `ConstructQuery` branch, since
  plain rdflib has none at all) rather than reimplementing any of it. See
  findings #13/#14.
- `starsparql/lower_rdf11.py` — tree-level SPARQL 1.2 algebra -> 1.1
  algebra lowering: `lower_algebra_to_rdf11`/`query_to_rdf11`/
  `rdf11_to_query`/`rdf11_to_sparql11_text`. `rdf11_to_query` is preferred
  for execution — a directly-runnable `Query` object, no SPARQL 1.1 text
  involved anywhere; `rdf11_to_sparql11_text` stays for cases that need
  real text (debugging, external tools). No dependency on starlayergraph's own
  text-based `sparql12_to_11.py` rewriter either way. See the Phase 6
  status entry's "Tree-level 1.2-algebra->1.1-algebra lowering is now
  done" and "Execution now skips the SPARQL 1.1 text step entirely"
  paragraphs for the design and three real bugs found/fixed while building
  it. Also `lower_update_to_rdf11`/`update_to_rdf11`/`rdf11_to_update` —
  the Update-side counterpart (`InsertData`/`DeleteData`/`DeleteWhere`'s
  flat `.triples`/`.quads`, `Modify`'s `.delete`/`.insert` template
  clauses) — and non-ground triple-term *pattern* matching
  (`_add_component_constraints`/`_add_single_constraint`/
  `_collect_mandatory_plain_vars`), which needed three separate,
  cross-repo bug fixes (two in the sibling `starlayergraph` repo's own
  `evaluate_patches.py`/`sparql12_to_11.py`) to work correctly — see
  finding #28. `_lower_delete_where`/`_contains_nonground_triple_term`/
  `_lower_triples_for_pattern` — `DeleteWhere` rewritten into an
  equivalent `Modify` when a non-ground triple term is present, closing
  the gap finding #28 itself left open — needed two more cross-repo fixes
  (a confirmed `evalModify` bug, and a real `StarLayerDataset` API gap —
  no `TripleTerm`-aware `add`/`remove`/`addN`) — see finding #29.
- `tests/test_lower_rdf11.py` — unit tests per lowering branch plus
  end-to-end reuse of the W3C SELECT/CONSTRUCT fixtures against official
  ground truth (not just self-consistency).
- `tests/conftest.py` — shared `fixture_graph` (a small FOAF-ish graph).
- `tests/test_roundtrip.py` — Phase 1.
- `tests/test_phase2_*.py` — Phase 2, one file per feature area (forms,
  values/subquery, aggregates, paths, update).
- `tests/test_phase3_rdf12.py` — Phase 3, against a real `StarLayerGraph`
  (via starlayergraph's *lowering* `prepareQuery`/`prepareUpdate` — the
  SPARQL-1.1-equivalent-shape path, distinct from Phase 6's native path).
- `tests/test_phase4_prologue.py` — Phase 4.
- `tests/test_query_collection.py` — Phase 8: `salg:QueryCollection`
  round-tripped through real Turtle text, reusing `test_roundtrip.QUERIES`
  as the concrete "our own test queries" collection the user asked for.
- `tests/test_shacl_shapes.py` — Phase 5/6: valid Phase 1 + VALUES/subquery +
  top-level `LIMIT`/`ORDER BY`/`DISTINCT`/`REDUCED` + Phase 6 `TripleTerm`
  queries conform; deliberately malformed graphs fail with the expected
  violation.
- `tests/test_phase6_rdf12_native.py` — Phase 6: structural round-trip
  (tree shape + `_vars` bookkeeping), the cheap/fast-feedback layer.
- `tests/test_phase6_serialize12.py` — Phase 6: execution-verified
  round-trip via `serialize12.py` + a real `StarLayerGraph`, the semantic
  layer — see the Phase 6 status entry above. Covers term-position triple
  terms, expression-position (`isTRIPLE`/`SUBJECT`/`PREDICATE`/`OBJECT`/bare
  `BIND`), and `CONSTRUCT` (both plain and with a triple term in the
  template).
- `tests/w3c_sparql12/download_w3c_sparql12_tests.py` — Phase 7: fetches
  `manifest.ttl` (parsed as real Turtle via rdflib, not regex — unlike
  starlayergraph's own Turtle-suite downloader) plus every referenced file for 4
  manifest categories from `w3c/rdf-tests`, writes a local `data/index.tsv`
  for the harness to read. Safe to re-run (skips files already on disk).
- `tests/w3c_sparql12/harness.py` — Phase 7: `load_index`/`TestEntry`, plus
  a hand-written SPARQL JSON Results parser (`parse_srj`) — needed because
  rdflib's own built-in one doesn't understand the RDF 1.2 `"type":
  "triple"` result-term shape at all (confirmed: raises
  `NotImplementedError`), a pre-existing rdflib gap unrelated to this
  project's own work.
- `tests/test_w3c_sparql12.py` — Phase 7: the actual harness tests (syntax/
  eval-SELECT/eval-CONSTRUCT/eval-Update-skipped) — see the Phase 7 status
  entry above for current pass/fail counts and the unresolved state-leak
  caveat on trusting them fully yet.

## Setup / running tests

Not published to PyPI; depends on the sibling `starlayergraph` checkout.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ../starlayergraph
pip install -e ".[test]"   # includes pyshacl, for shapes.py
pytest
```

## Not started (from the original plan)

- **SHACL shapes beyond Phase 5/6's current scope** — covers
  `BGP`/`Filter`/`LeftJoin`/`Union`/`Extend`/`Join`/`ToMultiSet`/`values`/
  `Slice`/`Distinct`/`Reduced`/`OrderBy`/`TripleTerm` + the `SELECT` wrapper,
  and (a later session) full expression-tree validation for all 63 of
  rdflib's expression builtins (see `shapes.py`'s `ExpressionShape`/
  `_EXPR_NODE_FAMILY`). Still needed: `shapes.py` coverage for property
  paths, aggregates/`GROUP BY`/`HAVING`, Update, `MINUS`/`SERVICE`,
  `CONSTRUCT`/`ASK`/`DESCRIBE`-specific shapes, and validating
  `Builtin_EXISTS`/`NOTEXISTS`'s `.graph` (a raw, untranslated parse-tree
  fragment — a genuinely different vocabulary, deliberately out of scope,
  see the Phase 5 status entry above). **The `salg-ontology.ttl` side of
  this gap was closed in a later session** (ontology-only pass, explicitly
  before any `shapes.py` work, per direct instruction): real classes/
  subclasses now exist for all ten Update operations (`salg:UpdateOperation`
  had zero concrete subclasses before), `salg:Minus`/`salg:Group`/
  `salg:AggregateJoin`/`salg:ServiceGraphPattern` (all `rdfs:subClassOf
  salg:GraphPattern` directly — nothing else needed since
  `GraphPatternShape` is already a single `sh:class` check, not an
  enumerated `sh:or`), two new standalone dispatch superclasses
  `salg:Aggregate` (7 real SPARQL 1.1 aggregate subclasses, confirmed
  empirically — not 8, an earlier draft of this miscounted) and `salg:Path`
  (5 `rdflib.paths.Path` subclasses, mirroring vocab.py's already-encoded
  `to_rdf._encode_path`), plus every new property this required.
  Confirmed empirically before writing, same method as the 63-builtin
  table: `translateUpdate`/`translateQuery` against real text for every
  new operator's exact key shape. One real, load-bearing find while doing
  this: `salg:res` already had `rdfs:domain salg:values` (for
  `VALUES.res`) — reusing the same key name for `Aggregate_*.res` (an
  unrelated meaning, forced by this project's generic key-name encoding)
  would have silently re-triggered the exact "two `rdfs:domain` triples on
  one property, entailed as both simultaneously" bug this file's own
  `salg:PV`/`salg:var` comments already document — fixed by removing that
  domain declaration (matching the project's existing "when in doubt,
  don't declare domain/range" bias, made explicit by instruction:
  domain/range were deliberately *not* the focus of this pass, added only
  where genuinely clear-cut — e.g. `salg:delete`/`salg:insert`/`salg:where`
  on the leaf class `salg:Modify`, `salg:operations` on `salg:Update` —
  and left undeclared on anything feeding one of the (now five) dispatch
  superclasses `salg:GraphPattern`/`salg:Expression`/`salg:SubSelect`/
  `salg:Aggregate`/`salg:Path`, or shared across multiple unrelated
  classes, same as the existing `salg:triples`/`salg:PV`/`salg:p1`
  precedent). Verified: `ontology_graph()` still parses
  (326 triples, up from ~200), and the full existing test suite (155 +
  323 W3C, same 4 pre-existing deliberate divergences) is unaffected —
  confirmed a pure ontology addition, no shapes/tests touched yet.
  **The `shapes.py` side of this gap was closed in the same later
  session, immediately after, as the planned follow-on pass — see Phase 9
  below. This whole bullet (property paths/aggregates/Update/`MINUS`/
  `SERVICE`/`CONSTRUCT`/`ASK`/`DESCRIBE`) is no longer "not started."**
  The one piece still genuinely out of scope is `Builtin_EXISTS`/
  `NOTEXISTS`'s (and, found this session, `ServiceGraphPattern`'s own,
  same-shaped) `.graph` — still deliberately cardinality-only, a
  genuinely different untranslated vocabulary, not a gap.
  - **Still-open, deliberately not chased in the same pass: cross-referential
    semantic checks SHACL's per-node shapes structurally cannot see.**
    Confirmed via a real, reproducible counter-example, not a hypothetical:
    a `Project.PV` referencing a variable never bound anywhere in `.p`
    conforms perfectly (every individual shape — `ProjectShape`,
    `BGPShape`, etc. — only checks cardinality/type on its own node and
    immediate neighbors) and decodes into a real, executable `Query`
    object with no error; run it and the phantom variable just silently
    comes back unbound in every row. The mirror-image bug (a variable
    *bound* by `.p` but missing from `PV`, silently dropped from output)
    was a real regression fixed in `lower_rdf11.py`'s CONSTRUCT-template
    handling the same session this was found — so this isn't
    theoretical, it's a class of bug that's already bitten this project
    once. `PV ⊆ vars(.p)` needs a query spanning the whole subtree under
    `.p` (same shape as `TriplePatternListShape`'s `sh:sparql` approach,
    generalized), not a local per-node property shape — and there's no
    natural stopping point once you start down that road: SPARQL's real
    well-formedness rules (variable scoping, aggregate-expression
    restrictions, etc.) are a much bigger surface, and rdflib's own
    `_addVars`/`analyse`/`evalQuery` are already the ground-truth
    implementation of a lot of it, so re-deriving that independently in
    SHACL risks the two notions of "valid" drifting apart. The sibling
    `starShacl` (`pyshacl_starlayergraph`) project's SHACL 1.2 predicates
    (path-valued `sh:equals`/`sh:disjoint` in particular) may help express
    this kind of check more directly than plain `sh:sparql` — revisit
    when this is picked up; deliberately not used yet, per explicit
    instruction to stay on SHACL 1.1 for this pass.
- **The W3C SPARQL 1.2 test suite harness itself is built and running**
  (Phase 7, `tests/test_w3c_sparql12.py` — see that status entry above) —
  no longer "not started." Four originally-reported gaps were resolved in
  a follow-up pass (105/218 → 130/218) — see findings #15–#18 and the Phase
  7 status entry's fix-by-fix breakdown for what changed and why. What's
  still genuinely open:
  - ~~**`syntax-update-anonreifier-02`** (a `NegativeSyntaxTest`) — annotation
    syntax inside `INSERT DATA`/`DELETE DATA` still incorrectly parses.~~
    **Resolved in a later session, see finding #26** — turned out to need
    only a small post-translate semantic check, not the grammar redesign
    this bullet originally called for.
  - **A `<<...>>` reifier term's subject/object can't yet themselves be
    another reifier term or a nested ground triple term** — see finding
    #15's closing paragraph (`subject-tripleterm`,
    `nested-tripleterm-02`, `nested-reifier-02`, `nested-anonreifier-*`,
    and several `update-*reifier-*` syntax tests all trace to this same
    gap).
  - **StarLayer's own Turtle parser's `~ reifier` handling** (finding #18)
    and the **harness's dataset/`ConjunctiveGraph` limitation** for
    `.trig`/`.nq` fixtures using named graphs (also finding #18) — the
    first is out of this project's control without patching the sibling
    `starlayergraph` repo; the second needs the harness's
    `StarLayerGraph()` construction to become dataset-capable for
    multi-graph fixtures specifically.
  - **`list-anonreifier-01`/`list-tripleterm-01`** (`NegativeSyntaxTest`s) —
    an empty collection `()` as a triple term's/reifier term's own object
    still parses when the fixture expects rejection - see finding #24.
    Deliberately left open, not deferred-by-oversight: the fixture's own
    text carries a `# TODO: See if this should be throwing an error`
    comment, i.e. genuine spec ambiguity even the W3C suite's own authors
    flagged, not a clear-cut gap to close.
  - **`compound-tripleterm-subject`/`nested-tripleterm-02`**
    (`PositiveSyntaxTest`s) — correctly fail `test_syntax_positive`, a
    deliberate divergence from the suite's own label, not a bug: both
    exercise a triple term nested in *another* triple term's own subject
    slot, which is invalid RDF 1.2 regardless of parsing successfully as
    SPARQL text (`ttSubject ::= iri | BlankNode`, no `tripleTerm`
    alternative — see finding #27, which also documents how this project's
    own grammar previously, wrongly, treated these two fixtures as
    requiring acceptance). `InvalidTripleTermError` now rejects this shape
    at `TripleTermNode` construction, regardless of what parses.
  - `order-1`/`order-2`/`basic-9` and the two `results-*` tests have their
    own distinct root causes (an `ExpressionNotCoveredException` from
    `serialize12.py` for one shape, a `ValueError` from
    `starlayergraph.model.triple.TripleTerm`'s own nesting-restriction
    constructor for another) not yet individually triaged.
  - A real Oxigraph backend as a second execution leg alongside
    `StarLayerGraph` is still not wired up at all.
  - ~~A genuinely unresolved cross-test state-isolation bug... still means
    some fraction of both the 130 passes and the 88 remaining failures
    aren't fully trustworthy in combination...~~ **Resolved in a later
    session — see finding #25.** Root cause was a real, deterministic
    import-order hazard (`from_rdf.py`'s import-time grammar snapshot
    racing `grammar12.install()`), not a pytest/pyparsing mystery; fixed
    in `starsparql/__init__.py`. The suite's pass/fail counts are now
    confirmed stable (byte-identical) across repeated full runs — **216
    passed / 221 total** (2 failed, 3 skipped), the two failures being the
    deliberately-left-open, spec-ambiguous ones (finding #24).
- **Open question, come back to: is `TripleTermNode` actually aligned with
  the SPARQL 1.2 spec's own formal algebra, or only with rdflib+starlayergraph's
  pragmatic representation of one?** Tried to confirm directly against
  `https://www.w3.org/TR/sparql12-query/#algebraicSyntax` and couldn't get a
  definitive answer — the spec document is too large for available fetch
  tooling and truncated before reaching section 18 in every attempt tried
  (rendered TR page, editor's draft, raw source guess — the last 404'd on a
  wrong branch/path, not retried further). What's actually confirmed: the
  1.1-inherited operator vocabulary (`BGP`/`Filter`/`Join`/`LeftJoin`/
  `Union`/etc.) does genuinely match the spec's own algebra notation, not
  just rdflib's internal naming by coincidence — confirmed via a live
  spec-repo GitHub issue, `w3c/sparql-query#228`, quoting the spec's own use
  of "Filter" as an algebra-operator name in exactly this sense. What's
  *not* confirmed: whether the SPARQL 1.2 spec's formal algebra treats a
  triple term as a distinct first-class node the way `TripleTermNode` does
  (sitting directly in a triple's subject/predicate/object slot — the shape
  starlayergraph's parser happens to produce), or instead defines triple-term
  *pattern* matching via a rewrite/decomposition into ordinary BGP triples
  plus a bind (one secondary source described a `TR(triple pattern,
  variable)`/`Lift` construct for exactly this — but attributed to "the
  SPARQL-star/RDF-star extension," which may be the older CG precursor
  draft rather than the current official SPARQL 1.2 WD; not disambiguated).
  This project has never claimed literal transcription of the spec's
  algebra notation — the documented design has always been "mirror
  rdflib's internal `CompValue` tree," spec-inspired but not spec-verified
  — so for everything except triple terms this gap is low-risk (rdflib's
  1.1 algebra is well-established), but for `TripleTermNode` specifically
  it's a real open question worth resolving before treating this project's
  representation as canonical. Revisit once section 18 text is actually
  accessible (try smaller targeted fetches, or a different tool/session).
- **Making Phase 6's native `TripleTermNode`-bearing algebra tree directly
  executable in-process (no text round-trip at all)** — **done, in a later
  session**: `lower_rdf11.py`'s tree-level 1.2-algebra → 1.1-algebra
  lowering (`lower_algebra_to_rdf11`/`query_to_rdf11`/`update_to_rdf11` +
  `rdf11_to_query`/`rdf11_to_update`) is exactly this - no SPARQL 1.1 text
  anywhere in the path, a real, directly-executable `Query`/`Update` object
  handed straight to `StarLayerGraph`/`StarLayerDataset`. Built as the
  centerpiece of replacing starlayergraph's `sparql12_to_11.py` text rewriter
  entirely (that module is now deleted from `starlayergraph`; see that
  repo's own `CHANGELOG.md`). `rdf11_to_sparql11_text`/
  `_AlgebraTranslator11` (text serialization) still exists too, for cases
  that genuinely need text (a remote store that hard-requires a string) -
  not the default execution path, which needs no text at all.
- **Update serialization back to SPARQL text** — **done, in the same later
  session**: `rdf11_update_to_sparql11_text` (`lower_rdf11.py`) - covers
  `InsertData`/`DeleteData`/`DeleteWhere`/`Modify` (including `WITH`/
  `USING`) and all 7 graph-management operations (`Load`/`Clear`/`Drop`/
  `Create`/`Add`/`Move`/`Copy`). Built specifically for `starlayergraph`'s
  `native_update()` remote-rdf-1.1-store text path, which had no
  non-text-rewriting way to reach a store hard-requiring a plain string
  (`SPARQLUpdateStore.update()`'s own `assert isinstance(query, str)`).
  Not attempted: the W3C `update-*` test suite's own `.ru` fixtures still
  aren't wired up anywhere - this closed the *mechanism* gap, not that
  specific test-suite integration, which nothing in current scope needs.
- **`ASK`/`DESCRIBE` serialization** — same "no `_AlgebraTranslator` branch
  exists at all" gap `ConstructQuery` had before this session (see finding
  #14) — confirmed to also apply to these two, not pursued further since
  nothing in current scope needs them.
- **The "syntax layer" beyond Prologue** — original PName spelling,
  formatting/whitespace, comments. Not attempted; algebra-layer round-trip
  is semantically canonical but not textually faithful (e.g. `OPTIONAL`
  round-trips as the `LeftJoin` it always was, not literally as
  `OPTIONAL { }` text — though `translateAlgebra` does regenerate valid
  `OPTIONAL` syntax for that specific case since it's a direct algebra→text
  mapping, just without prefixes, per finding #3 above).
- ~~**Porting starlayergraph's `sparql12_to_11.py` regex rewriter onto this
  IR**~~ **Done - `sparql12_to_11.py` is deleted.** What was a stretch
  goal (flagged as higher-risk since it touches production code in the
  *other* repo) ran to completion across several sessions, culminating in
  the full removal (not just an opt-in flag) of starlayergraph's ~2,164-line
  hand-rolled text rewriter, replaced everywhere by this project's real
  grammar/algebra pipeline. Phase 0a (closing the `LANGDIR`/`hasLANGDIR`/
  `STRLANGDIR`/`hasLANG` grammar gap - the one real gap found between the
  two pipelines) through Phase 3 (flip the default, retire the old
  rewriter) are all complete; see `starlayergraph`'s own `CHANGELOG.md`
  for the full write-up, including several real bugs this migration found
  and fixed in *this* project along the way (a `CompValue.get()` footgun
  in `_lower_modify`, a missing-encoding-triples gap in `InsertData`
  lowering, `base`/`initNs` support added to `prepare_query_12`/
  `prepare_update_12`, a new `rdf11_update_to_sparql11_text` serializer,
  and the pytest/pyparsing grammar-corruption root cause finally isolated
  and fixed - see finding #31, now marked [RESOLVED]). `starlayergraph.query.
  parseQuery`/`prepareQuery`/`parseUpdate`/`prepareUpdate`/`processUpdate`
  (`sparql_api.py`) now delegate to this project's `parse12`/`lower_rdf11`
  directly instead of text-rewriting + post-hoc `TripleTerm` reassembly.
- ~~**Remove this project's backwards dependency on `starlayergraph`**~~
  **Explicitly decided against, per direct instruction (same later
  session as above): this project's dependency on `starlayergraph`
  stays, and `starlayergraph` is gaining a matching dependency on this
  project too - a two-way dependency between the two packages is
  intentional, not a defect to engineer around** (this project is treated
  as part of `starlayergraph`'s own SPARQL engine layer, not an
  independent generic library - see that repo's own `todos.md`).
  `lower_rdf11.py` is not being relocated; its existing
  `starlayergraph.model.encoding`/`starlayergraph.query.algebra_translator_patches`
  imports stay exactly as they are. The dirLangString neutral-encoding
  half of finding #30 (this project's *own* `vocab.py` encoding for
  `grammar12.py`/`serialize12.py`, distinct from starlayergraph's, so a
  `StarLayerGraph` never mistakes an in-flight encoded literal for one of
  its own) was already completed in an earlier session and remains in
  place - only the "relocate `lower_rdf11.py`" half of finding #30's
  proposed resolution is what's being explicitly not pursued.
- **Actual LLM integration/prompting** — explicitly out of scope for this
  project per the original plan; a separate downstream effort once the IR +
  validator + translator exist.
