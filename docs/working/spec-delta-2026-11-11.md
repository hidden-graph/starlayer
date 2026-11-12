# Spec and test-suite delta, and the plan for `shacl-engine` (2026-11-11)

Extends `spec-drift-2026-11-09.md`. That note covers the spec text; this one adds what changed in the upstream **test suites**,
what that does to our code (measured by running the new suites against `shacl-engine`, in a scratch copy, nothing committed),
and what changed in the drafts after 2026-11-09. Prototype artifacts are in `spec-delta-2026-11-11/`.

## 1. What changed upstream

### Test suites

| Suite | Pinned at | Now | Size of the change |
|---|---|---|---|
| `w3c/rdf-tests` (RDF 1.2, Turtle, SPARQL 1.1 and 1.2) | `d5d930b` (2026-10-12) | `4158bca` (2026-11-10), 14 commits | small: negative syntax tests for bad IRIs, language and direction tags and `BASE` (10 new RDF 1.2 tests), two IRIs removed from a Turtle test, a CSV variant, manifest tidying |
| `w3c/data-shapes` SHACL suite | `59b38cd` (2026-08-15) | `47c6e07` (2026-11-11), 390 commits | large: 325 to 591 entries, plus about 240 new SPARQL-RL (SRL) tests; directories reorganised (`sparql/rules` to `inference-rules`, `rules` to `sparql-rl`); new result type `mf:result sht:Failure`; tests now carry `mf:requires sht:Core` and similar |

SHACL suite by area, before and after: core 138 to 162 validate entries; node-expr 145 to 284; inference rules (was
`sparql/rules`) 16 to 47; SPARQL 26 to 98; and SPARQL-RL 0 to about 240 (syntax 173, well-formedness 8, stratification 14, evaluation 47).

### Spec drafts (new since the 2026-11-09 review)

- SHACL Core WD 2026-11-10 and Inference Rules WD 2026-11-10: only the **role-class wording** ("graphs *acting in the role of*"
  a data, shapes or rules graph, not "typically") and two editorial clarifications in Inference Rules. No code effect; the
  `sh:DataGraph` / `ShapesGraph` / `RulesGraph` comments in the vocabulary change.
