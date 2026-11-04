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

## 3. The store rewrites derived numeric datatypes to `xsd:integer` (issue #190)

Project note, not a draft for posting. Oxigraph normalises literals on insert: `"3"^^xsd:nonNegativeInteger` is stored as
`"3"^^xsd:integer`, and `"4.0"^^xsd:decimal` as `"4"`. The parser keeps the written form; the store does not. Reproduced on a
bare `pyoxigraph.Store` (0.5.13).

Where it surfaces here: the six cardinality shapes in `packages/starlayer/starlayer/starontology/manchester_shapes.ttl`
(`manch:ExactShape`, `MaxShape`, `MinShape`, `DMinShape` and two more) named `sh:datatype xsd:nonNegativeInteger`, which the
stored data can never match. **Decision (2026-11-04): keep the workaround.** They now say `sh:datatype xsd:integer` with
`sh:minInclusive 0`. The checking is looser (a literal written as `xsd:integer` now passes). The Manchester encoder still
emits `nonNegativeInteger`.

Revisit when the store keeps derived types (upstream PR #2010): restore `xsd:nonNegativeInteger` in those shapes, regenerate
`starontology.trig` and the Manchester snapshot, and drop the related strict xfails. Any other shape that names a derived
numeric `sh:datatype` will hit the same rewrite.

## 4. `rdf:parseType="Literal"` keeps in-scope namespace declarations (no exclusive canonicalisation)

Project note, not for posting. RDF 1.2 XML Syntax says the lexical form of an `rdf:XMLLiteral` is the exclusive XML
canonicalisation of the element content, so a namespace declaration that the content does not use is not written. Oxigraph's
RDF/XML parser copies every in-scope declaration onto the literal's top element.

```python
import pyoxigraph as ox

doc = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:eg="http://example.org/" xml:base="http://example.com/">
  <rdf:Description rdf:about="http://www.example.org/a"><eg:prop rdf:parseType="Literal"><br /></eg:prop></rdf:Description>
</rdf:RDF>"""
print(next(iter(ox.parse(input=doc, format=ox.RdfFormat.RDF_XML))).object.value)
```

Expected (exclusive canonical form): `<br></br>`. Actual (pyoxigraph 0.5.13):
`<br xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:eg="http://example.org/"></br>`.

Where it surfaces here: the W3C RDF 1.2 RDF/XML evaluation tests `rdf12-xml-an-13` and `rdf12-xml-an-14` (pinned as known gaps in
`tests/graph/w3c_rdf12/test_w3c_rdf12_oxigraph.py`, `KNOWN_GAPS`). The owner also named `xml-canon-test001` and
`xml-canon-test002`; they are not in the vendored `rdf12` suite (`tests/graph/w3c_rdf12/data/`), so they are not exercised
here. The cause is the same: the literal differs only in namespace declarations that the content does not use.

Consequence for users: two XMLLiterals that are equal under exclusive canonicalisation can be different terms after an RDF/XML
parse, depending on the declarations in scope at the point of the literal. No workaround in the wrapper (it would mean
re-canonicalising XML on every RDF/XML parse).

## 5. A default graph built from several graphs is not a set: duplicates are counted

Project note, not for posting. Checked 2026-11-05 on pyoxigraph 0.5.13 with one triple stored in two named graphs:

| Query | Result | Expected (SPARQL 1.1, 13.2: several `FROM` graphs form the RDF merge, a set) |
|---|---|---|
| `SELECT (COUNT(*) ...) FROM <g1> FROM <g2> WHERE { ?s ?p ?o }` | 2 | 1 |
| same with `default_graph=[g1, g2]` | 2 | 1 |
| same with `use_default_graph_as_union=True` | 2 | 1 |
| `SELECT ?s ?p ?o` (no DISTINCT), union default | one row per graph | one row |
| `Store.quads_for_pattern(s, p, o, None)` / `len(store)` | quads (3 with a copy in the default graph) | quads: correct for a quad store |

An RDF graph is a set, so the merge of two graphs holding the same triple holds it once; counts, aggregates and non-DISTINCT
SELECTs over a union default graph are wrong. Our wrapper's `len`, `triples` and `iter` already deduplicate; SPARQL run through
the wrapper does not. In the code-KG data this is 373 duplicate triples (`starlayer_kg.load()`).
Handling in this project (decided 2026-11-05: fix in the wrapper, not document-only): `graph/oxgraph/union.py`. A dataset with
`default_union=True` that holds a triple in more than one graph (detected with `COUNT(*)` against `COUNT(DISTINCT)`; free when at most one graph holds data) runs its
queries and `sparql_query` on a cached in-memory copy of the store whose default graph is the set of all triples (the named graphs are copied as they are), and
a SPARQL Update reads the union from a scratch graph filled by the engine (`INSERT ... WHERE { {?s ?p ?o} UNION {GRAPH ?g {?s ?p ?o}} }`).
The copy is dropped by every write through the wrapper (`union.touch()`, also called by `as_store()`).

Options measured (pyoxigraph 0.5.13, 5 graphs, 2% of the triples in a second graph; one run each, this machine):

| | 1k triples | 100k | 1M | code-KG data (168,362 quads, 160,941 distinct) |
|---|---|---|---|---|
| Oxigraph `COUNT(*)` on the union (wrong when duplicates exist) | 1 ms | 58 ms | 0.3 s | 0.1 s |
| detect overlap (`COUNT` vs `COUNT(DISTINCT)`) | 1 ms | 0.14 s | 1.8 s | 0.3 s |
| (b) build the merged copy (engine `INSERT` into the copy) | ~0.1 s | 1.3 s (first query 1.28 s) | ~10 s | 2.3 s |
| (b) a query on the cached copy | 14 ms | 30 ms | - | 80 ms (a point query 0.3 ms) |
| (b) first query after a write, duplicates present | 11 ms | 1.5 s | ~10 s | 2.6 s |
| (b) same, no duplicates (only detection) | ~1 ms | 0.2 s | ~2 s | - |
| (a) build a merged graph in the store once | 15 ms | 1.1 s | 12 s | - |
| (a) 1000 single adds with write-through | 2 -> 17 ms | 1.8 -> 10 ms | 2.3 -> 11 ms | - |

(a), a merged default graph kept in the store write-through, is cheaper after a write but is not exact here: a `pyoxigraph.Store` takes no attributes, so the
merged graph would be a hidden named graph in the store, visible to `len(store)`, TriG output and any other client of the file, and a write that does not go
through the wrapper (the engine view, a second client of a persisted store, `ds.store`) leaves it wrong with no way to notice. SPARQL Update would still need the
copy. (c), an `sqe` tree or text rewrite, is exact only for BGP matching: every triple pattern would need a `SELECT DISTINCT` over `GRAPH ?g`, and property paths
(`a/b`, `a|b`, `^a`) multiply by the duplicates inside the path, aggregates, `MINUS` and `EXISTS` see different multiplicities; not adopted.
Limits of (b): the cost is O(n) on the first union query after a write when a triple is in two graphs (about 1.3 s per 100k triples), a write straight on the
store through a kept reference is not seen until `union.touch()`, a query with its own `FROM` clauses is unchanged, and the SHACL engine's own union view
(`engine_view()`, used by `validate`) is not covered.

## 6. REPLACE and REGEX do not follow the XPath rules

Project note, not for posting. Checked 2026-11-06 on pyoxigraph 0.5.13. SPARQL 1.1 (17.4.3.14, 17.4.3.15) defines `REGEX` and
`REPLACE` by `fn:matches` and `fn:replace` (XPath F&O 3.1), whose dialect is the XSD regular expression with a few additions.
Oxigraph runs the Rust `regex` crate with its own replacement syntax.

```python
import pyoxigraph as ox

store = ox.Store()
for expr in [
    "REPLACE('abc', 'x*', '-')",            # a pattern that can match the empty string
    "REPLACE('abc', '', '-')",
    "REPLACE('abc', 'b', '$')",             # '$' not followed by a digit
    r"REPLACE('abc', 'b', '\\x')",          # '\' not followed by '\' or '$'
    r"REPLACE('abc', 'b', '\\$')",          # '\$' is a literal '$'
    r"REGEX('a b', '\\bb')",                # \b is not in the XSD dialect
    r"REGEX('abc', '\\p{IsBasicLatin}+')",  # an XSD block escape
]:
    (row,) = list(store.query(f"SELECT ({expr} AS ?r) {{}}"))
    print(expr, "->", None if row["r"] is None else row["r"].value)
```

| Expression | XPath gives | Oxigraph |
|---|---|---|
| `REPLACE('abc','x*','-')` and `REPLACE('abc','','-')` | error (FORX0003, a match of length zero), so unbound | `-a-b-c-` |
| `REPLACE('abc','b','$')` | error (FORX0004), unbound | `a$c` |
| `REPLACE('abc','b','\x')` | error (FORX0004), unbound | `a\xc` |
| `REPLACE('abc','b','\$')` | `a$c` | `a\$c` |
| `REGEX('a b','\bb')` | error (FORX0002, `\b` is not in the dialect), unbound | `true` |
| `REGEX('abc','\p{IsBasicLatin}+')` | `true` (block escapes are in the dialect) | unbound (rejected) |

Valid XSD constructs such as `\p{L}`, `\d` and `\w` work, and a lookahead `(?=...)` is rejected, as XPath does. So the deviation
runs both ways: Rust-only syntax (`\b`, and others the crate accepts) is accepted, and XSD-only syntax (`\p{Is...}` block escapes,
`\i`, `\c`, character-class subtraction `[a-z-[aeiou]]`) is not. The B1 classification said `\p{L}+` is rejected; that was wrong,
it is accepted and gives `true`.

Where it surfaces: the old rdflib evaluator was patched toward the XPath rules (`tests/graph/unit/test_contracts_hunt3.py`, five
tests); on Oxigraph they differ. Recorded as the strict xfail `test_replace_and_regex_follow_xpath` in
`tests/graph/oxgraph/test_oxigraph_deviations.py`. It stays an expected failure until every row above agrees with XPath, so a
partial fix is visible only in this table. No client-side patch (it would need a translator from the XSD dialect to the `regex`
crate's).

## 7. Boolean ordering: `false < true` is an error

Project note, not for posting. Checked 2026-11-06 on pyoxigraph 0.5.13. SPARQL 1.1 17.3 maps `<`, `>`, `<=`, `>=` on two
`xsd:boolean` values to `op:boolean-less-than` and `op:boolean-greater-than` (`false` before `true`).

```python
import pyoxigraph as ox

store = ox.Store()
for expr in ["false < true", "true > false", "false <= true", "true >= false", "true < false", "true < true"]:
    (row,) = list(store.query(f"SELECT ({expr} AS ?r) {{}}"))
    print(expr, "->", None if row["r"] is None else row["r"].value)
```

Expected `true, true, true, true, false, false`. Actual: the first five are unbound (an error), only `true < true` gives `false`.
`ORDER BY` over booleans does put `false` first, so the engine knows the order; only the comparison operators lack it.
Recorded as the strict xfail `test_boolean_ordering_false_before_true`.

## 8. A negated property set with forward and inverse members is returned as a set, not a bag

Project note, not for posting. Checked 2026-11-06 on pyoxigraph 0.5.13. SPARQL 1.1 18.2 translates a negated property set with
both forward and inverse members to the union of the forward set and the inverse of the reverse set, a bag: a pair found twice is
two solutions.

```python
import pyoxigraph as ox

store = ox.Store()
for s, p, o in [("a", "p", "b"), ("b", "q", "c"), ("c", "p", "d"), ("d", "p", "a"), ("x", "p", "b"), ("a", "r", "b")]:
    store.add(ox.Quad(ox.NamedNode("urn:" + s), ox.NamedNode("urn:" + p), ox.NamedNode("urn:" + o)))
n = lambda q: next(iter(store.query(q)))["n"].value
print(n("SELECT (COUNT(*) AS ?n) { ?s !(<urn:p>|^<urn:q>) ?o }"))                                   # 6
print(n("SELECT (COUNT(*) AS ?n) { { ?s !(<urn:p>) ?o } UNION { ?s ^!(<urn:q>) ?o } }"))          # 7
```

The inverse arm finds `(b, a)` twice (through `a :p b` and through `a :r b`); the union keeps both, Oxigraph returns it once.
Expected 7, actual 6. A set with members in one direction only is a bag in Oxigraph, as the specification has it
(`?s !(:q) ?o` returns `(a, b)` twice here); only the mixed form drops duplicates, also `?s !(:q|^:q) ?o`. Recorded as the strict
xfail `test_negated_property_set_with_both_directions_is_a_bag`; it compares the path against its own UNION translation on the same
data, so it needs no hand-computed rows.

## 9. COPY and ADD from a graph that does not exist: not a deviation

Project note, not for posting. Checked 2026-11-06 on pyoxigraph 0.5.13; the spec text re-read 2026-11-06 (SPARQL 1.1 Update, W3C
Recommendation 21 March 2013). `CLEAR`, `DROP` and `MOVE` of a graph that does not exist raise `The graph <...> does not exist`
unless `SILENT`; `COPY` and `ADD` do not. **The earlier reading of this as against the spec was wrong.** Sections 3.2.3 (COPY),
3.2.4 (MOVE) and 3.2.5 (ADD) say: "By default, the service _MAY_ return _failure_ if the input graph does not exist." Failure is
permitted, not required, so Oxigraph succeeding is allowed. COPY is defined by the equivalence
`DROP SILENT (GRAPH <to> | DEFAULT); INSERT { ... } WHERE { ... }`, so a `COPY` from an absent graph empties the target, which
is what Oxigraph does; the spec does not address that case explicitly, but the equivalence gives it. There is nothing to report.

What remains is a usage warning: an unchecked `COPY` from a mistyped graph name wipes the target. Pinned by
`test_copy_and_add_of_an_absent_graph_are_allowed_to_succeed` (not an xfail).
