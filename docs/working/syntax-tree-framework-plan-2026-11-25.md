# One family for the three "text <-> RDF syntax tree" languages: findings and plan (2026-11-25)

Status: investigation note for John to decide. Nothing in the code, tests or notebooks was changed to produce it.
Another agent was editing `sparql/*`, `parse_srl.py`, `srl.py` and the Manchester code while this was written, so every
file and line count below is a reading of the working tree on 2026-11-25 and may have moved by the time you read it.
Where a claim rests on a skim rather than a full read, it says so.

## 0. Short answer

- The three languages already share more than the question assumes, and less than a single "common layer" would want.
  They share the `spexpr:` expression/variable/path vocabulary and its shapes, one term/expression encoder
  (`parse_sparql._Encoder`), one SHACL engine path and one report type. They do not share a validation pipeline: each
  language has its own copy of "build the shapes graph, close under RDFS, validate, add findings from Python".
- That pipeline plumbing is the one place where a common layer pays off (roughly 230 lines in three styles down to
  about 80 shared plus short per-language hooks). The shapes themselves overlap less than hoped: what is truly common
  is the term-position shapes, the triple-term shape and about 30 copy-pasted "well-formed rdf:List of X" constraints.
- The `owl:imports` already declared in `sqe_shapes.ttl` and `srl_shapes.ttl` is not what the code uses: both
  languages merge the shapes graphs by hand in Python. The engine and `starontology.local_loader` can resolve imports;
  using them is the low-risk first step.
- Recommended order: finish parse-returns-tree, then common shapes via imports, then a private hook pipeline for SQE and
  SRL, then Manchester. Keep the per-language public functions; add generic ones only when a caller needs them (section 5).

## 1. Class-by-class mapping

Sources: `starontology/sqe/sqe-ontology.ttl`, `sqe_shapes.ttl`, `srl/srl-ontology.ttl`, `srl_shapes.ttl`,
`spexpr/*.ttl`, `sparql/vocab.py`, `sparql/sqe/vocab.py`, the `_Writer` in `srl.py`, `_Encoder` in `parse_sparql.py`.

| Concept | `sqe:` | `srl:` | Same structure? | Shared today |
|---|---|---|---|---|
| Triple pattern | `sqe:TriplePattern` with `sqe:subject/predicate/object`; predicate may be a path | `srl:TriplePattern` with `srl:subject/predicate/object`; no path (paths are expanded into triples by `parse_srl._expand_path`) | Same three properties, different namespace. Predicate shape differs: sqe adds paths | Nothing; two shapes, same message wording |
| Filter | `sqe:Filter` with `sqe:expr` | `srl:FilterElement` with `srl:expr` | Identical in shape, different names | The expression itself (`spexpr:`) |
| Bind / assignment | `sqe:Bind` with `sqe:var`, `sqe:expr` | `srl:AssignmentElement` with `srl:var`, `srl:expr` | Identical in shape. `sqe:Alias` (projection/GROUP BY) is the same pair again | `spexpr:Variable` datatype, expression |
| Negation | `sqe:Exists` (`sqe:where`, `sqe:negated`) sits inside an expression, holds a full pattern list | `srl:NegationElement` (`srl:inner`, `srl:negationEvaldata`) is a body element, inner list limited to triple patterns and filters | Different. Same idea, different place in the tree, different content rules, GROUND flag only in SRL | Nothing |
| Lists | `rdf:List` everywhere (`sqe:where`, `projection`, ...) | `rdf:List` (`rules`, `body`, `head`, `inner`, `keys`, ...) | Identical encoding (`_list` in the encoder; `graph.items` to read) | The encoder helper. The list shapes are copied per class: 6 in sqe, 9 in srl, 3 in spexpr, 13 in manch |
| Triple terms | `sqe:TripleTerm` with `sqe:subject/predicate/object` | Reuses `sqe:TripleTerm` (the shared encoder writes it, `srl.py` decodes it with `sqe.vocab`) | Same node class, so identical. But SRL depends on the `sqe:` namespace for it | Encoder, text renderer idea (two near copies of `_term_text`) |
| Aggregation | spexpr `Aggregate_*` nodes inside expressions; `sqe:groupBy`, `sqe:having`, `sqe:Alias` | `srl:GroupElement` (`keys`, `pattern`, `aggregations`) with `srl:Aggregation` (`var`, `function` as a plain string, `argument`, `distinct`) | Different. SQE aggregates are expressions; SRL's are separate rule elements, and SRL forbids aggregates and EXISTS in FILTER/SET | Nothing |
| Data | `sqe:InsertData`, `DeleteData` (quads: patterns plus `sqe:QuadGraph`) | `srl:Data` with `srl:triples`, ground triples only | Similar (a list of triple patterns), different meaning and rules | Nothing |
| Imports | none (SPARQL has no imports) | `srl:imports`, a list of IRIs on the rule set | SRL-only | n/a |
| Rule set / rule | none. Closest relative: `sqe:ConstructQuery` (`sqe:template` list of triple patterns, `sqe:where`) | `srl:RuleSet` (`rules`, `data`, `imports`), `srl:Rule` (`head`, `body`, `ruleEvaldata`, `id`) | SRL-only. `srl:head` has the same shape as `sqe:template` | n/a |
| Everything else | Query forms, `Optional`, `Union`, `Minus`, `Graph`, `Values`, `SubSelect`, `Service`, dataset clauses, order/limit/offset, prologue (`PrefixBinding`), the whole update family | n/a | SQE-only | n/a |
| Variables, expressions, paths | `spexpr:` | `spexpr:` | Shared already | `spexpr_shapes.ttl` (456 lines), imported by both with `owl:imports` |

