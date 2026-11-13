# D2 delete list: tests D1 deletes with the old classes (2026-11-06)

Branch `mig-d2-oxgraph-tests` (from `shacl-engine` at 970a97e). Tests only; nothing was deleted. Every test whose subject is
behaviour the library keeps now runs on `OxGraph` / `OxDataset` (or on a plain `rdflib.Graph` where the old class was only an
rdflib-term vehicle). What is listed here tests dropped behaviour and still runs on the old class, so D1 can delete it. Paths are under
`packages/starlayer/tests/`; counts are collected test items (parameters count). A mixed file was split: its dropped-behaviour tests
moved verbatim (old class names) into `<name>_oldclass.py`, which D1 deletes whole.

## 1. Whole files (untouched)

| File | Tests | Lines | Reason |
|---|---:|---:|---|
| graph/integration/test_cross_backend_parity.py | 48 | 505 | backend parity (rdf-1.1 vs rdf-1.2) |
| graph/integration/test_fuseki_backend.py | 41 | 677 | rdflib SPARQLUpdateStore / Fuseki through the old class |
| graph/integration/test_oxigraph_backend.py | 69 | 1157 | old class over an OxigraphStore / HTTP Oxigraph, `tt:` encoding |
| graph/integration/test_oxigraph_store_rdf12.py | 46 | 470 | old class over an OxigraphStore vs in memory |
| graph/integration/test_sqlalchemy_backend.py | 10 | 230 | rdflib-sqlalchemy store |
| graph/integration/test_blank_node_identity.py | 15 | 136 | store-backed old class, `skolem_semantics` |
| graph/integration/test_entailment_native.py | 5 | 168 | `entailment="native"` against a reasoning Fuseki |
| graph/oxgraph/test_conformance.py (+ conformance.py, 578 lines) | 25 | 41 | old-vs-new comparator |
| graph/oxgraph/test_helpers_conformance.py | 199 | 606 | old-vs-new comparator |
| graph/unit/test_direct_query.py | 6 | 58 | rdflib direct query path |
| graph/unit/test_lexer.py | 52 | 302 | hand-written lexer |
| graph/unit/test_syntax.py | 64 | 436 | hand-written Turtle syntax |
| graph/unit/test_native_and_update_hunt2.py | 8 | 77 | `backends.native` |
| graph/unit/test_ntriples12.py | 1 | 32 | hand N-Triples parser |
| graph/unit/test_operator_patches.py | 24 | 108 | rdflib evaluator patches |
| graph/unit/test_parser_fixes.py | 110 | 260 | hand-written parser |
| graph/unit/test_parser_fixes_hunt2.py | 58 | 134 | hand-written parser |
| graph/unit/test_query_prepare_cache.py | 12 | 258 | prepared-query cache |
| graph/unit/test_rdflib_inherited_contract.py | 4 | 98 | the old class's rdflib contract |
| graph/unit/test_remote_decompose.py | 4 | 131 | remote decomposition |
| graph/unit/test_skolem_semantics.py | 14 | 76 | store skolem semantics |
| graph/unit/test_trig12_parser.py | 9 | 116 | hand TriG parser |
| graph/unit/test_trig12_round_trip.py | 10 | 67 | hand TriG parser / writer |
| graph/unit/test_trig_graph_blocks.py | 12 | 89 | hand TriG parser vs rdflib |
| graph/unit/test_trig_unterminated_block.py | 6 | 50 | hand TriG parser |
| graph/unit/test_turtle12_serializer.py | 52 | 593 | hand-written Turtle writer |
| graph/unit/test_turtle_parser.py | 82 | 912 | hand-written Turtle parser (uses the `parser` fixture of graph/conftest.py) |
| graph/unit/test_turtle_parser_errors.py | 15 | 145 | hand-written Turtle parser |
| graph/unit/test_lowering_hunt3.py | 51 | 224 | lowering |
| graph/unit/test_proposition_form_encoding.py | 14 | 137 | plain turtle parse adopting the basic encoding (O4: not adopted) |
| graph/unit/test_is_triple_filter_join.py | 14 | 108 | lowering of isTRIPLE |
| graph/unit/test_sparql12_parse.py | 31 | 346 | `parseQuery` / `prepareQuery` / `processUpdate` of the rdflib query machinery |
| graph/w3c_turtle12/test_w3c_turtle.py | 106 | 235 | hand Turtle parser (superseded by w3c_rdf12) |
| sparql/unit/test_lower_rdf11.py | 89 | 802 | lowering |
| sparql/unit/test_phase3_rdf12.py | 8 | 149 | lowering / algebra round trip |
| sparql/unit/test_entailment_rdf.py | 10 | 136 | `sparql/entailment_rdf.py`, deleted at D1 |
| sparql/unit/test_entailment_rdfs.py | 87 | 369 | `sparql/entailment_rdfs.py`, deleted at D1 |
| shacl/integration/test_native_backend_oxigraph.py | 12 | | old class over an `OxigraphStore` / server (rdf-1.1 / rdf-1.2 modes) |
| shacl/integration/test_native_backend_oxigraph_store.py | 4 | | same, in-process `OxigraphStore` |
| shacl/w3c_shacl12/stores.py (support module) | 0 | 149 | factories over rdflib stores for the opt-in `--store-matrix`; D1 also removes its use sites in `w3c_shacl12/conftest.py`, `test_w3c_validate.py`, `test_w3c_infer.py` |

