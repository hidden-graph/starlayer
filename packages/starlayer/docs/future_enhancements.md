# StarLayer Future Enhancements

*Last reviewed: 2026-09-30*

Moved here from `packages/starlayer/docs/graph/` (2026-09-30) - this
document's content spans the whole merged `starlayer` package (graph,
SPARQL, and SHACL), not just the graph subpackage, so it belongs at the
package's own top level, not nested under one subpackage's docs.

---

## Open suggestions

- **DONE 2026-10-21: UI companion graphs for `shacl_shacl`** (was: create SHACL UI files for the validation files). The archived presentation shapes are back as the registered companion `shacl_shacl_ui` (`starontology/shacl12-shacl-ui.ttl`: 18 `sh:PropertyGroup` sections, `sh:group`/`sh:order` per predicate, `shui:editor` hints), and a baseline scoring catalog is registered as `shacl_ui_baseline` (one catalog for both roles). Done the same day: the overlay's widget preferences became `shacl_shacl_ui_scores` (a scoring layer on the generic catalog) and its 20 `stsh:widgetType` fields were dropped (no widget outside `shui:`; an application layer can bring them back). Open: review the text-field preference for `sh:targetClass` and its siblings; decide whether the catalog should be the default scoring graph (now opt-in); `starlayer-apps` may own the presentation content; the same two-file layer for `sqe`, `srl`, `manch`.
- **DONE 2026-10-17: the shape-authoring UI vocabulary (`stsh:` presentation shapes) was archived, not deleted.** Moved to the repo-root `docs/working/shacl-presentation/` (README there); the library no longer ships or merges it, and 66 of its 86 `stsh:widgetType` hints now use standard `shui:editor`. Open follow-ups: edit notebooks 05d and appendix-a (they list the removed `presentation_shapes` asset), refresh `shacl12-gap-matrix.md` prose, and decide whether `starlayer-apps` should own this content.

- *Done 2026-10-17:* **a project-side guard for the Oxigraph `dirLangString` `=` process abort** (upstream: oxigraph/oxigraph#1982). `starlayer/graph/backends/dirlang_equality.py` rewrites an equality that could compare two `dirLangString` terms (`=`, `!=`, `IN`, `NOT IN`) into an `IF(both are dirLangString, sameTerm(...), original)` before the query reaches Oxigraph, in the `execute_*` seam; automatic for an in-process Oxigraph, opt-in for a remote one (`store.starlayer_engine = 'oxigraph'`). See `docs/upstream-issues/oxigraph-upstream-issues.md` and `starlayer/graph/CLAUDE.md`. **To revisit:** retire the guard when upstream fixes the engine (the opt-in abort tests in `TestDirLangStringEquality` will then report that `=` no longer aborts). Residual: an equality whose operand calls `RAND()`, `NOW()`, `UUID()`, `STRUUID()`, `BNODE()` or `EXISTS` is left as written.

- **Use Oxigraph's direct Python API (`pyoxigraph`) for the store-touching primitives of an in-process Oxigraph graph, instead of going through SPARQL text** (2026-10-16, from the in-memory benchmark - `benchmarks-graph/bench_inmemory_oxigraph.py`). An in-process Oxigraph graph (`StarLayerGraph(store=OxigraphStore(...), backend='rdf-1.2')`, see `starlayer/graph/backends/native_oxigraph.py`) already sends `query()`/`update()` straight to Oxigraph's engine, which is where its large wins on triple-term queries come from (7-120x faster than the default store in the 50K-triple quick run). But every other operation - `add`, `addN`, `remove`, `triples`, `triples_choices`, `__len__`, `__contains__` - is still turned into SPARQL text and parsed by the engine, even though `pyoxigraph.Store` has direct calls for each: `bulk_extend`/`extend`/`bulk_load` (bulk load from `Quad` objects, no giant `INSERT` text to build and parse), `quads_for_pattern(s, p, o, g)` (an index scan, no query), `add`/`remove` (no per-triple `INSERT DATA`/`DELETE DATA`), and `named_graphs()`. The same quick run found single-subject lookups 9-10x *slower* than the default store - exactly the SPARQL-round-trip cost a direct `quads_for_pattern` call should remove. The work is bounded because these primitives already funnel through the `execute_*` seam in `native.py` and about seven `StarLayerGraph` methods (plus `StarLayerDataset.__len__`); SPARQL queries and updates, and everything built on the primitives (SHACL, entailment, canonicalization), would inherit the speedup unchanged, and remote HTTP stores would stay on SPARQL text since they have no direct API. **Needs:** a term converter from rdflib / `TripleTerm` / `DirLangString` to `pyoxigraph` `Quad`/`Triple`/`Literal` objects (the inverse of `_parse_ox_term()`, which already exists); keeping the two code paths in step via the cross-backend parity suite. **A real simplification this would bring:** the direct API takes real blank-node objects, so SPARQL Update's per-request blank-node scoping does not apply - on this path the skolemize/provenance machinery for blank nodes goes away. **Decide with data first:** measure the ceiling with raw `pyoxigraph` (load via `bulk_extend` vs `update()` with `INSERT` text; subject lookup via `quads_for_pattern` vs SPARQL; vs the default store) before writing it - if the direct calls are only ~2x faster the second code path may not be worth carrying, and documenting the lookup tradeoff would be enough.

- **Periodically re-check the W3C SPARQL 1.2 test suite for the 7 documented syntax-triple-terms-positive divergences** (2026-10-12, re-check procedure revised 2026-10-13) - `docs/sparql/w3c-sparql12-test-suite-issues.md` tracks 7 fixtures believed to be a suite defect (triple-term-as-subject, now `xfail(strict=True)` in `test_syntax_positive` so an upstream fix surfaces as an unexpected pass, not silent drift). That doc's own "Maintenance" section has the concrete re-check steps - as of 2026-10-13 the downloader fetches one pinned-commit tarball snapshot rather than live per-file requests, so a real check means bumping `PINNED_SHA` (via `git ls-remote`) and re-running, not just re-running as-is (re-running alone always reproduces the same pinned commit byte-for-byte now) - and the decision rule: if unchanged on re-check, file Issue 1 upstream against `w3c/rdf-tests` (not yet done as of this writing). A 2026-10-13 bump (incidental to an unrelated fetch-script consistency pass, not a dedicated re-check) found the 7 fixtures unchanged. (The eighth fixture this item originally also tracked, `list-anonreifier-01`, turned out to be a real implementation gap rather than suite ambiguity and was fixed the same day - see `starlayer/sparql/CLAUDE.md`.)

- **The code-KG extractor does not record imports between starlayer's own modules** (2026-10-19, found building the query library): `slkg:importsModule` points only at `slkg:ExternalModule` nodes, so "which module imports which" and import-based coupling cannot be answered; `subpackage-coupling` uses the call graph instead. Fix in `codekg/extractor/imports.py`/`visitor.py` by resolving project imports to `slkg:Module` nodes, then restore the competency question to answerable.
- **No HTML-rendered user guide exists** (migrated 2026-10-12 from the repo-root `Task List` scratch file, retired the same day after a full review - see that file's own git history for the original note). Confirmed still true: no `mkdocs.yml`/Sphinx `conf.py`/rendered HTML anywhere in the repo as of this writing - the guides are notebook-only (`docs/guides/*.ipynb`, readable on GitHub or via Jupyter, but not published as a browsable HTML site). Worth deciding whether this is actually wanted before building it (a notebook-rendering static-site generator, vs. just linking GitHub's own notebook preview) - no decision made yet, just confirmed the gap is real and still open.

- **Process question, not yet answered: why does real-usage testing keep surfacing bugs that the existing test suite didn't catch - does the testing approach itself need to change?** (migrated 2026-10-12 from the same retired `Task List` file, original wording: "why are we still finding bugs? need to expand testing? different approach?"). Not a concrete code gap - a standing question about testing methodology, carried forward rather than dropped since it's never actually been answered anywhere in this project's own docs. One partial, suggestive data point from the same day this item was migrated: a dedicated retrospective performance audit (triggered by a direct user question, not by any existing test failing) found four independent, real, previously-undetected bugs purely by profiling real call patterns rather than by unit-testing individual functions in isolation (unbounded global grammar growth, a factorial brute-force search, an O(n) `__len__`, an uncached meta-validation pass - see `starlayer/graph/CLAUDE.md`/`starlayer/shacl/CLAUDE.md`/`starlayer/sparql/CLAUDE.md`'s 2026-10-12 entries). None of these were wrong *outputs* a correctness-focused unit test would have caught - they were real-world-usage-pattern costs (repeated calls, cumulative state, realistic data shapes) invisible to tests that each exercise one function once, in isolation, with trivial input. Worth considering whether this suite's own testing strategy should add a periodic "run realistic, repeated, larger-scale usage patterns and profile them" pass alongside its existing per-function correctness tests - not yet decided or scheduled.

