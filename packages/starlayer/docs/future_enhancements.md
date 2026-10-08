# StarLayer Future Enhancements

*Last reviewed: 2026-09-30*

Moved here from `packages/starlayer/docs/graph/` (2026-09-30) - this
document's content spans the whole merged `starlayer` package (graph,
SPARQL, and SHACL), not just the graph subpackage, so it belongs at the
package's own top level, not nested under one subpackage's docs.

---

## Open suggestions

- Add SHACL Compact syntax to the roadmap - already tracked in
  `docs/functionality-overview.md`'s `starshacl` deferred list (an
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
  patterns (property paths included - confirmed working, inherited for
  free from the same technique reused), `OPTIONAL`, `UNION`, `FILTER`,
  `BIND`. Not yet covered: aggregates/`GROUP BY`/`HAVING`, subqueries,
  `VALUES`, and SPARQL Update entirely - widen deliberately, later, one
  construct at a time, each with its own round-trip + SHACL coverage
  added alongside it (same testing discipline `test_sqe_ontology.py`
  already establishes).

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
  `starlayer/sparql/expr_text.py`) first, and update both `srl.py`'s and
  `sqe/to_text.py`'s imports to the new location - so neither depends on
  a module slated for deletion. Then delete the rest of `ssyn:`/all of
  `sast:` plus their test files (`test_ast_ontology.py`,
  `test_ssyn_ontology.py`), and update `starlayer/sparql/CLAUDE.md`'s
  file map and `docs/api-reference.md`'s "Lower-level" table accordingly.

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
  Inference Rules draft (`docs/shacl12-gap-matrix.md` tracks it) says
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

- **Repo-wide stale `starlayergraph` import, found 2026-10-07 while `nbconvert`-verifying the entailment-regime work above** - a leftover from before this project's own `starlayergraph`→`starlayer` package merge. `from starlayergraph import ...`/`from starlayergraph.graph.owl_dl import ...` still appears in **20+ guide notebooks** under `docs/` (confirmed via `grep -rl "from starlayergraph\|import starlayergraph" docs/`), making every one of them fail to execute via `nbconvert` - not a cosmetic issue, a real broken-guide bug. Fixed only in the 3 notebooks the entailment-regime work actually touched (`03b-sparql-inferencing.ipynb`, `05b-backend-graph-databases.ipynb`, `05e-owl-dl-reasoning.ipynb`), scoped deliberately on explicit user instruction - the other ~17 are still broken. Worth a dedicated sweep later: find every stale `starlayergraph` import across `docs/`, replace with the real `starlayer`/`starlayer.graph` path, and re-execute each touched notebook via `nbconvert` to confirm, the same verification discipline used for the 3 already fixed.

**Done**: "produce a documentation doc outlining every method/import
available under `starlayer`" → `packages/starlayer/docs/api-reference.md`,
built 2026-09-30.

---

## Deferred / open follow-ups

- **rdflib 8 compatibility.** Currently built on and tested against rdflib 7.6.0 (`pyproject.toml` requires `rdflib>=7.0`). rdflib 8.0.0a0 (pre-release) was tested too; revisit compatibility when a stable rdflib 8 release ships.

- **More examples.** Only two exist today (`packages/starlayer/examples/`); no example covers `StarLayerDataset` (multi-graph). Decide what's worth adding.

