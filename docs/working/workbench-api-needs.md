# What the graph workbench reaches into, and the public API each reach asks for

Design principle (project owner, 2026-11-02): an app does not import a library's internal modules. A need that can only be met that
way is a missing public API component, to be built, not a deep import to keep or a shim to leave at the old path.

Source: `graph-workbench/src/graph_workbench/_starlayer.py` (the app's single import boundary), read on branch `shacl-engine-trial`
(workbench `983f3c7`). The workbench was run on this branch's native engine on 2026-11-02: the light suite passed after one engine
fix (result messages, commit `Report graph results carry the old generic message wording`); the full run is recorded at the end.

Public today: `starlayer.shacl.__all__` (`StarShaclSchema`, `validate`, `validate_each`, `apply_rules`, `evaluate`, `extract_subgraph`,
`target_nodes`, the result types, adapters), `starlayer.graph` (terms, graphs), `starlayer.starontology`, `starlayer.sparql`.

| # | Workbench reaches into | Used for | Engine / cut-over status of that module | Proposed public component |
|---|---|---|---|---|
| 1 | `pyshacl.shapes_graph.ShapesGraph` (in `eval_node_expression`) | builds the object the old evaluator wants | pyshacl is removed at stage d | none needed once 3 exists; the app must not import pyshacl at all |
| 2 | `shacl.node_expressions.eval_expr` | evaluate a node expression against data, with scope variables and a function-call scope (the expression editor's preview) | module deleted at stage c (engine: `expressions.evaluate_expression`) | `starlayer.shacl.evaluate_expression(shapes, data, expr, focus, *, scope=None) -> list` |
| 3 | `shacl.sparql_node_expressions._ALL_PREDICATES` (private name) | list the `sparql:` functions a node expression can call (function picker) | deleted at stage c; the engine has the operator table (`component_table`, `expressions`) | `starlayer.shacl.node_expression_functions() -> list[IRI]` (also `node_expression_operators()` for the `shnex:` ones) |
| 4 | `shacl.shape_types.infer_types` | the types a shapes graph's structure entails (is it a node or property shape) | stays (no pyshacl); runs the shipped rules on the engine | export from `starlayer.shacl` (documented, already the module's purpose) |
| 5 | `shacl.paths.path_values`, `is_inverse` | follow a SHACL path from a node; test for an inverse path | stays (34 lines); the engine has `paths.eval_path` | `starlayer.shacl.path_values(graph, node, path, shapes=None)`, `is_inverse(graph, path)` |
| 6 | `shacl.shapes_graphs.shapes_graph_members` | which graphs a shapes graph imports (Profiling 2.4 to 2.6) | stays; duplicated by engine `modules.py` | `starlayer.shacl.shapes_graph_members(graph, shapes_graph)` (one implementation) |
| 7 | `shacl.meta_shapes.sparql_query_problems`, `parameter_value_shapes` | defects of the SPARQL a shapes graph holds; per-parameter value shapes for the shapes-about-shapes check | meta_shapes mostly replaced by engine `meta.py` | `starlayer.shacl.sparql_query_problems(shapes)` and `parameter_value_shapes(shapes)`, or folded into `validate(..., meta_shacl=True)` reports |
| 8 | `shacl.ui_widget_selection.select_widgets` | pick widgets for a shape's properties | stays (independent of pyshacl); a method `StarShaclSchema.select_widgets` exists | use the method; export the function from `starlayer.shacl` or a `starlayer.shacl.ui` package |
| 9 | `graph.compare.isomorphic` | graph isomorphism | stays | export from `starlayer.graph` (it is not exported there today) |
| 10 | `sparql.parse12.parse_query_12` | syntax check of query text | replaced by the owned parser (`parse_sparql`) | `starlayer.sparql.check_query(text) -> str | None` (the app wraps this today) |
| 11 | `starlayer.starontology` (many calls) | registry of shipped graphs | public package | none; confirm the used functions are documented |

## Notes
- Items 1 to 3 are the ones the cut-over breaks. The others only move or get a public name.
- Item 7 may disappear into the engine's meta-SHACL preflight; decide when the reports of `meta_shacl=True` carry the same information.
- None of the proposed names is final; they follow the existing `starlayer.shacl` style (plain functions on graphs).

## Trial results (2026-11-02): the workbench on the pure engine

Workbench branch `shacl-engine-trial` (its changes are discarded; the integration is redone later), pyshacl uninstalled, the library
imports only through the public names above. Light suite: 345 passed, 333 skipped (shapes-tab and browser tests), 4 failed, of which:

| Failure | Cause | Where it is fixed |
|---|---|---|
| `test_demos::test_a_sparql_text_expression_is_evaluated_and_a_list_holds_constants_only` | engine gap: a node expression as a list member must be an error (Node Expressions 4.1.3) | engine (fixed, regression test) |
| `test_nodeexprmodel::test_the_kinds_are_the_defining_predicates_starlayer_evaluates` | the workbench *test* imports the deleted `starlayer.shacl.node_expressions` | workbench: use `node_expression_operators()` / `node_expression_functions()` |
| `test_paths::test_a_path_written_in_one_graph_can_be_followed_through_another` | `path_values` raises `ShapeError` for a malformed path (it was `NotImplementedError`) | workbench: expect `ShapeError` |
| `test_import_report::test_the_committed_report_is_current` | the committed import report lists the old import names | workbench: regenerate with `tools/import_report.py --write` |

Earlier in the trial the engine fixed, from workbench runs: result messages in the report graph (prefixed names, "Less than 1 values
on ..."), a `sh:NodeShape` with `sh:path` is ill-formed, and `include_source_rule_provenance` (the earlier native run had passed only
because that option fell back to the old code).

API differences the workbench integration must expect: `ValidationResult` / `RulesResult` have no `engine` fields; `evaluate_component`,
`TripleTermAdapter` and the keywords `validate_fn`, `adapter`, `decode_report`, `iterate_rules`, `engine=` are gone; `inference=` takes
entailment regime IRIs; a graph with a term that is not an RDF term (a relative IRI) raises `TermError` unless `invalid_terms="lenient"`.

## Added 2026-11-11 (SHACL UI, from the spec-delta plan; `docs/working/spec-delta-2026-11-11.md`)

Public, in `starlayer.shacl`: `select_widget(s)(implemented=, on_report=)` and `WidgetReport` (the draft: an implementation must not
offer a widget it does not implement and must report that one matched or none did), and `property_shapes_for_role(shape_node=, role=,
shapes_graph=)` (the property shapes of a node shape that play a `shui:propertyRole`, in the draft's order). The label and language
resolution of the draft stay with the application. The SHACL UI namespace is now `http://www.w3.org/ns/shacl-ui/` (slash).
