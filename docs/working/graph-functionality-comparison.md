# StarLayerGraph and Oxigraph, compared by function: keep or drop

Branch `shacl-engine`, 2026-10-31. Sources: `graph-rdflib-compat-inventory.md` (what the graph package contains, with line counts) and
`oxigraph-capability-matrix.md` (what pyoxigraph 0.5.13 does, each row backed by a check in
`packages/starlayer/benchmarks-graph/oxigraph_capability_checks.py`). Line counts are the inventory's; they are file-level, so
"lines affected" is the size of the code that exists for that function, not a promise of what will be deleted.

Each row says what StarLayerGraph does, whether Oxigraph does it, and a recommendation. The rows fall into three groups:

- **Group 1, overlap.** Oxigraph already does it. Recommendation: use Oxigraph's and retire ours.
- **Group 2, rdflib legacy that Oxigraph did not carry.** Oxigraph chose not to provide it. Each row needs a decision: keep a
  small StarLayer version, or drop the function.
- **Group 3, StarLayer's own.** Oxigraph does not do it and is not likely to. Recommendation: keep.

"Verified" means the matrix ran a check. "Unverified" means it did not, and the row says what to run before relying on it.

## Group 1: Oxigraph already does it (use Oxigraph's, retire ours)

| # | Function | StarLayerGraph today | Oxigraph | Recommendation | Lines affected |
|---|---|---|---|---|---:|
| 1.1 | RDF 1.2 triple terms as terms | A `TripleTerm` class, stored in rdflib as a content-hash `tt:` IRI plus `rdf:PropositionForm` triples, and decoded again on the way out | Native `Triple` term in subject and object position, hashable (verified) | **Drop the `tt:` encoding.** Use Oxigraph's `Triple`. Keep a thin public name if the API should keep `TripleTerm`. | `model/encoding.py` 433; tt machinery in the graph classes 775 and dataset 105 |
| 1.2 | Base-direction strings, `rdf:dirLangString` | A `DirLangString` class and a `dirlang:` datatype encoding, because rdflib rejects `lang="en--ltr"` | Native: `Literal(language=, direction=)` (verified); `=` on dirLangString no longer aborts in 0.5.13 (verified) | **Drop `DirLangString`.** **Retire `backends/dirlang_equality.py`** and its guard; the upstream abort is fixed in 0.5.13. | `dirlang_equality.py` 296; `model/dirlangstring.py` 84 |
| 1.3 | RDF 1.2 syntax: Turtle, TriG, N-Triples, N-Quads, RDF/XML (triple terms, `{\| \|}`, `~` reifiers, `VERSION`, base direction) | Hand-written parsers and serializers | Native, and 10 to 20 times faster: N-Triples load 0.35 s against 4.6 s, Turtle 0.55 s against 11 s on 100k triples (verified) | **Replace.** Before deleting, run the W3C RDF 1.2 syntax tests against Oxigraph (unverified here; the matrix checked behaviour on examples, not the suite). Keep our parser only for what Oxigraph lacks (see 2.6, 2.7, 3.1). | parsers and serializers except Manchester: about 5,600 |
| 1.4 | SPARQL 1.2 execution: `VERSION`, `TRIPLE`, `SUBJECT`, `PREDICATE`, `OBJECT`, `isTRIPLE`, `hasLANG`, `LANGDIR`, `STRLANGDIR`, annotation syntax in UPDATE | Lowering of 1.2 queries to 1.1 plus custom functions registered in rdflib | Native (all verified) | **Retire the lowering for execution.** The parse side stays, for the front-end layers (see 3.2). | `query/custom_functions.py` 552; `query_cache.py` 172; `remote_decompose.py` 322; `version_directive.py` 133 |
| 1.5 | Fixes for bugs in rdflib's evaluator | 35 patch functions applied on `import starlayer.graph`; 41 numbered rdflib issues | Not applicable: Oxigraph runs its own engine | **Retire the evaluator-side patches.** Keep the parse-side ones while rdflib's parser is used (3.2). | evaluator-side about 2,440 (`evaluate_patches` 702, `builtin_error_patches` 879, `operator_patches` 424, `update_patches` 360, `result_patches` 76); the 617 lines of triple-term patching in `evaluate_patches` and `operator_patches` go with 1.1; parse-side 503 stay |
| 1.6 | All SPARQL UPDATE operations, `CREATE GRAPH`, default-graph `INSERT DATA` on a Dataset | Patched into rdflib (`update_patches`) | Native, all operations (verified) | **Drop** with 1.5 | included in 1.5 |
| 1.7 | RDFC-1.0 canonicalisation | `rdfc.py`, written from scratch, with triple terms and datasets | `Dataset.canonicalize(RDFC_1_0 …)` native (verified for plain RDF; **triple terms unverified**) | **Replace**, after checking triple terms | `rdfc.py` 410 |
| 1.8 | Graph isomorphism, `graph_diff` | `compare.py`, a triple-term-aware layer over rdflib's | Canonicalise both sides, compare as sets (verified); no diff helper | **Replace** with canonicalise plus set difference | `compare.py` 282 |
| 1.9 | Per-document blank-node scoping | `bnode_scope.py` (a context variable) and a fix for `INSERT DATA` reusing labels | Correct natively: two loads give two nodes, `rename_blank_nodes` exists, two `INSERT DATA` requests give two nodes (verified) | **Drop** | `parsers/bnode_scope.py` 44, plus the `INSERT DATA` fix in `parse12` |
| 1.10 | `"x"` and `"x"^^xsd:string` are one term | Special handling, documented as a difference from rdflib | One term, as RDF Concepts says (verified) | **Drop the special handling** | small |
| 1.11 | Pre-binding variables in a query | `native.inject_init_bindings` (VALUES injection) | `substitutions=` (verified). The variable must appear in the SELECT projection, or it raises. | **Replace**, and keep the projection rule in mind | small |
| 1.12 | Persistent storage | rdflib stores (Memory, SQLAlchemy, Berkeley DB, SPARQLStore) | RocksDB on disk, reopen verified; one writer per path | **Replace.** What this gives up is in 2.9. | n/a |
| 1.13 | Threads | GIL-bound: 2 threads no faster than 1 (3.70 s against 3.54 s) | Queries run in parallel; readers and writers worked together (verified) | **Gain** | n/a |
| 1.14 | Custom functions | Global registry in rdflib | Per call (`custom_functions=`); also custom aggregates (verified) | **Replace.** Per-call is a behaviour change: functions must be passed on each call. | in 1.4 |

