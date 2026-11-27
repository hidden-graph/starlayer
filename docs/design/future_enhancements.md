# StarLayer Future Enhancements

*Last reviewed: 2026-09-30*

Moved here from `docs/design/graph/` (2026-09-30) - this
document's content spans the whole merged `starlayer` package (graph,
SPARQL, and SHACL), not just the graph subpackage, so it belongs at the
package's own top level, not nested under one subpackage's docs.

---

## Open suggestions

- **DONE 2026-10-21: UI companion graphs for `shacl_shacl`** (was: create SHACL UI files for the validation files). The archived presentation shapes are back as the registered companion `shacl_shacl_ui` (`starontology/shacl/shacl12-shacl-ui.ttl`: 18 `sh:PropertyGroup` sections, `sh:group`/`sh:order` per predicate, `shui:editor` hints), and a baseline scoring catalog is registered as `shacl_ui_baseline` (one catalog for both roles). Done the same day: the overlay's widget preferences became `shacl_shacl_ui_scores` (a scoring layer on the generic catalog) and its 20 `stsh:widgetType` fields were dropped (no widget outside `shui:`; an application layer can bring them back). Open: review the text-field preference for `sh:targetClass` and its siblings; decide whether the catalog should be the default scoring graph (now opt-in); `starlayer-apps` may own the presentation content; the same two-file layer for `sqe`, `srl`, `manch`.
- **DONE 2026-10-17: the shape-authoring UI vocabulary (`stsh:` presentation shapes) was archived, not deleted.** Moved to the repo-root `docs/working/archive/shacl-presentation/` (README there); the library no longer ships or merges it, and 66 of its 86 `stsh:widgetType` hints now use standard `shui:editor`. Open follow-ups: edit notebooks 05d and appendix-a (they list the removed `presentation_shapes` asset), refresh `shacl12-gap-matrix.md` prose, and decide whether `starlayer-apps` should own this content.

- *Done 2026-10-17, REMOVED 2026-10-31:* **a project-side guard for the Oxigraph `dirLangString` `=` process abort** (upstream: oxigraph/oxigraph#1982). `backends/dirlang_equality.py` rewrote equalities that could compare two `dirLangString` terms before they reached Oxigraph. The abort is fixed in Oxigraph 0.5.13, and the owner decided StarLayer supports only versions that do not abort, so the guard was deleted entirely and 0.5.13 is the minimum supported version (checked at import for pyoxigraph; a remote server cannot be checked). See `docs/upstream-issues/oxigraph-upstream-issues.md` and `starlayer/graph/CLAUDE.md`.

- **Use Oxigraph's direct Python API (`pyoxigraph`) for the store-touching primitives of an in-process Oxigraph graph, instead of going through SPARQL text** (2026-10-16, from the in-memory benchmark - `benchmarks/graph/bench_inmemory_oxigraph.py`). An in-process Oxigraph graph (`StarLayerGraph(store=OxigraphStore(...), backend='rdf-1.2')`, see `starlayer/graph/backends/native_oxigraph.py`) already sends `query()`/`update()` straight to Oxigraph's engine, which is where its large wins on triple-term queries come from (7-120x faster than the default store in the 50K-triple quick run). But every other operation - `add`, `addN`, `remove`, `triples`, `triples_choices`, `__len__`, `__contains__` - is still turned into SPARQL text and parsed by the engine, even though `pyoxigraph.Store` has direct calls for each: `bulk_extend`/`extend`/`bulk_load` (bulk load from `Quad` objects, no giant `INSERT` text to build and parse), `quads_for_pattern(s, p, o, g)` (an index scan, no query), `add`/`remove` (no per-triple `INSERT DATA`/`DELETE DATA`), and `named_graphs()`. The same quick run found single-subject lookups 9-10x *slower* than the default store - exactly the SPARQL-round-trip cost a direct `quads_for_pattern` call should remove. The work is bounded because these primitives already funnel through the `execute_*` seam in `native.py` and about seven `StarLayerGraph` methods (plus `StarLayerDataset.__len__`); SPARQL queries and updates, and everything built on the primitives (SHACL, entailment, canonicalization), would inherit the speedup unchanged, and remote HTTP stores would stay on SPARQL text since they have no direct API. **Needs:** a term converter from rdflib / `TripleTerm` / `DirLangString` to `pyoxigraph` `Quad`/`Triple`/`Literal` objects (the inverse of `_parse_ox_term()`, which already exists); keeping the two code paths in step via the cross-backend parity suite. **A real simplification this would bring:** the direct API takes real blank-node objects, so SPARQL Update's per-request blank-node scoping does not apply - on this path the skolemize/provenance machinery for blank nodes goes away. **Decide with data first:** measure the ceiling with raw `pyoxigraph` (load via `bulk_extend` vs `update()` with `INSERT` text; subject lookup via `quads_for_pattern` vs SPARQL; vs the default store) before writing it - if the direct calls are only ~2x faster the second code path may not be worth carrying, and documenting the lookup tradeoff would be enough.

- **Periodically re-check the W3C SPARQL 1.2 test suite for the 7 documented syntax-triple-terms-positive divergences** (2026-10-12, re-check procedure revised 2026-10-13) - `docs/sparql/w3c-sparql12-test-suite-issues.md` tracks 7 fixtures believed to be a suite defect (triple-term-as-subject, now `xfail(strict=True)` in `test_syntax_positive` so an upstream fix surfaces as an unexpected pass, not silent drift). That doc's own "Maintenance" section has the concrete re-check steps - as of 2026-10-13 the downloader fetches one pinned-commit tarball snapshot rather than live per-file requests, so a real check means bumping `PINNED_SHA` (via `git ls-remote`) and re-running, not just re-running as-is (re-running alone always reproduces the same pinned commit byte-for-byte now) - and the decision rule: if unchanged on re-check, file Issue 1 upstream against `w3c/rdf-tests` (not yet done as of this writing). A 2026-10-13 bump (incidental to an unrelated fetch-script consistency pass, not a dedicated re-check) found the 7 fixtures unchanged. (The eighth fixture this item originally also tracked, `list-anonreifier-01`, turned out to be a real implementation gap rather than suite ambiguity and was fixed the same day - see `starlayer/sparql/CLAUDE.md`.)

- **The code-KG extractor does not record imports between starlayer's own modules** (2026-10-19, found building the query library): `slkg:importsModule` points only at `slkg:ExternalModule` nodes, so "which module imports which" and import-based coupling cannot be answered; `subpackage-coupling` uses the call graph instead. Fix in `codekg/extractor/imports.py`/`visitor.py` by resolving project imports to `slkg:Module` nodes, then restore the competency question to answerable.
- **No HTML-rendered user guide exists** (migrated 2026-10-12 from the repo-root `Task List` scratch file, retired the same day after a full review - see that file's own git history for the original note). Confirmed still true: no `mkdocs.yml`/Sphinx `conf.py`/rendered HTML anywhere in the repo as of this writing - the guides are notebook-only (`docs/guides/*.ipynb`, readable on GitHub or via Jupyter, but not published as a browsable HTML site). Worth deciding whether this is actually wanted before building it (a notebook-rendering static-site generator, vs. just linking GitHub's own notebook preview) - no decision made yet, just confirmed the gap is real and still open.

- **Process question, not yet answered: why does real-usage testing keep surfacing bugs that the existing test suite didn't catch - does the testing approach itself need to change?** (migrated 2026-10-12 from the same retired `Task List` file, original wording: "why are we still finding bugs? need to expand testing? different approach?"). Not a concrete code gap - a standing question about testing methodology, carried forward rather than dropped since it's never actually been answered anywhere in this project's own docs. One partial, suggestive data point from the same day this item was migrated: a dedicated retrospective performance audit (triggered by a direct user question, not by any existing test failing) found four independent, real, previously-undetected bugs purely by profiling real call patterns rather than by unit-testing individual functions in isolation (unbounded global grammar growth, a factorial brute-force search, an O(n) `__len__`, an uncached meta-validation pass - see `starlayer/graph/CLAUDE.md`/`starlayer/shacl/CLAUDE.md`/`starlayer/sparql/CLAUDE.md`'s 2026-10-12 entries). None of these were wrong *outputs* a correctness-focused unit test would have caught - they were real-world-usage-pattern costs (repeated calls, cumulative state, realistic data shapes) invisible to tests that each exercise one function once, in isolation, with trivial input. Worth considering whether this suite's own testing strategy should add a periodic "run realistic, repeated, larger-scale usage patterns and profile them" pass alongside its existing per-function correctness tests - not yet decided or scheduled.

