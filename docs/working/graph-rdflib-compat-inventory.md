# Inventory of the rdflib-compatibility code in `starlayer.graph`

Branch `shacl-engine`, rdflib 7.6.0 (the version the patch docs were written against). Facts and numbers only; no recommendation. Paths are relative to `packages/starlayer/starlayer/` unless they start with `docs/` or `tests/`. Pyoxigraph behaviour is NOT re-measured here (pyoxigraph is not installed in this checkout); see `docs/working/oxigraph-capability-matrix.md` (being produced separately, empirical) for what pyoxigraph really does. Claims about pyoxigraph below are limited to what this repo's own code or docs already rely on, and are marked.

How the numbers were made: `wc -l` per file; `ast` for method spans in the two large files; `grep` for imports. Class A-E assignment is per file, except `graph/graph/starlayer_graph.py`, `starlayer_dataset.py`, `query/evaluate_patches.py` and `query/operator_patches.py`, which are split by method range (so the split is approximate to a few lines, and some methods are mixed, flagged below).

Classes (as given in the task):
- A: RDF 1.2 features rdflib lacks (triple terms, dirLangString, `*12` parsers/serializers, Manchester, annotation syntax).
- B: workarounds for rdflib bugs.
- C: glue so `StarLayerGraph`/`StarLayerDataset` behave as rdflib `Graph`/`Dataset`.
- D: StarLayer features independent of rdflib.
- E: engine-specific (Oxigraph, plus the other "native" engine transport).

---

## 1. MAP

### 1.1 Headline totals (graph/ = 23,112 lines, 55 files)

| Class | Lines | Share | What it is |
|---|---:|---:|---|
| A  RDF 1.2 features rdflib lacks | 11,714 | 50.7% | parsers 5,686; serializers 2,301; model 769; 1.2 lowering/custom functions/etc. in query/ 1,796; compare.py 282; triple-term code inside the two graph classes 880 |
| B  rdflib bug workarounds | 2,944 | 12.7% | seven `query/*_patches.py` files (35 `patch_*` functions) |
| C  rdflib-compat glue | 3,280 | 14.2% | method bodies and wrappers of the two classes that mirror rdflib's API 2,349; `__init__` re-exports 240; inherited-contract snapshot 312; prefixes 136; SPARQL API wrappers 243 |
| D  StarLayer-specific, rdflib-independent | 2,777 | 12.0% | shape derivation, OWL-DL/RustDL, entailment/infer, resolve_imports, skolemise, cbd, RDFC-1.0, timeout |
| E  engine-specific | 1,890 | 8.2% | Oxigraph-only 431; native-engine transport 990 (HTTP SPARQL, Fuseki skolem rewrite); `_native_*` branches inside the two graph classes 469 |
| Unallocated | 507 | 2.2% | imports, class docstrings, constants in the two big graph files |
| Total | 23,112 | 100% | |

Caveats on the split:
- `StarLayerGraph.parse` (257 lines), `query` (421), `update` (80), `serialize` (93) and `print` (11) = 862 lines are counted in C but are mixed: each is an rdflib-signature method whose body mostly routes to the `*12` parsers, the 1.2-to-1.1 lowering, or the native engine (A and E in substance). If they were moved to A, C would be 2,418 and A 12,576.
- The `tt:` content-addressed encoding (`model/encoding.py` and the `_coerce_tt`/`_intern_tt`/`_restore` family) is counted in A because it exists only to carry triple terms in an rdflib store that has no such term. It is also the cause of part of the B-class patch files (see 1.4).
- "Native" (`backend="rdf-1.2"`) means the store is a SPARQL engine (in-process Oxigraph, or Oxigraph/Fuseki over HTTP). `backend="rdf-1.1"` (the default) means rdflib's in-memory store plus the `tt:` encoding (`graph/CLAUDE.md`, rule 1).

### 1.2 Per-file table

