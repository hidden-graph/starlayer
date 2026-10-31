# SPARQL direct execution spike: query text straight to Oxigraph

Branch `sparql-direct` (a copy of `shacl-engine`), worktree `/Users/johnclements/Documents/GitHub/starlight/sparql-direct`.
Question: what does it take, and what is lost, if SPARQL 1.2 text is sent to Oxigraph with no rdflib parse, no
algebra-to-RDF encoding, no 1.2-to-1.1 lowering and no rdflib evaluator. pyoxigraph 0.5.13, oxrdflib 0.5.0, rdflib 7.6.0,
Python 3.10, 4-core macOS. Paths are relative to `packages/starlayer/starlayer/graph/` unless stated.

## 0. Summary

- **The `backend='rdf-1.2'` path already is "text straight to the engine".** `StarLayerGraph.query` calls
  `backends/native.native_query`, which does regex/tokenizer work on the text and calls `pyoxigraph.Store.query`. It never
  parses, lowers or evaluates with rdflib. The lowering round trip (`prepare_query_12 -> query_to_rdf11 -> rdf11_to_query`)
  runs only on the **default rdf-1.1 backend** (and for the OWL entailment regimes on any backend). So "go direct" is a
  decision about the rdf-1.1 backend and about what `query()` promises, not a new execution path.
- The prototype (`query/direct.py`, 150 lines) differs from `native_query` in three ways: `initNs`/`base` are passed to the
  engine (`prefixes=`, `base_iri=`; `native_query` ignores both), `initBindings` use the engine's `substitutions=` with the
  `VALUES` injection as fallback, and the dirLangString `=` guard is skipped on pyoxigraph >= 0.5.13 (it no longer aborts).
- **Tests: no difference found.** Flag on and off give identical counts on `tests/graph` (2526 passed) and `tests/sparql`
  (1078 passed). But those suites run almost entirely on rdf-1.1, so the flag touched only 53 to 165 queries per run
  (section 3). The real differences come from a 33-query probe of rdf-1.1 versus direct (section 3.2).
- **Speed:** the lowering path costs 10 to 40 ms per distinct query text (median 16 ms, of which rdflib parse is median 9 ms),
  paid once per (text, namespaces, base, entailment) because of the cache. Evaluation by rdflib is the larger cost: direct is
  2x to 50x faster on 18 of 20 queries; two queries do not finish in 120 s on rdflib at either size. One query (nested
  `FILTER EXISTS`) is 6x to 20x **slower** on Oxigraph.
- A parsed tree is still needed for: `entailment=RDF/RDFS`, the OWL regimes' query step, the prepared-query cache and
  `prepareQuery/parseQuery` (return rdflib objects), `Query.algebra` consumers (SHACL engine query checks, SRL, sqe, the
  remote decomposition), and reliable error positions. Section 5.

## 1. Trace: what happens to the text between `StarLayerGraph.query(text, initNs, initBindings, entailment=)` and execution

T = needs a parsed tree (rdflib algebra / `CompValue`). X = text only (regex, tokenizer, string splice). R = works on the result.

