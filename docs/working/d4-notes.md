# D4 notes: rdflib becomes an optional dependency (branch `mig-d4`)

Goal: a user who installs `starlayer` without rdflib can import `starlayer`, `starlayer.graph`, `starlayer.shacl`, `starlayer.sparql`;
parse and serialize; run SPARQL query and update; run SHACL validation and rules (including `sh:sparql` constraints and
`FILTER [NOT] EXISTS`). Features that need rdflib import it lazily and raise one `ImportError` that names the extra:
`pip install starlayer[rdflib]`.

## 1. Measurement

`tests/test_core_without_rdflib.py` runs each case in a child interpreter that sets `sys.modules["rdflib"] = None` first, so every
`import rdflib` fails. Before the work, `import starlayer` failed at `graph/compare.py` (first of a chain: `compare`,
`model/triple`, `model/dirlangstring`, `model/encoding`, `entailment_regimes`, `setops`, `shacl/ui_widget_selection`,
`sparql/*`, `star_query`, `starontology`). The walk over every module of the package (`pkgutil.walk_packages`, blocked) then listed
29 modules that cannot be imported without rdflib; they are the "optional" rows below.

### Classification of the 52 files that imported rdflib at module level (excluding `_rdflib_bridge.py`)

Lines are the file length at HEAD 29ad8aa. **Core** = on the path of the goal above, fixed now. **Optional** = a feature that
needs rdflib: kept rdflib-based, guarded with a clear error. **Dead** = no live caller, listed but not deleted (see the end of the
table).

