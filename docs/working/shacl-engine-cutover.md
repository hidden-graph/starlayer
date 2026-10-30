# SHACL engine: cut-over plan (pyshacl out, `starlayer.shacl_engine` in)

Branch `shacl-engine`, worktree `starlight/shacl-engine`. Read-only analysis, 2026-10-30. Inputs: `shacl-engine-feasibility.md`,
`-design.md`, `-differential.md`, `docs/working/differential/results2.jsonl` (3,126 calls), and greps/`wc -l` over
`packages/starlayer/starlayer`, `tools/`, `scripts/`, `docs/guides`, `pyproject.toml`. Line counts are `wc -l`; splits inside
`validator.py` are estimates from function ranges (marked ~).

State of the engine today: `shacl_engine/` is 3,202 lines plus `components/` 1,595 = 4,797 lines. Run on this branch just now:
`tests/shacl_engine` plus the four `w3c_shacl12/test_w3c_engine_*` files, 619 passed, 2 failed
(`shnex-sparql/seconds::seconds-example`, a fixture-formatting entry also in `known_failures.py`; and
`sparql/pre-binding/pre-binding-002`, a duplicate-row count 2 vs 1 that needs a look before stage 1).

## 1. Inventory: where pyshacl is relied on

Old code under `starlayer/shacl/` is 16,074 lines (incl. `shacl/engine/` 375, `validator.py` 6,110, `native_components.py` 3,416).
pyshacl is named in 21 modules under `starlayer/` (`grep -c`: validator 72, native_components 68, rule_engine 13,
node_expressions 13, meta_shapes 13, salg/sparql_shapes 10, then 2 to 6 each) and in 51 test files, 12 notebook cells, and
`pyproject.toml:22` (`"pyshacl>=0.40.1"`, a hard dependency).

### 1.1 Validation loop (pyshacl.validate and its Shape machinery)
| Site | Symbol | Use | Engine covers? |
|---|---|---|---|
| `shacl/validator.py:5758,5771` `_reject_unknown_validate_options`, `_default_validate` | `pyshacl.validate` | the actual validation; option-name whitelist built from `inspect.signature(pyshacl.validate)` | Yes: `shacl_engine.api.validate` (executor + `report.build_report`). Option whitelist must be re-based (see 2.3) |
| `validator.py:5084-5143` | `pyshacl.shape.Shape.validate` patched | `sh:filterShape` shim | No need (legacy, DROP-LEGACY; engine uses `shnex:filterShape`) |
| `validator.py:5381-5537` | `Shape.value_nodes` patched | `sh:values` / `sh:defaultValue` | Yes: `plan.Shape.values/default_values`, `executor` |
| `validator.py:5538-5621` | `Shape.focus_nodes` patched | `sh:deactivated` as node expression | Yes (`deactivation.py`, `Shape.deactivated_exprs`); 2 differential diffs were closed in round 2 |
| `validator.py:5622-5710` | `pyshacl.constraints.advanced` expression constraint patched | `sh:expression` value scope | Yes: `components/expression_components.py` |
| `validator.py:5144-5271` | `RdfLibDataGraph.clone` patched | keep the triple-term adapter on clones | Not needed: no encoding in the engine |
| `validator.py:4344-4457` | `pyshacl.rdfutil.stringify` patched | bnode stringification for the native backend | Not needed |
| `validator.py:4758-4820` | `pyshacl.validator` module patched | rules in the global engine | Replaced by `shacl_engine/rules.py` (570) |
| `shacl/list_functions.py:64`, `component_cache.py:58`, `recursion.py:53` | `pyshacl.validator`, `CONSTRAINT_PARAMETERS_MAP`, `Shape` | list-function registration, per-shape component cache, recursion guard | Replaced: `Plan.components()` builds once; `Context.conforms` handles recursion; list functions in `expressions.py` |
| `shacl/engine/core.py:120` | `ShapesGraph` | `target_nodes`, `evaluate_component` seam | `targets.focus_nodes`, `components.registry` replace it |

### 1.2 Constraint-component base classes (native_components.py)
`native_components.py` (3,416 lines) has 68 pyshacl references: 28 imports of `ConstraintComponent` (one per `_build_*_component`
factory, imported inside the function), plus `pyshacl.constraints.core.{value,logical,shape_based,property_pair,string_based}_constraints`
delegate classes (and `CONSTRAINT_PARAMETERS_MAP` at line 3321 for registration), `pyshacl.constraints.sparql.sparql_based_constraints`
(line 1110), `pyshacl.helper.path_helper.shacl_path_to_sparql_path` (299), `pyshacl.rdfutil.stringify_node` (7 sites).
Engine: all 28 are re-written as `@component(iri, *predicates)` functions in `components/core_value.py` (257), `core_string_pair.py` (355),
`core_shape_based.py` (236), `core_cross_node.py` (46), `sparql_*.py` (197), `expression_components.py`, `extensions.py` (28, lazy trampoline
to `sparql/salg/engine_components.py`). Not a base-class port: the old code subclasses pyshacl, the engine has a registry of generators of
`Violation` records. Nothing from `native_components.py` is reusable as text except the per-component semantics, which the
engine already carries (W3C core 137/138 on the first spike, now all but the two noted above).
Outside `shacl/`: `sparql/salg/native_components.py:52,68` imports `pyshacl.constraints.*` and `ConstraintComponent`
for `salg:NoUnboundProjectedVariablesConstraintComponent`; the engine twin `sparql/salg/engine_components.py` exists (ported).

### 1.3 Errors
`pyshacl.errors`: `ShapeRecursionWarning` imported in `sparql/srl.py:1058`, `sparql/sqe/shapes.py:65`, `sparql/salg/sparql_shapes.py:89`,
`starontology/manchester.py:1231`, `starontology/skos.py:82` (each to silence the warning around `starlayer.shacl.validate`);
`ReportableRuntimeError`, `ValidationFailure`, `ConstraintLoadError`, `RuleLoadError`, `ShapeLoadError` inside `native_components.py` (26 sites),
`rule_engine.py` (7 sites), `rule_conditions.py`, `meta_shapes.py:228,497`, `triple_rule.py:38`, `validator.py:2495,4686`.
`shacl_engine/meta.py:21` still imports `pyshacl.errors.ReportableRuntimeError` as the base of `MetaShaclError`
(try/except fallback to `RuntimeError`): the only pyshacl import left in the engine. Engine has its own `ShapeError` (`plan.py`),
`EvaluationFailure` (`expressions.py`), `RuleError` (`rules.py`). Plan: introduce `starlayer.shacl.errors` with
`ShapeError`, `RuleError`, `MetaShaclError(ValueError-compatible)`; alias the old names for a release; five `ShapeRecursionWarning`
call sites lose their `warnings.catch_warnings` wrapper (the engine never warns: it assumes conformance on positive re-entry and raises
`ShapeError` on cycles through `sh:not`).