| Step | A. default rdf-1.1 over rdflib store | B. `backend='rdf-1.2'`, in-process `OxigraphStore` | C. `backend='rdf-1.2'`, remote HTTP (Fuseki, `oxigraph serve`) |
|---|---|---|---|
| argument checks (type, entailment value, `engine=`, `timeout=`) | X (values only) | X | X |
| `entailment=OWL-RDF-Based / OWL-Direct` | T: `prepare_query_cached` on a union view, then `union.query` (rdflib evaluator); delta from `infer()` | same as A (native self-view snapshot) | same as A |
| `entailment=RDF / RDFS` | T: `rewrite_algebra_for_rdf(s)` on the lowered algebra, in `query_cache.py` ~162 | `NotImplementedError` (never wired) | `NotImplementedError` |
| `entailment='native'` | `NotImplementedError` | X: label only, no behaviour | X: label only |
| plain `Graph` view over the store, copy of bound namespaces (`starlayer_graph.py` ~2500) | X (namespaces are data) | not done | not done |
| `strip_version_directive` | X (regex) | not done; engine reads `VERSION` | not done |
| conformance warning for `VERSION` | T: `contains_triple_term(algebra)` | X: regex `<<(`, `<<`, `{|`, `~`, `--` in `check_native_version_conformance` | X (same) |
| parse | T: `prepare_query_12` (rdflib grammar patched for 1.2), median 9 ms | none | none |
| lower to 1.1 and encode (`query_to_rdf11`) | T: walks the algebra, rewrites triple terms to `tt:` encoding triples | none | none |
| decode to a `Query` (`rdf11_to_query`) | T: rebuilds a `CompValue` tree, finds expression evaluators in the live grammar | none | none |
| prepared-query cache (`query_cache.py`) | T: stores the `Query` object, key (text, namespaces, base, entailment) | none | none |
| `initNs` | X: merged into the parse (`prepare_query_12(initNs=)`) | **ignored** (`native_query` documents it as unused) | ignored |
| `base` | T: parse argument | ignored | ignored |
| `initBindings` | R/terms: `_encode_init_bindings` (TripleTerm to `tt:HASH`), then rdflib `initBindings` | X: `inject_init_bindings` splices `VALUES` after the outer `{` (tokenizer skips strings, IRIs, comments) | same as B |
| remote-only store (rdflib `SPARQLStore`) | T: `decompose_for_remote` + `_AlgebraTranslator11.translateAlgebra` to text | n/a | n/a (`native` ships text) |
| blank-node stability / skolem rewrite | n/a | skipped (in-process ids are stable) | X: `blank_node_ids_are_stable` probe (one HTTP round trip, cached), then `skolem_semantics.rewrite` (tokenizer) |
| dirLangString `=` guard (`dirlang_equality.guard`) | n/a | X: tokenizer rewrite; no longer needed on 0.5.13 | only if `store.starlayer_engine == 'oxigraph'` |
| query type detection | T (`Query.algebra.name`) | X: regex `\b(ASK|CONSTRUCT|DESCRIBE)\b` on the whole text (a string literal "ask" would fool it; untested) | X |
| evaluation | rdflib evaluator, under `EVALUATION_LOCK` (one query at a time per process) | `pyoxigraph.Store.query`, no lock | HTTP POST |
| result | R: `restore_select_bindings` (`tt:HASH` back to `TripleTerm`), CONSTRUCT through `inject_missing_tt_encoding` | R: `_parse_ox_term` (TripleTerm, DirLangString, decimal fix, skolem IRI to `BNode`) | R: `_parse_json_term` (SPARQL JSON) |

Reading: only steps marked T need a tree, and every one of them belongs to the rdf-1.1 path or to the entailment regimes.
Everything B and C do is text-only already.

## 2. The prototype

`query/direct.py` (new). Opt-in: `StarLayerGraph(store=OxigraphStore(...), backend='rdf-1.2', direct_query=True)`, or
`STARLAYER_QUERY_DIRECT=1`. The same environment variable also switches `StarLayerDataset` with `backend='rdf-1.2'`
(query and update, `default_union=self.default_union`). Default off; the rdf-1.1 path and the remote HTTP path never use it
(the hook requires `_in_process(store)` and text input). Hook sites: `StarLayerGraph.query/update` and
`StarLayerDataset.query/update`, 4 to 8 lines each.

```python
run_direct(store, text, *, init_ns=None, init_bindings=None, base=None, default_union=True) -> rdflib.query.Result
run_direct_update(store, text, *, init_ns=None, base=None) -> None
direct_enabled(explicit=None) -> bool
```

- `store`: `pyoxigraph.Store` or the `OxigraphStore` wrapper (`_inner`).
- `init_ns` goes to `Store.query(prefixes=...)` (a `PREFIX` in the text wins), `base` to `base_iri=`. Checked: both exist
  on `query` and `update` in 0.5.13. No prologue is prepended. The graph hook passes `initNs or dict(self.namespaces())`
  so a bound prefix works as on rdf-1.1.
