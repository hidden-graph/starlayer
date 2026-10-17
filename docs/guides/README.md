# StarLayer User Guides

*Last reviewed: 2026-10-14*

This is the single master index for every guide notebook - every notebook's own "How to run this notebook" cell links back here, rather than repeating this list in-body (see [`STYLE_GUIDE.md`](STYLE_GUIDE.md)). Update this file when a guide is added, renamed, or reordered; no other file needs to change.

The full guide set has been reorganized into `docs/guides/`, one focused notebook per topic, replacing the single broad `user-guide-v1_01.ipynb` plus three separately-named SHACL deep-dives (those four original files are deleted as of 2026-10-10 - nothing referenced them except this note - everything below now lives in `docs/guides/`).

**Reading order**: if you're new to the project, start at the top and work down. If you already know what you're doing, jump straight to the topic you need.

## The guides

1. **[Getting Started](01-getting-started.ipynb)** - install, first parse, first query, first validate.
2. **[Graphs](02-graphs.ipynb)** - `TripleTerm`/`DirLangString` semantics.
   - **2.a [Working with datasets](02a-graphs-datasets.ipynb)** - `StarLayerDataset`, multiple named graphs in one store.
   - **2.b [Inferencing](02b-graphs-inferencing.ipynb)** - RDF/RDFS/OWL 2 RL reasoning via `owlrl` (and natively for RDF), the full entailment-regime picture (what each regime means, the regime-support status table, which one to use), and a worked example of both the `infer()` and `query(entailment=...)` forms per regime.
   - **2.c [OWL 2 DL reasoning](02c-owl-dl-reasoning.ipynb)** - `infer(entailment=ENTAILMENT["OWL-Direct"])`, genuine DL reasoning via HermiT (default, needs a real JVM) or RustDL (pure Rust, no JVM, with its own tradeoffs).
3. **[SPARQL](03-sparql.ipynb)** - query semantics and built-in functions.
   - **3.a [SPARQL entailment](03a-sparql-entailment.ipynb)** - what's specific to `query(entailment=...)` beyond what 2.b already covers per regime: caching behavior (`infer=`) and detecting an inconsistency via `ASK`.
   - **3.b [SRL (SPARQL Rules)](03b-srl-sparql-rules.ipynb)** - a separate Datalog-style rules language independent of SHACL: parsing (including RDF 1.2 triple terms, annotations, `/` `^` property paths and `IMPORTS`), inference, the evaluation plan (strata and dependency edges), querying, and well-formedness checking.
4. **[SHACL shapes](04-shacl-shapes.ipynb)** - what starshacl adds over pySHACL, and an overview of its four processing modes (`validate()`, `apply_rules()`, `evaluate()`, `extract_subgraph()`).
   - **4.a [SHACL node expressions](04a-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabulary, `sh:values`/`sh:expression`, custom functions.
   - **4.b [SHACL and SPARQL](04b-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintComponent`.
   - **4.c [SHACL inference rules](04c-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, execution ordering, rule sets, provenance.
   - **4.d [SHACL UI](04d-shacl-ui.ipynb)** - `shui:` widgets: fixed `shui:editor`/`shui:viewer` choices via `select_widgets()` (a dict of property shape to widget), launching a form in a browser, then `shui:WidgetScore` scoring for properties that name no widget.
   - **4.e [SHACL profiling](04e-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging conventions.
   - **4.f [SHACL subgraph extraction & hashing](04f-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_shape()`, and the hash-and-verify commitment pattern.
5. **[StarLayer Schemas and Ontologies](05-starlayer-schemas-and-ontologies.ipynb)** - the vocabularies StarLayer defines for representing an artifact's own internal structure as RDF, inspectable/editable/validatable like any other graph; plus the registry that bundles all of them (including SKOS and the SHACL meta-shapes).
   - **5.a [Manchester Syntax](05a-manchester-syntax.ipynb)** - OWL 2 Manchester Syntax's English-readable notation, via `parse()`/`serialize()` with `format="manchester"`, plus treating a document's own internal structure as an inspectable, editable RDF graph via the `manch:` ontology.
   - **5.b [SPARQL queries as RDF](05b-sparql-query-as-rdf.ipynb)** - encoding, editing, and validating a query itself as an RDF graph, under the `sqe:` ontology.
   - **5.c [SRL (SPARQL Rules) as RDF](05c-srl-sparql-rules-as-rdf.ipynb)** - encoding a parsed SRL rule set as RDF under the `srl:` namespace, and SHACL-validating that encoding.
6. **Other**
   - **6.a [Serialization formats](06a-serialization-formats.ipynb)** - all eight RDF 1.2 formats `parse()`/`serialize()` support.
   - **6.b [Choosing where your data lives](06b-backend-graph-databases.ipynb)** - remote SPARQL endpoints, SQLAlchemy-backed storage, and embedded Oxigraph - Transport and Persistence, independent of the RDF 1.1/1.2 representation.
   - **6.c [Canonical hashing and graph comparison](06c-canonical-hashing.ipynb)** - RDFC-1.0 canonicalization/hashing and graph isomorphism.

## Appendices

Standalone reference notebooks that don't fit the numbered guide sequence above - catalogs and collections of more advanced examples, rather than topic walkthroughs.

- **[Appendix A: Public Resources](appendix-a-public-resources.ipynb)** - every ontology/SHACL/profile file StarLayer bundles, and how to fetch each one directly from GitHub.
- **[Appendix B: Complex examples](appendix-b.ipynb)** - index of worked examples too large to keep inline in the guide they're drawn from.
  - **B1. [Named, shared parts in `sqe:` query trees](appendix-b1-sqe-shared-parts.ipynb)** - giving a query part a real, named identity instead of a private `BNode`, so more than one query can share and jointly edit it.
  - **B2. [A complex DL reasoning example](appendix-b2-dl-reasoning-examples.ipynb)** - a 20-person employee/job constraint-satisfaction problem encoded as an OWL 2 DL ontology and solved via consistency-checking alone.

## Related project documentation

The guides above are user-facing walkthroughs. For implementation detail, compatibility contracts, and spec-tracking:

- [`functionality-overview.md`](../functionality-overview.md) - a concise, bullet-point inventory of what's currently covered across all three packages, and what's planned/deferred - start here for "does StarLayer support X".
- [`api-reference.md`](../api-reference.md) - the exhaustive, name-by-name public API surface (every class/function/method importable from `starlayer`) - start here for "what's the exact signature of X."
- [`../../packages/starlayer/docs/future_enhancements.md`](../../packages/starlayer/docs/future_enhancements.md) - open suggestions and known, deliberately-deferred gaps.
- [`../../packages/starlayer/docs/graph/starlayergraph.md`](../../packages/starlayer/docs/graph/starlayergraph.md) - the graph subpackage's architecture and design, including backend compatibility.
- [`../../packages/starlayer/docs/shacl/compatibility.md`](../../packages/starlayer/docs/shacl/compatibility.md) - the shacl subpackage's graph contract, version support, and backend compatibility matrix.
- [`../../packages/starlayer/docs/shacl/shacl12-gap-matrix.md`](../../packages/starlayer/docs/shacl/shacl12-gap-matrix.md) - SHACL 1.2 feature-by-feature status across all six W3C documents.
