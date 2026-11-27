# Step A: one error scheme for StarLayer, plan (2026-11-25)

Phase 1 of step A of `docs/working/error-handling-audit-2026-11-25.md`: a plan, no code. Scanned at HEAD `86d8b216` (step C done: the cause-not-path rule and `context` are in SHACL; the `ambiguous` kind was removed again and `RecordingGraph.value` raises `ValueError`). Counts come from an `ast` walk of `packages/starlayer/starlayer`, `packages/starlayer-reasoning` and `packages/starlayer-kg` (tests, benchmarks and `shacl/` raise sites excluded unless said), from greps of `tests/`, `docs/guides/*.ipynb` and the read-only `../graph-workbench`, and from running pyoxigraph 0.5.13 for the behaviours marked "run". What I could not determine is listed at the end of each part and in part 7.

## Summary

1. **Design.** One new leaf module `starlayer/errors.py` (standard library only, so it cannot be in an import cycle) holds six public names: `StarLayerError(Exception)`, `ShapeError`, `ShapeCompileError`, `MetaShaclError`, `ExecutionError` (one class, 13 kinds) and `FormatError` (one class, 6 kinds). `starlayer.shacl` and `starlayer.shacl.errors` re-export the same SHACL objects, so SHACL imports keep working with no alias. One more public name stays: `EndpointError`, rebased to `(StarLayerError, OSError)`, because a network failure is an I/O error and the guides and the workbench catch `OSError` for it. The other 20 existing classes disappear (14 become `FormatError`, 6 become `ExecutionError`); `SRLUnresolvedImportsWarning` and the private `_NotComputable` / `_InvalidInstance` stay. Nothing derives from `ValueError`, `SyntaxError` or `RuntimeError` any more, `ShapeError` included (question 1).
2. **Rule that results.** `ValueError` / `TypeError`: a bad argument at a public call. `ImportError`: a missing optional package. `NotImplementedError`: only the 13 wrapper methods that really are not implemented. Protocol errors (`AttributeError`, `KeyError`, `StopIteration`) in dunder methods. Everything else a library error: `FormatError` (a document or data is malformed), `ExecutionError` (a run failed or the input is valid but unsupported), `ShapeError` (a shapes graph is wrong). pyoxigraph's own `SyntaxError` and `RuntimeError` are wrapped at 5 boundary points (part 4).
3. **Size.** About 150 raise sites in 33 files (the audit's 125 plus the unsupported / internal sites it counted separately and the 7 `RecursionError` conversions), 17 catch clauses, 5 boundary points, 52 non-SHACL test files that name an old class (plus up to about 25 that assert a builtin class for a changed site), 8 guide notebooks that name an old class (24 cells) plus 6 cells that catch a builtin class around a changed call. The workbench has no `except SyntaxError`, about 7 `except ValueError` that wrap `parse_term`, term conversion or `update()` and would stop catching, and imports only `ShapeError` and `MetaShaclError`.
4. **Order and release.** Eight stages (0, 0b, 1 to 6), each its own green commit, the order chosen so that the same cause changes class in one commit (SPARQL syntax from the graph and from the parser together). Do them as consecutive commits on `main` but tag one release after stage 6: with no aliases, one break is better than five (question 7). Stage 3 (SRL) and stage 2 (SPARQL text plus the query/update boundary) are the two big ones.
5. **Verification.** Targeted test slices per stage (part 5), plus three new contract tests added in stage 0 and tightened each stage: the class tree and kind table, an AST scan that bans builtin raises outside an allowlist and unnamed broad catches, and a scan that every `kind=` literal is in the table.

## Questions the user must answer (my proposed answer first)

Already decided and not repeated: scheme (C then A), cause-not-path, `context` as a string, plain `ValueError`/`TypeError` only for a bad argument, one class plus a kind.

1. **`ShapeError` and `ValueError`.** PROPOSED: `ShapeError` derives from `StarLayerError` only; it stops being a `ValueError` (a caller's `except ValueError` for a wrong shapes graph stops working; the rule "plain ValueError only for bad arguments" can then be tested by scanning). Alternative: keep it a `ValueError` (no break, the rule has a named exception). Known users of the old base: `tests/shacl/unit/test_error_classes.py:70,254`, `graph-workbench/tests/test_paths.py:83`, guide 05.02 cell `e9020030` (`except ValueError`), `sparql/check.py:140` (a clause that exists only for this).
2. **Position fields.** PROPOSED: `FormatError` always has optional `line`, `col`, `pos` (all `None` when unknown) and `why` (the reason without the position), the names `SparqlSyntaxError` has today (`sparql/check.py:82-87` reads `pos`, `why`, `col`); never parsed out of an engine message. Alternative: kind and message only.
3. **Wrap pyoxigraph at `graph.query()`, `update()`, `parse()`, `serialize()` and the endpoint reader.** PROPOSED: yes (the only way "a malformed query is one class" holds). It breaks every `except SyntaxError` / `except RuntimeError` around those calls; the workbench has none of the former and uses broad `except Exception` there.
4. **`NotImplementedError`.** PROPOSED: keep it for the 13 wrapper refusals of a method the object does not have (`endpoint.py:323,330,341`, `run.py:70,74,130,185`, `core.py:657,843,907,911` and the entailment one at `core.py:721` becomes `ValueError`); the 14 "no rendering / not modelled for this tree node" and the unsupported entailment of `sqe/entailment.py:123` become `ExecutionError(kind="unsupported")`. Alternative: all to `ExecutionError`.
5. **SRL wrong rule set** (`StratificationError`, the §4.2 well-formedness errors, a head variable not bound, `SRLDecodeError`, a bad `DATA` block). PROPOSED: `FormatError(kind="srl")` (the SRL counterpart of `ShapeError`; it is found by analysis of the document, not by running). Alternative: `ExecutionError(kind="rule")` for the three that are raised while running.
6. **Missing packages.** PROPOSED: `ImportError` for a missing optional Python package (3 `RuntimeError` sites become `ImportError`); a missing or broken Java runtime is `ExecutionError(kind="inference")`. Alternative: a `kind="missing-package"`.
7. **One release or stages.** PROPOSED: stages as separate commits, one release (tag) after the last. Alternative: one tag per subsystem (callers update up to five times).
8. **`EndpointError`.** PROPOSED: keep as the one extra public class, `(StarLayerError, OSError)` with `status`, instead of `ExecutionError(kind="endpoint")`. It is the only place where a Python builtin base is kept on purpose. Alternative: `kind="endpoint"` plus a `status` attribute on `ExecutionError` (7b notebook and the workbench's `except OSError` break).
9. **Parsing a too deeply nested text.** PROPOSED: `ExecutionError(kind="nesting")` everywhere (SHACL's kind; the cause is the limit, not the document), so a caller who catches `FormatError` for a hostile query misses it. Alternative: `FormatError` with the same text but a `nesting` flag; I advise against it.
10. **A `limit` kind.** PROPOSED: add `limit` (RDFC-1.0 complexity cap, and SHACL's `max_iterations` / `max_triples`), which moves SHACL's two sites (`shacl/engine/rules.py:628,722`) from `kind="rule"` to `"limit"` (SHACL tests and guide 05c/05.02 text change). Alternative: `limit` only for canonicalization and leave SHACL's two as `"rule"` (the same cause then has two kinds, against the rule just adopted).

(Audit question 9 is answered by step C; its two open sub-points are done in `b584f164`, except that `RuleResult.failures` is still a `list[str]`, `shacl/engine/rules.py:258,704`: not in scope here unless you want it.)

## 1. Final design

### 1.1 Module and import safety

Path: `packages/starlayer/starlayer/errors.py`. It imports `from __future__ import annotations` and `typing` only; never `starlayer.*`, `rdflib` or `pyoxigraph`. Importing it needs no part of the package, so it is a leaf.

Real import graph (AST walk of all `import` / `from` statements, module level and lazy): `graph` imports `starlayer.sparql`, `starlayer.shacl` (3 + 4 + 1 + 2 lazy and top-level statements), `sparql` imports `graph` (15+4+1) and `shacl` (8+5+1), `shacl` imports `graph` (20+17+5+3) and `sparql` (5), `starontology` imports `graph` and `shacl`. So the subpackages already import each other (graph-shacl-sparql form cycles, kept working with function-level imports); `starlayer/__init__.py` imports `graph`, `shacl`, `sparql` at top. `starlayer-reasoning` imports only `starlayer.graph` (`interop`, `rdflib_bridge`) and `starlayer-kg` imports nothing from `starlayer`. Proof of no new cycle: a graph with an added node that has no outgoing edges has no new cycle; every new edge is `X -> starlayer.errors`, and `errors` has none. One subtlety: importing `starlayer.errors` first runs `starlayer/__init__.py`, which imports `graph`, `shacl`, `sparql`; those modules do `from starlayer.errors import ...` while `starlayer.errors` is not yet imported, which Python resolves by importing the submodule on demand, with no dependency on a name in the partly built package. The same already happens for every `from starlayer.graph.x import y` today. Pinned by a test (part 5): `errors.py` imports only the standard library.

Where the classes are imported from today: `shacl/engine/plan.py` defines `ShapeError`, `ShapeCompileError`, `ExecutionError`; `shacl/engine/meta.py` defines `MetaShaclError`; `shacl/errors.py` and `shacl/__init__.py` re-export. 40 files under `starlayer/` import `from starlayer.shacl.engine.(plan|meta) import ...`, 37 of them name one of the four classes, and 22 test files import from `shacl.engine.plan` / `.meta` (19 of them an error class). The first stage moves the definitions and rewrites these imports (no alias left in `plan.py` or `meta.py`).

Import path stability decided: `starlayer.shacl.ShapeError` and `starlayer.shacl.errors.ShapeError` stay (the same objects; a re-export, not an alias, and what the guides, the workbench and the shacl docs use). The new public home is `starlayer.errors`. Not added to `starlayer.__all__` (`tests/packaging/test_reexports.py` pins that list to the three top-level entry points).

### 1.2 Public classes

```
StarLayerError(Exception)                     never raised bare; no ValueError, SyntaxError, RuntimeError, OSError base
 |- ShapeError                                 as today: context
 |   |- ShapeCompileError
 |   `- MetaShaclError                         problems, report_text, report_graph, scope (unchanged)
 |- ExecutionError                             kind, context (and KINDS, __reduce__, reraise_unless helper as today)
 |- FormatError                                kind, context, why, line, col, pos
 `- EndpointError(StarLayerError, OSError)     status (graph/endpoint.py, exported from starlayer.graph as today)
```

- **`StarLayerError(Exception)`.** No `ValueError` base: the rule "a plain ValueError is only a bad argument" cannot hold if the library's own errors are caught by `except ValueError` (the audit counted 14 custom `ValueError` subclasses and 12 `except ValueError` clauses in the library). `ShapeError` gives up its `ValueError` base (question 1); `StarLayerError` itself is the catch-all, `except StarLayerError` means "the library said no on purpose". `context` lives on `ExecutionError`, `FormatError`, `ShapeError`, not on the base (keeps the base empty, and `EndpointError` has `status` instead).
- **`ExecutionError(message, *, kind, context=None)`.** Unchanged signature. `KINDS` is a class tuple checked in `__init__` (an unknown kind raises `ValueError`, as now); each stage adds its kinds to `KINDS` together with the first raise site that uses them, so no kind exists unused.
- **`FormatError(message, *, kind, context=None, why=None, line=None, col=None, pos=None)`.** `kind` checked against `KINDS` as above. `str(error)` is the message (the position is already in it, as `SparqlSyntaxError` does today). `why` is the reason without the position (defaults to the message). `pos` is the 0-based offset into the text, `line` / `col` are 1-based. Private helpers in each subsystem build the position prefix and caret text (`parse_sparql._syntax_error(why, text, pos)`, `manchester/parser._syntax_error(why, text, pos, line)`); they are not public names. `ManchesterSyntaxError.text` (the local text used only to draw the caret) is not kept. `__reduce__` like `ExecutionError`'s so the keyword-only fields survive pickle and `copy` (multiprocessing is used by `starlayer_reasoning/_timeout.py`).
- **`EndpointError(message, status=None)`** keeps `OSError` second so `except OSError` still catches it; no other library class has a builtin base.
- Warnings are not errors: `SRLUnresolvedImportsWarning(UserWarning)` and `StarLayerFidelityWarning(UserWarning)` stay where they are.

Public names: 7 (`StarLayerError`, `ShapeError`, `ShapeCompileError`, `MetaShaclError`, `ExecutionError`, `FormatError`, `EndpointError`); today SHACL has 4 and the rest of the library 20 (plus 2 private).

### 1.3 `ExecutionError` kinds

Six exist (SHACL, step C). Checked against the real raise sites; 7 new:

| kind | meaning | raise sites it replaces (file, count) | verdict |
|---|---|---|---|
| `rule` (exists) | a rule failed while running, or the rule set as a whole | SHACL | keep (minus the two limit sites, question 10) |
| `expression` (exists) | node expression cannot be evaluated | SHACL; after stage 2 also an engine function failure reported through a SPARQL expression | keep |
| `nesting` (exists) | depth limit | SHACL plus 7 `RecursionError` conversions: `parse_sparql.py:1803,1827,2179,2200`, `parse_srl.py:315`, `sqe/to_text.py:150`, `sqe/entailment.py:142`, `manchester/parser.py:1692`, `starontology/manchester/__init__.py:1120`; and 3 classes' raises (`SqeTextTooDeepError` 1, `EntailmentRewriteError` nesting 1, the Manchester one) | keep; one kind for the five "nested too deeply" classes |
| `recursion`, `constraint-query` (exist) | SHACL only | SHACL | keep |
| `internal` (exists) | a bug in StarLayer | `AssertionError` at `manchester/parser.py` 2, `manchester/serializer.py` 2, `starontology/manchester/__init__.py` 6, `pretty.py` 1; `TypeError` at `srl_eval.py` 1, `srl_semantic_checks.py` 1 (13 sites) | keep |
| `query` (new) | the engine failed to evaluate a query or update (pyoxigraph `RuntimeError`) | the boundary only (part 4), `_NotComputable`-style fallbacks stay; 3 call sites in `run.py` | add (stage 2) |
| `unsupported` (new) | well-formed input the library cannot handle | 14 `NotImplementedError` render gaps (`sqe/to_text.py` 5, `expr_text.py` 3, `srl.py` 3, `parse_sparql.py` 1, `sqe/entailment.py` 1, plus `sqe/to_text` helper), about 7 of the 13 plain `ValueError` "unsupported" (`relevant.py` 2, `endpoint.py:158,242`, `manchester/serializer.py` 5, `execution/update_scope.py:160`, `sparql_text.py:175`; the ones fixed by changing an argument stay `ValueError`: `interop.py:430`, `pretty.py:735`, `core.py:534,1022`), a rustdl pre-check (`owl_dl_rustdl.py` `UnsupportedAxiomError`, 1) | add (stage 6) |
| `timeout` (new) | OWL-DL reasoning exceeded its time | `_timeout.py` 1 of its 2 sites | add (stage 1) |
| `inconsistent` (new) | the ontology is inconsistent | `owl_dl.py` 1, `owl_dl_rustdl.py` 1, the parent-side re-raise `owl_dl.py:123` | add (stage 1); callers (4 guide notebooks, 5 test files) do branch on it |
| `inference` (new) | the reasoner could not run: crashed child, Java missing or broken, owlready2 Java error | `_timeout.py:156` (reported today as a timeout but the message says it is not), `owl_dl.py` 3 `RuntimeError`, `owl_dl.py:126` | add (stage 1) |
| `limit` (new) | a size or complexity cap was exceeded | `rdfc_native.py` 2 (`CanonicalizationComplexityError`), SHACL `rules.py:628,722` (question 10) | add (stage 6) |
| `import` (new) | an `IMPORTS` document could not be read or resolved (SRL) | `srl.py` 2 (`SRLImportError`: cannot read), `srl_eval.py` 1 (`SRLImportsNotSupportedError`) | add (stage 3); the weakest kind (3 sites): the first to drop if "too granular" is the verdict, the fallback is `unsupported` |
| `endpoint` | not a kind: `EndpointError` stays a class (question 8) | `endpoint.py` 5 | - |

Dropped from the audit's list: `endpoint` (class kept), a separate `ambiguous` (`value()` is `ValueError` again since `b584f164`: "found more than one match" is a bad call on a lookup that asked for one), `missing-package` (`ImportError`). 13 kinds in all.

### 1.4 `FormatError` kinds

| kind | for | existing classes / sites |
|---|---|---|
| `sparql` | SPARQL query or update text, an `sqe:` tree, a VERSION declaration | `SparqlSyntaxError` (`parse_sparql.py` 8, `srl.py:442` 1), `SQEValidationError` (`parse_sparql.py` 2, `sqe/to_rdf.py` 1), `SPARQL12ConformanceError` (`version_conformance.py` 2 via `error_class`), `update_scope.py:165` builtin `SyntaxError`, pyoxigraph `SyntaxError` from `query()` and `update()` |
| `srl` | SRL text or rule-set tree: syntax, §4.2 well-formedness, stratification, decode, bad `DATA` | `SRLParseError` (`srl.py` 2, `_srl_ast.py` 1, `parse_srl.py` 5 via `_srl_error`), `SRLDecodeError` 4, `StratificationError` 2, `SRLEvalError` 3, invalid rule set from an import |
| `rdf` | an RDF document or RDF data structure that is malformed: parser errors, N-Triples VERSION line, a malformed `rdf:List`, the PropositionForm encoding | pyoxigraph `SyntaxError` from `parse()`, `ntversion.py:52` 1, `BasicEncodingError` (`interop.py` 13), `core.py:381,386` 2, `rdflist.py:44,48` 2 |
| `term` | a term in text or a lexical form that is not valid | `terms.py:150,177,183,185` (4), `InvalidTripleTermError` (`triple_term.py:80` 1) |
| `manchester` | Manchester syntax text, and the `manch:Document` RDF tree | `ManchesterSyntaxError` (`manchester/parser.py` 3, `starontology/manchester/__init__.py:1122` render-nesting goes to `nesting`), `starontology/manchester/__init__.py:716,753,774` (3 ValueError) |
| `owl` | OWL-in-RDF that is not a valid class / property / range / list | `manchester/serializer.py` 9 `ValueError` (`:378,382,399,426,455,458,460,507,511` in the audit's numbering; re-scan at stage time) |

Merged or dropped from the audit's list of candidates: `json` and `xml` (no library raise site: a malformed JSON result from an endpoint is pyoxigraph's `SyntaxError` and becomes `EndpointError`, because the endpoint's answer is the failure, which is a judgement call), `turtle` (folded into `rdf`), `rule-set` (folded into `srl`), `encoding` (folded into `rdf`). 6 kinds; `manchester` and `owl` could merge (the user's call, minor).

### 1.5 What happens to each of the 21 existing classes (22 counting the warning)

| Class | Becomes | Where |
|---|---|---|
| `SparqlSyntaxError`, `SQEError`, `SQEValidationError`, `SPARQL12ConformanceError` | `FormatError(kind="sparql")` | stage 2 |
| `SRLError`, `SRLParseError`, `SRLDecodeError`, `SRLEvalError`, `StratificationError` | `FormatError(kind="srl")` | stage 3 |
| `SRLImportError`, `SRLImportsNotSupportedError` | `ExecutionError(kind="import")` (an invalid imported rule set: `FormatError("srl")`) | stage 3 |
| `BasicEncodingError` | `FormatError(kind="rdf")` | stage 4 |
| `InvalidTripleTermError` | `FormatError(kind="term")` | stage 4 |
| `ManchesterSyntaxError` | `FormatError(kind="manchester")` (file `graph/manchester/errors.py` removed) | stage 5 |
| `SqeTextTooDeepError`, `EntailmentRewriteError` | `ExecutionError(kind="nesting")` / `"unsupported"` | stage 6 |
| `CanonicalizationComplexityError` | `ExecutionError(kind="limit")` | stage 6 |
| `ReasoningTimeoutError` | `ExecutionError(kind="timeout")` (the crash case `"inference"`) | stage 1 |
| `InconsistentOntologyError` | `ExecutionError(kind="inconsistent")` | stage 1 |
| `EndpointError` | kept, base `(StarLayerError, OSError)` | stage 6 |
| `SRLUnresolvedImportsWarning` | kept | - |
| `_NotComputable`, `_InvalidInstance` | kept (private control flow, caught in the module) | - |

## 2. The audit's 9 questions

| # | Question | PROPOSED | Alternative |
|---|---|---|---|
| 1 | Scheme | decided: C then A | B, C only |
| 2 | `ShapeError` a `ValueError`? | No (question 1 above). The tree is "documents are wrong", not "arguments are wrong"; the swallow risk is the same as for every other `ValueError` subclass. Cost: 3 test assertions, 1 guide cell, one workbench test, and the `check.py:140` clause goes | keep, document as the exception |
| 3 | `pos/line/col` on `FormatError` | yes, optional, all kinds, `None` when unknown | message only |
| 4 | Wrap pyoxigraph | yes, 5 boundary points (part 4) | leave `SyntaxError` / `RuntimeError` for `query()` etc. |
| 5 | `NotImplementedError` | keep for the 13 wrapper refusals, library error elsewhere | all `ExecutionError` |
| 6 | `StratificationError` and SRL well-formedness | `FormatError(kind="srl")` | execution failure |
| 7 | Missing package | `ImportError`; Java runtime: `ExecutionError(kind="inference")` | `kind="missing-package"` |
| 8 | Order and scope | stages as commits, one release | one release per subsystem |
| 9 | Principle and mechanism | adopted in step C (`context` as a string); fragments and rule-value swallowing already raise (`b584f164`); `RuleResult.failures` still `list[str]` and not in step A | structured failures |

## 3. Migration: ordered stages

Every stage ends green on its slice and on `tests/packaging` and `tests/repo`, deletes the old classes it replaces in the same commit (no alias), and updates the tests that assert them. File lists are from the scan; "sites" are raise statements. Guide cells are ids in the notebook; edits go through `docs/guides-staging` (standing rule) and `scripts/check_notebook_links.py` / the `review-notebook-links` skill after.

### Stage 0: the module and the move (no behaviour change)

- New `starlayer/errors.py` with `StarLayerError`, `ShapeError`, `ShapeCompileError`, `MetaShaclError`, `ExecutionError` (+ `reraise_unless`, `_rebuild_execution_error`), `FormatError`, `KINDS` for `FormatError` empty until stage 2 (or the first kind added with its first user). `ShapeError` is still `ValueError` here, so the commit is a pure move plus the new base.
- Edit `shacl/engine/plan.py`, `shacl/engine/meta.py` (definitions removed), `shacl/errors.py` and `shacl/__init__.py` (re-export from `starlayer.errors`), and the 40 files that import from `plan` / `meta` (37 name an error class). `shacl/errors.py` docstring says the classes now live in `starlayer.errors`.
- Tests: 22 test files import from `shacl.engine.plan` / `meta` (19 an error class): imports change only. New: `tests/repo/test_error_scheme.py` (class tree, `errors.py` imports only the standard library, kind tables).
- Docs: `AGENTS.md:45` (the "Outside shacl/ not yet uniform" sentence is updated at stage 6, not here), `shacl/CLAUDE.md` (where the classes live). No guide changes.
- Size: small, 45 files, mechanical.

### Stage 0b: `ShapeError` stops being a `ValueError` (question 1)

- `starlayer/errors.py` base change. Remove the clause `sparql/check.py:140` (`except ShapeError: raise`) and re-read every `except ValueError` that can see a `ShapeError` from a call inside its try: shacl `engine/reads.py:144`, `engine/entailment.py:64`, `engine/expressions.py:242`, `engine/targets.py:123`, `engine/text.py:97`, `engine/value_form.py:46`, `engine/builtin_functions.py:84`, `components/core_string_pair.py:49,196`, `form_model.py:225,251`, `ui/property_roles.py:42`, `ui/widget_selection.py:278,299`, `overlay_oxigraph.py:51,105,125`: all of them wrap `int()`, `float()`, string or term conversions, none a call that raises `ShapeError` (read, not run).
- Tests: `tests/shacl/unit/test_error_classes.py:70,254` (assert `issubclass(.., ValueError)`) become "is not a ValueError"; 32 shacl test files use `pytest.raises(ValueError` (most for bad arguments, unchanged); any that raises a `ShapeError` is found by running `tests/shacl` and fixing the failures (not enumerable without running).
- Docs: guide 05.02 cell `e9020030` (markdown: "a ValueError"), `shacl/CLAUDE.md` ("`ShapeError` (a `ValueError`)"), the `errors.py` docstring.
- Workbench: `tests/test_paths.py:83` (`pytest.raises(ValueError)` with the comment "ShapeError, which is a ValueError"); the other ~100 `except ValueError` in `src/` were not individually traced to a `ShapeError`, the adapter already catches `ShapeError` by name (`_starlayer.py:330,358`).
- Size: 1 class, 1 clause, about 4 tests, 1 cell.

### Stage 1: reasoning package (leaf, no library callers)

- Files: `starlayer_reasoning/_timeout.py` (2 raises of `ReasoningTimeoutError`, class defined at `:72`), `owl_dl.py` (`InconsistentOntologyError` defined `:46` plus 1 raise, 3 `RuntimeError`, handler `:123,126`), `owl_dl_rustdl.py` (1 `InconsistentOntologyError`, 1 `RuntimeError`, 1 `UnsupportedAxiomError` raise). 9 sites in 3 files. Kinds added: `timeout`, `inconsistent`, `inference`; the 3 missing-package `RuntimeError` become `ImportError`; the Java ones `inference`. `starlayer-reasoning/pyproject.toml` must require the core release that has `starlayer.errors`; the SHACL note in `shacl/engine/api.py` ("propagate") is updated.
- Tests: `starlayer-reasoning/tests/test_timeout.py`, `test_infer_owl_dl.py`, `test_infer_owl_dl_rustdl.py`, `test_entailment_direct.py`, `test_owl_dl_on_pyoxigraph.py`, `test_infer.py`; in the core tests: `ReasoningTimeoutError` named in 7 files, `InconsistentOntologyError` in 5 (incl. `tests/graph/entailment`), and the `pytest.raises(RuntimeError)` ones around OWL-DL (5 files outside shacl/ use `RuntimeError`).
- Guides: `02f-owl-dl-reasoning` cells `ae0d6817` (md), `b87b0ce5`; `03c-sparql-entailment` `a1c2e304` (md); `appendix-b2-dl-reasoning-examples` `8447c470`, `319385b0`, `181958f0` (md), `497e70e3`, `0cfb6b13`.
- Size: small; the pickling of `ExecutionError` across the child process is the only technical risk (`_timeout.py` sends a tagged tuple, not the exception).

### Stage 2: SPARQL text (parser, SQE, conformance) and the query/update boundary

- Raise sites: `sparql/parse_sparql.py` 8 `SparqlSyntaxError` + 2 `SQEValidationError` (class `SparqlSyntaxError` defined `:127`), `sparql/sqe/to_rdf.py` 1 `SQEValidationError` (classes `SQEError`, `SQEValidationError` at `:18,26`), `sparql/srl.py` 1 `SparqlSyntaxError`, `graph/execution/version_conformance.py` 2 via `error_class`, `graph/execution/update_scope.py:165` 1 `SyntaxError`. 15 sites, plus the 4 `RecursionError` conversions in `parse_sparql.py:1803,1827,2179,2200` that become `nesting` (only when the stage touches them; they are `ExecutionError(kind="nesting")` from the start of this stage).
- Boundary (part 4): `graph/execution/run.py` `store.query` (3 call sites) and `store.update` (2), the wrap of `SyntaxError` to `FormatError(kind="sparql")` and `RuntimeError` to `ExecutionError(kind="query")`, with the existing "projection" message test kept inside (`run.py:55,157`).
- Catch clauses: `sparql/check.py:75,80,125,138,140,142` (the last one: narrow to `FormatError`, `ExecutionError` and `NotImplementedError`), `sparql/sqe/rewrite.py:68`, `sparql/sqe/entailment.py:150`, `sparql/sqe/to_rdf.py:121`, `sparql/srl.py:443`, `shacl/meta_shapes.py:405` (`(SparqlSyntaxError, ValueError)` becomes `FormatError`), `graph/execution/update_scope.py:164`.
- Tests: `SparqlSyntaxError` named in 11 files, `SPARQL12ConformanceError` 4, `SQEValidationError` 2, and the 11 non-SHACL files with `pytest.raises(SyntaxError)` (the engine's). Directories: `tests/sparql/*` (including `test_parse_sparql.py` and `test_parse_sparql_semantics.py`, which read `.pos` / `.col` / `.why`) and `tests/graph/*`.
- Guides: `03a-sparql-12-queries` `f6a58c6a` (`except ValueError` around a VERSION error), `03b-preparing-extending-checking-queries` `32f5f2c6` (a syntax error from `StarQuery` caught as `ValueError`) and `e79f89e7` (`except RuntimeError` on a missing function), `06b-sparql-query-as-rdf` `5034b553` (md), `bf561c0b` (md), `06ad6b5e` (`SQEValidationError`).
- Size: medium (about 16 sites, 12 clauses, one real behaviour change at `query()` / `update()`).

### Stage 3: SRL

- Files: `sparql/srl.py` (`SRLError` `:174`, `SRLParseError` `:185`, `SRLImportError` `:194`, `SRLDecodeError` `:418`; raises: 4 `SRLDecodeError`, 2 `SRLParseError`, 1 `StratificationError`, 2 `SRLImportError`, 3 `NotImplementedError` render gaps that go to stage 6), `sparql/parse_srl.py` (5 via `_srl_error`, `RecursionError` `:315`), `sparql/_srl_ast.py` (1 `SRLParseError`, and the `infer(schema=)` crossing at `:533-545`), `sparql/srl_eval.py` (class defs `:54,61,68`; raises 1 `SRLImportsNotSupportedError`, 3 `SRLEvalError`, 1 `StratificationError`; handlers `:324,377,629,634,1095,1168,1268` keep catching the engine's own `RuntimeError`), `sparql/srl_semantic_checks.py:138`. 20 sites in 5 files.
- Catch clauses: `srl.py:288,548,550,758,767`.
- Tests: `SRLParseError` in 13 files (14 `pytest.raises`), `SRLError` 6, `StratificationError` 6, `SRLImportsNotSupportedError` 2, `SRLImportError` 1, plus `tests/packaging/test_core_without_rdflib.py:384` (`test_srl_errors_work_without_rdflib`).
- Guides: `04a-srl-running-rule-sets` `e1000006` (md), `c0a10006`, `e1000007` (md), `06aa75fa`, `d9a10006`, `a6b6c602`; `04b-srl-more-features` `d9a1000f`, `n12-group-md` (md); `06c-srl-sparql-rules-as-rdf` `a8f39e1c` (md), `c313022c` (md), `ad058c1c`.
- Crossing: `infer(schema=)` documents which of `FormatError`, `ExecutionError`, `ShapeError` escape and a test pins it (the three families are now under one base).
- Size: medium-large (20 sites, 5 clauses, 21 tests, 11 cells).

### Stage 4: RDF documents and terms (the `parse()` boundary)

- `graph/core.py` (`parse` boundary `:519-534` including the lazy iteration inside `store.extend`, `:381,386` list errors), `graph/rdflist.py` (`:44,48`, handler `:71`), `graph/ntversion.py:52`, `graph/terms.py` (`:150,177,183,185`; the existing `SyntaxError` catch at `:182` goes), `graph/interop.py` (`BasicEncodingError` `:75`, 13 raises), `sparql/triple_term.py` (`InvalidTripleTermError`, `:16`, 1 raise). About 23 sites in 6 files.
- Boundary `parse()`: pyoxigraph's `SyntaxError` has `lineno` / `offset` here (run: `(1, 1)` for a Turtle error), used for `line` / `col`; an unsupported named-graph document stays `ValueError` for the wrong target (the single string match `core.py:532` stays and is noted for a later pre-check by format).
- Tests: `BasicEncodingError` 1 file, `InvalidTripleTermError` 2, and the `pytest.raises(SyntaxError)` ones of `tests/graph` that test `parse()`; `tests/graph/test_*parse*`, `test_terms*`, `test_rdf_list*`, `test_interop*` (names not individually checked).
- Guides: none name these classes; the cell `02c-graph-content` `0e389edf` catches `(ValueError, TypeError)` around `to_python` (a bad lexical form, `terms.py`; check the final class).
- Size: medium (23 sites, one boundary).

### Stage 5: Manchester and OWL-in-RDF

- `graph/manchester/errors.py` (class removed), `graph/manchester/parser.py` (3 raises, handlers `:231,550,563,618,642,652,884,1692`), `graph/manchester/serializer.py` (14 `ValueError`, 2 `AssertionError`), `starontology/manchester/__init__.py` (1 `ManchesterSyntaxError`, 5 `ValueError`, 6 `AssertionError`), the export in `graph/manchester/__init__.py`. About 31 sites in 4 files; the ones that are fixed by a different argument stay `ValueError`.
- Tests: `ManchesterSyntaxError` in 6 files (21 `pytest.raises`), mostly `tests/graph/manchester` and `tests/starontology`.
- Guides: `06a-manchester-syntax` `709876ac` (md), `a4e85f77`.
- Size: medium.

### Stage 6: run failures, unsupported, internal, the rest

- `graph/endpoint.py` (`EndpointError` `:47`, 5 raises, rebased on `StarLayerError`; `ValueError` `:158,242` become `unsupported`), `graph/rdfc_native.py` (2 `limit`, class `:37`; handler `graph/bnodes.py:61`), `sparql/sqe/entailment.py` (5 `EntailmentRewriteError` + 1 `NotImplementedError`), `sparql/sqe/to_text.py` (1 `SqeTextTooDeepError`, 5 `NotImplementedError`), `sparql/sqe/expr_text.py` (3), `sparql/srl.py` (3), `sparql/parse_sparql.py:1965`, `sparql/relevant.py` (2 `ValueError` `:120,122`, which the SHACL read recorder catches at `shacl/engine/reads.py:144`: must change together), `graph/pretty.py` (1 `AssertionError`), `graph/interop.py` (`:345,430`), the `AssertionError`s not done in stage 5, `srl_eval.py:704`, `srl_semantic_checks.py:138`, the two `shacl/engine/rules.py` limit sites (question 10), and `core.py:721` to `ValueError`. About 40 sites in 14 files.
- Tests: `EndpointError` 1 file, `CanonicalizationComplexityError` 4, `EntailmentRewriteError` 3, the `NotImplementedError` tests (6 non-SHACL files, of which the 13 wrapper refusals do not change).
- Guides: `03c-sparql-entailment` `7d8d5b33` (`except (NotImplementedError, ValueError)`), `07a-serialization-formats` `ba3d53f0` (`except OSError`, source not traced) and `07b-backend-graph-databases` `252791c5` (`except OSError`, unchanged if question 8 is kept).
- Close-out docs: `AGENTS.md:45`, `graph/CLAUDE.md`, `sparql/CLAUDE.md`, `shacl/CLAUDE.md`, `docs/design/future_enhancements.md:489` (close the entry), a release note listing old name to class and kind; the generated docs and the code KG are rebuilt after the last stage, not per stage.
- Size: medium-large but dispersed.

### Totals

Raise sites: stages 1+2+3+4+5+6 = 9 + 15 + 20 + 23 + 31 + 40 = about 138, plus the SHACL moves; catch clauses 17; boundary points 5. Compared with the audit's "125 in about 35 files": the extra is the `unsupported` / `internal` conversions and the `RecursionError` handlers it listed in other buckets. Files touched: about 33 source files, plus 40 import-line edits in stage 0.

### Tests that must change (counts, non-SHACL unless stated)

- By old class named (files): `SparqlSyntaxError` 11, `SRLParseError` 13, `StratificationError` 6, `SRLError` 6, `ManchesterSyntaxError` 6, `ReasoningTimeoutError` 7, `InconsistentOntologyError` 5, `SPARQL12ConformanceError` 4, `CanonicalizationComplexityError` 4, `EntailmentRewriteError` 3, `SQEValidationError` 2, `SRLImportsNotSupportedError` 2, `InvalidTripleTermError` 2, `BasicEncodingError` 1, `EndpointError` 1, `SRLImportError` 1; 52 distinct files outside `shacl/` (graph 45 + sparql 32 combined with builtin-class files below, see next bullet).
- By builtin class asserted around a call that changes class: `pytest.raises(SyntaxError)` 11 files, `RuntimeError` 5, `NotImplementedError` 6, `ValueError` 42 (most are bad arguments and do not change). The union of files that name an old class or assert `SyntaxError` / `RuntimeError` / `NotImplementedError` / `ValueError` outside SHACL is 90 (graph 45, sparql 32, reasoning 5, starontology 4, kg 2, packaging 1, repo 1); my estimate of files that actually change is 55 to 65 (the audit said 64).
- SHACL tests: `tests/shacl/unit/test_error_classes.py` (stage 0b), the 22 import-line files (stage 0), and the tests that assert `kind == "rule"` for the two limit sites (stage 6).
- Existing tests that guard step C and keep applying: `tests/sparql/unit/test_error_narrowing_clauses.py`.

## 4. Public-API effect

What a caller must write after the change, per call. "Before" is what the code raises at HEAD (the ones marked "run" were executed).

| Call | Failure | Before | After |
|---|---|---|---|
| `graph.query(text)` | malformed query | `SyntaxError` (pyoxigraph, run) | `FormatError` kind `sparql` (`line`/`col` `None`: pyoxigraph gives them only in its message for queries, run) |
| `graph.query(text)` | evaluation failure, unknown function | `RuntimeError` (run: "The custom function ... is not supported") | `ExecutionError` kind `query` |
| `graph.query(entailment=bad)` | bad value | `NotImplementedError` (`core.py:721`) | `ValueError` (the same as `infer()`) |
| `graph.query(entailment=<known IRI the query rewrite lacks>)` | unsupported regime | `NotImplementedError` / `EntailmentRewriteError` | `ExecutionError` kind `unsupported` |
| `graph.update(text)` | malformed or failed | `SyntaxError` / `RuntimeError`; `scope_update`: `SyntaxError` rebuilt from `SparqlSyntaxError` | `FormatError("sparql")` / `ExecutionError("query")`; scope refusals stay `ValueError` |
| `graph.parse(...)` | malformed document | `SyntaxError` (run) | `FormatError` kind `rdf` (`line`/`col` set from pyoxigraph) |
| `graph.parse(...)` | document has named graphs, target is a graph | `ValueError` (by message match) | `ValueError` (unchanged, bad target) |
| `graph.serialize(format=...)` | format cannot hold named graphs (run: pyoxigraph `ValueError`) | `ValueError` | `ValueError` (a bad argument combination; unchanged) |
| `graph.infer(entailment=...)` | bad argument | `ValueError` | `ValueError` |
| `graph.infer(OWL-Direct)` | inconsistent / timeout / crash | `RuntimeError` subclasses | `ExecutionError` kind `inconsistent` / `timeout` / `inference` |
| `graph.infer(OWL-Direct)` | package missing / Java missing | `RuntimeError` | `ImportError` / `ExecutionError("inference")` |
| `validate()` with OWL-Direct inference | same | `RuntimeError` subclasses escape | `ExecutionError`; `except ExecutionError` now catches all |
| `parse_sparql()`, `parse_sparql_update()`, `check_query()`, `sqe_parse_to_tree()` | malformed | `SparqlSyntaxError` / `SQEValidationError` (both `ValueError`) | `FormatError("sparql")` (the same `pos`, `line`, `col`, `why`); nesting: `ExecutionError("nesting")` |
| `StarQuery(text)` | malformed | `ValueError` family | `FormatError("sparql")` |
| `parse_ruleset()`, `RuleSet.infer()`, `RuleSet.query()` | wrong text / tree / stratification / bad head / bad DATA | `SRL*Error`, `StratificationError` (all `ValueError`) | `FormatError("srl")`; imports: `ExecutionError("import")` |
| `RuleSet.infer(schema=)` | a wrong schema / validation failure | `ShapeError` or `ExecutionError` beside SRL's classes | the same classes; all are `StarLayerError` and documented |
| Manchester parse / serialize | malformed | `ManchesterSyntaxError` (`SyntaxError`) / `ValueError` | `FormatError("manchester")` / `FormatError("owl")` |
| `parse_term()`, `terms.literal` lexical | not a term | `ValueError` / `SyntaxError` | `FormatError("term")` (bad *argument types* stay `TypeError`) |
| `canonical_hash` / `StarLayerGraph.canonicalize` | too symmetric | `CanonicalizationComplexityError` (`RuntimeError`) | `ExecutionError("limit")` |
| `Endpoint.query()` etc. | HTTP / network failure | `EndpointError` (`OSError`) | `EndpointError` (unchanged for `except OSError` and `except EndpointError`) |
| Wrapper method not implemented | | `NotImplementedError` | `NotImplementedError` (13 sites, unchanged) |
| `graph.value()` several matches | | `ValueError` | `ValueError` (unchanged) |
| unwritable / unrenderable tree | | `NotImplementedError`, `ValueError`, `AssertionError` | `ExecutionError("unsupported")` or `("internal")` |

Catch-all: `except StarLayerError` for everything the library raises on purpose; builtin `TypeError` / `ValueError` / `ImportError` / `NotImplementedError` remain outside it by design.

### The pyoxigraph boundary points (to wrap, all `from` the original)

1. **query**: `graph/execution/run.py:52,54` (widening path) and `:156,167` `store.query(...)`; raises `SyntaxError`, `RuntimeError` (run).
2. **update**: `graph/execution/run.py:199,211` `store.update(...)`; the same two classes (run). `:117` and `graph/execution/union.py:99-117` are internal helpers on a scratch graph, left raw.
3. **parse**: `graph/core.py:519` `ox.parse(...)` and the iteration at `:524-526` (`store.extend(lexical.watch(parser, ...))`), where pyoxigraph raises `SyntaxError` lazily; the existing handler is `core.py:532`.
4. **serialize**: `graph/core.py:614,685` `ox.serialize(...)` and `graph/interop.py:434` (pyoxigraph raises `ValueError` for named graphs in a triple format, run; the library already checks first, so the wrap is a safety net for the argument error: it stays `ValueError`).
5. **endpoint responses**: `graph/endpoint.py:107,109,118,121` (`ox.parse_query_results`, `ox.parse`; `SyntaxError` on garbage, run), wrapped into `EndpointError` (which `endpoint.py:89,92` already does for HTTP and URL errors; `HTTPException` and `ConnectionResetError` are not caught, not checked whether they occur).

Not boundary points, but touched: `graph/terms.py:181` (`ox.parse` of a term, the handler `:182` converts today), engine-internal calls in `srl_eval.py` (`store.update` / `store.query` at `:1050,1094,1137,1166,1267`, which keep catching `RuntimeError` on purpose and re-raise by message), and SHACL's `sparql_support.py:181,208,289`, already converted in step C.

### Workbench (read-only grep of `../graph-workbench` at `fa750ed`)

- `except SyntaxError`: none, in `src/`, `tests/` and `tools/`.
- `except ValueError` in `src/`: about 100 clauses; the library-facing ones I found by a try-body scan:
  - term and lexical conversion that will stop being `ValueError`: `_starlayer.py:215` (`_to_python`), `_starlayer.py:1179,1193` (`_parse_term`, which re-raises as its own `ValueError`), `edits.py:183`, `nodeexpr.py:291`, `web/app.py:1466,1795` (`parse_term`).
  - `update()`: `edits.py:1345` (`sl.` triples `update`; this is a `set.update`, not a graph update: no change, listed because the scan flagged it).
  - parse: `web/app.py:668` (`turtlediff.parse`, which itself converts `Exception` to `ValueError` at `turtlediff.py:231-232`: unaffected).
  - others not traced to a library call (about 85, mostly `edits.py` and `web/app.py`: their own validation); `cli.py:38` `except (OSError, ValueError)` around `Workspace.load(...)`, which loads files with `graph.parse`: a Turtle error from there is a `SyntaxError` today (not caught by it) and a `FormatError` after (still not caught), so no change; `_starlayer.py:612` `except ValueError` around `_members(...)` (not traced).
- `except NotImplementedError`: `evaluation.py:119` around `sl.walk_path(...)` (`_starlayer.py:399`; the class the path code raises was not traced).
- `except RuntimeError`: none in `src/`.
- `except Exception` / bare around StarLayer calls (33 in `src/`, so they keep working): `_starlayer.py:1107,1565` (`apply_rules`), `edits.py:415`, `exprtree.py:232`, `graphstore.py:68`, `nodeexpr.py:418,445,478`, `shapebuilder.py:103`, `turtlediff.py:231`, `validation.py:287`, `web/app.py:553`, `web/evaluate.py:130,132`, `web/extract.py:167`, `web/validate.py:191`. They already re-raise as the workbench's own `ValueError` / `GraphError` / `EditError`.
- Imports of StarLayer error classes: `_starlayer.py:34` (`ShapeError`), `:713,726` (`MetaShaclError`), `:330,358` (`except ShapeError`), `:316-319`; no other class is imported. All keep working through the `starlayer.shacl` re-export.
- Tests: `tests/test_paths.py:83` expects `ValueError` from a `ShapeError` (stage 0b); `tests/test_shapes_tab.py:5054` `except ValueError` (not traced).
- Not determined: whether any of the ~85 untraced `except ValueError` clauses sits around a StarLayer call that will now raise `FormatError` (the way to know is to run the workbench tests against each stage).

## 5. Risks and verification

| Risk | Stage | How it is caught |
|---|---|---|
| A clause that relied on a `ValueError` base now misses (`except ValueError` around `relevant_triples` at `shacl/engine/reads.py:144`, `check.py:140`, `meta_shapes.py:405`, workbench) | 0b, 2, 6 | Grep and run `tests/shacl`, `tests/sparql`; workbench tests run once per stage |
| `ExecutionError` / `FormatError` lost across the reasoning child process or pickling | 1 | Round-trip test of `pickle` and `copy` for every class (`kind`, `context`, position fields) |
| A typo in a kind | all | `__init__` rejects unknown kinds; AST test checks every `kind="..."` literal against `KINDS` |
| The pyoxigraph message test "projection" (`run.py:55,157`) and "triple term that is not a valid" (`srl_eval.py:377`) depends on engine wording | 2, 3 | Keep one shared helper per message; a test per message that fails on an engine upgrade (audit said not checked whether one exists; I did not check either) |
| Two classes for the same cause remain (`query()` versus `parse_sparql()`) | 2 | A table test: for 6 malformed inputs (query, update, `StarQuery`, `parse_sparql`, `check_query`, `sqe_parse_to_tree`) all raise `FormatError` kind `sparql` |
| Lazy parse errors escape the wrap (`ox.parse` iterates later) | 4 | A test with a Turtle error in the last line of a large document |
| `FormatError` and `ShapeError` overlap | 3, 5 | Rule in `AGENTS.md`: a shapes graph (and a rules graph) is `ShapeError`; SRL rule sets are `FormatError("srl")` |
| One-time break for every caller | 6 | Release note old to new; question 7 |
| `kg` and `starlayer-reasoning` versions | 1 | `pyproject.toml` pins the core minimum that has `starlayer.errors` |

New tests (contract, written before or in stage 0 and tightened per stage; I wrote none now):

1. **Class tree**: every `Exception` subclass defined in `packages/*/` source, found by AST, is a subclass of `StarLayerError`, except an allowlist (`_NotComputable`, `_InvalidInstance`, `_Err`, and warnings); `StarLayerError` is not a subclass of `ValueError`, `SyntaxError`, `RuntimeError`, `OSError`; `EndpointError` is the only class with `OSError`.
2. **No builtin raises**: an AST scan of the package for `raise X(...)` where `X` is `RuntimeError`, `AssertionError`, `SyntaxError`, `OSError`, `Exception`, or a `ValueError` / `TypeError` / `NotImplementedError` that is not in `tests/repo/error_allowlist.json` (file, function, class, count). The allowlist starts at the bad-argument sites (about 96 of the audit's bucket plus 13 wrapper refusals) and shrinks only; each stage removes entries. `AttributeError`, `KeyError`, `StopIteration` are allowed only inside dunder methods (`__getattr__`, `__getitem__`, `__next__`, `__setattr__`, `__delattr__`).
3. **No broad catches**: bare `except:` and `except Exception` / `BaseException` banned except an allowlist with a comment on the line (today 18 in the tree: 1 outside `shacl/`, `srl.py:758`, the user's `imports_loader`; 17 in `shacl/`: `engine/expressions.py:636`, `fidelity.py:57,62,80`, `graphs.py:27`, `report.py:141`, `rules.py:527,567`, `sparql_support.py:181,208`, `text.py:62,157,261,387`, `meta_shapes.py:155`, `ui/widget_selection.py:732`, `validator.py:681`: each to be justified or narrowed when the test is added).
4. **Kinds**: every `kind=` literal at a call to `ExecutionError(...)` / `FormatError(...)` is in the class's `KINDS`; every kind in `KINDS` is raised at least once (so no dead kind).
5. **`errors.py` imports only the standard library** (the cycle proof of part 1).
6. **Boundary table test** (stage 2) and **cause-not-path table**: the same malformed SPARQL, the same nesting depth, the same bad rule set give the same class and kind from every entry point.

Per-stage verification (targeted, per the standing rule; the full suite only when you ask): stage 0 `tests/shacl/unit/test_error_classes.py`, `tests/packaging`, `tests/repo`, and `tests/shacl` import-only checks; stage 0b `tests/shacl`; stage 1 `starlayer-reasoning/tests` and `tests/graph/entailment`; stage 2 `tests/sparql`, `tests/graph/execution*`, `tests/sparql/unit/test_error_narrowing_clauses.py`; stage 3 `tests/sparql` (SRL) and `tests/packaging/test_core_without_rdflib.py`; stage 4 `tests/graph` (parse, terms, lists, interop); stage 5 `tests/graph/manchester`, `tests/starontology`; stage 6 `tests/graph`, `tests/sparql`, `tests/shacl/unit/test_error_classes.py`. Notebooks per stage: `scripts/check_notebook_links.py` and the opt-in `pytest --notebooks` for the changed notebooks.

## 6. Size and release

| Stage | Sites | Files | Clauses | Test files | Cells | Effort |
|---|---|---|---|---|---|---|
| 0 | 0 (moves) | about 45 (imports) | 0 | 22 | 0 | small, mechanical |
| 0b | 0 | 3 + a few | about 1 | 3 to 6 | 1 | small |
| 1 reasoning | 9 | 3 | 4 | 12 | 9 | small |
| 2 SPARQL text + boundary | about 16 | 9 | 12 | 20 | 6 | medium |
| 3 SRL | about 20 | 5 | 5 | 20 | 11 | medium to large |
| 4 RDF documents, terms | about 23 | 6 | 3 | 8 to 10 | 1 | medium |
| 5 Manchester / OWL | about 31 | 4 | 8 | 7 | 2 | medium |
| 6 the rest | about 40 | 14 | 4 | 8 to 10 | 3 | medium to large |

Total roughly 140 sites, 17 clauses, 5 boundaries, about 60 test files, 8 + 5 notebooks. The audit's "about a day of mechanical edits per subsystem" fits: about 5 to 6 working days if the tests are fixed with each stage.

**Recommendation: do it in stages (separate green commits) and release once.** Reasons: the sites of one cause must change together (stage 2 before stage 3 changes nothing for SRL callers, but `graph.query()` and `parse_sparql()` change in the same commit); a partial release leaves the library with three families again (the state the audit complained about) and breaks callers more than once; and no alias is allowed, so a caller's break cannot be softened. If a stage is deferred, the later stages still leave the tree green, but the release waits. Start with stage 0 and 1 (no caller inside the library for stage 1) to prove the module, then 2.

## 7. What I could not determine

- Which of the ~85 untraced `except ValueError` clauses in the workbench wrap a StarLayer call whose class changes: needs a run of the workbench tests per stage.
- The exact list of test files that change (55 to 65 estimated): needs running each slice after a stage.
- Whether the "projection" and "triple term that is not a valid" message tests (`run.py:55,157`, `srl_eval.py:377`) have a test that fails on a pyoxigraph wording change.
- Which of the 13 plain-`ValueError` "unsupported" sites of the audit are fixable by a different argument (my split of about 7 versus 6 is a read of the messages, to be confirmed per site in stage 6), and the final site lines of the `manchester/serializer.py` `owl` group (the audit's line numbers predate the step-C edits; the file was not re-read here).
- Whether `07a` cell `ba3d53f0` (`except OSError` around a JSON-LD serialize) catches a library or a pyoxigraph error.
- `RuleResult.failures` as structured data is left out of step A.