- **rdflib bugs: mostly consolidated; a tail remains** (2026-10-17). `docs/upstream-issues/rdflib-upstream-issues.md` now lists 12 confirmed bugs, each with a minimal plain-rdflib repro (added: `FILTER` variable loss, `INSERT DATA` into a `Dataset`, `REPLACE` flags, `STRLANG` empty tag, decimal lexical form). Items 11, 13 and 14 are now fixed (`STRLANG` patch; `starlayer/sparql/_syntax_checks.py`). Still open (the escapes are strict xfails in `tests/sparql/w3c_sparql12/`): escapes that spell a keyword or sit inside a prefixed name (`codepoint-esc-01-bad`, `-03-bad`), and, for simple literal vs `^^xsd:string` (item 15), `Literal.__eq__` and triple-pattern matching (only `sameTerm()` is fixed).

- **Notebooks never show how to fetch one of `starontology`'s own bundled registry files directly by URL, bypassing `starlayer`'s Python API entirely** (2026-10-11, found while reviewing `05.08-shacl-profiling.ipynb` Section 4) - every example in the guides reaches a registry file (`skos_shapes.ttl`, the conformance-profiles mapping, etc.) through a function call (`starontology.get_ontology_graph()`/`get_conformance_profiles()`), never by handing a plain `Graph().parse(location=url)` the file's own URL directly the way any other RDF consumer on the web would.

  **A real, concrete blocker found while checking this live, not just a missing demo**: the resource IRIs this project already mints and uses everywhere (`get_resource_iri()`, every `prof:hasArtifact`/`prof:isProfileOf` object in `ontology-shapes-profiles.ttl`) are GitHub **blob** URLs - e.g. `https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/skos/skos_shapes.ttl`. Confirmed via a live `curl`: that URL returns `content-type: text/html` (GitHub's own syntax-highlighted file-viewer page), not the Turtle content - `Graph().parse(location=...)` against it would fail outright, not silently misparse. The actual fetchable file lives at the **raw** equivalent, `https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/starontology/skos/skos_shapes.ttl` (confirmed `200 OK`, `content-type: text/plain`, real file bytes) - and GitHub's own blob-URL response even advertises this via an `x-raw-download` response header, confirmed live in the same check.

  So this isn't just "add a notebook cell" - the resource identity scheme itself currently can't be dereferenced as-is. Two distinct things worth deciding, not conflating: (1) whether the identity URL *itself* should become the raw form (a breaking change to every already-published `prof:hasArtifact` IRI in `ontology-shapes-profiles.ttl` and the bundled conformance assets), or (2) whether a notebook should just show the *separate*, non-identity-changing move of deriving the raw URL from the blob URL (a mechanical `blob/` → `raw.githubusercontent.com` rewrite) purely as a "how to fetch the actual bytes" convenience, leaving the blob URL as the resource's own stable identity untouched. Likely (2) for a notebook addition - (1) is a bigger, separate design question about what these IRIs are *for* (human-readable identity vs. machine-fetchable location - the two are allowed to differ, and dx-prof's own `prof:hasArtifact` doesn't require they be the same URL).


- **Build a dedicated user guide for `validate()`/`StarShaclProcessor` validation itself** (2026-10-09) - none of the existing `docs/guides/04*` notebooks cover the validation call's own full parameter surface in one place. `05.01-validating-with-shacl-1.2.ipynb` is about authoring shapes; `04a`-`04f` each cover one specific SHACL 1.2 spec document (node expressions, rules, SPARQL, UI, profiling, subgraph extraction). None walks through `validate()`/`StarShaclProcessor` comprehensively: `mode=` (validator option presets), `shapes_graph_resource=` (2026-10-09, redesigned 2026-10-10 - one value, either selecting a named `sh:ShapesGraph` module to validate against or tagging the report's provenance, depending on what's actually in the bound `shacl_graph` - see `starlayer/shacl/CLAUDE.md`'s dated entry), `data_graph_iri=` (report provenance), `shapes_graph_loader=`/`ignore_imports=` (`owl:imports` handling), `meta_shacl=`, `rdfs_subclass_reasoning_includes_shapes_graph_resource=`, `include_used_configuration=`, `decode_report=`, the `ValidationReport` object's own fields, and `validate_each()`. Found while building out `05.08-shacl-profiling.ipynb`'s own Section 1/2 examples, which ended up exercising several of these without a home guide to send a reader to for the full picture.
- *Closed 2026-10-17:* **`ValidationReport.report_text` versus `report_graph`.** The `sh:conformsTo` (now `sh:conformsToShapesGraph`) and used-graph statements were closed 2026-10-10 by the `Provenance:` block (made data-driven 2026-10-17: no "Not specified" placeholders, no block when nothing is known). The remaining question, whether other post-processing leaves the text behind, found one divergence: for a `sh:Debug`/`sh:Trace`-only result pySHACL's text said `Conforms: False` while the recomputed value and the graph said true. `_sync_report_text_conforms` now corrects that line. See `starlayer/shacl/CLAUDE.md`.
- Add SHACL Compact syntax to the roadmap - already tracked in
  `docs/generated/functionality-overview.generated.md`'s `starshacl` deferred list (an
  ontology/shape over the syntax to drive validation and an editor,
  mirroring the Manchester/SPARQL AST-as-RDF pattern). Not repeated here.
- For the functionality overview, incorporate a reference from each item
  to where that functionality is shown in a user guide. Create a stub
  guide for anything not yet covered by one.
- Enhance the backend-stores guide with a discussion of backend stores'
  own inference settings - likely Fuseki-only for now.
- Create a user guide for `starlayer.shacl.derive_shape()` (creating a SHACL
  shape for one class or one node from a graph's own data) - the function
  exists, and guide 05 still describes the old whole-graph method.
- Consider adding a `processQuery(graph, queryString, ...)` to
  `starlayer.graph.execution.sparql_api` for symmetry with the existing
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
  `DESCRIBE` and SPARQL Update are covered too (2026-11). The coverage is measured,
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

- **Done 2026-11-24: "expand SHACL rules only, skip constraint validation".** `apply_rules()` now only runs the rules and returns `RulesResult(inferred_graph)`; it validates nothing, because the shapes that check the outcome may differ from the shapes that hold the rules. To check a result: `validate(data, shapes, rules=True)`, or validate the data together with `result.inferred_graph` against any shapes.

- **`sh:entailment` + rule execution - built 2026-10-07, re-verify against the final spec once it stabilizes.** Worked out and implemented by reading the live SHACL 1.2 Core and SHACL 1.2 Inference Rules editor's drafts directly (both still Working Draft/Editor's Draft, not stable text - the trigger to re-check this). **Status: fully built and tested** - `infer()`/`query()` speak the real W3C regime IRIs directly (`ENTAILMENT.*`, replacing the old starlayer-internal strings - see `starlayer/graph/CLAUDE.md`'s dated entry), `infer()` gained a native `ENTAILMENT.RDF` materialization path, and `starlayer.shacl.entailment` now reads `sh:entailment` from a shapes graph and wires it into `StarShaclProcessor.validate()`/`apply_rules()` (see `starlayer/shacl/CLAUDE.md`'s own dated entry for the full account, including a real inplace-mutation regression found and fixed via testing). `tests/shacl`: 1065 passed, zero regressions.
  - Core §1.4: `sh:entailment` is a **shapes-graph-level** declaration ("a shapes graph contains any triple with the predicate `sh:entailment`"), not scoped to an individual shape. Multiple declared regimes combine into **one** entailment pass, not one pass per regime: "the processor MUST provide the entailments for all of the values of `sh:entailment`... during the validation process" (plural values, singular process).
  - Inference Rules spec: "validation engines that... execute the rules... prior to performing the actual validation" - rules run before validation, producing an evaluation graph (base graph ∪ inference graph) that validation then checks.
  - **Neither document says anything about the other's mechanism.** Core's entailment guarantee is scoped to queries made "during the validation process"; the Inference Rules spec never mentions `sh:entailment` at all. Whether entailed triples are supposed to be visible *to rules while they execute* (not just to the validation step that follows) is genuinely unspecified by either text - this is a real gap between two still-moving documents, not something we resolved by finding the answer.
  - **Design implemented as our own reasonable extrapolation, not a cited requirement**: `sh:entailment` runs over the data graph *before* executing any rules (so rules see entailed facts, the same way they already see the unconditional `rdf:type`/`rdfs:subClassOf` "SHACL type" closure that needs no entailment declaration at all), then runs again over the resulting evaluation graph (base ∪ every inferred triple, shape-attached and global alike) before the final conformance check - so newly-inferred triples get the same entailment treatment the original data graph did, rather than silently missing out on it. **Before relying on this further**: re-check against whatever the SHACL 1.2 Core and Inference Rules documents say once they're closer to final (see `docs/shacl/shacl12-gap-matrix.md`) - the rules/entailment interaction specifically might get clarified (or resolved differently) in a later draft.
  - **`ont_graph` limitation closed, 2026-10-07**: `apply_entailment()` (and pySHACL's own `inference=`, also replaced the same day with an equivalent routed through `StarLayerGraph.infer()`) now compute entailment over `data_graph` union `ont_graph`, materializing only the newly-entailed delta back - `ont_graph` itself is never mutated or copied in wholesale. See `starlayer/shacl/CLAUDE.md`'s dated entry for the full design and the real `CustomRDFSSemantics` parity wrinkle found and accounted for along the way. **`StarShaclProcessor.validate()`'s own class method gained both fixes too, same day** - not via step 2 of the bare-function flip (still not done, see that section's own entry), but by mirroring the same two code changes directly into the class method's still-duplicated body, after a direct user question ("I thought we would be running this through the graph inference engine, so we ensure comparable results") surfaced that its `inference=` was still silently running pySHACL's own separate internal reasoning. `apply_rules()`'s class method already had both, since it already delegates to the bare function (unlike `validate`/`validate_each`/`evaluate`).

