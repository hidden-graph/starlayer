# D1 readiness: what still touches the old graph classes (2026-11-04)

Branch `mig-d1-prereqs`, from `shacl-engine` at 194db92. D1 renames `OxGraph` to `StarLayerGraph` and `OxDataset` to
`StarLayerDataset` and deletes the rdflib-based classes. This branch moved every live caller off them (list below) and
did not delete anything. `packages/starlayer/tests/test_d1_readiness.py` walks `starlayer/`, `scripts/`, `tools/` and
`packages/starlayer-kg` with `ast` (lazy imports included, names re-exported by a package `__init__` followed) and requires the
importers of the old class and old modules to be exactly the table in section 1. It fails when a new importer appears and when
one in the table is gone (so D1 progress is a shrinking `ALLOWED` dict).

## 1. Remaining live references (what the test allows)

| File | What it imports | Who needs it | What unblocks it |
|---|---|---|---|
| `starlayer/__init__.py` | `StarLayerGraph`, `StarLayerDataset` from `starlayer.graph` (re-export) | the public API names | D1 points the names at `OxGraph` / `OxDataset` |
| `starlayer/graph/__init__.py` | the old classes, `query.custom_functions`, the rdflib query patches (`algebra_translator_patches`, `builtin_error_patches`, `evaluate_patches`, `operator_patches`, `path_patches`, `result_patches`, `update_patches`), `parseQuery` / `prepareQuery` / `parseUpdate` / `prepareUpdate` / `processUpdate` (`query.sparql_api`) | facade; importing `starlayer.graph` installs the patches into rdflib | D1 rewrites it. `used_prefixes` is no longer exported (`mig-union-fixes`: its only caller was its own test) |
| `starlayer/graph/graph/__init__.py` | the two old classes | facade | D1 |
| `starlayer/graph/query/__init__.py` | `sparql_api` | facade | goes with the package |
| `starlayer/graph/serializers/__init__.py` | `ntriples12`, `rdfxml12`, `trig12`, `turtle12` | facade | goes with the package |
| `starlayer/graph/oxgraph/_rdflib_bridge.py` | `starlayer_graph()` builds an old-style graph | `oxgraph/helpers/shapes.py` (`derive_shape`), which copies to an old graph and calls `graph/graph/shape_derivation.py` | branch `mig-small-ports` ports `shape_derivation`; then delete `starlayer_graph()` here |

Nothing else in `starlayer/`, `scripts/`, `tools/` or `packages/starlayer-kg` imports the old classes, the old parsers,
serializers, backends, `graph.query`, `graph.graph.prefixes`, `lower_rdf11`, `entailment_rdf` or `entailment_rdfs`.

Not imports but still the old class by name:

- Docstrings and error messages in kept modules say `StarLayerGraph.infer(...)` / `.derive_shape()` (`owl_dl.py`, `owl_dl_rustdl.py`,
  `shape_derivation.py`, `oxgraph/helpers/*.py`, `shacl/*.py`). They become correct at D1 and need no edit.
- `sparql/_grammar12.py` and `sparql/lower_rdf11.py` mention it in comments only.

## 2. What D1 deletes, with lines

The old class and every module only it (directly or through another old module) imports. Computed with the same `ast` walk;
`parsers/manchester_parser`, `parsers/errors`, `serializers/manchester` and `backends/_versions` stay (live).

