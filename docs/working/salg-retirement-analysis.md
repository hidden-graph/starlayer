# Retiring the salg export: dependencies and the minimal path

Read-only analysis, branch `shacl-engine` (HEAD e4ffd68). Decision taken as given: the `salg:` export (rdflib's resolved SPARQL
algebra encoded as RDF) need not be preserved; sqe stays; a StarLayer-owned parser will replace rdflib as the parser, and execution
will send text to Oxigraph (both separate work). Paths are under `packages/starlayer/starlayer/` unless they start with `tests/`,
`docs/`, `scripts/`, `tools/`. Line counts are `wc -l`. I ran no tests; "unverified" marks anything I did not check in code.
Builds on `docs/working/sparql-layers-exploration.md` (its section 1.2 rule check is confirmed below).

## 1. Inventory

### 1.1 The `sparql/salg/` subpackage (812 lines Python, salg-only)

| File | Lines | What it does |
|---|---|---|
| `salg/__init__.py` | 32 | Exports `ontology_graph`, `find_unbound_projected_variables`, `UnboundProjectedVariable`, and (if pyshacl imports) `shapes_graph`, `validate_query`. |
| `salg/sparql_ontology.py` | 142 | `ontology_graph()`: loads `salg-ontology.ttl` and generates expression-class Turtle from `_EXPR_NODE_FAMILY`. |
| `salg/sparql_shapes.py` | 227 | `shapes_graph()`, `validate_query(graph)`: runs `starlayer.shacl.validate` over an algebra graph using `sparql_shapes.ttl` plus the shared spexpr shapes. |
| `salg/semantic_checks.py` | 203 | `find_unbound_projected_variables`; decodes a `salg:Project` node with `from_rdf._decode`, runs rdflib `_addVars`/`_traverseAgg`/`analyse`, adds a VALUES-row workaround. |
| `salg/native_components.py` | 148 | pySHACL `ConstraintComponent` `salg:noUnboundProjectedVariables` (wraps the check above). |
| `salg/engine_components.py` | 54 | The same component for `shacl_engine` (registers `SALG.NoUnboundProjectedVariablesConstraintComponent`). |
| `salg/expr_families.py` | 6 | Re-export of `sparql/expr_families.py` (not salg content). |

Data files (in `starontology/`, see section 5): `salg-ontology.ttl` 331, `sparql_shapes.ttl` 1,013 (about 100 node shapes, all
`salg:*Shape`, mostly cardinality and rdf:List well-formedness; one `sh:sparql` per list shape).

### 1.2 Top-level encoder, decoder, vocabulary (`sparql/`)