- **SPARQL 1.2 Protocol gap analysis done (2026-09-27), no action needed.** Full writeup: `packages/starlayer/docs/graph/sparql12_protocol_gap_analysis.md`. Bottom line: the 1.2 revision changes almost nothing at the protocol level (mostly editorial; the one new HTTP `QUERY` method and the `version` announcement mechanism are both optional). `starlayer/graph/backends/native.py` (the only code this spec's requirements land on - this project has no server-side SPARQL endpoint anywhere) already conforms to everything it needs to; its single-submission-mode choices (POST-direct for both query and update, `GRAPH`-clause-based dataset scoping instead of protocol-level parameters) are documented, deliberate design choices, not gaps. Three small, genuinely optional loose ends if ever revisited: round-tripping the already-computed in-band `VERSION` value onto the wire's out-of-band `version` parameter; verifying `Content-Type` before parsing a CONSTRUCT response; distinguishing HTTP 400 from 500 at the four HTTP call sites.

- **RDF 1.2 Interoperability spec gap analysis done (2026-09-27), not implementation-ready.** Full writeup: `packages/starlayer/docs/graph/rdf_interop_gap_analysis.md`. This spec (`rdf:PropositionForm`-based Full↔Basic encoding for triple terms) is still an Editor's Draft with its `basic-decode` algorithm literally unwritten ("Write this algorithm") and an open question on whether RDF 1.1 interop is even in scope - not comparable in maturity to the seven CR/WD documents `rdf12_sparql12_gap_analysis.md` tracks. This project already has three independently-designed, narrower analogs solving related problems differently (`compare.py::_decompose()`'s private-namespace blank-node encoding for canonicalization/reasoner bridges; `_intern_tt()`'s content-addressed URIRef encoding for in-memory storage) - none worth retrofitting onto the spec's vocabulary, since both are internal details no external caller ever observes. `jsonld12` itself was removed as a recognized format entirely (2026-10-02) rather than kept around as a partial format with no real spec to converge on, so there's no longer a live payoff for this spec on the JSON-LD side. Revisit once (if) this reaches Working Draft and JSON-LD gets a real RDF 1.2 companion spec of its own worth adding a format for.

  **Retrofit design done (2026-09-27), paused pending a cost/benefit call, not started.** Fully investigated at the time (two Explore agents mapping every touch point across `starlayergraph` and the sibling `starsparql` - the two packages were still separate at the time this investigation ran; both are now the `starlayer.graph`/`starlayer.sparql` subpackages of the merged `starlayer` package, see `packages/starlayer/docs/`), plus a Plan-agent validation pass that read the real code and caught two genuine bugs a naive version would introduce - a query-result correctness bug from bare-adding `rdf:type` to the shared encoding-predicate set, and a native-backend crash on Turtle 1.2 parsing from an unguarded 4th triple). Scope: swap `_intern_tt()`'s in-memory storage encoding (currently classic `RDF.subject`/`RDF.predicate`/`RDF.object` reification, no type triple) onto the real `rdf:PropositionForm`/`rdf:propositionForm{Subject,Predicate,Object}` vocabulary, keeping the existing content-addressed-URIRef minting strategy as-is - touches roughly a dozen files, now all within the single merged `starlayer` package. Paused, not rejected: asked directly whether this improves performance or reduces complexity before proceeding, and the honest answer is no to both - a 4th triple per unique triple-term value (~33% more triples for triple-term-bearing data), longer predicate IRIs, doubled filter-check logic at 5 sites, for a spec that (per the entry above) has zero confirmed real-world adopters of this vocabulary today. The benefit is standards-alignment optics, not a functional or performance gain. Revisit only with that tradeoff explicitly accepted, not assumed away - the scratch plan file this was originally written up in has since been reused for unrelated work, so the design above (not a linked file) is the authoritative record to resume from.

