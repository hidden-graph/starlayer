# SHACL engine: the existing SHACL tier run on the native engine (stage a, adapter)

Branch `shacl-engine`, 2026-10-31. The old public API (`validate`, `validate_each`, `apply_rules`, `evaluate`, `extract_subgraph`,
`StarShaclSchema` methods) delegates to `starlayer.shacl_engine` through `starlayer/shacl/native_adapter.py` when asked:
`engine="native"` per call, `StarShaclSchema(..., engine="native")` per schema, or `STARLAYER_SHACL_ENGINE=native` for the process
(pytest: `--shacl-engine native`). Precedence: call keyword, schema default, environment variable, `pyshacl`. An option with no native
equivalent falls back to the old path for that call and records why (`ValidationResult.engine`, `.engine_fallback_reason`; the same
on `RulesResult`; `native_adapter.last_run()` for calls that return a bare graph).

## Command and counts

    STARLAYER_SHACL_ENGINE=native PYTHONPATH=packages/starlayer /usr/local/bin/python3 -m pytest packages/starlayer/tests/shacl \
      --ignore=packages/starlayer/tests/shacl/w3c_shacl12 --ignore=packages/starlayer/tests/shacl_engine -q -p no:cacheprovider -W ignore

(run in three file shards in parallel; the sum is reported).

| run | passed | failed | skipped |
|---|---:|---:|---:|
| default (no variable), baseline | 1738 | 0 | 12 |
| native, first run (adapter as first written) | 1562 | 176 | 12 |
| native, final | 1584 | 154 | 12 |

Engine suite (4 W3C engine files + `tests/shacl_engine`, now with `test_native_adapter.py`): 1316 passed, 2 failed
(`pre-binding-002`, `seconds-example`, as before), 5 xfailed, 1 skipped.

## What was fixed between the first and the final run (176 to 154)

ADAPTER-BUG (fixed):
- `sh:conformanceDisallows` is always written as the explicit set of blocking severities, as the old validator does (the engine
  writes it only for a non-default floor): `test_conformance_disallows::test_default_conformance_disallows_includes_all_three_severities`
  and the three `test_hunt3_shacl_audit2` report tests.
- `apply_rules(..., data_graph_iri=..., shapes_graph_resource=..., ...)`: validate()'s own keywords are accepted by the old
  `apply_rules` (they are forwarded) and were rejected as unknown: `test_used_graphs_and_configuration`.
- `meta_shacl=True` preflight ran with the engine's own tolerant default (Warning and Info allowed) and without the SPARQL text
  check: the adapter now runs `meta_validate` with the caller's `allow_warnings` / `allow_infos` and then
  `check_sparql_query_text`: 7 tests of `test_meta_shapes_extensions` and `test_meta_shacl_integration`.

ENGINE-BUG (fixed, small):
- `InferredView` (the overlay used for entailment and rules) lacked `predicates`, `items`, `namespace_manager`, `namespaces`:
  report text crashed on a blank-node focus under entailment/rules, and printed full IRIs instead of prefixed names
  (`test_starlayergraph_dataset_input`, 6 more).
- `modules.resolve_shapes_resource` turned a `Literal` provenance identity into an IRI (`test_used_graphs_and_configuration`).
- `ShapeError` and `RuleError` now derive from `ValueError`, as the old validator's malformed-shapes errors did (callers that
  catch `ValueError` keep working).

## The 154 remaining native-mode failures, by cause

Every one is in a named disposition below, or is the one open ENGINE-GAP. The tests in the exception-class group assert `pytest.raises(pyshacl.errors.X)`, the old `NodeExpressionError`, or a message regex; the
engine raises its own `ShapeError` / `RuleError` (now `ValueError` subclasses) or, being more lenient, none.


### DISPOSITIONED: SPARQL-based targets removed (branch remove-sparql-targets; differential cat. 7) (3)