| File | Lines | Salg export (go with it) | Generic / shared (sqe and srl use it) |
|---|---|---|---|
| `to_rdf.py` | 508 | `query_to_rdf`, `update_to_rdf`, `queries_to_collection` (136-235), `_encode_prologue`, `_encode_quads_map`, `_encode_triple_pattern`, `_encode_binding_row` (about 180 lines, estimate from function boundaries) | `_encode` (262), `_encode_comp_value`, `_encode_path` (370), `_encode_list`, `_build_rdf_list`, `_new_starlayer_graph` (112), hooks `_NS_OVERRIDES` (76), `_ENCODE_HOOK` (81), `_comp_value_ns` (about 330 lines) |
| `from_rdf.py` | 599 | `rdf_to_query`, `rdf_to_update`, `rdf_to_collection`, `_decode_prologue`, `_decode_quads_map`, `_decode_binding_row`, `_decode_triple_pattern` (about 160 lines) | `_decode` (259), `_decode_comp_value`, `_decode_path`, `_decode_list(_field)`, `_comp_value_type`, `_discover_expr_evalfns`/`_EXPR_EVALFNS` (104-132, walks rdflib's live grammar), `_DECODE_HOOK` (256) (about 440 lines) |
| `vocab.py` | 344 | `SALG` namespace uses at 303-344 (TriplePattern, TripleTerm, Query, Update, UpdateOperation, QueryCollection markers) | `SPEXPR`, `SQE`, `PY_STR_DATATYPE`, `VARIABLE_DATATYPE`, dirlang helpers (used by `_grammar12`, `serialize12`, `lower_rdf11`) |
| `expr_families.py` | 63 | none | the `_EXPR_NODE_FAMILY` table (rdflib's 63 builtins), used by `to_rdf`, `expr_validation`, spexpr shapes generation |
| `expr_validation.py` | 59 | none | spexpr ontology/shapes loader, used by sqe and srl |
| `ast_vocab.py` 66, `from_ast_rdf.py` 118, `to_ast_rdf.py` 132, `to_ssyn_rdf.py` 282, `ssyn_to_text.py` 268, `ssyn_vocab.py` 80 | 946 | orphan `ssyn:`/`sast:` layers; `ast_vocab.py` re-exports from `vocab.py`; `to_ssyn_rdf.py` calls `to_rdf._encode_path`. Imported by no file outside this group (per exploration doc); 4 test files use them. |

Classification: "salg export" = the root-level algebra functions and the outer-algebra vocabulary; "sqe-owned" = `sqe/` (1,692 lines)
and its two Turtle files; "generic" = the recursive term/expression/path/list codec that both reuse. The line that matters:
**sqe and srl depend on the generic half of the same two files that hold the salg export.** `salg:` terms are not emitted by sqe
(`test_no_salg_terms_in_any_tree`, `tests/sparql/sqe_coverage/test_w3c_through_sqe.py:106`), but code is shared.

### 1.3 What the shared half encodes

`_EXPR_NODE_FAMILY`/`_EXPR_EVALFNS` are rdflib's `Builtin_*` names and rdflib `Expr` objects with live evaluators. sqe stores
expressions as that generic encoding under the `spexpr:` namespace; `sqe/from_rdf.py:76` rebuilds `Expr(name, _EXPR_EVALFNS[name])`
and feeds rdflib's unmodified `translateQuery`. So the "sqe encoder" question is really "an expression/path/term codec independent
of salg", and its final shape depends on what the new parser emits.

## 2. Consumers

### 2.1 Source (everything outside `salg/` that imports or calls into it or the shared codec)

| Consumer | What it uses | Salg export or generic? |
|---|---|---|
| `shacl/meta_shapes.py:500-535` (`check_sparql_query_text`) | `salg.validate_query(query_to_rdf(prepare_query_12(text)))`; `_is_prebound_variable_only_report` (414-437) reads `SALG.NoUnboundProjectedVariablesConstraintComponent` | salg export |
| `shacl_engine/components/extensions.py:23-30` | lazy trampoline to `salg.engine_components.no_unbound_projected_variables`, IRIs built from a hardcoded `_SALG` string | salg export |
| `shacl_engine/component_table.py:116-117` | text row naming the extension | salg export (documentation row) |
| `sparql/srl.py:146-151` | `from_rdf._decode`, `sqe.to_rdf._encode_expr`, `to_rdf._NS_OVERRIDES/_encode/_new_starlayer_graph` (+ lines 614, 642-646, 720-743 use them) | generic |
| `sparql/srl_eval.py:482` | `from_rdf._EXPR_EVALFNS` (to evaluate `Expr` nodes) | generic |
| `sparql/sqe/to_rdf.py:59-61, 136-141, 502` | `_ENCODE_HOOK`, `_NS_OVERRIDES`, `_encode_path`, `_new_starlayer_graph`, `_encode` | generic |
| `sparql/sqe/from_rdf.py:28-29, 76, 84-88` | `_DECODE_HOOK`, `_EXPR_EVALFNS`, `_decode` | generic |
| `sparql/sqe/to_text.py:29, 255` | `_decode` (property paths only) | generic |
| `sparql/sqe/vocab.py:102`, `sqe/expr_text.py:16` | `SQE`, `SPEXPR` datatypes from `vocab.py` | generic |
| `sparql/lower_rdf11.py:173-174, 1643-1827, 1957-1971` | `query_to_rdf`, `update_to_rdf`, `rdf_to_query`, `rdf_to_update`: the lowering path | salg export |
| `graph/query/sparql_api.py:110-117, 163-170` | `query_to_rdf11` -> `rdf11_to_query`; `update_to_rdf11` -> `rdf11_to_update` | salg export (via lowering) |
| `graph/query/query_cache.py:40, 162-163` | same pipeline, cached | salg export (via lowering) |
| `graph/graph/starlayer_graph.py:2729-2748`, `graph/graph/starlayer_dataset.py:1048-1069`, `graph/backends/native.py:803-822` | `update_to_rdf11` (+ `rdf11_to_update`, text rendering) for updates and remote-store text | salg export (via lowering) |
| `sparql/__init__.py:11-15, 55-60` | public re-exports: `query_to_rdf`, `rdf_to_query`, `update_to_rdf`, `rdf_to_update`, `queries_to_collection`, `rdf_to_collection`, `SALG` | salg export (public API) |
| `starontology/__init__.py:226, 251-252, 338-364` | prefix map `salg`, registry entries `sparql_owl` -> `salg-ontology.ttl`, `sparql_shacl` -> `sparql_shapes.ttl` (excluded from listings and profiles) | salg export |
| `sparql/expr_validation.py` -> spexpr ontology/shapes | spexpr `.ttl` files contain `salg:` only in comments and `sh:message` text plus one `PREFIX salg:` line (spexpr_shapes.ttl:106); no `salg:` IRI is a shape path or class | generic (cosmetic salg mentions) |

Not consumers (checked): `tools/` and `scripts/*.py` do not import salg or the encoder; only `scripts/generate_api_docs.py:51,65`
lists the `starlayer.sparql.salg` module in the API doc buckets. `tools/kg/codekg/queries.py` (496 lines) uses sqe only
(`sqe_tree_to_text`, `sqe_validate`, `sqe_tree_to_query`); `tools/kg/codekg/curated/query-library.ttl` holds the 24 named queries as `sqe:`
trees and no `salg:` term (grep of all `.ttl`/`.trig` under `tools/`: no hit). `sqe_tree_to_query` needs rdflib `translateQuery`, so
the KG's run path ties to the generic decoder, not to salg.

### 2.2 Docs and notebooks (text only, no code dependency)

`docs/guides/05-starlayer-schemas-and-ontologies.ipynb`, `05d-shacl-library-registry.ipynb`, `appendix-a-public-resources.ipynb`
(salg ontology/shapes links); generated: `docs/generated/api-reference.generated.md`, `api-overview.generated.md`; working notes
(8 files in `docs/working/`), `packages/starlayer/docs/{sparql/implementation-notes,future_enhancements,graph/manchester_syntax_gap_analysis,shacl/shacl12-gap-matrix}.md`;
`sparql/CLAUDE.md` (rule on salg/sqe; stale `starsparql` paths), `graph/CLAUDE.md`. Notebook `05b` uses the encoder per the earlier
doc (not re-verified; the grep for the word `salg` did not list it).

### 2.3 Tests that exercise salg or the encoder

My scan: files under `tests/` referencing `starlayer.sparql.salg`, `SALG`, the encoder/decoder functions, `rdf11_*`, or `sparql.to_rdf/from_rdf/vocab`:
**30 files, about 545 `def test_` (whole-file counts, upper bound; parametrization multiplies runs)**. This matches the earlier 12 files / 539
only in size; the earlier figure counted a narrower set. By role:

| Role | Files (defs) | Fate |
|---|---|---|
| Salg-only: shapes, checks, components, collection | `tests/sparql/unit/test_shacl_shapes.py` (77), `test_semantic_checks.py` (10), `test_native_components_unbound_pv.py` (7), `tests/shacl_engine/test_salg_components.py` (5), `tests/sparql/unit/test_query_collection.py` (3) | delete (102); port the unbound-variable cases (about 10 of the 17 in semantic_checks/native) to sqe |
| Salg partial | `tests/shacl/integration/test_meta_shapes_extensions.py` (127; salg part is the class at about line 1312-1420, 10 `salg` hits; rest unverified), `tests/starontology/unit/test_starontology.py` (39; the sparql_owl/sparql_shacl assertions at lines 25-27, 84-97, 158, 197), `tests/graph/unit/test_skos_shapes.py` (23; 1 hit, unverified), `tests/sparql/unit/test_sqe_ontology.py` (41; 13 `salg` hits are mostly "no salg terms" assertions, unverified) | edit |
| Encoder round trip (lowered algebra <-> RDF) | `test_roundtrip` 2, `test_phase2_{aggregates,forms,paths,update,values_subquery}` 8, `test_phase3_rdf12` 3, `test_phase4_prologue` 4, `test_phase6_rdf12_native` 6, `test_phase6_serialize12` 5, `test_remainders_93` 11, `test_rdf_nil_roundtrip` 3, `test_dirlang_string_functions` 40, `tests/sparql/integration/test_adversarial_roundtrip.py` 9, `tests/sparql/w3c_sparql12/test_w3c_sparql12.py` 5, `test_w3c_sparql12_oxigraph_roundtrip.py` 2, `tests/graph/w3c_sparql12/test_algebra_regenerated_queries.py` 2 | delete or rewrite to test the new parser plus Oxigraph (about 100 defs; some, such as dirlang functions, test evaluation and survive as execution tests) |
| Lowering | `tests/sparql/unit/test_lower_rdf11.py` (36) | depends on whether lowering survives (step 5) |
| Generic codec via sqe/srl | `tests/sparql/sqe_coverage/{test_w3c_through_sqe 2, test_sqe_property_based 2, test_sqe_features 3, test_sqe_modifiers 4}`, `tests/sparql/srl_conformance/test_sr_architecture.py` (5) | keep; imports change |
| Graph-level, incidental | `tests/graph/integration/test_oxigraph_backend.py` (70), `tests/graph/unit/test_contracts_hunt3.py` (23) | keep; check imports (the pattern matched; whether they call salg directly: unverified) |

## 3. What salg provides uniquely

Two things: (a) SHACL structural validation of a full resolved-algebra graph (`sparql_shapes.ttl`), (b) one semantic check,
`noUnboundProjectedVariables`. Both are used by exactly one production caller (`meta_shapes.check_sparql_query_text`, for
`sh:select/ask/construct` text in shapes graphs) plus the engine trampoline.

| Check | Salg implementation | sqe equivalent today | Gap and what a port needs from the tree |
|---|---|---|---|
| Projected variable never bound in `WHERE` | python, via rdflib `_addVars` on `Project.p` (`semantic_checks.py`) | `sqe_shapes.ttl:294` ("Projected variable {?var} is never bound anywhere in this query's own sqe:where pattern"); also unbound variable inside an expression (47, 172, 332) and CONSTRUCT template variable (133) | None structural; sqe has more cases than salg. Needs: `sqe:projection` list, the flat `sqe:where` pattern elements (triple patterns, Optional, Union, Bind, Values, SubSelect). Unverified: parity on VALUES-bound and sub-select-projected variables (salg has a VALUES workaround); needs a test per case. |
| SHACL pre-bound `$this/$value/$PATH` exemption | `meta_shapes._is_prebound_variable_only_report` filters the salg report by component IRI and `sh:value` | none | New: filter sqe report results by the unbound-variable shape and variable name, or add the three names as a bound-set parameter. The sqe messages carry `{?var}`; whether the `sh:value` is the variable is unverified. |
| Per-operator cardinality and rdf:List shape (Join p1/p2, Slice start/length, OrderBy, ...) | `sparql_shapes.ttl` | `sqe_shapes.ttl` (810 lines) covers the sqe forms: SelectQuery, Ask, Construct, Filter, Bind, Optional, Minus, Graph, Values, Alias, OrderCondition, TripleTerm, group/having/limit/offset, distinct-vs-reduced | Different vocabulary (flat pattern list, no Join/LeftJoin/Project/Slice nodes), so no port: the sqe shapes are the replacement. |
| Update operations (Modify, Load, Clear, Copy, ...), DESCRIBE, `QueryCollection` | `sparql_shapes.ttl` | none: sqe does not cover DESCRIBE or Update (`sqe/__init__.py:6-7`) | Not needed by the single caller (SHACL allows select/ask/construct only). Lost on purpose. |
| Expression and property-path structure | shared spexpr shapes (`spexpr_shapes.ttl` 457) | same shapes, already used by `sqe_validate` | Nothing to port. |
| Triple-term position rules | `salg:TripleTerm*` shapes | `sqe_shapes.ttl:500-514` plus `_syntax_checks.py` at parse time | Nothing to port. |
| EXISTS body structure | cardinality only (raw parse fragment, not shaped) | `sqe:Exists` shape (524) | sqe stronger. |

What the replacement meta_shapes call needs: `sqe_parse_to_tree(text)` then `sqe_validate(graph)` (which goes through
`starlayer.shacl.validate` with RDFS entailment, `max_validation_depth=100`; cost versus the cached salg path is unverified, and the
existing `_SPARQL_STRUCTURE_CACHE` keyed on text/prefixes/is_target carries over). Open: `sqe_parse_to_tree` must accept every query
the SHACL libraries embed; `tests/sparql/sqe_coverage/sqe_known_gaps.txt` lists 9 known gaps (contents not read).

## 4. The retirement path

Order constraint: the salg export cannot be deleted until nothing outside `salg/` calls `query_to_rdf`/`rdf_to_query`
(steps 3, 4) and nothing shared lives in the two files (step 1). Steps 1-3 do not wait on the parser or Oxigraph work; step 4 does.

**Step 1. Separate the generic codec from the salg export (not blocked).** Create one new module owned by sqe/spexpr (for example
`sparql/spexpr_codec.py`) and move into it the "generic" functions of table 1.2: `_encode*`, `_decode*`, `_new_starlayer_graph`,
`_EXPR_EVALFNS`, `_comp_value_ns`, hooks removed by parametrizing the namespace (`sqe`/`srl` pass theirs; `_NS_OVERRIDES` and
`_ENCODE_HOOK/_DECODE_HOOK` exist only to keep salg terms out, so they become ordinary arguments). `to_rdf.py`/`from_rdf.py` then import
from it (the direction the project rule asked for). Files touched: `to_rdf.py`, `from_rdf.py`, `sqe/to_rdf.py`, `sqe/from_rdf.py`,
`sqe/to_text.py`, `srl.py`, `srl_eval.py`, `lower_rdf11.py` (import lines), `vocab.py` (split `SALG` outer terms away from `SPEXPR/SQE`).
Tests to run/adjust: all of `tests/sparql/sqe_coverage` (opt-in, about 4 minutes), `test_sqe_ontology`, `test_sr_architecture`, plus the
round-trip tests (they must still pass here because the salg export still exists). Delete afterwards: nothing yet. Size: about 770 lines
move (estimate: 330 + 440). **Parser dependency:** the codec still speaks rdflib's `Expr`/`CompValue` and node names; when the new parser
lands, this module is what gets rewritten (or replaced by sqe's own flat expression nodes), which is separate work.

**Step 2. Port the checks to sqe (not blocked).** Add to `sqe_shapes.ttl`/`sqe/shapes.py` only what section 3 marks missing: the pre-bound
variable parameter, and parity tests for VALUES-bound and sub-select variables. Files touched: `sqe/shapes.py` (80), possibly
`starontology/sqe_shapes.ttl` (that is a starontology file: decision point, section 5). Tests: move about 10 cases from
`test_semantic_checks.py`/`test_native_components_unbound_pv.py` into a new sqe test. Delete afterwards: nothing yet.

**Step 3. Re-point the two salg consumers outside `sparql/` (not blocked; depends on step 2).**
- `shacl/meta_shapes.py:500-535`: replace the `query_to_rdf` + `salg.validate_query` block by `sqe_parse_to_tree` + `sqe_validate`; rewrite
  `_is_prebound_variable_only_report` for the sqe shape; drop the `SALG` import (414-437). Tests: the salg class in
  `test_meta_shapes_extensions.py` (about 1312-1420; messages that name `salg:` change).
- Engine component: `shacl_engine/components/extensions.py:23-30` and `component_table.py:116-117` row removed (the component only fires
  on `salg:Project` focus nodes, which no longer exist; the table note already says "a port may omit it"). Delete `salg/engine_components.py` (54)
  and `salg/native_components.py` (148); `test_salg_components.py` (5) and `test_native_components_unbound_pv.py` (7) go. Unverified: that no
  shapes file in `starontology/` activates `salg:noUnboundProjectedVariables` apart from `salg:ProjectShape` in `sparql_shapes.ttl`.

**Step 4. Remove the lowering path's dependence on the encoder (BLOCKED on the parser and execution work).** Today
`prepareQuery`/`query_cache` do `prepare_query_12 -> query_to_rdf11 -> rdf11_to_query`; updates do `update_to_rdf11 -> rdf11_to_update`
(and, for remote stores, a text rendering of the lowered update). All of that exists to hand rdflib's evaluator a runnable `Query`. When
Oxigraph receives the original text, `sparql_api.py` (110-117, 163-170), `query_cache.py` (162-163), `starlayer_graph.py` (2729-2748),
`starlayer_dataset.py` (1048-1069), `backends/native.py` (803-822) stop calling these. The SHACL engine's `check_query`
(`shacl_engine/sparql_support.py`, `_walk` about 50 lines) still needs a walkable parsed tree, which must come from the new parser, not salg.
Then `lower_rdf11.py` (1,971) has no production caller except `srl_eval.py` (lazy, line 482 area; unverified exactly where) and
`star_query.py`/entailment (unverified); whether it is deleted or kept depends on whether native Oxigraph triple terms replace the lowering
(execution work). Tests: `test_lower_rdf11.py` (36) and the round-trip group (about 100) are rewritten or removed with it.

**Step 5. Delete (after steps 1-4).**
| Delete | Lines |
|---|---|
| `sparql/salg/` (all 7 files) | 812 |
| `to_rdf.py` root-level functions (`query_to_rdf`, `update_to_rdf`, `queries_to_collection`, prologue/quads/binding helpers) | about 180 (estimate) |
| `from_rdf.py` root-level functions | about 160 (estimate) |
| `vocab.py` outer-algebra `SALG` terms (303-344) and docstring | about 80 |
| `starontology/salg-ontology.ttl`, `starontology/sparql_shapes.ttl` | 331 + 1,013 |
| `sparql/__init__.py` re-exports (11-15, 55-60), `starontology/__init__.py` registry entries (226, 251-252, 338-364) and the stale comment at 821 | about 40 |
| Salg-only tests (section 2.3) | about 102 defs, plus round-trip group |
| `scripts/generate_api_docs.py:51,65` bucket, regenerate `docs/generated/*`; `sparql/CLAUDE.md` rule text; notebooks 05, 05d, appendix-a links | docs |
| Orphan `ssyn`/`sast` (946 lines, 4 test files) | optional, same cleanup; `to_ssyn_rdf.py` otherwise needs the codec from step 1 |

Total deletable: about 2,300 Python and Turtle lines directly attributable to salg, plus the lowering layer if step 4 removes it.
Rebuild `starontology.trig` with `scripts/build_starontology.py` after the Turtle deletions (decision point below).

## 5. Risks and open questions

1. **Starontology rule.** Your rule is to work in a copy and never merge into `starontology/` unprompted. Files involved, all in
   `packages/starlayer/starlayer/starontology/`: `salg-ontology.ttl` and `sparql_shapes.ttl` (delete), `starontology.trig` (748 lines mention
   `salg`; it is the built store, regenerate), `__init__.py` (registry and prefix map), `sqe_shapes.ttl` (step 2 addition, possibly),
   `spexpr-ontology.ttl` (comments cite `salg:args` etc.), `spexpr_shapes.ttl` (39 `salg:` mentions, all `sh:message`/comment text plus
   one `PREFIX salg:`), `srl-ontology.ttl:15`, `srl_shapes.ttl:12,78` (messages say "a salg: expression"), `starlayer-profiles.ttl:98,110`
   (comments), and stale `@prefix salg:` declarations in `shacl12-shacl.ttl`, `shacl12-shacl-ui.ttl`, `shacl12-vocabulary.ttl`, `skos-ontology.ttl`.
   Also Python docstrings in `skos.py`, `manchester.py`. Everything except the two deletions and the trig rebuild is cosmetic and can wait.
   Each is a decision for you; I edited none.
2. **Public API break.** `starlayer.sparql.query_to_rdf`, `rdf_to_query`, `update_to_rdf`, `rdf_to_update`, `queries_to_collection`,
   `rdf_to_collection`, `SALG` are exported (`sparql/__init__.py`). External consumers: none found in this repo (`tools/`, `scripts/`); outside
   the repo unverified. The registry names `sparql_owl`/`sparql_shacl` are public lookups (`get_ontology_graph`) even though hidden from listings.
3. **Stored `salg:` data.** I found none: no `.ttl/.trig` under `tools/` or outside `starontology/` contains `salg:` or the `algebra#` namespace,
   and the KG's 24 stored queries are `sqe:` trees. Unverified: other branches, KG build outputs not in the tree, user data.
4. **Namespace IRI hardcoded elsewhere.** `shacl_engine/components/extensions.py:15` hardcodes the salg namespace string; remove with step 3.
5. **sqe replaces a strictly smaller language** for the meta_shapes check: no Update or DESCRIBE (not needed for `sh:select/ask/construct`), and a
   query that sqe cannot parse (`sqe_known_gaps.txt`, 9 lines, unread) would turn from "validated" to an error or be skipped. Needs a measured
   comparison over the SHACL-library queries before step 3.
6. **Loss of a second opinion.** `_addVars`-based check relied on rdflib's own scoping rules; the sqe shape re-derives scoping in SPARQL. The
   old docstring named drift between the two as the reason it was written in Python; parity tests (step 2) are the mitigation.
7. **Performance.** `sqe_validate` runs full RDFS entailment per query versus the cached salg path; unmeasured.
8. **The rule check from the exploration doc is confirmed in code:** srl and sqe do not import `salg/` but do import the generic half of the
   salg encoder files (`sqe/to_rdf.py:59-61`, `sqe/from_rdf.py:28-29`, `srl.py:146-151`); step 1 removes that.
9. **Parser replacement changes step 1's codec** (rdflib `Expr` names, `_EXPR_EVALFNS` introspection of rdflib's live grammar); doing step 1
   first still pays off because it ends the circular ownership and shrinks what the parser work must touch.
10. Not verified: whether any other file in `tests/` calls `salg` helpers indirectly through fixtures (`tests/conftest.py` mentions salg per the
    earlier doc; I did not open it).