- **Repo-wide stale `starlayergraph` import, found 2026-10-07 while `nbconvert`-verifying the entailment-regime work above** - a leftover from before this project's own `starlayergraph`→`starlayer` package merge. `from starlayergraph import ...`/`from starlayergraph.graph.owl_dl import ...` still appears in **20+ guide notebooks** under `docs/` (confirmed via `grep -rl "from starlayergraph\|import starlayergraph" docs/`), making every one of them fail to execute via `nbconvert` - not a cosmetic issue, a real broken-guide bug. Fixed only in the 3 notebooks the entailment-regime work actually touched (`03a-sparql-inferencing.ipynb`, `07.02-backend-graph-databases.ipynb`, `02.07-owl-dl-reasoning.ipynb` - renamed since, see `docs/guides/README.md`), scoped deliberately on explicit user instruction - the other ~17 are still broken. Worth a dedicated sweep later: find every stale `starlayergraph` import across `docs/`, replace with the real `starlayer`/`starlayer.graph` path, and re-execute each touched notebook via `nbconvert` to confirm, the same verification discipline used for the 3 already fixed.

**Done**: "produce a documentation doc outlining every method/import
available under `starlayer`" → `docs/generated/api-reference.generated.md`,
built 2026-09-30.

---

## Review how well the guides demonstrate the capabilities (2026-10-19)

The curated capability list (`codekg/curated/functionality.ttl`) and the guide notebooks should describe the same thing, and the notebook links (`codekg/curated/notebook-links.ttl`, 31 so far) are the bridge. A first pass found gaps in both directions. Revisit them, ideally with the `review-notebook-links` skill, once the guides settle.

- **Capability symbols no guide cell demonstrates.** `derive_shape`, `apply_entailment`, `select_widget` (only `select_widgets` is shown), `graph_diff`, `declared_conformance`, the RDF and RDFS entailment helpers, `StarQuery`, the Rust OWL-DL engine module, and `CanonicalizationComplexityError`. For each, decide whether the guides should cover it (a cell or a section) or whether it is internal and should not be named by a capability.
- **Things the guides demonstrate that the capability list does not name.** (SPARQL 1.2 Update was added as `cap-sparql-5` on 2026-10-19.) `infer()` returning only the delta or mutating in place (02b, section 5); caching query-time entailment with `recompute=` (03c); delegating reasoning to the store with `entailment="native"` on Fuseki (06b, section 1.2); class unsatisfiability detection in OWL-DL (02c, section 2). Candidates for new capabilities or for widening an existing one.
- **Guide ideas that are patterns, not capabilities.** Hash a tracked subgraph and re-verify it (04f, sections 5 and 12); use the OWL-DL reasoner as a constraint solver (appendix B2). Worth a line in the overview as "what you can build", not as a capability.
- **Weak links.** The link for the native backend (06b, cell `252791c5`) rests on a cell that sets up an endpoint demo and mentions the native layer only in a comment. Find or write a better cell.
- **Not covered by any guide or capability.** The reasoning timeout (an `ExecutionError` of kind `"timeout"`) has tests but no guide cell and no capability.
- **Keep it current.** The check (`python scripts/check_notebook_links.py`) catches edited, moved and broken cells but not new capabilities or new guide sections. A periodic review (each release) should compare the guide headings with the capability list again.

---

## SRL follow-ups (spec draft 2026-10-14)

*(Added 2026-10-17, from diffing `WD-sparql12-rl-20260919` against `WD-sparql12-rl-20261014`; what was fixed is in `starlayer/sparql/CLAUDE.md`.)* The 04b guide has a matching "Not yet covered" section to fill in as the open items land.

