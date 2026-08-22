# starsparql

`starsparql` adds structured SPARQL 1.2 support to the StarLayer stack.

It translates SPARQL 1.2 queries into an RDF data model so they can be stored, versioned, inspected, and validated in the same way as other graph content. This is useful for query analysis, query generation, validation, and execution against RDF 1.2 graphs that support triple terms and reification.

`starsparql` depends on [`starlayergraph`](../graph) for RDF 1.2 execution and is part of the larger StarLayer stack. See the root [README](../../README.md#dependency-shape) for the package layout and dependency model.

## Install

This package is installed as part of the StarLayer monorepo. For local development, use the repo-root installation flow from the main project README, which installs the graph and SPARQL packages together:

```bash
pip install -e packages/graph -e packages/sparql
```

## What it does

- **Query round-tripping** — parses SPARQL queries and converts them into a structured RDF representation of their algebra, then reconstructs working query objects.
- **RDF-native query structure** — makes it possible to inspect, serialize, and reason about query structure as graph data.
- **RDF 1.2 support** — works with triple-term patterns and reification-aware graph data.
- **Execution against StarLayerGraph** — evaluates queries against RDF graphs using the graph and SPARQL layers together.
- **Validation and conformance checks** — includes a SPARQL 1.2 conformance validation for the RDF query vocabulary using a SHACL shape that defines the schema of the SPARQL RDF data model.

## SPARQL as RDF

`starsparql` represents SPARQL queries as RDF rather than keeping them only as text strings. This allows a query to be stored, versioned, validated, and reasoned about like any other graph resource.

The core vocabulary for that RDF representation lives in [starsparql/ontology/salg-ontology.ttl](starsparql/ontology/salg-ontology.ttl). This file defines the ontology for the query-algebra RDF model used by the package.

The SHACL validation layer is defined in the canonical RDF document:

- [starsparql/ontology/sparql_shapes.ttl](starsparql/ontology/sparql_shapes.ttl) — RDF/SHACL document that defines the shape model used to validate SPARQL algebra graphs



## More detail

The technical details for maintainers and advanced contributors live in [docs/implementation-notes.md](docs/implementation-notes.md).

That document covers the internal algebra-to-RDF mapping, execution model, validation approach, and the implementation details that matter when working on the package itself.