- **rdflib bugs: mostly consolidated; a tail remains** (2026-10-17). `docs/upstream-issues/rdflib-upstream-issues.md` now lists 12 confirmed bugs, each with a minimal plain-rdflib repro (added: `FILTER` variable loss, `INSERT DATA` into a `Dataset`, `REPLACE` flags, `STRLANG` empty tag, decimal lexical form). Items 11, 13 and 14 are now fixed (`STRLANG` patch; `starlayer/sparql/_syntax_checks.py`). Still open (the escapes are strict xfails in `tests/sparql/w3c_sparql12/`): escapes that spell a keyword or sit inside a prefixed name (`codepoint-esc-01-bad`, `-03-bad`), and, for simple literal vs `^^xsd:string` (item 15), `Literal.__eq__` and triple-pattern matching (only `sameTerm()` is fixed).

- **Notebooks never show how to fetch one of `starontology`'s own bundled registry files directly by URL, bypassing `starlayer`'s Python API entirely** (2026-10-11, found while reviewing `04e-shacl-profiling.ipynb` Section 4) - every example in the guides reaches a registry file (`skos_shapes.ttl`, the conformance-profiles mapping, etc.) through a function call (`starontology.get_ontology_graph()`/`get_conformance_profiles()`), never by handing a plain `Graph().parse(location=url)` the file's own URL directly the way any other RDF consumer on the web would.

  **A real, concrete blocker found while checking this live, not just a missing demo**: the resource IRIs this project already mints and uses everywhere (`get_resource_iri()`, every `prof:hasArtifact`/`prof:isProfileOf` object in `ontology-shapes-profiles.ttl`) are GitHub **blob** URLs - e.g. `https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/skos_shapes.ttl`. Confirmed via a live `curl`: that URL returns `content-type: text/html` (GitHub's own syntax-highlighted file-viewer page), not the Turtle content - `Graph().parse(location=...)` against it would fail outright, not silently misparse. The actual fetchable file lives at the **raw** equivalent, `https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/starontology/skos_shapes.ttl` (confirmed `200 OK`, `content-type: text/plain`, real file bytes) - and GitHub's own blob-URL response even advertises this via an `x-raw-download` response header, confirmed live in the same check.

  So this isn't just "add a notebook cell" - the resource identity scheme itself currently can't be dereferenced as-is. Two distinct things worth deciding, not conflating: (1) whether the identity URL *itself* should become the raw form (a breaking change to every already-published `prof:hasArtifact` IRI in `ontology-shapes-profiles.ttl` and the bundled conformance assets), or (2) whether a notebook should just show the *separate*, non-identity-changing move of deriving the raw URL from the blob URL (a mechanical `blob/` → `raw.githubusercontent.com` rewrite) purely as a "how to fetch the actual bytes" convenience, leaving the blob URL as the resource's own stable identity untouched. Likely (2) for a notebook addition - (1) is a bigger, separate design question about what these IRIs are *for* (human-readable identity vs. machine-fetchable location - the two are allowed to differ, and dx-prof's own `prof:hasArtifact` doesn't require they be the same URL).


- **Build a dedicated user guide for `validate()`/`StarShaclSchema` validation itself** (2026-10-09) - none of the existing `docs/guides/04*` notebooks cover the validation call's own full parameter surface in one place. `04-shacl-shapes.ipynb` is about authoring shapes; `04a`-`04f` each cover one specific SHACL 1.2 spec document (node expressions, rules, SPARQL, UI, profiling, subgraph extraction). None walks through `validate()`/`StarShaclSchema` comprehensively: `mode=` (validator option presets), `shapes_graph_resource=` (2026-10-09, redesigned 2026-10-10 - one value, either selecting a named `sh:ShapesGraph` module to validate against or tagging the report's provenance, depending on what's actually in the bound `shacl_graph` - see `starlayer/shacl/CLAUDE.md`'s dated entry), `data_graph_iri=` (report provenance), `shapes_graph_loader=`/`ignore_imports=` (`owl:imports` handling), `meta_shacl=`, `rdfs_subclass_reasoning_includes_shapes_graph_resource=`, `include_used_configuration=`, `decode_report=`, the `ValidationResult` object's own fields, and `validate_each()`. Found while building out `04e-shacl-profiling.ipynb`'s own Section 1/2 examples, which ended up exercising several of these without a home guide to send a reader to for the full picture.
- *Closed 2026-10-17:* **`ValidationResult.report_text` versus `report_graph`.** The `sh:conformsTo` and used-graph statements were closed 2026-10-10 by the `Provenance:` block (made data-driven 2026-10-17: no "Not specified" placeholders, no block when nothing is known). The remaining question, whether other post-processing leaves the text behind, found one divergence: for a `sh:Debug`/`sh:Trace`-only result pySHACL's text said `Conforms: False` while the recomputed value and the graph said true. `_sync_report_text_conforms` now corrects that line. See `starlayer/shacl/CLAUDE.md`.
- Add SHACL Compact syntax to the roadmap - already tracked in
  `docs/generated/functionality-overview.generated.md`'s `starshacl` deferred list (an
  ontology/shape over the syntax to drive validation and an editor,
  mirroring the Manchester/SPARQL AST-as-RDF pattern). Not repeated here.
