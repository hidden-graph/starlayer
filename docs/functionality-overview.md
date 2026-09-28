# StarLayer Functionality Overview

*Last reviewed: 2026-09-28*

---

## Currently covered

### RDF graph (`starlayergraph`)

1. Manage RDF 1.2 graphs, including triple terms and direction-tagged literals.
2. In-memory graph management through rdflib using an RDF 1.1 transformation of RDF 1.2 graphs (the default backend).
3. Parse and serialize various RDF formats including both 1.1 and 1.2 versions of Turtle, LongTurtle, N-Triples, N-Quads, TriG, RDF/XML, and TriX 1.2. Parse and serialize JSON 1.1 and 1.2 (1.2 pending).
4. Multi-graph support via `StarLayerDataset`.
5. Support for native backend storage over HTTP (e.g. Fuseki, Oxigraph) using backend RDF 1.2 support when available. Also supports SQLAlchemy-backed storage as a `Store=` plugin.
6. RDF-1.2-aware graph isomorphism/comparison.
7. RDFC-1.0 canonicalization/hashing of RDF 1.2 graphs.

### SPARQL (`starsparql`)

1. SPARQL 1.2 query of starlayergraph.
2. Starlayer specific RDF ontology for representing SPARQL queries. (`salg:` namespace)
3. SHACL shapes for `salg:` graphs.
4. Cross-referential semantic checks beyond SHACL's own per-node reach (`find_unbound_projected_variables()`) - e.g. a query projecting a variable never actually bound anywhere in its own pattern.

### Manchester Syntax

1. Manchester OWL syntax support for parse and serialize.
2. Starlayer specific RDF ontology for representing a Manchester document. (`manch:` namespace)
3. SHACL shapes for `manch:` graphs.

### Reasoning

1. Support for reasoning/inference using various entailment regimes: RDF, RDFS, OWL-RL, and OWL-DL.
2. OWL-DL support via two engines: `engine="hermit"` (`owlready2`, Java) or `engine="rustdl"` (Rust).
3. Support for both graph reasoning and query-time reasoning.
4. A wall-clock timeout (`timeout=`, default 120s, both engines) for OWL-DL reasoning calls, with a real subprocess/process-group kill on expiry - no orphaned JVM/native process left behind.

### SHACL (`starshacl`)

1. Support for use of SHACL 1.2 over RDF 1.2 graphs.
2. Support for additional SHACL 1.2 specifications:
   - SPARQL Extensions
   - Node Expressions
   - Rules
   - User Interfaces
   - Profiling
3. SHACL 1.2 meta-shapes for use with SHACL shape files.
4. SHACL-driven subgraph extraction.
5. Ability to infer a SHACL shape from a graph's own data.

### Other

1. VERSION-directive conformance warnings.
2. SKOS: an OWL/RDFS ontology based on the W3C SKOS Reference's own formal axioms.
3. SHACL shape validation of SKOS graphs.
4. A registry to list/look up any of the supported ontology/SHACL-shapes files:
   - `manchester_owl` / `manchester_shacl`
   - `skos_owl` / `skos_shacl`
   - `sparql_owl` / `sparql_shacl`
   - `shacl_meta`

## Planned / deferred

**Cross-cutting (`packages/graph/docs/future_enhancements.md`)**


1. rdflib 8 compatibility (currently pinned to rdflib 7.x; revisit once a stable rdflib 8 ships).
2. The RDF 1.2 Interoperability spec's `rdf:PropositionForm` vocabulary retrofit onto internal triple-term storage - fully designed, explicitly paused (worse performance and complexity, standards-alignment optics only, no confirmed adopters of the vocabulary yet).

**`starsparql` (planned, not a known gap - see `packages/shacl/docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" for the spec-status writeup)**

1. SRL/SPARQL-RL - "a Datalog-style rules language for RDF," general-purpose and SHACL-independent (the spec's own framing, despite living in the `shacl12-*`-adjacent W3C Data Shapes WG family). Not blocked on spec maturity: `WD-sparql12-rl-20260919` already has a complete, real EBNF grammar and formal evaluation semantics (stratification, rule-dependency graphs) - enough to build a real parser against today, same bar this project already applies to RDF 1.2/SPARQL 1.2/the rest of SHACL 1.2 (all pre-Recommendation too). No RDF representation for SRL rules exists in the spec yet, though - the same shape of gap `manch:`/`salg:` already fill elsewhere in this project: parse the text, invent the RDF-as-AST representation (a new `srl:` namespace), add SHACL shapes over it, mirroring the Manchester/SPARQL AST-as-RDF pattern - belongs in `starsparql`, not `starshacl`, since SRL is its own general-purpose rules language, not part of the `sh:` vocabulary. Not yet designed/scoped.

**`starshacl` (see `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred")**

1. SHACL 1.2 UI's `shui:WidgetScore`/`shui:WidgetAcceptMatcher` widget-selection algorithm - blocked on upstream: `WidgetAcceptMatcher` still has no formal vocabulary shape in the spec itself.
2. SHACL Compact syntax support, plus an ontology/shape over *that* syntax (mirroring the Manchester/SPARQL AST-as-RDF pattern) to drive validation and an editor.