- `init_bindings` go to `substitutions={Variable: term}`. The engine raises `RuntimeError("... does not contains variable
  ?s in its SELECT projection")` when the variable is not projected, also for an aggregate-only projection; the fallback
  catches that one message and re-runs with `native.inject_init_bindings` (`VALUES`). For `SELECT *`, ASK and CONSTRUCT
  substitution works. Terms are converted rdflib -> pyoxigraph (`TripleTerm`/3-tuple to `Triple`, `BNode` to its skolem
  IRI as stored, `DirLangString` to a literal with `BaseDirection`).
- Results use `native_oxigraph._parse_ox_term` (same conversions as the current native path). CONSTRUCT/DESCRIBE return a
  new in-process native graph, as `execute_construct` does. ASK sets `askAnswer`.
- Errors are the engine's: `SyntaxError("error at 1:9: expected ...")` for bad syntax and unknown prefixes. rdflib's are
  `pyparsing.ParseException` and `Exception("Unknown namespace prefix")`. No StarLayer test asserts either type for a native
  graph, so none was adapted.
- Kept: the `VERSION` conformance warning (regex). Dropped when pyoxigraph >= 0.5.13: the dirLangString equality guard.
  Not supported (raises `NotImplementedError`): a prepared `Query` object as input.
- Tests: `tests/graph/unit/test_direct_query.py` (6 tests: initNs, base, projected and unprojected bindings, triple term
  and dirLangString results, ASK/CONSTRUCT/update, engine syntax error, flag default off).

## 3. Correctness

### 3.1 Existing suites, flag off (`STARLAYER_QUERY_DIRECT=0`) versus on (`=1`)

| Suite (command) | Off | On | Queries/updates that actually took the direct path (on) |
|---|---|---|---|
| `pytest tests/graph` (default groups) | 2526 passed, 317 skipped, 55 deselected | 2526 passed, 317 skipped, 55 deselected | not counted (these two runs predate the dataset hook and the namespace default) |
| `pytest tests/sparql` (default groups) | 1078 passed, 171 skipped, 11 xfailed | 1078 passed, 171 skipped, 11 xfailed | not counted |
| Final code, 21 targeted files: the 16 that use `backend='rdf-1.2'` on in-process Oxigraph (`test_oxigraph_*`, `test_native_and_update_hunt2`, `test_cross_backend_parity`, `test_dirlangstring`, `test_starlayer_graph`, `test_conformance`, shacl `test_native_backend_oxigraph*` ...), `test_direct_query`, `tests/graph/w3c_sparql12`, the Oxigraph round-trip W3C file, `test_dataset*`, with `--store-matrix` | 745 passed, 351 skipped | 745 passed, 351 skipped | 230 queries, 66 updates |
| `tests/shacl_engine` (run once, flag off, at the end) | 879 passed, 1 skipped | not run on | no query path involved |

Skips are the Oxigraph-HTTP and Fuseki tests ("Oxigraph not running"); no server was available. So **the remote HTTP path
was not exercised at all**. Differences by test id: none (zero). That is a weak result, not a strong one: the two
suites that matter most for rdflib-versus-Oxigraph semantics (`tests/graph`, `tests/sparql` on rdf-1.1) never reach the
flag. Not run: `--sqe-coverage` (the differential suite against Oxigraph, ~4 min), `--srl-conformance`, `tests/kg`,
`tests/shacl` (pySHACL tiers), the Fuseki and HTTP tiers.

### 3.2 Probe: the same 33 queries on rdf-1.1 (`StarLayerGraph()`) and direct (`probe.py`, scratchpad, not committed)

Data: a handful of triples with `"x"@EN-us`, mixed numerics, a triple term, `"hi"@en--ltr`. Results compared as sorted row
sets. 20 SAME, 13 DIFF with the final code (before the graph's bound prefixes were passed to the engine, `graph-bound-prefix` and
`unknown-prefix` also differed). Seven of the 13 only show the language-tag case of one stored literal. Clusters:

