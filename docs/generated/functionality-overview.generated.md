# StarLayer Functionality Overview

What StarLayer does today, and what is planned.

## RDF graph

- Manage RDF 1.2 graphs, including triple terms and direction-tagged literals. ([rdf12-concepts](https://www.w3.org/TR/rdf12-concepts))
- In-memory graph management through rdflib using an RDF 1.1 transformation of RDF 1.2 graphs (the default backend).
- Parse and serialize various RDF formats including both 1.1 and 1.2 versions of Turtle, LongTurtle, N-Triples, N-Quads, TriG, RDF/XML, and TriX 1.2. Parse and serialize JSON-LD 1.1 (1.2 pending). ([rdf12-n-triples](https://www.w3.org/TR/rdf12-n-triples), [rdf12-turtle](https://www.w3.org/TR/rdf12-turtle), [rdf12-xml](https://www.w3.org/TR/rdf12-xml))
- Multi-graph datasets with named graphs. ([rdf12-concepts](https://www.w3.org/TR/rdf12-concepts))
- Storage backends: the default in-memory rdflib store; Oxigraph in memory, on disk or as a server; Fuseki as a server; and SQLAlchemy-backed storage through a store plugin. Oxigraph and Fuseki use their own RDF 1.2 support when available.
- RDF-1.2-aware graph isomorphism and comparison. ([rdf12-concepts](https://www.w3.org/TR/rdf12-concepts))
- RDFC-1.0 canonicalization and hashing of RDF 1.2 graphs. ([rdf-canon](https://www.w3.org/TR/rdf-canon))
- Resolve owl:imports using a loader you supply, so you decide how an imported document is fetched. There is no built-in fetching.
- Concise bounded descriptions of a resource, and lookup of the triple terms that have at least one reifier.
- Triple terms are stored using the vocabulary of the RDF 1.2 Interoperability specification (each one a node typed rdf:PropositionForm), found by that type, and converted to and from the standard's blank-node form when writing or reading plain RDF formats.

**Planned / deferred:**

- rdflib 8 compatibility (currently pinned to rdflib 7.x; revisit once a stable rdflib 8 ships).
- Built-in fetching of owl:imports, and one import mechanism shared by graphs, SHACL and SRL. ([details](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/docs/future_enhancements.md))

## SPARQL

- SPARQL 1.2 queries over StarLayer graphs. ([sparql12-query](https://www.w3.org/TR/sparql12-query))
- A StarLayer RDF vocabulary for representing SPARQL queries as graphs, for hand or UI editing (the sqe namespace). It covers SELECT, ASK and CONSTRUCT with every clause, aggregates, sub-selects, VALUES and the SPARQL 1.2 additions; DESCRIBE and Update are not covered.
- SHACL shapes for sqe graphs.
- Prepared queries: prepare a query once, with options such as entailment, and run it against any number of graphs.
- SPARQL 1.2 Update over StarLayer graphs and datasets: INSERT DATA, DELETE DATA and DELETE/INSERT WHERE, including triple terms. ([sparql12-update](https://www.w3.org/TR/sparql12-update))

## SRL (SPARQL Rules)

- A Datalog-style rules language from the W3C SPARQL 1.2 working draft (2026-10-14), general-purpose and independent of SHACL. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))
- Parse rule sets and represent them as RDF graphs that convert back to the same rule set (the srl namespace), with SHACL shapes that validate them. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))
- Rule sets are checked against those shapes as they are parsed, so a malformed rule set is rejected up front.
- Rule bodies and heads can use RDF 1.2 triple terms, reified triples and annotations; bodies can use the / and ^ property paths. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))
- IMPORTS of other rule sets, resolved through a loader you supply. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))
- Stratified evaluation: infer new triples, query the result, and show the order in which rules run. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))
- Optional entailment and SHACL validation of the result.
- Verified against the specification's own worked example. ([sparql12-rl](https://www.w3.org/TR/sparql12-rl))

**Planned / deferred:**

- Aggregation, and converting a rule set to SPARQL - waiting on the specification. ([details](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/docs/future_enhancements.md))

## Manchester Syntax

- Manchester OWL syntax support for parse and serialize. ([owl2-manchester-syntax](https://www.w3.org/TR/owl2-manchester-syntax))
- A StarLayer RDF vocabulary for representing a Manchester document (the manch namespace).
- SHACL shapes for manch graphs.

## Reasoning

- Support for reasoning and inference using various entailment regimes: RDF, RDFS, OWL-RL, and OWL-DL. ([sparql12-entailment](https://www.w3.org/TR/sparql12-entailment))
- OWL-DL support via two engines: HermiT (through owlready2, which needs Java) or a Rust engine.
- Support for both graph reasoning and query-time reasoning. ([sparql12-entailment](https://www.w3.org/TR/sparql12-entailment))

## SHACL

- Support for SHACL 1.2 over RDF 1.2 graphs. ([shacl12-core](https://www.w3.org/TR/shacl12-core))
- Support for additional SHACL 1.2 specifications: SPARQL Extensions, Node Expressions, Rules, User Interfaces, Profiling. ([shacl12-inference-rules](https://www.w3.org/TR/shacl12-inference-rules), [shacl12-node-expr](https://www.w3.org/TR/shacl12-node-expr), [shacl12-profiling](https://www.w3.org/TR/shacl12-profiling), [shacl12-sparql](https://www.w3.org/TR/shacl12-sparql), [shacl12-ui](https://www.w3.org/TR/shacl12-ui))
- SHACL 1.2 meta-shapes for checking shapes graphs. ([shacl12-core](https://www.w3.org/TR/shacl12-core))
- SHACL-driven subgraph extraction.
- Derive a SHACL shape from a graph's own data.
- SHACL 1.2 User Interfaces widget selection: choose a widget for each property of a shape using the specification's scoring and matcher rules. ([shacl12-ui](https://www.w3.org/TR/shacl12-ui))
- Validation reports record the data and shapes graphs used and derive sh:conformsTo, and dcterms:conformsTo when given a profiles graph. ([shacl12-profiling](https://www.w3.org/TR/shacl12-profiling))
- Named shapes graph modules: validate against one module, extract one, and resolve owl:imports using a loader you supply.
- Entailment during validation: a shapes graph's sh:entailment declarations, or an inference option, run the same entailment regimes as graph reasoning.

**Planned / deferred:**

- SHACL 1.2 User Interfaces: property roles (shui:propertyRole) are accepted but not interpreted, and no default widget scoring catalog ships (the specification publishes none). ([details](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/docs/shacl/shacl12-gap-matrix.md))
- SHACL Compact syntax support, plus an ontology and shapes over that syntax (mirroring the Manchester and SPARQL syntax-as-RDF pattern) to drive validation and an editor. ([details](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/docs/shacl/shacl12-gap-matrix.md))
- SHACL UI shapes for the SHACL validation shapes, so a form can edit a shapes graph, starting from the archived presentation shapes. ([details](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/docs/future_enhancements.md))

## Other

- VERSION-directive conformance warnings.
- SKOS: the W3C's own SKOS vocabulary as an OWL/RDFS ontology (skos.rdf from the SKOS Reference, converted to Turtle with no change to its content). ([skos-reference](https://www.w3.org/TR/skos-reference))
- SHACL shapes for SKOS: the Reference's numbered conditions as validation shapes, some non-normative recommendations, and form shapes with datatype-based UI widgets. ([skos-reference](https://www.w3.org/TR/skos-reference))
- A registry of the bundled ontologies and SHACL shapes (Manchester Syntax, SKOS, SPARQL algebra, SQE, SPARQL expressions, SRL), the SHACL 1.2 meta-shapes, and the profiles document, each available by name and as a file on GitHub.
- StarLayer declares its conformance in one profiles document: StarLayer profiles for SKOS, Manchester Syntax, SPARQL 1.2 Query, SRL and SHACL 1.2, each a profile of the public specification, plus the declared conformance of the graph, SPARQL and SHACL packages. Data validated against a shapes graph is reported as conforming to the matching profile and, through it, to the specification. ([dx-prof](https://www.w3.org/TR/dx-prof))
