# StarLayer Code Knowledge Graph (Experimental v1)

This folder contains a code-structure knowledge graph for the monorepo plus a companion ontology.

## What this gives you

- A queryable RDF graph of packages, modules, classes, functions, methods, parameters, imports, and package dependencies.
- Docstrings and source comments captured as literals for LLM memory and semantic grounding.
- A hybrid ontology:
  - Reuses existing vocab where useful (`prov:Entity`, `schema:SoftwareSourceCode`, `dcterms:*`).
  - Adds StarLayer-specific classes/properties for symbol-level structure.

## Files

- `ontology.ttl`: Ontology for the code KG.
- `codebase.ttl`: Generated codebase graph.
- `codebase-summary.json`: Counts and package dependency summary.
- `dependencies.mmd`: Mermaid dependency view.

## Build / refresh

From repo root:

```bash
python scripts/build_code_kg.py
```

This is intentionally manual-run in v1.

## Load and query with StarLayer

```python
from starlayergraph import StarLayerGraph

kg = StarLayerGraph()
kg.parse("docs/kg/ontology.ttl", format="turtle")
kg.parse("docs/kg/codebase.ttl", format="turtle")

rows = kg.query("""
PREFIX slkg: <https://github.com/hidden-graph/starlayer/kg/ontology#>
SELECT ?module ?class WHERE {
  ?module a slkg:Module ;
          slkg:defines ?class .
  ?class a slkg:Class .
}
LIMIT 25
""")

for r in rows:
    print(r.module, r.class)
```

## Suggested SPARQL snippets

### 1) Most-connected modules by import count

```sparql
PREFIX slkg: <https://github.com/hidden-graph/starlayer/kg/ontology#>
SELECT ?module (COUNT(?dep) AS ?imports)
WHERE {
  ?module a slkg:Module ; slkg:importsModule ?dep .
}
GROUP BY ?module
ORDER BY DESC(?imports)
LIMIT 20
```

### 2) Methods with docstrings mentioning "rule"

```sparql
PREFIX slkg: <https://github.com/hidden-graph/starlayer/kg/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?method ?doc
WHERE {
  ?method a slkg:Method ; rdfs:comment ?doc .
  FILTER(CONTAINS(LCASE(STR(?doc)), "rule"))
}
LIMIT 25
```

### 3) Cross-package dependency edges

```sparql
PREFIX slkg: <https://github.com/hidden-graph/starlayer/kg/ontology#>
SELECT ?src ?dst
WHERE {
  ?src a slkg:Package ; slkg:dependsOnPackage ?dst .
}
ORDER BY ?src ?dst
```

## Notes on standards / best practice alignment

This v1 model is informed by:

- PROV-O for general entity modeling.
- schema.org / CodeMeta software metadata patterns (`SoftwareSourceCode`, `codeRepository`).

The model intentionally keeps symbol-level terms in the `slkg:` namespace so it is practical for code navigation and LLM memory workflows.
