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
| `manch:` (Manchester Syntax's own AST as RDF) | `manchester-ast-ontology.ttl` | `manchester_shapes.ttl` | `starontology.manchester` (lives right here - see below) |
| `skos:` (the W3C SKOS Reference's own formal axioms) | `skos-ontology.ttl` | `skos_shapes.ttl` | `starontology.skos` (lives right here - see below) |
| `salg:` (a SPARQL 1.2 query's own algebra as RDF) | `salg-ontology.ttl` | `sparql_shapes.ttl` | `starlayer.sparql` |
| `srl:` (SRL/SPARQL-RL's own rule-set AST as RDF) | `srl-ontology.ttl` | `srl_shapes.ttl` | `starlayer.sparql.srl` |

This top-level module (`starontology/__init__.py`) is pure data plus a small registry: `get_ontology_list()` (every entry's `name`/`description`/`type`), `get_ontology_graph(name)` (a fresh `StarLayerGraph` - call `.serialize(format='turtle12')` on it for Turtle text; a dedicated `get_ontology_turtle12()` wrapper existed briefly but was removed 2026-10-03 for being nothing more than that one-line composition). No `pyshacl` here - but it does depend on `starlayer.graph` (every loader returns a `StarLayerGraph`, not a plain `rdflib.Graph` - see `starontology/__init__.py`'s own "Dependency note" for why that was accepted). Actually *validating* against the `salg:`/`srl:` shapes (with the right reasoning settings per vocabulary) is still each consuming package's own job - see `starlayer.sparql.sparql_shapes`/`starlayer.sparql.srl`, or the unified catalog at `starlayer.registry.list_ontologies()`/`get_ontology()`.

**`manch:`/`skos:` are the exceptions** (2026-10-03): `starontology.manchester`/`starontology.skos`, submodules right here, hold real validate (and, for `manch:`, parse/serialize too) logic for their vocabularies, not just a loader - see each submodule's own docstring for why a vocabulary that needs more than "load this `.ttl` file" gets a real logic home in this package instead of staying data-only like `salg:`/`srl:` still are.

The SHACL 1.2 meta-shapes themselves (`starlayer.shacl`'s shapes-about-shapes) are not here - they're generated Python, not a static file, and stay inside `starlayer.shacl`.

Part of the [StarLayer](https://github.com/hidden-graph/starlayer) stack - see the [root README](../../README.md) for the full picture.

## License

MIT
