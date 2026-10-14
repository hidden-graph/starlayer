# StarLayer User Guides

*Last reviewed: 2026-10-14*

This is the single master index for every guide notebook - every notebook's own "How to run this notebook" cell links back here, rather than repeating this list in-body (see [`STYLE_GUIDE.md`](STYLE_GUIDE.md)). Update this file when a guide is added, renamed, or reordered; no other file needs to change.

The full guide set has been reorganized into `docs/guides/`, one focused notebook per topic, replacing the single broad `user-guide-v1_01.ipynb` plus three separately-named SHACL deep-dives (those four original files are deleted as of 2026-10-10 - nothing referenced them except this note - everything below now lives in `docs/guides/`).

**Reading order**: if you're new to the project, start at the top and work down. If you already know what you're doing, jump straight to the topic you need.

## The guides

1. **[Getting Started](01-getting-started.ipynb)** - install, first parse, first query, first validate.
2. **[Graphs](02-graphs.ipynb)** - `TripleTerm`/`DirLangString` semantics.
   - **2.a [Working with datasets](02a-graphs-datasets.ipynb)** - `StarLayerDataset`, multiple named graphs in one store.
   - **2.b [Inferencing](02b-graphs-inferencing.ipynb)** - RDFS and OWL 2 RL reasoning via `owlrl`, and the full entailment-regime picture (what each regime means, the regime-support status table, which one to use).
   - **2.c [OWL 2 DL reasoning](02c-owl-dl-reasoning.ipynb)** - `infer(entailment=ENTAILMENT["OWL-Direct"])`, genuine DL reasoning via HermiT (default, needs a real JVM) or RustDL (pure Rust, no JVM, with its own tradeoffs).
3. **[SPARQL](03-sparql.ipynb)** - query semantics and built-in functions.
   - **3.a [SPARQL entailment](03a-sparql-inferencing.ipynb)** - query-time entailment (`.query(entailment=ENTAILMENT.RDF/.RDFS/["OWL-RDF-Based"]/["OWL-Direct"]/"native")`), independent of `infer()`'s own graph-materializing entailment; the regimes themselves are explained in 2.b above, this guide just shows them applied at query time.
   - **3.b [SPARQL-RL rules](03b-sparql-rules.ipynb)** - SRL, a separate Datalog-style rules language independent of SHACL: parsing, inference, dependency-graph/stratification, and well-formedness checking.
4. **[SHACL shapes](04-shacl-shapes.ipynb)** - what starshacl adds over pySHACL, and an overview of its four processing modes (`validate()`, `apply_rules()`, `evaluate()`, `extract_subgraph()`).
   - **4.a [SHACL node expressions](04a-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabulary, `sh:values`/`sh:expression`, custom functions.
   - **4.b [SHACL and SPARQL](04b-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintComponent`.
   - **4.c [SHACL inference rules](04c-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, execution ordering, rule sets, provenance.
   - **4.d [SHACL UI](04d-shacl-ui.ipynb)** - `shui:` presentation metadata.
   - **4.e [SHACL profiling](04e-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging conventions.
   - **4.f [SHACL subgraph extraction & hashing](04f-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_shape()`, and the hash-and-verify commitment pattern.
5. **StarLayer Schemas and Ontologies** - the vocabularies StarLayer defines for representing an artifact's own internal structure as RDF, inspectable/editable/validatable like any other graph.
   - **5.a [Manchester Syntax](05a-manchester-syntax.ipynb)** - OWL 2 Manchester Syntax's English-readable notation, via `parse()`/`serialize()` with `format="manchester"`, plus treating a document's own internal structure as an inspectable, editable RDF graph via the `manch:` ontology.
   - **5.b [SPARQL queries as RDF](05b-sparql-query-as-rdf.ipynb)** - encoding, editing, and validating a query itself as an RDF graph, under the `salg:` ontology.
   - **5.c [SPARQL-RL rules as RDF](05c-sparql-rules-as-rdf.ipynb)** - encoding a parsed SRL rule set as RDF under the `srl:` namespace, and SHACL-validating that encoding.
   - **5.d [The SHACL library registry](05d-shacl-library-registry.ipynb)** - discovering and loading any of `manch:`/`skos:`/`salg:`/`srl:`/the SHACL 1.2 meta-shapes by name via `starontology.get_ontology_list()`/`get_ontology_graph(name)` - ties together every ontology/shapes pair above, plus `skos:` (the W3C SKOS Reference, formalized the same way) and `shacl_meta`, neither of which needs a guide of its own beyond what this registry already shows.
6. **Other**
   - **6.a [Serialization formats](06a-serialization-formats.ipynb)** - all eight RDF 1.2 formats `parse()`/`serialize()` support.
   - **6.b [Working with backend graph databases](06b-backend-graph-databases.ipynb)** - Oxigraph, Fuseki, and SQLAlchemy-backed storage.
   - **6.c [Canonical hashing and graph comparison](06c-canonical-hashing.ipynb)** - RDFC-1.0 canonicalization/hashing and graph isomorphism.

## Related project documentation

The guides above are user-facing walkthroughs. For implementation detail, compatibility contracts, and spec-tracking:

- [`functionality-overview.md`](../functionality-overview.md) - a concise, bullet-point inventory of what's currently covered across all three packages, and what's planned/deferred - start here for "does StarLayer support X".
- [`api-reference.md`](../api-reference.md) - the exhaustive, name-by-name public API surface (every class/function/method importable from `starlayer`) - start here for "what's the exact signature of X."
- [`../../packages/starlayer/docs/future_enhancements.md`](../../packages/starlayer/docs/future_enhancements.md) - open suggestions and known, deliberately-deferred gaps.
- [`../../packages/starlayer/docs/graph/starlayergraph.md`](../../packages/starlayer/docs/graph/starlayergraph.md) - the graph subpackage's architecture and design, including backend compatibility.
- [`../../packages/starlayer/docs/shacl/compatibility.md`](../../packages/starlayer/docs/shacl/compatibility.md) - the shacl subpackage's graph contract, version support, and backend compatibility matrix.
- [`../../packages/starlayer/docs/shacl/shacl12-gap-matrix.md`](../../packages/starlayer/docs/shacl/shacl12-gap-matrix.md) - SHACL 1.2 feature-by-feature status across all six W3C documents.