Two leaks in the "shared" encoder worth knowing: `parse_sparql._Encoder.node` writes `sqe:TripleTerm` and `sqe:Exists`
even though it is also SRL's encoder, and `spexpr_shapes.ttl` still carries an `ExistsExpression` body shape
(`spexpr:graph`) that the encoder no longer produces (skimmed, not traced to a test; treat as possibly dead).

What a shared "common" shapes graph can hold:

- Fully safe (no property names involved): the term-position shapes (subject-or-variable, predicate-or-variable,
  object-or-variable; today duplicated as `srl:SubjectOrVariableShape` / `sqe:SubjectOrVariableShape` and friends), and a
  generated "well-formed list of class X" shape, using the same trick `spexpr` already uses to generate per-builtin
  shapes (`expression_shapes_turtle`). This removes about 30 copies of one SPARQL constraint.
- Safe but with a naming question: the triple-term shape. It targets `sqe:TripleTerm` and the properties `sqe:subject` etc.
  A "common" file that mentions `sqe:` terms is not common. Options in section 5.
- Needs matching property names, so it costs something: a shared TriplePattern / Filter / Assignment shape. It requires
  `subject/predicate/object`, `expr` and `var` to be one set of IRIs, or a mapping.

The cheap mapping that avoids any rename: write the shared shape over common property IRIs and declare in a common
ontology that `sqe:subject` and `srl:subject` are `rdfs:subPropertyOf` it (likewise `TriplePattern` as `rdfs:subClassOf`).
Both validators already run `rdfs_entailed_copy`, which implements sub-property (rdfs7) and sub-class (rdfs9). Stored
graphs and the notebooks do not change. Costs: validation reports would then name the common path, not `sqe:subject`
(anything that reads `sh:resultPath`, such as a form editor, would see a new IRI), and the `sqe:expr` ontology note says
`rdfs:domain` was avoided on purpose, so no domain may be put on the common properties. I did not run this, so it is a
design, not a verified result. Gain is small (a few dozen lines of Turtle), so I do not recommend doing it now.

Cost of a real rename (one merged namespace or common property names):

