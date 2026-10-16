# StarLayer Functionality Overview (generated)

Generated from the hand-curated functionality graph (`packages/starlayer/starlayer/codekg/curated/functionality.ttl`). First pass - not a byte-for-byte reproduction of the hand-written `docs/functionality-overview.md` this is meant to eventually replace.

## RDF graph (`starlayergraph`)

- Manage RDF 1.2 graphs, including triple terms and direction-tagged literals.
- In-memory graph management through rdflib using an RDF 1.1 transformation of RDF 1.2 graphs (the default backend).
- Parse and serialize various RDF formats including both 1.1 and 1.2 versions of Turtle, LongTurtle, N-Triples, N-Quads, TriG, RDF/XML, and TriX 1.2. Parse and serialize JSON 1.1 and 1.2 (1.2 pending).
- Multi-graph support via `StarLayerDataset`.
- Support for native backend storage over HTTP (e.g. Fuseki, Oxigraph) using backend RDF 1.2 support when available. Also supports SQLAlchemy-backed storage as a `Store=` plugin.
- RDF-1.2-aware graph isomorphism/comparison.
- RDFC-1.0 canonicalization/hashing of RDF 1.2 graphs.

**Planned / deferred:**

- rdflib 8 compatibility (currently pinned to rdflib 7.x; revisit once a stable rdflib 8 ships).
- The RDF 1.2 Interoperability spec's `rdf:PropositionForm` vocabulary retrofit onto internal triple-term storage - fully designed, explicitly paused (worse performance and complexity, standards-alignment optics only, no confirmed adopters of the vocabulary yet).

## SPARQL (`starsparql`)

- SPARQL 1.2 query of starlayergraph.
- Starlayer specific RDF ontology for representing SPARQL queries, for hand/UI editing. (`sqe:` namespace - built on an internal, non-public full-algebra encoding)
- SHACL shapes for `sqe:` graphs.
- SRL/SPARQL-RL (`WD-sparql12-rl-20260919`) - a Datalog-style rules language, general-purpose and SHACL-independent: parsing (`srl.py`, reusing rdflib's own SPARQL expression/terminal grammar directly), a `srl:` RDF-as-AST representation with a full round trip (also `srl.py`), SHACL shapes over `srl:` graphs, the §4.2 well-formedness cross-referential check (`srl_semantic_checks.py`), and a full stratified Datalog evaluation engine (`srl_eval.py` - dependency graph, stratification, `evalRule`, top-level `Infer`/`Query`) verified end to end against the spec's own §6.6 worked example.

## Manchester Syntax

- Manchester OWL syntax support for parse and serialize.
- Starlayer specific RDF ontology for representing a Manchester document. (`manch:` namespace)
- SHACL shapes for `manch:` graphs.

## Reasoning

- Support for reasoning/inference using various entailment regimes: RDF, RDFS, OWL-RL, and OWL-DL.
- OWL-DL support via two engines: `engine="hermit"` (`owlready2`, Java) or `engine="rustdl"` (Rust).
- Support for both graph reasoning and query-time reasoning.

## SHACL (`starshacl`)

- Support for use of SHACL 1.2 over RDF 1.2 graphs.
- Support for additional SHACL 1.2 specifications: SPARQL Extensions, Node Expressions, Rules, User Interfaces, Profiling.
- SHACL 1.2 meta-shapes for use with SHACL shape files.
- SHACL-driven subgraph extraction.
- Ability to create a SHACL shape from a graph's own data.

**Planned / deferred:**

- SHACL 1.2 UI's `shui:WidgetScore`/`shui:WidgetAcceptMatcher` widget-selection algorithm - blocked on upstream: `WidgetAcceptMatcher` still has no formal vocabulary shape in the spec itself. (see `packages/starlayer/docs/shacl/shacl12-gap-matrix.md`)
- SHACL Compact syntax support, plus an ontology/shape over *that* syntax (mirroring the Manchester/SPARQL AST-as-RDF pattern) to drive validation and an editor. (see `packages/starlayer/docs/shacl/shacl12-gap-matrix.md`)

## Other

- VERSION-directive conformance warnings.
- SKOS: an OWL/RDFS ontology based on the W3C SKOS Reference's formal axioms.
- SHACL shape validation of SKOS graphs.
- A registry of the supported ontology and SHACL-shapes files: `manchester_owl` / `manchester_shacl`, `skos_owl` / `skos_shacl`, `sparql_owl` / `sparql_shacl`, `srl_owl` / `srl_shacl`, `shacl_meta`.
