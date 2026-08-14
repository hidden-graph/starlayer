# starlayergraph

*Last reviewed: 2026-07-17*

RDF 1.2 wrapper for rdflib.

**RDF 1.2** was published as a W3C Candidate Recommendation on April 7, 2026. It represents the formal standardization of RDF-star, a community-driven extension to RDF that had been under development since 2019. The primary change RDF 1.2 introduces is **reification** — the ability to make statements *about* statements. RDF 1.2 makes reification a first-class feature of the data model through **triple terms** — triples that can themselves appear as the object of other triples.

**rdflib** (current version 7.6.0) is based on RDF 1.1 and does not support the reification features of RDF 1.2.

**starlayergraph** is a lightweight wrapper that extends rdflib to handle the reification features of RDF 1.2. It is intended to remain relevant until rdflib is updated to incorporate the final RDF 1.2 specification.

starlayergraph works by translating RDF 1.2 data and queries into RDF 1.1 format internally, so that rdflib can process them natively. It can operate fully in-memory, or use the backend storage options supported by rdflib — including Fuseki, SQL, and Oxigraph. When the backend natively supports RDF 1.2, starlayergraph delegates storage and querying to it directly.

> **Scope note:** starlayergraph focuses on reification and base-direction literals — the two RDF 1.2 data-model additions. Base-direction support for language-tagged literals (`"text"@en--ltr`, `rdf:dirLangString`) is available as `DirLangString`; see [starlayergraph.md](docs/starlayergraph.md) for details.

Not yet published to PyPI — install the checkout directly:

```
pip install -e /path/to/starlayergraph
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