| Group | Modules | Lines |
|---|---|---:|
| Old classes | `graph/graph/starlayer_graph.py` 4,011; `starlayer_dataset.py` 1,226; `_rdflib_inherited_contract.py` 312 | 5,549 |
| Prefix manager | `graph/graph/prefixes.py` (public `used_prefixes` goes too) | 136 |
| Hand-written parsers | `parsers/`: `turtle_parser` 1,307, `syntax` 847, `trig12` 477, `ntriples12` 376, `rdfxml12` 360, `lexer` 313, `faithful` 46, `bnode_scope` 44 | 3,770 |
| Hand-written serializers | `serializers/`: `turtle12` 895, `ntriples12` 168, `rdfxml12` 203, `trig12` 83, `_xml` 49 | 1,398 |
| Backends | `backends/`: `native` 709, `skolem_semantics` 166, `native_oxigraph` 137 | 1,012 |
| rdflib query machinery | `graph/query/`: `evaluate_patches` 1,266, `builtin_error_patches` 879, `custom_functions` 552, `operator_patches` 477, `update_patches` 360, `algebra_translator_patches` 344, `remote_decompose` 322, `sparql_api` 220, `direct` 176, `query_cache` 172, `path_patches` 159, `result_patches` 76, `version_directive` 70 (now only a re-export of `oxgraph.sparql_text`) | 5,073 |
| Lowering and query-time entailment | `sparql/lower_rdf11.py` 1,971; `sparql/entailment_rdf.py` 151; `sparql/entailment_rdfs.py` 289 | 2,411 |
| **Total** | 36 modules | **19,349** |

`entailment_rdf.py` and `entailment_rdfs.py` (440 lines) were not in the Phase C inventory: only `graph/query/query_cache.py`
imports them, so they go with it (their tests `test_entailment_rdf.py`, `test_entailment_rdfs.py` go too).

Also D1 work that is not a deletion of source:

- **Tests.** 207 test files mention the old classes (D2 migrates them); 124 import an old class or module path
  (`starlayer.graph.graph.starlayer_graph`, `parsers.*`, `serializers.*`, `backends.*`, `query.*`, `lower_rdf11`,
  `entailment_rdf(s)`). The ones that exist only to test a deleted module are listed in `phase-c-dependency-inventory.md`
  ("Tests"). `tests/graph/conftest.py` imports `parsers.turtle_parser` (and `w3c_turtle12` with it).
- **Code KG.** `tools/kg/codekg/curated/upstream-issues.ttl` cites the rdflib patch functions in `graph/query/*_patches.py`
  (`slkg:workedAroundByIdentifier`); `tests/kg/unit/test_upstream_issues.py` also scans that directory. Both change when the
  patches go. Curated entries that cite names that are already gone fail today (see section 5).
- **Facade rewrites** (table 1) and the generated docs (`docs/generated/*.generated.md`) are regenerated at D3.
- **Guides.** 26 of 28 mention the names in prose; only `05c-srl-sparql-rules-as-rdf.ipynb` has one in a code cell
  (a comment). `starlayer-kg`'s README says `StarLayerDataset`, which is true after D1.

## 3. What moved in this branch

