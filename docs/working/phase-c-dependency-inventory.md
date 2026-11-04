# Phase C1: dependency inventory of the old graph machinery (2026-11-04)

Branch `mig-phase-c`. Who imports each module of `starlayer/graph/{parsers,serializers,backends,graph,query}`, `compare.py`,
`rdfc.py`, `rdfc_native.py` and `starlayer/sparql/{lower_rdf11,serialize12,parse12,_grammar12}`, found by walking every
`import` in `starlayer/`, `tests/`, `scripts/` and `tools/` with `ast` (lazy imports inside functions included; a name re-exported
by a package `__init__` is followed to its defining module). Calls through a string (`parse(format='turtle12')`) are not imports:
that is how the old class reaches its parsers, and why the old class is the only caller of most of them.

**Classes**

- **a**: no live caller. Imported only by `StarLayerGraph`/`StarLayerDataset` (`graph/graph/starlayer_graph.py`,
  `starlayer_dataset.py`), by `_rdflib_inherited_contract.py`, by other class-a modules, or by the facade `__init__` files
  (`starlayer`, `graph`, `graph.graph`, `graph.query`, `graph.serializers`, `graph.parsers`) that re-export them. Computed as the
  modules not reachable from any module outside the list without passing through the old class or a facade.
- **b**: a live non-test module outside the old class imports it (named in the column). "Live" here still includes code that is itself
  waiting on the old class (`sparql/srl_eval.py`, `sparql/check.py`); those are listed in the second table.
- **c**: tests only.

## Deleted in this phase

| What | Lines | Why it was safe |
|---|---:|---|
| `graph/parsers/trix12.py`, `graph/serializers/trix12.py` | 324 | TriX is dropped (decision 2026-10-31); only the old class imported them. The old classes now raise `ValueError("TriX is not supported ...")` for `trix` and `trix12`. |
| TriX tests (`test_rdf12_formats.py` TriX classes, `TestOxigraphTrix12Parse`, six single tests, five parametrised cases) | about 340 | Each tested the deleted format; the one behaviour kept (a clear error) has `test_trix_is_refused`. `tests/graph/oxgraph/test_behaviour.py` already asserts that `OxGraph` rejects `trix`. |

## Module table

