# Oxigraph (pyoxigraph) versus rdflib: capability matrix for StarLayer

Branch `shacl-engine`. Measured 2026-10-31 with `/usr/local/bin/python3` 3.10.8 on macOS x86_64: pyoxigraph 0.5.13,
oxrdflib 0.5.0, rdflib 7.6.0. Every row marked yes/partial/no comes from a check in
`packages/starlayer/benchmarks-graph/oxigraph_capability_checks.py` (run it; `--net` adds the PyPI/Pyodide rows,
`--perf` adds the timing table) or from a document named in the evidence column. Anything neither run nor read is
marked **unverified**.

"rdflib" means stock rdflib 7.6.0, **without** StarLayer's patches (`parse12`, `*_patches.py`, `DirLangString`).
Where the StarLayer layer changes the answer, the impact column says so. "pyoxigraph" means `pyoxigraph.Store` and the
module functions; "oxrdflib" means rdflib's `Graph(store='Oxigraph')`, the route StarLayer already uses.

Check names below are the strings printed by the script (`ox:` = pyoxigraph, `rdflib:` = stock rdflib).

## 0. Headline

1. **The `=` abort on `rdf:dirLangString` is gone in 0.5.13.** All 16 shapes in the table of
   `docs/upstream-issues/oxigraph-upstream-issues.md` (and more: join, DISTINCT, GROUP BY, ORDER BY, MIN, MINUS,
   VALUES join, `IN`, `!=`, `<`) ran to completion, each in its own subprocess, and `=` returns the right answers
   (`ox:dirLangString-eq-correct-results`). The upstream doc was written against 0.5.11 / server 0.5.9.
2. **No algebra tree, no `initBindings`-style hook on a parsed query, no SPARQL timeout.** pyoxigraph takes query text
   and returns results. Nothing in the module parses a query into an inspectable structure (`ox:algebra-access`).
   StarLayer's `sqe`, `srl` and `spexpr` layers build on rdflib's algebra, so they cannot move to Oxigraph as is.
3. **Oxigraph rewrites literal lexical forms on store, and also in the query parser**; so does rdflib by default
   (`NORMALIZE_LITERALS`), including `StarLayerGraph`. Oxigraph cannot be told to stop; rdflib can.
4. **Oxigraph is 10 to 1000 times faster** on every operation timed (section 7), and its query engine releases the
   GIL.
5. **Oxigraph reads and writes RDF 1.2 Turtle, TriG and N-Triples natively.** Stock rdflib parses none of it.
   StarLayer's `parse12` and serializers (about 8,000 lines, by `docs/working/graph-rdflib-compat-inventory.md`)
   exist for that gap. But Oxigraph's JSON-LD writer refuses triple terms, and it has no TriX, RDFa, HexTuples or
   pretty (nested `[ ]`, `( )`) Turtle output.

