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
4. **[SRL (SPARQL Rules)](04-srl-sparql-rules.ipynb)** - a Datalog-style rules language independent of SHACL: a first rule, matching several patterns, rules that build on each other, `FILTER`, negation (`NOT`), computing values (`SET`), creating nodes, and asking a question of a rule set (`query()`).
   - **4.a [SRL: how a rule set runs](04a-srl-running-rule-sets.ipynb)** - the evaluation plan, run-once rules, cycles and rejected rule sets, validation errors, running a rule set again, `DATA` blocks and `IMPORTS`.
   - **4.b [SRL: more features](04b-srl-more-features.ipynb)** - RDF 1.2 triple terms and annotations, property paths, grouping and aggregation, and combining SRL with entailment (`inference=`) and SHACL (`schema=`).
   - **4.c [SRL vs. SPARQL](04c-srl-vs-sparql.ipynb)** - a rule compared with a `CONSTRUCT`, `SET` and `BIND`, and the parts of the `WHERE` clause that SRL changes or leaves out: property paths, `EXISTS`, `NOT`, functions, and `WHERE GROUND` / `NOT GROUND`.
5. **[Validating with SHACL 1.2](05.01-validating-with-shacl-1.2.ipynb)** - the standard `validate()` call, then `StarShaclProcessor`, which is unique to StarLayer, and its three processing modes, what SHACL 1.2 adds to validation (RDF 1.2 terms and reifiers, new constraint components, lists, targets, severities, subclasses read from the shapes graph), reading a validation result and the errors (`ValidationReport`, `validate_each`, `ShapeError`), and entailment during validation. Its headings are numbered 05.01.1, 05.01.2 and so on.
   - **05.02 [The StarLayer SHACL engine](05.02-starlayer-shacl-engine.ipynb)** - the processor and the functions of `starlayer.shacl`: what is a method of `StarShaclProcessor` and what is only a function, how the processor is configured, deriving a shape from data (`derive_shape()`), checking a shapes graph (`meta_validate()`), which graphs the engine accepts, and the properties that describe a shape without validating it (`sh:name`, `sh:description`, `sh:intent`, `sh:unit`, `sh:order` and others).
   - **05.03 [SHACL shapes as classes](05.03-shapes-as-classes.ipynb)** - a shape that is also a class (`sh:ShapeClass`) targeting its instances, inheriting properties through the class hierarchy with `sh:closed sh:ByTypes`, and reading the hierarchy from the shapes graph (`subclass_of_in_shapes_graph`).
   - **05.04 [SHACL node expressions](05.04-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabulary, `sh:values`/`sh:expression`, custom functions.
   - **05.05 [SHACL and SPARQL](05.05-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintComponent`.
   - **05.06 [SHACL inference rules](05.06-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, execution ordering, rule sets, provenance.
   - **05.07 [SHACL UI](05.07-shacl-ui.ipynb)** - `shui:` widgets: fixed `shui:editor`/`shui:viewer` choices via `select_widgets()` (a dict of property shape to widget), launching a form in a browser, then `shui:WidgetScore` scoring for properties that name no widget, and `explain_widgets()` for why a widget was chosen.
   - **05.08 [SHACL profiling](05.08-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging conventions, making a set of shapes self-contained (`referenced_shapes`, `rule_dependencies`), `sh:conformsToShapesGraph` inference, profiling with SHACL, and StarLayer's own declared profiles.
   - **05.09 [SHACL subgraph extraction & hashing](05.09-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_shape()`, and the hash-and-verify commitment pattern.
   - **05.10 [Building on SHACL](05.10-building-on-shacl.ipynb)** - what an application that edits or displays shapes asks of `starlayer.shacl`: `infer_types`, `shapes_graph_members`, `meta_validate`, `path_values`, `evaluate_expression` and the widget functions.
   - **05.11 [SHACL `evaluate()`](05.11-shacl-evaluate.ipynb)** - using a shape to select the nodes and values to present, and to compute values and defaults, for a report or a UI.
6. **[StarLayer Schemas and Ontologies](06.01-starlayer-schemas-and-ontologies.ipynb)** - the vocabularies StarLayer defines for representing an artifact's own internal structure as RDF, inspectable/editable/validatable like any other graph; plus the registry that bundles all of them (including SKOS and the SHACL meta-shapes).
   - **06.02 [Manchester Syntax](06.02-manchester-syntax.ipynb)** - OWL 2 Manchester Syntax's English-readable notation, via `parse()`/`serialize()` with `format="manchester"`, plus treating a document's own internal structure as an inspectable, editable RDF graph via the `manch:` ontology.
   - **06.03 [SPARQL queries as RDF](06.03-sparql-query-as-rdf.ipynb)** - encoding, editing, and validating a query itself as an RDF graph, under the `sqe:` ontology.
   - **06.04 [SRL (SPARQL Rules) as RDF](06.04-srl-sparql-rules-as-rdf.ipynb)** - encoding a parsed SRL rule set as RDF under the `srl:` namespace, and SHACL-validating that encoding.
   - **06.05 [The SHACL library registry](06.05-shacl-library-registry.ipynb)** - loading the bundled ontologies and shapes by name, validating data against them, the StarLayer profiles that tie each shapes graph to its specification, and fetching each file directly from GitHub.
7. **Other**
   - **07.01 [Serialization formats](07.01-serialization-formats.ipynb)** - all eight RDF 1.2 formats `parse()`/`serialize()` support.
   - **07.02 [Choosing where your data lives](07.02-backend-graph-databases.ipynb)** - an on-disk Oxigraph store, and reading a remote SPARQL endpoint from a query with `SERVICE`.
   - **07.03 [Canonical hashing and graph comparison](07.03-canonical-hashing.ipynb)** - RDFC-1.0 canonicalization/hashing and graph isomorphism.

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