| Where | Size | Notes |
|---|---|---|
| Stored sqe trees | `tools/kg/codekg/curated/query-library.ttl`: 977 `sqe:` occurrences (142 triple patterns, 91 `sqe:expr`, 74 `sqe:where`), source of the `codekg.trig`, built by `scripts/build_kg.py` | Would need a migration script and a rebuild; no alias is allowed |
| Tests | about 40 files under `tests/sparql` and `tests/graph/unit` call the three public groups; `test_sqe_parse_update.py`, `test_starontology.py` and `test_srl_shapes.py` match the namespace IRIs | One batch edit, but the shape-mutation and property-based suites encode property names |
| Guides | 06.03 (25 mentions of the function names), 06.04 (18), 06.02 (24), B1 (9), plus 06.01, 06.05, 04.x | The notebook text quotes IRIs |
| Graph-workbench | My grep of `src`, `tests`, `docs`, `tools` finds no `sqe:` or `srl:` IRI and no `sqe_`, `srl_`, `manchester_` call. Only `docs/assistance-log.md` mentions that the codekg named queries are stored as sqe trees | So the workbench is not coupled at the code level. `hidden-graph-app`, `starlayer-apps` and `shape-builder` gave no hits either |
| Variable datatype | `spexpr:Variable` is inside every variable literal | Renaming `spexpr:` is the worst case: it changes literal identity in every stored tree. Never touch it |

## 2. SRL checks done in Python

Where they live now (working tree): `sparql/srl_semantic_checks.py` (296 lines: `_check_ruleset` and the `_check_*`
functions) and `srl.py` (`srl_validate`, `_rule_set_problems`). The `_check_against_shapes` named in the question is gone: the
parse-no-longer-validates commit (de211be6) removed it. `parse_ruleset` now checks nothing beyond the grammar. Running a
rule set calls `_require_well_formed` (a `FormatError` kind `srl`) and `_stratify` (a `StratificationError`). The
stratification step is §4.4, not §4.2.

| Check (issue kind in the code) | Needs | As shape / SPARQL constraint? |
|---|---|---|
| `triple_term_in_subject`, `triple_term_in_predicate` | One node's own properties | Easy. A plain shape on the triple pattern and the triple term |
| `variable_in_data` | Look inside `srl:Data` triples for a variable | Easy |
| `unsupported_variable_name` | A code point above U+FFFF in a variable literal | Easy in principle. Needs a regex on code points; whether the engine's regex flavour accepts that range is unverified |
| `aggregate_in_expression` (also catches EXISTS) | Expression subtree contains an `Aggregate_*` node or `sqe:Exists` | Easy to moderate: property-path walk over the `spexpr:` argument properties, as `sqe_shapes.ttl` already does for its unbound-variable check |
| `unbound_head_variable` | Every head variable is bound somewhere in the body (no ordering) | Moderate. Same walk as the sqe projected-variable check; must count group keys and aggregation variables, and ignore what a negation or group pattern binds |
| `unbound_filter_variable`, `unbound_assignment_expr_variable` | A variable is bound by an earlier body element | Moderate and different from the sqe check: sqe's check ignores order, this one needs "earlier list cell". Expressible with `rdf:rest+` between two cells of the same body list, but a new kind of constraint |
| `reused_assignment_variable` | The SET variable is not already in scope or in use | Moderate to hard (needs "in use", next row) |
| `variable_in_use` | The spec's `inUse` set: variables seen inside a negation or group pattern but not in scope outside it, carried forward | Hard. Depth is bounded (negation cannot nest in negation, a group cannot nest in a group or negation), so it is finite SPARQL, but long and unreadable |
| `group_key_unbound`, `aggregation_variable_in_scope`, `duplicate_aggregation_variable`, `unbound_aggregation_argument` | Group-local set arithmetic | Moderate. Four constraints on `srl:GroupElement` |
| Stratification (`_stratify`) | Dependency graph across all rules (a rule's head against other rules' bodies, open and closed edges, fixpoint of strata) | Stays Python. It is a cross-rule graph algorithm, not a property of one node |
| `IMPORTS` resolution, tree that cannot be decoded (`SRLDecodeError`) | A loader, or a decoder | Stays Python (and the decode error is the reason extras run only after the shapes conform) |

