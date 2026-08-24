# StarLayer

StarLayer is a Python RDF 1.2 wrapper built on rdflib and pyshacl. 


Note: the RDF, SPARQL and SHACL 1.2 specifications are currently under development.  Starlayer will be periodically updated to reflect changes in the draft specifications as they evolve.  Eventually, rdflib and pyshacl will be updated to the final 1.2 specifications and starlayer will be retired.  This version is current as of 22 August 2026.



## Install

Install Starlayer directly from GitHub:

```bash
pip install "git+https://github.com/hidden-graph/starlayer.git"
```

This is the supported public install path for the StarLayer stack. It brings in the graph, SPARQL, and SHACL layers together.

For the canonical walkthrough with example code, see the [user guide](docs/user-guide-v1.md).
Guide version metadata is tracked in [docs/user-guide-version.json](docs/user-guide-version.json).

If you are working from a local checkout for development, you can install the same package in editable mode from the repo:


## Packages

| Package | Import | Description |
| --- | --- | --- |
| [packages/graph](packages/graph) | `starlayergraph` | RDF 1.2 graph and dataset support, including triple terms, reification, annotation folding, and multiple storage backends. |
| [packages/sparql](packages/sparql) | `starsparql` | Real grammar-based SPARQL 1.2 parsing and algebra support, with execution against in-memory `starlayergraph`. |
| [packages/shacl](packages/shacl) | `starshacl` | SHACL validation and rule execution with RDF 1.2 / triple-term support built on `pyshacl`. |


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

See the package folders in this repository for the implementation details and examples behind the full-stack install:

- [packages/graph](packages/graph)
- [packages/sparql](packages/sparql)
- [packages/shacl](packages/shacl)

## Development

Use the package for local development, then run the package test suites from the repo root:

```bash
git clone https://github.com/hidden-graph/starlayer.git
cd starlayer
python3 -m venv .venv
source .venv/bin/activate

pip install -e .
pip install pytest hypothesis
```

```bash
cd packages/graph && pytest tests/ -m "not integration" -v
cd ../sparql && pytest tests/ -q
cd ../shacl && pytest tests/ -q
```

The monorepo is organized into implementation packages for `graph`, `sparql`, and `shacl`, while the public-facing install remains the single `starlayer` package. The project also uses CI checks across a Python version matrix; see the GitHub Actions workflow at https://github.com/hidden-graph/starlayer/blob/main/.github/workflows/test.yml for the current validation setup.

## Project status

This project is under active development. It is structured for research, semantic-web experimentation, and early production use, but it is not yet presented as a mature, broadly deployed public library.

## License

MIT
