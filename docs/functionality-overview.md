# StarLayer Functionality Overview

A concise, bullet-point inventory of what the `starlayer` stack (`starlayergraph` +
`starsparql` + `starshacl`) currently does, and what's planned but not built.
For narrative walkthroughs with code, see the [guides index](README.md); for
full detail behind any bullet, see the linked per-package doc.

*Last reviewed: 2026-09-27*

---

## Currently covered

### RDF graph (`starlayergraph`)
1. (*) Manage any RDF 1.2 compliant graph, including triple terms and direction-tagged literals. 
2. Parse and serialize various RDF foramats including both 1.1 and 1.2 versionf of Turtle, LongTurtle,N-Triples, N-Quads, TriG, RDF/XML, and TriX 1.2.
3. Parse and serialize JSON 1.1 and 1.2 (1.2 pending).
4. Multi-graph support via `StarLayerDataset`.
5. In-memory graph management through rdflib using an RDF 1.1 transformation of RDF 1.2 graphs.
6. Backends graph database support through `store` (e.g. SQLAlchemy) and `httpp` (e.g Fuseki and Oxigraph.)   

### SPARQL (`starsparql`)

- SPARQL 1.2 query of starlayergraph.  
- Starlayer specific RDF ontology for representing SPARQL queries. (`salg:` namespace) 
- SHACL shape validation of SHACL queries using `salg:` including ui components.


### Reasoning

- Support for reasoning/inference using various entqailemnt regimets: RDF, RDFS, OWL-RL, and OWL-DL.
- OWL-DL support using  `owlready2` \ `"hermit"` (java) and `rustdl"`, (Rust SROIQ engine - a real,
  documented completeness/no-JVM tradeoff, not a strictly-better option),
  both at `infer()` and query time (`entailment=`).
- RDFC-1.0 canonicalization/hashing and RDF-1.2-aware graph
  isomorphism/comparison (`compare.py`).
- SHACL-driven subgraph extraction + hash-commitment pattern
  (`extract_subgraph()`/`close_shape()`).
- VERSION-directive conformance warnings (`RDF12ConformanceWarning`/
  `SPARQL12ConformanceWarning`) when a document/query's declared version
  doesn't match what it actually uses.
- Manchester OWL Syntax: native parse + serialize (OWL 2 RDF Mapping, no
  Java/OWL API dependency), **plus** its own AST as RDF (`manch:` ontology +
  SHACL shapes, encode/edit-via-graph-surgery/decode/re-serialize) - see
  `packages/graph/docs/manchester_syntax_gap_analysis.md`.
- SKOS: an OWL/RDFS ontology restating the W3C SKOS Reference's own formal
  axioms, plus SHACL shapes checking that document's numbered integrity
  conditions (class disjointness, lexical-label constraints, semantic-relation
  domain/range, property disjointness).
- `g.derive()` - infer a SHACL shape from a graph's own data, one
  `sh:NodeShape` per class found, closed, RDF-1.2-aware (recognizes
  triple-term-valued properties via `sh:nodeKind sh:TripleTerm`); with an
  existing template shape, reconciles it against real data - relaxing
  constraints with a principled data-driven fix, dropping ones that no
  longer hold and have none, extending new properties/classes - always
  through `starshacl`, never bare `pyshacl`.



### SHACL / SHACL 1.2 (`starshacl`)

- SHACL Core + SHACL-AF (built on `pyshacl`), with native RDF 1.2
  triple-term support throughout - one validation/rules path for RDF 1.1
  and 1.2 data, no separate modes.
- Full SHACL 1.2 Core coverage; the other five SHACL 1.2 Working Draft
  documents (SPARQL Extensions, Node Expressions, Rules, User Interfaces,
  Profiling) covered to the depth in `packages/shacl/docs/compatibility.md`.
- SHACL 1.2 meta-shapes shipped as reusable standalone assets (validation,
  presentation/UI-hint metadata, conformance-profile self-declaration).
- A W3C SHACL 1.2 test-suite harness (3 phases integrated) - nearly every
  finding fixed; the couple of remaining xfails are confirmed, documented
  fixture/spec quirks, not open bugs.

---

## Planned / deferred

Pulled from each package's own tracking doc - see those for full reasoning,
not repeated here.

**Cross-cutting (`packages/graph/docs/future_enhancements.md`)**
- A "list/return a specific SHACL library" registry API spanning every
  vocabulary this stack ships (SPARQL AST, SKOS, Manchester AST, SHACL,
  generic RDF, OWL RDF) - both the OWL ontology and the SHACL file per entry.
- A generic RDF SHACL shape to drive a generic RDF editor (not tied to one
  vocabulary).
- Wiring `g.derive()` (see "Currently covered" above) into an actual
  generic-RDF-editor UI.
- SHACL Compact syntax support, plus an ontology/shape over *that* syntax
  (mirroring the Manchester/SPARQL AST-as-RDF pattern) to drive an editor.
- rdflib 8 compatibility (currently pinned to rdflib 7.x; revisit once a
  stable rdflib 8 ships).
- The RDF 1.2 Interoperability spec's `rdf:PropositionForm` vocabulary
  retrofit onto internal triple-term storage - fully designed, explicitly
  paused (worse performance and complexity, standards-alignment optics only,
  no confirmed adopters of the vocabulary yet).
- A RustDL hang-avoidance safety net (pre-flight unsupported-axiom detection
  + cross-engine timeout) for the OWL-DL reasoning engine - designed,
  explicitly paused for the same cost/benefit reason.
- SKOS: `skos:memberList`/`skos:member` list-consistency (S32-S35) and
  vocabulary-specific best-practice shapes (e.g. "a Concept should have a
  `prefLabel`") - deliberately out of scope for the shipped shapes, which
  cover only the spec's own numbered integrity conditions.

**`starsparql` (known gaps, not oversights - see `CLAUDE.md`)**
- Cross-referential semantic checks SHACL's per-node shapes structurally
  can't see (e.g. a query projecting an unbound variable).
- A `<<...>>` reifier-shorthand term's own subject/object can't yet be
  another reifier term or nested ground triple term.
- Whether `TripleTermNode` fully aligns with SPARQL 1.2's formal algebra, or
  only with rdflib's pragmatic representation, is still an open question.
- Actual LLM integration/prompting is out of scope for this project - a
  separate downstream effort once the IR + validator + translator exist.

**`starshacl` (see `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred")**
- SHACL 1.2 UI's `shui:WidgetScore`/`shui:WidgetAcceptMatcher`
  widget-selection algorithm - blocked on upstream: `WidgetAcceptMatcher`
  still has no formal vocabulary shape in the spec itself.
- `sh:PropertyRule`/`sh:values` as a `sh:rule` shorthand.
- SRL/SPARQL-RL's own rule text syntax - deferred alongside the rest of the
  Rules family (rule-set *selection*, `sh:RuleSet`/`sh:hasRule`, already
  shipped, was promoted out of this bucket on request).
