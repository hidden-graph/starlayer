# StarLayer

An RDF 1.2 stack for Python, built on [rdflib](https://github.com/RDFLib/rdflib): a graph engine, a SPARQL 1.2 engine, and a SHACL 1.2 validator, each usable on its own or together.

This repo is a monorepo of three independently-installable packages:

| Package | Import as | What it does |
|---|---|---|
| [`packages/graph`](packages/graph) | `starlayergraph` | `StarLayerGraph`/`StarLayerDataset` — triple terms, reification, annotation folding, 8 serialization formats, multiple backends (in-memory, Fuseki, Oxigraph, SQLAlchemy). Usable standalone for CRUD/parse/serialize with no SPARQL engine installed. |
| [`packages/sparql`](packages/sparql) | `starsparql` | Real grammar-based SPARQL 1.2 parser and an RDF encoding of SPARQL algebra, plus the lowering that makes SPARQL 1.2 queries executable against `starlayergraph`. |
| [`packages/shacl`](packages/shacl) | `starshacl` | SHACL validation with RDF 1.2/triple-term support, built on `pyshacl`. |

## Dependency shape

```
starlayergraph  <──►  starsparql      (intentional two-way dependency — see
      ▲                                starsparql's own README/CLAUDE.md)
      │
      └──────────────  starshacl      (needs the graph, and transitively the
                                        SPARQL engine, for SHACL-AF constraints)
```

`starlayergraph` and `starsparql` depend on each other by design — `starsparql` is this stack's own SPARQL engine layer, not an independent generic library. `starshacl` depends on `starlayergraph` (and transitively `starsparql`) plus `pyshacl`.

## Install

Each package is independently installable from a local checkout:

```bash
pip install -e packages/graph
pip install -e packages/graph -e packages/sparql
pip install -e packages/graph -e packages/sparql -e packages/shacl
```

None of these are published to PyPI yet.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/graph -e packages/sparql -e packages/shacl
pip install pytest hypothesis

# run each package's own test suite from its own directory
cd packages/graph   && pytest tests/ -m "not integration" -v
cd packages/sparql  && pytest tests/ -q
cd packages/shacl   && pytest tests/ -q
```

See each package's own `README.md`/`CLAUDE.md` for details specific to it.

## History

This repo was created 2026-08 by merging three previously-separate repos (`rdflib-starlight`, `sparql1.2_to_rdf`, `starShacl`/`pyshacl-starlight`) into one, with fresh git history — the old repos' commit history was intentionally not carried over. Package/class names changed to a consistent `StarLayer`/`Star*` family (`StarlightGraph` → `StarLayerGraph`, `sparql1_2_to_rdf` → `starsparql`, `pyshacl_starlight` → `starshacl`); functionality is unchanged.

## License

MIT