| Cluster | Cases (probe name) | Direction |
|---|---|---|
| (a) Oxigraph lacks what the lowering supplied | `entailment-rdfs`: rdf-1.1 returns `:i` for `?x a :Super`; native raises `NotImplementedError` (also on the existing native path). Nothing else found in the probe; the lowering supplies no function Oxigraph lacks, except RDFS/RDF rewrite | Oxigraph worse |
| (a) performance, not features | nested `FILTER EXISTS { ... FILTER }` (q16): 2.9 s versus rdflib 0.48 s at 20k, 55 s versus 2.8 s at 100k | Oxigraph worse |
| (b) language tag case | `"x"@EN-us` stored: rdf-1.1 returns `lang='EN-us'`, direct `'en-us'`; `LANG()` also lower case; `FILTER(lang(?o)="en-us")` matches only on direct | Oxigraph normalises (RDF 1.2 treats tags case-insensitively) |
| (b) numeric formatting | `1/3`: rdflib 28 digits, Oxigraph 18. `STR(1.0e0)`: `'1.0'` versus `'1'` | differs; both inside the XSD lexical rules |
| (b) `SELECT *` column order | rdflib: order of appearance (`?s ?o`); Oxigraph: alphabetical (`?o ?s`), also with substitutions. Breaks tuple unpacking of `SELECT *` rows | differs |
| (b) error type and message | bad syntax: `pyparsing.ParseException` versus `builtins.SyntaxError` with line:column; unknown prefix: `Exception("Unknown namespace prefix : zz")` versus `SyntaxError ... expected OPTIONAL` (the engine message is less helpful) | differs |
| (c) needs a tree | `entailment=`, cache, `prepareQuery`/`parseQuery`/`Query.algebra`, query-type detection, `initNs` defaulting, see section 5 | n/a |

Equal in the probe: aggregates, property paths, VALUES, CONSTRUCT, DESCRIBE, ASK, regex flags, `TRIPLE()`, `isTRIPLE`,
`LANGDIR`, `STRLANGDIR`, `CONCAT` on language literals, `VERSION`, mixed numeric `SUM`, decimal whole-number lexical form,
`initBindings` for projected, unprojected (fallback), literal, ASK and aggregate cases.

Known from `docs/working/oxigraph-capability-matrix.md` and not re-run here: `xsd:dateTime("2020-01-01")` (probe: equal),
`sameTerm` on `01` and `1`. `LOAD <file://...>` fails on Oxigraph (use `Store.load`).

## 4. Speed

Harness `bench.py` (scratchpad, not committed). Data: persons with 6 triples each plus 5% triple-term evidence nodes and a
chain of 20 departments; 20k and 100k triples (`len` 20,0xx and 100,0xx). Three paths on the same data: (i) default
`StarLayerGraph()` (rdf-1.1 over rdflib, best of 2 warm, so the cache is hit), (ii) native text path, (iii) direct. Columns
(ii) and (iii) are the same engine and agree within noise (mean 170 versus 171 ms at 20k, 2888 versus 2835 ms at 100k), so
only (iii) is shown. "Prep" is `prepare_query_cached({}, ...)` on an empty cache: parse + lower + encode + decode (best of
3). Row counts agreed across all three paths wherever rdflib finished. Milliseconds.