Subtotal if all of Group 1 is retired: about 12,100 of the graph package's 23,100 lines (52%) are candidates, the sum of the
figures above: `tt:` family 1,313, triple-term patch share 617, evaluator patches 2,441, lowering and custom functions 1,179,
parsers and serializers 5,600, and `dirlang_equality`, `rdfc` and `compare` 988. It is a sum of file-level counts, not a
measured deletion.

## Group 2: rdflib legacy that Oxigraph did not carry (decide each)

Oxigraph never had these, and its API leaves them out on purpose or by omission. The question for each is whether StarLayer's
users, or the engine, need the function enough to keep a small version.

| # | Function | StarLayerGraph today | Oxigraph | Recommendation | Why |
|---|---|---|---|---|---|
| 2.1 | Namespace manager: `bind`, `qname`, `compute_qname`, `expand_curie`, the 29 default prefixes | Inherited from rdflib; `prefixes.py` works around its writers; you decided to keep the default bindings | None. Prefix maps are passed per call (`serialize`, `dump`, `query`, `update`). | **Keep a small StarLayer prefix map** (a dictionary plus `used_prefixes`), passed to Oxigraph on each call. Drop the rdflib `NamespaceManager` class itself. | Serialization and queries need prefixes; you already chose to keep the defaults. About 140 lines plus a few methods. |
| 2.2 | List and graph helpers: `value()`, `objects()`, `subjects()`, `predicate_objects()`, `items()`, `Collection`, `transitive_*` | Inherited | None (`quads_for_pattern` plus SPARQL paths) | **Keep a small set**: `objects`, `subjects`, `predicate_objects`, `value`, and a read-only list helper. **Drop** `Resource`, unless a user needs it. | The engine and SHACL code call these constantly; they are a few dozen lines over `quads_for_pattern`. Check usage of `Resource` first (unverified here). |
| 2.3 | Graph set operators `+ - & ^` | Inherited | None on `Store`; Python `set`s of `Quad` work | **Drop**, unless usage shows otherwise | Trivial to wrap if needed |
| 2.4 | Being an rdflib `Graph` / `Dataset` (`isinstance`, `store=`, any rdflib `Store`) | `StarLayerGraph(Graph)`, `StarLayerDataset(Dataset)`; 33 inherited methods recorded in `_rdflib_inherited_contract.py` | Not applicable | **Keep as a compatibility facade for a transition period**, and make new code use the Oxigraph-based API. Then retire. | 252 test files import rdflib and the SHACL, SPARQL and notebook code uses these types. A hard break is the biggest single cost (see the options in the plan). |
| 2.5 | rdflib's `Result` objects from `query`/`update` | Returned today; SHACL and SRL iterate them | `QuerySolutions`, `QueryBoolean`, `QueryTriples` | **Keep a thin `Result` adapter** during the transition | The consumers are ours |
| 2.6 | Pretty Turtle: nested `[ ]`, `( )` lists, grouped subjects, `longturtle` | `serializers/turtle12.py` | None: streaming serializer, flat statements | **Decision needed.** Cosmetic, but visible in notebooks and golden test files. Recommendation: keep our writer as an optional `pretty` format, and default to Oxigraph's for speed. | About 895 lines |
| 2.7 | TriX (read and write), HexTuples, LongTurtle output | TriX 1.2 in both directions | None | **Decision needed.** Recommendation: drop unless a user needs TriX; it is rare. | 324 lines for TriX |
| 2.8 | JSON-LD output of RDF 1.2 data | rdflib passes it through; **rdflib has no RDF 1.2 JSON-LD either** | Refuses triple terms | **No loss.** Neither does it. | n/a |
| 2.9 | rdflib stores: SQLAlchemy, Berkeley DB, SPARQLStore | Accepted via `store=` | Not available | **Decision needed, and a real give-up.** Recommendation: drop; RocksDB replaces persistence. | Check whether anyone uses the SQLAlchemy store. The repo has an optional extra for it. |
| 2.10 | Remote SPARQL engines (Fuseki, Oxigraph server over HTTP) | `native.py` 824 lines of HTTP client, `skolem_semantics.py` 166 | The server speaks HTTP; pyoxigraph is in-process | **Decision needed.** Recommendation: keep only if remote endpoints matter; otherwise drop. | 990 lines |
| 2.11 | Pure-Python install and browser (Pyodide) deployment | rdflib is pure Python | Native wheels only, no emscripten wheel (verified) | **A real give-up.** Decide whether browser-only use matters. | n/a |
| 2.12 | Language-tag case preserved; `sameTerm` distinguishes `"1"` and `"01"` | Preserved | Lowercased on construction and storage; the SPARQL parser normalizes numeric constants too (verified) | **A real give-up.** SPARQL W3C tests that echo the tag's case will differ. | Document it |
| 2.13 | `LOAD <file://…>` in UPDATE | Works | Fails | **Drop**; use `Store.load(path=…)` | n/a |
| 2.14 | Format selection by string name and MIME type | `parse(format="turtle12")`, rdflib's plugin names | `RdfFormat` members only | **Keep a thin name-to-`RdfFormat` map** | Small |
| 2.15 | Control of literal lexical forms | `NORMALIZE_LITERALS=False`, or the `turtle12` parser, keeps them. The default `turtle` parser and the `Literal` constructor normalize. | Parser keeps them, **the store rewrites on insert, with no switch** | **A real give-up**, and the biggest for SHACL. Upstream fix pending (issue #190). Bridge: the reifier sidecar and the warning. | See `shacl-engine-feasibility.md` |

## Group 3: StarLayer's own (keep)

Oxigraph does not provide these and is unlikely to.

| # | Function | Where | Recommendation | Lines |
|---|---|---|---|---:|
| 3.1 | OWL 2 Manchester syntax, parse and serialize | `parsers/manchester_parser.py`, `serializers/manchester.py` | **Keep** | 2,387 |
| 3.2 | The SPARQL front-end layers: `sqe`, `srl`, `spexpr`, `salg`, built on rdflib's parsed algebra (`CompValue` trees); the 1.2 grammar spliced into rdflib's; the algebra-to-text translator | `sparql/` (34 of 40 files import rdflib; 23 its parser, 15 its algebra) | **Keep, and decide separately what supplies the parser.** pyoxigraph has no algebra access and no explain (verified), so these layers cannot move to Oxigraph as written. See the options in the plan. | `sparql/` about 12,600 |
| 3.3 | Entailment and OWL reasoning: `infer()` (owlrl), OWL-DL via HermiT and rustdl, entailment regime API, query-time RDFS entailment | `graph/graph/`, `entailment_regimes.py`; `sparql/entailment_rdfs.py` | **Keep.** The algebra-rewriting entailment depends on 3.2. | about 885 in the class file plus the owl modules (570) |
| 3.4 | Shape derivation | `graph/graph/shape_derivation.py` | **Keep** | 576 |
| 3.5 | Imports resolution, concise bounded description, skolemisation, RDF 1.2 reifier helpers (`add_reification`, `reifiers`, `reifier_annotations`, `reified_triples`) | the class files | **Keep**, rewritten as thin helpers over `quads_for_pattern` | within D, about 2,777 |
| 3.6 | Conformance labels ("1.2", "1.2-basic", "1.1") | `model/conformance.py` | **Keep** | 138 |
| 3.7 | Lexical-form fidelity layer | new: reifier sidecar in a separate named graph, plus the warning | **Keep** (new) until upstream fixes the store | to write |
| 3.8 | Wall-clock timeout for reasoning | `_timeout.py` | **Keep** (neither library has a query timeout) | 193 |

## Where Oxigraph is ahead (gains, for completeness)

Speed (10 to 1000 times on every timed operation), parallel queries, RocksDB persistence, `CREATE GRAPH`, custom aggregate
functions, native RDFC-1.0, TSV results, no `=` abort on dirLangString (in 0.5.13), RDF 1.2 syntax and SPARQL without any
lowering.

## Decisions I need from you

1. **Keep or drop** (Group 2): pretty-Turtle writer (2.6), TriX (2.7), rdflib stores such as SQLAlchemy (2.9), remote HTTP
   engines (2.10), `Resource` and graph operators (2.2, 2.3).
2. **Accept** the real give-ups: browser/Pyodide deployment (2.11), language-tag case (2.12), `LOAD <file://>` (2.13), and
   store-level lexical forms until #190 is fixed (2.15).
3. **The front end for SPARQL (3.2).** Keep rdflib as the SPARQL parser dependency, or write a parser. That choice decides
   whether rdflib stays in the dependency list.
4. **Transition.** Whether `StarLayerGraph(Graph)` stays as a compatibility facade for a period (2.4).

## Unverified, to run before deleting

W3C RDF 1.2 syntax tests against Oxigraph's parsers (1.3); RDFC-1.0 with triple terms (1.7); who uses `Resource`, graph set
operators and the SQLAlchemy store (2.2, 2.3, 2.9); JSON-LD and N3 conformance beyond one example each.

---

## Decisions recorded (2026-10-31)

| Row | Decision |
|---|---|
| 1.7 RDFC-1.0 with triple terms | **Maintain.** See "RDFC with triple terms" below for what the specs say and the plan. |
| 2.1 Prefix map | **Drop the prefix manager and the 29 default bindings** (reverses the earlier decision to keep rdflib's defaults). Oxigraph ships with no prefixes: `Store` has no prefix API, `dump()` without prefixes writes full IRIs, SPARQL with an undeclared prefix is a syntax error. Prefixes are passed per call. The parser reports the prefixes a document declared (`parser.prefixes`, filled once the parse has run), so a document's own prefixes can be captured for round trips if wanted. Consequence to handle: serialized output in notebooks and golden files that relied on the default bindings will change. |
| 2.2 `Resource` | **Drop.** Not used by any code, test, notebook or tool (only a doc mention, our capability-check script, and one recorded inherited method). |
| 2.6 Pretty Turtle | **Keep.** `serializers/turtle12.py`, rebuilt over Oxigraph terms. |
| 2.9 rdflib stores (SQLAlchemy) | **Drop.** Remove the `sqlalchemy` extra and its tests at cut-over. |
| 2.10 HTTP engines | **Keep** (`native.py`, `skolem_semantics.py`, 990 lines). |
| 2.4 `StarLayerGraph` | **Keep, as a wrapper over pyoxigraph.** StarLayer capabilities are built on the object. Other functions may consume an Oxigraph store or dataset directly (the engine's graph view already does). Open sub-question: whether the wrapper subclasses rdflib's `Graph` during a transition or is a standalone class from the start. |
| 3.2 `sqe`, `spexpr`, `salg`, `srl` | Under exploration: `sparql-layers-exploration.md`. Working hypothesis from the owner: salg is ours and independent of rdflib; sqe and spexpr are what tie into rdflib's algebra and may be given up. To be tested. |
| Still open | TriX (2.7, kept for now: already written, independent of the store); graph set operators (2.3, drop unless used); the three give-ups: browser/Pyodide (2.11), language-tag case (2.12), `LOAD <file://>` (2.13). |

### RDFC with triple terms: what the specs say (read 2026-10-31)

- RDFC-1.0 (W3C Recommendation, 21 May 2024) does not mention triple terms or RDF 1.2. Its input is an RDF 1.1 dataset, and it says
  a future update will replace the RDF 1.1 references. No W3C text, erratum or working-group issue found specifies the
  canonicalisation of triple terms. (The editor's draft and sections 4.4.3 to 9 were only summarised, not read verbatim.)
- The only W3C-hosted rewriting is the **RDF 1.2 Interoperability** draft's "basic encoding" (non-normative; the page as fetched
  has no status line or date), not RDF 1.2 Concepts: for each triple term `tt`, mint a fresh blank node `b`, add
  `b rdf:type rdf:PropositionForm`, `b rdf:propositionFormSubject s`, `b rdf:propositionFormPredicate p`,
  `b rdf:propositionFormObject o`, and replace `tt` with `b`. It targets "RDF 1.2 Basic" (no triple terms), not RDF 1.1, it
  deliberately does not reuse `rdf:Statement/subject/predicate/object`, and it warns the output is not semantically equivalent to
  the input. For datasets, the fresh blank node must not appear in any graph of the dataset.
- Rewritings to a true RDF 1.1 form (`rdf:subject/predicate/object` "unstarring", or an `rdf:TripleTerm` with
  `rdf:tripleTermSubject/...`) exist only as proposals in w3c/rdf-star-wg issue #152 (open; consensus 2025-03-07 was to put it in the
  Primer or elsewhere). They are not spec text.
- **pyoxigraph's native RDFC-1.0** (tested 2026-10-31): canonicalising a dataset with a triple term ran; two isomorphic datasets that
  differ only in blank-node labels, including a blank node *inside* a triple term, gave identical canonical quads; a dataset
  differing in one literal gave a different result. So it is sound for isomorphism checks. No spec defines the canonical labels it
  assigns to triple terms, so its output cannot be assumed to match another implementation.
- **Plan (to confirm):** `isomorphic()` uses Oxigraph's native canonicalisation. A published canonical form or hash applies the
  Interoperability draft's basic encoding and then runs RDFC-1.0, so it rests on a documented rewriting and an actual standard;
  state in the API that the form is defined by that draft and may change with it. Test both against our current `rdfc.py`
  (410 lines) on its corpus before retiring it.