| Path | Lines | Class | Purpose |
|---|---:|---|---|
| `graph/graph/starlayer_graph.py` | 3,953 | mixed (1.3) | `class StarLayerGraph(Graph)` |
| `graph/graph/starlayer_dataset.py` | 1,226 | mixed (1.3) | `class StarLayerDataset(Dataset)` |
| `graph/graph/shape_derivation.py` | 576 | D | `derive_shape()` |
| `graph/graph/owl_dl_rustdl.py` | 335 | D | OWL-DL via rustdl |
| `graph/graph/_rdflib_inherited_contract.py` | 312 | C | recorded signatures of 33 inherited rdflib methods/properties; drift test |
| `graph/graph/owl_dl.py` | 237 | D | OWL 2 Direct Semantics via owlready2+HermiT |
| `graph/graph/_timeout.py` | 193 | D | wall-clock timeout for DL reasoning |
| `graph/graph/prefixes.py` | 136 | C | `used_prefixes()`; works around rdflib's ~29 default bindings in the writers; `unbind` |
| `graph/graph/entailment_regimes.py` | 52 | D | `ENTAILMENT` namespace of W3C regime IRIs |
| `graph/graph/__init__.py` | 4 | C | |
| `graph/__init__.py` | 236 | C | re-exports rdflib `BNode, Dataset, Graph, Literal, Namespace, URIRef, Variable, Collection, RDF/RDFS/XSD`; applies all patches at import |
| `graph/compare.py` | 282 | A | triple-term-aware `isomorphic()` etc. around `rdflib.compare` |
| `graph/rdfc.py` | 410 | D | RDFC-1.0 (W3C algorithm) with triple terms and datasets, written from scratch |
| `graph/model/triple.py` | 111 | A | `TripleTerm` |
| `graph/model/dirlangstring.py` | 84 | A | `DirLangString` (rdflib rejects `Literal(lang="en--rtl")`, so a custom type) |
| `graph/model/encoding.py` | 433 | A | `tt:` hash encoding, `rdf:PropositionForm` triples, numeric canonicalisation |
| `graph/model/conformance.py` | 138 | A | VERSION label ("1.2", "1.2-basic", "1.1") checking |
| `graph/parsers/turtle_parser.py`, `syntax.py`, `lexer.py` | 1,307; 847; 313 | A | hand-written Turtle 1.2 parser |
| `graph/parsers/trig12.py`, `ntriples12.py`, `trix12.py`, `rdfxml12.py` | 477; 376; 161; 358 | A | |
| `graph/parsers/manchester_parser.py` | 1,672 | A | OWL 2 Manchester (rdflib has no Manchester parser) |
| `graph/parsers/errors.py`, `bnode_scope.py` | 128; 44 | A | |
| `graph/serializers/turtle12.py` | 895 | A | Turtle/longturtle 1.2 writer |
| `graph/serializers/manchester.py` | 715 | A | |
| `graph/serializers/rdfxml12.py`, `trix12.py`, `ntriples12.py`, `trig12.py`, `_xml.py` | 203; 163; 168; 83; 49 | A | |
| `graph/query/evaluate_patches.py` | 1,266 | B 702 / A 564 | see 1.4 |
| `graph/query/builtin_error_patches.py` | 879 | B | |
| `graph/query/operator_patches.py` | 477 | B ~424 / A ~53 | |
| `graph/query/update_patches.py` | 360 | B | |
| `graph/query/algebra_translator_patches.py` | 344 | B | |
| `graph/query/path_patches.py` | 159 | B | |
| `graph/query/result_patches.py` | 76 | B | |
| `graph/query/custom_functions.py` | 552 | A | registers `TRIPLE`, `SUBJECT`, `PREDICATE`, `OBJECT`, `STRLANGDIR` etc. in rdflib's global function registry |
| `graph/query/remote_decompose.py` | 322 | A | runs lowered queries against a remote SPARQL 1.1 store |
| `graph/query/query_cache.py` | 172 | A | per-graph cache of the 1.2-to-1.1 lowering |
| `graph/query/sparql_api.py` | 220 | C | `parseQuery/parseUpdate/prepareQuery/prepareUpdate/processUpdate` with rdflib return types |
| `graph/query/version_directive.py` | 133 | A | SPARQL 1.2 `VERSION` prologue |
| `graph/query/__init__.py` | 23 | C | re-exports `CompValue` |
| `graph/backends/native.py` | 824 | E (native transport) | HTTP SPARQL JSON client; `engine_aborts_on_dirlang_equality`, `new_graph_like` |
| `graph/backends/dirlang_equality.py` | 296 | E (Oxigraph) | rewrites `=` over dirLangString (oxigraph#1982 abort) |
| `graph/backends/native_oxigraph.py` | 135 | E (Oxigraph) | in-process transport through `oxrdflib.OxigraphStore._inner` |
| `graph/backends/skolem_semantics.py` | 166 | E (Fuseki) | skolem-IRI rewrite so blank nodes behave across queries |

Subpackage subtotals: parsers 5,686 (11 files); serializers 2,301 (8); query 4,983 (13); graph 7,024 (10); backends 1,421 (5); model 769 (5); top level 928 (`__init__`, `compare`, `rdfc`). There is no `graph/store*` directory: stores are rdflib's own (memory, `oxrdflib.OxigraphStore`, SQLAlchemy, SPARQLStore) passed in by the caller; the only store-specific code is in `backends/` and `prefixes.py` (`unbind_prefix` reaches into rdflib's `_Memory__namespace` and oxrdflib's `_delete_from_prefix`).

There is no rdflib plugin registration in graph/: grep for `plugin.register` finds nothing. The `*12` format names are dispatched inside `StarLayerGraph.parse/serialize` and `StarLayerDataset.parse/serialize`, not through rdflib's plugin system. The only registry hook into rdflib is the global SPARQL custom-function registry (`query/custom_functions.py`, 552 lines).

### 1.3 The two class files, by method group

`starlayer_graph.py` (3,953 lines, 36 uses of `self._is_native`):

| Group | Lines | Methods |
|---|---:|---|
| A: triple-term machinery | 664 + 111 helper | `_coerce_tt*`, `_intern_tt`, `_restore`, `_is_encoding_triple`, `_adopt_basic_encoding`, `_build_registry_from_store`, `_discard_unreferenced_tt`, `_triples_tt_wildcard`, `add_reification`, `add_reifier_annotation`, `reifiers`, `reifications`, `reifier_annotations`, `reified_triples`, `triple_terms`, `has_triple_term`, `remove_reification`, `qname_term`; helpers `_UnionForQuery`, `_unfold_tt_encoding`, `_unfold_native_triple_terms` |
| C: rdflib API methods | 1,386 + 115 helper | `__init__`, `__reduce__`/`__setstate__`, `open/close`, `add`, `addN`, `remove`, `triples`, `triples_choices`, `__contains__`, `__len__`, `parse` (2010-2267), `query` (2267-2688), `update` (2688-2768), `serialize` (2768-2861), `print`, `isomorphic`, `unbind`, `used_prefixes`, `reduce_prefixes`, `from_rdflib` |
| D | 885 + 26 helper | `infer` (3408-3658), `_resolve_owlrl_semantics`, `_infer_*`, `_before_and_delta_for`, `owl_imports`, `has_import_locally`, `resolve_imports` (3704-3840), `derive_shape`, `skolemize`, `de_skolemize`, `cbd`, `empty_like` |
| E: `_native_*` | 466 | `_native_add`, `_native_add_many`, `_native_triples` (723-893), `_native_remove`, `_native_triples_choices`, `_native_len`, `_native_reifiers`, `_native_scoped`, `_native_skolem_node_exists` |
| Unallocated | 300 | imports, class docstring, constants |

`starlayer_dataset.py` (1,226 lines, 4 `_is_native` uses): C 848 (`get_context`, `contexts`, `quads`, `triples`, `add`, `remove`, `addN`, `parse` 528-667, `query` 915-978, `update` 1006-1100, `serialize` 1115-1226, `default_graph`, `default_context`, `remove_graph`, `to_graph`, `_build_raw_execution_graph`); A 105 (`reifiers`, `reifications`, `reifier_annotations`, `reified_triples`, `_restore_any`, `_is_encoding_triple`); D 63 (`cbd`, `skolemize`, `de_skolemize`); E 3; unallocated 207.

### 1.4 Class B in detail: the seven patch modules

All are applied on `import starlayer.graph` (`graph/__init__.py`), each idempotent via a sentinel attribute. `docs/upstream-issues/rdflib-upstream-issues.md` has 41 numbered entries (1 to 43; 3 and 4 withdrawn 2026-10-25, issue #54, numbers not reused). The doc states none are filed upstream.

| Module | Lines | `patch_*` functions | Doc entries it fixes (wholly or partly) |
|---|---:|---:|---|
| `evaluate_patches.py` | 1,266 | 11 | #5, #8, #9, #16, #17, #18, #19, #20, #21, #31, #33 |
| `builtin_error_patches.py` | 879 | 12 | #22, #23, #24, #25, #26, #27, #28, #29, #34, #35, #36, #37, #38 |
| `operator_patches.py` | 477 | 6 | #1, #7, #11, #12, #15 (`sameTerm` only), #20 (`isIRI`/`STR`), #30 |
| `update_patches.py` | 360 | 1 | #19, #31, #32 |
| `algebra_translator_patches.py` | 344 | 2 | #2, #43 |
| `path_patches.py` | 159 | 2 | #21, #39 |
| `result_patches.py` | 76 | 1 | #6 |
| Total | 3,561 | 35 | |

Entries fixed outside the patch files: #10 (`REPLACE` flags) in `query/custom_functions.py`; #13, #14 (grammar accepts invalid queries) in `sparql/_syntax_checks.py`; #40, #41, #42 (negative decimal, `\'` in strings, `PN_LOCAL_ESC`) in `sparql/_grammar12.py::_fix_rdflib_lexical_gaps`. By the doc's own "Fix:" lines: 36 of 41 entries are fixed in `graph/query/` (including #10), 5 (#13, #14, #40, #41, #42) in `sparql/`. The module docstrings also cite GitHub issues #76, #134, #135, #140 for fixes beyond the numbered entries. Count of entries per cause is not further split here.

Class A content inside the "patch" files (not rdflib bugs; they teach rdflib's evaluator about the `tt:` encoding, because rdflib predates triple terms):
- `evaluate_patches.py`: `patch_construct_skips_encoding_solutions` (466-554), the tt-hash equality block (619-805, includes `_decode_tt_hash`, `_tt_aware_eq`), `patch_order_by_tt_hash_term_kind` (816-933), `patch_negated_path_skips_encoding_triples` (995-1039), `patch_bgp_skips_encoding_triples` (1042-1154): about 564 lines.
- `operator_patches.py`: `patch_triple_terms_are_not_iris` and `_is_encoded_triple_term` (412-464): about 53 lines.
These matter only on the `rdf-1.1` backend; a native engine bypasses them.

Upstream-doc sizes: `docs/upstream-issues/rdflib-upstream-issues.md` 630 lines; `oxigraph-upstream-issues.md` 171 lines, with exactly 1 numbered issue (SPARQL `=` aborts the process on dirLangString, oxigraph/oxigraph#1982, filed) and 1 tracked limitation (literals are normalised when stored); `fuseki-upstream-issues.md` 148 lines.

### 1.5 Class A: what "RDF 1.2" support consists of

| Feature | Where | Lines | rdflib has it? |
|---|---|---:|---|
| Triple terms (`TripleTerm`, `<<( )>>`, reifiers, `rdf:reifies`, `{| |}` annotation, `~`) | model/triple.py, encoding.py, graph-class A group, parsers, serializers, `sparql/lower_rdf11.py` | spread | no |
| `rdf:dirLangString` / `"x"@en--ltr` | model/dirlangstring.py, parsers, `custom_functions.py` (`LANGDIR`, `hasLANGDIR`, `STRLANGDIR`), `builtin_error_patches.normalise_directional_language`, `backends/dirlang_equality.py` | 84 + parts | no |
| Turtle/TriG/N-Triples/N-Quads/RDF-XML/TriX 1.2 parsers and writers | parsers/*, serializers/* | 5,686 + 2,301 (includes Manchester) | rdflib has 1.1 versions of all but TriX 1.2, which follows Jena's convention (`packages/starlayer/docs/graph/starlayergraph_vs_rdflib.md`) |
| Manchester syntax | parsers/manchester_parser.py 1,672; serializers/manchester.py 715 | 2,387 | no |
| SPARQL 1.2 syntax (parse and lower to 1.1) | `sparql/parse12.py` 341, `_grammar12.py` 932, `lower_rdf11.py` 1,971 (sparql/ total 3,244); `graph/query/*` A files | 3,244 + 1,796 | no |
| RDFC-1.0 canonicalisation | rdfc.py (D), compare.py (A) | 410 + 282 | no (rdflib's `compare.py` is a different algorithm) |

JSON-LD is not RDF 1.2: `format="json-ld"` is passed to rdflib; `jsonld12` was removed (2026-10-02). RDF/XML parsing still calls rdflib's XML parser (`parsers/rdfxml12.py` does `import rdflib`).

---

## 2. DEPENDENCY DEPTH

### 2.1 Files importing rdflib (any `import rdflib` / `from rdflib ...`, including function-local)

| Package | .py files | Lines | Files importing rdflib | Lines in those files |
|---|---:|---:|---:|---:|
| `starlayer/graph` | 55 | 23,112 | 42 | 21,482 |
| `starlayer/sparql` | 40 | 12,646 | 34 | 12,249 |
| `starlayer/shacl` | 30 | 16,851 | 21 | 16,190 |
| `starlayer/shacl_engine` (new on this branch) | 34 | 6,568 | 24 | 5,626 |
| `starlayer/starontology` | 3 | 2,257 | 3 | 2,257 |
| `starlayer/conformance.py` | 1 | 157 | 1 | 157 |
| `tools/` (repo root; `tools/kg/codekg/*`) | 13 | 3,209 | 6 | 2,388 |
| `scripts/` (repo root) | 16 | 2,124 | 6 | 1,269 |
| Total | 192 | 66,924 | 143 | 61,618 |

Within `graph/`: parsers 8 of 11 files, serializers 6 of 8, query 13 of 13 (all 4,983 lines), backends 2 of 5, model 3 of 5, graph 7 of 10. In parsers/serializers the import is almost only the term classes (`Literal`, `URIRef`, `BNode`) and `rdflib.namespace` constants; the Turtle, TriG, N-Triples and Manchester parsers are hand-written and do not call rdflib's parsers. Exceptions: `parsers/rdfxml12.py` (`import rdflib`, uses rdflib's XML parser), `turtle_parser.py` (imports `Graph`), `serializers/trix12.py` and `ntriples12.py` (`DATASET_DEFAULT_GRAPH_ID`).

### 2.2 What is imported (count of files, by rdflib symbol or module; grep, includes function-local imports)

Files whose rdflib import line names the symbol:

| Symbol | graph/ | sparql/ | shacl/ | shacl_engine/ |
|---|---:|---:|---:|---:|
| `URIRef` | 36 | 17 | 17 | 22 |
| `Literal` | 32 | 19 | 14 | 14 |
| `BNode` | 25 | 18 | 13 | 12 |
| `Variable` | 14 | 19 | 1 | 0 |
| `Graph` | 12 | 19 | 5 | 1 |
| `Namespace` | 4 | 5 | 18 | 3 |
| `Dataset` | 6 | 1 | 1 | 0 |
| `ConjunctiveGraph` | 1 | 1 | 0 | 0 |

Files referencing rdflib internals:

| Module | graph/ | sparql/ | shacl/ | shacl_engine/ |
|---|---:|---:|---:|---:|
| `rdflib.plugins.sparql` (any) | 14 | 26 | 2 | 2 |
| `...sparql.parser` | 9 | 23 | 0 | 1 |
| `...sparql.parserutils` (`CompValue`, `Comp`, `Param`) | 9 | 21 | 0 | 1 |
| `...sparql.algebra` | 2 | 15 | 0 | 0 |
| `...sparql.sparql` (`Query`, `Prologue`, `QueryContext`, `SPARQLError`) | 7 | 10 | 2 | 2 |
| `...sparql.evaluate` | 3 | 2 | 0 | 0 |
| `...sparql.operators` | 3 | 2 | 1 | 2 |
| `rdflib.namespace` | 20 | 16 | 14 | 9 |
| `rdflib.term` | 10 | 2 | 3 | 1 |
| `rdflib.paths` | 3 | 10 | 0 | 0 |
| `rdflib.collection` | 2 | 11 | 2 | 1 |
| `rdflib.compare` | 3 | 0 | 0 | 0 |
| `rdflib.store` / `plugins.stores` | 3 | 1 | 1 | 0 |

(A "plugin/register" pattern matched too broadly and is not reported.)

External packages on top of rdflib: `pyshacl` is referenced in 16 files of `shacl/` and 5 files of `shacl_engine/`; `owlrl` (optional `reasoning` extra) is used by `StarLayerGraph.infer()` for RDF/RDFS/OWL-RDF-Based; `oxrdflib` (extra `oxigraph = ["oxrdflib>=0.4", "pyoxigraph>=0.5"]`, `pyproject.toml:50`) is rdflib's Store adapter for Oxigraph. `rdflib>=7.0` is a hard dependency (`pyproject.toml:14`).

Direct pyoxigraph use today: `graph/backends/native_oxigraph.py` (13 mentions), `graph/backends/native.py` (5), `graph/graph/starlayer_dataset.py` (3), `graph/graph/prefixes.py` (2) and, on this branch, `shacl_engine/overlay_oxigraph.py` (8) and `shacl_engine/oxigraph_view.py` (7). The in-process Oxigraph path in graph/ goes through `oxrdflib.OxigraphStore`, whose private attribute `store._inner` is the `pyoxigraph.Store` (`native_oxigraph.py:_engine`); `is_oxigraph_store` is duck-typed on the class name `OxigraphStore`.

### 2.3 Where rdflib's SPARQL parser, algebra and evaluator are load-bearing

1. Grammar. `sparql/_grammar12.py` (932 lines) splices SPARQL 1.2 productions into rdflib's live pyparsing grammar in place (`GraphTerm`, `VarOrTerm`, `GraphNode`, `GraphNodePath` are `MatchFirst` objects extended with `.append`). `graph/CLAUDE.md` records that importing the grammar lazily during pytest collection corrupts it for the rest of the run, so `tests/conftest.py` installs it eagerly. 23 of 40 sparql/ files import `rdflib.plugins.sparql.parser`.
2. Algebra translator. `sparql/lower_rdf11.py` (1,971 lines; 124 lines mention `rdflib.plugins.sparql`/`CompValue`/`translateQuery`/`translateAlgebra`/`_AlgebraTranslator`) defines `_AlgebraTranslator11(_AlgebraTranslator)` (line 1689); `sparql/serialize12.py` (542 lines, 36 matching lines) defines `_AlgebraTranslator12(_AlgebraTranslator)` (line 153). `graph/query/algebra_translator_patches.py` patches rdflib's own `translateAlgebra`.
3. Algebra as data (sqe/salg/SRL). `sparql/from_rdf.py` (599; 35 matching lines), `to_rdf.py` (508; 25), `sqe/to_rdf.py` (523; 14), `srl.py` (1,073; 23), `srl_eval.py` (859; 9) read and write rdflib `CompValue` trees. `sparql/sqe/` and `sparql/salg/` total about 2,500 lines. A directory named `spexpr` does not exist on this branch; the expression helpers are `expr_text.py`, `expr_families.py`, `expr_validation.py` and `sqe/expr_text.py`.
4. Evaluator. The `rdf-1.1` backend lowers a 1.2 query to a 1.1 algebra and rdflib's `evalQuery` runs it against the in-memory store, with all of class B patching that evaluator. Files referencing the evaluator: `evaluate_patches.py`, `update_patches.py`, `remote_decompose.py`, `sparql/srl_eval.py`, `sparql/from_rdf.py`. The SRL rule engine evaluates through `g.query(...)` (`srl_eval.py:341`), i.e. `StarLayerGraph.query`, so rdflib's evaluator when the graph is `rdf-1.1`.
5. Expression semantics in SHACL. `shacl/sparql_node_expressions.py`, `shacl/list_functions.py`, `shacl_engine/sparql_support.py` and `shacl_engine/expressions.py` use `rdflib.plugins.sparql.operators.EBV`, `SPARQLError` and `CompValue`.
6. Function registry. `custom_functions.py` registers `TRIPLE`-family functions into rdflib's global registry as an import side effect; the `lower_rdf11.py` lowering emits calls to them.

`graph/CLAUDE.md` records past bugs from this coupling: lazy grammar import corrupting the shared grammar; pyparsing parse-action arity discovery failing in a pool thread (issue #100); `Dataset.remove` removing from every graph (#135); `ctx.graph` being the union under `default_union` (#78).

---

## 3. USER-VISIBLE API

Sources: `docs/working/archive/api-reference.md` (generated member tables), `graph/graph/_rdflib_inherited_contract.py`, and `ast` of the two class files.

Row counts in api-reference.md:

| Class | New | Modified (overrides an rdflib method) | Unchanged (inherited) |
|---|---:|---:|---:|
| `StarLayerGraph` | 15 methods | 16 methods | 25 methods + 3 properties |
| `StarLayerDataset` | 5 methods | 17 methods | 34 methods + 5 properties |

(The generated table does not list every public method, e.g. the Graph "New" count of 15 is lower than the 20 new names found in the source below.)

`StarLayerGraph(Graph)`:
- Overridden: `__init__` (adds `backend=`), `__reduce__`/`__setstate__` (copy/pickle), `open`, `close`, `add`, `addN`, `remove`, `triples`, `triples_choices`, `__contains__`, `__len__`, `parse` (adds the 12 format names, `MultipleGraphsError`), `query` (adds `entailment=`, SPARQL 1.2), `update`, `serialize` (default `format='turtle12'`), `print` (default `turtle12`), `cbd` (returns `StarLayerGraph`, `include_reifications=`), `skolemize`, `de_skolemize`, `isomorphic`.
- New: `add_reification`, `add_reifier_annotation`, `remove_reification`, `reifiers`, `reifications`, `reifier_annotations`, `reified_triples`, `triple_terms`, `has_triple_term`, `qname_term`, `infer`, `owl_imports`, `has_import_locally`, `resolve_imports`, `derive_shape`, `empty_like`, `unbind`, `used_prefixes`, `reduce_prefixes`, `from_rdflib` (classmethod).
- Inherited unchanged, recorded in `_rdflib_inherited_contract.py` (33 entries): `add_graph`, `all_nodes`, `bind`, `collection`, `commit`, `compute_qname`, `connected`, `context_id`, `destroy`, `get_graph`, `graph`, `graphs`, `isomorphic` (Dataset side), `items`, `n3`, `namespaces`, `objects`, `predicate_objects`, `predicates`, `print` (Dataset side), `qname`, `remove_context`, `resource`, `rollback`, `set`, `subject_objects`, `subject_predicates`, `subjects`, `toPython`, `transitiveClosure`, `transitive_objects`, `transitive_subjects`, `value`; properties `store`, `namespace_manager`, `identifier`. The inherited read methods work because they delegate to the overridden `triples()`. A drift test (`tests/graph/unit/test_rdflib_inherited_contract.py`) compares live rdflib signatures against the snapshot.

`StarLayerDataset(Dataset)`:
- Overridden: `__init__` (adds `backend=`, `bind_namespaces`), `open`, `close`, `get_context` (returns `StarLayerGraph`), `contexts`, `quads`, `triples`, `triples_choices`, `add`, `remove`, `__contains__`, `remove_graph`, `addN`, `parse` (accepts rdflib's `trig`/`nquads`/`nq`/`trix` and routes them to `*12`), `__len__`, `query`, `update`, `serialize` (default `trig12`), `cbd`, `skolemize`, `de_skolemize`, `default_graph`/`default_context` (return `StarLayerGraph`).
- New: `unbind`, `used_prefixes`, `reduce_prefixes`, `to_graph`, plus `reifiers`, `reifications`, `reifier_annotations`, `reified_triples` (these return a `StarLayerDataset`, not generators of nodes).
- Inherited unchanged: 34 methods and 5 properties, including `add_graph`, `graphs`, `graph`, `get_graph`, `bind`, `namespaces`, `collection`, `resource`, `isomorphic`, `print`, `commit`, `rollback`, `destroy`, and properties `store`, `namespace_manager`, `identifier` (deprecated by rdflib).

Other public symbols re-exported from `starlayer.graph`: `Graph, Dataset, Literal, URIRef, BNode, Namespace, Variable, Collection, RDF, RDFS, XSD` (rdflib pass-throughs), `TripleTerm`, `DirLangString`, `ENTAILMENT`, `parseQuery/prepareQuery/parseUpdate/prepareUpdate/processUpdate`, `CompValue`, `used_prefixes`, and the `compare` and `rdfc` functions (`rdfc10_hash`, `to_canonical_nquads`).

What a replacement has to provide or drop (facts about current dependents):
- Types: `Graph`, `Dataset`, `ConjunctiveGraph` and `Store` appear in signatures and `isinstance` checks across `shacl/` (`shacl/adapters.py:30` subclasses `Graph`), in pyshacl calls, in `sparql/` (`g.query`, `g.parse`) and in the notebooks.
- `Graph.query(..., initNs, initBindings, processor, result)` and `Graph.update(...)` return rdflib `Result` objects; SHACL and SRL code iterates them.
- Namespace manager and ~29 default prefix bindings (an explicit user decision in `graph/CLAUDE.md`: "keep rdflib's default bindings for `StarLayerGraph`").
- Stores: any rdflib `Store` can be passed in (`store=`); `backend="rdf-1.2"` accepts an `OxigraphStore` or a SPARQL endpoint.
- Formats: `turtle`, `nt`, `xml`, `n3` (= Turtle), `json-ld` (rdflib only), `manchester`, `nquads`, `trig`, `trix` and their `*12` names. Any other rdflib-recognised format is documented as unsupported ("unpredictable results").
- Python protocol: iteration, `in`, `len`, set operators inherited from `Graph`, `copy`, `pickle`.

---

## 4. TEST EXPOSURE

`packages/starlayer/tests`: 310 `test_*.py` files, 4,254 `def test_` functions (static count; a parametrised test counts once), 68,871 lines. 252 of the 310 test files import rdflib (267 of 363 `.py` files in tests/). 236 test files import `starlayer.graph`, `starlayer`, `starlayer.sparql` or `starlayer.shacl`.

By directory (static def count; `imp` = files importing rdflib):

| Directory | Files | Tests | imp |
|---|---:|---:|---:|
| `tests/graph/unit` | 79 | 1,636 | 61 |
| `tests/graph/integration` | 7 | 169 | 7 |
| `tests/graph/w3c_sparql12`, `w3c_turtle12` | 3 | 13 | 2 |
| `tests/sparql/unit` | 40 | 483 | 37 |
| `tests/sparql/{sqe_coverage, srl_conformance, integration, w3c_sparql12}` | 17 | 65 | 11 |
| `tests/shacl/integration` | 85 | 1,059 | 84 |
| `tests/shacl/unit`, `w3c_shacl12` | 25 | 165 | 13 |
| `tests/shacl_engine` | 22 | 312 | 21 |
| `tests/starontology/*` | 11 | 77 | 5 |
| `tests/kg/unit` | 13 | 232 | 9 |
| top-level `tests/test_*.py` | 8 | 43 | 2 |

Files that touch rdflib internals (`rdflib.plugins`, `rdflib.store`, `rdflib.query`, `rdflib.compare`, `rdflib.paths`): 50. Files that name plain rdflib as a comparison oracle (loose regex: "plain rdflib", "oracle", "against rdflib", `rdflib.Graph()`): 29. Files that cite patch modules or the upstream-issues doc: 18. Files that use `pyoxigraph`/`oxrdflib`: 17. Union of the first three loose criteria: 77 files, 1,625 test functions, 27,212 lines. This is an upper bound (some `shacl/integration` files import `rdflib.plugins` for one helper).

`tests/graph` (1,818 tests, 89 files) classified by file name (heuristic keyword match; approximate):

| Class | Files | Tests | Examples |
|---|---:|---:|---|
| A: parsers, serializers, triple terms, 1.2 SPARQL | 36 | 852 | `test_turtle_parser.py` (82), `test_turtle12_serializer.py` (52), `test_manchester_*`, `test_trig12_*`, `test_ntriples12`, `test_sparql12_*`, `test_proposition_form_encoding`, `test_lowering_hunt3` |
| B: patch behaviour | 13 | 152 | `test_sparql_builtins_hunt3.py` (80), `test_operator_patches.py` (14), `test_result_patches.py`, `test_bind_scoping.py`, `test_update_graph_management.py`, `test_group_filter_falsy_literal.py` |
| C: rdflib-API surface | 13 | 341 | `test_starlayer_graph.py` (104), `test_dataset.py` (96), `test_rdflib_inherited_contract.py`, `test_prefixes.py`, `test_unbind_prefix.py`, `test_thread_safety_hunt2.py`, `test_compare.py` |
| D: StarLayer features | 14 | 216 | `test_entailment*.py`, `test_infer*.py`, `test_shape_derivation.py`, `test_rdfc*.py`, `test_resolve_imports.py`, `test_skolem_semantics.py` |
| E: engine-specific | 9 | 182 | `test_oxigraph_backend.py` (70), `test_fuseki_backend.py` (39), `test_oxigraph_store_rdf12.py` (31), `test_dirlang_equality.py`, `test_remote_decompose.py` |
| Other | 4 | 75 | includes `test_sqlalchemy_backend.py` |

Opt-in or environment-gated: engine-abort tests (`STARLAYER_RUN_ENGINE_ABORT_TESTS=1`), store-matrix (`--store-matrix`), Fuseki integration (local server). `graph/CLAUDE.md` says the parser fixes were found with rdflib as the oracle (parsers compared against rdflib's own parsers on the same input).

---

## 5. WHAT REMAINS PER CLASS IF OXIGRAPH / OXRDF IS THE BASELINE

Scope note: this section lists only what the repo already uses or documents about pyoxigraph. Empirical behaviour (supported formats, RDF 1.2 triple terms, `quads_for_pattern`, SPARQL 1.2 coverage, base direction, update semantics) belongs to `docs/working/oxigraph-capability-matrix.md`; the lines below are not verified claims about pyoxigraph.

Used in this repo today, which shows availability in the `pyoxigraph>=0.5` range the code targets:
- `pyoxigraph.Store().query(sparql, use_default_graph_as_union=True)` and `.update(sparql)` (`native_oxigraph.py:_query`, `ox_update`).
- Term classes `ox.NamedNode`, `ox.BlankNode`, `ox.Literal` (`.language`, `.direction`, `.datatype`) and `ox.Triple` (`native_oxigraph.py:_parse_ox_term` converts `ox.Triple` to `TripleTerm` and a directional `ox.Literal` to `DirLangString`).
- SPARQL SELECT/ASK/CONSTRUCT results as typed objects (`ox_select`, `ox_ask`, `ox_construct`).
- `quads_for_pattern` is used in `shacl_engine/overlay_oxigraph.py` (2 uses) and `oxigraph_view.py` (1); graph/ does not use it (grep).
- `graph/CLAUDE.md` and `docs/upstream-issues/oxigraph-upstream-issues.md` record: SPARQL `=` on two dirLangString terms aborts the process (#1982, filed); literals are normalised when stored (whole-number `xsd:decimal`; `xsd:string` datatype on every plain literal; both handled in `_parse_ox_term`); on an in-process Oxigraph store `add()` and N-Triples `parse()` store a blank node as a skolem IRI (issue #98, owner decision pending) while `addN()` and `INSERT DATA` keep a real blank node.

### Class A (11,714 lines)
- Needed whichever baseline: the Manchester parser and serializer (2,387; the repo shows no Oxigraph counterpart); `VERSION` conformance (`model/conformance.py`, 138); annotation/reifier helper methods; any format or behaviour pyoxigraph does not provide; `TripleTerm`/`DirLangString` wrapper types if the public API keeps them (`model/triple.py` 111, `dirlangstring.py` 84; today they convert to and from `ox.Triple`/`ox.Literal` in `_parse_ox_term`).
- Exists to emulate triple terms in rdflib's store (the `rdf-1.1` backend), so not exercised on a native engine: `model/encoding.py` 433; the `tt:` family in the graph classes (664 + 111 helper, plus Dataset 105); the A part of `evaluate_patches`/`operator_patches` (about 617); `compare.py` 282; and the 1.2-to-1.1 lowering: `graph/query/custom_functions.py` 552, `query_cache.py` 172, `remote_decompose.py` 322, `version_directive.py` 133, plus `sparql/lower_rdf11.py` 1,971 outside graph/. Subtotal inside graph/: about 3,500 lines.
- Hand-written parsers/serializers excluding Manchester: 5,686 + 2,301 - 2,387 = 5,600 lines. They are needed for formats or behaviours pyoxigraph does not match (e.g. `Turtle12SyntaxError` messages, longturtle layout, TriX 1.2 convention, per-document blank-node scoping, positional prefixes); which of those apply is for the capability matrix to say.

### Class B (2,944 lines)
- The 41 numbered rdflib issues are bugs in rdflib's evaluator, algebra and grammar. If SPARQL is executed by Oxigraph's engine instead of `evalQuery`, the evaluator patches (`evaluate_patches` B part, `builtin_error_patches`, `operator_patches` B part, `update_patches`, `result_patches`) have no target. `oxigraph-upstream-issues.md` lists 1 open Oxigraph issue.
- The parse-side patches (`path_patches`, `algebra_translator_patches`, tab handling in `builtin_error_patches`, `sparql/_syntax_checks.py`, `sparql/_grammar12.py::_fix_rdflib_lexical_gaps`) stay relevant for as long as SPARQL text is parsed with rdflib's grammar, which `sparql/` (sqe/srl/salg on `CompValue` trees) does today.

### Class C (3,280 lines)
- The subclassing of `Graph`/`Dataset`, `_rdflib_inherited_contract.py` (312), `sparql_api.py` (220) and the `__init__` re-exports (240) exist to satisfy rdflib's API. Without an rdflib superclass the 33 inherited methods in section 3 are either written or dropped.
- Namespace and prefix handling (`prefixes.py`, `bind`, `namespaces`, `qname`, `compute_qname`, the ~29 default bindings) has no pyoxigraph counterpart evidenced in the repo: `prefixes.unbind_prefix` reaches into oxrdflib's store for its prefix map (confirm in the matrix whether `pyoxigraph.Store` keeps prefixes).

### Class D (2,777 lines)
- Independent of rdflib in algorithm but expressed over `Graph.triples`/`Graph.objects` and rdflib term classes: shape derivation, `infer` (the `owlrl` path builds an rdflib graph view via `_deskolemize_to_graph`; OWL-DL uses owlready2/HermiT/rustdl), `resolve_imports`, skolemisation, CBD, `rdfc.py` (RDFC-1.0, takes quads, no use of rdflib's canonicalisation), timeout.

### Class E (1,890 lines)
- Oxigraph-only (431): `dirlang_equality.py` (296) exists because of oxigraph#1982; `native_oxigraph.py` (135) reaches the engine through `oxrdflib.OxigraphStore._inner`.
- Native-engine transport (990): `native.py` (HTTP JSON client plus engine detection, 824) and `skolem_semantics.py` (166, Fuseki-only).
- `_native_*` branches in the graph classes (469) and the 36 + 4 `self._is_native` forks: the other half of the "two representations, one class" design (`graph/CLAUDE.md` rule 1: "a change to one path usually needs a twin in the other").

### Dependencies outside graph/ that the A-E picture does not cover
- 23 `sparql/` files import rdflib's SPARQL parser and 15 its algebra (section 2.3); changing the graph backend does not remove those.
- `shacl/` is built on `pyshacl` (16 files), itself on rdflib. The new `shacl_engine/` (6,568 lines; 24 files import rdflib) already has an Oxigraph-direct overlay (`overlay_oxigraph.py`, `oxigraph_view.py`) that uses `pyoxigraph` without `oxrdflib`.

---

## Surprises, stated plainly
- The default backend, `backend="rdf-1.1"`, is rdflib plus the `tt:` encoding; the native Oxigraph path is opt-in (`pyproject.toml:46-50`: "Opt-in, never a default").
- About 617 lines of the "patch" files (564 in `evaluate_patches.py`, 53 in `operator_patches.py`) are not rdflib bug fixes; they are the cost of the `tt:` encoding inside rdflib's evaluator.
- The in-process Oxigraph path reaches pyoxigraph through a private attribute of oxrdflib (`store._inner`), not directly; `shacl_engine/` does use pyoxigraph directly.
- All 35 patches are applied as a side effect of `import starlayer.graph`, so plain rdflib used in the same process also gets the patched behaviour.
- The rdflib-upstream-issues doc says none of the rdflib bugs have been filed upstream.
- 93% of graph/ lines (21,482 of 23,112) sit in files that import rdflib, but in parsers and serializers the import is mostly term classes; only `query/` (4,983 lines, 13 of 13 files) and the two class files are coupled to rdflib's behaviour.