What it means for "parse returns a tree; validate reports": that line is already true for SQE and SRL. The honest
question is whether the SRL conditions should be reported by shapes or by Python.

- Python keeps one source of truth, shared with run time (`_require_well_formed` must exist anyway, since a rule set
  that is not well-formed would evaluate to a wrong answer). The cost: every finding has the `srl:RuleSet` node as focus
  node, so an editor cannot highlight the offending element, and nothing is reported for a tree that cannot be decoded.
- Shapes report on the exact node and also work for a tree that cannot be decoded. The cost: a second implementation of
  the same rules, and the scope/in-use rules are the part that is hard to write and easy to drift.
- Recommendation: do not move any check now. If an editor needs per-element focus, move only the "easy" rows (term
  positions, data, aggregate placement, head binding, group-local) into `srl_shapes.ttl`, keep the Python function as the
  authority, and add a differential test (both must agree on the existing corpus in `tests/sparql/srl_conformance`).
  Scope and in-use stay in Python. Stratification stays in Python in every case.

## 3. Function surface today, and what is generic

| Today | Signature in short | Generic counterpart | Language-specific |
|---|---|---|---|
| `sqe_parse_to_tree` | `(text, tree_graph=None, root=None) -> (graph, root)`; reads queries and updates | `parse_to_tree` | `root=` argument |
| `sqe_tree_to_text` | `(tree_graph, root) -> str` | `tree_to_text` | |
| `sqe_validate` | `(tree_graph) -> ValidationReport`; shapes, then Oxigraph on each rendered query | `validate_tree` | the engine check is an SQE extra |
| `check_query` | text in, `QueryCheck` out (grammar, VERSION, shapes as warnings, engine) | none | Text-level, SPARQL only; keep as is |
| `srl_parse_to_tree` | `(text, base=None, tree_graph=None) -> (graph, root)` | `parse_to_tree` | `base=` |
| `srl_tree_to_text` | `(tree_graph, root)` | `tree_to_text` | |
| `srl_validate` | `(tree_graph)`; shapes, then §4.2 and ordering from the decoded rule set | `validate_tree` | the two extras |
| `parse_ruleset`, `tree_to_ruleset`, `ruleset_to_tree`, `ruleset_to_text`, `RuleSet.infer/query/materialize`, `resolve_imports` | work on the `RuleSet` object | none | all SRL-only; `RuleSet` existed before any tree. Cannot be generic |
| `manchester_parse_to_tree` | `(text, base=None, tree_graph=None) -> graph` (no root; one `manch:Document` per graph) | `parse_to_tree` | returns only the graph; raises if the graph already holds a document |
| `manchester_tree_to_text` | `(tree_graph)` (root found by itself) | `tree_to_text` | no root argument |
| `manchester_validate` | `(tree_graph)`; a pre-flight check on the asserted graph, then SHACL with engine RDFS inference | `validate_tree` | the pre-flight runs before the shapes and can stop them (a cyclic list) |
| `manchester_tree_to_owl` | tree to OWL triples | none | Manchester-only |

Differences a generic function has to hide: `(graph, root)` against `graph` only; `root` required against optional;
`base`, `root`, `tree_graph` accepted by some; Manchester uses a different RDFS route (engine `inference=` and an
`ont_graph`) from the native `rdfs_entailed_copy` the SQE and SRL validators use; only SQE and SRL use `shared_plans`.

Duplication, measured by reading (not by a tool; my line counts are approximate):