### 1.4 ShapesGraph harvesting (who needs a shapes-graph model)
`pyshacl.shapes_graph.ShapesGraph` (sg.shapes, `lookup_shape_from_node`, `shape.deactivated`, `shape.property_shapes`, `.path`) is built at:
`validator.py:1114` and `:2336` (target node expressions: `eval_expr(..., throwaway_sg)`), `:1915` and `:3930` (module and method `evaluate`:
harvest all shapes with `sh:values`/`sh:defaultValue`), `shacl/subgraph_extraction.py:595` (`extract_subgraph`: candidate shapes,
walks property shapes and paths), `shacl/engine/core.py:120`. Non-users that look like users: `ui_widget_selection.py` (527) calls only
`validate()` and `_find_genuine_report_node` (no ShapesGraph); `profiling.py` and `shacl_profiling.py` read plain RDF with SPARQL;
`shape_types.py` and `shapes_graphs.py` read RDF; `graph/graph/shape_derivation.py:309,521` calls `starlayer.shacl.validate`
(derive shapes from data, then validate); `owl_dl_rustdl.py:140` same.
Can `shacl_engine.plan.Plan`/`Shape` serve? Yes for all three real consumers. `Plan(shapes_graph).all_shape_nodes()` replaces
`sg.shapes`; `Plan.shape(node)` replaces `lookup_shape_from_node`; `Shape` already has `node, is_property, path (Path tree), targets,
params, property_shapes, severity, deactivated, messages, values, default_values, annotations, deactivated_exprs`. Gaps to add before
porting: (i) `Shape.params` holds only parameter predicates seen by the builder, extraction needs the `sh:node`/`sh:and`/`sh:or`/
`sh:qualifiedValueShape` references (present in `params`, just not pre-resolved), (ii) a `reachable_shapes(node)` helper for `close_shape`,
(iii) `Plan.shape()` is lazy and raises `ShapeError` on a malformed shape, whereas pyshacl's harvest tolerated it (differential
category 11: old raises, engine returns, or vice versa on closure extracts). About 150 lines of new engine code plus rewriting the three
consumers (~1,100 lines touched: `evaluate` ~360 in validator.py, `extract_subgraph` 791 of which ~200 is harvest glue).