- **SPARQL entailment regimes not planned (and why).** Of the six regimes the [SPARQL 1.1/1.2 Entailment Regimes](https://www.w3.org/TR/sparql12-entailment/) spec defines, three have no plans to be built: **OWL 2 RDF-Based Semantics** (full, beyond the RL fragment already covered by `entailment="owl-rl"`) - undecidable in general (OWL Full has roughly first-order expressive power plus RDF's own reflective quirks); `owlrl`, the only OWL-RL dependency in this stack, implements the RL fragment specifically *because* that's the version with a terminating rule-based algorithm at all. **D-Entailment** (datatype canonicalization, e.g. recognizing `"01"^^xsd:integer` and `"1"^^xsd:integer` as the same *value*) - needs a full XSD datatype-map implementation inside the query engine's own term-equality logic; narrow and orthogonal to what this project exists for (RDF 1.2: triple terms, direction-tagged literals), and confirmed live against Jena's own docs that a Fuseki/Jena backend doesn't cover this either - an explicitly stated, deliberate gap in Jena's RDFS reasoner, not something delegating to a backend (`entailment="native"`) would close. **RIF Core Entailment** - no RIF interpreter anywhere in this stack, and no spec-conformance test infrastructure to verify one against even if built. (**OWL 2 Direct Semantics** is not in this bucket - `infer(profile="owl-dl")`/`query(entailment="direct")` cover it fully; see `packages/starlayer/starlayer/graph/CHANGELOG.md`.)

---

## Guide review findings (2026-09-26)

A full editorial pass over every notebook under `docs/guides/` plus `docs/README.ipynb` and the three standalone `docs/shacl-*-guide.ipynb` deep-dives (five parallel review passes, one per topic area) fixed typos and confirmed-stale references directly - see each notebook's own history for the specifics; not repeated here. What's below is what those passes found but deliberately did *not* fix, because it was bigger than a typo/staleness correction - grouped by guide-content gaps vs. underlying library gaps. **Snapshot from that date** - some items may have been resolved since by unrelated work; re-verify before acting on any of them rather than assuming they're still open.

**Guide-content gaps:**
- `docs/README.ipynb`'s index stops at "5.d" - `05e-owl-dl-reasoning.ipynb` and `05f-manchester-syntax.ipynb` both exist but aren't listed. Left unadded during the review since both files were being actively edited in the same session; worth a follow-up pass now that they've stabilized.
- `01-getting-started.ipynb`'s own "Where to go next" list has no entry at all for `05f-manchester-syntax.ipynb`.
- `03b-sparql-inferencing.ipynb`'s regime-support table lists "OWL 2 Direct Semantics" as "planned" - `entailment="direct"` has since shipped (see `packages/starlayer/starlayer/graph/CHANGELOG.md`). This table (and its "which regime to use" section) now needs a real update, not just a status-label flip.
- The three standalone root-level SHACL guides (`docs/shacl-node-expressions-guide.ipynb`, `docs/shacl-rules-guide.ipynb`, `docs/shacl-subgraph-extraction-guide.ipynb`) are near-verbatim frozen copies of `docs/guides/04a`/`04b`/`04f` respectively (per `docs/README.md`'s own "still present in `docs/` for reference" note) - not independent deep-dives, and already drifted slightly out of sync with their `docs/guides/` counterparts (a stale doc path, a "pending" reference to a guide that now exists - both already fixed in the `04a`/`04b` copies, not in the standalone ones). Two silently-diverging copies of the same content is a standing maintenance cost, not a one-time fix.
- `04-shacl-shapes.ipynb` §3.3: after correcting an overbroad claim about which constraint components support per-value severity annotation (see the starshacl gap below), the guide doesn't explicitly say the other three (`sh:uniqueMembers`/`sh:reificationRequired`/`sh:singleLine`) currently lack it.
- `05d-canonical-hashing.ipynb` narrates `.isomorphic()` in method-call style but only ever demonstrates the free function `starlayer.graph.compare.isomorphic()` - the bound `StarLayerGraph.isomorphic()` method (which exists, with its own more detailed TripleTerm-awareness docstring) is never shown or contrasted; ambiguous whether that's deliberate house style.
- `05f-manchester-syntax.ipynb`'s first markdown cell has a stray leftover editing instruction embedded in the guide's own prose ("CLAUDE: show this as a two column table.") - looks like an artifact from building the guide, not intentional content.

**graph/shacl subpackage gaps (code-level, found while reading the guides' own examples):**
- `infer(profile="owl-rl")`'s inconsistency signal (`err:error`/`err:ErrorMessage` triples) has no dedicated accessor - a caller has to know to filter the result graph for that namespace by hand. A convenience method (e.g. `graph.inconsistencies()`) would close an easy-to-miss footgun.
- `remove_reification(reifier, triple_term=None)` silently no-ops when `triple_term` isn't actually reified by that reifier - there's no way to distinguish "already gone" from "wrong reference/typo" anywhere in this API surface.
- `packages/starlayer/starlayer/shacl/subgraph_extraction.py`'s own module docstring (design decision #3) is stale relative to its own code: it still says `sh:or`/`sh:xone` extraction includes "only the branch that actually caused the pass... the first list member that conforms," which is correct for `sh:xone` but wrong for `sh:or` - the actual implementation (and the guide, correctly) includes *every* passing `sh:or` disjunct, per the 2026-09-13 revision recorded in this project's own memory/design notes. A one-line source-level docstring fix, not a behavior change.
- The per-constraint severity-annotation mechanism (`_annotation_value(...)`/`annotation_severity` in `packages/starlayer/starlayer/shacl/native_components.py`) is implemented once, ad hoc, inside `DatatypeConstraintComponent` rather than as a reusable mixin - if `sh:uniqueMembers`/`sh:reificationRequired`/`sh:singleLine` are meant to eventually support it too, the current structure requires duplicating it rather than reusing it. No test coverage exists for severity/deactivation annotations on any constraint type besides `sh:datatype`/`sh:property` either - not documented anywhere as a deliberate scope decision.
- `05b-backend-graph-databases.ipynb`'s two backend paths raise two different exception types on an unreachable endpoint - `urllib.error.URLError` for `backend="rdf-1.1"`, `requests.exceptions.ConnectionError` for `backend="rdf-1.2"` (native). A caller has to know which backend they're using just to catch the right exception; not documented as a known asymmetry anywhere in `packages/starlayer/docs/graph/`.
- `entailment="native"` is restricted to `backend="rdf-1.2"` only, even though `backend="rdf-1.1"` can also talk to a live SPARQL endpoint (via a `Store` plugin) and just can't delegate entailment to it. Possibly deliberate, but not called out as such anywhere.

---

## Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes

RDF 1.2 was at **Candidate Recommendation** (published 2026-04-07) as of this writing — not yet a final W3C Recommendation. Everything in this project (the gap analysis, the rewriter, the format modules) is checked against that CR-stage text. This project's own stated purpose (README: "intended to remain relevant until rdflib is updated to incorporate the final RDF 1.2 specification") means it has a deliberately limited lifespan, and needs periodic re-checking rather than a one-time gap analysis. Concrete steps for whoever picks this up as the spec progresses:

1. **Re-run the gap analysis at each W3C stage transition** (CR → PR → REC). CR-stage text can still change in response to implementation/horizontal-review feedback before Proposed Recommendation; re-diff `packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md` against the current editor's draft whenever the spec's status changes, not just once. `packages/starlayer/tests/graph/vendor/spec_snapshots/refresh_snapshots.py` automates the "what actually changed" half of that: it re-fetches all seven tracked documents and overwrites the saved snapshots, so `git diff packages/starlayer/tests/graph/vendor/spec_snapshots/` shows exactly what moved since the last review instead of requiring a full re-read.
2. **Watch the CR exit criteria / implementation report.** The RDF-star Working Group's CR exit requires a set of independent conforming implementations. Whichever engines end up counted (Oxigraph and Fuseki are the two this project already tracks) are worth re-verifying `starlayer.graph`'s rewriter against each time one of them ships a release claiming closer conformance — a live three-way comparison against the in-memory backend (see `packages/starlayer/tests/graph/integration/test_cross_backend_parity.py`) is the reusable tool for that, not a one-off.
3. **Watch for a real JSON-LD RDF-1.2 companion spec.** `jsonld12` was removed as a recognized format entirely (2026-10-02, see `packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md` §6) rather than kept as a partial "plain RDF 1.1 content only, refuse triple terms" format, since JSON-LD has no published RDF 1.2 companion spec at all. If the JSON-LD Working Group ever publishes an RDF-1.2-aware revision with its own native representation for quoted/triple terms, consider adding a real `jsonld12` format back for that representation. TriX has no standards body actively developing it, so `trix12` is unlikely to ever gain a real target to converge on — its "starlayer.graph convention, not a spec" status is probably permanent, and the documentation callout is the whole fix rather than a placeholder for a future code change.
4. **Once rdflib ships native RDF 1.2 support** — re-evaluate this project's continued existence, per its own stated scope. At that point: (a) consider deprecating `starlayer.graph`'s SPARQL 1.2→1.1 rewriter and in-memory triple-term encoding in favor of delegating straight to rdflib, and (b) check whether the `turtle12`/`nt12`/`nq12`/`trig12`/`rdfxml12` format modules can be dropped in favor of rdflib's own native parsers/serializers.