- `integration/test_hunt3_targets.py::test_target_nodes_equals_the_focus_nodes_validate_reports_on[sparql_target]`
- `integration/test_extract_subgraph.py::TestWholeShapesGraphExtraction::test_sparql_based_target_is_discovered_via_advanced_mode`
- `integration/test_node_expression_integration_points.py::TestTargetNodeExpression::test_select_based_target_node_still_works`

### DISPOSITIONED: ambient @prefix without sh:declare (differential cat. 10) (4)

- `integration/test_sh_values.py::test_values_select_computes_the_checked_value_set`
- `integration/test_sh_values.py::test_values_select_violates_when_computed_value_does_not_match`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_an_optional_parameter_without_a_value_is_left_unbound`
- `integration/test_sparql_shacl_integration.py::test_sparql_constraint_resolves_prefix_via_ambient_shapes_graph_declare`

### DISPOSITIONED: legacy SHACL-AF forms (sh:this, sh:filterShape, untyped rules; issue #185 / differential cat. 14) (51)

- `integration/test_evaluate_virtual_values.py::TestIsolationFromApplyRules::test_rule_recomputing_the_same_expression_materializes_a_real_triple`
- `integration/test_evaluate_virtual_values.py::TestIsolationFromApplyRules::test_evaluate_and_apply_rules_compose_without_interference`
- `integration/test_hunt3_targets.py::TestRuleConditionList::test_list_means_conforms_to_all_listed_shapes`
- `integration/test_hunt3_targets.py::TestRuleConditionList::test_single_shape_condition_unchanged`
- `integration/test_meta_shapes_extensions.py::TestNodeExpressionWellFormedness::test_real_function_call_fixture_still_works_end_to_end`
- `integration/test_rule_engine.py::test_a_rule_that_is_neither_a_triple_rule_nor_a_sparql_rule_is_a_failure`
- `integration/test_rule_engine.py::test_provenance_of_rules_run_over_a_graph_with_no_triple_terms_does_not_credit_the_encodings_support_triples`
- `integration/test_rule_set_selection.py::TestShapeAttachedRulesPath::test_no_rule_set_runs_every_shape_attached_rule`
- `integration/test_rule_set_selection.py::TestShapeAttachedRulesPath::test_rule_set_restricts_shape_attached_rules_too`
- `integration/test_rules_flow.py::test_apply_rules_adds_inferred_triple`
- `integration/test_rules_flow.py::test_apply_rules_preserves_existing_triple_terms`
- `integration/test_sh_values.py::test_property_rule_sh_values_remains_a_separate_unimplemented_mechanism`
- `integration/test_shacl_ui_compatibility.py::test_shui_annotations_do_not_interfere_with_rule_application`
- `integration/test_shnex_node_expressions.py::test_shnex_pathvalues_with_triple_rule_carries_rdf12_triple_term`
- `integration/test_shnex_node_expressions.py::test_shnex_and_old_sh_forms_coexist_in_same_validate_call`
- `integration/test_used_graphs_and_configuration.py::test_used_data_graph_and_shapes_graph_work_through_apply_rules`
- `integration/test_custom_node_expression_functions.py::TestCustomListParameterFunction::test_spacedconcat_via_triple_rule`
- `integration/test_custom_node_expression_functions.py::TestCustomNamedParameterFunction::test_body_sees_the_real_focus_node_via_shnex_var`
- `integration/test_hunt3_shacl_audit2.py::test_rule_set_accepts_a_plain_str_iri[http://ex/RS1_0]`
- `integration/test_hunt3_shacl_audit2.py::test_rule_set_accepts_a_plain_str_iri[http://ex/RS1_1]`
- `integration/test_hunt3_shacl_audit2.py::test_rule_set_accepts_a_plain_str_iri[rule_set2]`
- `integration/test_hunt3_shacl_audit2.py::test_condition_class_shape_fires_when_superclasses_conform`
- `integration/test_hunt3_shacl_audit2.py::test_condition_ignores_a_deactivated_superclass_shape`
- `integration/test_metadata_only_predicates.py::test_metadata_only_predicates_do_not_interfere_with_rule_application`
- `integration/test_node_expressions_integration.py::test_node_expression_path_carries_triple_term_value`
- `integration/test_node_expressions_integration.py::test_node_expression_union_carries_mixed_values`
- `integration/test_node_expressions_integration.py::test_node_expression_intersection_carries_triple_term_value`
- `integration/test_node_expressions_integration.py::test_node_expression_intersection_carries_plain_rdf11_value`
- `integration/test_node_expressions_integration.py::test_node_expression_shacl_function_carries_triple_term_value`
- `integration/test_shacl_r4.py::test_infer_types_is_idempotent_and_never_types_vocabulary_terms[ex:S sh:targetClass ex:C ; sh:or ( ex:A ex:B ) . ex:A sh:path ex:q .]`
- `integration/test_shacl_ui_form_kinds.py::test_a_triple_rule_with_no_subject_runs_with_the_focus_node_as_subject`
- `integration/test_expression_node_types.py::test_every_expression_under_sh_values_is_typed_including_the_nested_ones`
- `integration/test_expression_node_types.py::test_the_cells_of_the_argument_lists_are_typed_rdf_list`
- `integration/test_expression_node_types.py::test_every_node_under_sh_values_has_a_shape_that_targets_it_once_typed`
- `integration/test_expression_node_types.py::test_any_nesting_depth_is_reached[0]`
- `integration/test_expression_node_types.py::test_any_nesting_depth_is_reached[1]`
- `integration/test_expression_node_types.py::test_any_nesting_depth_is_reached[3]`
- `integration/test_expression_node_types.py::test_any_nesting_depth_is_reached[6]`
- `integration/test_expression_node_types.py::test_the_other_places_an_expression_can_start_are_typed_too[sh:defaultValue]`
- `integration/test_expression_node_types.py::test_the_other_places_an_expression_can_start_are_typed_too[sh:expression]`
- `integration/test_expression_node_types.py::test_a_path_is_not_an_expression`
- `integration/test_expression_node_types.py::test_a_shape_or_a_class_given_to_a_function_is_not_an_expression`
- `integration/test_expression_node_types.py::test_constants_are_not_typed`
- `integration/test_expression_node_types.py::test_lists_outside_expressions_are_not_typed_rdf_list`
- `integration/test_rule_condition.py::test_condition_admits_conforming_focus_node_only`
- `integration/test_rule_condition.py::test_condition_over_rdf12_triple_term_valued_property`
- `integration/test_rule_condition.py::test_condition_shape_does_not_need_explicit_typing`
- `integration/test_rule_condition.py::test_property_rule_sh_values_is_not_implemented`
- `integration/test_sh_entailment.py::TestApplyRulesSeesEntailmentBeforeRulesRun::test_rule_targeting_entailed_class_fires`
- `unit/test_validator.py::test_validate_applies_filter_shape_compatibility_patch_correctly`
- `unit/test_validator.py::test_validate_hard_fails_on_sh_filter_shape_when_patch_unavailable`

### DISPOSITIONED: malformed sh:uniqueValuesFor under meta_shacl=False is a ShapeError (differential cat. 16) (1)

- `integration/test_meta_shapes_extensions.py::test_meta_shacl_false_still_skips_preflight_entirely`

### DISPOSITIONED: nested sh:uniqueValuesFor peers (Core 7.9.5) (15)

- `integration/test_native_component_composition.py::test_unique_values_for_inside_and_correctly_detects_duplicate`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_not_conforms_via_double_negative`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_and_blank_node_inner_shape`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_and_two_properties_one_duplicated`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_xone_correctly_detects_duplicate`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_nested_and_two_levels_deep`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_direct_node_correctly_detects_duplicate`
- `integration/test_native_component_composition.py::test_unique_values_for_via_property_path_then_node_correctly_detects_duplicate`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_qualified_value_shape_correctly_detects_duplicate`
- `integration/test_native_component_composition.py::test_unique_values_for_inside_and_via_node_mixed_mechanism_nesting`
- `integration/test_native_component_composition.py::test_qualified_max_count_with_cross_node_value_shape_conforms_via_vacuous_exclusion`
- `integration/test_native_component_composition.py::test_unique_values_for_via_node_self_reference_terminates_and_still_finds_the_violation`
- `integration/test_native_component_composition.py::test_two_independent_cross_node_shapes_in_and_list_do_not_cross_contaminate`
- `integration/test_native_component_composition.py::test_multi_valued_node_two_independent_cross_node_shapes_do_not_cross_contaminate`
- `integration/test_native_component_composition.py::test_qualified_value_shapes_disjoint_with_cross_node_sibling_conforms_via_duplicate`

### DISPOSITIONED: old-validator deviation (SPARQL pre-binding, conformsToShape multi-output; differential cat. 5, 15) (3)

- `integration/test_custom_constraint_components.py::test_select_based_custom_component_flags_violations`
- `integration/test_custom_constraint_components.py::test_malformed_custom_validator_raises_cleanly_not_a_confusing_typeerror`
- `integration/test_shnex_node_expressions.py::test_conformstoshape_over_expression_yielding_multiple_nodes`

### DISPOSITIONED: shapes-graph-only rdfs:subClassOf for implicit class targets (differential cat. 12) (1)

- `integration/test_new_target_types.py::test_shape_class_implicit_target_follows_rdfs_subclassof_and_needs_no_separate_nodeshape_typing`

### ENGINE-GAP: sh:detail not produced for sh:memberShape (2)

- `integration/test_native_component_composition.py::test_member_shape_one_result_per_list_with_detail_per_bad_member`
- `integration/test_native_component_composition.py::test_member_shape_severity_warning_conforms_when_allowed`

### TEST-ASSERTS-PYSHACL: exception class or message of the old/pySHACL error (engine raises ShapeError/RuleError, or is more lenient: differential cat. 11) (41)

- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_bare_node_is_reported_not_silently_empty[[ sparql:year [ shnex:pathValues ex:birthDate ] ]]`
- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_bare_node_is_reported_not_silently_empty[[ sparql:str [ shnex:pathValues ex:name ] ]]`
- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_bare_node_is_reported_not_silently_empty[[ sparql:concat [ shnex:pathValues ex:name ] ]]`
- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_bare_node_is_reported_not_silently_empty[[ shnex:concat [ shnex:pathValues ex:name ] ]]`
- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_bare_node_is_reported_not_silently_empty[[ shnex:intersection [ shnex:pathValues ex:name ] ]]`
- `integration/test_evaluate_virtual_values.py::TestFunctionArgumentMustBeAList::test_a_bare_node_nested_in_coalesce_no_longer_falls_back_quietly`
- `integration/test_node_expressions_hunt2.py::test_negative_limit_and_offset_are_not_python_slices[limit]`
- `integration/test_node_expressions_hunt2.py::test_negative_limit_and_offset_are_not_python_slices[offset]`
- `integration/test_closed_by_types.py::TestClosedMalformedValueRejectedCleanly::test_string_literal_false_is_rejected_not_silently_coerced_to_true`
- `integration/test_closed_by_types.py::TestClosedMalformedValueRejectedCleanly::test_iri_value_is_still_rejected_cleanly`
- `integration/test_custom_node_expression_functions.py::TestCustomFunctionAmbiguity::test_blank_node_matching_two_functions_key_parameters_raises`
- `integration/test_extract_shapes_graph_closure.py::test_the_extract_without_the_option_cannot_be_validated_standalone`
- `integration/test_hunt3_shacl_audit2.py::test_reification_on_a_non_iri_path_is_a_shapes_graph_error[ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path (ex:p ex:q) ; sh:reificationRequired true ] .]`
- `integration/test_hunt3_shacl_audit2.py::test_reification_on_a_non_iri_path_is_a_shapes_graph_error[ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path [ sh:inversePath ex:p ] ; sh:reificationRequired true ] .]`
- `integration/test_hunt3_shacl_audit2.py::test_reification_on_a_non_iri_path_is_a_shapes_graph_error[ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:reificationRequired true .]`
- `integration/test_hunt3_shacl_audit2.py::test_non_numeric_order_is_a_rule_load_error["a"]`
- `integration/test_hunt3_shacl_audit2.py::test_non_numeric_order_is_a_rule_load_error["1.5"]`
- `integration/test_hunt3_shacl_audit2.py::test_non_numeric_order_is_a_rule_load_error[true]`
- `integration/test_meta_shacl_integration.py::test_meta_shacl_override_false_skips_preflight_but_still_errors_on_bad_shape_load`
- `integration/test_pyshacl_inference_compat.py::TestInferenceNoneAndInvalid::test_pyshacl_style_string_no_longer_accepted`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_a_subclass_of_a_template_has_instances_too`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_a_required_parameter_without_a_value_is_a_failure`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_a_required_parameter_without_a_value_is_a_failure_for_an_attached_instance_too`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_a_parameter_with_two_values_is_a_failure`
- `integration/test_rule_templates_and_processors.py::TestTemplates::test_an_instance_of_two_templates_is_a_failure`
- `integration/test_rule_templates_and_processors.py::TestRuleProcessor::test_a_rule_that_names_a_processor_is_a_failure`
- `integration/test_rule_templates_and_processors.py::TestRuleProcessor::test_a_string_names_a_processor_too`
- `integration/test_rule_templates_and_processors.py::TestRuleProcessor::test_a_selected_rule_set_that_names_a_processor_is_a_failure`
- `integration/test_rule_templates_and_processors.py::TestRuleProcessor::test_a_processor_of_an_included_rule_set_applies_to_the_including_one`
- `integration/test_rule_templates_and_processors.py::TestRuleProcessor::test_entailment_naming_such_a_rule_set_is_a_failure`
- `integration/test_shacl_r4.py::test_global_sparql_rule_with_a_bad_construct_raises[CONSTRUCT { ?s <http://ex/p> ?o WHERE { ?s ?p ?o }]`
- `integration/test_shacl_r4.py::test_global_sparql_rule_with_a_bad_construct_raises[CONSTRUCT { ?s zz:p ?o } WHERE { ?s ?p ?o }]`
- `integration/test_shacl_r4.py::test_global_sparql_rule_with_a_non_construct_query_raises_a_clear_error[SELECT * WHERE { ?s ?p ?o }]`
- `integration/test_shacl_r4.py::test_global_sparql_rule_with_a_non_construct_query_raises_a_clear_error[ASK { ?s ?p ?o }]`
- `integration/test_shacl_r4.py::test_sh_pattern_that_cannot_be_translated_raises_a_clear_error[^\\p{Foo}$]`
- `integration/test_shacl_r4.py::test_sh_pattern_that_cannot_be_translated_raises_a_clear_error[^\\p{IsFoo}$]`
- `integration/test_shacl_r4.py::test_sh_pattern_that_cannot_be_translated_raises_a_clear_error[(]`
- `integration/test_hunt3_shacl_fastpath.py::TestInvalidPattern::test_an_invalid_regex_is_a_clean_error_naming_the_pattern`
- `integration/test_small_fixes_172_169.py::test_a_literal_target_where_raises_shape_load_error_with_the_function`
- `integration/test_small_fixes_172_169.py::test_a_literal_target_where_raises_shape_load_error_with_the_method`
- `unit/test_validator.py::test_validate_hard_fails_when_reification_path_is_not_simple_iri`

### TEST-ASSERTS-PYSHACL: internals of the pySHACL pipeline (patches, component cache, typing helpers, call recording) (8)

- `unit/test_component_cache.py::test_sh_in_list_is_walked_once_not_once_per_focus_node`
- `integration/test_shape_types.py::test_a_shape_with_a_target_and_no_path_is_a_node_shape`
- `integration/test_shape_types.py::test_every_member_of_an_or_list_is_a_shape_including_one_with_no_constraints`
- `integration/test_shape_types.py::test_and_and_xone_lists_are_walked_too`
- `integration/test_shape_types.py::test_non_shapes_get_their_type_from_the_vocabulary`
- `unit/test_validator.py::test_apply_rules_requests_inplace_advanced_mode`
- `unit/test_validator.py::test_apply_rules_carries_diagnostics`
- `unit/test_validator.py::test_apply_rules_uses_rules_profile_defaults`

### TEST-ASSERTS-PYSHACL: result message wording of pySHACL (25)

- `integration/test_shacl_r4.py::test_reifier_shape_violation_carries_a_result_message`
- `integration/test_hunt3_shacl_fastpath.py::TestNodeKindMessage::test_single_kind_violation_has_pyshacls_message`
- `integration/test_hunt3_shacl_fastpath.py::TestNodeKindMessage::test_node_shape_violation_has_a_message`
- `integration/test_pyshacl_parity_small_differences.py::test_unique_lang_compares_language_tags_without_regard_to_case['x'@en, 'y'@EN]`
- `integration/test_pyshacl_parity_small_differences.py::test_unique_lang_compares_language_tags_without_regard_to_case['x'@en, 'y'@en]`
- `integration/test_pyshacl_parity_small_differences.py::test_unique_lang_compares_language_tags_without_regard_to_case['x'@en-GB, 'y'@en-gb]`
- `integration/test_pyshacl_parity_small_differences.py::test_unique_lang_compares_language_tags_without_regard_to_case['x'@EN-gb, 'y'@en-GB, 'z'@en]`
- `integration/test_pyshacl_parity_small_differences.py::test_unique_lang_compares_language_tags_without_regard_to_case['x'@fr, 'y'@FR, 'z'@FR]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Violation-none]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Violation-infos]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Violation-warnings]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Violation-both]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Warning-none]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Warning-infos]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Warning-warnings]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Warning-both]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Info-none]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Info-infos]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Info-warnings]`
- `integration/test_pyshacl_parity_small_differences.py::test_allow_flags_decide_conformance_as_pyshacl_does[Info-both]`
- `integration/test_pyshacl_parity_small_differences.py::test_result_messages_are_pyshacls[closed]`
- `integration/test_pyshacl_parity_small_differences.py::test_result_messages_are_pyshacls[closed-with-ignored]`
- `integration/test_pyshacl_parity_small_differences.py::test_result_messages_are_pyshacls[languageIn-several]`
- `integration/test_pyshacl_parity_small_differences.py::test_result_messages_are_pyshacls[languageIn-one]`
- `integration/test_pyshacl_parity_small_differences.py::test_result_messages_are_pyshacls[uniqueLang]`

## Remaining adapter gaps (fall back to pySHACL, recorded in `engine_fallback_reason`)

`validate_fn`, a custom `adapter`, `decode_report=False`, `rdfs_subclass_reasoning_includes_shapes_graph`, an explicit
`iterate_rules`, pySHACL-only switches (`js`, `sparql_mode`, `do_owl_imports`, `focus_nodes`, `use_shapes`, `*_format`,
`serialize_*`), `include_source_rule_provenance`, `apply_rules` on a graph that is not a `StarLayerGraph` (the old call raises
`TypeError`; the fallback reproduces it). Unknown option names reach the old `TypeError` unchanged.
Not translated: the engine has no `sh:sourceRule` reifiers, no `sh:detail` (open ENGINE-GAP above), no pySHACL-style generic
result messages (`Less than 1 values on ex:a->ex:p`), and `validate_each` does not share one `Plan` across graphs in native mode
(each item calls `validate` once).