| Caller | Before | Now |
|---|---|---|
| `oxgraph/run.py`, `shacl_engine/oxigraph_view.py` | `backends.native.{inject_init_bindings, check_native_version_conformance}` | new `oxgraph/sparql_text.py` (`inject_init_bindings` over rendered terms, `check_native_version_conformance`, `strip_version_directive`); `backends.native` and `query.version_directive` delegate to it. Three W3C / builtin tests import `strip_version_directive` from the new place |
| `sparql/parse_sparql.py` | `parsers.turtle_parser._join` | its own five-line `_join` |
| `sparql/sqe/expr_text.py`, `to_text.py` | `serializers.turtle12._PN_LOCAL` | `oxgraph.pretty._PN_LOCAL` (the same pattern) |
| `sparql/srl_eval.py` (866 -> 796 lines) | `StarLayerGraph` / `StarLayerDataset`, `lower_rdf11`, `backends.native.sparql_term`, rdflib `evalBGP` and `Expr` evaluation | evaluates on `OxGraph` over Oxigraph: a run of triple patterns is one `SELECT` joined in Python, an expression is rendered with `expr_text` and evaluated with `substitutions`, `NOW()` is fixed to the evaluation instant. Triple terms are `ox.Triple` s |
| `sparql/check.py` | `StarLayerGraph().query(text)` | `OxGraph().query(text)` |
| `sparql/spexpr_codec.py` | `_new_starlayer_graph()` | `_new_tree_graph()` returns a plain `rdflib.Graph` (the encoded trees hold no triple term) |
| `sqe_parse_to_tree`, `manchester_parse_to_tree` | default graph was the old class (a plain `Graph` for Manchester) | default is a fresh `OxGraph`, root a pyoxigraph term. An `OxGraph` or an rdflib graph passed in works as before. `manchester_tree_to_owl` returns an `OxGraph`. `sparql_to_tree` / `ast_to_tree` / `ruleset_to_tree` / `srl_parse_to_tree` default to a plain `rdflib.Graph` (they were the old class): their ~650 render-fixpoint tests assert that numeric literals keep their spelling, which an `OxGraph` does not |
| `_rdflib_bridge.to_starlayer_graph` | old-class snapshot | `to_rdflib_graph`: plain `rdflib.Graph` (a triple term becomes the decomposed reification fragment). Used by `read_boundary`, Manchester serialisation, `ui_widget_selection` |
| `shacl/ui_widget_selection.py` | built `StarLayerGraph` probe / scoring graphs, snapshotted every Oxigraph argument | plain `rdflib.Graph` for the probe and scoring graphs; copies only the shapes and scoring graphs; the data graph goes to `validate()` as it is |
| `starontology/__init__.py` | rdflib parse, copy into `StarLayerGraph`, convert (`_as_oxigraph`) on every call | Oxigraph parses each file once into a cached `OxGraph`; each call copies it, identifier and used prefixes set |
| `starontology/manchester.py` | `StarLayerGraph` for `manchester_tree_to_owl` | `OxGraph` |
| `sparql/star_query.py` | prepared rdflib `Query` plus `infer` / `engine` / `timeout` kwargs (only the old class took them) | an `OxGraph` gets the query text with `initNs` / `initBindings` / `base`; `entailment` and `timeout` raise `NotImplementedError` (not in the inventory: found by reading callers) |
| `tools/kg/codekg` (`__init__`, `queries`, `extractor/build`, `extractor/stamp`, `extractor/cli`), `scripts/build.py`, `build_kg.py`, `publish_kg.py`, `packages/starlayer-kg` | `StarLayerGraph` / `StarLayerDataset`, `rdflib.compare.isomorphic`, `compare.isomorphic`, `parse12` / `parseQuery` for free-form queries | `OxGraph` / `OxDataset`, `rdfc_native.isomorphic`, `parse_sparql` for the free-form check. The query library stays a plain `rdflib.Graph` (the sqe decoders read rdflib terms). `build.py --only codekg kg` builds clean |

## 4. Behaviour changes (tests migrated; nothing skipped or weakened)

1. **`sqe_parse_to_tree(text)` and `manchester_parse_to_tree(text)` return an `OxGraph`.** Oxigraph keeps a literal in canonical
   form, so `FILTER(?x > 9.0)` is stored as `"9"^^xsd:decimal` and `sqe_tree_to_text` writes `"9"^^xsd:decimal`; the datatype and
   meaning are kept, the spelling is not (`1.50` -> `1.5`, `01` -> `1`). Passing an rdflib `Graph` as `graph=` keeps the spelling.
   Tests that edit a Manchester tree with rdflib's `Collection` / `set` now pass `graph=Graph()`; `test_tree_to_owl_matches...`
   compares two `OxGraph` s.
2. **A tree read back from an `OxGraph` lists a node's properties in store order, not source order.** `expr_text.render_expression`
   therefore fixes the argument order of the builtins whose names do not sort into it (`REGEX`, `REPLACE`, `SUBSTR`), since it can
   no longer take it from the node (SRL evaluation renders expressions decoded from a tree). `CompValue` equality is
   order-sensitive, so comparing a parsed rule set with one decoded from an `OxGraph` needs keys sorted; the existing round-trip
   tests use rdflib graphs and are unchanged.