| Piece | SQE | SRL | Manchester | Could move |
|---|---|---|---|---|
| Shapes graph building, RDFS closure, plan cache, validate call | `sqe/shapes.py` about 90 lines | `srl.py` about 90 (lines 718-800) | about 40 in `manchester_validate` | about 150 lines into one function of about 50 |
| Adding Python findings as `sh:Violation` | `_with_violations` (about 30), which `srl.py` imports from `sqe.shapes` | the same, imported | `_preflight_report` / `_preflight_text` (about 50), a second implementation | about 80 lines into one |
| Engine/preflight/semantic extras | `_engine_problems` about 35 | `_rule_set_problems` about 20 | `_preflight` about 50 | stay, as hooks |
| Rendering a term to text | `to_text._term_text` about 12 | `srl._term_text` about 14 | n/a | about 14, low value |
| List read/build helpers | `_Sink`/`_list` and `graph.items` | `_read_list` | `_build_rdf_list`, `_read_rdf_list` (about 25) | about 30 |
| Encoder | shared `_Encoder` | uses it | its own | nothing |
| `_is_true` | n/a | one copy | one copy (five more exist in `shacl/`) | trivial |

Total code in play is about 6,000 lines (SQE python 2.1k including the 2.2k-line parser share, SRL about 1.7k excluding
the evaluator, Manchester 1.3k). A common layer saves perhaps 150 to 250 of them. The case for it is one behaviour, not
size: one report shape, one way Python findings are added, one plan cache.

## 4. Registry and hook design

What a language registers (one row per language; the table is private to the package, no public `register()`):

| Field | SQE | SRL | Manchester |
|---|---|---|---|
| name | `sqe` | `srl` | `manchester` |
| namespaces | `sqe:`, `spexpr:` | `srl:`, `spexpr:`, (`sqe:` for triple terms today) | `manch:` |
| root classes | `sqe:Query`, `sqe:UpdateRequest` | `srl:RuleSet` | `manch:Document` |
| form detection (text) | first keyword after prologue: SELECT/ASK/CONSTRUCT/DESCRIBE, or the update keywords (the regex `_UPDATE_START` in `to_rdf.py` already does the second part) | first keyword after PREFIX/BASE/VERSION is RULE, DATA or IMPORTS | a frame keyword with a colon at line start (`Prefix:`, `Ontology:`, `Class:` ...) |
| parse | `sqe_parse_to_tree` | `srl_parse_to_tree` | `manchester_parse_to_tree` (adapted to return `(graph, root)`) |
| render | `sqe_tree_to_text` | `srl_tree_to_text` | `manchester_tree_to_text` (root ignored) |
| shapes entry | `sqe_shacl` (imports `spexpr_shacl`) | `srl_shacl` (imports `spexpr_shacl`) | `manchester_shacl` |
| ontology for the closure | `sqe_owl` + `spexpr_owl` | `srl_owl` + `spexpr_owl` (+ `sqe_owl`) | `manchester_owl` |
| pre-checks | none | none | `_preflight` |
| post-checks (run when the shapes conform) | Oxigraph on each rendered query | §4.2 conditions and ordering | none |
| error kind | `sparql` | `srl` | `manchester` |

How `validate_tree` composes one report: (1) choose the language, from the argument or from the root classes found in the
graph; (2) run the language's pre-checks; one of them may stop here (Manchester's cycle) and the report is built from the
findings alone; (3) validate the shapes with the language's cached shapes graph, RDFS-closed copy of the tree and
`shared_plans`; (4) only if the shapes conform, run post-checks (they decode the tree, which fails on broken structure,
which is why SQE and SRL already do it this way); (5) add each finding as one `sh:Violation` with the focus node the hook
gave, through the single `_with_violations`. Manchester's merge of pre-flight findings into the shapes report happens when
the shapes do not conform too, so the pipeline needs both "merge always" (pre-checks) and "only if conforming"
(post-checks). The hook shape has to allow that from the start, even though Manchester registers last.

