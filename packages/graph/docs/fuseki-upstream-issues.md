# Apache Jena (ARQ) Upstream Issues

*Last reviewed: 2026-08-10*

Bugs found in [Apache Jena](https://github.com/apache/jena)'s ARQ SPARQL engine (`jena-arq` - the module that parses and evaluates SPARQL, shared by every Jena-based tool), accessed via a Fuseki HTTP endpoint, the native `rdf-1.2` backend's second SPARQL-star option alongside Oxigraph. Confirmed via [apache/jena#3658](https://github.com/apache/jena/pull/3658)'s own file list that the closely related fix discussed below lives entirely under `jena-arq` - the separate `jena-fuseki2` module (the actual HTTP server) isn't touched at all. So this is an ARQ defect, not a Fuseki-specific one: it would reproduce in any Jena-based application that calls into `jena-arq` directly, not just through a running Fuseki server. Tested against the latest available release rather than a pinned old version - currently `jena-6.1.0` (via `atomgraph/fuseki:latest`, confirmed 2026-08-10; `secoresearch/fuseki`, used earlier, tops out at `jena-5.5.0` and is no longer updated by its maintainer).

## Issue 1 - ARQ rejects an invalid triple-term predicate, but not an invalid triple-term subject

ARQ generally rejects inserting an invalid triple into the graph. Per RDF 1.2 (`ttSubject ::= iri | BlankNode`, `verb ::= iri`), a triple term's `subject` must be an IRI or blank node and its `predicate` must be an IRI - never a Literal in either position. ARQ correctly enforces this for `predicate` - inserting a triple term with a Literal predicate is rejected outright, at parse time, with an HTTP 400 syntax error (from Fuseki, the HTTP surface used to reach it here). It does **not** enforce the identical rule for `subject` - the same shape with a Literal subject is accepted and written to the graph.

**Reproduction** (pure Python standard library, no dependencies beyond a running Fuseki endpoint at `localhost:3030` with an in-memory dataset named `repro` - create with: `docker run -d --name fuseki-repro -p 3030:3030 atomgraph/fuseki:latest --update --mem --ping /repro`):

```python
import json
import urllib.parse
import urllib.request
import urllib.error

BASE = "http://localhost:3030/repro"

def sparql_update(update):
    req = urllib.request.Request(
        f"{BASE}/update",
        data=urllib.parse.urlencode({"update": update}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    urllib.request.urlopen(req).read()

def sparql_query(query):
    url = f"{BASE}/query?" + urllib.parse.urlencode({"query": query})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"})
    return json.load(urllib.request.urlopen(req))

sparql_update("CLEAR ALL")

# Invalid Literal in PREDICATE position of a triple term
try:
    sparql_update('PREFIX : <http://example/> INSERT DATA { :claim :about <<( :s "bad predicate" :o )>> . }')
    print("predicate case: accepted (unexpected)")
except urllib.error.HTTPError as e:
    print(f"predicate case: rejected, HTTP {e.code}")

# Invalid Literal in SUBJECT position of a triple term
try:
    sparql_update('PREFIX : <http://example/> INSERT DATA { :claim :about <<( "bad subject" :p :o )>> . }')
    print("subject case: accepted (unexpected bug)")
except urllib.error.HTTPError as e:
    print(f"subject case: rejected, HTTP {e.code}")

# Query out everything actually stored
result = sparql_query("SELECT * { ?s ?p ?o }")
print("stored triples:")
for row in result["results"]["bindings"]:
    print(" ", row)
```

Output:

```
predicate case: rejected, HTTP 400
subject case: accepted (unexpected bug)
stored triples:
  {'s': {'type': 'uri', 'value': 'http://example/claim'}, 'p': {'type': 'uri', 'value': 'http://example/about'}, 'o': {'type': 'triple', 'value': {'subject': {'type': 'literal', 'value': 'bad subject'}, 'predicate': {'type': 'uri', 'value': 'http://example/p'}, 'object': {'type': 'uri', 'value': 'http://example/o'}}}}
```

The predicate case is rejected before the triple ever reaches storage - ARQ's own SPARQL parser has no grammar production for a Literal there at all (`Encountered "bad predicate" ... Was expecting <IRIref> ...`). The subject case is accepted, and the stored triple's object (`o`) is `<<( "bad subject" :p :o )>>` - a triple term with a Literal subject, not a valid RDF 1.2 term under any reading of the grammar. This is real, persisted data corruption, not a query-time artifact: any later read of this graph, by any client, gets this invalid term back.

Oxigraph, a second independent RDF 1.2 engine, correctly rejects both cases (HTTP 400 either way, nothing written) on the identical update text - confirming this is a genuine ARQ bug, not an ambiguous spec reading.

Also confirmed via `TRIPLE()` (the SPARQL function, as opposed to inserting the literal `<<( )>>` syntax directly): `TRIPLE(:s, "bad predicate", :o)` correctly leaves its result unbound, while `TRIPLE("bad subject", :p, :o)` wrongly binds one - so this isn't specific to the `INSERT DATA` parser path, the same asymmetry holds for `TRIPLE()`'s own evaluation-time validation too.

### Status

**Reported upstream: [apache/jena#4141](https://github.com/apache/jena/issues/4141), filed 2026-08-10. Open, unresolved.**

Confirmed still present in `jena-6.1.0`, the latest release at time of filing - not just an old-container artifact.

- A closely related bug was already reported and fixed: [apache/jena#3659](https://github.com/apache/jena/issues/3659) ("Restrict triple terms to have only IRI as a constant subject in VALUES and expressions"), fixed by [apache/jena#3658](https://github.com/apache/jena/pull/3658) (merged 2025-12-20, first released in `jena-6.0.0`/2026-01-27). Both are scoped to `jena-arq`, not Fuseki - the fix is narrower than its title suggests, too: it covers exactly what the title says, literal `<<( )>>` syntax written directly in a `VALUES` row or `BIND`, and nothing else. Confirmed directly against a live `jena-6.1.0` endpoint:
  - `VALUES ?x { <<( "bad" :p :o )>> }` - fixed by #3658, HTTP 400.
  - `BIND(<<( "bad" :p :o )>> AS ?x)` - fixed by #3658, HTTP 400.
  - `TRIPLE("bad", :p, :o)` (the function - what this repo's own failing W3C fixtures actually use) - **still broken**, silently accepts it.
  - `INSERT DATA { :s :q <<( "bad" :p :o )>> . }` (a ground triple term written directly - the reproduction above) - **still broken**, still persists it.
  - Re-ran `expression/triple-on-triple-terms.rq` (the actual W3C fixture behind 3 `xfail`'d tests in this repo's own suite) straight through `StarLayerGraph` against `jena-6.1.0`: identical failure to the older `jena-5.5.0`.
- Filed as [#4141](https://github.com/apache/jena/issues/4141) rather than reopening #3659, since #3658's own fix was real and correctly scoped to what its title said - this is a distinct gap the fix didn't cover (`TripleTermOps.java`/`E_TripleFn.java`, the `TRIPLE()` function's own implementation, was touched by #3658 but apparently not for the subject-argument case), not a regression or an incomplete revert of it.
