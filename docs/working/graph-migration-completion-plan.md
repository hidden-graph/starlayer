# Completing the move off rdflib: remaining work

Branch `shacl-engine`, 2026-11-03. A draft for sign-off. This updates `graph-oxigraph-migration-plan.md` (the staged plan and
its recorded decisions, which still stand) with where the work actually is. Nothing here is done yet.

## 1. Where things stand

Done and merged into `shacl-engine`: the SHACL engine on pyoxigraph terms; the Oxigraph-backed wrapper (`OxGraph`, `OxDataset`)
with its StarLayer helpers; native interop and RDFC; set operations; direct SPARQL execution; the new SPARQL parser, Update and
the switch branches (`mig-parser`, `mig-update`, `mig-switch`); the pretty serializers; lexical-fidelity defaults; pySHACL removed.

Not done: the **old rdflib-based `StarLayerGraph` is still the library's internal graph type.** Measured today:

| What | Size |
|---|---|
| Source files that mention `StarLayerGraph` | 86 (engine 17, `sparql` 15, `shacl` 9, graph packages ~35) |
| Source files that import rdflib | ~105 |
| Test files that mention `StarLayerGraph` / import rdflib | 210 / 275 |
| Old graph machinery (`graph/graph` 7,100 lines, `graph/query` 5,200, `graph/parsers` 5,700, `graph/serializers` 2,300, `graph/backends` 1,100, salg 650) | ~22,000 lines |
| Guides using `OxGraph` | 25 of 28 |

The default constructor is still `StarLayerGraph(backend='rdf-1.1')`, an rdflib store with the `tt:` triple-term encoding.
The public SHACL functions accept both graph types but convert an `OxGraph` to an old `StarLayerGraph` snapshot internally
(`_oxigraph_to_starlayer`).

## 2. End state

- `StarLayerGraph` and `StarLayerDataset` are the Oxigraph-backed classes (today's `OxGraph`, `OxDataset`). One backend. Terms are
  pyoxigraph terms.
- No `import rdflib` in `starlayer/` outside the bridge modules. rdflib stays an optional extra for two supported conversions and
  for `owlrl`, which runs on an rdflib copy. **In** (`from_rdflib`) is a supported public feature. **Out** (`to_rdflib`) presents
  triple terms in the RDF 1.2 Interoperability basic encoding, i.e. RDF 1.2 as RDF 1.1, the same form as `serialize(rdf_version="1.1")`.
- RDF 1.1 output only through the basic-encoding export (already decided).
- All suites pass on the new classes; the old classes and their tests are deleted, not skipped.

## 3. Work, in order

Each step ends with the affected suites green, and the full suite at the end of each phase. Work stays on branches.

**Phase A: make the engine and public API native (no rdflib on the SHACL path).**
- A1. `validate`, `evaluate`, `apply_rules`, `target_nodes`, `extract_subgraph` take and return the Oxigraph-backed graph; remove
  `_oxigraph_to_starlayer` and the snapshot copy. Report graphs are built natively.
- A2. `shacl/` helpers (`meta_shapes`, `paths`, `subgraph_extraction`, `normalization`, `shacl_profiling`) and `starontology/`
  loaders (`as_oxigraph=True` becomes the only return type; the flag goes).
- A3. Engine modules that import rdflib (13 files) use only `terms.py`'s pyoxigraph forms; ban `import rdflib` in the engine with an
  AST test, as `str(term)` already is.
- Gate: `tests/shacl`, `tests/shacl_engine`, W3C engine suites, `tests/starontology`; the guides 04–05 run unchanged apart from
  imports; the workbench trial branch needs no snapshot conversion.

**Phase B: SPARQL layers off rdflib.**
- B1. Query/Update execution: the Oxigraph backend is the only backend; remove the `rdf-1.1` backend, `tt:` encoding use, and the
  evaluator patches (~2,440 lines), the lowering layer and its cache (~1,180). Port query-time RDF/RDFS entailment onto the sqe
  tree (`entailment_rdf.py`, `entailment_rdfs.py` rewrite rdflib algebra today).
- B2. SRL onto the new parser (`parse_srl`; decision 10): retire pyparsing-on-rdflib's-grammar and `_grammar12.py`. Gate: SRL's 929
  tests pass unchanged.
- B3. sqe, spexpr: drop rdflib imports (sqe 5 files, `sparql/` 19 files).
- B4. Retire salg as decided (steps 1–3 of `salg-retirement-analysis.md`, then the encoder).
- Gate: `tests/sparql`, `tests/graph/w3c_sparql12`, SRL and SQE suites; the nested `FILTER EXISTS` slowdown measured and either
  accepted or rewritten.

**Phase C: parsers, serializers and the rest of `graph/`.**
- C1. Delete the hand-written parsers and serializers Oxigraph replaces (~5,600 lines; not Manchester, pretty Turtle). Gate: the W3C
  RDF 1.2 syntax suites pass against Oxigraph's parsers (**not yet run**: do this first, it decides how much can go).
- C2. Delete TriX (decided), `compare.py` and `rdfc.py` once Oxigraph canonicalisation covers their corpus, the rdflib stores,
  `Resource`, the 29-binding prefix manager.
- C3. `owl_dl`, `shape_derivation`, entailment and imports: already ported to the wrapper as helpers; delete the rdflib originals.

**Phase D: the switch.**
- D1. Rename `OxGraph` → `StarLayerGraph`, `OxDataset` → `StarLayerDataset`; delete the rdflib subclass (`graph/graph/starlayer_graph.py`,
  `starlayer_dataset.py`, `_rdflib_inherited_contract.py`).
- D2. Mechanical migration of 210 test files and the guides: rdflib term classes become pyoxigraph ones; tests that exercised old-class
  behaviour are deleted when the behaviour was dropped (the "give-ups" in plan section 4), rewritten otherwise.
- D3. Regenerate docs, API reference, code KG and notebook links; rerun all notebooks.
- D4. Remove rdflib from core dependencies (move to an optional extra); update `AGENTS.md` and the package `CLAUDE.md` files.

**Phase E: before replacing `main`.** Full suite, `build.py --check`, notebooks, workbench integration redone on the final API, CI.

## 4. Risks and open points

- The old class is the internal currency: Phases A and B change what every caller gets back. Expect the biggest churn in tests, not
  in the library.
- Evidence for "identical behaviour" is thinner than it looks (most old suites ran on the rdf-1.1 backend): each phase's gate must run
  the suites on the new default, not behind a flag.
- Parsing a tree: triple order follows the source, not rdflib's `reorderTriples`, which can move blank-node order in golden files.
- `owlrl` and the OWL-DL paths need an rdflib copy; keep the conversion in one module (`_rdflib_bridge.py`).
- Remote engines (Fuseki, `oxigraph serve`) were not exercised by the spikes.
- Third-party code expecting an rdflib `Graph` breaks (accepted in the original plan).
- `uv.lock` and the dependency change in D4 need a machine with `uv`.

## 5. Decisions (recorded 2026-11-03)

1. **Phases A and B run in parallel**, on separate branches (`mig-native-shacl`, `mig-native-sparql`), each from `shacl-engine`.
   They meet in `graph/` and `shacl/normalization.py`; merge A first, then rebase B.
2. **`from_rdflib` is supported; `to_rdflib` emits the basic encoding** (see section 2). `to_rdflib` is built on `interop.to_rdf11`.
3. **The rename (D1) gets its own branch**, started only after A, B and C are merged and green. That is the safest option.