- For the functionality overview, incorporate a reference from each item
  to where that functionality is shown in a user guide. Create a stub
  guide for anything not yet covered by one.
- Enhance the backend-stores guide with a discussion of backend stores'
  own inference settings - likely Fuseki-only for now.
- Create a user guide for `StarLayerGraph.derive_shape()` (creating a SHACL
  shape from a graph's own data) - the method exists, no guide covers it
  yet.
- Consider adding a `processQuery(graph, queryString, ...)` to
  `starlayer.graph.query.sparql_api` for symmetry with the existing
  `processUpdate`, found while reviewing the api-reference.md doc
  (2026-10-04). rdflib itself only defines `processUpdate`, not
  `processQuery` - confirmed by reading both `Graph.update()`'s and
  `Graph.query()`'s own source: they're architecturally identical
  (`use_store_provided` dispatch preferring the store's own native
  query()/update() if available, else falling back to the pluggable
  processor), and `processUpdate` exists specifically to bypass that
  entire layer and call `evalUpdate()` directly - a real, different code
  path from `graph.update()`, not just an alternate spelling. The same
  bypass would be equally meaningful on the query side via `evalQuery`
  (which already exists in rdflib, operating on an already-prepared
  `Query` object), so there's no principled reason only updates get this
  escape hatch - just an asymmetry in rdflib's own public API that
  `sparql_api.py` currently mirrors as-is rather than closing. Low
  priority: no confirmed caller has asked for this, and it would be new
  surface area StarLayer invents rather than a gap rdflib itself expects
  wrapped.
- Consider making `StarLayerGraph.addN(quads)` accept plain triples
  (3-tuples), not just quads (4-tuples), found while reviewing the
  api-reference.md doc (2026-10-04). Inherited directly from plain
  `rdflib.Graph.addN()` (confirmed identical failure on both):
  `g.addN([(s, p, o)])` raises `ValueError: not enough values to unpack
  (expected 4, got 3)`, because `addN()`'s own source unconditionally
  unpacks `for s, p, o, c in quads` even on an ordinary `Graph` that only
  ever has one context - so adding bare triples in bulk requires the
  caller to manually tag every one with the graph itself first
  (`g.addN((s, p, o, g) for s, p, o in triples)`). Worse than just
  verbose: this isn't "the context is ignored" - it's a silent *filter*.
  Confirmed directly: `c.identifier is self.identifier` for each quad's
  4th element determines inclusion, and anything else (an unrelated
  graph, a plain string, a typo'd identifier) causes that triple to be
  dropped with no error, not added with the mismatched context
  discarded. A fix would detect 3-tuples vs 4-tuples by length and
  default the context to `self` for the 3-tuple case - unambiguous and
  backward-compatible (existing quad-based callers see no change), but
  it's new behavior beyond what rdflib's own `addN()` provides, not a
  bug fix, so it needs a deliberate decision to diverge from the
  "drop-in replacement for rdflib" contract `StarLayerGraph`'s other
  overrides otherwise hold to exactly (see the `processQuery` entry
  above for the same tension).
- **Survey every plain-inherited (`Unchanged`) method on `StarLayerGraph`/
  `StarLayerDataset` that returns `None`, and consider adding a
  StarLayer-specific override that returns `self` instead - for
  chaining consistency with the rest of the mutating-method surface
  (`add()`/`remove()`/`addN()`/`add_reification()`, all fixed or added
  2026-10-04 to return `self`). Found while reviewing the
  api-reference.md doc (2026-10-04): `bind()` (both classes),
  `StarLayerDataset.print()`, and `StarLayerDataset.remove_context()`
  all confirmed via `inspect.signature()` against plain rdflib to
  genuinely return `None` there too - these are real, unmodified rdflib
  behavior, not a StarLayer gap, so **deliberately not touched now**.
  Unlike the `add_reification()` fix, this would mean diverging from
  rdflib's own return contract for an *inherited* method (not adding a
  return value to a StarLayer-original one) - the same
  "drop-in-replacement" tension the `processQuery`/`addN` entries above
  already describe, just for a different method category. Revisit as a
  deliberate, scoped decision (likely: override each one explicitly to
  add `return self`, matching the chaining convention, rather than
  leaving some mutating methods chainable and others not for no
  principled reason) - not something to fix opportunistically one
  method at a time.

- **Build a generic check that compares every StarLayer function/method
  against rdflib's own `Unchanged` behavior**, found while reviewing the
  api-reference.md doc (2026-10-05). This review session found several
  real behavioral-consistency gaps by manually comparing live
  `inspect.signature()`/actual calls against plain rdflib's own equivalent
  (the chaining-contract fixes, `triples_choices()`, the
  `MultipleGraphsError` consistency work) - each found ad hoc, one method
  at a time, not via any systematic sweep. A reusable version (e.g. a test
  or script walking every `Modified`/`Unchanged` entry in
  api-reference.md, or every method on `StarLayerGraph`/`StarLayerDataset`,
  and checking for divergence from the plain rdflib equivalent's real
  behavior, not just its signature) would catch this class of issue
  proactively instead of one review pass at a time.
  - **Example already found**: `n3()` is inconsistent in practice across
    term types read from the same graph. `TripleTerm.n3()` (a StarLayer-
    original method) remembers a `_namespace_manager` stamped on it by
    `StarLayerGraph._restore()`, so a bare `tt.n3()` call shows prefixed
    names; `URIRef`/`BNode`/`Literal`'s `n3()` are genuinely `Unchanged`
    rdflib methods with no such memory, so a bare `.n3()` call on them
    always shows the raw, unprefixed URI - confirmed live: the same
    `g.triples()` iteration returns a `URIRef` rendering
    `<http://example.org/bob>` right next to a `TripleTerm` rendering
    `<<( ex:alice ex:knows ex:bob )>>`. Not a bug (`URIRef` etc. can't be
    given instance state without modifying rdflib's own classes), but a
    real surprise for anyone mixing term types in output - worth a
    deliberate decision either way (document as expected, or make `n3()`
    consistent some other way) rather than leaving it an accidental gap.

- **SRL's own documented scope-reduction precedent** (recorded here
  explicitly 2026-10-05, after the user didn't recall it existed when
  discussing `sqe:`'s own v1 scope - worth not losing again):
  `starlayer/sparql/srl_grammar.py`'s module docstring lists SRL's own
  deliberate scope reductions explicitly (e.g. only `;`-chained property
  lists, not `,`-chained object lists; no property paths beyond a bare
  IRI/`a` predicate; `IMPORTS` a hard rejection rather than resolved) -
  "not oversights." Any new vocabulary/grammar built in this project
  going forward should follow the same discipline: state what v1
  deliberately excludes, in the module's own docstring, rather than
  leaving a gap for someone to later mistake for a bug.

- **`starlayer.sparql.sqe` - built 2026-10-05**, a new, hand-designed
  RDF vocabulary for editing a SPARQL `SELECT`/`ASK`/`CONSTRUCT` query as
  a flat, human-readable tree (paired with its own SHACL shapes designed
  for UI-editor field-level validation), sourced from the raw parse tree
  rather than `salg:`'s resolved algebra - see
  `starlayer/sparql/sqe/vocab.py`'s own module docstring for the full
  design rationale and `/clever-napping-mountain.md`-style plan this
  followed (comparison against `manch:`/`srl:`, why `salg:`/`ssyn:`/
  `sast:` don't already serve this purpose). **v1 scope, deliberately
  reduced, mirroring the SRL precedent above**: `SELECT`/`ASK`/
  `CONSTRUCT` only (no `DESCRIBE`); `WHERE`-clause limited to triple
  patterns, `OPTIONAL`, `UNION`, `FILTER`, `BIND`.

  **Widened 2026-10-18 (the v1 limits above no longer apply):** sqe now
  also covers solution modifiers, `SELECT *`, `CONSTRUCT WHERE`, projected
  expressions, aggregates with `GROUP BY`/`HAVING`, sub-selects, `VALUES`,
  `MINUS`, `GRAPH`, `EXISTS`, every expression builtin, and the SPARQL 1.2
  additions (triple terms, reifiers, annotations, base-direction strings).
  Still not covered: `DESCRIBE` and SPARQL Update. The coverage is measured,
  not assumed: the opt-in test set (`pytest --sqe-coverage`) runs every W3C
  SPARQL 1.2 query fixture and a per-feature suite through sqe against a
  StarLayerGraph/Dataset (see `starlayer/sparql/CLAUDE.md`'s 2026-10-18
  entry). Earlier docs and notes that described sqe as covering "queries"
  generally were wrong at the time they were written (a probe of 34 real
  questions passed only 11) - they are corrected, not just superseded.

  **Open follow-up, deliberately not resolved as part of building
  `sqe:`**: once `sqe:` is in real use, revisit whether `salg:` (the
  algebra encoding) still has a genuine consumer. Unlike `sast:`/`ssyn:`
  (explicit, unfinished prototypes for the exact purpose `sqe:` now
  serves properly - real candidates for retirement, see below), `salg:`
  represents something genuinely different in principle - the *resolved
  execution plan*, not the authored syntax - but nobody has named a
  concrete consumer for that distinction either (same open question as
  `sqe:`'s own validation use case, discussed the same session). Don't
  let `salg:` keep its place by default just because it's already built
  and tested.

  **Cleanup, scheduled for after `sqe:` is proven in real use, not done
  as part of this initial build**: `sast:` (`to_ast_rdf.py`/
  `from_ast_rdf.py`/`ast_vocab.py`) and `ssyn:` (`to_ssyn_rdf.py`/
  `ssyn_vocab.py`) become dead prototypes once `sqe:` covers their shared
  purpose - confirmed via `grep` that nothing outside their own test
  files depends on either, except `srl.py`'s real dependency on
  `ssyn_to_text.render_expr_text` (vocabulary-independent - renders an
  already-decoded `Expr` tree to text - so a third consumer alongside
  `sqe:`'s own `to_text.py`, which currently imports it from its present
  location too). Before deleting `ssyn:`: move `render_expr_text` out of
  `ssyn_to_text.py` into its own small, neutral module (e.g.
  `packages/starlayer/starlayer/sparql/sqe/expr_text.py`) first, and update both `srl.py`'s and
  `sqe/to_text.py`'s imports (sqe no longer imports it, as of 2026-10-18) to the new location - so neither depends on
  a module slated for deletion. Then delete the rest of `ssyn:`/all of
  `sast:` plus their test files (`test_ast_ontology.py`,
  `test_ssyn_ontology.py`), and update `starlayer/sparql/CLAUDE.md`'s
  file map and `docs/generated/api-reference.generated.md`'s "Lower-level" table accordingly.

- **Consider a lightweight "expand SHACL rules only, skip constraint
  validation" path**, found 2026-10-06 while auditing `starlayer.shacl`
  against pyshacl's own public surface (`__init__.__all__`). pyshacl's
  `shacl_rules()`/`RuleExpandRunner` is a dedicated entry point that does
  rule expansion *only* - `StarShaclSchema.apply_rules()` always routes
  through `self.validate(profile="rules")` instead, which always also
  runs full SHACL constraint checking (the `"rules"` profile in
  `profiles.py` has no flag to skip it). No data is lost -
  `RulesResult.inferred_graph` already carries the rule-produced triples
  (the "inference graph" - see `starlayer/shacl/CLAUDE.md`'s 2026-10-07
  entry on this), plus a bonus validation report `shacl_rules()` wouldn't
  give you - but there's no way to get rules-without-validation
  specifically, which costs unnecessary constraint-checking work for a
  caller who only wants the expansion. **Before implementing**: check
  whether the SHACL 1.2
  Inference Rules draft (`packages/starlayer/docs/shacl/shacl12-gap-matrix.md` tracks it) says
  anything that bears on whether rule expansion and validation are meant
  to be separable operations in SHACL 1.2 specifically, not just in
  pyshacl's own (SHACL-AF-era) API shape - `apply_rules()`'s own
  `rule_set`/`include_source_rule_provenance` parameters are already
  SHACL-1.2-specific extensions pyshacl's `shacl_rules()` has no concept
  of, so a bare pass-through to it would be wrong regardless; this entry
  is about whether a *new*, SHACL-1.2-aware "rules only" mode is worth
  building, not about using pyshacl's existing one as-is.

- **`sh:entailment` + rule execution - built 2026-10-07, re-verify against the final spec once it stabilizes.** Worked out and implemented by reading the live SHACL 1.2 Core and SHACL 1.2 Inference Rules editor's drafts directly (both still Working Draft/Editor's Draft, not stable text - the trigger to re-check this). **Status: fully built and tested** - `infer()`/`query()` speak the real W3C regime IRIs directly (`ENTAILMENT.*`, replacing the old starlayer-internal strings - see `starlayer/graph/CLAUDE.md`'s dated entry), `infer()` gained a native `ENTAILMENT.RDF` materialization path, and `starlayer.shacl.entailment` now reads `sh:entailment` from a shapes graph and wires it into `StarShaclSchema.validate()`/`apply_rules()` (see `starlayer/shacl/CLAUDE.md`'s own dated entry for the full account, including a real inplace-mutation regression found and fixed via testing). `tests/shacl`: 1065 passed, zero regressions.
  - Core §1.4: `sh:entailment` is a **shapes-graph-level** declaration ("a shapes graph contains any triple with the predicate `sh:entailment`"), not scoped to an individual shape. Multiple declared regimes combine into **one** entailment pass, not one pass per regime: "the processor MUST provide the entailments for all of the values of `sh:entailment`... during the validation process" (plural values, singular process).
  - Inference Rules spec: "validation engines that... execute the rules... prior to performing the actual validation" - rules run before validation, producing an evaluation graph (base graph ∪ inference graph) that validation then checks.
  - **Neither document says anything about the other's mechanism.** Core's entailment guarantee is scoped to queries made "during the validation process"; the Inference Rules spec never mentions `sh:entailment` at all. Whether entailed triples are supposed to be visible *to rules while they execute* (not just to the validation step that follows) is genuinely unspecified by either text - this is a real gap between two still-moving documents, not something we resolved by finding the answer.
  - **Design implemented as our own reasonable extrapolation, not a cited requirement**: `sh:entailment` runs over the data graph *before* executing any rules (so rules see entailed facts, the same way they already see the unconditional `rdf:type`/`rdfs:subClassOf` "SHACL type" closure that needs no entailment declaration at all), then runs again over the resulting evaluation graph (base ∪ every inferred triple, shape-attached and global alike) before the final conformance check - so newly-inferred triples get the same entailment treatment the original data graph did, rather than silently missing out on it. **Before relying on this further**: re-check against whatever the SHACL 1.2 Core and Inference Rules documents say once they're closer to final (see `docs/shacl/shacl12-gap-matrix.md`) - the rules/entailment interaction specifically might get clarified (or resolved differently) in a later draft.
  - **`ont_graph` limitation closed, 2026-10-07**: `apply_entailment()` (and pySHACL's own `inference=`, also replaced the same day with an equivalent routed through `StarLayerGraph.infer()`) now compute entailment over `data_graph` union `ont_graph`, materializing only the newly-entailed delta back - `ont_graph` itself is never mutated or copied in wholesale. See `starlayer/shacl/CLAUDE.md`'s dated entry for the full design and the real `CustomRDFSSemantics` parity wrinkle found and accounted for along the way. **`StarShaclSchema.validate()`'s own class method gained both fixes too, same day** - not via step 2 of the bare-function flip (still not done, see that section's own entry), but by mirroring the same two code changes directly into the class method's still-duplicated body, after a direct user question ("I thought we would be running this through the graph inference engine, so we ensure comparable results") surfaced that its `inference=` was still silently running pySHACL's own separate internal reasoning. `apply_rules()`'s class method already had both, since it already delegates to the bare function (unlike `validate`/`validate_each`/`evaluate`).

- **Repo-wide stale `starlayergraph` import, found 2026-10-07 while `nbconvert`-verifying the entailment-regime work above** - a leftover from before this project's own `starlayergraph`→`starlayer` package merge. `from starlayergraph import ...`/`from starlayergraph.graph.owl_dl import ...` still appears in **20+ guide notebooks** under `docs/` (confirmed via `grep -rl "from starlayergraph\|import starlayergraph" docs/`), making every one of them fail to execute via `nbconvert` - not a cosmetic issue, a real broken-guide bug. Fixed only in the 3 notebooks the entailment-regime work actually touched (`03a-sparql-inferencing.ipynb`, `06b-backend-graph-databases.ipynb`, `02c-owl-dl-reasoning.ipynb` - renamed since, see `docs/guides/README.md`), scoped deliberately on explicit user instruction - the other ~17 are still broken. Worth a dedicated sweep later: find every stale `starlayergraph` import across `docs/`, replace with the real `starlayer`/`starlayer.graph` path, and re-execute each touched notebook via `nbconvert` to confirm, the same verification discipline used for the 3 already fixed.

**Done**: "produce a documentation doc outlining every method/import
available under `starlayer`" → `docs/generated/api-reference.generated.md`,
built 2026-09-30.

---

## Review how well the guides demonstrate the capabilities (2026-10-19)

The curated capability list (`codekg/curated/functionality.ttl`) and the guide notebooks should describe the same thing, and the notebook links (`codekg/curated/notebook-links.ttl`, 31 so far) are the bridge. A first pass found gaps in both directions. Revisit them, ideally with the `review-notebook-links` skill, once the guides settle.

- **Capability symbols no guide cell demonstrates.** `derive_shape`, `apply_entailment`, `select_widget` (only `select_widgets` is shown), `graph_diff`, `declared_conformance`, the RDF and RDFS entailment helpers, `StarQuery`, the Rust OWL-DL engine module, and `CanonicalizationComplexityError`. For each, decide whether the guides should cover it (a cell or a section) or whether it is internal and should not be named by a capability.
- **Things the guides demonstrate that the capability list does not name.** (SPARQL 1.2 Update was added as `cap-sparql-5` on 2026-10-19.) `infer()` returning only the delta or mutating in place (02b, section 5); caching query-time entailment with `infer=` (03a); delegating reasoning to the store with `entailment="native"` on Fuseki (06b, section 1.2); class unsatisfiability detection in OWL-DL (02c, section 2). Candidates for new capabilities or for widening an existing one.
- **Guide ideas that are patterns, not capabilities.** Hash a tracked subgraph and re-verify it (04f, sections 5 and 12); use the OWL-DL reasoner as a constraint solver (appendix B2). Worth a line in the overview as "what you can build", not as a capability.
- **Weak links.** The link for the native backend (06b, cell `252791c5`) rests on a cell that sets up an endpoint demo and mentions the native layer only in a comment. Find or write a better cell.
- **Not covered by any guide or capability.** The reasoning timeout (`ReasoningTimeoutError`) has tests but no guide cell and no capability.
- **Keep it current.** The check (`python scripts/check_notebook_links.py`) catches edited, moved and broken cells but not new capabilities or new guide sections. A periodic review (each release) should compare the guide headings with the capability list again.

---

## SRL follow-ups (spec draft 2026-10-14)

*(Added 2026-10-17, from diffing `WD-sparql12-rl-20260919` against `WD-sparql12-rl-20261014`; what was fixed is in `starlayer/sparql/CLAUDE.md`.)* The 03b guide has a matching "Not yet covered" section to fill in as the open items land.

**Open**
1. **Aggregation (Issue 840).** *Trigger:* the draft gains grammar in §7.6 (today it has none) and a finished `evalAggregate`. *Then:* add the aggregation element to `_srl_ast.py`; the well-formedness conditions (keys in scope, aggregation variables distinct and new, functions over the pattern's variables); dependencies (the aggregation pattern is a closed dependency, and aggregation rules are run-once); the grammar and `ruleset_to_text`; the `srl:` RDF encoding and its SHACL shapes; evaluation (`COUNT`, `COUNT DISTINCT`, `MIN`, `MAX`, `SUM`; an error in a group drops that group); a guide section. *Until then:* an aggregate inside `FILTER` or `SET` is rejected at parse time.
2. **SRL-to-SPARQL translation (Issue 1303, Appendix A).** A placeholder in the draft; a worked algorithm would also give a way to run rule sets on a SPARQL engine.
3. **Re-diff the draft when it changes** (`/TR/sparql12-rl/` is a moving working draft); the date in the module docstrings and notes should follow.

**Resolved 2026-10-17**
- *`IMPORTS`.* Supported through a caller-supplied loader (`srl.resolve_imports`, `imports_loader=` on `infer()`/`query()`/`plan()`); import-once and the Appendix B merge as specified. No default loader on purpose (reading documents has security implications). Possible later additions: a ready-made directory loader, and caching of loaded documents.
- *Property paths in rule bodies.* The spec allows only `/` and `^` (§5, §7.6) and says arbitrary-length paths are written with recursion; both are supported, expanded into triple patterns when the rule is built, and every other operator is rejected with a clear message. Kept strict on purpose (decision 2026-10-17): no `|`, `*`, `+`, `?` or `!` extension.
- *Triple terms in rule text.* `<<( s p o )>>`, reified triples, reifiers and annotations parse, render, round-trip through RDF and evaluate, in bodies, heads and DATA blocks; `,` lists, `[ ]` and collections came with them. See `starlayer/sparql/CLAUDE.md`.
- *`parse_ruleset()` validates against the `srl:` shapes.* On by default, with `validate=False` to skip it. It costs about 140 ms per parse (the shapes run over the rule set's RDF encoding); that cost is accepted. Decision (2026-10-17): shapes are not re-implemented in Python to make this faster. Any speed-up has to come from the SHACL validator itself (a generic fast path), not from a hand-written copy of one shapes graph.
- *`data` renamed to the spec's `evaldata`, with the spec's polarity.* In the AST, the parser, evaluation, the `srl:` vocabulary (`srl:ruleEvaldata`/`srl:negationEvaldata`), the shapes, the published `.ttl` files and the 05c guide; no compatibility layer, so RDF written with `srl:ruleData`/`srl:negationData` no longer decodes.
- *rdflib `xsd:integer()` of a decimal/double/boolean was an error* (the spec's Examples 9 and 10 depend on it). Patched in `operator_patches.py` and recorded in `docs/upstream-issues/rdflib-upstream-issues.md` (item 7, not filed). The Examples now infer `:B :distanceKilometers 16`.
- *Blank-node rule ids.* The abstract syntax allows them, but the grammar (§7.6, `Rule ::= 'RULE' iri? ...`) only has an IRI, so there is no text syntax to add. The RDF encoding can already carry one.
- *Lint-level checks (literal head subject, duplicate rule ids, empty head).* The draft says nothing that forbids them: rule ids only "help identify" a rule, and a template term is "a variable or an RDF term". They stay accepted.
- *Parse-time stratification check.* The draft puts "check well-formed" and "calculate the dependency graph and stratification" in the *preparation for evaluation*, not in parsing. `parse_ruleset()` checks well-formedness (§4.2) and `plan()`/`infer()` raise `StratificationError`, which matches that split, so it stays as it is.

## Rationalize the three import mechanisms

*(Added 2026-10-17, after adding `IMPORTS` to SRL.)* The project now resolves imports in three places that were built separately, and they differ in naming and loader contract:

| | where | loader argument | loader returns | an import it cannot load |
|---|---|---|---|---|
| `owl:imports` on a graph | `StarLayerGraph.resolve_imports()` | `loader=` | a graph, or `None` | skipped, no error |
| `owl:imports` in SHACL validation | `validate(shapes_graph_loader=, ignore_imports=)` | `shapes_graph_loader=` | a graph, or `None` | skipped, no error |
| SRL `IMPORTS` | `srl.resolve_imports()`; `imports_loader=` on `RuleSet.infer()`/`.query()`/`.plan()` | `loader` (positional) / `imports_loader=` | SRL text or a `RuleSet` | `SRLImportError` |

The differences in error policy and in the merge (graph union with `owl:versionIRI` identity, against rules appended plus an RDF merge of `DATA` with blank nodes renamed) come from the specs and should stay. A single generic resolver is not worth it: its core is a visited set and a queue, about 15 lines, and the parsing step, the merge and the missing-import policy would all have to be parameters.

**To rationalize**
1. **Loader names.** Settle on one name for a loader argument across the three (`loader=` is the one `StarLayerGraph.resolve_imports()` already uses), and decide whether the SRL positional `loader` becomes keyword-only.
2. **Shared loaders.** Reading a document has security implications in all three, yet each caller writes its own loader today. Provide a small shared set so the safe choice is the easy one: a directory-confined loader, an allowlist-of-IRIs loader, and the bundled-files loader that already exists as `starontology.local_loader` (it returns graphs; SRL needs text or a `RuleSet`, so a thin adapter or a text variant is needed).
3. **Document the contract once**: what a loader receives (an IRI string or a `URIRef`), what it may return, what happens on failure, and that none of them has a default.
4. **Optional:** caching of loaded documents across calls, if resolving the same libraries repeatedly turns out to be slow.

*Not planned:* extracting the visited-set traversal into a shared helper, and changing the OWL/SHACL skip-on-failure behavior.

## Before publishing: clean-up checklist

*(Added 2026-10-17.)* Generated and hand-copied material goes stale as the code changes. Before a release or a doc publish, work through this list. None of it is automated yet; deciding which steps to fold into one script is itself a follow-up.

0. **One command for steps 1-3:** `python scripts/build.py` runs them in order (`--only starontology codekg apidocs overview` to pick some; `overview` is the functionality overview, built from `codekg/curated/functionality.ttl`). `python scripts/build.py --check` runs every step, compares each output with what is committed (graph isomorphism for the `.trig` files, bytes for the markdown), puts the committed files back, and exits 1 if anything is stale; CI runs it with `--skip codekg` (the code KG is repo tooling, rebuilt on demand, not checked in CI; the API docs are then checked against the committed `codekg.trig`). Build-time only; nothing in the library runs it.
1. **Refresh the code knowledge graph.** `python scripts/build_codekg.py --paths packages/starlayer/starlayer packages/starlayer/tests` rebuilds `packages/starlayer/starlayer/codekg/codekg.trig`.
2. **Regenerate the help/API docs** from that graph: `python scripts/generate_api_docs.py` writes `docs/generated/api-overview.generated.md` and `api-reference.generated.md`. Still open: whether `docs/generated/` is committed, and whether the generator joins step 1. `docs/generated/api-reference.generated.md` is the hand-kept predecessor and carries a stale-notice banner.
3. **Rebuild the starontology generated files**: `python scripts/build_starontology.py` regenerates `skos-ontology.ttl` and `shacl12-shacl.ttl` and assembles `starontology.trig` from the `.ttl` files, rewriting a file only when its graph changed. Run it after editing the validation shapes (`scripts/assets/shacl12-validation-shapes.ttl`), upgrading pySHACL, or editing any `.ttl` there; `--check` changes nothing and exits 1 if anything is stale (a test also fails while `shacl12-shacl.ttl` and a fresh build disagree).
4. **Refresh the widget appendix in `docs/guides/04d-shacl-ui.ipynb`.** The appendix is a deliberately *static* markdown table; the guide does not generate it when run. If the shipped widget descriptions change, regenerate it with the snippet below and paste the output over the appendix cell. The guide expects 16 editors and 10 viewers.
5. **Re-execute every guide** so the stored outputs are current: `BROWSER=true python -m jupyter nbconvert --to notebook --execute --inplace docs/guides/<guide>.ipynb` (`BROWSER=true` stops the UI guide opening pages).
6. **Run the test tiers**: the fast tier, the integration tier (live servers), `pytest --store-matrix` for the W3C suites across every store, and `pytest --srl-stratification` for the extended SRL stratification checks (both are opt-in groups, see `tests/conftest.py`).
7. **Check the docs for stale claims**: counts (widgets, triples, tests), spec citations and dates, and the upstream-issue links.

Snippet that produced the 04d appendix tables (run from `packages/starlayer`):

```python
from starlayer import starontology
from starlayer.graph import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
SHUI = Namespace("http://www.w3.org/ns/shacl-ui#")
meta = starontology.get_ontology_graph("shacl_shacl")


def widget_table(kind):
    """A markdown table of the built-in shui: widgets whose name ends with `kind`."""
    widgets = sorted(
        w for w in set(meta.subjects(SH.description, None))
        if str(w).startswith(str(SHUI)) and str(w).endswith(kind)
    )
    rows = [
        f"| `shui:{str(w).removeprefix(str(SHUI))}` | {next(meta.objects(w, SH.name), '')} | {next(meta.objects(w, SH.description), '')} |"
        for w in widgets
    ]
    return "| Widget | Name | What it is |\n|---|---|---|\n" + "\n".join(rows), len(widgets)


editor_table, n_editors = widget_table("Editor")
viewer_table, n_viewers = widget_table("Viewer")
assert (n_editors, n_viewers) == (16, 10)
print(f"### Editors (`shui:editor`) - {n_editors}\n\n{editor_table}\n\n### Viewers (`shui:viewer`) - {n_viewers}\n\n{viewer_table}")
```

---

## Deferred / open follow-ups

- **rdflib 8 compatibility.** Currently built on and tested against rdflib 7.6.0 (`pyproject.toml` requires `rdflib>=7.0`). rdflib 8.0.0a0 (pre-release) was tested too; revisit compatibility when a stable rdflib 8 release ships.

- **More examples.** Only two exist today (`packages/starlayer/tests/shacl/vendor/shacl12-test-suite/tests/rules/examples/`); no example covers `StarLayerDataset` (multi-graph). Decide what's worth adding.

- **SPARQL 1.2 Protocol gap analysis done (2026-09-27), no action needed.** Full writeup: `packages/starlayer/docs/graph/sparql12_protocol_gap_analysis.md`. Bottom line: the 1.2 revision changes almost nothing at the protocol level (mostly editorial; the one new HTTP `QUERY` method and the `version` announcement mechanism are both optional). `starlayer/graph/backends/native.py` (the only code this spec's requirements land on - this project has no server-side SPARQL endpoint anywhere) already conforms to everything it needs to; its single-submission-mode choices (POST-direct for both query and update, `GRAPH`-clause-based dataset scoping instead of protocol-level parameters) are documented, deliberate design choices, not gaps. Three small, genuinely optional loose ends if ever revisited: round-tripping the already-computed in-band `VERSION` value onto the wire's out-of-band `version` parameter; verifying `Content-Type` before parsing a CONSTRUCT response; distinguishing HTTP 400 from 500 at the four HTTP call sites.

- **RDF 1.2 Interoperability spec gap analysis done (2026-09-27), not implementation-ready.** Full writeup: `packages/starlayer/docs/graph/rdf_interop_gap_analysis.md`. This spec (`rdf:PropositionForm`-based Full↔Basic encoding for triple terms) is still an Editor's Draft with its `basic-decode` algorithm literally unwritten ("Write this algorithm") and an open question on whether RDF 1.1 interop is even in scope - not comparable in maturity to the seven CR/WD documents `rdf12_sparql12_gap_analysis.md` tracks. This project already has three independently-designed, narrower analogs solving related problems differently (`compare.py::_decompose()`'s private-namespace blank-node encoding for canonicalization/reasoner bridges; `_intern_tt()`'s content-addressed URIRef encoding for in-memory storage) - none worth retrofitting onto the spec's vocabulary, since both are internal details no external caller ever observes. `jsonld12` itself was removed as a recognized format entirely (2026-10-02) rather than kept around as a partial format with no real spec to converge on, so there's no longer a live payoff for this spec on the JSON-LD side. Revisit once (if) this reaches Working Draft and JSON-LD gets a real RDF 1.2 companion spec of its own worth adding a format for.

  **Retrofit DONE (2026-10-18), on branch `triple-term-encoding`.** The internal triple-term encoding now uses the Interoperability vocabulary: each content-addressed node is typed `rdf:PropositionForm` and described by `rdf:propositionFormSubject/Predicate/Object` (the old `rdf:subject/predicate/object` reification terms are no longer used, so real reification data cannot be mistaken for the encoding). Only the node *name* differs from the spec (a stable content hash instead of a fresh blank node, which the spec's own decode rules would not match). Reads find triple terms by the type (registry rebuild is one indexed lookup; the hiding filters test the vocabulary, not the name). `serialize()` to a plain RDF format now yields the spec's basic encoding, and `parse()` of a plain format converts a basic-encoded document back into triple terms. Measured on a 22,000-triple graph with 2,000 triple terms: 7% more stored triples, parse 12% slower, `FILTER(isTRIPLE(?o))` was unchanged (553 vs 576 ms) while the SPARQL lowering still tested the name; a type-based join measured 27 ms against 343 ms on plain rdflib, so `isTRIPLE` over a variable bound by a graph pattern is now lowered into that join (576 ms down to 32 ms, same rows; `lower_rdf11._filter_is_triple_as_join`). Details: `starlayer/graph/CLAUDE.md`, 2026-10-18.

- **SPARQL entailment regimes not planned (and why).** Of the six regimes the [SPARQL 1.1/1.2 Entailment Regimes](https://www.w3.org/TR/sparql12-entailment/) spec defines, three have no plans to be built: **OWL 2 RDF-Based Semantics** (full, beyond the RL fragment already covered by `entailment="owl-rl"`) - undecidable in general (OWL Full has roughly first-order expressive power plus RDF's own reflective quirks); `owlrl`, the only OWL-RL dependency in this stack, implements the RL fragment specifically *because* that's the version with a terminating rule-based algorithm at all. **D-Entailment** (datatype canonicalization, e.g. recognizing `"01"^^xsd:integer` and `"1"^^xsd:integer` as the same *value*) - needs a full XSD datatype-map implementation inside the query engine's own term-equality logic; narrow and orthogonal to what this project exists for (RDF 1.2: triple terms, direction-tagged literals), and confirmed live against Jena's own docs that a Fuseki/Jena backend doesn't cover this either - an explicitly stated, deliberate gap in Jena's RDFS reasoner, not something delegating to a backend (`entailment="native"`) would close. **RIF Core Entailment** - no RIF interpreter anywhere in this stack, and no spec-conformance test infrastructure to verify one against even if built. (**OWL 2 Direct Semantics** is not in this bucket - `infer(profile="owl-dl")`/`query(entailment="direct")` cover it fully; see `packages/starlayer/starlayer/codekg/CHANGELOG.md`.)

---

## Guide review findings (2026-09-26)

A full editorial pass over every notebook under `docs/guides/` (five parallel review passes, one per topic area) fixed typos and confirmed-stale references directly - see each notebook's own history for the specifics; not repeated here. What's below is what those passes found but deliberately did *not* fix, because it was bigger than a typo/staleness correction - grouped by guide-content gaps vs. underlying library gaps. **Snapshot from that date** - some items may have been resolved since by unrelated work; re-verify before acting on any of them rather than assuming they're still open.

**Guide-content gaps:**
- `01-getting-started.ipynb`'s own "Where to go next" list has no entry at all for `05a-manchester-syntax.ipynb` (renamed from `05f-`, see `docs/guides/README.md`).
- `04-shacl-shapes.ipynb` §3.3: after correcting an overbroad claim about which constraint components support per-value severity annotation (see the starshacl gap below), the guide doesn't explicitly say the other three (`sh:uniqueMembers`/`sh:reificationRequired`/`sh:singleLine`) currently lack it.
- `06c-canonical-hashing.ipynb` (renamed from `05d-`, see `docs/guides/README.md`) narrates `.isomorphic()` in method-call style but only ever demonstrates the free function `starlayer.graph.compare.isomorphic()` - the bound `StarLayerGraph.isomorphic()` method (which exists, with its own more detailed TripleTerm-awareness docstring) is never shown or contrasted; ambiguous whether that's deliberate house style.
- `05a-manchester-syntax.ipynb`'s (renamed from `05f-`, see `docs/guides/README.md`) first markdown cell has a stray leftover editing instruction embedded in the guide's own prose ("CLAUDE: show this as a two column table.") - looks like an artifact from building the guide, not intentional content.

**graph/shacl subpackage gaps (code-level, found while reading the guides' own examples):**
- `infer(profile="owl-rl")`'s inconsistency signal (`err:error`/`err:ErrorMessage` triples) has no dedicated accessor - a caller has to know to filter the result graph for that namespace by hand. A convenience method (e.g. `graph.inconsistencies()`) would close an easy-to-miss footgun.
- `remove_reification(reifier, triple_term=None)` silently no-ops when `triple_term` isn't actually reified by that reifier - there's no way to distinguish "already gone" from "wrong reference/typo" anywhere in this API surface.
- `packages/starlayer/starlayer/shacl/subgraph_extraction.py`'s own module docstring (design decision #3) is stale relative to its own code: it still says `sh:or`/`sh:xone` extraction includes "only the branch that actually caused the pass... the first list member that conforms," which is correct for `sh:xone` but wrong for `sh:or` - the actual implementation (and the guide, correctly) includes *every* passing `sh:or` disjunct, per the 2026-09-13 revision recorded in this project's own memory/design notes. A one-line source-level docstring fix, not a behavior change.
- The per-constraint severity-annotation mechanism (`_annotation_value(...)`/`annotation_severity` in `packages/starlayer/starlayer/shacl/native_components.py`) is implemented once, ad hoc, inside `DatatypeConstraintComponent` rather than as a reusable mixin - if `sh:uniqueMembers`/`sh:reificationRequired`/`sh:singleLine` are meant to eventually support it too, the current structure requires duplicating it rather than reusing it. No test coverage exists for severity/deactivation annotations on any constraint type besides `sh:datatype`/`sh:property` either - not documented anywhere as a deliberate scope decision.
- `06b-backend-graph-databases.ipynb`'s (renamed from `05b-`, see `docs/guides/README.md`) two backend paths raise two different exception types on an unreachable endpoint - `urllib.error.URLError` for `backend="rdf-1.1"`, `requests.exceptions.ConnectionError` for `backend="rdf-1.2"` (native). A caller has to know which backend they're using just to catch the right exception; not documented as a known asymmetry anywhere in `packages/starlayer/docs/graph/`.
- `entailment="native"` is restricted to `backend="rdf-1.2"` only, even though `backend="rdf-1.1"` can also talk to a live SPARQL endpoint (via a `Store` plugin) and just can't delegate entailment to it. Possibly deliberate, but not called out as such anywhere.

---

## Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes

RDF 1.2 was at **Candidate Recommendation** (published 2026-04-07) as of this writing — not yet a final W3C Recommendation. Everything in this project (the gap analysis, the rewriter, the format modules) is checked against that CR-stage text. This project's own stated purpose (README: "intended to remain relevant until rdflib is updated to incorporate the final RDF 1.2 specification") means it has a deliberately limited lifespan, and needs periodic re-checking rather than a one-time gap analysis. Concrete steps for whoever picks this up as the spec progresses:

1. **Re-run the gap analysis at each W3C stage transition** (CR → PR → REC). CR-stage text can still change in response to implementation/horizontal-review feedback before Proposed Recommendation; re-diff `packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md` against the current editor's draft whenever the spec's status changes, not just once. `packages/starlayer/tests/graph/vendor/spec_snapshots/refresh_snapshots.py` automates the "what actually changed" half of that: it re-fetches all seven tracked documents and overwrites the saved snapshots, so `git diff packages/starlayer/tests/graph/vendor/spec_snapshots/` shows exactly what moved since the last review instead of requiring a full re-read.
2. **Watch the CR exit criteria / implementation report.** The RDF-star Working Group's CR exit requires a set of independent conforming implementations. Whichever engines end up counted (Oxigraph and Fuseki are the two this project already tracks) are worth re-verifying `starlayer.graph`'s rewriter against each time one of them ships a release claiming closer conformance — a live three-way comparison against the in-memory backend (see `packages/starlayer/tests/graph/integration/test_cross_backend_parity.py`) is the reusable tool for that, not a one-off.
3. **Watch for a real JSON-LD RDF-1.2 companion spec.** `jsonld12` was removed as a recognized format entirely (2026-10-02, see `packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md` §6) rather than kept as a partial "plain RDF 1.1 content only, refuse triple terms" format, since JSON-LD has no published RDF 1.2 companion spec at all. If the JSON-LD Working Group ever publishes an RDF-1.2-aware revision with its own native representation for quoted/triple terms, consider adding a real `jsonld12` format back for that representation. TriX has no standards body actively developing it, so `trix12` is unlikely to ever gain a real target to converge on — its "starlayer.graph convention, not a spec" status is probably permanent, and the documentation callout is the whole fix rather than a placeholder for a future code change.
4. **Once rdflib ships native RDF 1.2 support** — re-evaluate this project's continued existence, per its own stated scope. At that point: (a) consider deprecating `starlayer.graph`'s SPARQL 1.2→1.1 rewriter and in-memory triple-term encoding in favor of delegating straight to rdflib, and (b) check whether the `turtle12`/`nt12`/`nq12`/`trig12`/`rdfxml12` format modules can be dropped in favor of rdflib's own native parsers/serializers.