| query | rows 20k/100k | rdf-1.1 20k | direct 20k | rdf-1.1 100k | direct 100k | prep (cold) 20k/100k |
|---|---|---|---|---|---|---|
| q01 bgp-const | 1000/1000 | 91 | 17.8 | 50 | 15.2 | 16/17 |
| q02 count-type | 1/1 | 47 | 2.1 | 222 | 8.6 | 10/11 |
| q03 join2 | 1111/5556 | 139 | 69.9 | 583 | 247.3 | 14/16 |
| q04 join3-knows | 1111/5000 | 196 | 48.3 | 828 | 263.7 | 17/13 |
| q05 filter-num | 594/2997 | 579 | 45.9 | 2502 | 179.5 | 14/23 |
| q06 filter-regex | 477/2381 | 439 | 9.9 | 2133 | 75.5 | 18/14 |
| q07 group-count | 20/20 | 112 | 5.1 | 580 | 11.9 | 15/26 |
| q08 group-avg | 20/20 | 396 | 13.7 | 2187 | 69.3 | 25/40 |
| q09 optional | 1111/5556 | >120000 | 34.1 | >120000 | 261.5 | 18/15 |
| q10 path-plus | 400/400 | 64 | 18.0 | 28 | 12.0 | 12/15 |
| q11 path-seq | 1111/5000 | 203 | 57.0 | 662 | 190.0 | 20/16 |
| q12 distinct-order | 50/50 | 187 | 9.3 | 1161 | 21.7 | 18/18 |
| q13 union | 1178/5890 | 65 | 18.2 | 286 | 104.4 | 17/15 |
| q14 subquery | 20/20 | 95 | 5.2 | 505 | 19.4 | 18/23 |
| q15 bind-str | 3333/5000 | 661 | 147.5 | 1133 | 233.4 | 29/28 |
| q16 exists | 625/3273 | 478 | 2873.5 | 2759 | 54750.4 | 21/40 |
| q17 ask | 1/1 | 1 | 0.2 | 1 | 0.2 | 15/9 |
| q18 construct | 1111/5556 | 179 | 27.0 | 733 | 162.3 | 10/10 |
| q19 tt-pattern (`<<( ?s :knows ?o )>>`) | 167/834 | 103 | 17.3 | 345 | 45.8 | 15/16 |
| q20 tt-join | 66/333 | >120000 | 4.6 | >120000 | 30.1 | 33/18 |

(">120000" = stopped by a 120 s alarm; the rdflib result was not obtained, direct's count is shown. q09 is an
`OPTIONAL` with a second pattern, q20 a triple-term pattern joined to a second BGP and a `FILTER`; at 3k triples these
already took 3.4 s and 14 s.)

Overhead of the lowering path itself (the "prep" column): 10 to 40 ms per distinct (text, namespaces, base, entailment),
median 16 ms, flat in data size; rdflib's parse alone is median 9 ms, so about 7 ms is lowering + encode + decode. Warm (cache
hit) it is zero. The first run of the first query in a process also pays grammar installation, not measured. A caller that
varies the text per call (generated queries, `LIMIT` values inlined) pays it every time; the pySHACL per-focus-node pattern
is what the cache exists for. Evaluation dominates: at 100k, rdflib takes 0.5 to 2.8 s for queries Oxigraph answers in 10
to 260 ms. Direct versus the existing native text path: no measurable difference (same engine). Not measured: first-call
cold cost including grammar install, memory, concurrent queries (rdf-1.1 serialises on `EVALUATION_LOCK`), on-disk
RocksDB stores, remote HTTP.

## 5. What is lost by dropping the lowering, and what a StarLayer-owned parser/tree must supply

Lost or changed for a user of `StarLayerGraph.query` on the rdf-1.1 backend (backend rdf-1.2 already has the "after" behaviour):

1. **The rdf-1.1 backend as a SPARQL target.** It stores triple terms as `tt:` nodes, which only the lowering understands.
   Direct execution means rdf-1.1 data must live in an Oxigraph store, or the backend goes away (a graph-functionality
   decision, not a parser one).
2. **rdflib-quirk results** that StarLayer patched (`builtin_error_patches.py`, `operator_patches.py`): arithmetic digits,
   `STR(1e0)`, case of language tags, error behaviour of casts. These become Oxigraph's (cluster b).
3. **Custom SPARQL functions** registered in rdflib (`tt:fn/*`): unneeded for native triple terms; user-registered ones would
   need Oxigraph's per-call `custom_functions=`.
4. **Query-time entailment** `entailment=RDF/RDFS` (algebra rewrite, `entailment_rdf(s).py`): not available on any native
   path today and raises there. Either keep the rewrite, which needs a tree (below), or materialise with `infer()`.
5. **OWL regimes' query step**: the delta is computed by `infer()` (no tree), but the union query runs through
   `prepare_query_cached` and rdflib's evaluator over `_UnionForQuery`. Direct needs a union of a store and a small delta
   graph, e.g. load the delta into a scratch named graph or `custom` default-graph list (`default_graph=[...]`, not tried).
