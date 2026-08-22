# starlayergraph

*Last reviewed: 2026-08-22*

StarLayerGraph adds RDF 1.2 support to rdflib, including **triple terms** and **reification**. It lets you work with RDF-star-style data in Python while keeping the familiar `rdflib.Graph` workflow.

**RDF 1.2** formalizes features that were previously in RDF-star, especially the ability to make statements about statements. In practice, this means a triple can itself appear as an object  value inside another triple. This is the core reification model for RDF 1.2.

`rdflib` currently targets RDF 1.1 and does not support these features natively. StarLayerGraph fills that gap by translating RDF 1.2 data and queries into a form that rdflib can process internally, while preserving the RDF 1.2 surface syntax and semantics needed by applications.

It can run fully in memory or use the backend storage options provided by rdflib, including SQL, Apache Fuseki, and Oxigraph. When a backend supports RDF 1.2 natively, StarLayerGraph passes those operations through directly, relying on the native RDF 1.2 storage and query capabiliteis of the backend.

> **Scope note:** this package focuses on reification and base-direction literals — the two main RDF 1.2 data-model additions. Base-direction support for language-tagged literals (`"text"@en--ltr`, `rdf:dirLangString`) is available via `DirLangString`; see [starlayergraph.md](docs/starlayergraph.md) for details.

## Install

This package is not yet published to PyPI. Install it from the repository checkout at https://github.com/hidden-graph/starlayer or use the instructions in the main project README.

```bash
# from the repository root
pip install -e packages/graph
```

If you already have a local clone, you can also install directly from that checkout:

```bash
pip install -e /path/to/starlayer/packages/graph
```

## Key features

- **Drop-in replacement for rdflib.Graph** — `StarLayerGraph` subclasses `rdflib.Graph`; existing rdflib code works unchanged
- **Full RDF 1.2 data model** — triple terms are first-class Python objects (`TripleTerm`), not encoded strings
- **All annotation forms** — parses and serializes `{| |}`, `~ :r`, `<<( )>>`, and `<< >>` syntax
- **SPARQL 1.2** — queries with triple term patterns are rewritten to SPARQL 1.1 for compatibility
- **8 serialization formats** — Turtle, N-Triples, N-Quads, TriG, JSON-LD, TriX, RDF/XML, longturtle (JSON-LD and TriX are starlayergraph-defined conventions, not W3C RDF 1.2 formats — see the note in [starlayergraph_vs_rdflib.md](docs/starlayergraph_vs_rdflib.md#serialization--parsing))
- **W3C conformance** — passes the full W3C RDF 1.2 Turtle syntax and eval test suite (103 tests: 29 `TestTurtleEval`, 41 `TestTurtlePositiveSyntax`, 33 `TestTurtleNegativeSyntax`; see [tests/w3c_turtle12/README.md](tests/w3c_turtle12/README.md) for scope and licensing)
- **Multiple backends** — in-memory, SQL (via rdflib-sqlalchemy), Apache Fuseki, Oxigraph

## Requirements

- Python 3.10+
- rdflib >= 7.0

## Quick start

Use `StarLayerGraph` in place of `rdflib.Graph`. Everything else stays the same — parse, query, and serialize just as you would with rdflib.

Given an input file `example.ttl`:

```turtle
@prefix : <http://example.org/> .

:bob :knows :carol {| :since "2020" ; :source :Wikipedia |} .
:alice :says <<( :bob :knows :carol )>> .
:alice :believes <<( :bob :knows :mike )>> .
```

The last triple uses an **unasserted triple term** — `:bob :knows :mike` is referenced as a value without being a standalone fact in the graph.

```python
from starlayergraph.graph.starlayer_graph import StarLayerGraph

g = StarLayerGraph()
g.parse('example.ttl', format='turtle12')

# Query using SPARQL 1.2 triple-term patterns
results = g.query("""
    PREFIX : <http://example.org/>
    SELECT ?source WHERE {
      ?stmt rdf:reifies <<( :bob :knows :carol )>> .
      ?stmt :source ?source .
    }
""")
for row in results:
    print(row.source)
```

```
http://example.org/Wikipedia
```

Serialize the graph back to Turtle 1.2 — annotations are folded into compact `{| |}` syntax automatically:

```python
print(g.serialize(format='turtle12'))
```

```turtle
@version "1.2" .
@prefix : <http://example.org/> .

:alice :believes <<( :bob :knows :mike )>> ;
    :says <<( :bob :knows :carol )>> .

:bob :knows :carol {| :since "2020" ; :source :Wikipedia |} .
```

## Backends

```python
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

# In-memory (default) — fastest, no setup required
g = StarLayerGraph()

# Persistent SQL store via rdflib-sqlalchemy
g = StarLayerGraph(store='SQLAlchemy')
g.open('sqlite:///graph.db', create=True)

# Apache Fuseki — SPARQL endpoint with RDF 1.1 encoding
store = SPARQLUpdateStore(query_endpoint='http://localhost:3030/ds/sparql',
                          update_endpoint='http://localhost:3030/ds/update')
g = StarLayerGraph(store=store, backend='rdf-1.1')

# Apache Fuseki 5.5+ — speaks the final RDF 1.2 <<( s p o )>> syntax natively
store = SPARQLUpdateStore(query_endpoint='http://localhost:3030/ds/sparql',
                          update_endpoint='http://localhost:3030/ds/update')
g = StarLayerGraph(store=store, backend='rdf-1.2')

# Oxigraph — native RDF 1.2 store
store = SPARQLUpdateStore(query_endpoint='http://localhost:7878/query',
                          update_endpoint='http://localhost:7878/update')
g = StarLayerGraph(store=store, backend='rdf-1.2')
```

`StarLayerDataset` (multi-graph, every named graph a `StarLayerGraph`) takes the same `store=`/`backend=` arguments and supports rdflib's own `default_union` flag (default `False`, matching rdflib's `Dataset`): `StarLayerDataset(default_union=True)` makes the default graph the union of every named graph for `.triples()`/`.query()`/`.update()`'s GRAPH-less patterns, same as plain `rdflib.Dataset`.

## Examples

- [`examples/ttl12_roundtrip_demo.py`](examples/ttl12_roundtrip_demo.py) — parses Turtle 1.2, then prints three views of the same graph side by side: the input, the internal RDF 1.1 encoding (normally hidden), and the Turtle 1.2 output.
- [`examples/sqlalchemy_store_demo.py`](examples/sqlalchemy_store_demo.py) — writes to a SQLite-backed `StarLayerGraph`, reloads it in a fresh process, and runs a SPARQL 1.2 query against the reloaded data. Requires the `sqlalchemy` extra: `pip install -e ".[sqlalchemy]"`.

## Testing

```bash
pytest tests/ -m "not integration" -v   # unit + W3C conformance — no server needed
pytest tests/ -m "integration" -v       # + real backends (Fuseki/Oxigraph/SQLite)
```

See [docs/testing-strategy.md](docs/testing-strategy.md) for the full tier breakdown (including cross-backend parity and performance benchmarks) and what each one is actually checking.

## License

MIT