Form detection. On a tree it is not a problem: the root classes name the language and the form (`sqe:Query` against
`sqe:UpdateRequest` is already what `_tree_to_text` branches on). On text it is a short sniff of the first keyword after
the prologue; `check_query` already tells query from update by trying the query grammar, then the update grammar, and
keeping whichever read further. Ambiguities: a text that is only a prologue, and SQE/SRL sharing `PREFIX`, `BASE`,
`VERSION`. So `language=None` should sniff, but error with "say which language" when the first keyword is not one of the
known ones, never guess. SRL `DATA` and SPARQL `INSERT DATA` do not collide because `DATA` is only a rule-set start when
it is the first keyword.

Cost. Measured now in this working tree (`.venv`, one run, a small tree each; times are one-off readings on this laptop):

| Call | First call in a process | Warm (mean of 5) | Shapes graph size |
|---|---|---|---|
| `sqe_validate` (SELECT with FILTER and OPTIONAL) | 128 ms | 6 ms | 1,422 triples (613 spexpr + the rest) |
| `srl_validate` (one rule) | 72 ms | 4 ms | 1,709 triples (spexpr + srl + the whole of sqe shapes) |
| `manchester_validate` (one class) | 22 ms | 19 ms | 852 triples |

What it says: the first call is the plan parse, paid once per process; warm calls are single-digit milliseconds. SRL
already carries every sqe shape (about 800 triples) and still validates in 4 ms, so a larger imported graph is not a
performance issue. Manchester does not use `shared_plans` and runs the engine's own RDFS inference, which is likely why
it is the slowest warm. Registering it later would probably cut that, but I did not measure it. One real risk: `shared_plans`
caches by the shapes graph object. If validation resolved the imports on every call (a new merged graph each time) the
cache would miss. So resolve the import closure once per language and cache the merged graph, exactly as `_shapes_graph()`
does now. Alternative I did not test: one combined shapes graph with the three `sh:ShapesGraph` modules selected through
`shapes_graph_resource`; I did not check how the engine scopes targets then.

## 5. Options and recommendations for the three open choices

### (a) Generic public functions, per-language functions, or both

| Option | For | Against |
|---|---|---|
| A. Per-language functions stay the API; the common layer is internal | No rename, so no churn in about 40 test files, 9 guides, CLAUDE.md files. Distinct signatures stay honest (`RuleSet`, Manchester's no-root, SQE's `root=`) | No language-agnostic call for tools that hold "a tree" |
| B. Generic functions only (`parse_to_tree(text, language)`, `tree_to_text`, `validate_tree`); old names removed | One mental model, one notebook, adding a language is one registration | No aliases allowed, so every call site and guide changes in one commit; `RuleSet`, `check_query`, `tree_to_owl` stay outside it anyway, so it is not one surface; Manchester's return type changes |
| C. Both public | Convenient | The repo has already decided against two paths to one thing (see `sparql/__init__.py`: flattening `srl` into `sparql` was tried and reverted on 2026-10-03). Two ways to validate the same tree will drift in docs and in tests |

Recommendation: A now. Add the two tree-side generic functions (`validate_tree` and `tree_to_text`, both dispatching on
the root class, so there is no ambiguity) publicly only when a real caller needs them, most likely the workbench. If
that happens, document them as the way to handle a tree of unknown language, and the per-language ones as the way to
work in a language you know, with the rule that the generic ones are thin calls into the same code. `parse_to_tree` with
`language=` is the one I would add last: it is the only one that needs sniffing, and callers always know the language.

### (b) Package or module name

| Name | For | Against |
|---|---|---|
| `starlayer.syntax_trees` | Says what it is; matches the wording already used in `starontology` ("syntax-tree-graph") and in the Manchester docs | Longer |
| `starlayer.trees` | Short | Too generic; "tree" also means RDF lists, parse trees (`Node`), `TreeIndex` in the same code |
| John's `sqtr`, `trsq`, `trmanch` | Short, in the spirit of the namespace prefixes `sqe:`/`srl:`/`manch:`, which are abbreviations already | A namespace prefix is a label inside Turtle that a reader sees next to its expansion; a package name has no expansion beside it. Three differently-ordered abbreviations (`sqtr` against `trsq` against `trmanch`) will not be remembered. `trmanch` also drops `srl` entirely |