- SHACL UI WD 2026-11-11: **an implementation MUST NOT select or offer a widget it does not implement, and MUST report to the
  application when an unimplemented widget matches or none matches** (#1206); ordering fallback and tie-breaking relaxed from MUST
  to SHOULD (the "MAY use an alternative tie-breaking" proviso is simpler). Earlier in the week: `shui:suggestedValues` text and a
  reworked search query (#1338, #1241).
- RDF Concepts CRD 2026-11-11 (typo in the RDF-term mapping), Turtle WD 2026-11-11 (a bracket glyph), TriG and N-Quads
  (grammar and wording fixes): editorial.
- SRL WD 2026-11-09 and the rest of the 2026-11-09 review stand: `GROUP` aggregation in rule bodies; SHACL Core
  `sh:dataGraph` and the optional `sh:ShapeAssignment` terms; relaxed reifier-message rule.

## 2. What the new suites do to `shacl-engine` (measured)

**RDF and SPARQL suites: nothing.** With the pin bumped and data regenerated, `tests/graph` and `tests/sparql` (including the
opt-in sqe coverage) pass, 8590 passed. The only failing assertion is the "suite has N tests" check (341 now 351). The 10 new
syntax tests all pass on Oxigraph.

**SHACL suite: 40 failures out of about 950 before any harness change** (38 distinct tests; `in-004` fails in three
harness modules). They break down as follows.

| Failures | What they are | Real engine gap? |
|---|---|---|
| 23 node-expr, 5 inference-rules | the suite now says `mf:result sht:Failure` for an expression or rule that must fail; our harness does not know the term. The engine already raises `EvaluationFailure` / `RuleError` | **no**: pass once the harness understands `sht:Failure` |
| 3 node-expr | **single-argument shorthand** for list-parameter functions: `sparql:abs -42` and `ex:twice 21` mean a one-element list (Node Expressions, "ListParameterFunctions"). We raise "the argument must be an RDF list" | **yes** |
| 1 inference | `sh:condition` that is both a node shape and a class must also require conformance to the class's superclass shapes (`condition-shape-class-superclass`). We infer an extra triple | **yes** |
| 1 inference | an unknown `sh:ruleProcessor` named on a **rule set** must fail (`ruleProcessor-unknown-at-ruleset`). We only fail on a rule (`rules.py` line 308 covers part of it) | **yes** |
| 1 inference | a rule template whose parameters are **all optional** is valid (`SPARQLRuleTemplate-optional-param`). We raise "needs at least one non-optional parameter" (`sparql_components.py` line 75), which is right for constraint components, not for rule templates | **yes** |
| 1 core, 1 node-expr | `in-004` and `intersection-termEquality` depend on a literal's lexical form (`"01"^^xsd:integer`, a `byte`), which Oxigraph normalises on storage | no: the known #190 class; add to `STORE_NORMALIZATION` |
| 1 sparql | `unsupported-sparql-002`, the VALUES deviation already documented in `check_query` | no: its known-failure key is a path that moved |
| 1 validate | `quoted-focus-optional` (triple-term focus) in the older `test_w3c_validate` path, which goes through rdflib terms | harness: the engine path passes it |

So after the harness work, **4 real engine gaps** are left in the SHACL suite, all small.

**SPARQL-RL (SRL) suite, run with a throwaway runner against `parse_ruleset` / `infer`:** 46 of 47 evaluation tests, all 14
stratification tests, all 8 well-formedness tests and 153 of 173 syntax tests pass. The rest:

- **16 positive syntax tests fail: all are `GROUP` in rule bodies.** This is the aggregation gap from the 2026-11-09 review, and it
  is now measurable.
- 4 negative syntax tests (`syntax-data-bad-04/05/06/08`: variables in a `DATA` block) are accepted by the grammar-level
  `parse_srl` but rejected by `parse_ruleset` as a well-formedness violation. The public API behaves correctly. The suite files
  this under syntax, so the harness should use `parse_ruleset` for negatives, or we tighten `parse_srl`.
- 1 evaluation test (`Eval-assign-01`) names `eval-assign-01.srl` and its results, and neither file exists upstream. Report it
  upstream rather than work around it.

**Vocabularies.** The vendored `w3c-shacl-shacl.ttl` is 5 lines behind (`shsh:DataGraphShape`); `w3c-shacl.ttl` is 14 lines behind
(`sh:dataGraph` with domain `sh:ShapesGraph` and range `sh:DataGraph`, and the role-class wording). The upstream `shacl-ui.ttl`
defines 32 terms; **7 are absent from our `starontology/*.ttl`**: `PropertyRole`, `ClassificationRole`, `DepictionRole`,
`DescriptionRole`, `IconRole`, `WidgetMatcher` and `suggestedValues`.

## 3. Plan, in order

**Status, 2026-11-11: phase 0 is done** (commits `a51133e3`, `f306f2e6`, `cbaa394b`). Both suites are pinned at the new commits; `rdf12`
has a download script; the sync script's destination path is fixed; `sht:Failure` is understood by the node-expression and
rule harnesses; the SPARQL-RL suite runs as `tests/shacl/w3c_shacl12/test_w3c_sparql_rl.py` (225 pass, 17 strict xfails); the
six engine gaps of phase 1 are strict xfails in `known_failures.py::ENGINE_GAPS`. `tests/shacl`, `tests/shacl_engine`,
`tests/sparql` and `tests/starontology` pass (8482 passed, 44 xfailed). Two corrections to section 2 found on the way:
the `unsupported-sparql-002` fixture was **corrected upstream** (it now uses `VALUES $this`, the pre-bound variable the spec
forbids), so our documented deviation for it is gone; and that fixture still uses a file-level `@prefix ex:` in its `sh:select`
with no `sh:prefixes`, so our strict prefix rule rejects it for that reason first. It passes, but not through the VALUES check:
worth reporting upstream. `Eval-assign-01` (files missing upstream) is also worth reporting.


Everything below is on `shacl-engine`. Items marked (shared) are data or scripts that would be the same on any branch.

**Phase 0. Pins and harness: gives a green, honest baseline (small to medium).**
1. Bump the `rdf-tests` pin to `4158bca` in the three download scripts and refresh the `rdf12` data directories (they have no
   script; the README says to copy them from the tarball: automate it while at it). Update the expected count in
   `test_w3c_rdf12_oxigraph.py`. (shared)
2. Bump the `data-shapes` pin to `47c6e07` in `scripts/sync_w3c_shacl12_suite.py` and **fix its destination path**
   (`tests/vendor/` should be `tests/shacl/vendor/`). Re-sync and update `VENDORED_FROM.md`. (shared)
3. Teach the harness `mf:result sht:Failure` in `test_w3c_engine_node_expr.py` and `test_w3c_infer.py`; re-key
   `known_failures.py` to the new paths; add `in-004` and `intersection-termEquality` to `STORE_NORMALIZATION`; settle
   `test_w3c_validate.py` (retire it or move it to engine terms, since the engine tests cover the same entries). A prototype of
   the first two is `spec-delta-2026-11-11/harness-prototype.patch`.
4. Add a SPARQL-RL runner, `tests/sparql/srl_conformance/test_w3c_sparql_rl.py`, from `srl_w3c_runner.py`. Known failures are the 16
   `GROUP` tests (strict xfail, reason "GROUP aggregation, phase 4") and `Eval-assign-01` (upstream file missing).
5. Mark the four real gaps of phase 1 as strict xfails with a reason, so the suite is green and each fix flips an XPASS.

Acceptance: `tests/shacl`, `tests/graph`, `tests/sparql` green; the opt-in suites unchanged; the failure list equals the table in
section 2.

**Phase 1. The four engine gaps (small each, independent). Done 2026-11-11** (`ENGINE_GAPS` is empty). Notes: the shorthand replaces GitHub issue #8's error for a bare node, and three tests that asserted that error now assert the list form's value; a rule set naming `sh:ruleProcessor` is a failure when a rule of it runs, which reverses our earlier test "a rule set that is not selected is not asked" (the W3C fixture is the same situation); `sh:ShapeClass` counts as a SHACL instance of `sh:NodeShape` and `rdfs:Class` for `sh:condition`. Guide 04a still says every `sparql:` call needs a list (a notebook edit, waiting for a go-ahead).
1. List-parameter single-argument shorthand (`shacl_engine/expressions.py`, around line 260). Read the "ListParameterFunctions"
   text first; check it also covers `shnex:` functions with a list parameter, not only `sparql:` ones.
2. `sh:condition` as node shape and class: also require the superclass shapes (`shacl_engine/rules.py`, condition handling).
3. Unknown `sh:ruleProcessor` on a rule set must fail (`rules.py` line 308).
4. Rule templates may have only optional parameters (`components/sparql_components.py` line 75: keep the rule for constraint
   components).

**Phase 2. Vocabulary and data (small to medium). Done 2026-11-11.** Re-vendored `w3c-shacl.ttl` (`9d7caf1`) and `w3c-shacl-shacl.ttl`
(`a6ed26f`): `sh:dataGraph`, `shsh:DataGraphShape` and the role-class wording are in the generated data. The upstream `shacl-ui.ttl`
(`40231df`) is now vendored as `w3c-shacl-ui.ttl` and is a third base of the `shacl_vocabulary` graph, so all 32 `shui:` terms are
defined (our overlay had defined six subclass relations and nothing else); `shui:suggestedValues` has a field in the property
shape form. **Found on the way: the SHACL UI namespace is `http://www.w3.org/ns/shacl-ui/` (slash), not `…#`.** Our 2026-10-21 note
that the draft used the hash form rested on an older source; the published WD 2026-11-11 and the editor's draft since at least
2026-10-21 use the slash form. Decided with the owner: a clean break. Code, data, tests and guide 04d moved; the workbench (24 files)
is logged in `graph-workbench/docs/deferred.md`. Not done: `sh:ShapeAssignment`, `sh:assignment` and `sh:nodeAssignmentCount` are
not in the WG vocabulary files, only in the draft text as an optional report extension, so there is nothing to vendor; the engine
does not produce them. (Original scope:) Re-vendor `w3c-shacl.ttl` and `w3c-shacl-shacl.ttl` (and the hash record);
add `sh:dataGraph` with `shsh:DataGraphShape`; decide whether to support the optional `sh:ShapeAssignment`,
`sh:assignment` and `sh:nodeAssignmentCount` report terms (they are optional in the spec); add the 7 UI terms; regenerate with
`scripts/build.py`. Check the role-class comments are in the regenerated data. (shared)

**Phase 3. SHACL UI behaviour (small to medium). Done 2026-11-11.** `select_widget` and `select_widgets` take `implemented=` (the widget IRIs
the application can draw: an unimplemented widget is never returned, the walk goes on) and `on_report=` (a callable that gets a
`WidgetReport` for each unimplemented widget that matched and when nothing matches; both default to off). `shui:searchQuery`
and `shui:suggestedValues` are renderer features: the library does not evaluate them. What it does now: the generic catalog scores
`AutoCompleteEditor` 4 for a property shape with `shui:searchQuery` ("the presence of shui:searchQuery raises the AutoCompleteEditor's
score"; the draft's number is 20, ours are tiers 1 to 4); `sparql_query_problems` checks a `shui:searchQuery` (a SELECT that parses, with
`$searchTerm` and `$language` free); `stsh:SearchQueryShape` and `stsh:SuggestedValuesShape` check the shape of the values. Ordering and
tie-breaking went from MUST to SHOULD in the draft: no change. **Property roles** (the 7 terms beyond `suggestedValues`):
the qualified annotation `shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0 ]` was rejected by our shape (it required an
IRI); it is accepted now, with rules for its own parts. `property_shapes_for_role(shape_node=, role=, shapes_graph=)` gives the
property shapes that play a role in the draft's order (qualified before direct, ascending `sh:order`; the triple annotation counts as
qualified); it and `WidgetReport` are exported from `starlayer.shacl`. The term documentation lists all five roles. Label and language
resolution (normative for renderers, they read the data graph and the language preferences) are not implemented: a proposal, not done. Guide 04d has a new subsection. (Original scope:) Widget selection must not offer an unimplemented widget and must report
the case to the application (`shacl/ui_widget_selection.py`: decide how the report is surfaced, which is an API choice); read the
reworked search-query text (`shui:searchQuery` substitution, `$language` for `$uiLanguage`) and `shui:suggestedValues`. Keep our
deterministic ordering: the spec now says SHOULD, so this is no change.

**Phase 4. SRL `GROUP` aggregation (medium to large; the one real feature). Done 2026-11-11.** `GROUP [BY ?k ...] { pattern } [ ?n := COUNT | MIN | MAX | SUM ]`
(productions [22] to [29] of the WD 2026-11-09): the parser (`parse_srl.py`), the AST (`_GroupElement`, `_Aggregation`, a rule with one is run-once),
the well-formedness conditions of 4.2 (`srl_semantic_checks._check_group`: the pattern sees only the keys already bound; a key is bound by the
pattern; an aggregation variable is new and unique; an argument is bound by the pattern), the evaluation of 6.4 (a group per key, one group
when there is no key even if the pattern has no solution, an aggregation error drops the group, `SUM`/`MIN`/`MAX` computed by the engine's own
SPARQL set functions), the closed dependencies of the group pattern in the dependency graph (so stratification orders it after what it reads,
and a rule that groups over its own output is a `StratificationError`), the `srl:` tree (`srl:GroupElement`, `srl:Aggregation`, six new
predicates) with shapes in `srl_shapes.ttl`, and the text renderer. The 16 positive and 10 negative `GROUP` syntax tests of the W3C suite pass
(the strict xfails are gone). The vendored grammar (161 productions, was 153: `BodyBasic` is now `NegationPattern`) and the 14 spec
examples were refreshed from the WD of 2026-11-09, and the corpus has `body-group-*` cases. The suite has no evaluation tests for `GROUP`;
`tests/sparql/test_srl_group.py` (47 tests) is built from the draft's algorithm and its example 8. Guide 03b has a new section 12.
(Original scope:) Read the 2026-11-09 text first. Parser (the 16
syntax tests), AST, the `srl:` tree encoding and shapes (`srl_shapes.ttl`, regenerate), evaluation, stratification (an aggregate
is non-monotonic, treat like negation), well-formedness rules for group variables, refreshed vendored productions and
examples, the coverage matrix and the baseline date mismatch. The suite has syntax tests only, no evaluation tests for `GROUP` yet,
so write evaluation cases from the spec's examples.

**Phase 5. Small items (small).** Snapshot refreshes for the RDF and SPARQL drafts (the changes are editorial; N-Quads and TriG
now have documents: fix the README claim); re-extract the SPARQL Query productions to confirm "editorial only"; decide on
`rdfs14a` (optional, one entailment rule); read the Entailment Regimes draft (no baseline date recorded).

**Phase 6. Stop doing this by hand (small).** Write `scripts/spec_drift.py`: for each pin, the upstream commit count and the files
changed, and each spec's current date against a recorded date. `AGENTS.md` says nothing watches the specs automatically; this
review took most of its time on exactly that.

## 4. Things I could not check

- The wording of the node-expression "ListParameterFunctions" section and the inference-rules condition rule beyond the test
  expectations: read both before phase 1.
- Whether our `sh:ShapeAssignment` handling is absent or merely untested (no suite test covers it).
- The Entailment Regimes changes (no baseline).
- `GROUP` evaluation semantics: the suite has no evaluation tests for it yet.
- The effect of the CSV/TSV and Graph Store Protocol test changes: those suites are not vendored.
