# Oxigraph upstream issues (drafts)

Drafts only: nothing here is filed externally. One section per issue.

## 1. A zero-length property path to a constant that is not a node of the graph matches nothing

### Minimal reproduction

```python
import pyoxigraph as ox

store = ox.Store()
store.add(ox.Quad(ox.NamedNode("urn:a"), ox.NamedNode("urn:p"), ox.NamedNode("urn:b")))

for q in [
    "SELECT ?p WHERE { ?p <urn:q>* <urn:absent> }",
    "SELECT ?p WHERE { <urn:absent> <urn:q>* ?p }",
    "SELECT * WHERE { <urn:absent> <urn:q>* <urn:absent> }",
    "SELECT ?p WHERE { ?p <urn:q>? <urn:absent> }",
]:
    print(q, [[str(t) for t in row] for row in store.query(q)])
```

### Expected vs actual

Expected: SPARQL 1.1 section 18.5 (ZeroLengthPath) says a zero-length path `ZeroOrMorePath(P)` / `ZeroOrOnePath(P)` with a
constant at an end matches that constant even when it does not occur in the graph. So the first query returns one row
(`?p = <urn:absent>`), the second the same, the third one empty solution, the fourth `?p = <urn:absent>`.

Actual: all four return no solution. With the constant a node of the graph (`?p <urn:q>* <urn:b>`) the row is returned, so
the difference is the constant's absence from the graph, which makes even the constant-to-same-constant case empty.

### Versions

pyoxigraph 0.5.13 (the version pinned in this repo's environment). Not checked on other versions.

### Where it surfaces in our tests

W3C SHACL 1.2 suite `tests/sparql/functions/langLabelCount-example`: the function body runs
`?predicate rdfs:subPropertyOf* rdfs:label` and `rdfs:label` is not a node of the data graph, so the label count is 0
instead of 2 (expected value `"2 2 1 false"`, actual `"0 0 0 false"`). Both the native engine
(`starlayer.shacl_engine`, which runs queries on Oxigraph) and the legacy validator show it. Recorded as a strict xfail
in `packages/starlayer/tests/shacl/w3c_shacl12/known_failures.py` (`OXIGRAPH_QUERY_BUGS`), applied in
`test_w3c_validate.py`.

A workaround would be a query rewrite (`?p P* C` as `{ ?p P+ C } UNION { VALUES ?p { C } }`), which needs the query parsed;
not done, because the engine passes SPARQL text to Oxigraph unchanged.
