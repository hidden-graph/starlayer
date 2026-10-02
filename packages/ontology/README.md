# ontology

The raw ontology / SHACL-shapes `.ttl` files shared across the StarLayer stack, in one place.

## Import

```python
import starontology
```

## What's here

Two files per vocabulary - an OWL/RDFS ontology and a SHACL shapes graph - for four vocabularies:

| Vocabulary | Ontology | Shapes | Consumed by |
| --- | --- | --- | --- |
| `manch:` (Manchester Syntax's own AST as RDF) | `manchester-ast-ontology.ttl` | `manchester_shapes.ttl` | `starlayer.graph` |
| `skos:` (the W3C SKOS Reference's own formal axioms) | `skos-ontology.ttl` | `skos_shapes.ttl` | `starlayer.graph` |
| `salg:` (a SPARQL 1.2 query's own algebra as RDF) | `salg-ontology.ttl` | `sparql_shapes.ttl` | `starlayer.sparql` |
| `srl:` (SRL/SPARQL-RL's own rule-set AST as RDF) | `srl-ontology.ttl` | `srl_shapes.ttl` | `starlayer.sparql` |

This package is pure data plus a small registry: `get_ontology_list()` (every entry's `name`/`description`/`type`), `get_ontology_graph(name)` (a fresh `StarLayerGraph`), `get_ontology_turtle12(name)` (the same, as Turtle 1.2 text). No `pyshacl`, no dependency on `starlayer.sparql`/`starlayer.shacl` - but it does depend on `starlayer.graph` (every loader returns a `StarLayerGraph`, not a plain `rdflib.Graph` - see `starontology/__init__.py`'s own "Dependency note" for why that was accepted). Actually *validating* against these shapes (with the right reasoning settings per vocabulary) is each consuming package's own job - see `starlayer.ontology.manchester_shapes`/`starlayer.ontology.skos_shapes`/`starlayer.sparql.sparql_shapes`/`starlayer.sparql.srl_shapes`, or the unified catalog at `starlayer.ontology.list_ontologies()`/`get_ontology()`.

The SHACL 1.2 meta-shapes themselves (`starlayer.shacl`'s shapes-about-shapes) are not here - they're generated Python, not a static file, and stay inside `starlayer.shacl`.

Part of the [StarLayer](https://github.com/hidden-graph/starlayer) stack - see the [root README](../../README.md) for the full picture.

## License

MIT