**Open**
1. **Aggregation (Issue 840).** *Trigger:* the draft gains grammar in §7.6 (today it has none) and a finished `evalAggregate`. *Then:* add the aggregation element to `_srl_ast.py`; the well-formedness conditions (keys in scope, aggregation variables distinct and new, functions over the pattern's variables); dependencies (the aggregation pattern is a closed dependency, and aggregation rules are run-once); the grammar and `ruleset_to_text`; the `srl:` RDF encoding and its SHACL shapes; evaluation (`COUNT`, `COUNT DISTINCT`, `MIN`, `MAX`, `SUM`; an error in a group drops that group); a guide section. *Until then:* an aggregate inside `FILTER` or `SET` is rejected at parse time.
2. **SRL-to-SPARQL translation (Issue 1303, Appendix A).** A placeholder in the draft; a worked algorithm would also give a way to run rule sets on a SPARQL engine.
3. **Re-diff the draft when it changes** (`/TR/sparql12-rl/` is a moving working draft); the date in the module docstrings and notes should follow.

**Resolved 2026-10-17**
- *`IMPORTS`.* Supported through a caller-supplied loader (`srl.resolve_imports`, `imports_loader=` on `infer()`/`query()`/`plan()`); import-once and the Appendix B merge as specified. No default loader on purpose (reading documents has security implications). Possible later additions: a ready-made directory loader, and caching of loaded documents.
- *Property paths in rule bodies.* The spec allows only `/` and `^` (§5, §7.6) and says arbitrary-length paths are written with recursion; both are supported, expanded into triple patterns when the rule is built, and every other operator is rejected with a clear message. Kept strict on purpose (decision 2026-10-17): no `|`, `*`, `+`, `?` or `!` extension.
- *Triple terms in rule text.* `<<( s p o )>>`, reified triples, reifiers and annotations parse, render, round-trip through RDF and evaluate, in bodies, heads and DATA blocks; `,` lists, `[ ]` and collections came with them. See `starlayer/sparql/CLAUDE.md`.
- *`parse_ruleset()` validates against the `srl:` shapes.* **Reversed 2026-11-25:** `parse_ruleset()` no longer validates and has no `validate=` parameter; `validate_sparql_tree` reports the shapes (and, since the same day, the §4.2 conditions and the evaluation order). The cost note below now belongs to `validate_sparql_tree`. It costs about 140 ms per parse (the shapes run over the rule set's RDF encoding); that cost is accepted. Decision (2026-10-17): shapes are not re-implemented in Python to make this faster. Any speed-up has to come from the SHACL validator itself (a generic fast path), not from a hand-written copy of one shapes graph.
- *`data` renamed to the spec's `evaldata`, then `evalground` (2026-11-25), with the spec's polarity.* In the AST, the parser, evaluation, the `srl:` vocabulary (`srl:ruleEvalground`/`srl:negationEvalground`), the shapes, the published `.ttl` files and the 05c guide; no compatibility layer, so RDF written with `srl:ruleData`/`srl:negationData` no longer decodes.
- *rdflib `xsd:integer()` of a decimal/double/boolean was an error* (the spec's Examples 9 and 10 depend on it). Patched in `operator_patches.py` and recorded in `docs/upstream-issues/rdflib-upstream-issues.md` (item 7, not filed). The Examples now infer `:B :distanceKilometers 16`.
- *Blank-node rule ids.* The abstract syntax allows them, but the grammar (§7.6, `Rule ::= 'RULE' iri? ...`) only has an IRI, so there is no text syntax to add. The RDF encoding can already carry one.
- *Lint-level checks (duplicate rule ids, empty head).* The draft says nothing that forbids them: rule ids only "help identify" a rule, and a template term is "a variable or an RDF term". They stay accepted. **A constant literal as the subject of a pattern, head template or `DATA` triple is rejected** (2026-11-18, `srl:SubjectOrVariableShape` in the `srl:` shapes): no triple can have one, so it can never match or be produced. A variable that is bound to a literal is data dependent, so that head triple is still dropped silently when the rules run, as in SPARQL `CONSTRUCT`.
- *Parse-time stratification check.* Decided 2026-10-17 to leave it to `plan()`/`infer()` (the draft puts it in the preparation for evaluation, not in parsing). Reversed 2026-11-18 (`parse_ruleset()` stratified the rules, skipped with `validate=False`, and a rule set with `IMPORTS` was checked on its own rules and got an `SRLUnresolvedImportsWarning`), **and back again 2026-11-25, final:** a parse returns the rule set whenever the text is understandable (the general rule for every parse is in "Review parse and validation behavior across the project"); `validate_sparql_tree` reports an unorderable rule set, `infer()`/`query()`/`materialize()` raise `StratificationError`, and `srl.resolve_imports()` and `plan()` check the combined rule set. What the warning told the user is kept without the class: when a rule set still has `IMPORTS` the ordering check can only cover the rules in the document, and an imported rule can add a dependency that makes them unorderable, so `validate_sparql_tree` reports each unresolved IRI as an `sh:Warning` result (`srl:UnresolvedImportsShape`, focus node the `srl:RuleSet`, message naming the IRI) that does not make `conforms` false. It stays in the report only: `infer()`, `query()` and `materialize()` already refuse a rule set with unresolved imports (`SRLImportsNotSupportedError`, §4.5), and the repo has no StarLayer warning class to use for `plan()` (the one warning class, `StarLayerFidelityWarning`, is about literal forms). *(Changed 2026-11-26: `plan()` without `imports_loader=` raises `ExecutionError` kind `"import"` like `infer()`; `ignore_imports=True` plans the document alone.)* `RuleSet.is_resolved` is `imports == []`.

## Rationalize the three import mechanisms

*(Added 2026-10-17, after adding `IMPORTS` to SRL. **Done in part 2026-11-26**: the missing-import policy is now one rule; the loader names and shared loaders remain.)*

**Done (maintainer decision 2026-11-26): one import rule on every path.** A graph, shapes graph or rule set that declares imports must resolve them or raise `ExecutionError` kind `"import"` (`error.unresolved`, the IRIs). An import is satisfied when its IRI is a subject of the graph after resolution (present, built in, or loaded; the `owl:versionIRI` of a present ontology counts; for SRL, when the loader produced a rule set); no loader, a loader returning `None` or a graph without the IRI is the error (nothing is skipped silently); a loader that raises is wrapped with the original as `__cause__`; `ignore_imports=True` loads and checks nothing; nothing is retried inside the library (`starlayer.graph.unresolved_imports(graph)` lets an application call again). One implementation, `graph/imports.py::resolve_or_raise`, behind every path:

| | where | loader argument | loader returns | skip flag |
|---|---|---|---|---|
| `owl:imports` on a graph | `StarLayerGraph.resolve_imports()` | `loader=` | a graph, or `None` | `ignore_imports=` |
| `owl:imports` of an ontology under an OWL regime | `infer()`, `query(entailment=)` | `imports_loader=` | a graph, or `None` | `ignore_imports=` |
| `owl:imports` in SHACL (shapes graph and `ont_graph`) | `validate()`, `validate_each()`, `apply_rules()`, `StarShaclProcessor` | `shapes_graph_loader=` | a graph, or `None` | `ignore_imports=` |
| SRL `IMPORTS` | `srl.resolve_imports()`, `parse_ruleset()`, `RuleSet.infer()`/`.query()`/`.plan()`/`.materialize()` | `loader` (positional) / `imports_loader=` | SRL text or a `RuleSet`, or `None` | `ignore_imports=` |

A malformed declaration (an `owl:imports` object that is not an IRI) is `FormatError` kind `"owl"` for a graph and `ShapeCompileError` for a shapes graph. Not applied (see the 2026-11-26 entry of `docs/working/error-scheme-decisions-log-2026-11-25.md`): the data graph of `validate()`, `derive_shape`, `meta_validate`, `parse_ruleset()` without a loader, the codekg tools.

**Done 2026-11-26 (step 2): the settings live on the graph.** `StarLayerGraph(imports_loader=, ignore_imports=)` and the properties of the same names; one accessor, `graph.resolved_imports()`, that every consumer calls (SHACL for the data, shapes and ontology graphs, `evaluate`, `target_nodes`, `target_shapes`, `extract_subgraph`, `close_shape`, `select_widgets`, `derive_shape`, `infer`, `query`, `resolve_imports`); the per-call parameters stay as overrides. See the decisions log (`## Imports on the graph (2026-11-26)`). Still open there: SRL `IMPORTS` keep their own loader; `candidate_values`, `check_value`, `form_model`, `value_form`, `select_widget`, `explain_widgets` and `extract_shapes_graph` read a shapes graph and do not resolve it; registry graphs carry no loader (`get_ontology_graph("srl_shacl")` needs `ignore_imports=True` or `local_loader`).

**Remains to rationalize**
1. **Loader names.** Settle on one name for a loader argument across the four (`loader=`, `shapes_graph_loader=`, `imports_loader=`, SRL's positional `loader`); `imports_loader=` is what the new `infer()` / `query()` parameters use. No rename was made (decision: keep each API's name).
2. **Shared loaders.** Reading a document has security implications in all of them, yet each caller writes its own loader today. Provide a small shared set so the safe choice is the easy one: a directory-confined loader, an allowlist-of-IRIs loader, and the bundled-files loader that already exists as `starontology.local_loader` (it returns graphs; SRL needs text or a `RuleSet`, so a thin adapter or a text variant is needed).
3. **Document the contract once**: what a loader receives (an IRI string for SRL, a `NamedNode` for graphs), what it may return, what happens on failure, and that none of them has a default.
4. **Optional:** caching of loaded documents across calls, if resolving the same libraries repeatedly turns out to be slow (a resolved `ont_graph` that gained triples is a new graph per call, so SHACL's entailment cache cannot share a copy for it, and `query(entailment=)` calls the loader on every call).
5. **Open:** `plan()` without a loader now raises (it used to show the document's own rules); a field on `RulePlan` for the unresolved IRIs is no longer needed.

## Review parse and validation behavior across the project (2026-11-18)

*(Added after the SRL guide review, to be done once the SRL work is finished.)* StarLayer never fetches an import by itself (reading a document has security implications), so a parse of a document with imports (`IMPORTS` in SRL, `owl:imports` in an ontology or a shapes graph) returns something that may be incomplete until the caller resolves it with a loader. A parse should say so, and each parse should check what it can on that basis.

**The principle to apply**
1. A parse checks what the text decides on its own: the grammar and every check on one rule, shape or axiom at a time.
2. A check that needs the whole document waits until the imports are resolved, because an import may supply the missing piece.
3. A check that an import can never undo (the text already breaks the rule, and imports only add) may run early. It is sound to fail early, with a message saying only the text was checked.
4. A parse with imports is flagged, with the list of imports left to resolve. For SRL that is `RuleSet.imports` (empty once resolved).

**To do**
- Decide what the flag is for each parse result (SRL has `RuleSet.imports`; a graph has `owl_imports(graph)`), and whether to add a readable property such as `is_resolved`.
- For each parse and validation, list the checks that cross the document and place them by the principle. Candidates: a shape or class that is mentioned but not defined in the text (Manchester and OWL parse, `sh:node` and `sh:property` references, rule dependencies for SRL stratification).
- Write the contract once with the loader contract above (an item of "Rationalize the three import mechanisms").

SRL, which has one cross-rule check (stratification), is the first case. See the decision of 2026-10-17 under "SRL follow-ups", which kept stratification out of `parse_ruleset()`.

## Before publishing: clean-up checklist

*(Added 2026-10-17.)* Generated and hand-copied material goes stale as the code changes. Before a release or a doc publish, work through this list. None of it is automated yet; deciding which steps to fold into one script is itself a follow-up.

0. **One command for steps 1-3:** `python scripts/build.py` runs them in order (`--only starontology codekg apidocs overview` to pick some; `overview` is the functionality overview, built from `codekg/curated/functionality.ttl`). `python scripts/build.py --check` runs every step, compares each output with what is committed (graph isomorphism for the `.trig` files, bytes for the markdown), puts the committed files back, and exits 1 if anything is stale; CI runs it with `--skip codekg` (the code KG is repo tooling, rebuilt on demand, not checked in CI; the API docs are then checked against the committed `codekg.trig`). Build-time only; nothing in the library runs it.
1. **Refresh the code knowledge graph.** `python scripts/build_codekg.py --paths packages/starlayer/starlayer packages/starlayer/tests` rebuilds `tools/kg/codekg/codekg.trig`.
2. **Regenerate the help/API docs** from that graph: `python scripts/generate_api_docs.py` writes `docs/generated/api-overview.generated.md` and `api-reference.generated.md`. Still open: whether `docs/generated/` is committed, and whether the generator joins step 1. `docs/generated/api-reference.generated.md` is the hand-kept predecessor and carries a stale-notice banner.
3. **Rebuild the starontology generated files**: `python scripts/build_starontology.py` regenerates `skos-ontology.ttl` and `shacl12-shacl.ttl` and assembles `starontology.trig` from the `.ttl` files, rewriting a file only when its graph changed. Run it after editing the validation shapes (`packages/starlayer/starlayer/starontology/_sources/shacl12-validation-shapes.ttl`), upgrading pySHACL, or editing any `.ttl` there; `--check` changes nothing and exits 1 if anything is stale (a test also fails while `shacl12-shacl.ttl` and a fresh build disagree).
4. **Refresh the widget appendix in `docs/guides/05.07-shacl-ui.ipynb`.** The appendix is a deliberately *static* markdown table; the guide does not generate it when run. If the shipped widget descriptions change, regenerate it with the snippet below and paste the output over the appendix cell. The guide expects 16 editors and 10 viewers.
5. **Re-execute every guide** so the stored outputs are current: `BROWSER=true python -m jupyter nbconvert --to notebook --execute --inplace docs/guides/<guide>.ipynb` (`BROWSER=true` stops the UI guide opening pages).
6. **Run the test tiers**: the fast tier, the integration tier (live servers), `pytest --store-matrix` for the W3C suites across every store, and `pytest --srl-stratification` for the extended SRL stratification checks (both are opt-in groups, see `tests/conftest.py`).
7. **Check the docs for stale claims**: counts (widgets, triples, tests), spec citations and dates, and the upstream-issue links.

Snippet that produced the 04d appendix tables (run from `packages/starlayer`):

```python
import pyoxigraph as ox
from starlayer import starontology

SH_NS = "http://www.w3.org/ns/shacl#"
SHUI = "http://www.w3.org/ns/shacl-ui/"
SH_DESCRIPTION = ox.NamedNode(SH_NS + "description")
SH_NAME = ox.NamedNode(SH_NS + "name")
meta = starontology.get_ontology_graph("shacl_shacl")


def first_value(subject, predicate):
    """The lexical form of the first object of (subject, predicate), or an empty string."""
    return next((o.value for o in meta.objects(subject, predicate)), "")


def widget_table(kind):
    """A markdown table of the built-in shui: widgets whose name ends with `kind`."""
    widgets = sorted(
        w for w in set(meta.subjects(SH_DESCRIPTION, None))
        if isinstance(w, ox.NamedNode) and w.value.startswith(SHUI) and w.value.endswith(kind)
    )
    rows = [
        f"| `shui:{w.value.removeprefix(SHUI)}` | {first_value(w, SH_NAME)} | {first_value(w, SH_DESCRIPTION)} |"
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

- **SPARQL 1.2 Protocol gap analysis done (2026-09-27), no action needed.** Full writeup: `docs/design/graph/sparql12_protocol_gap_analysis.md`. Bottom line: the 1.2 revision changes almost nothing at the protocol level (mostly editorial; the one new HTTP `QUERY` method and the `version` announcement mechanism are both optional). `starlayer/graph/backends/native.py` (the only code this spec's requirements land on - this project has no server-side SPARQL endpoint anywhere) already conforms to everything it needs to; its single-submission-mode choices (POST-direct for both query and update, `GRAPH`-clause-based dataset scoping instead of protocol-level parameters) are documented, deliberate design choices, not gaps. Three small, genuinely optional loose ends if ever revisited: round-tripping the already-computed in-band `VERSION` value onto the wire's out-of-band `version` parameter; verifying `Content-Type` before parsing a CONSTRUCT response; distinguishing HTTP 400 from 500 at the four HTTP call sites.

- **RDF 1.2 Interoperability spec gap analysis done (2026-09-27), not implementation-ready.** Full writeup: `docs/design/graph/rdf_interop_gap_analysis.md`. This spec (`rdf:PropositionForm`-based Full↔Basic encoding for triple terms) is still an Editor's Draft with its `basic-decode` algorithm literally unwritten ("Write this algorithm") and an open question on whether RDF 1.1 interop is even in scope - not comparable in maturity to the seven CR/WD documents `rdf12_sparql12_gap_analysis.md` tracks. This project already has three independently-designed, narrower analogs solving related problems differently (`compare.py::_decompose()`'s private-namespace blank-node encoding for canonicalization/reasoner bridges; `_intern_tt()`'s content-addressed URIRef encoding for in-memory storage) - none worth retrofitting onto the spec's vocabulary, since both are internal details no external caller ever observes. `jsonld12` itself was removed as a recognized format entirely (2026-10-02) rather than kept around as a partial format with no real spec to converge on, so there's no longer a live payoff for this spec on the JSON-LD side. Revisit once (if) this reaches Working Draft and JSON-LD gets a real RDF 1.2 companion spec of its own worth adding a format for.

  **Retrofit DONE (2026-10-18), on branch `triple-term-encoding`.** The internal triple-term encoding now uses the Interoperability vocabulary: each content-addressed node is typed `rdf:PropositionForm` and described by `rdf:propositionFormSubject/Predicate/Object` (the old `rdf:subject/predicate/object` reification terms are no longer used, so real reification data cannot be mistaken for the encoding). Only the node *name* differs from the spec (a stable content hash instead of a fresh blank node, which the spec's own decode rules would not match). Reads find triple terms by the type (registry rebuild is one indexed lookup; the hiding filters test the vocabulary, not the name). `serialize()` to a plain RDF format now yields the spec's basic encoding, and `parse()` of a plain format converts a basic-encoded document back into triple terms. Measured on a 22,000-triple graph with 2,000 triple terms: 7% more stored triples, parse 12% slower, `FILTER(isTRIPLE(?o))` was unchanged (553 vs 576 ms) while the SPARQL lowering still tested the name; a type-based join measured 27 ms against 343 ms on plain rdflib, so `isTRIPLE` over a variable bound by a graph pattern is now lowered into that join (576 ms down to 32 ms, same rows; `lower_rdf11._filter_is_triple_as_join`). Details: `starlayer/graph/CLAUDE.md`, 2026-10-18.

- **SPARQL entailment regimes not planned (and why).** Of the six regimes the [SPARQL 1.1/1.2 Entailment Regimes](https://www.w3.org/TR/sparql12-entailment/) spec defines, three have no plans to be built: **OWL 2 RDF-Based Semantics** (full, beyond the RL fragment already covered by `entailment="owl-rl"`) - undecidable in general (OWL Full has roughly first-order expressive power plus RDF's own reflective quirks); `owlrl`, the only OWL-RL dependency in this stack, implements the RL fragment specifically *because* that's the version with a terminating rule-based algorithm at all. **D-Entailment** (datatype canonicalization, e.g. recognizing `"01"^^xsd:integer` and `"1"^^xsd:integer` as the same *value*) - needs a full XSD datatype-map implementation inside the query engine's own term-equality logic; narrow and orthogonal to what this project exists for (RDF 1.2: triple terms, direction-tagged literals), and confirmed live against Jena's own docs that a Fuseki/Jena backend doesn't cover this either - an explicitly stated, deliberate gap in Jena's RDFS reasoner, not something delegating to a backend (`entailment="native"`) would close. **RIF Core Entailment** - no RIF interpreter anywhere in this stack, and no spec-conformance test infrastructure to verify one against even if built. (**OWL 2 Direct Semantics** is not in this bucket - `infer(profile="owl-dl")`/`query(entailment="direct")` cover it fully; see `tools/kg/codekg/CHANGELOG.md`.)

---

## Guide review findings (2026-09-26)

A full editorial pass over every notebook under `docs/guides/` (five parallel review passes, one per topic area) fixed typos and confirmed-stale references directly - see each notebook's own history for the specifics; not repeated here. What's below is what those passes found but deliberately did *not* fix, because it was bigger than a typo/staleness correction - grouped by guide-content gaps vs. underlying library gaps. **Snapshot from that date** - some items may have been resolved since by unrelated work; re-verify before acting on any of them rather than assuming they're still open.

**Guide-content gaps:**
- `01.01-getting-started.ipynb`'s own "Where to go next" list has no entry at all for `02.08-manchester-syntax.ipynb` (renamed from `05f-`, see `docs/guides/README.md`).
- `05.01-validating-with-shacl-1.2.ipynb` §3.3: after correcting an overbroad claim about which constraint components support per-value severity annotation (see the starshacl gap below), the guide doesn't explicitly say the other three (`sh:uniqueMembers`/`sh:reificationRequired`/`sh:singleLine`) currently lack it.
- `07.03-canonical-hashing.ipynb` (renamed from `05d-`, see `docs/guides/README.md`) narrates `.isomorphic()` in method-call style but only ever demonstrates the free function `starlayer.graph.compare.isomorphic()` - the bound `StarLayerGraph.isomorphic()` method (which exists, with its own more detailed TripleTerm-awareness docstring) is never shown or contrasted; ambiguous whether that's deliberate house style.
- `02.08-manchester-syntax.ipynb`'s (renamed from `05f-`, see `docs/guides/README.md`) first markdown cell has a stray leftover editing instruction embedded in the guide's own prose ("CLAUDE: show this as a two column table.") - looks like an artifact from building the guide, not intentional content.

**graph/shacl subpackage gaps (code-level, found while reading the guides' own examples):**
- `infer(profile="owl-rl")`'s inconsistency signal (`err:error`/`err:ErrorMessage` triples) has no dedicated accessor - a caller has to know to filter the result graph for that namespace by hand. A convenience method (e.g. `graph.inconsistencies()`) would close an easy-to-miss footgun.
- `remove_reification(reifier, triple_term=None)` silently no-ops when `triple_term` isn't actually reified by that reifier - there's no way to distinguish "already gone" from "wrong reference/typo" anywhere in this API surface.
- `packages/starlayer/starlayer/shacl/subgraph_extraction.py`'s own module docstring (design decision #3) is stale relative to its own code: it still says `sh:or`/`sh:xone` extraction includes "only the branch that actually caused the pass... the first list member that conforms," which is correct for `sh:xone` but wrong for `sh:or` - the actual implementation (and the guide, correctly) includes *every* passing `sh:or` disjunct, per the 2026-09-13 revision recorded in this project's own memory/design notes. A one-line source-level docstring fix, not a behavior change.
- `07.02-backend-graph-databases.ipynb`'s (renamed from `05b-`, see `docs/guides/README.md`) two backend paths raise two different exception types on an unreachable endpoint - `urllib.error.URLError` for `backend="rdf-1.1"`, `requests.exceptions.ConnectionError` for `backend="rdf-1.2"` (native). A caller has to know which backend they're using just to catch the right exception; not documented as a known asymmetry anywhere in `docs/design/graph/`.
- `entailment="native"` is restricted to `backend="rdf-1.2"` only, even though `backend="rdf-1.1"` can also talk to a live SPARQL endpoint (via a `Store` plugin) and just can't delegate entailment to it. Possibly deliberate, but not called out as such anywhere.

---

## Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes

RDF 1.2 was at **Candidate Recommendation** (published 2026-04-07) as of this writing — not yet a final W3C Recommendation. Everything in this project (the gap analysis, the rewriter, the format modules) is checked against that CR-stage text. This project's own stated purpose (README: "intended to remain relevant until rdflib is updated to incorporate the final RDF 1.2 specification") means it has a deliberately limited lifespan, and needs periodic re-checking rather than a one-time gap analysis. Concrete steps for whoever picks this up as the spec progresses:

1. **Re-run the gap analysis at each W3C stage transition** (CR → PR → REC). CR-stage text can still change in response to implementation/horizontal-review feedback before Proposed Recommendation; re-diff `docs/design/graph/rdf12_sparql12_gap_analysis.md` against the current editor's draft whenever the spec's status changes, not just once. `packages/starlayer/tests/graph/vendor/spec_snapshots/refresh_snapshots.py` automates the "what actually changed" half of that: it re-fetches all seven tracked documents and overwrites the saved snapshots, so `git diff packages/starlayer/tests/graph/vendor/spec_snapshots/` shows exactly what moved since the last review instead of requiring a full re-read.
2. **Watch the CR exit criteria / implementation report.** The RDF-star Working Group's CR exit requires a set of independent conforming implementations. Whichever engines end up counted (Oxigraph and Fuseki are the two this project already tracks) are worth re-verifying `starlayer.graph`'s rewriter against each time one of them ships a release claiming closer conformance — a live three-way comparison against the in-memory backend (see `packages/starlayer/tests/graph/integration/test_cross_backend_parity.py`) is the reusable tool for that, not a one-off.
3. **Watch for a real JSON-LD RDF-1.2 companion spec.** `jsonld12` was removed as a recognized format entirely (2026-10-02, see `docs/design/graph/rdf12_sparql12_gap_analysis.md` §6) rather than kept as a partial "plain RDF 1.1 content only, refuse triple terms" format, since JSON-LD has no published RDF 1.2 companion spec at all. If the JSON-LD Working Group ever publishes an RDF-1.2-aware revision with its own native representation for quoted/triple terms, consider adding a real `jsonld12` format back for that representation. TriX has no standards body actively developing it, so `trix12` is unlikely to ever gain a real target to converge on — its "starlayer.graph convention, not a spec" status is probably permanent, and the documentation callout is the whole fix rather than a placeholder for a future code change.
4. **Once rdflib ships native RDF 1.2 support** — re-evaluate this project's continued existence, per its own stated scope. At that point: (a) consider deprecating `starlayer.graph`'s SPARQL 1.2→1.1 rewriter and in-memory triple-term encoding in favor of delegating straight to rdflib, and (b) check whether the `turtle12`/`nt12`/`nq12`/`trig12`/`rdfxml12` format modules can be dropped in favor of rdflib's own native parsers/serializers.

---

## Parked ideas from the guide review (2026-11-14)

Discussed with the owner and set aside to come back to. Nothing here is decided.

**Prefix handling (guides 01 and 02 and every example that writes IRIs).** Today a new graph has no prefixes; parsing binds the document's own; `bind()`, `StarLayerGraph(prefixes=)` and `set_default_prefixes()` (process-wide, for graphs created afterwards) add more. Writing an unbound `rdf:` or `rdfs:` IRI prints it in full, and a query that uses an unbound prefix fails with "Prefix not found" (Oxigraph's message does not name the prefix).
- *Smart prefixes.* A `smart_prefixes` flag on the graph, default on. On a "Prefix not found" error: scan the text for standard prefixes that are not bound, bind them, retry once (so an error happens once per graph per prefix). The write side has no error to catch, so it would bind the standard prefix of any IRI it writes. Open points: an automatically bound prefix should print only when used (`only_used` is off by default, so every later `serialize()` would list it); the binding is persistent, so a read changes `g.prefixes` (the alternative is a per-call fallback that stores nothing); a prefix the user bound always wins; parsing stays strict (Turtle requires its own declarations); shapes graphs stay strict (`sh:prefixes` says there is no ambient lookup). Measured cost: a scan of a 142-character query is about 4 microseconds and of a 43,000-character query about 1 ms; classifying a million IRIs by namespace is about 0.1 s; retry-on-error costs nothing when the query succeeds. A fixed table of twelve: `rdf`, `rdfs`, `owl`, `xsd`, `sh`, `shui`, `skos`, `dcterms`, `foaf`, `prov`, `dcat`, `schema` (the constants of `graph/namespaces.py`).
- *Explicit binding with a helper* (the owner's other leaning). `STANDARD_PREFIXES` (a dict), `g.bind_standard(*names)` (all, or the named ones; never replaces a prefix already bound; returns the graph), used with `set_default_prefixes(STANDARD_PREFIXES)` or `StarLayerGraph(prefixes=STANDARD_PREFIXES)`, and `serialize(only_used=True)` so binding all twelve does not clutter the output. The unbound-prefix error could say "bind it with `g.bind_standard('rdf')`". Smart prefixes could later be added on top as a flag that calls the same helper.

**Blank nodes in query results.** `serialize(bnode_labels="short")` exists. Three cells in guide 03 print blank nodes from query rows with `qname_term(row.claim)` and still show the long ids (`_:c7c1af4e...`). A `short_labels` option for `qname_term`, or a helper that numbers the blank nodes of a result, would fix them.

**Reification helpers.** `reifiers`, `reified_triples` and `annotations` take an optional argument and answer for everything without one. Not added: `is_reified(tt)` (some node `rdf:reifies` it; `(None, None, tt) in g` answers the wider "is it used as an object", `tt in g` "is it asserted"), and a "remove every reification" form of `remove_reification` (`g.remove((None, RDF.reifies, None))` does it and leaves the annotations).

**Guides.** Guide 02 section 2.4 names only the outer reifier; both can be named (`<< ex:claim ex:about << s p o ~ ex:inner >> ~ ex:outer >>`), and then the outer triple term's object is `ex:inner`, not the inner triple. Guide 01 imports from `starlayer.graph`; `from starlayer import StarLayerGraph` also works (four names are exported at the top) and is shorter for a first run, but `validate` still comes from `starlayer.shacl`. The word "guide" for a single notebook (the owner wants "guide" for the whole collection) is still used in the README index and in the other notebooks.

**Inside the library.** Seven readers of an RDF list in the engine and the SPARQL tree code fail differently on a malformed list; merging them needs one error contract (see `docs/working/workbench-api-needs.md`, "Where a helper lives").


## OWL 2 RL without `owlrl` and rdflib (2026-11-14)

Explored with the owner and set aside. Nothing here is decided. Today `infer()` for OWL-RL (and the combined RDFS and OWL-RL regime) runs `owlrl` on an rdflib copy inside `starlayer-reasoning` (`owl_rl.py`). The native RDFS closure (`graph/entailment/rdfs_closure.py`) already replaced it for RDFS alone.

**Findings.**
- *`owlrl`'s rules are not data.* `OWLRL.py` is Python methods (`_properties`, `_classes`, `_equality`, ...) run over every triple on every cycle, one branch per W3C rule, commented with the rule name (`prp-dom` and so on). There is no rule table to import and apply elsewhere. What is reusable as data: the axiomatic triples and the datatype tables. `owlrl` 7.6.2 can run on a `pyoxigraph.Store` directly (an `oxigraph` extra), but the loop stays in Python and it was only about 20% faster than the rdflib copy.
- *Measured, RDFS only, synthetic class and property hierarchies (448 to 60,148 triples, one machine).* Native worklist: 9 ms, 86 ms, 484 ms, 2.4 s. `owlrl` on an rdflib copy: 0.5 s, 4.7 s, 23.6 s, 103 s (about 40 to 55 times slower). The 14 RDFS rules written as SPARQL `INSERT ... WHERE` run to a fixpoint inside Oxigraph: 30 ms, 327 ms, 1.9 s (3 rounds, identical output to the native closure, about 3 to 4 times slower than native, about 10 to 12 times faster than `owlrl`). StarLayer's own SRL engine on the same rules: 1.3 s, 12.5 s (correct, about 130 times slower than native, because heads are built in Python per solution). The scripts were scratch files (`bench_rdfs.py`, `bench_sparql_rdfs.py`, `bench_srl_rdfs.py`, `bench_owlrl_ox.py`, `gen.py`) and are not in the repo.
- *Not measured:* any OWL-RL rule. The speed-up for OWL-RL is an extrapolation from RDFS.

**Idea A: a rule table, run by Oxigraph.** One entry per W3C OWL 2 RL rule (about 75), each a SPARQL update; closure rules use property paths; run to a fixpoint, skipping rules whose triggering vocabulary is absent (a cheap `ASK`), with schema-only rules run once and the instance rules looped (stratified). `owlrl` and the W3C OWL 2 RL conformance tests become test oracles, not a runtime dependency, as `test_rdfs_closure.py` does for RDFS. It would also work on a persistent store and on a remote `Endpoint` without pulling triples into Python. Hard parts: list rules (property chains of unbounded length need a query generated per axiom; `intersectionOf`, `unionOf`, `oneOf`, `hasKey`), `owl:sameAs` replacement (the closure can blow up), inconsistency rules (they report, they do not add triples; `owlrl` writes `err:ErrorMessage` nodes), datatype rules, and reading base and inferred triples together (separate named graph versus diffing a scratch copy; the diff cost about 15% in the prototype). Next step if revived: prototype 10 to 15 of the hardest rules (a list rule, equality, one inconsistency rule) and measure rounds and time against `owlrl` on a real ontology before writing all 75.

**Idea B: an existing Rust reasoner.** Searched 2026-11-14 (from READMEs and docs pages; none was installed or run, the install was blocked, and the speed claims are the authors' own):
- *reasonable* (Rust on DataFrog, BSD-3; Python package `reasonable` / `pyreasonable`, the crate builds on `oxrdf`). The most established. Claims about 38 times faster than `owlrl` on Brick models; incremental updates. Its own rule tables list as unimplemented: `eq-ref`, `eq-diff1` to `eq-diff3`, `prp-irp`, `prp-asyp`, `prp-pdw`, `prp-adp`, `prp-key`, `prp-npa`, `cls-nothing2`, `cls-com`, most max-cardinality rules, `cax-dw`, `cax-adc`; datatypes only partial. The Python API is rdflib-oriented (`from_graph`, `load_file`); whether rdflib is required was not confirmed. Version numbers conflicted across pages (crate 0.4.4, PyPI listing 0.5.0a1).
- *TurbOWL* (Rust, MIT). Covers the W3C rule tables with switches; 101 of 119 runnable W3C OWL 2 RL cases (`owlrl` 100, Nemo 101); lists 15 places where `owlrl` departs from the W3C text. Python bindings take rdflib graphs; not yet on PyPI or crates.io, 0 stars.
- *oxilite-reason* (wraps `reasonable` for the oxilite store, in memory), *OntoLogos* (a facade over `reasonable`), *oxirs-rule* (thinly documented), *rdflib-reasoning* (Python RETE on rdflib, partial OWL 2 RL), *Nemo* (a general Datalog engine with a Python API; it could run a rule table, but is not an OWL-RL reasoner).
- Every Python API found takes rdflib graphs, so using one from pyoxigraph terms means a round trip through N-Triples text (linear, and it loses RDF 1.2 triple terms), plus a compiled dependency per platform. Worth running `reasonable` and TurbOWL against `owlrl` on a real ontology (output equality, time, inconsistency reporting) before choosing.

**Not changed.** RDFS stays native. OWL-RL stays on `owlrl` in `starlayer-reasoning` until one of the above is tried.


## What rdflib had that StarLayer could still offer (2026-11-15)

From the review of what the move to pyoxigraph gave up. The aim is rdflib's capabilities over pyoxigraph terms, not its class shape (the 2026-11-06 decision that fidelity to the old class is not a goal stands). Not done; in order of value.

1. **`custom_functions` (and aggregates) on `query()` and `update()`.** pyoxigraph takes them already, so this passes one argument through. Without it there is no way to extend SPARQL.
2. **`Result.serialize(format)`** over `QuerySolutions.serialize`: standard CSV, TSV, JSON and XML results.
3. **A small public term toolkit in `starlayer.graph`:** `literal(py_value)`, `to_python(term)`, `iri()`. The workbench rebuilt these; the library should own them.
4. **Public RDF list helpers** (`list_items`, `add_list`) in a home next to the graph, not inside the engine. `transitive_objects` / `transitive_subjects` only if wanted; property paths already cover the use.
5. **A short SALG-to-SQE migration note**, once the coverage is confirmed.

Not worth bringing back: subclassing `rdflib.Graph`, rdflib stores and plugins, `Resource` and slicing, the old algebra patches, the extra file formats.



## To raise with the SHACL working group (2026-11-21)

1. **`sh:uniqueValuesFor` when every listed property is missing.** Core says "No result is produced if `V` has no values for any of the properties", and test `uniqueValuesFor-004` expects no violation. StarLayer reads this as: a node is skipped only when none of the listed properties has a value, and a node with a value for some of them is compared (an empty set equals an empty set). Our view is that two nodes with no values at all for the listed properties are also the same combination, so they should be reported. The sentence is also ambiguous as written ("has no values for any of the properties"). Raise it in the data-shapes issue tracker, asking for the wording to be made explicit and for the all-missing case to be reconsidered. Until the working group answers, the engine and guide 05 (3.2.4) follow the draft: skipped when all are missing.

2. **Core and its own vocabulary disagree about where the report provenance lives (2026-11-23).** The Core editor's draft text (`shacl12-core/index.html` on `gh-pages`) says a `sh:ValidationReport` MAY have `sh:usedDataGraph`, `sh:usedShapesGraph` and `sh:usedConfiguration`. The vocabulary file (`shacl12-vocabularies/shacl.ttl`) has since changed: commit `6dba388ac` (2026-10-27, "correct domains for usedDataGraph and usedShapesGraph") gives the first two the domain `sh:ValidationActivity`, commit `16a17054e` (2026-10-09, "remove usedConfiguration; ... linked to Profiling for extended results graph elements") deleted the `sh:usedConfiguration` property while Core still defines it and keeps the `sh:ProcessorConfiguration` class, and the property comments still say "The subject Validation Report ...". The Profiling draft ("Persisting validation results with context") describes the activity-centric and output-linked forms. Ask which is meant: provenance on the report, as Core's text says, or on a `sh:ValidationActivity` that `prov:generated` the report. Decided 2026-11-23: StarLayer writes the activity form only (a `sh:ValidationActivity` that `prov:generated` the report carries `sh:usedDataGraph`, `sh:usedShapesGraph`, `sh:usedConfiguration` and `prov:wasAssociatedWith` a `sh:ValidationAgent`; the report node carries none), which the vocabulary and Profiling describe; Core's prose is the part that disagrees.

## Remove the deprecation aliases (2026-11-22)

Decision: StarLayer does not keep deprecation aliases or compatibility shims for renamed names. A renamed class gets no alias (`ValidationResult` became `ValidationReport` with none). The ones already in the code are to be removed, with their tests, and the guides and docs checked for the old names afterwards:

1. **`StarShaclSchema`**, the old name of `StarShaclProcessor`: a module `__getattr__` that warns and returns the class, in `starlayer/__init__.py`, `starlayer/shacl/__init__.py` and `starlayer/shacl/validator.py`. Remove the three shims and `tests/shacl/unit/test_star_shacl_processor_alias.py`, and the "deprecated alias" mentions in `starlayer/shacl/CLAUDE.md`.
2. **`advanced=`** on `validate()` (deprecated; `advanced=False` meant `rules=False`): `_adapter.py` (`_warn_advanced_deprecated`, the option handling and the `VALIDATE_OPTIONS` entry), `validator.py` docstrings, the tests that exercise it (`test_validator.py`, `test_validation_modes.py`, `test_fidelity_warning_location.py` and the W3C validate runner, which pass `advanced=`), and the `advanced=` note in `starlayer/shacl/CLAUDE.md`. After removal `advanced=` is an unknown option and raises `TypeError`.
3. **`turtle12` as a name for the `turtle` format** (and the other alias spellings in `starlayer/graph/formats.py`: `ttl`, `n3`, `text/turtle`, `text/n3`): decide which are real input formats and which are only old spellings; `turtle12` is the old one. Guide 07a lists them.
4. **A stale comment** in `starlayer/shacl/__init__.py` mentions `engine` "(evaluate_component() and friends, deprecated)", but no `evaluate_component` exists any more. Delete the comment.
5. **Check for others** when this is done: grep for `DeprecationWarning`, "deprecated", "old name" and "alias" in `packages/`, and look in the other packages (`starlayer-kg`, `starlayer-reasoning`).


## Validate on an interval when the data has changed (2026-11-22)

A `StarShaclProcessor` validates only when it is called; it has no timer. An application that wants to validate a graph on an interval, and only when the graph has changed, writes its own loop around `validate()`. The processor holds its graphs rather than copying them, so each call sees the current data.

What is missing is a public way to tell that a graph has changed. Each store has a write counter that moves on every write made through the graph (`starlayer.graph.execution.union.version_of(graph.store).stamp()` returns `(0, 0)` on a new graph and `(1, 0)` after a `parse`), and the shared entailment cache already uses it, but that module is internal. Writes made straight to the underlying store do not move it unless `union.touch()` is called.

To consider:

1. **A public change counter on the graph**, for example `graph.version` or `graph.changed_since(stamp)`, so an application loop needs only public API. This is the part that is awkward to do from outside.
2. **A scheduling helper on the processor**, for example `myProcessor.watch(interval=..., on_report=...)`, which runs `validate()` when the data graph's counter has moved. It would need a thread or an `asyncio` task, error handling, and a way to stop, so it is a larger decision. Keeping scheduling outside the library is the default.


## Record when a validation was run (2026-11-23)

A validation report has no date. Whether it should is a design question, not a gap in the spec: `sh:ValidationReport` in the current SHACL 1.2 Core and Profiling drafts has no date property, and the Profiling draft models a run as a `sh:ValidationActivity` (a PROV activity), which StarLayer now writes (without times) and which could carry `prov:startedAtTime` but is not required to.

The default should stay as it is, with no time in the report. StarLayer's provenance and fragment results are reproducible: identical inputs give an identical result, which is what lets a report be compared, hashed and committed as a stable artifact (the hash-and-reverify pattern). A timestamp in every report would make two runs on the same inputs differ.

An opt-in is consistent with how the report records its configuration (`include_used_configuration=True`):

1. **A flag such as `include_run_time=True`** on `validate()` and `validate_each()` that adds `prov:startedAtTime` and `prov:endedAtTime` (`xsd:dateTime` in UTC) to the `sh:ValidationActivity` that already carries `sh:usedDataGraph`, `sh:usedShapesGraph` and `sh:usedConfiguration` (the report node gets nothing). Decide whether the activity is also written when no name is known and no configuration is asked for, since it is skipped then today.
2. **An injectable clock.** The time has to come from a function the caller can replace, so that tests and any caller who needs deterministic output can fix it. A rule run already fixes one "now" for the whole run, so every `NOW()` in it agrees (`_Run.now` in `shacl/engine/rules.py`), but the caller cannot set it; one clock option could serve both.
3. **Decide the scope** with the rest of the report annotations: the data-graph and shapes-graph names, the configuration and the `sh:conformsToShapesGraph` link are all opt-in or conditional today, so the time should follow the same pattern.


## Error handling in SHACL, and uniformity across StarLayer (2026-11-25, updated 2026-11-26)

One scheme now covers the library (`starlayer/errors.py`, rules in `AGENTS.md`, pinned by `tests/repo/test_error_scheme.py`): the base `StarLayerError`; `ShapeError` (`ShapeCompileError`, `MetaShaclError`) for a wrong shapes graph; `FormatError` with a `kind` (kinds in `FormatError.KINDS`) for malformed text or data; `ExecutionError` with a `kind` for a failed run or input the library cannot handle; `EndpointError` (also an `OSError`) for a network failure. A plain `ValueError` or `TypeError` is only a bad argument at the entry of a public call. Classes removed by stages 1 to 6 have no alias; the summary of the whole change is `docs/working/error-scheme-summary-2026-11-26.md`.

**Done**
- Audit of the raises outside `starlayer/shacl`, and the scheme for the other subsystems (one library base, one class with a `kind` per family), written down once in `AGENTS.md` and the subsystem `CLAUDE.md` files.
- Staged migration, each stage its own commit: the leaf module and the SHACL move (stage 0), OWL-DL reasoning (1), SPARQL text and the query/update boundary (2), SRL (3), RDF documents and terms (4), Manchester and OWL (5), the leftovers (6: RDFC-1.0 limit, entailment rewrite, `sqe:` text rendering, SRL render gaps, internal states, `EndpointError`).
- The catch clauses outside SHACL name the failure they guard against; `only_kind` guards the clauses that take one kind of `ExecutionError`.
- The maintainer's review of 2026-11-26 (Q1 to Q6, in `docs/working/error-scheme-decisions-log-2026-11-25.md`): the SHACL caps are kind `"limit"`; an entailment name that is not a registered regime is `ExecutionError` kind `"unsupported"` (a non-text, non-IRI value is a `TypeError`); `relevant_subgraph` with DESCRIBE or SERVICE, an endpoint-origin blank node and the `"error"` direction policy are `"unsupported"`; an unrecognised rule body element is `FormatError` kind `"srl"`; a closed `Materialization` is a `ValueError` again; the `TypeError` audit moved one site to `FormatError`.
- A test fails if a removed class name returns, or if a `kind` used at a raise site is not declared (or a declared kind is never raised).
- The review of 2026-11-26, second part (Q15 to Q17 and the registry, in the decisions log): a shapes graph's `sh:entailment` naming an unregistered regime is `unsupported` like `infer()`; `export_rdf11` on named graphs is `unsupported`; `compute_qname` of an IRI with no prefixed form is `FormatError` kind `rdf`; an OWL regime reaching the query rewrite is `internal`; rows of a result of the wrong form is a `ValueError`; `ExecutionError.KINDS` and `FormatError.KINDS` are mappings kind -> meaning, the one list of the kinds.

**To do**
- **Manchester internal states.** Ten `AssertionError("unhandled ... tag")` raises remain in `graph/manchester/parser.py` (2), `graph/manchester/serializer.py` (2) and `starontology/manchester/__init__.py` (6); by the scheme they are `ExecutionError` kind `"internal"` (left for the owner of the Manchester vocabulary work).
- **Align the SHACL leftovers.** *Done 2026-11-26 (decision 22): `max_iterations` is validated like `max_triples` and its message names the option; decision 23: `RuleResult.failures` holds the `ExecutionError` objects.* (The kind question is decided: `max_iterations` and `max_triples` failures are kind `"limit"` since 2026-11-26; guide 05.02 / 05.06 text still says `"rule"`.)
- **`RuleResult.failures`** is still a `list[str]`, not structured.
- **Guides and the workbench** still name removed classes or catch builtin classes around changed calls (the lists are in the summary).
- **Strings that stay.** *(The "the document has named graphs" message match is gone: done 2026-11-26, decision 24a; a quad document into a single graph is parsed whole and decided by its quads.)* The `initBindings` text scan (24b) stays: it is a heuristic.

## SRL as an entailment regime (2026-11-26)

An SRL rule set could be offered as a custom entailment regime for `infer()`, `query()` and a shapes graph's `sh:entailment`, the way the SPARQL 1.2 Entailment Regimes specification offers RIF Core entailment.

- **What the specs say.** Neither specification defines this. The Entailment Regimes spec (`sparql12-entailment`) has a RIF Core regime, `http://www.w3.org/ns/entailment/RIF` (Section 8): a rule set is attached to the queried graph with `rif:usedWithProfile`, and RDFS and OWL 2 RL are given as rule sets (8.2). Section 1.4 says each regime is defined by a table (name, IRI, legal graphs and queries, entailment, inconsistency, query answers); it describes no mechanism for third-party regimes. The SRL spec (`sparql12-rl`) does not mention entailment regimes; its one mention of entailment is "This is related to the entailment extension point" (4.2.3, a feature at risk), and its query operation (infer, then match a goal against the base and inferred graphs, 4.1) is already what `RuleSet.infer()` and `.query()` do. Only the first half of each spec was read.
- **Design points.** A regime is an IRI of our own, registered with StarLayer. How the rule set is attached is open: an argument, or a reference in the data graph as RIF does. SRL's "infer, then match" is the entailment relation; the regime table's inconsistency and query-answer rows need to be written for it.
- **Errors.** An entailment name that is not a registered regime is `ExecutionError` kind `unsupported` (decision of 2026-11-26, error scheme review Q3), so adding the registry changes no error behaviour. The names are an open vocabulary of IRIs.