## 2. Split files (`*_oldclass.py`, delete whole)

| File | Tests | Lines | Reason |
|---|---:|---:|---|
| graph/unit/test_io_hunt3_oldclass.py | 12 | 114 | RDF/XML XML 1.0 character check, prefix `xml`/`xmlns`, UTF-8 BOM (see gaps) |
| graph/unit/test_parsers_r4_oldclass.py | 14 | 198 | `~ []` reifier, empty TriG graph, JSON-LD triple terms (gaps) |
| graph/unit/test_update_hunt3_oldclass.py | 12 | 24 | `TypeError` for a non-str query / update (gap) |
| graph/unit/test_contracts_hunt3_oldclass.py | 2 | 26 | hand Turtle splitter |
| graph/unit/test_prefixes_oldclass.py | 1 | 13 | blank-node identity of a reduced copy |
| graph/unit/test_starlayer_graph_oldclass.py | 33 | 525 | rdflib Graph subclass, store lifecycle, `tt:` registry, tuple wildcards, SPARQLUpdateStore |
| graph/unit/test_dataset_oldclass.py | 19 | 376 | rdflib Dataset instance, context cache, store lifecycle, raw cache, `triples_choices`, longturtle |
| graph/unit/test_graph_core_round4_oldclass.py | 3 | 42 | oxrdflib-store dataset variants |
| graph/unit/test_unbind_prefix_oldclass.py | 2 | 21 | unbind on rdflib stores |
| graph/unit/test_leftovers_72_75_83_oldclass.py | 11 | 56 | native store accepting unsafe blank node labels |
| graph/unit/test_rdf12_formats_oldclass.py | 3 | 169 | RDF/XML `parseType="Triple"` reads, `n3-12` alias |
| graph/unit/test_entailment_oldclass.py | 11 | 187 | `entailment="native"` on a store, owl-rl closure cache |
| graph/unit/test_dirlangstring_oldclass.py | 5 | 111 | `longturtle12`, `backends.native.sparql_term` |
| graph/unit/test_infer_oldclass.py | 1 | 84 | `infer` on a store-less native graph |
| graph/unit/test_conformance_oldclass.py | 12 | 185 | `sparql_api` VERSION tests, `native_update` rdf-1.1 |
| graph/unit/test_interop_oldclass.py | 3 | 95 | comparison with the `tt:` encoding |
| graph/unit/test_group_filter_falsy_literal_oldclass.py | 19 | 49 | rdflib Graph variant, algebra patch idempotence |
| graph/w3c_sparql12/test_w3c_sparql12_eval_oldclass.py + harness_oldclass.py | 110 | 552 + 462 | live Oxigraph / Fuseki / OxigraphStore variants of the W3C eval on the old class |
| graph/oxgraph/test_migration_gaps_oldclass.py | 1 | 125 | `from_rdflib` of an old-class graph with a triple term |
| sparql/unit/test_remainders_93_oldclass.py | 2 | | `rdf11_to_sparql11_text` (lowering) |
| shacl/unit/test_engine_normalization_oldclass.py | 1 | | normalising an old-class instance |
| shacl/unit/test_graph_protocol_contract_oldclass.py | 1 | | old class vs `StarLayerGraphProtocol`; NOT dropped behaviour, gap G2 |

Also removed from migrated files without a copy (old-vs-new comparators; see the commit messages): 3 tests of
`graph/unit/test_update_hunt3.py` (mem vs ox store comparator, triple-term-refused update, prepared query accepted) and 4 REPLACE
tests of `test_contracts_hunt3.py` (pinned by the strict xfails of `test_oxigraph_deviations.py`).

Also at D1: the `parser` fixture of `graph/conftest.py` (used only by D files above and `test_starlayer_graph_oldclass.py`; it imports the
hand parser lazily now). `fixture_ttl` stays if a kept test uses it.

The opt-in `--sqe-coverage` files (`test_sqe_features.py`, `test_sqe_property_based.py`, `test_parser_differential.py`) are on OxDataset
now (gap G10 resolved on `mig-d2-fixes`); no old-class reference is left in them.

Totals: 39 whole-file entries (about 1,260 collected tests, about 9,800 lines, counting the 4 shacl entries) and 24 `*_oldclass`
files (about 280 tests, about 3,500 lines including the 2 W3C harness files). Old-class references left in tests: see the final report.