Recommendation: `starlayer.syntax_trees`. Keep the prefixes `sqe:`, `srl:`, `manch:` as they are (stored graphs). The new
package starts as registry plus pipeline only; the language code stays where it is until there is a reason to move it, so
no import path changes at first. Import direction: `starlayer.sparql.*` imports the pipeline from `syntax_trees`;
`syntax_trees` imports languages lazily by dotted string (the pattern `sparql/__init__.py` already uses), so no cycle.

### (c) Manchester at the start or after SQE and SRL

Recommendation: after. SQE and SRL are near twins (same encoder, same validation steps, same return type), so a design
drawn from them is easy to check. Manchester differs in four ways that matter to the hooks: no root, one document per
graph, a pre-check that can stop the shapes, and a different RDFS route; its code is 1,345 lines in
`starontology/manchester/__init__.py`, while its text parser is in `starlayer.graph.manchester`. Fit the hook
signatures to allow pre-checks and an optional root from the first stage, so Manchester is a registration later, not a
redesign. Moving the Manchester code out of `starontology` is a separate and optional step (the data-only rule in
`starontology/__init__.py` has an exception noted for it already).

## 6. Staged plan

Each stage is a separate green commit (or a short run of them), targeted tests only, full suite on request.

| Stage | Scope | Risk | Tests | Guides | Workbench |
|---|---|---|---|---|---|
| 0. Finish parse-returns-tree (in progress) | SQE (0da83084) and SRL (de211be6) are in. Confirm what is left: `check_query`/`_shape_problems`, update trees, `parse_ruleset` docs, that Manchester parse has no `validate=` left, error-kind names (`sparql`, `srl`, `manchester`) | Low | the tests the other agent is already running | 06.03 is modified in the working tree now; 06.04, 04.x text | none |
| 1. Common shapes via imports | (1a) Replace the hand merges in `sqe/shapes.py` and `srl.py` by one cached function that resolves the declared `owl:imports` closure through `starontology.local_loader`. (1b) Add a small shared file with term-position shapes and a generated list shape; point sqe, srl at it | Low to medium. A new registry entry means `test_starontology` counts, `starlayer-profiles.ttl` resources, `get_ontology_list` and docs change. Report text may change where a message moves | `test_srl_shapes`, `test_sqe_shape_mutations`, `test_sqe_ontology`, `test_starontology`, `test_sqe_property_based`; compare reports before and after on a fixed corpus | B1 (shared parts) most; 06.01, 06.05 list the entries; 06.03, 06.04 mention shapes | none if no one reads `sqe_shacl`; my grep says no. Tell the other session that shape IRIs inside reports may change |
| 2. Hook pipeline, SQE and SRL only | New `starlayer/syntax_trees/` with the pipeline (shapes, closure, plans, `_with_violations`, report merge) and a private table of two rows; `sqe_validate` and `srl_validate` become calls into it; `srl.py` stops importing from `sqe.shapes` | Medium: report text, ordering of results, and the plan cache must stay as now | `test_sqe_validate_engine`, `test_srl_semantic_checks`, `test_srl_shapes`, `test_error_narrowing_clauses`; a golden test that the report graph is identical before and after on the corpus | None if public names stay. Docstrings only | None |
| 3. Generic tree-side functions (optional) | `validate_tree`, `tree_to_text`, maybe `parse_to_tree`, once a caller asks | Low code, high documentation cost (two paths) | A dispatch test per root class; a "language not given" error test | New short section in 06.03 or a new overview; a notebook merge is a separate decision | The workbench could call `validate_tree(graph)` on any tree |
| 4. Manchester joins | Register it: adapt return to `(graph, root)` inside the hook only; `_preflight` becomes a pre-check; move to `shared_plans`; one report-merge path | Medium: Manchester's tests (`test_manchester_ast*`, `manchester_conformance`) are strict, and RDFS route change may change what conforms | those, plus timing | 06.02 only if its public functions or output change | none expected |
| 5. Guides | One notebook or two, after a decision: 06.03 SQE, 06.04 SRL, 06.02 Manchester, B1 shared parts | Editing cost only | `scripts/check_notebook_links.py` | all via `docs/guides-staging/stage`, approval per batch, pushed with `scripts/guide_staging.py` | none |

