# SHACL engine: differential run on the project's own tests

Branch `shacl-engine`. The old validator (`starlayer.shacl`, pyshacl-backed) and the native engine
(`starlayer.shacl_engine`) were run on the same (data graph, shapes graph) for every `validate` / `StarShaclSchema.validate`
call made by `packages/starlayer/tests/shacl` (unit and integration; `w3c_shacl12` and `tests/shacl_engine` excluded;
default tier). Harness: `packages/starlayer/tests/shacl/differential_plugin.py`. Raw records: `docs/working/differential/results.jsonl`
(git-ignored).

Comparison: `sh:conforms` plus the multiset of results as (focusNode, resultPath, sourceConstraintComponent, value,
severity), blank nodes fingerprinted structurally (`comparison.find_report_node` / `conforms_of`; triple terms fingerprinted
by component, because `str(TripleTerm)` depends on the source graph's namespace manager). `sh:sourceShape`, messages and
report text are not compared. The engine ran on private snapshots taken before the old call; its input graphs never changed
(0 mutations seen). Run: 1,738 tests passed, 951 distinct tests made at least one call, 22 min with pyshacl in the loop.

## Summary

| | calls | share |
|---|---:|---:|
| total comparable calls | 3,136 | |
| agree (same conforms, same result multiset) | 2,806 | 89.5% |
| differ | 36 | 1.1% |
| engine_error | 12 | 0.4% |
| skipped (option the engine does not support) | 145 | 4.6% |
| old_error (old validator raised; the test expects it) | 137 | 4.4% |

Of the 2,991 calls the engine could be asked about (agree + differ + engine_error), 93.8% agree, 1.2% differ, 0.4%
engine_error. Longest engine call 0.43 s; no timeout.

Skipped, by option (a call can name several): `meta_shacl` 71, `inference` 24, `shapes_graph_resource` 21, `ont_graph` 20,
`kwarg:max_validation_depth` 18, `validate_fn` 16, `inplace` 7, `decode_report=False` 4, `shapes_graph_loader` 4,
`iterate_rules` 3, `rdfs_subclass_reasoning_includes_shapes_graph` 2, `kwarg:abort_on_first` 1.

old_error (137): the old validator raised, which these tests assert. The engine was also run on 27 of them (the rest used
skipped options, mostly `meta_shacl`, 99 calls): it also raised on 16 and returned a result on 11 (it is more lenient: see
category 11).

## Categories

Verdicts: ENGINE-TO-FIX, DROP-LEGACY (old behaviour that goes with issue #185), OLD-BUG, NEEDS-SPEC-CHECK.

| # | Category | Records | Verdict |
|---|---|---:|---|
| 1 | `sh:uniqueValuesFor` (cross-node) inside nested shapes | 15 differ | NEEDS-SPEC-CHECK (leaning ENGINE-TO-FIX) |
| 2 | `sh:deactivated` given as a node expression | 2 differ | ENGINE-TO-FIX |
| 3 | `"1"^^xsd:boolean` accepted as true | 3 differ | ENGINE-TO-FIX |
| 4 | RDFS entailment regime (`sh:entailment`) | 3 differ | ENGINE-TO-FIX or documented gap |
| 5 | SPARQL-based custom components: select/ASK pre-binding and `sh:value` | 3 differ | NEEDS-SPEC-CHECK |
| 6 | Custom node-expression functions | 6 engine_error | ENGINE-TO-FIX |
| 7 | `sh:SPARQLTarget`, `sh:targetNode` expression with focus = the shape, SPARQL custom function in a constraint | 4 differ | ENGINE-TO-FIX |
| 8 | Triple term as `sh:value` crashes the report builder | 22 calls (now worked around) | ENGINE-TO-FIX |
| 9 | Blank-node closure copied into the report | 4 differ | NEEDS-SPEC-CHECK (report content) |
| 10 | Prefix resolution: ambient namespaces and distractor declares | 3 engine_error | DROP-LEGACY (2) / ENGINE-TO-FIX (1) |
| 11 | Engine more lenient than old on malformed input | 11 old_error | NEEDS-SPEC-CHECK |
| 12 | Shapes-graph `rdfs:subClassOf` for implicit class targets | 1 differ | DROP-LEGACY |
| 13 | `sparql:tz` result | 1 differ | ENGINE-TO-FIX |
| 14 | Legacy `sh:` node-expression forms | 1 engine_error | DROP-LEGACY |
| 15 | `conformsToShape` with several output nodes | 1 engine_error | NEEDS-SPEC-CHECK |
| 16 | Malformed `sh:uniqueValuesFor` under `meta_shacl=False` | 1 engine_error | NEEDS-SPEC-CHECK (old is tolerant) |

### 1. sh:uniqueValuesFor inside sh:and / sh:or / sh:xone / sh:not / sh:node / qualified shapes (15 differ)
Old reports the duplicate through the wrapper; the engine conforms (14 of 15; the `not` double-negative and two
qualified-shape cases flip the other way). Examples:
`integration/test_native_component_composition.py::test_unique_values_for_inside_direct_node_correctly_detects_duplicate`,
`::test_unique_values_for_inside_and_correctly_detects_duplicate`,
`::test_unique_values_for_inside_not_conforms_via_double_negative`.
Diagnosis: the engine compares "nodes targeted by the same shape" per owning shape, so a node shape reached only through
`sh:node`/`sh:and` has no peer set; the old validator looks across every node that reaches the shape (its own
extension to pySHACL). The vocabulary comment says "no two nodes targeted by the same shape", which does not say what a
nested reach means. Decide the semantics; the project tests encode the old one.

### 2. sh:deactivated as a node expression (2 differ)
`integration/test_node_expression_integration_points.py::TestDeactivatedExpression::test_evaluated_per_focus_node_not_globally`,
`::test_global_condition_deactivates_every_target_uniformly`. The engine reads only literal `true` (`builder.py`
lines 31 and 50); a node-expression value is evaluated per focus node in the old code (SHACL 1.2 Core "Deactivating Shapes
and Constraints"). Engine misses the feature.

### 3. Alternate boolean lexical form (3 differ)
`integration/test_list_constraints.py::test_unique_members_alternate_boolean_lexical_form_leaves_constraint_inactive`,
`integration/test_single_line_and_some_value.py::...single_line_alternate_boolean...`,
`integration/test_reification_constraints.py::...reification_required_alternate_boolean...`. Only `"true"` turns these
on; `"1"^^xsd:boolean` must leave them inactive (these tests record that W3C `uniqueLang-002` needs it). The engine passes
that W3C case but treats `"1"` as true for `uniqueMembers`, `singleLine` and `reificationRequired` (and for
`sh:deactivated`, see `builder.py` `("true", "1")`). Apply the "only true" rule uniformly.

### 4. sh:entailment naming an RDFS regime (3 differ)
`integration/test_sh_entailment.py::TestValidateRespectsShEntailment::test_with_sh_entailment_alice_becomes_a_target_and_violates`,
`::test_plain_validation_profile_never_mutates_the_callers_data_graph`,
`integration/test_rules_entailment.py::test_rules_entailment_combines_with_an_entailment_regime`. The engine runs only the
rule-based entailment (`sh:RulesEntailment`, rule sets) and ignores RDFS/other regimes. Also, an unsupported regime or
an IRI that is neither a regime nor a rule set raises in the old code and is silently ignored by the engine
(category 11). Entailment regimes are skipped when passed as `inference=` (24 calls), so this is the declared-in-shapes path.

### 5. SPARQL-based custom constraint components (3 differ)
`integration/test_custom_constraint_components.py::test_select_based_custom_component_flags_violations` (old violates,
engine conforms), `::test_ask_based_custom_component_flags_violations` and
`::test_ask_based_custom_component_over_rdf12_triple_term_value` (same verdict; old omits `sh:value`, engine reports the
value node). The select query is `SELECT $this ?value WHERE { FILTER (?value < ?minScore) }`: no graph pattern, so under
the SHACL 1.2 SPARQL appendix's "join the pre-bound row into every basic graph pattern" the variables are unbound and
nothing is returned; the old code substitutes (pySHACL `initBindings`). Check Appendix A and the rule for `sh:value` in
ASK-based validators.

### 6. Custom node-expression functions (6 engine_error)
`integration/test_custom_node_expression_functions.py::TestCustomListParameterFunction::test_spacedconcat_matches_spec_worked_example`,
`::TestCustomNamedParameterFunction::test_average_matches_spec_worked_example`
(all 6 are in `test_custom_node_expression_functions.py`). Error: "a node expression needs exactly one operator predicate, found []".
`sh:ListParameterExpressionFunction` / `sh:NamedParameterExpressionFunction` (function IRI or key-parameter path as the
defining predicate, `shnex:arg`) are in the Node Expressions draft and not implemented in `expressions.py`.

### 7. Targets and functions (4 differ)
- `integration/test_hunt3_targets.py::test_target_nodes_equals_the_focus_nodes_validate_reports_on[sparql_target]`:
  `sh:target [ a sh:SPARQLTarget ; sh:select ... ]` yields no focus nodes in the engine (no `SPARQLTarget` support in
  `targets.py`). ENGINE-TO-FIX (in the vocabulary, see feasibility doc).
- `unit/test_node_expression_failures.py::test_target_node_expression_focus_is_the_shape` (2 calls): `sh:targetNode
  [ shnex:pathValues ex:t ]` and `[ shnex:var "focusNode" ]` are evaluated with the shape node as focus node; the
  engine does not report the targeted nodes.
- `unit/test_node_expression_failures.py::TestListParameterFunctionWithSparqlBody::test_the_function_can_be_called_by_its_iri_from_a_constraint_query`:
  a custom function called from a `sh:sparql` constraint is not available in the engine's query.

### 8. Triple term as sh:value (22 calls)
`report.build_report` builds a plain rdflib `Graph`, whose `add` asserts every object is an rdflib `Node`, so any result
whose value is a triple term raised `AssertionError: Object <<( ... )>> must be an rdflib term`
(`integration/test_hunt2_shacl_fixes.py::test_node_kind_of_a_triple_term[...]`,
`integration/test_report_fidelity.py::test_report_decodes_triple_term_value_node`,
`integration/test_hunt3_shacl_fastpath.py::TestTripleTermValueNodes::...`). The plugin retries with a
`StarLayerGraph` report (`report_graph_patched: true`) and those 22 calls then agree. Fix in the engine: use a graph
that holds triple terms for the report.

### 9. Report content for blank-node values and focus nodes (4 differ)
`integration/test_recursion.py::test_a_nested_shapes_graph_is_checked_against_shacl_shacl_at_depth` (3 calls),
`integration/test_native_backend_oxigraph_store.py::test_validate_and_apply_rules_with_default_graph_store[meta_off-bnode_focus]`.
`conforms`, components, focus nodes and path agree; only the blank-node fingerprint differs, because the two reports copy
different closures of the node into the report (old keeps `ex:seen ex:yes` on a blank focus node; deep list/or structures
differ in depth). The comparison is sensitive to this; likely benign. Decide what a report must carry for blank-node
focus nodes and values.

### 10. Prefix resolution (3 engine_error)
- `integration/test_sh_values.py::test_values_select_computes_the_checked_value_set` and `..._violates_when_computed...`:
  `ex:` used in a `sh:select` with no `sh:prefixes`/`sh:declare`; the old code resolves it from the Turtle `@prefix`
  lines of the shapes graph (pySHACL behaviour). Engine: "Unknown namespace prefix : ex". DROP-LEGACY if the spec requires
  `sh:declare`; confirm.
- `integration/test_sparql_shacl_integration.py::test_sparql_constraint_resolves_prefix_via_ambient_shapes_graph_declare`:
  engine raises "prefix 'test' is declared with two different namespaces" because it also reads the `owl:Ontology`
  distractor declare; the W3C `prefixes-002` case (the one failing sparql test) wants only the `sh:ShapesGraph` declare.
  ENGINE-TO-FIX.

### 11. Engine more lenient than old (11 old_error where the engine returned)
Old raises, engine returns a result: malformed property shape in a closure extract
(`integration/test_extract_shapes_graph_closure.py::test_the_extract_without_the_option_cannot_be_validated_standalone`),
`owl:imports` without a loader (`integration/test_shapes_graph_imports.py::test_without_loader_or_ignore_imports_raises`,
3 calls), unsupported entailment regime (`test_sh_entailment.py::...unsupported_regime_declared_raises`,
`test_rules_entailment.py::...refused`), unknown rule processor
(`test_rule_templates_and_processors.py::TestRuleProcessor::test_entailment_naming_such_a_rule_set_is_refused`...), literal
`sh:targetWhere`, `validate(inference=)` TypeError. Some are old-API policy (imports, `inference=`), some are shape
validation the engine does not do. Decide which errors the engine must raise.

### 12. Shapes-graph subClassOf (1 differ)
`integration/test_new_target_types.py::test_shape_class_implicit_target_follows_rdfs_subclassof_and_needs_no_separate_nodeshape_typing`:
`rdfs:subClassOf` is only in the shapes graph; the old code follows it for implicit class targets, the engine follows
the data graph only (SHACL "SHACL instance" is relative to the data graph). The old `rdfs_subclass_reasoning_includes_shapes_graph`
option exists for `sh:rootClass` for the same reason. DROP-LEGACY unless the spec says otherwise.

### 13. sparql:tz (1 differ)
`integration/test_shnex_node_expressions.py::test_sparql_function_through_real_pipeline[tz]`: `sparql:tz("...Z"^^xsd:dateTime)`
should be `"Z"`; the engine's check fails. Engine bug (SPARQL 1.1 `TZ`).

### 14. Old sh: node-expression forms (1 engine_error)
`integration/test_shnex_node_expressions.py::test_shnex_and_old_sh_forms_coexist_in_same_validate_call`: the old `sh:` forms
are the legacy of issue #185 candidate 1; engine reports "needs exactly one operator predicate". DROP-LEGACY.

### 15, 16. Singletons
- `test_shnex_node_expressions.py::test_conformstoshape_over_expression_yielding_multiple_nodes`: engine raises
  `EvaluationFailure: an argument of shnex:conformsToShape has more than one output node`; the old code accepts. Check
  the Node Expressions text.
- `integration/test_meta_shapes_extensions.py::test_meta_shacl_false_still_skips_preflight_entirely`: malformed
  `sh:uniqueValuesFor` is a ShapeError in the engine, tolerated by the old code when `meta_shacl=False`.

## Rerun

```
cd <worktree root>
PYTHONPATH=packages/starlayer:packages/starlayer/tests/shacl \
  /usr/local/bin/python3 -m pytest packages/starlayer/tests/shacl \
  --ignore=packages/starlayer/tests/shacl/w3c_shacl12 --ignore=packages/starlayer/tests/shacl_engine \
  -p differential_plugin -q -p no:cacheprovider -W ignore
# DIFF_OUT=path.jsonl changes the output file (default docs/working/differential/results.jsonl)
```

Takes about 22 minutes (pyshacl dominates). The summary line is printed on stderr at the end; outcomes are in the JSONL
(`outcome`, `skip_options`, `error`, `details` with only-in-old / only-in-new keys and small Turtle snippets). To rerun only
the non-agreeing tests, pass their node ids to pytest with the same plugin. The checked-in results come from one full run
plus a rerun of the 200 differ / engine_error / old_error tests after two harness fixes (triple-term fingerprint, retry with a
triple-term-capable report graph; `old_error` records also run the engine).

## Run 2 (2026-10-30, after the options round) and triage
`DIFF_OUT=docs/working/differential/results2.jsonl`, same command. 3,126 calls: agree 2,924 (run 1: 2,806 of 3,136),
differ 34 (36), engine_error 6 (12), skipped 25 (145), old_error 137 (137). Skipped now: validate_fn 16, inplace 7,
decode_report=False 4, iterate_rules 3, rdfs_subclass_reasoning_includes_shapes_graph 2.

Remaining differences and their disposition (after the round-2 fixes the affected test files were re-run):
- **Decided, follows the draft, old tests encode a project extension (about 15):** `sh:uniqueValuesFor` in nested shapes
  without targets (Core 7.9.5: peers are the shape's own targets). Revisit these tests at cut-over.
- **DROP-LEGACY (about 8):** SPARQL queries relying on ambient `@prefix` with no `sh:declare` (3 errors); `sh:SPARQLTarget`
  (1); shapes-graph-only `rdfs:subClassOf` for implicit class targets (1); legacy `sh:`-namespaced expression forms (1);
  malformed `sh:uniqueValuesFor` accepted under meta_shacl=False (1).
- **Fixed in round 2:** the three alternate-boolean-lexical-form differs were a harness artifact (`copy.deepcopy` of a
  StarLayerGraph normalised `"1"^^xsd:boolean` to `"true"`; the plugin snapshot now copies term for term). A `sh:targetNode`
  expression is evaluated with the shape as focus (Core 3.1.3.1); the engine now does this. List-parameter functions are
  callable by IRI from `sh:select`/`sh:ask` queries (SPARQL 7.3).
- **Old-validator deviations (engine follows the draft):** ASK validators pre-bind `$this` and `$value`, so `sh:value` is the
  value node (old reports none); SELECT validators pre-bind `$this` and parameters only (old also pre-binds `?value`);
  `shnex:conformsToShape` with an argument of several output nodes is a failure (Node Expressions 4.5.3; old reports a
  violation); the old report copies a blank-node focus/value description truncated at depth, the engine copies the full
  closure (the draft is silent); the old `validate` applies `sh:rule` first, the engine only with `rules=True` or `sh:entailment`.
- **Ported:** `salg:NoUnboundProjectedVariablesConstraintComponent`, via a lazy trampoline
  (`shacl_engine/components/extensions.py` -> `sparql/salg/engine_components.py`), so sqe/srl/spexpr gain no dependency on salg.
Existing salg-related test files (12) still pass: 539 passed.

## Run 3 (2026-10-30, commit 566f507): the gate baseline
`DIFF_OUT=docs/working/differential/results3.jsonl`. 3,046 calls (the project tests on this branch, which still carry the old
nested-`uniqueValuesFor` tests): agree 2,849, differ 29, engine_error 6, skipped 25, old_error 137.
Every remaining difference is in a category already decided above; nothing new appeared after the API and performance rounds:
- nested `sh:uniqueValuesFor` without targets (about 15): the draft (Core 7.9.5) wins; on `main` these tests are rewritten in
  branch `fix-unique-values-for-peers`;
- DROP-LEGACY (about 8): ambient-`@prefix` queries (3), `sh:SPARQLTarget` (2, `target_nodes` comparison), shapes-graph-only
  subclass for implicit class targets (1), legacy `sh:` expression form (1), malformed uniqueValuesFor under meta_shacl=False (1);
- old-validator deviations where the engine follows the draft (ASK/SELECT custom validators 3, conformsToShape with several
  output nodes 1, rules applied before validation 2);
- report-structure artifacts (3 SalG, 3 nested SHACL-SHACL): result sets agree, the blank-node focus description differs.
The skipped 25 have no native equivalent or no need: validate_fn 16, inplace 7 (supported, not comparable by the harness),
iterate_rules 3, decode_report=False 4, rdfs_subclass_reasoning_includes_shapes_graph 2.