| Module | Lines | Class | Live non-test importers | Test files | Disposition |
|---|---:|---|---|---:|---|
| `graph.parsers.bnode_scope` | 44 | b | graph.parsers.turtle_parser | 0 | follows turtle_parser |
| `graph.parsers.errors` | 128 | b | graph.parsers.lexer, graph.parsers.manchester_parser, graph.parsers.syntax, graph.parsers.turtle_parser, starontology.manchester | 15 | keep the Manchester part (`manchester_parser`, `starontology.manchester` use it); shrink at D1 |
| `graph.parsers.faithful` | 46 | a | - | 0 | delete at D1 (old class, rdfxml12) |
| `graph.parsers.lexer` | 313 | b | graph.parsers.syntax, graph.parsers.turtle_parser | 2 | follows turtle_parser (also `syntax`) |
| `graph.parsers.manchester_parser` | 1672 | b | graph.oxgraph.core, starontology.manchester | 7 | keep (Manchester stays hand-written) |
| `graph.parsers.ntriples12` | 376 | a | - | 0 | delete at D1 (Oxigraph 70/70 + 27/27 on the W3C N-Triples/N-Quads gate, bar the `VERSION` directive) |
| `graph.parsers.rdfxml12` | 360 | a | - | 1 | delete at D1 (wraps rdflib's RDF/XML parser; Oxigraph passes more) |
| `graph.parsers.syntax` | 847 | b | graph.parsers.turtle_parser | 2 | follows turtle_parser |
| `graph.parsers.trig12` | 477 | a | - | 2 | delete at D1 (Oxigraph 61/61 and 357/357) |
| `graph.parsers.turtle_parser` | 1307 | b | sparql.parse_sparql | 4 | delete at D1 after moving `_join` (one 5-line function) out of it: `sparql/parse_sparql.py` is the only live caller |
| `graph.serializers._xml` | 49 | a | - | 0 | delete at D1 (rdfxml12 writer only) |
| `graph.serializers.manchester` | 715 | b | graph.oxgraph.core | 1 | keep (Manchester stays hand-written) |
| `graph.serializers.ntriples12` | 168 | a | - | 0 | delete at D1 (Oxigraph writes the W3C canonical form 41/41 and 41/41; this one 7/41 and 8/41) |
| `graph.serializers.rdfxml12` | 203 | a | - | 0 | delete at D1 |
| `graph.serializers.trig12` | 83 | a | - | 0 | delete at D1 (`oxgraph/pretty.py` is the pretty TriG) |
| `graph.serializers.turtle12` | 895 | b | graph.graph.prefixes, sparql.sqe.expr_text, sparql.sqe.to_text | 2 | delete at D1 after moving `_PN_LOCAL` (a regexp) out of it: `sparql/sqe/expr_text.py` and `to_text.py` import only that; `oxgraph/pretty.py` is the pretty Turtle |
| `graph.backends._versions` | 35 | b | graph.backends.native_oxigraph, graph.oxgraph.core, shacl_engine.terms | 1 | keep: live (`oxgraph.core`, `shacl_engine.terms`) |
| `graph.backends.native` | 799 | b | graph.backends.native_oxigraph, graph.oxgraph.run, shacl_engine.oxigraph_view, sparql.srl_eval | 3 | delete at D1 after moving `inject_init_bindings`, `check_native_version_conformance` and `sparql_term` (live callers: `oxgraph/run.py`, `shacl_engine/oxigraph_view.py`, `sparql/srl_eval.py`) |
| `graph.backends.native_oxigraph` | 137 | b | graph.backends.native | 0 | follows native |
| `graph.backends.skolem_semantics` | 166 | b | graph.backends.native | 1 | follows native (its one test goes too) |
| `graph.graph._rdflib_inherited_contract` | 312 | a | - | 1 | delete at D1 (checks the old class against rdflib) |
| `graph.graph._timeout` | 193 | b | graph.graph.owl_dl, graph.graph.owl_dl_rustdl | 5 | keep with owl_dl* |
| `graph.graph.entailment_regimes` | 52 | b | sparql.salg.sparql_shapes, sparql.sqe.shapes, sparql.srl, sparql.star_query, starontology.manchester | 28 | keep: five live callers (IRI constants); relocate at D1 |
| `graph.graph.owl_dl` | 249 | b | graph.graph.owl_dl_rustdl, graph.oxgraph.helpers.entailment | 4 | NOT replaced: `oxgraph/helpers/entailment.py` calls it through the rdflib bridge. Owner decision: port or keep |
| `graph.graph.owl_dl_rustdl` | 337 | b | graph.oxgraph.helpers.entailment | 1 | same as owl_dl |
| `graph.graph.prefixes` | 136 | b | graph.serializers.turtle12 | 1 | delete at D1 (the rdflib-style prefix manager; used by the old class and `turtle12`) |
| `graph.graph.shape_derivation` | 580 | b | graph.oxgraph.helpers.shapes | 1 | NOT replaced: `oxgraph/helpers/shapes.py` copies to an old graph and calls it. Owner decision: port (580 lines over pyoxigraph terms) or keep through the bridge |
| `graph.graph.starlayer_dataset` | 1223 | a | sparql.srl_eval, scripts/build.py, tools/kg/codekg/__init__.py, tools/kg/codekg/extractor/build.py | 39 | D1: renamed over by `OxDataset` |
| `graph.graph.starlayer_graph` | 4011 | a | graph.backends.native, graph.oxgraph._rdflib_bridge, graph.serializers.turtle12, shacl.ui_widget_selection, sparql.check, sparql.spexpr_codec, sparql.srl_eval, starontology, starontology.manchester, tools/kg/codekg/__init__.py, tools/kg/codekg/queries.py | 154 | D1: renamed over by `OxGraph` |
| `graph.query.algebra_translator_patches` | 344 | b | sparql.lower_rdf11 | 1 | delete at D1 with lower_rdf11 (patches rdflib's algebra translator) |
| `graph.query.builtin_error_patches` | 879 | b | graph.query.operator_patches | 0 | delete at D1 (rdflib engine patch; chain native -> operator_patches -> this) |
| `graph.query.custom_functions` | 552 | a | - | 0 | delete at D1 |
| `graph.query.direct` | 176 | a | - | 1 | delete at D1 |
| `graph.query.evaluate_patches` | 1266 | b | graph.query.builtin_error_patches | 0 | delete at D1 (rdflib engine patch) |
| `graph.query.operator_patches` | 477 | b | graph.backends.native, graph.backends.native_oxigraph, graph.query.builtin_error_patches | 1 | delete at D1 (rdflib engine patch) |
| `graph.query.path_patches` | 159 | a | - | 0 | delete at D1 |
| `graph.query.query_cache` | 172 | a | - | 2 | delete at D1 |
| `graph.query.remote_decompose` | 322 | a | - | 1 | delete at D1 |
| `graph.query.result_patches` | 76 | a | - | 0 | delete at D1 |
| `graph.query.sparql_api` | 220 | a | - | 3 | delete at D1 |
| `graph.query.update_patches` | 360 | a | - | 0 | delete at D1 |
| `graph.query.version_directive` | 133 | b | graph.backends.native | 3 | delete at D1 (`VERSION` handling for the rdflib engine; native only) |
| `graph.compare` | 300 | b | graph.graph.owl_dl, graph.graph.owl_dl_rustdl, graph.oxgraph._rdflib_bridge, graph.rdfc, scripts/build_kg.py | 17 | NOT deletable: `owl_dl*` and `oxgraph/_rdflib_bridge.py` (`_decompose_quads`) and `scripts/build_kg.py` (`isomorphic`) call it. `isomorphic`/`to_canonical_hash` are covered by `rdfc_native`; `graph_diff`/`to_isomorphic` are not |
| `graph.rdfc` | 410 | b | graph.compare | 5 | follows compare; also owner decision (poison-graph guard, label differences) |
| `graph.rdfc_native` | 122 | c | - | 6 | new code (keep) |
| `sparql.lower_rdf11` | 1971 | b | graph.backends.native, sparql.srl_eval | 4 | delete at D1 once `sparql/srl_eval.py` is off the old class |
| `sparql.serialize12` | 542 | b | sparql.sqe.expr_text, sparql.sqe.to_text | 7 | live (`sqe/expr_text.py`, `sqe/to_text.py`); outside Phase C |
| `sparql.parse12` | 341 | b | graph.backends.native, sparql.check, sparql.star_query, tools/kg/codekg/queries.py | 17 | live (`sparql/check.py`, `star_query.py`, `tools/kg/codekg/queries.py`, `backends.native`); outside Phase C |
| `sparql._grammar12` | 932 | b | sparql.parse12 | 2 | follows parse12 (two test conftests install it) |

Totals: of the 25,700 lines in this table, about 20,400 are class a or follow a module that is (the old classes themselves are
5,234 of them) and go at D1; about 4,900 stay (Manchester, `_versions`, `entailment_regimes`, `serialize12`, `parse12`,
`_grammar12`, `rdfc_native`) or need a decision (`owl_dl*`, `shape_derivation`, `compare`, `rdfc`).

## What the live callers are (the real D1 prerequisites)

Almost everything above is held by a handful of live modules that still sit on the old class or on an old helper. Phases A and B
did not remove these:

| Live module | Old thing it still uses | Fix |
|---|---|---|
| `sparql/srl_eval.py` | `StarLayerGraph`/`StarLayerDataset`, `lower_rdf11`, `backends.native.sparql_term` | SRL evaluation onto the OxGraph path |
| `sparql/check.py`, `sparql/spexpr_codec.py` | `StarLayerGraph` | take an `OxGraph` |
| `shacl/ui_widget_selection.py` | `StarLayerGraph` (builds scoring graphs, converts an `OxGraph` into a snapshot) | build and read `OxGraph` |
| `starontology/__init__.py`, `starontology/manchester.py` | loaders create a `StarLayerGraph` and convert (`_as_oxigraph`) | Phase A2 leftover: load into `OxGraph` directly |
| `graph/oxgraph/_rdflib_bridge.py` | `starlayer_graph`, `compare._decompose_quads` | the bridge builds old graphs for owlrl/OWL-DL; move `_decompose_quads` in |
| `graph/oxgraph/helpers/{entailment,shapes}.py` | `owl_dl`, `owl_dl_rustdl`, `shape_derivation` (called through the bridge; the helpers wrap the originals, they do not replace them) | port or keep |
| `graph/oxgraph/run.py`, `shacl_engine/oxigraph_view.py` | `backends.native` (`inject_init_bindings`, `check_native_version_conformance`) | move three helpers (about 80 lines) |
| `sparql/parse_sparql.py` | `parsers.turtle_parser._join` | move one 5-line function |
| `sparql/sqe/expr_text.py`, `to_text.py` | `serializers.turtle12._PN_LOCAL` | move one regexp |
| `tools/kg/codekg/{__init__,queries,extractor/build}.py`, `scripts/build.py`, `scripts/build_kg.py` | `StarLayerGraph`/`StarLayerDataset`, `compare.isomorphic`, `parse12` | tooling onto `OxGraph` and `rdfc_native` |
| `sparql/{salg/sparql_shapes,sqe/shapes,srl,star_query}.py`, `starontology/manchester.py` | `graph/entailment_regimes.py` (IRI constants) | relocate the constants |

After those, class b collapses to class a for the parsers, serializers, backends, query patches and `lower_rdf11`.

## Tests

- `tests/graph/w3c_turtle12/` (106 tests, hand-written parser) is superseded by `tests/graph/w3c_rdf12/` (427 tests against Oxigraph);
  delete it at D1.
- Test files that import a class-a module and exist only to test it (`test_turtle_parser*.py`, `test_trig12_parser.py`,
  `test_trig12_round_trip.py`, `test_ntriples12.py`, `test_turtle12_serializer.py`, `test_lexer.py`, `test_syntax.py`,
  `test_native_and_update_hunt2.py`, `test_operator_patches.py`, `test_direct_query.py`, `test_query_prepare_cache.py`,
  `test_remote_decompose.py`, `test_rdflib_inherited_contract.py`, `test_lowering_hunt3.py`, `sparql/unit/test_lower_rdf11.py`)
  go with the module. Tests that use `StarLayerGraph` as a fixture (154 files for `starlayer_graph`, 39 for `starlayer_dataset`) are
  D2.
- `tests/graph/integration/test_sqlalchemy_backend.py` and `test_fuseki_backend.py` exercise rdflib stores through the old class;
  they go with it (the "rdflib stores" item of the plan has no code of its own: the stores and `Resource` are inherited from
  rdflib, and the prefix manager is `graph/prefixes.py` plus `namespace_manager` use in the old class).

## C2 and C3 outcome

| Item | Result |
|---|---|
| TriX | deleted (above) |
| Hand-written parsers/serializers | the Oxigraph gate passes (`phase-c-parser-measurement.md`), but every one is imported by the old class: **delete at D1** |
| `compare.py`, `rdfc.py` | **not deleted**. `isomorphic` and `to_canonical_hash` are covered by `rdfc_native` (W3C RDFC-1.0: 64/64 evaluation tests, 0 verdict disagreements in 2,500 random datasets; `interop-and-rdfc.md`), but (1) `owl_dl*`, the rdflib bridge (`_decompose_quads`) and `scripts/build_kg.py` call `compare`; (2) `rdfc.py`'s permutation budget is the only protection against poison graphs (pyoxigraph's canonicaliser does not finish on W3C test074); (3) native and old labels differ for quads that repeat a blank node (701 of 2,047 such datasets); (4) `graph_diff`/`to_isomorphic` have no native equivalent. Decision needed (below). |
| rdflib stores, `Resource`, prefix manager | no separate code to delete (see Tests); `graph/prefixes.py` goes at D1 |
| `owl_dl`, `owl_dl_rustdl`, `shape_derivation`, `entailment_regimes`, imports | **not deleted; the premise does not hold.** `oxgraph/helpers/imports.py` is a true port (the rdflib original is the `StarLayerGraph` methods, so it goes at D1). `owl_dl*` run on an rdflib copy by design (owlrl and the OWL-DL reasoners need rdflib), and `shape_derivation` is called by the helper through the bridge; neither is replaced. `entailment_regimes.py` is five live modules' IRI constants. |

## Decisions needed

1. `owl_dl`, `owl_dl_rustdl`: keep as the rdflib-bridge consumers (the plan's "owlrl and OWL-DL paths need an rdflib copy"), moving them next
   to `_rdflib_bridge.py`, or drop the OWL-DL paths?
2. `shape_derivation`: port over pyoxigraph terms (580 lines, self-checks through `starlayer.shacl`) or keep through the bridge?
3. `rdfc.py`/`compare.py`: port the permutation budget as a guard in front of `rdfc_native.canonical_*`, settle the self-loop label
   difference upstream, keep or drop `graph_diff`/`to_isomorphic`.
4. N-Triples/N-Quads `VERSION` directive and the Oxigraph XMLLiteral canonicalisation bug (`phase-c-parser-measurement.md`).