What must be decided first: (i) the triple-term question (below), (ii) whether any public generic function ships (a),
(iii) the package name (b). Stages 0 to 2 need only (i).

The triple-term question: SRL borrows `sqe:TripleTerm`. Options. Leave as is and let SRL keep importing the whole sqe
shapes (works; SRL carries about 800 unused triples; no migration). Or move the class, ontology and shape to the shared
vocabulary as `spexpr:TripleTerm` (the clean answer; every stored tree and test that holds a triple term changes, and
the query library has none today, 0 occurrences of `sqe:TripleTerm` in `query-library.ttl`, so the stored cost is small,
but tests and guides do). Or keep the IRI `sqe:TripleTerm` and move only its shape into the shared file (no rename,
but a "shared" file that names `sqe:`). I lean to the first for stages 1 and 2 and the second as its own later commit
once Manchester is in; the third is the one to avoid.

## 7. What not to do

- Do not merge the namespaces or rename `sqe:` / `srl:` / `spexpr:` terms. Stored trees (the query library, about 977
  `sqe:` terms and anything users keep) and `spexpr:Variable` inside every variable literal make it expensive, and there
  is no alias rule to soften it. A common layer that needs a rename is the wrong common layer; use `rdfs:subPropertyOf`
  if sharing a shape is ever worth it.
- Do not build the framework first and port the languages onto it. Extract it from the two near-identical pipelines that
  exist (SQE, SRL), shaped so Manchester's two phases fit, then add the third. A three-language abstraction drawn from
  one language and two guesses will be wrong in the hooks.
- Do not create a public `register_language` function. Three languages, all ours; a public hook invites a fourth party
  and a compatibility promise.
- Do not ship both generic and per-language public functions as equals (option C): the repo already reverted that
  pattern once.
- Do not move the §4.2 checks into shapes just because the sqe projected-variable check is one. That check ignores order;
  SRL's depend on order and on the "in use" set, and run time needs the Python version anyway.
- Do not move stratification, import resolution or the Oxigraph engine check into shapes. They are not properties of a
  node.
- Do not move language code into the new package in stage 2. It changes every import path and adds nothing.
- Do not make `check_query` generic. It is a text-level SPARQL check (grammar, VERSION, engine), not a tree function.

## 8. What I could not verify

- Behaviour of the declared `owl:imports` through `local_loader` in the validators (not run). The engine and
  `starontology.local_loader` exist and are documented to resolve it; plan-cache behaviour with a resolved import is
  inferred from `shared_plans` keying on the graph object, not tested.
- Whether the `rdfs:subPropertyOf` sharing trick works end to end with the shapes engine (design only).
- Whether `spexpr:ExistsExpression` and its body shape are dead.
- Whether a regex on code points above U+FFFF works in the engine's SPARQL, for the variable-name check.
- The files other agents were editing (`sparql/*`, `parse_srl.py`, `srl.py`, Manchester): line counts and the "what is
  left in stage 0" list may already be out of date. Manchester's parse path for a `validate=` argument was not re-read.
- Workbench coupling: I grepped `graph-workbench` (`src`, `tests`, `docs`, `tools`), `hidden-graph-app`, `starlayer-apps`
  and `shape-builder` for the namespace IRIs and function names and found only a prose mention; I did not read the
  workbench's use of the starontology registry (for example `get_ontology_graph("sqe_shacl")` by variable name).
- The duplicated-line figures are estimates from reading, not a tool; the timings are one run on one machine.
