# StarLayer

StarLayer is a Python layer over rdflib and pySHACL that adds RDF 1.2, SPARQL 1.2 and SHACL 1.2: triple terms, reifiers and annotations, direction-tagged literals, SPARQL 1.2 queries over them, and SHACL validation, rules and UI widget selection that understand them.

The RDF, SPARQL and SHACL 1.2 specifications are still drafts. StarLayer follows them as they change, and tracks how closely it matches each one (see [docs/README.md](docs/README.md)). When rdflib and pySHACL support the final 1.2 specifications, StarLayer will be retired.

## What is in it

| Import | What it does |
| --- | --- |
| `starlayer.graph` | `StarLayerGraph` and `StarLayerDataset`: RDF 1.2 graphs with triple terms, reifiers, annotations and direction-tagged literals. Parses and serializes Turtle, TriG, N-Triples, N-Quads, RDF/XML and TriX (1.1 and 1.2), Manchester Syntax and JSON-LD 1.1. Stores in memory, Oxigraph, Fuseki or SQLAlchemy. Inference with RDF, RDFS, OWL-RL and OWL-DL. Canonical hashing and graph comparison. |
| `starlayer.sparql` | SPARQL 1.2 queries and updates (`StarQuery`), queries as RDF (`sqe:`), and SRL (SPARQL Rules) rule sets. |
| `starlayer.shacl` | SHACL 1.2 validation (`StarShaclSchema`), rules, node expressions, subgraph extraction, UI widget selection and profiling. |
| `starlayer.starontology` | The ontologies and SHACL shapes the library ships, loaded by name. |

## Install

```bash
pip install "git+https://github.com/hidden-graph/starlayer.git"
```

Python 3.10 or later. Optional extras, added like `"starlayer[oxigraph] @ git+https://github.com/hidden-graph/starlayer.git"`: `oxigraph` (in-process Oxigraph store), `sqlalchemy`, `reasoning` (OWL-RL), `hermit` and `rustdl` (the two OWL-DL engines).

## A short example

```python
from starlayer import StarLayerGraph, StarShaclSchema

data = StarLayerGraph()
data.parse(data="""
PREFIX ex: <http://example.org/>
ex:alice ex:knows ex:bob .
<< ex:alice ex:knows ex:bob >> ex:certainty 0.9 .   # a reified triple with an annotation
ex:alice ex:age "thirty" .
""", format="turtle12")

# Ask about the triple term itself
for who, certainty in data.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?who ?certainty WHERE {
      ?r rdf:reifies <<( ?who ex:knows ex:bob )>> ; ex:certainty ?certainty .
    }"""):
    print(who, certainty)          # http://example.org/alice 0.9

# Validate with SHACL
shapes = StarLayerGraph()
shapes.parse(data="""
PREFIX ex: <http://example.org/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
ex:PersonShape a sh:NodeShape ;
  sh:targetSubjectsOf ex:knows ;
  sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] .
""", format="turtle12")

result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data)
print(result.conforms)             # False: "thirty" is not an integer
```

## Where to go next

- [User guides](docs/guides/README.md): notebooks from getting started through graphs, SPARQL, SHACL, ontologies and storage.
- [docs/README.md](docs/README.md): the map of every document (guides, generated reference, design notes, gap analyses, known upstream bugs).
- [Generated API reference](docs/generated/api-overview.generated.md) and [functionality overview](docs/generated/functionality-overview.generated.md).
- [Contributing](CONTRIBUTING.md). Working with an AI agent? Start from [AGENTS.md](AGENTS.md).

## Development

```bash
git clone https://github.com/hidden-graph/starlayer.git
cd starlayer
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
cd packages/starlayer && pytest tests -m "not integration"
```

Details, the test tiers and the generated-file rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Project status

Under active development. It is suitable for research, semantic-web experimentation and early production use, and is not yet presented as a mature, broadly deployed library.

## License

MIT
