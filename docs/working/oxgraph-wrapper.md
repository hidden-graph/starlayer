# The Oxigraph-backed graph wrapper (`OxGraph`, `OxDataset`)

Branch `mig-wrapper` (from `shacl-engine`), 2026-10-31. New files only: `packages/starlayer/starlayer/graph/oxgraph/` and
`packages/starlayer/tests/graph/oxgraph/`, plus `packages/starlayer/benchmarks-graph/bench_oxgraph_wrapper.py`. Nothing existing
was edited. The names are working names; at the switch they become `StarLayerGraph` and `StarLayerDataset`.
Decisions followed: `graph-oxigraph-migration-plan.md` sections 1 and 5.

## What it is

A composition wrapper over a `pyoxigraph.Store` (pyoxigraph classes cannot be subclassed). Terms are pyoxigraph terms
(`NamedNode`, `BlankNode`, `Literal`, `Triple`). It is not an rdflib `Graph`, and the package does not import rdflib at module level;
an rdflib or StarLayer term handed to `add` and friends is converted lazily through `shacl_engine.terms.to_engine`. The query path
reuses `graph/query/direct.py` (`_guard`) and `graph/backends/native.py` (`check_native_version_conformance`,
`inject_init_bindings`), imported lazily, because `direct.run_direct` itself returns rdflib terms and cannot choose a default graph.

- `OxGraph(store=None, path=None, identifier=None)`: a view of one graph of a store. `identifier=None` is the default graph.
  The extra keyword `prefixes=` shares a dict (used by `OxDataset.graph()`).
- `OxDataset(store=None, path=None, default_union=True)`: the whole store.
- `as_store(x)`: the `pyoxigraph.Store` behind a wrapper, an `OxigraphGraph` view or a bare store.
- `config.DEFAULT_PREFIXES` (empty), `set_default_prefixes(mapping)`, `config.new_prefix_dict()`.
- `Result`, `Row` (`result.py`), `reification` (functions), `formats.to_format`.

### Methods (both classes unless noted)

| Group | API |
|---|---|
| Write | `add(triple)`, `extend(triples)` (one transaction), `addN(quads)`, `remove(pattern)` (wildcards), `clear()` |
| Read | `__contains__`, `__len__`, `__iter__`, `triples(pattern)`, `quads(pattern)`, `objects`, `subjects`, `predicates`, `predicate_objects`, `subject_objects`, `subject_predicates` (all with `unique=`), `value(s, p, o, default, any)`, `items(head)` |
| Datasets | `graph(identifier)`, `graphs()`, `graph_names()`, `has_graph`, `remove_graph`, `clear`, `default_union` |
| I/O | `parse(source=, data=, file=, format=, base=)`, `serialize(destination=None, format=, base=, prefixes=, only_used=, rdf_version=)` |
| Prefixes | `prefixes` (plain dict), `bind`, `unbind`, `used_prefixes()` |
| SPARQL | `query(text, initNs, initBindings, base)` and `update(text, initNs, base)`, sent to Oxigraph as text |
| Operators | `+ - & ^` (`graph/setops.py`), `+=`, `copy()`, `__eq__` by identity |
| RDF 1.2 | `add_reification`, `reifiers`, `reifications`, `reifier_annotations`, `reified_triples` (methods and `reification.*` functions) |
| Engine | `engine_terms`, `preserves_lexical_forms = False`, `native_sparql`, `sparql_query`, `engine_view()` |

### Decisions made while building

- **Formats.** `turtle` is Turtle 1.2 and keeps lexical forms as the parser read them; `turtle12`, `ttl` are aliases. Also `trig`, `nt`,
  `nq`, `xml` / `rdf-xml`, `json-ld` (works for plain RDF), and `n3` (read and written as Turtle). `trix` and `longturtle` raise
  `ValueError`. MIME types and `nt12`, `trig12`, `nq12` are accepted.
- **Blank nodes** are renamed per parse (`rename_blank_nodes=True`), so two parses of one document give two sets of nodes, as the old
  class does. `rename_blank_nodes=False` merges them.
- **Parse is atomic.** A syntax error leaves the graph unchanged (one `Store.extend` transaction).
- **Quad formats into a graph view** raise `ValueError` if the document has named graphs; into a dataset each quad goes to its graph.
  A triple format goes to the default graph of a dataset.
- **Prefixes.** The global default is copied into each graph's own dict at build time; views from `OxDataset.graph()` share the dataset's
  dict. Parsers add the prefixes a document declares to the dict. The dict is passed to Oxigraph on every `serialize`, `query`,
  `update`; `initNs` / `prefixes=` override per call. `only_used=True` removes the `@prefix` lines the output does not use (Oxigraph writes
  every prefix it is given); `used_prefixes()` is read back from Oxigraph's own writer, so it cannot disagree with the output.