### 1.5 Rules (pyshacl.rules)
`rule_engine.py` (398, 13 refs), `triple_rule.py` (110), `rule_conditions.py` (117): `SHACLRule`, `SHACLRuleCondition`, `TripleRule`,
`SPARQLRule`, `RULES_ITERATE_LIMIT`, `TRIPLE_RULE_ITERATE_LIMIT`, `RuleLoadError`. `validator.py:4596-4741` `_GlobalShape`,
`_global_engine_rules`, `_borrow_template_rules`; `:4821-5083` expected-predicate, default-value, temp-triple, `sh:sourceRule` provenance
helpers. Engine: `shacl_engine/rules.py` (570: layers, order, `runOnce`, `expectedPredicate`, `tempTriple`, conditions, rule sets,
rule templates, `InferredView` so the caller's graph is never mutated) and `entailment.py` (108). Not in engine: `sh:sourceRule`
provenance reifiers (grep 0), `iterate_rules`, a full `sh:ruleProcessor` (3 refs: selection only; see section 5).

### 1.6 Helpers (rdfutil, stringify, path_helper, expression_helper, pytypes)
`pyshacl.rdfutil.stringify_node` (messages; 7 sites), `pyshacl.helper.path_helper.shacl_path_to_sparql_path` (native_components:300),
`pyshacl.helper.expression_helper.value_nodes_from_path` (node_expressions:512,624; native_components:2324), `pyshacl.helper.get_query_helper_cls`
(node_expressions:445, rule_engine:258, validator:5309: prefix handling for SPARQL), `pyshacl.pytypes.SHACLExecutor` (node_expressions:295,
subgraph_extraction:169, recursion:55). Engine equivalents: `paths.eval_path` (140), `sparql_support.py` (378: prefixes, pre-binding,
message templates), `report.py` message formatting. All covered; nothing to port.

### 1.7 Line counts per group (old `starlayer/shacl/`, 16,074 lines)
| Group | Lines | Files |
|---|---:|---|
| **Disappears** (pyshacl glue or replaced one-for-one by engine code) | ~11,300 | native_components 3,416; node_expressions 890; sparql_node_expressions 499; rule_engine 398; triple_rule 110; rule_conditions 117; adapters 715; component_cache 69; recursion 91; list_functions 80; entailment 221; `shacl/engine/` 375; meta_shapes ~440 of 538; validator.py ~3,900 (patches 711, patch-support helpers ~520, the module/method pipeline copies of validate, validate_each ~1,700, option/encode/decode plumbing ~400, rule glue ~600) |
| **Must be ported / rewritten on the engine** | ~2,500 | validator.py ~1,700 (`evaluate` x2 ~360, `StarShaclSchema` binding, target-augmentation ~430, report/provenance wrappers, `select_widgets`, `close_shape`, `extract_shapes_graph`, `_inject_shapes_graph_subclass_triples`, `_resolve_shapes_graph_imports` ~ mostly in `shacl_engine/imports.py` and `modules.py` already); subgraph_extraction 791 |
| **Independent of pyshacl** (stay) | ~1,750 + ~500 | profiling 329, shacl_profiling 24, ui_widget_selection 527 (needs `validate` only), shape_types 92, shapes_graphs 134 (duplicated by engine `modules.py` 98), validation_modes 70, results 83, types 78, xpath_regex 214, paths 34, `__init__` 69, meta_shapes loader ~98, validator.py ~500 (`_RawGraphView`, list helpers, widget wrappers) |

Net: about 70% of the old `shacl/` tree goes; about 15% is rewritten thinner; about 15% stays. Adapters (715) disappear only
internally: `TripleTermAdapter/Graph/Value` are exported (`starlayer.shacl.__all__`), tests (`test_adapters.py`, `test_triple_term_graph.py`,
`test_types.py`) and six test files import them; keep as a deprecated shim for one release (see 2.4).

## 2. Public API map

`starlayer.shacl.__all__` (`shacl/__init__.py`, 69 lines): `StarShaclSchema, validate, validate_each, apply_rules, evaluate,
extract_subgraph, TripleTermAdapter, TripleTermGraph, TripleTermValue, normalize_to_starlayer_graph, normalize_graph_inputs,
ExecutionDiagnostics, ValidationResult, RulesResult, target_nodes, StarLayerGraphProtocol, MutableStarLayerGraphProtocol`.
Top-level `starlayer/__init__.py:24` re-exports only `StarShaclSchema` (also `tests/test_reexports.py`). Qualified imports used in the wild:
`shacl_profiling`, `ui_widget_selection.select_widgets`/`select_widget`, `node_expressions.eval_expr`, `shacl.engine.*`,
`validator._find_genuine_report_node`, `validator._ensure_native_component_shapes_typed` (`scripts/build_meta_shapes.py:93`),
`StarShaclSchema.close_shape`.

### 2.1 Function and class map
| Public name | Old behaviour | Engine equivalent | Gap / action |
|---|---|---|---|
| `validate(data, shacl_graph, ont_graph, *, mode, adapter, validate_fn, decode_report, ..., **pyshacl kwargs) -> ValidationResult` | normalise, entail, augment targets, encode triple terms, `pyshacl.validate`, decode; `ValidationResult(conforms, report_graph, report_text, data_graph, diagnostics)` | `api.validate(...) -> Outcome(conforms, report_graph, results, rule_result, data_graph)` | Adapter must produce `report_text` (engine has no text formatter; ~60 lines, `meta._report_text` is a start), `diagnostics` (`ExecutionDiagnostics`: engine has no encode counters; return zeros plus `recursion_revisits` from `Context`), and map options (2.3) |
| `validate_each(...)` | validates each focus/shape separately, parallel copy of validate | none | ~750 lines old; re-express as a loop over `Plan.all_shape_nodes()` calling `run` with one shape (needs `run(plan, data, only_shapes=...)`, ~40 lines); check how its tests (`test_validator`, `test_hunt3_*`) assert |
| `StarShaclSchema(shacl_graph, ont_graph, *, data_graph, scoring_graph, inference, adapter, validate_fn)` | binds graphs; normalises once; properties `shacl_graph`, `ont_graph`, `data_graph`, `scoring_graph` | build `Plan` once in `__init__` (lazy) and pass through `api.validate` | `Plan` holds a cache of shapes; must be invalidated when `shacl_graph` is reassigned (setters at validator.py:223-250). `api.validate` currently builds `Plan(shapes_graph=shapes)` per call: add an optional `plan=` parameter (~10 lines) so the schema caches parsed shapes |
| `StarShaclSchema.validate` | same body as module `validate` | adapter delegating to module `validate` | the "two-step flip" duplicate (validator.py 465-997) is deleted outright |
| `StarShaclSchema.validate_each` | see above | see above | |
| `StarShaclSchema.apply_rules`, module `apply_rules(data, shacl, ont, include_source_rule_provenance, rule_set, **kw) -> RulesResult(inferred_graph, ..., conforms?)` | pyshacl rules patched, validates the result, `sh:sourceRule` reifiers on request | `rules.apply_rules(data, shapes, rule_sets=) -> RuleResult(view, ...)`, `rules.validate_with_rules` | map `RuleResult` to `RulesResult`; gaps: `include_source_rule_provenance`, `iterate_rules` (3 differential calls), `rule_set` argument forms (IRI or `sh:RuleSet` node; `rules.rule_set_members` exists) |
| `StarShaclSchema.evaluate`, module `evaluate(data, shacl, ont, *, inference, focus_nodes, properties, rules_entailment) -> Graph|None` | computes `sh:values`/`sh:defaultValue` virtual properties into a shape-driven subgraph | no entry point; the pieces exist (`executor` value-node computation, `Shape.values/default_values`, `expressions.evaluate_expression`) | port: ~150 lines on `Plan`; 8 test files use `evaluate(` (`test_evaluate_virtual_values`, `test_sh_values`) |
| `extract_subgraph(data, shacl_graph, ..., shape=, focus_node=) -> Graph|None` | shape-driven extraction | none | rewrite on `Plan`/`Shape` (section 1.4); 8 test files; `StarShaclSchema.extract_shapes_graph(iri, include_referenced)` 4 test files (engine has `modules.extract_module`, `resolve_shapes_resource`: cover the module part, the `include_referenced` closure needs `reachable_shapes`) |
| `StarShaclSchema.close_shape(shape)` | closure of a shape's referenced shapes | `modules._copy_cbd` is related, no direct equivalent | ~40 lines |
| `StarShaclSchema.select_widgets(...)`, `ui_widget_selection.select_widgets/select_widget` | UI 1.2 widget algorithm; calls `validate` and `_find_genuine_report_node` for matcher shapes | none needed | independent: swap the `validate` import; replace `_find_genuine_report_node` by `Outcome.results` (or keep a copy in `shacl/results.py`, ~50 lines). Highest per-call volume (matcher shapes per property) so also the best latency test |
| `target_nodes(shape, data, shacl)` (`shacl.engine`) | focus nodes a shape targets | `targets.focus_nodes(...)` | thin wrapper; `test_hunt3_targets` already compares them with `validate` |
| `StarShaclSchema.evaluate_component`, `build_report`, `target_nodes` (methods 399-465) and `shacl.engine.evaluate_component/ComponentRequest/STSH` | hard-coded dispatcher for single components | `components.registry.REGISTRY` + `executor` | deprecate; no engine equivalent (the draft notes there was no extension mechanism and no standalone use) |
| `ValidationResult`, `ExecutionDiagnostics`, `RulesResult` | result dataclasses | `Outcome`, `RuleResult` | keep the old dataclasses as the public type; adapter fills them. Do not expose `Outcome` in `__all__` until stable |
| `TripleTermAdapter`, `TripleTermGraph`, `TripleTermValue` | RDF 1.2 to 1.1 encode/decode for pyshacl | none (engine is native) | keep exported, deprecation warning on use in `validate(adapter=...)` (ignored), remove next major |
| `normalize_graph_inputs`, `normalize_to_starlayer_graph` | any graph to `StarLayerGraph` | engine accepts rdflib-like or `OxigraphGraph` (`interface.GraphView`) | keep; engine uses it at the edge |
| `StarLayerGraphProtocol`, `MutableStarLayerGraphProtocol` | typing | `interface.GraphView` | keep as aliases |
| `shacl_profiling.declared_conformance_profile/derive_conforms_to`, `shapes_graphs`, `shape_types` | Profiling utilities | independent; `api.annotate_provenance` already does the `sh:conformsTo` part | unchanged |
| `node_expressions.eval_expr(expr, focus, data, sg)` | single expression evaluation, public-by-submodule | `expressions.evaluate_expression(...)` | shim with a `Plan` instead of `ShapesGraph` |
| `validation_modes` (`validation`/`rules`/`debug`) | option presets: `advanced`, `inplace`, `meta_shacl`, `iterate_rules`, `debug` | none | keep and map (2.3) |
| Caches | `component_cache.py` (per-shape component init), `recursion.py` (revisit counter), `StarShaclSchema` pre-normalised graphs | `Plan._cache`, `Plan._components`, `Plan.sparql_cache`; `Context._focus_cache` | per-validate only today; per-schema reuse needs the `plan=` parameter above |

### 2.2 Return-shape gaps found by comparing signatures
- `report_text`: old is pyshacl's text, humanised; tests assert substrings (see section 3: report text is not compared in the differential).
- `ValidationResult.data_graph` only with `inplace=True`: engine does the same through `Outcome.data_graph`.
- `rules` default: old `validate` applied `sh:rule` first; engine applies rules only with `rules=True` or when `sh:entailment` is declared (differential "old-validator deviations"). The adapter must pass `rules=True` for `mode="rules"` and keep `None` for `validation`; this is a documented behaviour change for plain `validate`.

### 2.3 Option mapping (old kwargs to `api.validate`)
`mode` (via `validation_modes`) -> `meta_shacl`, `inplace`, `rules`; `inference`, `ont_graph`, `abort_on_first`, `max_validation_depth`,
`meta_shacl`, `shapes_graph_loader`, `ignore_imports`, `meta_shapes_extra`, `data_graph_iri`, `shapes_graph_iri`, `shapes_graph_resource`,
`specification_graph`, `include_used_configuration`, `inplace`: same name, pass through. `conformance_disallows` (old `allow_warnings`/`allow_infos`) -> map
`allow_warnings=True` to `conformance_disallows` excluding Warning (confirm the engine's set semantics: `report.conforms`). Dropped with a warning:
`advanced`, `debug`, `js`, `check_dash_result`, `sparql_mode`, `do_owl_imports`, `*_format`, `serialize_*` (the `_PYSHACL_KEYWORD_OPTIONS` set at
validator.py:5728; the TypeError for unknown kwargs (issue #94) stays, now against the engine signature plus this deprecated set).
Not supported: `decode_report=False` (4 calls; no encoded form exists: ignore with a warning), `iterate_rules` (3), `validate_fn`
(16 calls, see section 3), `rdfs_subclass_reasoning_includes_shapes_graph` (2; spec reads classes from the data graph: DROP-LEGACY).

### 2.4 Compatibility layer
New module `starlayer/shacl/_engine_adapter.py` (~250 lines): `run_engine(data, shapes, ont, options) -> ValidationResult`
(option mapping 2.3, `report_text` formatting, `ExecutionDiagnostics`), `rules_result(...)`, `plan_for(schema)`. Then in `validator.py`:
module `validate` and `StarShaclSchema.validate` become 10-line functions that choose the backend (stage 1) and later only call the adapter (stage 2).
Deprecate at stage 2, remove at stage 3: `validate_fn`, `adapter`, `decode_report`, `advanced`/`debug`/`js`, `evaluate_component`,
`ComponentRequest`, `STSH`, `shacl.engine.*`, `TripleTermAdapter` use inside `validate`. Keep forever: everything in `__all__` except
`ExecutionDiagnostics` fields that are encode counters (keep the type, fields stay 0).

## 3. Test migration

`packages/starlayer/tests/shacl`: `unit` 18 files, `integration` 88 files, `w3c_shacl12` 19 files, 1,224 `def test_` (1,738 passed in the
differential run after parametrisation, 951 of them reaching `validate`). Other directories importing `starlayer.shacl` (14 files):
`tests/test_reexports.py`, `test_conformance.py`, `test_build_scripts.py`, `sparql/unit/{test_srl_eval,test_srl_shapes,test_rdf_nil_roundtrip}.py`,
`sparql/srl_conformance/test_sr_architecture.py`, `graph/unit/{test_shape_derivation,test_skos_shapes}.py`,
`starontology/unit/{test_starontology,test_shipped_shapes_meta_validate}.py`, `kg/unit/{test_upstream_issues,test_curated,test_queries,test_notebook_links}.py`
(plus `tests/sparql/unit/test_shacl_shapes.py` and `test_srl_shapes.py` with pyshacl refs: SQE/SRL/SALG shape checks that run through `starlayer.shacl.validate`, so they also exercise the engine).

### 3.1 Numbers from `results2.jsonl` (3,126 calls: 2,277 `validate`, 849 `StarShaclSchema.validate`; 622 distinct test functions)
| Outcome | Calls | Share | Tests (functions) |
|---|---:|---:|---:|
| agree (same `sh:conforms` and result multiset) | 2,924 | 93.5% | 500 |
| differ | 34 | 1.1% | 30 |
| engine_error | 6 | 0.2% | 6 |
| skipped (option unsupported) | 25 | 0.8% | 22 |
| old_error (test expects the old validator to raise) | 137 | 4.4% | 75 |
489 of 622 test functions have only agreeing calls. Of the 3,126, 2,991 (agree + differ + engine_error ...) were comparable; run 1 had 145 skipped and 12 engine_error,
so the options round closed 120 skips and 6 errors.

Caveat: the comparison covers `sh:conforms` and (focus, path, component, value, severity). It does not compare `sh:sourceShape`, messages,
`report_text`, or `ValidationResult.diagnostics`, which many tests assert; "agree" is therefore an upper bound on pass-unchanged.
Run the suite itself against the adapter (stage 1 gate) to get the real figure. Also: the three alternate-boolean differs still in `results2.jsonl`
(`test_list_constraints`, `test_single_line_and_some_value`, `test_reification_constraints`) were a harness artifact fixed afterwards
(differential doc, round 2), so `results2.jsonl` pre-dates that fix; regenerate it (22 min) before using it as a gate.

### 3.2 Categories
1. **Pass unchanged** (~2,924 calls; about 480 of the 622 test functions; ~74% of the 1,224 functions if the same ratio holds). Includes the W3C
   `w3c_shacl12` Validate tests (already run by `test_w3c_engine_*`), recursion, closed shapes, node-expression integration (`test_shnex_*`),
   `test_sparql_shacl_integration` (except one), Oxigraph store tests, rule tests via `apply_rules` (`test_rule_layers_and_run_once`,
   `test_expected_predicate`, `test_triple_rule_import_order`).
2. **Need option mapping or an adapter shim** (25 skipped calls, ~12 tests plus the `evaluate`/`select_widgets`/`extract_*` families
   that do not call `validate` at all: 8 + 10 + 8 + 4 files use `evaluate(`, `select_widget`, `extract_subgraph`, `extract_shapes_graph`).
   `validate_fn=` (16 calls, 1 file: `test_validator.py`) asserts that a custom callable is invoked: pyshacl-specific, rewrite to inject an
   engine hook or delete. `inplace` (7), `decode_report=False` (4; no analogue, delete assertions), `iterate_rules` (3 calls, 4 files),
   `rdfs_subclass_reasoning_includes_shapes_graph` (2).
3. **Encode project extensions the draft does not have** (34 differ + 6 engine_error = 40 calls). Verdicts are in `-differential.md`:
   - nested `sh:uniqueValuesFor` (15 calls, all in `test_native_component_composition.py`, 4 more related in `test_recursion`): engine follows Core 7.9.5
     (peers are the shape's own targets); the tests encode "every node that reaches the shape". Decision needed (section 4, stage 2 gate): rewrite
     these 15 to give the nested shape targets, or implement the extension in the engine behind an option. The rewrite changes the user-visible semantics.
   - SPARQL pre-binding / `sh:value` (3 `test_custom_constraint_components`): engine follows the draft (SELECT validators pre-bind `$this` and
     parameters only; ASK validators pre-bind `$this`, `$value`, so `sh:value` is the value node). Update the expected results.
   - blank-node closure in reports (5: `test_recursion` 3, `test_native_backend_oxigraph_store` 2): report content, decision only.
   - node-expression failures (3 `test_node_expression_failures`: `sh:targetNode` expression with focus = shape, now fixed; custom SPARQL function in a
     constraint query, fixed by "callable by IRI": rerun), `test_hunt3_targets[sparql_target]`, `test_new_target_types` (DROP-LEGACY),
     ambient `@prefix` (3, `test_sh_values` x2 and `test_sparql_shacl_integration`: DROP-LEGACY / fix the `prefixes-002` distractor), legacy `sh:` forms (1),
     `conformsToShape` multi-output (1), malformed `uniqueValuesFor` under `meta_shacl=False` (1, plus 3 `test_meta_shapes_extensions` differs).
4. **pyshacl-specific** (delete or convert to differential fixtures): `test_pyshacl_smoke` (1 test), `test_pyshacl_inference_compat` (8),
   `test_pyshacl_parity_small_differences` (4), `test_rdf11_parity` (11), the `conftest.py` pyshacl import guard (lines 12-27: remove at stage 4), about 20 files
   guarded by `pytest.importorskip("pyshacl")`, tests of internals (`test_adapters`, `test_types`, `test_triple_term_graph`,
   `test_shacl_list_helpers`, `test_eval_expr_sparql_text`, `test_node_expression_failures` and `test_w3c_node_expr.py` which import
   `shacl.adapters`, `shacl.node_expressions`, `_patch_*` helpers: 27 files touch `_patch_`, `register_native_components`, `_default_validate`,
   `shacl.node_expressions`, `shacl.rule_engine`, `shacl.adapters` or `TripleTermAdapter` directly). These move with the deleted code (stage 3).
5. **Expected-raise tests** (`old_error`, 137 calls, 75 tests): 98 calls in `test_meta_shapes_extensions.py` (meta-SHACL preflight; the engine's `meta.py` now exists,
   so rerun to see how many still raise), 5 in `test_validator.py`, 4 in `test_hunt3_shacl_fastpath.py`, 3 each in `shapes_graph_imports`, `shacl_r4`, `hunt3_shacl_audit2`.
   Engine raised on 16 and returned on 11 of the 27 it was run on (leniency, differential category 11); each needs an explicit decision on which errors
   `validate` must raise (imports without loader, unsupported regime, unknown rule processor, literal `sh:targetWhere`, `inference=` TypeError).
6. Slow tests: the differential run takes 22 minutes with pyshacl in the loop; the engine alone runs 619 tests in 43 s. Expect the shacl directory's CI time to drop
   by more than half after stage 3.

## 4. Staged plan with gates

### Stage a: opt-in switch plus differential CI job
- Change: `shacl/_engine_adapter.py` (~250 lines, new); `validator.py` dispatch in `validate` and `StarShaclSchema.validate/apply_rules` (+40 lines, 1 file);
  engine keyword `engine="pyshacl"|"native"` (default `pyshacl`) and env `STARLAYER_SHACL_ENGINE`; `api.validate(plan=...)`; move `differential_plugin.py` into CI as a
  nightly job (22 min) plus a PR job on the 50 non-agreeing tests; regenerate `results2.jsonl`. Close the open engine items that block a clean run: `pre-binding-002`,
  `sh:SPARQLTarget`, nested `uniqueValuesFor` decision, `sparql:tz`, RDFS regime via `sh:entailment`, custom list/named-parameter functions (6 engine_error in run 1, now partly fixed).
  Total: ~700 lines, 6 files, plus 1 workflow file.
- Entry criteria (all measurable): engine W3C suites 0 new failures (today 619 pass, 2 fail: fix `pre-binding-002`); differential `engine_error` = 0 and
  `differ` <= 34 with each remaining one classified; every `differ` in `-differential.md` has a verdict; adapter covers `validate`, `StarShaclSchema.validate`, `apply_rules` only.
- Risk: low (default unchanged). Risk of drift: two code paths. Mitigation: the nightly job fails on any new differ.
- Rollback: delete the env var / argument; no data change.
- Users told: new `engine="native"` option; no behaviour change.

### Stage b: default flip
- Change: default `engine="native"`; run the entire `tests/shacl` and the 14 other test files against the native engine in CI (`STARLAYER_SHACL_ENGINE=native` as the CI default);
  adapters for `evaluate`, `extract_subgraph`, `extract_shapes_graph`, `close_shape`, `select_widgets` (~700 lines new on `Plan`/`Shape`, 4 files, section 1.4); port the 5
  `ShapeRecursionWarning` wrappers; migrate the 27 + 15 tests of categories 3 to 4 that must change (rewrite expected results: ~80 lines across ~6 files). pyshacl stays installed, reachable by `engine="pyshacl"`.
  Total ~1,100 lines, ~14 files.
- Entry criteria: nightly differential over 2 consecutive weeks with `engine_error` = 0, `differ` = only the documented set, `skipped` = only options deliberately dropped;
  `tests/shacl` + the 14 outside files: 100% pass on native (today unknown; run once at stage a end; expect the ~94% figure plus category 2-5 fixes); all W3C
  engine suites green; the five items in section 5 marked "before b" done; benchmark: `benchmarks-shacl/bench_engine_vs_old.py` shows native no more than 1.0x old wall time
  and no more than 1.5x peak RSS on 10k and 200k-triple data and on the `select_widgets` workload (the CI regression check `check_benchmark_regression.py` already exists);
  the notebooks `04*`, `01`, `05d` execute with the native engine (`review-notebook-links` check passes).
- Risk: medium. The unmeasured part is report text and SHACL-SHACL behaviours that the differential does not compare; also performance on SPARQL-heavy shapes
  (engine SPARQL goes through `StarLayerGraph.query`, one query per focus node). Downstream: `starlayer-kg` (`tools/kg/codekg/queries.py:320`), `sparql/{srl,sqe,salg}` shape checks, `starontology` shipped-shapes tests.
- Rollback: set the default back to `pyshacl` (one line) or env var in the field; pyshacl is still a dependency so no reinstall.
- Users told (release notes, from "old-validator deviations" and DROP-LEGACY): see 4.1.

### Stage c: delete the patches and pyshacl-coupled code
- Delete from `validator.py` (line ranges, 711 lines of `_patch_*` functions; helpers that exist only for them extra):
  `_patch_stringify_for_native_backend_bnodes` 4344-4457 (114), `_patch_rules_for_native_engine` 4742-4820 (79), `_patch_shape_validate_for_filter_shape` 5084-5143 (60),
  `_patch_rdflib_data_graph_clone_preserves_tt_adapter` 5144-5271 (128), `_patch_shape_value_nodes_for_sh_values` 5381-5537 (157),
  `_patch_shape_focus_nodes_for_deactivated_expression` 5538-5621 (84), `_patch_expression_constraint_for_value_scope` 5622-5710 (89). Support helpers (~520): `_GlobalShape`,
  `_global_engine_rules`, `_borrow_template_rules`, `_check_rule_processors` 4596-4741; `_materialize_expected_predicates`, `_materialize_default_value_triples`, `_strip_temp_triples`,
  `_shape_target_nodes` 4821-5083; `_compute_sh_values`, `_compute_sh_default_value` 5272-5380. Plus `_reject_unknown_validate_options`, `_default_validate`, `_PYSHACL_KEYWORD_OPTIONS` 5728-5775.
  Also delete: `native_components.py` (3,416), `node_expressions.py` 890, `sparql_node_expressions.py` 499, `rule_engine.py` 398, `triple_rule.py` 110, `rule_conditions.py` 117, `component_cache.py` 69,
  `recursion.py` 91, `list_functions.py` 80, `shacl/entailment.py` 221 (engine has its own), `shacl/engine/` 375, `adapters.py` 715 (after the deprecation release), the two parallel pipeline bodies in `validator.py`,
  `sparql/salg/native_components.py` (the pyshacl twin of `engine_components.py`; ~200 lines, check), the `ShapeRecursionWarning` wrappers, the `engine="pyshacl"` branch.
  Net: about -11,300 lines, 17+ files; +~300 lines (`MetaShaclError` base fix, errors module).
- Entry criteria: stage b default has been in a release for at least 1 minor version with no `engine="pyshacl"` reports; zero use of `engine="pyshacl"` in repo CI and notebooks;
  differential job retired (no reference left: see risk) but a frozen golden snapshot (results2-style JSONL of expected conforms/results for the 951 tests) kept as the regression oracle.
- Risk: medium-high on review size; the differential oracle disappears at this point. Mitigation: keep `docs/working/differential/results3.jsonl` and an `old/` tag
  (`shacl-engine-baseline`, tag already exists) so the old validator can be re-run from a checkout.
- Rollback: revert the merge commit; since stage b already flipped the default nothing runtime-wise depends on the deleted code.
- Users told: removal of `validate_fn`, `adapter`, `decode_report`, `evaluate_component`, `ComponentRequest`, `shacl.engine`, `TripleTermAdapter` internals; list in the release notes with the replacement.

### Stage d: remove the pyshacl dependency
- Change: `pyproject.toml:16-22` delete the dependency and its comment, drop `"pyshacl"` from `keywords` (line 24), remove the `conftest.py` import guard,
  the `importorskip("pyshacl")` guards, the 4 pyshacl comparison test files (24 tests), fix `shacl_engine/meta.py:21` (own base class), rewrite doc comments naming pyshacl (`starlayer/__init__.py:4`, `docs/shacl/compatibility.md`, `docs/upstream-issues/pyshacl-upstream-issues.md` becomes historical),
  regenerate lockfile, API reference (`scripts/` generator; see main's "Regenerate the API reference" commit), the 12 cells in `04c-shacl-inference-rules.ipynb`, 5 in `01-getting-started.ipynb`, 2 in `04-shacl-shapes.ipynb`.
  Also check `rdflib` transitive pins that pyshacl pulled in (`owlrl`, `prettytable`, `packaging`): remove from direct dependencies only if unused (`owlrl` is still the entailment oracle per memory note).
  ~150 lines, ~12 files.
- Entry criteria: `pip install` of a clean env without pyshacl then full test suite green; `python -c "import pyshacl"` fails in CI job and `grep -rn pyshacl packages/ tools/ scripts/ --include='*.py'` returns only historical docs.
- Risk: low; rollback revert, re-add dependency.
- Users told: pyshacl is no longer installed; code that imported `pyshacl` through starlayer must declare it.

### 4.1 Release notes: behaviours that change (from the differential doc)
Old-validator deviations (engine follows the draft):
- ASK-based component validators pre-bind `$this` and `$value`, so `sh:value` in the result is the value node (old reported none); SELECT validators pre-bind `$this` and the parameters only
  (old also pre-bound `?value`). Queries with a bare `FILTER (?value < ?x)` and no graph pattern stop matching.
- `shnex:conformsToShape` with an argument of several output nodes is an evaluation failure (Node Expressions 4.5.3), not a violation.
- A blank-node focus or value in the report copies the full closure of that node, not a depth-truncated one.
- `validate()` applies `sh:rule` only with `rules=True` (or `mode="rules"`) or when `sh:entailment` is declared; old always applied it first.
- `sh:uniqueValuesFor` inside shapes reached only through `sh:node/and/or/xone/not` or `sh:qualifiedValueShape` compares against the shape's own targets (Core 7.9.5);
  nested use without targets no longer reports duplicates (15 test calls).
- Engine is more lenient where the old validator raised (category 11): imports without loader, unsupported regimes, some malformed shapes; decide per item whether to restore the error.
DROP-LEGACY (removed, no replacement, issue #185):
- SPARQL queries using a Turtle `@prefix` that is not declared via `sh:declare`/`sh:prefixes` (3 calls).
- `sh:SPARQLTarget` as an old-style target (if the Core draft is confirmed not to define it; note feasibility doc lists it as in the vocabulary: decide before b).
- Shapes-graph-only `rdfs:subClassOf` for implicit class targets, and `rdfs_subclass_reasoning_includes_shapes_graph`.
- Legacy `sh:`-namespaced node expressions (`sh:union`, `sh:intersection`, `sh:filterShape`, `sh:path` as expression) and the `sh:filterShape` shim.
- Malformed `sh:uniqueValuesFor` accepted under `meta_shacl=False` (now a `ShapeError`).
- Dropped keywords: `validate_fn`, `adapter`, `decode_report`, `advanced`, `debug`, `js`, `iterate_rules`, `sparql_mode`, `do_owl_imports`, `*_format`, `serialize_*`.

## 5. What remains in the engine before stage b

| Item | Today | Size guess | Must precede b? |
|---|---|---:|---|
| Custom node-expression functions: `sh:ListParameterExpressionFunction`, `sh:NamedParameterExpressionFunction` defining predicate = function IRI / key-parameter path, `shnex:arg`, SPARQL-body functions (differential cat. 6; partly fixed in round 2: callable by IRI from `sh:select`/`sh:ask`) | `expressions._custom_functions`, `_call_custom` exist; the 6 run-1 engine_errors are down to 0 of that kind in `results2` | 100-200 lines + 10 tests | yes (worked examples in spec) |
| `sh:SPARQLTarget` / `sh:SPARQLTargetType`, `$currentShape`, `$shapesGraph` (0 grep hits) | missing; `test_hunt3_targets[sparql_target]` differs | 120-250 lines (`targets.py`, `sparql_support`) | yes if kept in the draft; otherwise DROP-LEGACY |
| `sh:ruleProcessor` (3 refs: selection only; `_check_rule_processors` old code raises on an unknown processor) | partial | 60 lines | yes (3 test files) |
| `sh:sourceRule` provenance reifiers (`include_source_rule_provenance`) | 0 refs | 150-250 lines in `rules._Run` (record which rule produced a triple) | yes (`test_source_rule_provenance`) |
| `iterate_rules` (pyshacl iteration to fixpoint; engine rules run layer/runOnce/iterating per the draft pseudocode) | not offered | 30 lines if the draft's iteration is the same; otherwise drop the option | decide; 3 calls |
| `decode_report` | not offered; nothing to decode | 0 (ignore option) | no |
| `validate_fn` | not offered | 0 in engine; adapter hook ~20 lines or drop | no (16 calls, 1 file) |
| `StarShaclSchema` caches / reuse of a `Plan` across calls | `Plan` rebuilt each call | 20 lines (`plan=`) + invalidation tests | yes for the performance gate |
| `evaluate`, `extract_subgraph`, `extract_shapes_graph`, `close_shape` on `Plan` | missing (section 1.4) | 500-700 lines | yes (public API) |
| `report_text` formatter, `ExecutionDiagnostics` | `meta._report_text` only | 60-100 lines | yes |
| `validate_each` | missing | 40-80 lines | yes (public API) |
| RDFS (and other) entailment regimes declared by `sh:entailment` | rules-based only; `inference=` is handled (`entailment.py`) | 60-120 lines | yes (3 differs) |
| `sh:uniqueValuesFor` nested semantics; `"1"^^xsd:boolean`; `sparql:tz`; `pre-binding-002` double row | open or recently fixed (round 2) | 20-80 lines each | yes |
| Triple term as `sh:value` in `report.build_report` (plain `Graph` asserts; plugin retries with `StarLayerGraph`) | worked around by the plugin only | 10 lines (build report in a triple-term-capable graph) | yes (22 calls) |
| Prefix resolution: only `sh:declare`/`sh:prefixes` of the `sh:ShapesGraph`, not the `owl:Ontology` distractor | 1 engine_error | 20 lines | yes |
| Meta/imports wiring: `api.validate` marks `meta.py`/`imports.py` as "TODO(wiring)" with try/except ImportError, and only resolves imports when a loader is given | seams only | 40 lines (remove ImportError guards; raise on unresolved `owl:imports` unless `ignore_imports`, as old default) | yes |
| `MetaShaclError` base class pyshacl import | `meta.py:21` | 10 lines | by stage d |
| Oxigraph-normalised literals (oxigraph#526) | store limitation, 7 xfails | n/a | no, document |

Rough total before b: 1,300 to 2,000 lines of engine and adapter code plus test rewrites.

## 6. Rust port notes

### 6.1 Pure data that serialises to JSON now
- **Plan format** (`plan.py`, 88 lines): `Shape`, `Path` are frozen dataclasses of terms and tuples. Serialisation needs a term encoding (IRI, bnode, literal with lexical form, datatype, lang,
  direction, triple term) and replacing `Plan.shapes_graph` (a graph reference and lazy builder) with an eager `shapes: dict[node, Shape]` plus the prefix and import tables;
  `Plan.shape()` laziness is a Python convenience, a Rust plan is built in one pass (error: malformed shape = plan error, like `ShapeError`).
- **Component registry** (`components/registry.py`, 62 lines): `ComponentSpec(iri, predicates, required)` is data; `fn` is code. Rust gets a table `iri -> (predicates, required)`
  plus a `match` on the IRI. `Violation` (value, message, path, component, source_constraint, severity, annotations) is the single record type crossing the boundary.
- **Operator table** (`expressions.py`, 687 lines, `@operator(*iris)` decorators, 21 `shnex:` operators plus the `sparql:` function namespace): the IRI to arity/role table is data;
  the per-operator functions are about 450 lines of straightforward list/term code that port one-to-one.
- **Result record** (`executor.Result`) and report mapping (`report.py`, 108): data.
- Rule model (`rules.Rule`: layer, order, run_once, conditions, body; `rules.py` selection, `_groups`, `entailment_selection`): the data (read_rule) and the layer/iteration driver are portable; SPARQL bodies are not.
- Targets (`targets.py`, 117), paths (`paths.py`, 140), deactivation (24): pure over the `GraphView` protocol (`interface.py`: `match` plus `sparql_query`).

### 6.2 What depends on starlayer's query layer and needs another SPARQL engine
Every SPARQL use goes through `sparql_support.py` (378 lines) and `rules.py:145`: `prepareQuery(text)` then `graph.query(prepared, initBindings=...)` (StarLayerGraph/rdflib algebra with starlayer patches),
for `sh:sparql` constraints and `sh:select`/`sh:ask` in components (`components/sparql_constraints.py`, `sparql_components.py`), `sh:SPARQLRule` bodies, `sh:select`/`sh:sparqlExpr` node expressions,
`sparql:` function calls (`_run_call` in `expressions.py`), SPARQL targets. `OxigraphGraph.sparql_query` (`oxigraph_view.py:180`) already implements the optional `SparqlCapable` protocol, so the seam exists.
A Rust executor would use `spareval`/`oxigraph` (SPARQL 1.2 parse via `spargebra`). The semantics to freeze:
- **Pre-binding is not `initBindings`.** SHACL-SPARQL Appendix A: the pre-bound row is joined into every basic graph pattern (equivalently, a `VALUES`/substitution at the start of each group), and `MINUS`,
  `VALUES`, `SERVICE`, and `AS` of a pre-bound variable are rejected up front (the engine already rejects them in `sparql_support`). rdflib's `initBindings` and Oxigraph's substitution differ for a query like
  `SELECT $this ?value WHERE { FILTER (?value < ?minScore) }`: with substitution of the variable into patterns and filters the result is empty; with "bind then evaluate" semantic the old code returned a row. This
  is the source of differential category 5 and test `pre-binding-002`. In Oxigraph use `QueryOptions` substitution through `PreparedQuery::substitute_variable` (spareval) or rewrite the algebra; do not use an outer join.
- Triple terms and `rdf:dirLangString`: needs RDF 1.2 support in spargebra/spareval (feature `rdf-12`); the starlayer query layer has patches for arithmetic and decimal lexical forms (`graph/query/*_patches.py`,
  multiply/divide/ceil/floor/round, `sparql:tz`): the port must have an equivalent function library, test against the W3C SPARQL 1.2 data and the `node-expr/shnex-sparql` cases.
- Lexical forms: Oxigraph normalises literals on storage (oxigraph#526); either keep the shapes/data lexical forms in a side table or run SHACL over an in-memory graph and use Oxigraph only for SPARQL.
- Error mapping: a SPARQL evaluation error is a validation failure/`sh:Violation` per component rules, not an exception; the Python code catches broad exceptions in places: freeze this in the contract.
- Function calls from `sh:select` into node-expression functions (list-parameter functions by IRI, SPARQL 7.3): needs an extension-function hook in spareval; today `_run_call` inlines.

### 6.3 Spec-dependent decisions to freeze before any Rust
1. Recursion: positive re-entry assumed conforming, cycle through `sh:not` is a failure (`Context.conforms`). Core 6.7.3 leaves it to the implementation.
2. `sh:uniqueValuesFor`: peer set = the shape's own targets (Core 7.9.5); nested reach semantics (15 tests).
3. `sh:class`/`sh:datatype`/`sh:nodeKind` accepting an `rdf:list` as a union (two fixtures need it).
4. `sh:nodeKind` and triple terms (`sh:TripleTerm` only matches a triple term) and `sh:targetWhere` candidate set (all subjects and objects; triple-term components not enumerated).
5. Implicit class targets and `sh:rootClass`: subclass triples from the data graph only (not the shapes graph).
6. Only `"true"` (not `"1"`) activates boolean parameters; `sh:deactivated` as a node expression evaluated per focus node.
7. Pre-binding rules (above), which of `$this`, `$value`, `$PATH`, `$currentShape`, `$shapesGraph` are bound for which validator type, and `sh:value` for ASK validators.
8. Report content: blank-node closure copied in full vs depth-limited; `sh:detail` for list components; result ordering is unspecified (compare as multisets).
9. Rules: layer/order/`runOnce`/iteration termination, `sh:tempTriple`, `sh:expectedPredicate`, `sh:ruleProcessor`, rule sets, what `sh:sourceRule` records, and that rules never mutate the caller's graph (`InferredView`).
10. Entailment: which regimes (`sh:entailment`, `inference=`), and `owlrl` as the oracle versus a Rust implementation (RDFS closure is small; OWL RL is not).
11. Prefix resolution: `sh:declare`/`sh:prefixes` only; no ambient `@prefix`; no `owl:Ontology` declares (W3C `prefixes-002`).
12. Error model: which malformed-shape cases are `ShapeError` before validation (plan errors) and which are tolerated; `meta_shacl` preflight and `max_validation_depth` default 500.
13. Term model: equality on RDF terms with lexical forms preserved, ill-formed literals kept, triple terms first-class.
14. Evaluation order and `abort_on_first`: first constraint component producing a result (order-dependent; define the component order or drop the option).

## Appendix: commands used
`wc -l` over `starlayer/shacl*/`, `grep -rn pyshacl` (by file), `grep -n 'def _patch_'` in `validator.py`, a Python pass over
`docs/working/differential/results2.jsonl` (outcome per test), and `pytest tests/shacl_engine test_w3c_engine_*` (619 passed, 2 failed in 43 s).
