# StarLayer User Guides

*Last reviewed: 2026-11-17*

This is the single master index for every guide notebook - every notebook's own "How to run this notebook" cell links back here, rather than repeating this list in-body (see [`STYLE_GUIDE.md`](STYLE_GUIDE.md)). Update this file when a guide is added, renamed, or reordered; no other file needs to change.

**Reading order**: if you're new to the project, start at the top and work down. If you already know what you're doing, jump straight to the topic you need.

## The guides

1. **[Getting Started](01-getting-started.ipynb)** - install, first parse, first query, first validate.
2. **[Graphs](02-graphs.ipynb)** - RDF 1.2 triple terms, reifiers, annotations and directional language strings, and the Turtle 1.2 syntax for them.
   - **2.a [Working with datasets](02a-graphs-datasets.ipynb)** - `StarLayerDataset`, multiple named graphs in one store.
   - **2.b [The Oxigraph-backed graph](02b-oxigraph-wrapper.ipynb)** - `StarLayerGraph` / `StarLayerDataset` hold a `pyoxigraph.Store`: any store method can be called through `.ox` on the graph or dataset (`g.ox.load(...)`), which is better than `.store` because the wrapper records writes (the caching warning); converting to and from rdflib.
   - **2.c [Reading and building graph content](02c-graph-content.ipynb)** - terms and Python values (`literal`, `to_python`, `parse_term`), RDF lists, single values and walks, prefixes, and `profile()` of a graph or dataset.
   - **2.d [Combining and comparing graphs](02d-combining-comparing-graphs.ipynb)** - set operations, `diff` and `GraphDelta`, matching blank nodes (`align_blank_nodes`), `owl:imports` with a loader, and skolemizing blank nodes.
   - **2.e [Inferencing](02e-graphs-inferencing.ipynb)** - RDF/RDFS/OWL 2 RL reasoning via `owlrl` (and natively for RDF), the full entailment-regime picture (what each regime means, the regime-support status table, which one to use), and a worked example of both the `infer()` and `query(entailment=...)` forms per regime.
   - **2.f [OWL 2 DL reasoning](02f-owl-dl-reasoning.ipynb)** - `infer(entailment=ENTAILMENT["OWL-Direct"])`, genuine DL reasoning via HermiT (default, needs a real JVM) or RustDL (pure Rust, no JVM, with its own tradeoffs).
3. **[SPARQL](03-sparql.ipynb)** - running a query and reading its result, prefixes, `DESCRIBE`, writing results as JSON, XML, CSV, TSV or RDF (`Result.serialize`), and SPARQL Update on a graph and on a dataset.
   - **3.a [SPARQL 1.2 in queries](03a-sparql-12-queries.ipynb)** - triple functions (`TRIPLE`, `SUBJECT`, `isTRIPLE`), triple-term and annotation syntax in queries, language and direction functions, and the `VERSION` directive.
   - **3.b [Preparing, extending and checking queries](03b-preparing-extending-checking-queries.ipynb)** - the triples an answer depends on (`relevant_subgraph`), a query prepared once (`StarQuery`), your own Python functions and aggregates (`custom_functions`), and `check_query`.
   - **3.c [SPARQL entailment](03c-sparql-entailment.ipynb)** - what's specific to `query(entailment=...)` beyond what 2.e already covers per regime: caching behavior (`recompute=`) and detecting an inconsistency via `ASK`.
   - **3.d [SRL (SPARQL Rules)](03d-srl-sparql-rules.ipynb)** - a Datalog-style rules language independent of SHACL: a first rule, matching several patterns, rules that build on each other, `FILTER`, negation (`NOT`), computing values (`SET`), creating nodes, and asking a question of a rule set (`query()`).
   - **3.e [SRL: how a rule set runs](03e-srl-running-rule-sets.ipynb)** - the evaluation plan, run-once rules, cycles and rejected rule sets, validation errors, running a rule set again, `DATA` blocks and `IMPORTS`.
   - **3.f [SRL: more features](03f-srl-more-features.ipynb)** - RDF 1.2 triple terms and annotations, property paths, grouping and aggregation, and combining SRL with entailment (`inference=`) and SHACL (`schema=`).
