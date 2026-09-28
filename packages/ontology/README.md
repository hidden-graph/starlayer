# ontology

The raw ontology / SHACL-shapes `.ttl` files shared across the StarLayer stack, in one place.

## Import

```python
import starontology
```

## What's here

Two files per vocabulary - an OWL/RDFS ontology and a SHACL shapes graph - for three vocabularies:

| Vocabulary | Ontology | Shapes | Consumed by |
| --- | --- | --- | --- |
| `manch:` (Manchester Syntax's own AST as RDF) | `manchester-ast-ontology.ttl` | `manchester_shapes.ttl` | `starlayergraph` |
| `skos:` (the W3C SKOS Reference's own formal axioms) | `skos-ontology.ttl` | `skos_shapes.ttl` | `starlayergraph` |
| `salg:` (a SPARQL 1.2 query's own algebra as RDF) | `salg-ontology.ttl` | `sparql_shapes.ttl` | `starsparql` |

This package is pure data plus thin loader functions (`manchester_ontology_graph()`, `manchester_shapes_graph()`, `skos_ontology_graph()`, `skos_shapes_graph()`, `sparql_ontology_graph()`, `sparql_shapes_graph()`) - no `pyshacl`, no dependency on any other package in this stack. Actually *validating* against these shapes (with the right reasoning settings per vocabulary) is each consuming package's own job - see `starlayergraph.ontology.manchester_shapes`/`starlayergraph.ontology.skos_shapes`/`starsparql.ontology.sparql_shapes`, or the unified catalog at `starlayergraph.ontology.list_ontologies()`/`get_ontology()`.

The SHACL 1.2 meta-shapes themselves (`starshacl`'s shapes-about-shapes) are not here - they're generated Python, not a static file, and stay inside `starshacl`.

Part of the [StarLayer](https://github.com/hidden-graph/starlayer) stack - see the [root README](../../README.md) for the full picture.

## License

MIT
