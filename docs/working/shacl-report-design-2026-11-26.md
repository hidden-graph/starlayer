# SHACL report: one source for the graph and the text (design note, 2026-11-26)

Status (2026-11-27): partly built, see "What was built" at the end; the proposal below is the original and is superseded where that section says so. Branch `perf/shacl-engine-efficiency`. Companion to `shacl-engine-efficiency-plan-2026-11-26.md`.

## Direction given

1. The report graph is the model. The text is derived from the same captured facts, and the graph should not carry more than the text says, unless the spec requires it. Where the text needs something the graph lacks, extend the graph (if the spec allows it).
2. `validate()` takes a parameter naming what to build on the first pass: graph, text, both or neither. A single call that wants graph and text does one pass, not two.
3. A `Result` captures what the report needs while it is made, so no later step goes back to the live shapes or data graphs.

## What exists today (checked in the code)

- `Result` (`executor.py`) holds: focus, path, value, component, shape, severity, messages, source_constraint, annotations, details. It does not hold the constraint's parameter values.
- A component has the parameters in hand when it makes a violation (`min_count` reads `n` from `params`, parsed once in the plan) and writes its own message. The report then discards that wording and rebuilds it: `result_messages` calls `generic_message`, which reads the same parameter back out of the shapes graph (`_params(shapes, r, ...)`, `_list_items`, `Words`).
- The messages are computed twice when both outputs are wanted: once in `build_report` for `sh:resultMessage`, once in `report_text` for each result block.
- The report graph copies the blank-node closure of the focus node, value, path, source constraint and annotation values (`_copy_closure`), not of the source shape. The text prints `stringify_node` of focus, value, source shape, path and source constraint, so for a blank source shape it prints structure the graph does not hold.
- `report_text` is not in the standard. It is the pySHACL listing layout, reimplemented (`text.py` docstring). `shacl/CLAUDE.md` records that W3C conformance does not compare message text.

- The public `ValidationReport` (`shacl/results.py`, what `validate()` returns to callers) already builds `report_text` on first read, from a function it is given, and its docstring says a lazily built text "describes the graphs as they are when it is first read". So lazy text with reads of the live graphs is the current public contract; this note proposes to replace the live reads by captured facts, which changes that sentence. The engine's own `Outcome` (`engine/api.py`) is the object under it; both would follow the same `build` choice.

## Proposed model

**One record per result, made once.** When a result is produced, the engine also captures a small immutable `ResultFacts` (name provisional) holding everything the message and the text blocks need:
- the final message literals (computed once, used by both outputs);
- the parameter values the message named, as terms, with list members resolved (`sh:in`, `sh:languageIn`, `sh:and/or/xone`, `sh:rootClass`);
- the rendered words for any shape or path term the message names (the `[ sh:class ex:Duck ]` form), and the closures the text prints;
- the prefixes the words were abbreviated with.

Per-shape facts are computed once per (shape, component) and shared by reference between results; only the focus, path and value words are per result. That is where the saving is.

**Graph and text are two renderings of the facts.** `build_report` and `report_text` both read the facts and never read the live graphs. The graph keeps the standard's properties, with `sh:resultMessage` carrying the final message. The closure triples the text needs are in the graph too. Closures the text does not need are not copied.

**What each output builds, chosen by a parameter.** `validate(..., build=...)` takes `"graph"`, `"text"`, `"both"` or `"none"` (results only). A requested output is built on the first pass, sharing the message work. An output not requested is built on first access to `outcome.report_graph` or `outcome.report_text`, from the captured facts, so a late request still needs no live graph. The default stays as today's behaviour (graph built, text on first use) until it is changed on purpose.

## What each component's message needs

From `generic_message`. "Captured" is what the facts record.

| Component | Needs beyond the result | Captured |
|---|---|---|
| `sh:minCount`, `maxCount`, `minLength`, `maxLength`, ranges, `pattern` (+ `sh:flags`) | the parameter literal | the literal(s) |
| `sh:class`, `datatype`, `nodeKind` | one or more parameter terms | the terms |
| `sh:equals`, `disjoint`, `lessThan`, `lessThanOrEquals`, `subsetOf` | a path term, worded as a path | the path words |
| `sh:not`, `sh:node` | a shape term, worded | the shape words |
| `sh:and`, `or`, `xone` | lists of shape terms, worded | the member words |
| `sh:in`, `languageIn`, `rootClass` | list members | the resolved members |
| `sh:expression`, expression-based node shape | the source constraint, worded (shortened if long) | the words |
| `sh:sparql` | whether the shape or reifier has its own `sh:message` | the own messages |
| custom SPARQL-based component | the component's declared parameters and the shape's values for them | the (parameter, value) pairs |
| `sh:singleLine` | nothing | nothing |
| any, when the shape has its own `sh:message` | the shape's messages (`own`) | the messages, with `messages_stated` |

