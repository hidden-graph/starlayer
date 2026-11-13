# E2 notes: the small rdflib removals (branch `mig-e2-small`, from `shacl-engine` 57dedd8)

Goal (owner): shacl-engine is fully converted off rdflib before it replaces main. rdflib may remain only for `from_rdflib` / `to_rdflib`,
`owlrl` through `graph/oxgraph/_rdflib_bridge.py`, the OWL-DL exporters, and as an optional extra. E2 covers the small items of the D4
follow-up list (5, 8, 4, and the "term types only" conversions). E1 (sqe, spexpr, vocab, to_rdf, from_rdf, expr_text) and E3 (Manchester) are not touched.

## 1. Dead encoding code (D4 follow-up 5)

Proof of deadness is a grep of `packages scripts tools` for every name of `graph/model/encoding.py` (`tt_hash`, `term_key`, `TT_NS`, `BN_NS`,
`TT_*`, `ENCODING_*`, `lookup_tt_hash`, `remember_tt_hash`, `canonicalize_query_result_value`, `restore_select_bindings`,
`inject_missing_tt_encoding`, `_reencode_tt`, `encoding_triples`). Outside `encoding.py` and its own test, the only hits were comments,
the KG tests/curated files, a test of `ENCODING_PREDS`, and `benchmarks-graph/bench_scaling.py` (imports the deleted `backends.native`, dead already).

- `graph/model/encoding.py` is **deleted** (433 lines). The three dirlang helpers that had live callers (`DIRLANG_NS`, `encode_dirlang_datatype`,
  `decode_dirlang_datatype`) moved to `graph/model/dirlangstring.py` (`DIRLANG_NS` is `interop.DIRLANG_NS`); they work on IRI text.
  The bridge imports `decode_dirlang_datatype` from there. `tests/graph/unit/test_encoding.py` (tt_hash memo tests) is deleted.
- `graph/compare.py` kept only `isomorphic` (300 lines to 45). `graph_diff`, `to_isomorphic`, `to_canonical_hash` are gone with their tests
  (nothing but tests called them; `rdflib.compare` is used directly by a few tests and scripts). `isomorphic` now canonicalises natively for every input;
  an rdflib `Graph` / `Dataset` is converted first through `to_oxgraph` / `to_oxdataset` of the bridge.
  The triple-term decomposition helpers (`_decompose`, `_decompose_quads`) moved to the bridge as `decompose` / `_decompose_quads`: only the rdflib
  reasoners (`owl_dl*.py`, `rdflib_graph`) and one test need a triple-term-free rdflib graph.
- **`graph/rdfc.py` is kept, as a 40-line front over `rdfc_native`**, not deleted: `rdfc10_hash` and `to_canonical_nquads` are used by guide
  notebooks 06c and 04f, the curated KG (`functionality.ttl`, `notebook-links.ttl`) and `tests/graph/oxgraph/test_library_entry_points.py`, and an app may call
  them. The 410-line pure-Python canonicaliser, its `permutation_budget` argument and the hash algorithms other than SHA-256 / SHA-384 are gone
  (the specification names those two). For a graph without triple terms the output is the plain RDFC-1.0 text, identical to before (the committed
  hash in 06c is unchanged). **For a graph with triple terms the canonical text and hash change**: they now come from the Interoperability basic encoding
  (`rdfc_native` documents it) instead of the removed `urn:starlayer:canon-tt#` decomposition. Deleted tests: `test_rdfc.py` (rewritten, 6 tests),
  `test_rdfc_hunt2.py`, `test_rdfc_remainders_103.py`; two cross-checks against the removed code in `test_rdfc_native.py` became oracle-only tests.
- KG: `tests/kg` and `query-library.ttl` used `tt_hash` as the fixture symbol. They now use `starlayer.graph.interop.to_basic` (caller
  `rdfc_native.canonical_quads`). `functionality.ttl` cites `dirlangstring` and `interop`.

## 2. Poison-graph guard (follow-up 8, non-spec row 27)