3. **`ruleset.infer(graph)`.** Oxigraph input: unchanged (an `OxGraph` with the input's prefixes plus the rule set's own).
   rdflib input: a plain `rdflib.Graph`, or the caller's own old-class instance when it is a `Graph` subclass; a result that holds
   a triple term from a plain `rdflib.Graph` input is returned as an `OxGraph` (a plain `Graph` cannot hold it). Before, any
   rule set that mentioned a triple term silently switched to the old class. A FILTER that errors is false, as in SPARQL.
4. **`StarQuery.run(OxGraph)`** takes text, not a prepared query; `entailment=` and `timeout=` raise `NotImplementedError`.
5. **`manchester_tree_to_owl`** returns an `OxGraph` for every input.
6. **Code-KG dataset.** `get_codekg_dataset()` returns an `OxDataset` (`get_context` -> `graph`, `contexts()` -> `graph_names()`;
   read terms with `.value`). The dataset's union default graph returns a triple once for each named graph that holds it
   (7,421 of 168,362 quads repeat a triple), where the old class's union held each once. Fixed on branch `mig-union-fixes`
   (`graph/oxgraph/union.py`, see `oxigraph-upstream-issues.md` section 5); `test_combined_kg.py` compares rows again.

## 5. Found, not fixed

- Fixed on branch `mig-union-fixes`: the stale citations of `test_curated.py::test_every_implementing_symbol_of_a_capability_exists_in_the_code_graph`
  (now `starlayer.shacl_engine.entailment.resolve_data_view`) and `test_upstream_issues.py::test_every_workaround_exists_in_the_code_graph`
  (pyshacl issues 3 to 7 are `documented-only`: pySHACL is no longer a dependency, the workarounds are gone).
- 29 modules under `starlayer/sparql/` still import rdflib (parse12 and `_grammar12`, the sqe / srl / salg tree codecs, `expr_text`,
  `serialize12`, `star_query`, `triple_term`, `vocab`). That is plan item B3, not a D1 blocker; it is the D4 list.
- `graph/graph/entailment_regimes.py` (constants, five live importers) stays where it is.

## 6. Remaining blockers for D1

1. `oxgraph/helpers/shapes.py` + `shape_derivation.py` (branch `mig-small-ports`): until it lands, `_rdflib_bridge.starlayer_graph()`
   imports the old class.
2. `used_prefixes`: decided on branch `mig-union-fixes`; the export is gone (no caller needs it), `OxGraph.used_prefixes()` stays.
3. The facade `starlayer/graph/__init__.py` installs the rdflib patches on import; deleting `graph/query` changes what a plain
   `import starlayer.graph` does to rdflib for any third-party code that relied on it.

## 7. Decisions needed

1. **Union duplicates.** Decided and done on branch `mig-union-fixes`: the wrapper deduplicates (cached merged copy; cost in
   `oxigraph-upstream-issues.md` section 5).
2. **Lexical forms in trees.** Accept that the default `OxGraph` tree normalises `9.0` to `9` (decimal), or make the tree builders
   keep the rdflib spelling by default (pass an rdflib `Graph`)? The meaning is the same either way.
3. **`StarQuery` on an `OxGraph`** has no entailment or timeout: port query-time entailment (plan section 3, B1 says it was
   deferred) or drop those options at D1?
4. **`used_prefixes`:** removed with `graph.prefixes` (the method on `OxGraph` / `OxDataset` is the API).

## 8. Gate at the end of this branch

Full `packages/starlayer/tests`: 12,315 passed, 502 skipped, 35 xfailed (serial-equivalent run with `-n 4`, `PYTHONHASHSEED=0`).
The code-KG tests with `--deferred --codekg-queries` after `build.py --only codekg kg`: all pass except the two pre-existing stale-citation
tests of section 5 (and the combined-KG comparison, which now compares distinct rows). `build.py --check --skip codekg`: all generated
files current (`api-reference.generated.md` was regenerated in its own commit). `ruff check packages/`: clean. All 28 guides run
(`pytest --notebooks`).