The facts do not hold the shapes graph. Every row is either a term from the compiled plan or a value computed when the result is made.

## Open points

1. **Spec check.** I have not yet read the vendored spec for what a validation report may contain beyond the listed properties. Extra triples such as closures are what the engine writes today and the conformance suite passes with them. Whether adding the source-shape closure is allowed needs checking against the SHACL 1.2 Core text and the W3C tests before it is done.
2. **Source shape in the text.** A blank-node source shape prints its structure in the text today and not in the graph. Under the direction above, the graph gains that closure (once per shape, deduplicated by `seen`), unless the spec says no. Alternatively the text stops printing it.
3. **Prefixes.** Words are abbreviated with a graph's prefixes. Captured words fix the prefixes at result time, which also fixes the text if the graph's prefixes change later. That is the intent, but it is a behaviour change for anyone relying on late prefix binding.
4. **Messages computed per result when the shape is shared.** Per-result parts are the value, focus and path words; the rest is shared. Needs a measurement after the first implementation, not a prediction.
5. **Default of `build`.** Keeping the current default is safest. Changing it to lazy for both is the larger saving and a visible change.
6. **API.** `Outcome.report_graph` becomes a property (as `report_text` already is); anything that reads the dataclass field directly, copies or pickles an `Outcome` needs checking. `annotate_provenance`, `diagnostics.report_triples` and the profiling `conformsTo` step move to the deferred build.

## Stages (each its own commit, targeted tests only)

1. Capture: add the facts to each result, shared per (shape, component), with no change to any output. Test: facts equal what the live-graph path reads, on the existing SHACL tests plus the benchmark.
2. Render the text from the facts. Test: text identical to today's, on the existing report-text tests.
3. Render the graph's messages and closures from the facts. Test: report graphs isomorphic to today's, plus any intended additions listed.
4. The `build` parameter and the deferred build. Test: each mode gives the same graph and text as today.
5. Measure: violation cost per result against the 49 µs baseline (100% violate 54.9 µs per dog, 10% 10.6 µs).

## Measured background (baseline, 100k dogs, one `sh:minCount`)

All conform 5.7 µs per dog; 10% violate 10.6 µs; every dog violates 54.9 µs. About 49 µs per violation. The write of the report quads is limited by pyoxigraph's `Quad` constructor (2 to 4 µs each; N-Triples loading is faster but relabels blank nodes, so it is rejected). Skipping the graph (`build="none"` or `"text"`) removes the write entirely.


## What was built (2026-11-27) and what was not

Direction given in between: results are still read through the report graph; a caller that knows it needs the graph asks for it, and otherwise the graph is written on first read. So the design changed from "a facts record per result that both outputs are drawn from" to the following.

Built:
- **`text.MessageMemo`**: the messages of a run, and the fixed lines of a text block, worded once for each distinct result. No facts record was needed: the key is the result's own fields (shape, component, path node, value, source constraint, own messages, and the focus node for a SPARQL constraint).
- **Collect and write.** `report.collect_report` takes, in the call, the triples, the blank-node closures, the messages and the prefixes of the two graphs; `report.write_report` makes the graph from that and reads neither graph. So a graph written later is the graph of the call (tested by emptying both graphs first).
- **A lazy graph.** `Outcome.report_graph`, `ValidationReport.report_graph` and `.diagnostics`, and `MetaResult.report_graph` and `.diagnostics` are taken on first read; `Outcome.after_report_graph(hook)` is for what must be done to the graph when it is written (the conformance floor).
- **`build=None | "graph" | "text"`** on `validate()` and the processor's `validate()`. The checks that always read the graph pass `build="graph"` (`validate_bounded`, the reading calls in `derive.py`).

Not built, and why:
- **The text from the report graph alone.** Not wanted: results keep their path through the graph, and the text keeps reading the shapes and data graphs for its blocks (the public contract already says a lazily built text describes the graphs as they are when first read). The text's provenance lines come from the graph, so reading `report_text` writes it.
- **Captured parameter values on `Result`**, and extra closures in the graph (open points 1 and 2 above): not needed for the speed-up. The spec check on what a report graph may contain is still open and would matter only if the graph is to gain triples.
- **Graph content is unchanged.** Nothing was added to or taken out of a report graph.

Measured: see `shacl-engine-efficiency-plan-2026-11-26.md`, stages R1 and R2.