- **`OxDataset` is a union by default.** `triples`, `len`, `iter` and SPARQL's default graph are the union of all graphs (matching the
  engine's `OxigraphGraph` view); `default_union=False` gives rdflib's `Dataset` behaviour. A graph view queries its own graph as the
  default graph. `quads()` always shows graph names. `serialize` of a dataset with named graphs needs `trig` / `nq`.
- **`update` acts on the whole store**, also from a named-graph view; aim it with `WITH` / `GRAPH` in the text.
- **`Result`**: SELECT rows are `Row` tuples readable by name (`row["x"]`, `row.x`, `row.get`), `.vars` are `pyoxigraph.Variable`,
  `.bindings` are `{name: term}` dicts with `str` keys (rdflib uses `Variable` keys), `.askAnswer`, `.type`, CONSTRUCT / DESCRIBE iterate
  triples and `.graph` is an `OxGraph`. `.raw` is the one-shot pyoxigraph result (use it instead of, not after, the readers; it is how to get
  `serialize()` to JSON / CSV / TSV).
- **`initBindings`** uses Oxigraph `substitutions=`; when the variable is not projected, the existing `VALUES` injection is used.
- **RDF 1.1 export** (`serialize(rdf_version="1.1")`) calls `starlayer.graph.interop.to_rdf11(graph_or_store) -> Store | wrapper` if that
  module exists, else raises `NotImplementedError`. The contract is a guess until `interop.py` lands; adjust `core._to_rdf11`.