`rdfc_native.check_complexity` runs before every native canonicalisation (also inside `isomorphic`) and raises `CanonicalizationComplexityError`
(defined in `rdfc_native`, re-exported by `rdfc`). Measured on pyoxigraph 0.5.13 (the cost of one RDFC-1.0 run): a 7-blank-node clique 1.3 s, an
8-clique 13 s, a 9-clique and larger do not finish; K(5,5) 3 s, K(6,6) does not finish; a 4 x 4 torus 0.2 s, a 6 x 6 torus does not finish; a
200-node cycle 1.4 s; leaves and a hub with 500 blank children are instant. A node-degree rule does not separate these (a torus has degree 4), so the
guard is: colour refinement (a blank node is coloured by its quads and the colours of its neighbours, until stable, at most 64 rounds), then the blank
nodes that share a colour with another are linked by the quads that join them, and a connected group whose cycle rank (edges - nodes + 1) exceeds 20
is refused. Paths, trees, one cycle, and any number of interchangeable leaves never trigger it; the W3C suite (64 evaluations) is unaffected; test074 now
passes as a negative test instead of being skipped. **Limit**: it is a heuristic. A long blank-node path is not caught: Oxigraph finishes it but slowly
(500 nodes 4.0 s, 700 nodes 12.9 s, 1000 nodes 35.0 s, roughly cubic; a 500-node cycle 4.7 s; an 8-clique 3.1 s on a machine about 4x faster than the one above). The right fix is upstream (a work limit in the canonicaliser); row 27 says so.

## 3. SHACL UI widget selection on pyoxigraph terms

`shacl/ui_widget_selection.py` reads `StarLayerGraph` / `StarLayerDataset` / `pyoxigraph.Store` directly (no `to_rdflib_graph` snapshot, no `_via_rdflib`).
`SHUI` is a `starlayer.shacl_engine.terms.NS` of `NamedNode`s. The probe shapes graph of the conformance check is a `StarLayerGraph` copy of the shapes
(with the target declarations dropped), as before in rdflib. The public functions keep accepting rdflib graphs and nodes: `_Boundary` converts them in
(`to_oxgraph`, `from_rdflib_term`) and converts the answer out. **Rule for the answer**: pyoxigraph terms when `shape_node` or `focus_node` is a
pyoxigraph term, else rdflib terms (also for `WidgetChoice.property_shape`, `candidates[i].widget`, `data_checks`). `shacl.select_widget(s)` are plain
imports again and are back in `shacl.__all__`. `starontology.PROF`'s companion change is in section 4. The module needs no rdflib to import or to run
on Oxigraph graphs (`tests/test_core_without_rdflib.py`).

## 4. `starontology.get_resource_iri()` and `PROF`

`get_resource_iri(name)` always returns a `pyoxigraph.NamedNode` (it returned an rdflib `URIRef` when rdflib was installed). `starontology.PROF` is now an
`NS` of `NamedNode`s instead of an rdflib `Namespace`. Guides 05d and 04e print / pass the value; their stored outputs show the old plain text until re-run
(notebooks are not edited here).

## 5. The remaining conversions

- `graph/graph/shape_derivation.py` **deleted** (580 lines): `derive_shape` is `oxgraph/helpers/shapes.py`; the test now reads `DEFAULT_IGNORED_PROPERTIES` from there.
  `functionality.ttl` cites the native function.
- `graph/graph/entailment_regimes.py` re-exports `ENTAILMENT`, `KNOWN_REGIMES`, `SUPPORTED_REGIMES` from `oxgraph/helpers/entailment.py` (pyoxigraph
  `NamedNode`s; the two sets hold IRI text). Every caller passes `ENTAILMENT.X` as `inference=` / `entailment=`, which takes either family.
- `graph/model/triple.py` and `dirlangstring.py` had no module-level rdflib use left (D4); `dirlangstring.encode_dirlangstring` keeps a lazy rdflib import
  (it makes the rdflib `Literal` that carries a direction as a datatype; used by test support).
- `owl_dl.py` and `owl_dl_rustdl.py` are **unchanged except** that they import `decompose` from the bridge: they build rdflib graphs for HermiT / rustdl, so
  they keep `import starlayer._needs_rdflib` (the clear `ImportError`). The `import starlayer._needs_rdflib` guards were removed from `rdfc.py` (the file is
  rdflib-free) and `shape_derivation.py` (deleted).

## 6. Decisions for the owner

1. `rdfc.py` stays as the public front (notebooks use it). Triple-term graphs hash differently than before. Say if you would rather the notebooks use `rdfc_native`.
2. The poison guard is a heuristic with a stated limit; the real fix is a work limit upstream in Oxigraph's canonicaliser (add to the upstream list).
3. `select_widget(s)` answer family follows the node arguments (rdflib nodes in, rdflib out) for compatibility with the existing tests and guide 04d.
4. Hash algorithms other than SHA-256 / SHA-384 are no longer accepted by `rdfc10_hash`.
