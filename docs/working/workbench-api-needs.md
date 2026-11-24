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
| 7 | `shacl.meta_shapes.sparql_query_problems`, `parameter_value_shapes` | defects of the SPARQL a shapes graph holds; per-parameter value shapes for the shapes-about-shapes check | meta_shapes mostly replaced by engine `meta.py` | folded into the meta check (2026-11-24): `starlayer.shacl.meta_validate(shapes)` reports both, each defect a `sh:ValidationResult` in `MetaShaclError.report_graph`; the two functions are internal to `meta_shapes` |
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

API differences the workbench integration must expect: `ValidationReport` / `RulesResult` have no `engine` fields; `evaluate_component`,
`TripleTermAdapter` and the keywords `validate_fn`, `adapter`, `decode_report`, `iterate_rules`, `engine=` are gone; `inference=` takes
entailment regime IRIs; a graph with a term that is not an RDF term (a relative IRI) raises `TermError` unless `invalid_terms="lenient"`.

## Added 2026-11-11 (SHACL UI, from the spec-delta plan; `docs/working/spec-delta-2026-11-11.md`)

Public, in `starlayer.shacl`: `select_widget(s)(implemented=, on_report=)` and `WidgetReport` (the draft: an implementation must not
offer a widget it does not implement and must report that one matched or none did), and `property_shapes_for_role(shape_node=, role=,
shapes_graph=)` (the property shapes of a node shape that play a `shui:propertyRole`, in the draft's order). The label and language
resolution of the draft stay with the application. The SHACL UI namespace is now `http://www.w3.org/ns/shacl-ui/` (slash).

## Added 2026-11-13 (what the workbench's `_starlayer.py` did that the library should do)

Read from `graph-workbench/src/graph_workbench/_starlayer.py` (workbench `c95f541`). Public now, so the workbench can drop its own versions:

| The workbench had | Public in StarLayer |
|---|---|
| `literal(value, datatype, lang, direction)`, `py_value(term)` | `starlayer.graph.literal`, `starlayer.graph.to_python` (an ill-formed lexical form is a `ValueError`, where `py_value` gave `None`) |
| `parse_literal(text)`, `parse_term(text)` (through a throwaway graph) | `starlayer.graph.parse_term(text, prefixes=None)`: one IRI, blank node, literal or triple term of Turtle 1.2 text; a prefixed name needs `prefixes` |
| its own `Namespace` (with `in` and `.term()`), and `SKOS`, `SCHEMA`, `SHUI` | `starlayer.graph.Namespace` now has both; `SKOS`, `SCHEMA`, `DCTERMS`, `DC`, `FOAF`, `PROV`, `DCAT` and `SHUI` are in `starlayer.graph.namespaces` (one definition each) |
| `set_triple` | `graph.set(triple)` |
| `_cells`, `_chain`, `list_with`, `list_without` (list editing in `edits.py`) | `graph.add_list(items, head=None)`, `graph.remove_list(head)`, `graph.set_list(subject, predicate, items)`; reading stays `graph.items(head)` |
| the closure loops in `graph_classes`, `shape_closure` | `graph.transitive_objects(subject, predicate)` / `transitive_subjects(predicate, object)` |
| additions and deletions as sets (`Change`, `turtlediff`) | `starlayer.graph.GraphDelta` (`apply`, `inverse`, `then`) and `diff(old, new)`; the undo stack and the Turtle drawing stay in the app |
| `widget_trace` (imports six private functions of `shacl.ui.widget_selection`) | `starlayer.shacl.explain_widgets(...) -> WidgetTrace` (candidates, their `WidgetCondition`s and outcome); the app's `known` (rendered widgets) stays in the app |
| `shape_closure` | `starlayer.shacl.referenced_shapes` (it already follows `sh:rule`, `sh:condition`, `sh:target` and the node expressions that take a shape; the starting shapes are not part of its result) |
| `rule_closure` | `starlayer.shacl.rule_dependencies`: what `referenced_shapes` leaves out for rules (the shapes in a `sh:condition` list, `sh:prefixes` / `sh:declare` / `owl:imports`, rule templates and the classes they specialise) |

Already in the library, and the workbench keeps its own copy: `copy_graph` is `graph.copy()`, `list_items` is `graph.items`, `describe_nodes` is close to
`graph.cbd` (which takes one node), `expand_name` is `graph.expand_curie` (the app adds the standard prefixes), `n3` / `qname` are `graph.qname_term` / `compute_qname`. The
`prefix_options` workaround for `used_prefixes()` binding an `nsN` prefix does not apply to the current library (checked 2026-11-13: it does not change the graph).

The data index (`DataIndex`) is split: the part that is a fact about the data is `starlayer.graph.profile(graph)` / `graph.profile()` (`GraphProfile`: `classes`,
`properties`, `instances(cls)`, `types_of(node)`, `class_properties(cls)`, `properties_of(nodes)` giving `PropertyUse(property, nodes, max_values, datatypes, kinds)`). The rest stays
in the app: what the shapes' targets reach (`focus_nodes`, scope, uncovered properties) is built on the library's `target_nodes` and the pickers' lists are display. The profile is a snapshot
with no cache: the app keeps its own, keyed on its own data and shapes versions, which is what it did already.

### Where a helper lives (decided 2026-11-13)

A helper is StarLayer's when it states a fact about RDF data or SHACL, or does what a standard says, **and a second user needs it** (the library, another app, the tests): a
value or term conversion, an RDF list, a closure over a vocabulary's predicates, a profile of a graph, why a widget was chosen. It is the application's when it exists to be shown or to
manage the app's own state: option lists and their labels and order, forms, undo history, drawing a diff, caches and their invalidation. A cache belongs to whoever knows when the
data changed: the library gives snapshots (`profile`, `GraphDelta`) and the app decides when to take another. Inside the library there is one implementation of a concept.

`derive_shape()` was checked against the profile and keeps its own analysis: it needs the values (ranges, enumerations, languages), not the summary. It shares the pieces that are the same
(`terms.term_kind`, and `graph.add_list` for writing lists; the copies in `shacl/derive.py` (formerly `graph/shapes.py`) and `starontology/manchester` are gone). What remains duplicated inside the library are the
readers of an RDF list in the SHACL engine and the SPARQL tree code (`engine/graphs.list_items`, `shapes_graphs._items`, `text._items`, `subgraph._items`, `core_value.rdf_list`,
`core_string_pair._list_items`, `sqe/expr_text._list_items`): each fails differently on a malformed list (a `ShapeError` naming the shape, `None`, a short list), so merging them is
a decision about one error contract, not a tidy-up. Open.

## Added 2026-11-24 (what a field can offer)

| Workbench reaches into | Used for | Public component |
|---|---|---|
| `forms.py:_options` (nodes whose `rdf:type` is exactly the shape's `sh:class`) | the candidates a property field offers | `starlayer.shacl.candidate_values(shapes, property_shape, data, focus=, only_valid=, subclass_of_in_shapes_graph=)` / `StarShaclProcessor.candidate_values(...)` -> `Candidates(kind, values, closed, entry)`: subclass instances, `sh:in`, `sh:hasValue`, `sh:rootClass`, `sh:or`; `only_valid=True` with a `focus` drops what would break the field's other constraints. The workbench is not edited yet; labels stay in the app. |
| `validation.py`: `Issue`, `ValidationIndex.for_node` / `for_field` / `node_level` / `error_count` / `total_errors`, and the de-duplication at the end of `refresh()`, all read from `report.subjects(rdf:type, sh:ValidationResult)` | indexing the report by node and field | `ValidationReport.results` (tuple of `ReportResult`: focus, path, value, component, source_shape, severity, severity_name, messages, details) with `for_node(node)`, `for_field(node, path)`, `node_level(node)`, `counts()`, `deduplicated()`; `report_results(report_graph)` for a `MetaShaclError.report_graph`; `diff_reports(old, new)` -> `ReportDiff(added, fixed, unchanged)`. Top-level results only (nested `sh:detail` results are in `.details`, which is what made the workbench count the same mistake at each level). The workbench is not edited yet; wording and messages stay in the app. |
| `editors.ttl`: `wbm:isList`, `wbm:singleOrList` (how a field's value is held), and `wbm:check` (`edits.CHECKS`: LanguageTag, Regex, SparqlQuery, Iri, TimeZone) | whether a field takes one term or an RDF list, and whether a value would be accepted | `starlayer.shacl.value_form(shapes, property_shape)` / `StarShaclProcessor.value_form(...)` -> `"single"`, `"list"` or `"single-or-list"`, from the shape's own constraints (`sh:node` / `sh:and` to a list shape, the SHACL 1.2 list constraints, `sh:class rdf:List`, `sh:or` / `sh:xone` with both kinds of alternative); `check_value(shapes, property_shape, focus, value, data)` / `StarShaclProcessor.check_value(...)` -> `ValueCheck(conforms, results)`, the value replacing the field's values on a scratch copy, validated against that property shape only. `isList` / `singleOrList` can be derived where the shapes say so (they do for `sh:languageIn`, `sh:ignoredProperties`, `sh:in` on the shapes that check it, `shui:languagePreference`, `sh:uniqueValuesFor`, `sh:nodeKind`; not for `shui:suggestedValues` and `shui:labelPreference`, whose shapes only say `sh:maxCount 1`). `wbm:check` is not replaced: the regex and SPARQL text checks are `meta_validate` shapes, and language-tag syntax, IRI-as-text and time zone are in no shape. The workbench is not edited yet. |
| `validation.py`: `ValidationIndex.refresh()` re-runs the whole-graph meta check after every edit | a quick check of an edit before it is committed | `starlayer.shacl.meta_validate(shapes, add=[...], remove=[...])` before the edit is applied to the app's graph (the graph is not changed; the check runs on a copy with the edit, and covers the nodes the edit touches, their inline property shapes and the shapes that refer to them), and `meta_scope(shapes, add=, remove=)` -> `MetaScope(full, nodes, reasons)` to say what was covered and why. A risky edit (prefix declarations, components and parameters, rule templates, `rdf:type` / `rdfs:subClassOf`) is checked in full by itself. About 0.1 s on 2000 node shapes (the whole-graph check: 4.5 s); a full check before saving or publishing is still the safe default. The workbench is not edited yet. |
