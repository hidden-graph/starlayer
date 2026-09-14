# StarLayer User Guides

*Last reviewed: 2026-09-14*

The full guide set has been reorganized into `docs/guides/`, one focused notebook per topic, replacing the single broad `user-guide-v1_01.ipynb` plus three separately-named SHACL deep-dives (those four original files are still present in `docs/` for reference, but everything below now lives in `docs/guides/`).

**Reading order**: if you're new to the project, start at the top and work down. If you already know what you're doing, jump straight to the topic you need.

## The guides

1. **[Getting Started](guides/01-getting-started.ipynb)** - install, first parse, first query, first validate.
2. **[Graphs](guides/02-graphs.ipynb)** - `TripleTerm`/`DirLangString` semantics, all eight RDF 1.2 formats, `StarLayerDataset`, RDFC-1.0 canonicalization/hashing and graph isomorphism.
3. **[SPARQL](guides/03-sparql.ipynb)** - query semantics and built-in functions, plus encoding/editing/validating a SPARQL query as RDF.
   - **3.a [SPARQL rules (pending)](guides/03a-sparql-rules-pending.md)** - SPARQL-RL (SRL), a separate Datalog-style rules language, is deliberately out of scope for this project.
4. **[SHACL shapes](guides/04-shacl-shapes.ipynb)** - what starshacl adds over pySHACL, and an overview of its four processing modes (`validate()`, `apply_rules()`, `evaluate()`, `extract_subgraph()`).
   - **4.a [SHACL node expressions](guides/04a-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabulary, `sh:values`/`sh:expression`, custom functions.
   - **4.b [SHACL inference rules](guides/04b-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, execution ordering, rule sets, provenance.
   - **4.c [SHACL and SPARQL](guides/04c-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintComponent`.
   - **4.d [SHACL UI](guides/04d-shacl-ui.ipynb)** - `shui:` presentation metadata.
   - **4.e [SHACL profiling](guides/04e-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging conventions.
   - **4.f [SHACL subgraph extraction & hashing](guides/04f-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_shape()`, and the hash-and-verify commitment pattern.
5. **[Inferencing](guides/05-inferencing.ipynb)** - RDFS subclass reasoning and (not yet implemented) OWL reasoning.
6. **[Working with backend graph databases](guides/06-backend-graph-databases.ipynb)** - Oxigraph, Fuseki, and SQLAlchemy-backed storage.

## Related project documentation

The guides above are user-facing walkthroughs. For implementation detail, compatibility contracts, and spec-tracking:

- `packages/graph/docs/starlayergraph.md` - starlayergraph architecture and design, including backend compatibility.
- `packages/shacl/docs/compatibility.md` - starshacl's graph contract, version support, and backend compatibility matrix.
- `packages/shacl/docs/shacl12-gap-matrix.md` - SHACL 1.2 feature-by-feature status across all six W3C documents.