## 1. Formats

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| Parse Turtle | yes | yes | `parse-turtle` | none |
| Parse TriG | yes | yes | `parse-trig` | none |
| Parse N-Triples / N-Quads | yes | yes | `parse-nt`, `parse-nquads` | none |
| Parse RDF/XML | yes | yes | `parse-xml` | none |
| Parse JSON-LD | yes | yes | `parse-json-ld` (one small document with `@vocab`; not the JSON-LD test suite) | JSON-LD conformance of either: **unverified** |
| Parse N3 | yes | yes (syntax; parsed as triples, formulae/rules not checked) | `parse-n3` | N3 rules and formulae: **unverified** |
| Parse TriX | yes | **no** (no `RdfFormat` member) | `parse-trix` | low; TriX is rare |
| Parse RDFa | **no** (no plugin in 7.6.0 here) | **no** | `parse-rdfa` | none gained or lost |
| Parse Manchester syntax | **no** (no parser plugin) | **no** | `parse-manchester` | none; StarLayer's own Manchester code is separate |
| Serialize Turtle, TriG, N-Triples, N-Quads, RDF/XML, JSON-LD, N3 | yes | yes | `serialize-*` | none |
| Serialize TriX, HexTuples, LongTurtle | yes | **no** | `serialize-trix`, `serialize-longturtle/hext` | `longturtle` and `hext` are used only if StarLayer exposes them (**unverified** whether it does) |
| Pretty Turtle (nested `[ ]`, `( )` lists, grouped subjects) | yes | **no**: streaming serializer, flat statements | `turtle-pretty (nested [ ] / lists)`, `rdflib:turtle-pretty` | cosmetic, but visible in notebooks and golden files |
| Round trip fidelity (isomorphic after serialize and parse) of a mixed document (plain, lang, integer, date, escapes, IRI) | yes for Turtle, N-Triples, RDF/XML, JSON-LD, N3, TriX (TriX via Dataset) | yes for Turtle, N-Triples, RDF/XML, JSON-LD, N3 | `roundtrip-*` | none |
| Round trip of *lexical forms* | yes only with `rdflib.NORMALIZE_LITERALS=False`; default changes `04`, `1`(boolean), `1E0`, dateTime offsets | parser keeps them; **the store does not** (section 2) | `lexical-preserved-*` | see section 2 |
| RDF 1.2 Turtle: `<<( s p o )>>` triple term | **no** (BadSyntax) | yes | `rdf12-triple-term` | rdflib route needs `parse12` |
| RDF 1.2 annotation `{| |}` | **no** | yes | `rdf12-annotation` | same |
| RDF 1.2 reifier `~ :r` | **no** | yes | `rdf12-reifier-tilde` | same |
| `VERSION "1.2"` and `@version` directives | **no** | yes | `rdf12-version-directive*` | same |
| Base-direction literal `"hi"@en--ltr` | **no** | yes | `rdf12-dir-literal` | same |
| RDF-star `<< s p o >>` (old syntax) | **no** | yes (becomes a reifier blank node plus `rdf:reifies`) | `rdf12-reified-triple-star` | same |
| RDF 1.2 in TriG and N-Triples | no | yes (both) | `rdf12-trig-triple-term`, `rdf12-ntriples-triple-term` | same |
| Serialize triple terms | n/a | Turtle, TriG, N-Triples, RDF/XML yes; **JSON-LD no** (`OSError: JSON-LD does not support RDF 1.2 yet`) | `serialize-rdf12-*`, `serialize-triple-term-jsonld` | JSON-LD export of 1.2 data must keep StarLayer's own writer or fail |
| Serialize `"x"@en--ltr` | n/a | yes, round trips | `serialize-rdf12-dir-literal-*` | none |
| Stream parse (`ox.parse` yields Quads; `rename_blank_nodes`, `lenient`, `without_named_graphs`) | partial (no flags of these kinds) | yes | `parse-rename_blank_nodes`; signature in docstring | `lenient=True` skips IRI validation: faster, can ingest bad IRIs |