- **Engine.** `validate(OxDataset, OxDataset)` works with no change to the engine: the wrapper provides the `GraphView` methods,
  `engine_terms = True` (so no term conversion happens) and `sparql_query` (delegating to `OxigraphGraph`).
  `tests/graph/oxgraph/test_engine_adapter.py` runs the 138 W3C SHACL 1.2 core Validate entries through it, with `OxDataset` and with
  `OxGraph`: 268 passed, 8 expected failures (the same four Oxigraph-literal-normalization entries as `test_w3c_engine_core_oxigraph.py`,
  strict xfails, issue #190).

## Differences from the old `StarLayerGraph` (conformance)

`tests/graph/oxgraph/conformance.py` defines 26 scenarios run on both classes: add / remove / len / contains, triple patterns with
wildcards, literals through `add` and through a Turtle parse, parse and serialize round trips (turtle, nt, rdf/xml, json-ld, n3, trig,
nquads), blank nodes across two parses (nt and turtle), SELECT / ASK / CONSTRUCT / DESCRIBE, `initBindings` and `initNs`, numeric
formatting, `sameTerm` on numeric constants, SPARQL 1.2 triple terms, all update operations (INSERT DATA, INSERT/DELETE, DELETE WHERE,
CREATE, COPY, ADD, MOVE, CLEAR, DROP), named-graph management, set operators, error types, prefixes, base resolution and language tags.
`test_conformance.py` requires the unlisted scenarios to agree exactly, and each listed one to still differ (so a stale entry fails).

Identical on both: add / remove / len / contains, all triple patterns, parse/serialize round trips in every format above, blank-node
scoping across parses, SELECT / ASK / CONSTRUCT / DESCRIBE results, `initBindings` / `initNs`, SPARQL 1.2 triple terms, every update
operation (INSERT DATA, INSERT/DELETE WHERE, CREATE, COPY, ADD, MOVE, CLEAR, DROP, CLEAR DEFAULT), named graphs, set operators,
base resolution.

| # | Difference | Old | New | Verdict |
|---|---|---|---|---|
| 1 | Language-tag case | `"x"@EN-us` kept; `LANG()` gives `en-US` | lowercased: `en-us` | accepted give-up (plan 5.2) |
| 2 | Lexical forms after storing | decimal `1.0` and double `1e0` kept as `1.0` / `1.0` (rdflib's own canonical form) | store rewrites on insert: `1` and `1` (the parser keeps them; the store does not, issue #190) | accepted give-up until upstream PR #2010 |
| 3 | Numeric formatting in SPARQL results | `1/3` is 28 digits, `xsd:decimal(3)` is `3.0`, `1e0*2` is `2.0` | 18 digits, `3`, `2` | accepted give-up |
| 4 | Integer constants beyond i64 | `xsd:double(100000000000000000000)` works (`1e+20`) | unbound (error in Oxigraph) | accepted give-up (Python ints are unbounded; Oxigraph's are i64) |
| 5 | `sameTerm("1"^^xsd:integer, "01"^^xsd:integer)` | false | true (Oxigraph's SPARQL parser normalises numeric constants) | accepted give-up (plan 4) |
| 6 | Error types | `BadSyntax`, `ParseException`, `PluginException`, `ValueError` for a literal subject | `SyntaxError` (with position), `ValueError` (unknown format), `TypeError` for a literal subject or predicate | accepted give-up (plan 4) |
| 7 | `SELECT *` column order | the order comes from a Python set (varies with the hash seed) | alphabetical, always | accepted give-up (plan 4); an improvement in determinism |
| 8 | Fresh graph prefixes | 29 default bindings | none (global `DEFAULT_PREFIXES`, empty) | accepted give-up (decision 2.1) |
| 9 | Dataset default graph in a query, `triples()` | default graph only | union of all graphs (`default_union=True`); `False` agrees | accepted, by design; the flag keeps both |

No scenario ended as a **bug** in the wrapper. Differences seen while testing but outside the scenario set, all by design:
`update()` from a named-graph view acts on the whole store; `Result.bindings` has `str` keys; `len(OxDataset)` counts distinct triples of
the union, not quads (`len(ds.store)` counts quads); `serialize(destination)` returns `None` where rdflib returns the graph; `__eq__` is
identity (rdflib compares graph identifiers); `+=` is built, `-=`, `&=`, `^=` are not.

## Persistence

`OxDataset(path=...)` / `OxGraph(path=...)` open a RocksDB store (one writer per path: drop the first object before reopening).
`tests/graph/oxgraph/test_persistence.py` writes a parse, a named-graph parse and an `INSERT DATA`, flushes, reopens, and compares all
quads, then clears a graph, reopens as an `OxGraph` and checks the default graph.

## Benchmark

`benchmarks-graph/bench_oxgraph_wrapper.py` (100,000 triples; median of 3 runs; seconds). One run on the development machine (macOS, Python 3.10, pyoxigraph 0.5.13), in seconds:

| Operation | `StarLayerGraph` | `OxGraph` | bare `Store` | old / wrapper |
|---|---:|---:|---:|---:|
| load 100,000 triples, N-Triples text | 25.1 | 2.22 | 1.56 | 11x |
| 20,000 `add` calls | 3.20 | 1.91 | 0.78 | 1.7x |
| join, `COUNT(*)` | 11.33 | 0.75 | 0.59 | 15x |
| `GROUP BY` | 2.04 | 0.072 | 0.049 | 28x |
| point query | 0.0163 | 0.0002 | 0.0001 | 82x |
| iterate all triples | 3.15 | 0.88 | 0.46 | 3.6x |
| 1,000 pattern lookups | 0.257 | 0.162 | 0.038 | 1.6x |

The wrapper costs 1.1 to 1.5 times the bare store on queries and about 2x on load, `add` and iteration. The load gap is `Store.extend`
(transactional, so a syntax error leaves the graph unchanged) against `Store.load` (the bulk path); `add` and iteration pay for building
a `Quad` / tuple in Python. Not tuned further.

## StarLayer helpers (branch `mig-helpers`)

Code in `oxgraph/helpers/` (`entailment.py`, `shapes.py`, `imports.py`, `rewrite.py`, `qnames.py`); `core.py` has one-line delegating
methods on `OxGraph` and `OxDataset`. Tests: `tests/graph/oxgraph/test_helpers_conformance.py` (198 cases, old `StarLayerGraph` against
`OxGraph`, triple sets compared up to blank-node isomorphism with `rdfc_native.isomorphic`, inputs taken from `test_infer.py`,
`test_resolve_imports.py`, `test_shape_derivation.py`, `test_dataset.py`, `test_leftovers_72_75_83.py`).

| Capability | How | Conformance |
|---|---|---|
| `infer(entailment, mode, target_graph, engine, timeout)` | RDF regime native on pyoxigraph terms; RDFS, OWL-RL and RDFS+OWL-RL through owlrl on an rdflib copy (`_rdflib_bridge.py`, the one module that converts), run to a fixpoint as before, delta converted back, generalized triples dropped. `ENTAILMENT` constants as `NamedNode`s (`str` and `NamedNode` accepted as regimes). OWL-Direct calls the old `owl_dl.classify_owl_dl` / `owl_dl_rustdl.classify_owl_dl_rustdl` on the rdflib copy: same optional-dependency errors and the same subprocess timeout wrapper | 9 data sets x 6 regime sets x full/delta, in-place, 8 error cases, constants, default timeout: all agree |
| `derive_shape` | stage-1 bridge: data and template copied to a `StarLayerGraph`, the old `shape_derivation.derive_shape` runs, the shapes graph is copied into a new `OxGraph` | 6 fresh, 5 template, ignored-property options: all agree |
| `owl_imports`, `has_import_locally`, `resolve_imports`, `can_resolve_import` | native; the loader may return a wrapper or an old graph | 7 registries x 3 modes (same loader calls in the same order), error cases: all agree |
| `skolemize`, `de_skolemize` | native, rdflib's skolem IRI scheme, triple terms rewritten consistently | exact equality of triple sets with same blank-node ids (with and without triple terms), `bnode=`, `authority=`, `basepath=`, round trip |
| `cbd` | native, rdflib's algorithm (statements, blank-node closure, `rdf:subject`-style reifications); dataset honours `default_union` | 5 resources x with/without reifications, triple term, target graph, dataset union |
| `empty_like` | new empty in-memory graph (dataset: dataset with same `default_union`), prefixes copied | agree |
| `qname`, `compute_qname`, `expand_curie` | over the graph's prefix dict, longest namespace wins, `ns1`... generated | agree on the cases rdflib accepts |

Differences found and verdicts:

| # | Difference | Verdict |
|---|---|---|
| H1 | `infer` on an inconsistent graph with owlrl: the old class itself gives 127 or 128 triples depending on the hash seed (number of `err:ErrorMessage` nodes). The test compares the blank-node-free triples and requires an error message on both sides | owlrl nondeterminism, not a wrapper difference |
| H2 | `de_skolemize(uriref=...)`: old restores nothing (rdflib compares a `Genid` with a plain `URIRef` as unequal); new restores just that IRI | accepted; old behaviour was a quirk |
| H3 | `de_skolemize` of a foreign `/.well-known/genid/` IRI: old memoises the fresh blank node in a process-global dict, new once per call | accepted give-up (no global state) |
| H4 | `target_graph` / `new_graph` must be an `OxGraph` / `OxDataset` (`TypeError` otherwise) | by design |
| H5 | `empty_like()` has no identifier link to the source and is always in-memory (old: "like its source"; native Oxigraph, SQLAlchemy and remote stores were the cases) | accepted give-up |
| H6 | `cbd` / `skolemize` / `de_skolemize` on an `OxDataset` return an `OxGraph` (as old); `infer` / `resolve_imports(mode="delta")` on a dataset return a dataset (old datasets had no `infer`) | by design |
| H7 | `qname` is regex-based, not rdflib's `split_uri`; a local name containing `/` is a `ValueError`, rdflib raises as well | accepted |

No difference ended as a bug. Not exercised because the packages are absent on the development machine: HermiT (`owlready2`, Java) and
`rustdl`. The tests check the identical `RuntimeError` text when missing and that the timeout is passed through to the old classifier
(monkeypatched); a run with both installed compares the closures isomorphically (`test_owl_direct_hermit_same_outcome_as_old`,
`test_owl_direct_rustdl_same_outcome_as_old`), untested here.

## NOT built (follow-ups, with where the old code lives)

| Feature | Old code | Notes |
|---|---|---|
| Native `derive_shape` | `graph/graph/shape_derivation.py` | today a bridge to rdflib terms; a native port over pyoxigraph terms replaces `helpers/shapes.py` only |
| Native OWL-RL / RDFS rules | owlrl | today owlrl on an rdflib copy; the OWL-DL engines are the old modules, reused |
| Entailment-aware `query(entailment=...)` | `sparql/entailment_rdfs.py`, rewriting the rdflib algebra; `query` here raises `NotImplementedError` | waits for the sqe-tree port (plan stage 2) |
| Manchester syntax | `parsers/manchester_parser.py`, `serializers/manchester.py` | independent of the store; add `format="manchester"` that parses to a temp graph |
| Pretty Turtle (nested `[ ]`, `( )`, grouped subjects) | `serializers/turtle12.py` | another agent (`oxgraph/pretty.py`) |
| RDF 1.1 export | the other agent's `graph/interop.py` | hook in place (`core._to_rdf11`); contract assumed |
| Others | `isomorphic()` / `compare.py`, `rdfc.py` (RDFC), `triple_terms()`, `Collection`, `transitive_*`, `qname_term`, `namespaces()`, `dump`-style helpers, `Result.serialize` to JSON/CSV, custom functions per call, `LOAD` in UPDATE, remote HTTP engines (`backends/native.py`) | `Dataset.canonicalize` exists in pyoxigraph for RDFC |

## Open points

- The `interop` hook name and signature.
- `parse(source=URL)` uses `urllib` without content negotiation beyond an `Accept` header; format is guessed from the URL extension.
- Query-time `FILTER EXISTS` slowness (plan section 2.2) applies to this wrapper unchanged.
