# StarLayer Functionality Overview

*Last reviewed: 2026-09-29*

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
4. SRL/SPARQL-RL (`WD-sparql12-rl-20260919`) - a Datalog-style rules language, general-purpose and SHACL-independent: parsing (`srl_grammar.py`, reusing rdflib's own SPARQL expression/terminal grammar directly), a `srl:` RDF-as-AST representation with a full round trip (`srl_vocab.py`/`srl_to_rdf.py`/`srl_from_rdf.py`), SHACL shapes over `srl:` graphs, the §4.2 well-formedness cross-referential check (`srl_semantic_checks.py`), and a full stratified Datalog evaluation engine (`srl_eval.py` - dependency graph, stratification, `evalRule`, top-level `Infer`/`Query`) verified end to end against the spec's own §6.6 worked example.


### Manchester Syntax

1. Manchester OWL syntax support for parse and serialize.
2. Starlayer specific RDF ontology for representing a Manchester document. (`manch:` namespace)
3. SHACL shapes for `manch:` graphs.

### Reasoning

1. Support for reasoning/inference using various entailment regimes: RDF, RDFS, OWL-RL, and OWL-DL.
2. OWL-DL support via two engines: `engine="hermit"` (`owlready2`, Java) or `engine="rustdl"` (Rust).
3. Support for both graph reasoning and query-time reasoning.


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
5. Ability to create a SHACL shape from a graph's own data.

### Other

1. VERSION-directive conformance warnings.
2. SKOS: an OWL/RDFS ontology based on the W3C SKOS Reference's formal axioms.
3. SHACL shape validation of SKOS graphs.
4. A registry of the supported ontology and SHACL-shapes files:
   - `manchester_owl` / `manchester_shacl`
   - `skos_owl` / `skos_shacl`
   - `sparql_owl` / `sparql_shacl`
   - `srl_owl` / `srl_shacl`
   - `shacl_meta`

## Planned / deferred

**Cross-cutting (`packages/graph/docs/future_enhancements.md`)**


1. rdflib 8 compatibility (currently pinned to rdflib 7.x; revisit once a stable rdflib 8 ships).
2. The RDF 1.2 Interoperability spec's `rdf:PropositionForm` vocabulary retrofit onto internal triple-term storage - fully designed, explicitly paused (worse performance and complexity, standards-alignment optics only, no confirmed adopters of the vocabulary yet).

**`starshacl` (see `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred")**

1. SHACL 1.2 UI's `shui:WidgetScore`/`shui:WidgetAcceptMatcher` widget-selection algorithm - blocked on upstream: `WidgetAcceptMatcher` still has no formal vocabulary shape in the spec itself.
2. SHACL Compact syntax support, plus an ontology/shape over *that* syntax (mirroring the Manchester/SPARQL AST-as-RDF pattern) to drive validation and an editor.

