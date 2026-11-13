# D1: the switch (record, 2026-11-06)

Branch `mig-d1`, from `shacl-engine` at 86b3a2d. This file began as the readiness list on `mig-d1-prereqs` (what still touched the old
classes) and now records what D1 did. Decisions the docs did not settle are in `d1-notes.md`.

## 1. Done

- `OxGraph` is `StarLayerGraph` and `OxDataset` is `StarLayerDataset` (`starlayer/graph/oxgraph/core.py`; the module path is unchanged).
  `from starlayer import ...` and `from starlayer.graph import ...` give them; `starlayer.graph.graph` re-exports them too.
- The rdflib-based classes and everything only they used are deleted (section 2). `starlayer.graph.query` no longer exists.
- Facades rewritten: `starlayer`, `starlayer.graph` (exports `StarLayerGraph`, `StarLayerDataset`, `isomorphic`, `ENTAILMENT`,
  `TripleTerm`, `DirLangString`, `can_resolve_import`), `starlayer.graph.graph`, `starlayer.graph.serializers` (docstring only: Manchester).
  Importing `starlayer.graph` no longer patches rdflib.
- `tests/test_d1_readiness.py` now asserts the deleted modules are gone and that nothing in `starlayer/`, `scripts/`, `tools/` or
  `packages/starlayer-kg` imports them (its `ALLOWED` table is empty and gone).
- Tests of the deleted behaviour are deleted as listed in `d2-delete-list.md` (section 3).
- `curated/upstream-issues.ttl`: 35 entries whose code was in the deleted patch modules are `documented-only`.

## 2. What was deleted (source)

| Group | Modules | Lines |
|---|---|---:|
| Old classes | `graph/graph/starlayer_graph.py`, `starlayer_dataset.py`, `_rdflib_inherited_contract.py` | 5,494 |
| Prefix manager | `graph/graph/prefixes.py` | 136 |
| Hand-written parsers | `parsers/`: `turtle_parser`, `syntax`, `trig12`, `ntriples12`, `rdfxml12`, `lexer`, `faithful`, `bnode_scope` | 3,770 |
| Hand-written serializers | `serializers/`: `turtle12`, `ntriples12`, `rdfxml12`, `trig12`, `_xml` | 1,398 |
| Backends | `backends/`: `native`, `skolem_semantics`, `native_oxigraph` | 1,012 |
| rdflib query machinery | all of `graph/query/` (13 modules and the facade) | 5,087 |
| Lowering and query-time entailment | `sparql/lower_rdf11.py`, `entailment_rdf.py`, `entailment_rdfs.py` | 2,411 |
| **Total** | 37 files | **19,308** (measured with `wc -l` before `rm`; includes the 344 lines of `algebra_translator_patches.py` that moved, see `d1-notes.md` 13) |

Kept (live): `parsers/manchester_parser`, `parsers/errors`, `serializers/manchester`, `backends/_versions`, `graph/graph/entailment_regimes`,
`owl_dl`, `owl_dl_rustdl`, `_timeout`, and `shape_derivation` (no library caller; a test reads its constant).

## 3. Tests deleted

39 whole-file entries and 23 `*_oldclass.py` files from `d2-delete-list.md` (about 11,600 and 3,500 lines), plus `tests/graph/unit/test_result_patches.py`,
the store-matrix variants of `w3c_shacl12/test_w3c_validate.py` and `test_w3c_infer.py`, one rdflib-patch test in
`sparql/unit/test_phase2_aggregates.py`, and one patch-census test in `kg/unit/test_upstream_issues.py`. The `parser` / `parse` fixtures of
`tests/graph/conftest.py` are gone.

## 4. Remaining rdflib in `starlayer/` (D4 / B3 backlog)

Outside `_rdflib_bridge.py`: see the final report of the D1 run for the file list. Bridge modules stay by plan: `_rdflib_bridge.py`,
`from_rdflib` / `to_rdflib`, `owlrl` on an rdflib copy, `rdfc.py`, `compare.py`.

## 5. Gate

Full `packages/starlayer/tests` with `--deferred --codekg-queries`, `build.py --check` (with codekg) and `ruff check packages/` are clean;
numbers are in the final report. Guides were not re-run (D3): their stored outputs still show old names in any repr.