4. **[SHACL shapes](04-shacl-shapes.ipynb)** - what starshacl adds over pySHACL, an overview of its four processing modes (`validate()`, `apply_rules()`, `evaluate()`, `extract_subgraph()`), reading a validation result and the errors (`ValidationResult`, `validate_each`, `ShapeError`), entailment during validation, and deriving a shapes graph from data (`derive_shape()`).
   - **4.a [SHACL node expressions](04a-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabulary, `sh:values`/`sh:expression`, custom functions.
   - **4.b [SHACL and SPARQL](04b-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintComponent`.
   - **4.c [SHACL inference rules](04c-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, execution ordering, rule sets, provenance.
   - **4.d [SHACL UI](04d-shacl-ui.ipynb)** - `shui:` widgets: fixed `shui:editor`/`shui:viewer` choices via `select_widgets()` (a dict of property shape to widget), launching a form in a browser, then `shui:WidgetScore` scoring for properties that name no widget, and `explain_widgets()` for why a widget was chosen.
   - **4.e [SHACL profiling](04e-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging conventions, and making a set of shapes self-contained (`referenced_shapes`, `rule_dependencies`).
   - **4.f [SHACL subgraph extraction & hashing](04f-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_shape()`, and the hash-and-verify commitment pattern.
   - **4.g [Building on SHACL](04g-building-on-shacl.ipynb)** - what an application that edits or displays shapes asks of `starlayer.shacl`: `infer_types`, `shapes_graph_members`, `sparql_query_problems`, `path_values`, `evaluate_expression` and the widget functions.
5. **[StarLayer Schemas and Ontologies](05-starlayer-schemas-and-ontologies.ipynb)** - the vocabularies StarLayer defines for representing an artifact's own internal structure as RDF, inspectable/editable/validatable like any other graph; plus the registry that bundles all of them (including SKOS and the SHACL meta-shapes).
   - **5.a [Manchester Syntax](05a-manchester-syntax.ipynb)** - OWL 2 Manchester Syntax's English-readable notation, via `parse()`/`serialize()` with `format="manchester"`, plus treating a document's own internal structure as an inspectable, editable RDF graph via the `manch:` ontology.
   - **5.b [SPARQL queries as RDF](05b-sparql-query-as-rdf.ipynb)** - encoding, editing, and validating a query itself as an RDF graph, under the `sqe:` ontology.
   - **5.c [SRL (SPARQL Rules) as RDF](05c-srl-sparql-rules-as-rdf.ipynb)** - encoding a parsed SRL rule set as RDF under the `srl:` namespace, and SHACL-validating that encoding.
   - **5.d [The SHACL library registry](05d-shacl-library-registry.ipynb)** - loading the bundled ontologies and shapes by name, validating data against them, the StarLayer profiles that tie each shapes graph to its specification, and fetching each file directly from GitHub.
6. **Other**
   - **6.a [Serialization formats](06a-serialization-formats.ipynb)** - all eight RDF 1.2 formats `parse()`/`serialize()` support.
   - **6.b [Choosing where your data lives](06b-backend-graph-databases.ipynb)** - an on-disk Oxigraph store, and reading a remote SPARQL endpoint from a query with `SERVICE`.
   - **6.c [Canonical hashing and graph comparison](06c-canonical-hashing.ipynb)** - RDFC-1.0 canonicalization/hashing and graph isomorphism.

## Appendices

Standalone reference notebooks that don't fit the numbered guide sequence above - catalogs and collections of more advanced examples, rather than topic walkthroughs.

- **[Appendix A: Public Resources](appendix-a-public-resources.ipynb)** - every ontology/SHACL/profile file StarLayer bundles, and how to fetch each one directly from GitHub.
- **[Appendix B: Complex examples](appendix-b.ipynb)** - index of worked examples too large to keep inline in the guide they're drawn from.
  - **B1. [Named, shared parts in `sqe:` query trees](appendix-b1-sqe-shared-parts.ipynb)** - giving a query part a real, named identity instead of a private `BNode`, so more than one query can share and jointly edit it.
  - **B2. [A complex DL reasoning example](appendix-b2-dl-reasoning-examples.ipynb)** - a 20-person employee/job constraint-satisfaction problem encoded as an OWL 2 DL ontology and solved via consistency-checking alone.

## Related project documentation

The guides above are user-facing walkthroughs. For implementation detail, compatibility contracts, and spec-tracking:

- [`functionality-overview.generated.md`](../generated/functionality-overview.generated.md) - an inventory of what's currently covered, generated from the curated functionality graph - start here for "does StarLayer support X".
- [`api-overview.generated.md`](../generated/api-overview.generated.md) and [`api-reference.generated.md`](../generated/api-reference.generated.md) - the public API surface, name by name, generated from the code knowledge graph - start here for "what's the exact signature of X."
- [`../../docs/design/future_enhancements.md`](../../docs/design/future_enhancements.md) - open suggestions and known, deliberately-deferred gaps.
- [`../../docs/design/shacl/compatibility.md`](../../docs/design/shacl/compatibility.md) - the shacl subpackage's graph contract, version support, and backend compatibility matrix.
- [`../../docs/design/shacl/shacl12-gap-matrix.md`](../../docs/design/shacl/shacl12-gap-matrix.md) - SHACL 1.2 feature-by-feature status across all six W3C documents.
