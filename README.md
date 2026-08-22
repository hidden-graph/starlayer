# StarLayer

StarLayer is a Python RDF 1.2 wrapper built on rdflib and pyshacl. Starlayer can be used in two modes:

1. full: graph, SPARQL and SHACL
2. graph and SPARQL, without SHACL

Note: the RDF, SPARQL and SHACL 1.2 specifications are currently under development.  Starlayer will be periodically updated to reflect changes in the draft specifications as they evolve.  Eventually, rdflib and pyshacl will be updated to the final 1.2 specifications and starlayer will be retired.  This version is current as of 22 August 2026.


## Packages

| Package | Import | Description |
| --- | --- | --- |
| [packages/graph](packages/graph) | `starlayergraph` | RDF 1.2 graph and dataset support, including triple terms, reification, annotation folding, and multiple storage backends. |
| [packages/sparql](packages/sparql) | `starsparql` | Real grammar-based SPARQL 1.2 parsing and algebra support, with execution against in-memory `starlayergraph`. |
| [packages/shacl](packages/shacl) | `starshacl` | SHACL validation and rule execution with RDF 1.2 / triple-term support built on `pyshacl`. |

## Dependency model

```text
starlayergraph ───► starsparql
      ▲
      │
      └──────────────► starshacl
```

The graph and SPARQL layers are designed to work together. SHACL depends on the graph layer and uses the SPARQL layer for SHACL rule execution.

## Install

This repository is not currently published to PyPI. The current install path is from a GitHub checkout / local clone of this repo.

For the full Starlayer stack:

```bash
git clone https://github.com/hidden-graph/starlayer.git
cd starlayer
python3 -m venv .venv
source .venv/bin/activate

pip install -e packages/graph -e packages/sparql -e packages/shacl
```

For the core RDF + SPARQL layer only:

```bash
git clone https://github.com/hidden-graph/starlayer.git
cd starlayer
python3 -m venv .venv
source .venv/bin/activate

pip install -e packages/graph -e packages/sparql
```


## Example usage

```python
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

# Example RDF data
# Use your own graph and shape definitions here.

data = StarLayerGraph()
shapes = StarLayerGraph()

validator = StarShaclValidator()
result = validator.validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)
```

See the package READMEs for more complete examples and API details:

- [packages/graph/README.md](packages/graph/README.md)
- [packages/sparql/README.md](packages/sparql/README.md)
- [packages/shacl/README.md](packages/shacl/README.md)

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/graph -e packages/sparql -e packages/shacl
pip install pytest hypothesis

cd packages/graph && pytest tests/ -m "not integration" -v
cd ../sparql && pytest tests/ -q
cd ../shacl && pytest tests/ -q
```

The project uses continuous integration checks across a Python version matrix and smoke tests for the monorepo install flow. See the GitHub Actions workflow at https://github.com/hidden-graph/starlayer/blob/main/.github/workflows/test.yml for the current validation setup.

## Project status

This project is under active development. It is structured for research, semantic-web experimentation, and early production use, but it is not yet presented as a mature, broadly deployed public library.

## License

MIT