| File | Lines | Class | What was done |
|---|---:|---|---|
| `graph/compare.py` | 300 | core | rdflib imports moved into the functions that need them; `isomorphic()` of two Oxigraph-backed graphs/datasets uses `rdfc_native` (RDFC-1.0 on Oxigraph); `graph_diff`, `to_isomorphic`, `to_canonical_hash` and the rdflib-graph paths call `require_rdflib` |
| `graph/model/triple.py` | 111 | core | `TripleTerm` accepts pyoxigraph IRIs/blank nodes (and rdflib's when rdflib has been imported); `n3()` writes pyoxigraph components by `str` |
| `graph/model/dirlangstring.py` | 84 | core | `n3()` quotes with pyoxigraph; `encode_dirlangstring` imports rdflib when called |
| `graph/model/encoding.py` | 433 | core (import) / dead (body) | rdflib types are `TYPE_CHECKING` only; the `TT_*` / `ENCODING_*` constants are built on first access (`__getattr__`, `_consts()`) |
| `graph/graph/entailment_regimes.py` | 52 | core (import) | the rdflib `ENTAILMENT` / `KNOWN_REGIMES` / `SUPPORTED_REGIMES` are built on first access; `starlayer.graph.ENTAILMENT` is now the pyoxigraph-term one from `oxgraph/helpers/entailment.py` |
| `graph/setops.py` | 239 | core | rdflib is looked up in `sys.modules` (an rdflib graph can only exist if its owner imported rdflib) |
| `sparql/star_query.py` | 172 | core | `Result` import dropped; the regime IRIs are plain strings; `prepare_query_12` runs only when rdflib is installed (syntax check at construction); running against an rdflib graph calls `require_rdflib` |
| `starontology/__init__.py` | 850 | core | `get_resource_iri` returns an rdflib `URIRef` when rdflib is installed (as before) and a pyoxigraph `NamedNode` otherwise; the rdflib `PROF` namespace is built on first access |
| `sparql/parse_sparql.py` | 2155 | core | terms come from `sparql/_terms.py` (rdflib's when installed, small stand-ins when not); only the sqe-tree encoder at the end needs rdflib and calls `require_rdflib` |
| `sparql/sqe/rewrite.py` | 182 | core | same `_terms` import; returns the query unchanged when rdflib is missing (the rewrite only makes `EXISTS` faster) |
| `sparql/__init__.py`, `sparql/sqe/__init__.py`, `shacl/__init__.py` | - | core (facade) | PEP 562 lazy names (`select_widget(s)` in `shacl`; every rdflib-based name in `sparql` and `sqe`) |
| `shacl/ui_widget_selection.py` | 584 | optional | `require_rdflib` before its imports; reached through the lazy `shacl.select_widget(s)` |
| `graph/graph/owl_dl.py`, `owl_dl_rustdl.py` | 249 + 337 | optional (HermiT / rustdl bridges) | guarded |
| `graph/graph/shape_derivation.py` | 580 | optional | guarded (`derive_shape` goes through the bridge) |
| `graph/parsers/manchester_parser.py`, `graph/serializers/manchester.py`, `starontology/manchester.py` | 1672 + 715 + 1320 | optional (Manchester syntax) | guarded |
| `graph/rdfc.py` | 410 | optional (old RDFC-1.0 over rdflib terms) | guarded; `isomorphic` of Oxigraph graphs no longer reaches it |
| `sparql/_grammar12.py`, `parse12.py`, `_translate_patches.py`, `serialize12.py`, `_syntax_checks.py`, `triple_term.py` | 932 + 341 + 320 + 549 + 199 + 249 | optional (rdflib-grammar SPARQL 1.2 parse / prepare / serialize) | guarded |
| `sparql/spexpr_codec.py`, `to_rdf.py`, `from_rdf.py`, `vocab.py`, `expr_text.py` | 802 + 157 + 149 + 344 + 118 | optional (algebra / spexpr RDF encoding) | guarded; `spexpr_codec.py` now imports `parse12` first (the grammar-order rule that `sparql/__init__.py` used to enforce) |
| `sparql/sqe/to_rdf.py`, `from_rdf.py`, `to_text.py`, `expr_text.py`, `shapes.py`, `entailment.py` | 189 + 301 + 512 + 246 + 85 + 365 | optional (sqe trees are rdflib graphs) | guarded; `entailment=` on a query calls `require_rdflib` |
| `sparql/srl.py`, `_srl_ast.py`, `srl_eval.py`, `srl_semantic_checks.py`, `parse_srl.py` | 775 + 577 + 796 + 219 + 247 | optional (SRL) | guarded |
| `sparql/salg/{engine_components,semantic_checks,sparql_ontology,sparql_shapes}.py` | 57 + 203 + 142 + 211 | optional (salg) | guarded |
| `graph/oxgraph/helpers/entailment.py` | 222 | core (uses the bridge) | `infer()` with the RDFS or OWL-RL regime calls `require_rdflib` before `owlrl` (owlrl itself imports rdflib) |

Guards: a module that is rdflib-based throughout starts with `import starlayer._needs_rdflib` (a module whose body calls
`require_rdflib`, naming the importing module), followed by `# isort: split` so ruff keeps it first.

**Dead code.** Nothing was deleted: each candidate has tests, and two have KG tests that name them.
- `graph/model/encoding.py` everything except `encode_dirlang_datatype` / `decode_dirlang_datatype` and the `*_NS` strings
  (`tt_hash`, `term_key`, the memo, `restore_select_bindings`, `inject_missing_tt_encoding`, `_reencode_tt`,
  `canonicalize_query_result_value`, `encoding_triples`): no caller in `starlayer/`, `scripts/`, `tools/`; used by
  `tests/graph/unit/test_encoding.py`, `test_dirlangstring.py`, `test_interop.py`, and `tests/kg/unit/test_queries.py` expects
  `_reencode_tt` to call `tt_hash`. About 330 lines. Delete with those tests at the next KG regeneration (D3's area).
- `graph/compare.py` `graph_diff`, `to_isomorphic`, `to_canonical_hash` (about 80 lines): tests only.
- `graph/rdfc.py` (410 lines): reached only through `compare` for rdflib inputs and by its own tests (W3C RDFC suite);
  `rdfc_native` covers Oxigraph input.

## 2. What is lazy now, and how

- `starlayer`, `starlayer.graph`, `starlayer.shacl`, `starlayer.starontology`, `starlayer.sparql` (the package), `starlayer.conformance`
  import with rdflib blocked.
- `starlayer.sparql` and `starlayer.sparql.sqe` resolve their names on first use; `starlayer.shacl.select_widget(s)` likewise (and
  were taken out of `shacl.__all__`, so `from starlayer.shacl import *` works without rdflib). `starlayer.StarQuery` runs on Oxigraph without rdflib.
- Python-level helpers: `starlayer/_optional.py` (`require_rdflib(feature)`, `have_rdflib()`, `RDFLIB_EXTRA_HINT`),
  `starlayer/_needs_rdflib.py` (the import-time guard). `_rdflib_bridge` re-exports `require_rdflib`.
- `StarLayerGraph.to_rdflib` / `from_rdflib` (and the dataset forms): `require_rdflib`.
- `infer()` with RDFS / OWL-RL, and `entailment=` on a query (RDF / RDFS rewrite): `require_rdflib`.
- The sparql parser's term classes: `sparql/_terms.py`. A test parses a set of queries with and without rdflib and compares the dumps.

## 3. Behaviour that differs with rdflib absent

- `StarQuery(text)` checks the syntax at construction only when rdflib is installed; without it the error comes when the query runs.
- A correlated `FILTER [NOT] EXISTS` is not rewritten as a join (same rows, slower on large data).
- `isomorphic()` of two Oxigraph-backed graphs now always uses Oxigraph's RDFC-1.0 (rdflib or not). The old path first ran the
  `rdfc.py` canonicaliser, which stops a "poison" (highly symmetric blank-node) graph with `CanonicalizationComplexityError`; Oxigraph's
  canonicaliser has no such limit (`rdfc_native` docstring). Comparing untrusted symmetric graphs can hang. Open decision below.
- `starontology.get_resource_iri()` returns a `pyoxigraph.NamedNode` instead of an rdflib `URIRef` (open decision: make it always a `NamedNode`).

## 4. What remains rdflib-only, and why

Module-level rdflib imports still in `starlayer/` (each guarded, see the table): `graph/graph/owl_dl.py`, `owl_dl_rustdl.py`,
`shape_derivation.py`, `graph/rdfc.py`, `graph/parsers/manchester_parser.py`, `graph/serializers/manchester.py`,
`shacl/ui_widget_selection.py`, `sparql/{_grammar12,_srl_ast,_syntax_checks,_translate_patches,expr_text,from_rdf,parse12,parse_srl,serialize12,spexpr_codec,srl,srl_eval,srl_semantic_checks,to_rdf,triple_term,vocab}.py`,
`sparql/salg/{engine_components,semantic_checks,sparql_ontology,sparql_shapes}.py`, `sparql/sqe/{entailment,expr_text,from_rdf,shapes,to_rdf,to_text}.py`,
`starontology/manchester.py`. Also `sparql/_terms.py` (a guarded `try: import rdflib`, falling back to stand-ins) and the bridge
(lazy imports inside functions).

Why: SRL, salg and the sqe/spexpr trees are rdflib *graphs* and rdflib's own SPARQL grammar objects (pyparsing); Manchester syntax
is a hand-written parser that builds rdflib terms; owlrl and the OWL-DL reasoners take rdflib graphs (owner decision: keep through
the bridge). The sqe text path (`sqe_parse_to_tree` / `sqe_tree_to_text`) therefore needs rdflib; the *query* path that StarLayerGraph
uses (Oxigraph text execution, SHACL SPARQL checks through `parse_sparql`) does not.

## 5. Proposed follow-ups, by value

1. **Native parse tree for sqe, off rdflib** (large, about 2,500 lines: `sqe/{to_rdf,from_rdf,to_text,expr_text,shapes}`,
   `spexpr_codec`, `vocab`). Terms become pyoxigraph terms, the tree a `StarLayerGraph`. Lets the sqe text path, `rewrite_exists_text`
   and the RDF / RDFS entailment rewrite run without rdflib, and then deletes `_terms.py`. Biggest single step toward an rdflib-free
   default.
2. **SRL onto the native parser (`parse_srl`)** (medium, about 1,500 lines: `srl*.py`, `parse_srl.py`, `_srl_ast.py`): retires the
   pyparsing grammar (`_grammar12.py`, `parse12.py`) that only SRL, salg and `StarQuery`'s prepared object still use. Gate: SRL's 929 tests.
3. **Retire salg** (`salg-retirement-analysis.md`; about 1,000 lines plus `to_rdf` / `from_rdf` / `serialize12` / `_translate_patches`).
4. **SHACL UI widget selection on pyoxigraph terms** (small-medium, 584 lines): it is public SHACL UI surface (`StarShaclSchema.select_widgets`)
   and reads graphs through rdflib snapshot copies today.
5. **Delete the dead encoding code** (small, about 330 lines of `encoding.py`, `compare.graph_diff` and friends, with their tests and
   the KG test that names `_reencode_tt`); with it `compare.py` shrinks to `isomorphic`.
6. **Manchester syntax on pyoxigraph terms** (medium, about 3,700 lines in three files): hand-written parser and serializer, so a term-type
   change rather than a rewrite. Or leave: it is a self-contained optional feature.
7. **owlrl bridge** (small to keep, large to replace): keeps working through `_rdflib_bridge`; a native OWL-RL / RDFS closure would remove
   the last reason for `starlayer[reasoning]` to pull in rdflib. `infer()` with the RDF regime is already native.
8. **`rdfc.py` / `compare.py` poison-graph guard for the native path** (small): either a cheap symmetry pre-check in `rdfc_native`, or
   accept and document.

## 6. Packaging

`pyproject.toml` (repo root): `rdflib` and `owlrl` left `dependencies` (now `requests`, `pyoxigraph`). New extra `rdflib`
(`rdflib>=7.0`); `reasoning` is `owlrl` + `rdflib`; `sqlalchemy`, `oxigraph`, `hermit`, `rustdl` include `rdflib`; `test` and
`notebooks` include `rdflib` and `owlrl` (CI installs `.[test]`, so the suites still run). There is no `all` extra. **`uv.lock` was not
regenerated** (`uv` is not installed here): run `uv lock` on a machine with uv.
