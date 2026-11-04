# Oxigraph upstream issues (drafts)

Project notes only. Nothing here is, or is to be, posted to Oxigraph's GitHub or any other outside forum: this file records
what we found so that someone can decide later. One section per issue. Before anyone acts on a section, check it against a
current Oxigraph release (written against pyoxigraph 0.5.13) and against existing issues.

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

## 2. FILTER EXISTS with an inner FILTER over an outer variable is evaluated per outer row (6x to 400x slower than the equivalent join)

Status: DRAFT, not filed. Written 2026-11-03 against pyoxigraph 0.5.13.

### Search for an existing report

Searched oxigraph/oxigraph issues (`gh search issues`: "EXISTS", "FILTER EXISTS slow", "decorrelat") and the discussion titles reachable with `gh api`. No issue reports this case. The nearest:

- #885 "Poor performance on FILTER NOT EXISTS" (open). A `FILTER NOT EXISTS` inside a larger query is run once per outer row; the maintainer (Tpt) says the planner should one day rewrite `FILTER NOT EXISTS` to `MINUS` from a cost model, and the reporter suggests two optimisations: "translate FILTER NOT EXISTS to MINUS" and "penalise inner loops". The slowdown there comes from join ordering around the EXISTS; this report is about the EXISTS evaluation itself, with an inner FILTER that names an outer variable, and a rewrite that is exact without any cost model. It could be added to #885 as a second data point instead of a new issue; that is the call to make before filing.
- #1980 and #1894 (open) are other slow-query reports (named-graph loops, variable-length paths); not this.

### Title

`FILTER [NOT] EXISTS` whose inner `FILTER` uses an outer variable is re-evaluated for every outer solution; a decorrelated sub-select join is hundreds of times faster

### Reproduction (pyoxigraph only)

```python
import sys, time
import pyoxigraph as ox

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3300
E = "http://e/"
XSD_INT = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
n = lambda s: ox.NamedNode(E + s)
store = ox.Store()
for i in range(N):
    p = n(f"p{i}")
    store.add(ox.Quad(p, n("age"), ox.Literal(str(20 + i % 60), datatype=XSD_INT)))
    store.add(ox.Quad(p, n("knows"), n(f"p{(i * 7 + 1) % N}")))
    store.add(ox.Quad(p, n("knows"), n(f"p{(i * 13 + 5) % N}")))

SLOW = """PREFIX : <http://e/>
SELECT ?p WHERE { ?p :age ?a .
  FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }"""
FAST = """PREFIX : <http://e/>
SELECT ?p WHERE { ?p :age ?a .
  { SELECT DISTINCT ?p ?a WHERE { ?p :age ?a . ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } }"""

print("pyoxigraph", ox.__version__, "triples", len(store))
res = {}
for name, q in (("FILTER EXISTS", SLOW), ("sub-select join", FAST)):
    t = time.perf_counter()
    res[name] = sorted(str(s["p"]) for s in store.query(q))
    print(f"{name:16s} {time.perf_counter() - t:8.2f} s  rows={len(res[name])}")
assert res["FILTER EXISTS"] == res["sub-select join"]
```

The same holds with `FILTER NOT EXISTS` and `MINUS { SELECT DISTINCT ... }`.

### Timings

| Case | Data | Time |
| --- | --- | --- |
| pyoxigraph `FILTER EXISTS` (the script above, N=3300, 9,900 triples, machine under load) | 9.9k triples | 38.2 s |
| same, sub-select join (`FAST`) | 9.9k triples | 0.20 s |
| same script, N=1000 (3.0k triples) | 3.0k triples | 3.56 s vs 0.08 s |
| StarLayer benchmark (3,300 persons with type, age, 2 x knows, name, city: 20k triples), Oxigraph evaluating the query text | 20k triples | 25.7 s |
| same query lowered to rdflib's evaluator (rdflib algebra on a StarLayer graph) | 20k triples | 4.2 s |
| same query rewritten as the sub-select join, run on Oxigraph | 20k triples | 95 ms |

Row sets are identical in every case. Time grows roughly with the square of the data for the original form, so the gap widens as the store grows. The 20k-triple figures were taken by the benchmark in `/private/tmp/claude-501/s/exists_bench.py` (not in the repo); the 9.9k-triple row and the N=1000 row come from the script above.

### Expected vs actual

Expected: the cost of `FILTER EXISTS { ... }` grows with the size of the inner pattern times the number of outer solutions that reach it, and an inner `FILTER` that mentions an outer variable does not make it worse than a join; the time should be within a small factor of the sub-select form, and no worse than evaluating the inner pattern with the outer binding pushed in through the indexes.

Actual: with the inner `FILTER(?b > ?a)` over the outer `?a`, the inner pattern appears to be evaluated per outer row without using the outer row to restrict `?p :knows ?q` (the `?p` binding is available, and `?q :age ?b` is then a lookup per `?q`), so each outer row scans far more than it needs. The join form evaluates the inner pattern once and the DISTINCT set is hash-joined back, 100 to 400 times faster here. (I have not read the evaluator to say which step is the cost; that is a guess from the timings, so check it with a profile.)

### Suggested optimisation

EXISTS subquery decorrelation (unnesting), as in relational engines. For a group `{ A FILTER EXISTS { Q } }` where `A` is a basic graph pattern whose variables are always bound, and `Q` is triple patterns and filters:

```
{ A  FILTER EXISTS { Q } }      ->  { A  { SELECT DISTINCT ?v... WHERE { A Q } } }
{ A  FILTER NOT EXISTS { Q } }  ->  { A  MINUS { SELECT DISTINCT ?v... WHERE { A Q } } }
```

where `?v...` are the variables `A` and `Q` share (so `A`'s own variables, bound in every solution, make the join exact; NOT EXISTS needs at least one shared variable for MINUS to remove anything). It is a semi-join / anti-join, so it can also be done inside the planner as a semi-join operator instead of a textual rewrite, which would not need the copy of `A`. Cases to leave alone (the rewrite is not exact): variables of `A` that may be unbound (OPTIONAL, UNION), `Q` with BIND, sub-selects or non-deterministic functions, a group that is the right side of OPTIONAL (its FILTER sees left-side variables), a group inside GRAPH or another EXISTS (outer bindings are visible), and EXISTS used inside a larger expression. A cost-based version could pick the join only when the outer side is large.

The StarLayer implementation is `packages/starlayer/starlayer/sparql/sqe/rewrite.py` with a differential test against the original text on Oxigraph (`tests/sparql/unit/test_exists_rewrite.py`); it can be used as a reference for the conditions above.