## 2. Data model

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| RDF 1.2 triple terms as terms | **no** node class | yes (`Triple` is a term in subject/object position, hashable) | `triple-term-in-Graph`, `Triple-as-term`, `terms-hashable` | StarLayer's `tt:` content-addressed encoding exists only because of the rdflib column |
| `rdf:dirLangString` / base direction | **no** (`Literal(lang='en--ltr')` raises `ValueError`) | yes (`Literal(language=, direction=BaseDirection.LTR)`, datatype `rdf:dirLangString`) | `dirLangString-literal` | `DirLangString` class and `dirlang:` datatype encoding are rdflib-only workarounds |
| Literal lexical form kept on store | partial: normalizes on `Literal()` construction by default (`04`^^integer -> `4`, `1`^^boolean -> `true`, `1E0` -> `1.0`, `INF` -> `inf`, dateTime `Z` -> `+00:00`, `0001`^^positiveInteger -> `1`); **kept** if `NORMALIZE_LITERALS=False`; ill-formed `abc`^^integer kept | **no**: `04`->`4`, `1`^^boolean->`true`, `300`^^byte -> **retyped** `xsd:integer`, `+1.50`->`1.5`, `1E0`->`1`, `0001`^^positiveInteger -> `1`^^**integer**. Parser alone keeps all of them; the store rewrites. `STR()` and `dump()` return the rewritten form. No switch. | `lexical-preserved-default`, `lexical-preserved-NORMALIZE_LITERALS=False`, `lexical-preserved-parser`, `lexical-preserved-store`, `lexical-preserved-store-add()`, `STR()-of-stored-"04"^^integer`, `dump-keeps-original-lexical`; upstream [oxigraph#526](https://github.com/oxigraph/oxigraph/issues/526) | Re-verifies the finding in `shacl-engine-feasibility.md` and **refines it**: `StarLayerGraph()` on the default store also returns `4` for `"04"^^xsd:integer` (checked), because StarLayer never sets `NORMALIZE_LITERALS=False`. So the 7 Oxigraph xfails are not "Oxigraph versus a faithful default"; the default store loses the same forms. Only an rdflib store with that flag preserves them |
| Retyping of derived integer types | no | yes: `xsd:byte` etc. become `xsd:integer` (datatype changes, not just lexical form) | `lexical-preserved-store` | SHACL `sh:datatype xsd:byte` cannot hold; rdflib does not do this |
| Blank-node scope across documents | yes (2 parses, 2 nodes) | yes (2 `load()`s, 2 nodes; `parse()` keeps file labels, `rename_blank_nodes=True` renames) | `bnode-scope-two-parses-distinct`, `bnode-scope-two-loads-distinct`, `bnode-label-same-across-parse()`, `parse-rename_blank_nodes` | none |
| Blank-node scope across two `INSERT DATA` requests with the same label | **no** (one node, 1 triple) | yes (two nodes) | `bnode-scope-two-INSERT-DATA-distinct` (both libs) | StarLayer's `parse12._fresh_blank_nodes_in_insert_data` fixes this for rdflib; Oxigraph needs nothing |
| User-chosen blank-node id kept | yes | yes | `BlankNode(id)-stored-as-given` | none |
| Language tag case | keeps `EN-us`; equality case-insensitive | **lowercases on construction and storage** (`en-us`); `LANG()` returns lowercase | `langtag-case-kept`, `langtag-case-stored`, `functions-agree...` (`LANG("a"@EN-us)`) | documented difference confirmed; SPARQL W3C tests that echo tag case differ |
| `"x"` versus `"x"^^xsd:string` | **different terms** (`==` False) | same term | `plain-eq-xsd-string` | confirms `starlayergraph_vs_rdflib` note; Oxigraph matches RDF 1.1/1.2 Concepts |
| Term equality versus value equality | `Literal.__eq__` term-based after normalization; `.eq()` value | term equality in Python is lexical; value equality is SPARQL `=` | `literal-eq-by-value`, `literal-eq-term-identity` | none |
| `sameTerm("1"^^xsd:integer, "01"^^xsd:integer)` | false | **true**: the SPARQL parser normalizes literal constants too | `functions-agree-rdflib-vs-ox` (difference list) | a query cannot distinguish two lexical forms even if they were stored |

## 3. Store API

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| Named graphs / dataset | yes (`Dataset`) | yes (quad store) | `named-graphs-quads`, `dataset-named-graphs` | none |
| Wildcard pattern match | yes (`triples`, `triples_choices`, property paths) | yes (`quads_for_pattern`, `None` = wildcard, `DefaultGraph()` = default only); no `triples_choices` | `quads_for_pattern-wildcards`, `triples-wildcard-and-choices` | `triples_choices` must be emulated (oxrdflib already does) |
| `default_union` | yes (`Dataset(default_union=True)`) | yes as a query option: `use_default_graph_as_union`, `default_graph=[...]`, `named_graphs=[...]`; **not** for `Store.update` | `default_union`; StarLayer doc line on update with `default_union` | known, already handled in `native_oxigraph.py` |
| Removal, counts, `clear`, `remove_graph` | yes | yes | `remove-count`, `remove_graph/clear_graph`, `clear` | none |
| Transactions | no (Memory store is not transaction aware) | partial: **no** `Store.transaction`; each `update()` is atomic (rolled back on syntax error and on runtime error, verified); "repeatable read" snapshot per read | `explicit-transactions`, `update-is-atomic-on-*`, `rdflib:transactions` | single SPARQL UPDATE as the unit of atomicity; multi-statement Python-level transactions: **no** |
| On-disk persistence | partial: no persistent store bundled in 7.6.0 here (installed store plugins: Auditable, Concurrent, Memory, SimpleMemory, SPARQLStore, SPARQLUpdateStore, Oxigraph); BerkeleyDB / SQLAlchemy are separate packages, **unverified** | yes (RocksDB, `Store(path)`; reopen verified, `backup`, `optimize`, `flush`) | `persistence-rocksdb-reopen`, `backup/optimize/flush`, `persistence-stock` | a real on-disk option rdflib lacks |
| Multi-process access | n/a | one writer per path (second opener refused: `OSError ... lock`); `Store.read_only(path)` opened while the writer was open and read data, docs call that undefined behaviour | `second-writer-on-same-path-refused`, `read_only-opened-while-writer-open` | a server in front is needed for several writer processes |
| Threads | pure-Python, GIL-bound: 2 threads no faster than 1 (3.70 s vs 3.54 s) | concurrent readers and writers worked without errors; query work parallelizes (4 queries 0.06 s sequential vs 0.03 s threaded) | `threads-concurrent-read-write`, `GIL-released-in-query`, `GIL-bound-in-query` | gain for the workbench / server use |
| Bulk load | `Graph.parse` | `Store.bulk_load` / `load` / `bulk_extend` | section 7 | 15 to 20 times faster loads |
| Query timeout | no | no (`TypeError: unexpected keyword 'timeout'`) | `query-timeout-param` | StarLayer has its own timeout code (class D in the inventory); applies to both |

## 4. SPARQL

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| SPARQL 1.1 Query: property paths (`+`, `/`, `^`, `\|`, `!()`), aggregates, subqueries, VALUES, MINUS, EXISTS, OPTIONAL, GRAPH, FROM | yes | yes; identical rows on every case in `sparql_core` | `path-plus`, `path-inverse-alt-neg`, `aggregates`, `subquery+VALUES+BIND`, `MINUS-EXISTS-OPTIONAL`, `GRAPH-named`, `FROM-NAMED-dataset` | none |
| Built-in functions agree | reference | 34 of 40 expressions identical. Differences: `1/3` (rdflib 23 digits, ox 18), `STR(1.0e0)` (`1.0` vs `1`), `LANG("a"@EN-us)` (case), `xsd:dateTime("2020-01-01")` (rdflib no row, ox unbound), `str(1e0)`, `sameTerm` on `01` / `1` | `functions-agree-rdflib-vs-ox` | StarLayer's `builtin_error_patches.py` targets rdflib; the Oxigraph engine does not need those but results differ in digits and tag case |
| SPARQL 1.2 `VERSION` declaration | **no** (ParseException) | yes | `sparql-VERSION-declaration` | rdflib route uses StarLayer's `parse12` |
| `isTRIPLE`, `TRIPLE()`, `SUBJECT`, `PREDICATE`, `OBJECT` | **no** | yes (all verified with data) | `sparql-isTRIPLE`, `-TRIPLE()`, `-SUBJECT/PREDICATE/OBJECT` | same |
| Triple-term patterns `<<( ?s ?p ?o )>>`, `VALUES` with a triple term, `<< >>` reified pattern | **no** | yes | `sparql-triple-term-pattern`, `-VALUES-with-triple-term`, `-reified-triple-star-pattern` | same |
| `hasLANG`, `hasLANGDIR`, `LANGDIR`, `STRLANGDIR`, `STR` / `DATATYPE` / `CONCAT` / `SUBSTR` on dirLangString | `LANGMATCHES` yes; the rest **no** | yes; `CONCAT` and `SUBSTR` keep the direction | `sparql-hasLANG`, `-hasLANGDIR`, `-LANGDIR`, `-STRLANGDIR`, `-CONCAT-keeps-dir`, `-SUBSTR-dirLangString` | same |
| Annotation syntax `{\| \|}` in UPDATE | **no** | yes | `sparql-annotation-syntax-in-update` | same |
| `=`, `!=`, `IN`, `<`, join, GROUP BY, DISTINCT, ORDER BY, MIN, MINUS, VALUES join on `dirLangString` | n/a | **yes, no abort in 0.5.13**, correct results (`"hi"@en--ltr` = `"hi"@EN--ltr` true, versus `--rtl` false) | `dirLangString-*` (16 subprocess runs), `dirLangString-eq-correct-results` | `backends/dirlang_equality.py` is no longer needed on 0.5.13; keep it for older pinned versions. The opt-in abort tests will now report "no longer aborts" |
| UPDATE: INSERT DATA, DELETE DATA, DELETE/INSERT WHERE, WITH, DELETE WHERE, ADD, COPY, MOVE, CLEAR, DROP, DROP SILENT, CLEAR ALL | yes except below | yes, all | `update-*` | none |
| UPDATE `CREATE GRAPH` | **no** (`Create not implemented!`) | yes | `update-CREATE` | stock rdflib gap; StarLayer text says "does not exist" errors are patched |
| UPDATE `INSERT DATA` of a default-graph triple on a `Dataset` | **fails** on stock 7.6.0 (`ValueError: not enough values to unpack`) | yes | `rdflib:update-INSERT-DATA` | StarLayer replaces `evalInsertData` (documented in the graph CLAUDE.md) |
| `LOAD <http://...>` | yes | yes | `update-LOAD-http` | none |
| `LOAD <file://...>` | yes | **no** (`OSError: invalid format`) | `update-LOAD-file-URL` | use `Store.load(path=...)` instead |
| `SERVICE` | yes (HTTP SPARQL JSON, tested against a local server) | yes (same test); no switch to disable it was found | `SERVICE-http`, `SERVICE-disabled-by-default?` | note security: query text can make the process fetch URLs in both |
| Custom scalar functions | yes (`register_custom_function`, global registry) | yes, **per call**: `custom_functions={NamedNode: callable}` on `query` and `update`; terms in, term or `None` out | `custom-function` | StarLayer's `tt:fn/*` functions could be passed per call |
| Custom aggregate functions | no | yes (`custom_aggregate_functions`, class with `accumulate` / `finish`) | `custom-aggregate` | new capability |
| Pre-binding of variables | yes (`initBindings`) | yes (`substitutions={Variable: term}`, SEP-0007; the variable **must be in the SELECT projection** or `RuntimeError`) | `substitutions`, `initBindings` | `native.inject_init_bindings` (VALUES injection) could use it; check projection rule |
| Query timeout / cancel | no | no | `query-timeout-param` | unchanged |
| Result formats | JSON, XML, CSV, txt; **TSV missing** | JSON, XML, CSV, TSV; parse via `parse_query_results`; CONSTRUCT serializes through any `RdfFormat` | `results-serialize-*`, `results-parse`, `CONSTRUCT-serialize` | none |
| **Parsed algebra tree / EXPLAIN** | yes: `prepareQuery(q).algebra`, `parseQuery`, `translateQuery`, `pprintAlgebra`, `translateAlgebra` (back to text) | **no**: `QuerySolutions` has only `serialize` and `variables`; no `parse_query`, no `explain` / `with_stats` in `Store.query` | `algebra-access`, `explain-in-query-signature`, `rdflib:algebra-access`, `rdflib:translateQuery/pprintAlgebra` | **the main blocker**: `sqe`, `srl`, `spexpr` consume rdflib's algebra. They cannot run on pyoxigraph without a separate SPARQL parser (e.g. spargebra via a new binding, or keep rdflib for parsing and send text to Oxigraph) |
| Syntax errors | `ParseException` (pyparsing) | `SyntaxError` with position | `syntax-error-*` | none |

Other SPARQL features in the task list that were not run: query-time `LOAD ... INTO GRAPH`, `SERVICE` timeouts,
federation with authentication, full W3C SPARQL 1.1 suite on either library (StarLayer's own suites do that:
`docs/graph/*`, **unverified here**).

## 5. Python-level API

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| Namespace manager, `bind`, `qname`, `compute_qname`, `expand_curie` | yes | **no** (prefix dictionaries are passed per call: `serialize`, `dump`, `query`, `update`) | `namespace-manager` | with oxrdflib the rdflib `NamespaceManager` is kept in Python (`oxrdflib:namespace-manager` works; persistence of prefixes is not done by Oxigraph) |
| `Collection`, `Resource`, `value()`, `objects()`, `subjects()`, `items()`, `transitive_*` | yes | **no** (`quads_for_pattern` plus SPARQL paths) | `Collection-helper`, `Resource-helper`, `RDF-list/Resource-helper`, `Store-dunders` | all of `starlayer` code calling these needs a wrapper; oxrdflib gives them back through `Graph` |
| Lists in Turtle | parse and pretty-print | parse (as 5 triples for 2 items); no pretty-print | `list-handling-in-turtle`, `list-in-turtle-parse-only` | see section 1 |
| Set operations `+ - & ^` on graphs | yes | **no** on `Store`/`Dataset`; terms are hashable so Python `set`s of `Triple` / `Quad` work | `set-ops-+-&^`, `set-ops-via-python-set`, `Store-operators` | trivial to wrap |
| Graph isomorphism | yes: `rdflib.compare.isomorphic`, `graph_diff` | partial: `Dataset.canonicalize(RDFC_1_0 \| RDFC_1_0_SHA_256 \| RDFC_1_0_SHA_384 \| UNSTABLE)`, then compare sets; no diff helper | `isomorphic`, `canonicalize-for-isomorphism` | RDFC-1.0 is native, so StarLayer's own RDFC-1.0 code (class D) is redundant on Oxigraph |
| Skolemization | yes (`skolemize`, `de_skolemize`) | **no** | `skolemize` | StarLayer has its own skolemizer |
| `serialize(format=...)` | `Graph.serialize(destination, format, base, encoding)`: names, MIME types, plugin registry, returns `str` | `ox.serialize(triples, output, format, prefixes, base_iri)`: module function, `RdfFormat` required (no string names), returns `bytes`; `Store.dump(output, format, from_graph, prefixes, base_iri)` | `serialize(...)` rows, `serialize-turtle-with-prefixes` | adapter needed; oxrdflib already registers `ox-*` plugin names inside rdflib |
| oxrdflib as the bridge | n/a | `Graph(store='Oxigraph')` gives the whole rdflib API over Oxigraph, with rdflib's algebra for parsing but Oxigraph's engine for query/update (performance section) | `oxrdflib` column in section 7 | StarLayer's present route; keeps rdflib dependence |

## 6. Packaging

| Capability | rdflib | pyoxigraph | Evidence | Impact on StarLayer |
|---|---|---|---|---|
| Pure-Python install | yes (`py3-none-any`, 0.62 MB wheel; 3.8 MB installed) | **no**: native wheels only (5.1 to 9.5 MB each; 17.1 MB installed); the sdist needs a Rust toolchain | `rdflib:pure-python`, `ox:pure-python-install`, `local-installed-size-MB`, `pyoxigraph-wheels` (PyPI listing of 0.5.13, 32 wheels) | affects any environment without a published wheel |
| Platforms (0.5.13 wheels) | any | macOS x86_64 and arm64; manylinux_2_28 x86_64 and aarch64; musllinux_1_2 x86_64 and aarch64; Windows x86_64 and arm64; PyPy 3.11 on manylinux; CPython 3.9+ via one abi3 wheel, plus 3.11 to 3.15 and free-threaded builds | same | ARM is covered on all three OSes |
| Python versions | >=3.8.1 | >=3.9 | `requires-python` rows | none |
| Pyodide / WebAssembly | pure Python, installable by micropip (not tested here: **unverified**) | **no** emscripten wheel on PyPI for 0.5.13; **not bundled** in Pyodide 0.27.7's lock file | `pyoxigraph-has-emscripten-wheel`, `pyodide-0.27.7-bundles` | browser-only deployments cannot use pyoxigraph today (an npm `oxigraph` WASM package exists upstream: **unverified** here) |
| Dependencies | pyparsing, isodate (py3.10) | none | `oxrdflib:depends` shows oxrdflib needs `pyoxigraph~=0.5.0` and `rdflib>=6.3,<8.0` | none |

## 7. Performance

Generated data: 100,000 triples (25,000 subjects x type, name, integer value, knows). Single run on the same x86_64
Mac; seconds; lower is better. "oxrdflib" is rdflib's `Graph(store='Oxigraph')`. Parse-only and load are one row for
the two rdflib columns (no separate parse step). pyoxigraph "parse only" materializes a Python list of Quads.
Timings vary from run to run; use ratios.

| Operation | pyoxigraph | rdflib (Memory) | rdflib over oxrdflib |
|---|---:|---:|---:|
| Parse only, N-Triples | 0.222 | 4.646 | 8.026 |
| Load into store, N-Triples (`bulk_load`) | 0.348 | 4.646 | 8.026 |
| Load, `Store.load` (transactional) | 0.305 | 4.646 | 8.026 |
| Load into store, Turtle | 0.552 | 11.069 | 11.954 |
| Serialize N-Triples | 0.109 | 1.020 | 3.243 |
| Serialize Turtle | 0.157 | 10.337 | 16.567 |
| Point lookup x1000 | 0.003 | 0.016 | 0.029 |
| `COUNT(*)` | 0.030 | 2.238 | 0.050 |
| Join (type, knows, name) | 0.006 | 0.098 | 0.011 |
| `FILTER REGEX` | 0.018 | 2.548 | 0.029 |
| `GROUP BY` + `SUM` | 0.058 | 2.915 | 0.106 |
| Property path `+` from one node | 0.000 | 0.005 | 0.001 |
| Iterate all quads | 0.096 | 0.349 | 1.723 |

Reading it: queries through oxrdflib are as fast as native pyoxigraph (within 2 times) but **loading, serializing and
iterating through oxrdflib is slower than stock rdflib**. Peak memory was not measured here (`bench_inmemory_oxigraph.py` measures it: not
re-run).

## 8. What would be given up by making Oxigraph the baseline

Not given up (the Oxigraph column wins or ties): all SPARQL 1.1 forms tested, every UPDATE operation, `CREATE
GRAPH`, custom aggregates, RDF 1.2 syntax in Turtle, TriG, N-Triples and SPARQL (including `VERSION`, triple terms,
`dirLangString`), the `=` abort (fixed), the `xsd:string` equivalence, TSV results, persistence, threads, speed,
RDFC-1.0 canonicalization.

Given up, in order of consequence for StarLayer:

1. **rdflib's algebra tree** (`prepareQuery(...).algebra`, `translateAlgebra`). `sqe`, `srl`, `spexpr` depend on it.
2. **Control of literal lexical forms.** rdflib can be told to keep them; Oxigraph cannot, and rewrites datatypes
   (`xsd:byte` to `xsd:integer`). The default StarLayer store already loses them, so the loss is only relative to a
   store configured with `NORMALIZE_LITERALS=False`.
3. **The Python convenience API**: `NamespaceManager`, `Collection`, `Resource`, `value()`, graph set operators,
   `skolemize`, `graph_diff`, `Graph.serialize` with string formats and pretty Turtle.
4. **Formats**: TriX (both directions), HexTuples and LongTurtle output, JSON-LD output of RDF 1.2 triple terms.
5. **Pure-Python and browser deployment**: native wheels only, no Pyodide package.
6. **Language-tag case** (lowercased) and `sameTerm` on equal-valued, differently written numerals.
7. **`LOAD <file://>`** in UPDATE; per-call-only custom functions (no global registry).

Open points this run did not settle: JSON-LD and N3 conformance beyond one small document each; the StarLayer
SHACL/SRL suites on pure pyoxigraph (they ran through oxrdflib per existing docs); peak memory; Pyodide with micropip
for rdflib; whether pyoxigraph's SPARQL results match rdflib's on the W3C SPARQL 1.1 suite.