6. **The prepared-query cache and prepared objects**: `prepareQuery`, `parseQuery`, `processUpdate` return rdflib `Query`,
   `CompValue`, `Update`. A direct path has only text; it could keep a "prepared" wrapper that holds text + prefixes.
7. **Error types and messages** (cluster b), and rdflib's line/column for syntax errors with a StarLayer grammar.
8. **Single-engine lock-in**: any engine difference (Oxigraph `FILTER EXISTS` slowness, `SELECT *` order, alphabetical
   variable order) can no longer be dodged by running the other evaluator.
9. **Not preserved by decision:** the `salg:` RDF export of the algebra, `Query.algebra` access, `lower_rdf11.py`,
   `to_rdf.py`/`from_rdf.py` on the query path.

What the **parsed tree** must provide for each remaining need (the minimum, not a full AST):

| Need | Minimum the StarLayer-owned tree must supply |
|---|---|
| `entailment=RDF/RDFS` rewrite | BGP nodes with triple patterns whose predicate is a term or a path object, a way to insert a path (`rdf:type/rdfs:subClassOf*`) and fresh variables, and printing back to text. Round trip tree -> text must preserve the rest of the query. |
| Query kind and `VERSION`/triple-term/dirLangString detection | form (SELECT/ASK/CONSTRUCT/DESCRIBE) and flags "uses triple term", "uses `--` language"; today regexes (known false-positive risk: a string literal containing `ask`). A real tokenizer fixes both without a full tree. |
| `initBindings` | projected variables and the outermost group's brace position, so `VALUES` is not spliced by regex; or just the variable list (to choose substitution versus `VALUES`). |
| `initNs` / `base` / prefix defaults | declared prefixes and `BASE`, so a graph's bound prefixes can be applied by the engine (done here with `prefixes=`) and unknown prefixes reported with a position. |
| Prepared-query cache | a hashable normal form (text + prefix map is enough; no tree needed). |
| SHACL engine query checks (`shacl_engine/sparql_support.py`, `shacl/meta_shapes.py`, `salg/semantic_checks`) | projected variables, `sh:select` structure, `$this`/`$PATH` placement, unbound projected variables: a scope-aware variable analysis (the `_addVars`/`find_unbound_projected_variables` equivalent). |
| `sqe` (editor, text rendering), 24 KG queries | already works from the parse tree to text; needs the same node kinds (query, group, BGP, filter, bind, values, path, aggregate, subquery, expression) and a printer. |
| SRL (`srl.py`) | expression trees for rule bodies/heads, variable use, aggregates; evaluates rule bodies as SELECT/CONSTRUCT text on Oxigraph (not tried here). |
| `remote_decompose` (rdf-1.1 over a remote rdflib store) | goes away with the rdf-1.1 backend. |
| Errors | position (line, column) and expected-token message from the owned parser (cluster b). |

The biggest design fork: **everything above except entailment rewrite and SHACL/sqe/SRL analysis needs only a tokenizer**,
not a tree. If the entailment rewrite stays text-to-text, the tree is needed only by the analysis consumers.

## 6. Not run, and caveats

- The remote HTTP engine (Fuseki, `oxigraph serve`) and the on-disk Oxigraph store: no server, so skipped; the direct path
  is in-process only by construction.
- `--sqe-coverage` differential suite, `--srl-conformance`, `tests/kg`, `tests/shacl` (pySHACL), `tests/starontology`.
- The full `tests/graph` and `tests/sparql` runs happened before the dataset hook and before the graph's bound prefixes were
  passed to the engine. The 21-file targeted run (section 3.1) used the final code. The final code was not re-run over the
  full suites.
- No force-the-rdf-1.1-suites-through-Oxigraph experiment: it would need a harness that mirrors each rdf-1.1 test's data into a
  native graph; the probe in 3.2 stands in for it, at 33 queries.
- Timings are on a machine shared with other test runs for part of the work; the 20k and 100k runs ran concurrently with each
  other (4 cores) and, for the shacl_engine run, with the 100k run. Treat milliseconds as +-30%. q16 reproduced twice.
- `ruff check packages/ tools/` reports 85 errors in files this spike does not touch; the new and edited files are clean.
