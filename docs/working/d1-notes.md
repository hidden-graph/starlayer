# D1 notes: decisions made while doing the switch (branch `mig-d1`)

Decisions the docs did not settle; each is the simplest option consistent with `graph-migration-completion-plan.md`.

1. **Module location.** The classes stay in `starlayer/graph/oxgraph/core.py` (`StarLayerGraph`, `StarLayerDataset`); `starlayer.graph`,
   `starlayer.graph.graph` and `starlayer` re-export them. No module was moved.
2. **`starlayer.graph.query` is deleted as a package**, not kept as an empty facade: every module in it was on the delete list and its
   `__init__` re-exported only `sparql_api`. `tests/test_d1_readiness.py` asserts the directory is gone.
3. **`starlayer.graph` exports** `StarLayerGraph`, `StarLayerDataset`, `isomorphic`, `ENTAILMENT`, `TripleTerm`, `DirLangString`,
   `can_resolve_import`, `interop`/`setops`/`rdfc_native` stay importable as submodules. The rdflib term re-exports (`BNode`, `Literal`, `URIRef`,
   `Variable`, `Namespace`, `RDF`, `RDFS`, `XSD`, `Graph`, `Dataset`, `Collection`) and the `parseQuery` family are gone; the eight tests that
   used `Namespace` / `RDF` from `starlayer.graph` now import them from `rdflib`.
4. **`graph/graph/shape_derivation.py` is kept** (not on the delete list): the library no longer calls it, but
   `tests/graph/unit/test_shape_derivation.py` reads its rdflib `DEFAULT_IGNORED_PROPERTIES`. D4/C3 backlog.
5. **`_rdflib_bridge.starlayer_graph()`** (built an old-style graph, no caller left) is deleted.
6. **`w3c_shacl12` store matrix.** `stores.py` is deleted, so the `store_matrix` variants in `test_w3c_validate.py` and `test_w3c_infer.py`,
   the `store_under_test` fixture (`w3c_shacl12/conftest.py`, deleted) and the `KNOWN_FAILURES_OXIGRAPH_*` / `KNOWN_FAILURES_FUSEKI_HTTP` tables
   are removed. The `--store-matrix` option in `tests/conftest.py` stays (other tests may use the marker).
7. **`tests/graph/w3c_turtle12/`**: only `test_w3c_turtle.py` was on the list and is deleted; its data, README and downloader stay (the
   SPARQL suite's downloader refers to them). Candidate for removal with `w3c_rdf12` as the one syntax suite.
8. **`curated/upstream-issues.ttl`**: the 35 entries whose only code was in `graph/query/*_patches.py` / `custom_functions.py` became
   `documented-only` (no code here deals with them any more, the same treatment as the pySHACL entries); the write-ups stay as history.
   `test_every_patch_function_is_recorded_as_a_workaround_or_explained` is deleted (no patch modules), and the lower bound on cited
   identifiers in `test_every_workaround_exists_in_the_code_graph` went from 20 to 5 (7 remain).
9. **Notebooks.** The 26 guides were edited in source cells only (`OxGraph` -> `StarLayerGraph`, `OxDataset` -> `StarLayerDataset`, markdown cells
   included); no output was touched, so stored outputs that print a repr still show the old name until the guides are re-run (D3).
10. **Working notes under `docs/working/` keep the old names** (they are history); only `d1-readiness.md` was rewritten. The generated docs are regenerated.
11. **Docs.** The "Rules that bite" block of `graph/CLAUDE.md` was rewritten for the single Oxigraph backend, and the lowering rule of
    `sparql/CLAUDE.md` replaced; the long history sections below them are untouched and describe deleted machinery.
13. **rdflib `translateAlgebra` shims kept.** `sparql/serialize12.py` still subclasses rdflib's `_AlgebraTranslator`, and three W3C SPARQL 1.2
    tests (`eval-triple-terms` order-1, order-2, expr-1) regenerate query text through it and failed without the two shims in
    `graph/query/algebra_translator_patches.py`. The shims moved to `sparql/_translate_patches.py` (344 lines, applied when `serialize12`
    is imported). They go with `serialize12` at B3 / D4. Everything else in `graph/query/` is deleted.
14. **Tests of deleted rdflib patches are deleted or moved to Oxigraph.** `tests/graph/unit/test_result_patches.py` (the rdflib
    `Result.__iter__` patch) and `test_unaliased_expression_group_by_key_roundtrips` (rdflib evaluator, patched `GROUP BY`) are deleted; the
    nested-negated-path round trip and two `test_syntax_checks.py` tests now evaluate on `StarLayerGraph` (Oxigraph) instead of rdflib.
15. `README.md` example prints `.value` of the pyoxigraph result terms (`test_readme_example.py` is unchanged).
16. `scripts/generate_api_docs.py` lost its entries for the deleted `entailment_rdf(s)` modules and the `graph/query` facade.
17. The 20 notebook links whose cells changed only by the rename were restamped after checking each is a rename-only edit.
12. **Left alone:** `scripts/b1_*.py` (one-off classification experiments that name the deleted files in strings) and the stray tracked
    file `tests/shacl/integration/test_expression_node_types.py-E`.
