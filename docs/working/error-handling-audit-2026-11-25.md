# Error handling outside SHACL: audit and proposal (2026-11-25)

Read-only audit of every `raise` and every `except` under `packages/` outside `starlayer/shacl/` (library, `starlayer-reasoning`, `starlayer-kg`), at HEAD `07ae07d5`. It answers the "Error handling in SHACL, and uniformity across StarLayer" entry in `docs/design/future_enhancements.md`. No code, tests, notebooks or `future_enhancements.md` were changed.

Method: the sites were found with a Python `ast` walk (297 `raise` statements, 77 `except` handlers in 100 files; `tests/`, `benchmarks/` and `shacl/` skipped). The classification below is mine, by reading the messages and the surrounding code; the group counts are therefore exact for the walk and a judgement for the grouping. Behaviour claims marked "verified" were run against the installed library. Not covered: `scripts/`, `tools/`, `docs/` code, the notebooks' own try/except, and the exceptions that pyoxigraph, rdflib or owlready2 raise and the library lets through (they are not `raise` sites; see part 4, row 1).

## Summary (half a page)

1. **Outside SHACL the library has 21 error classes in four unrelated families, and no common base.** `SparqlSyntaxError`, `SRLError` (and 6 subclasses), `SQEError` (and 1), `SqeTextTooDeepError`, `InvalidTripleTermError`, `BasicEncodingError` and `SPARQL12ConformanceError` derive `ValueError`. `ManchesterSyntaxError` derives `SyntaxError`. `EndpointError` derives `OSError`. `ReasoningTimeoutError`, `InconsistentOntologyError` and `CanonicalizationComplexityError` derive `RuntimeError`. `EntailmentRewriteError` derives `NotImplementedError` (itself a `RuntimeError`). Only `EndpointError` and `ManchesterSyntaxError` are exported from a package `__init__`; none of the 14 `sparql/` and reasoning classes is.
2. **The "plain ValueError only for a bad argument" rule does not hold.** Of 92 `ValueError` raises, about 55 are not a bad argument at a call's entry: 20 are bad document or data (malformed RDF list, a Manchester tree or OWL-in-RDF pattern, a term text), about 13 are an unsupported feature, and one is an ambiguous lookup. Worse, 14 custom classes are `ValueError` subclasses, so any `except ValueError` (the library has 12, plus tuples) can swallow a syntax error, a stratification failure or an SRL evaluation failure. This is the same risk SHACL's `ExecutionError` was built to avoid.
3. **The same problem is raised as different classes.** A malformed SPARQL query is a builtin `SyntaxError` from `graph.query()` and `graph.update()` (pyoxigraph's, verified) but `SparqlSyntaxError(ValueError)` from `parse_sparql()` and `check_query()`, and `SRLParseError` from SRL. "Nested too deeply" is five different classes. An unsupported entailment regime is `NotImplementedError` from `query()` and `ValueError` from `infer()` (verified). A missing optional package is `ImportError` in the graph layer and `RuntimeError` in the reasoning package.
4. **Swallowing clauses.** About 12 handlers could hide a different failure than the one meant (part 3). The worst are `srl_eval.py:619,624` (any `Exception` from SPARQL aggregation becomes "no value"), `srl_eval.py:1085,1156,1254` (any `RuntimeError` from the engine becomes "use the slow path"), `_timeout.py:139,147` (`except Exception` around a queue read), and the broad tuples in `sqe/rewrite.py:68` and `sqe/entailment.py:150` (a bug such as `AttributeError` becomes "return the text unchanged" or "unsupported query").
5. **SHACL crosses into the rest of the library unwrapped, both ways.** SRL checked inference (`infer(schema=...)`, `_srl_ast.py:533-545`) lets `ShapeError` and `ExecutionError` escape beside SRL's own errors; SHACL's OWL-Direct inference lets `InconsistentOntologyError` and `ReasoningTimeoutError` escape (documented in `shacl/engine/api.py`). A caller needs to know three families to catch "inference failed". The error classes live in `shacl/engine/plan.py`, and `graph/` and `sparql/` already import from `starlayer.shacl.engine.*` for terms, so a library-wide base would have to be moved out of `shacl/`.
6. **Recommendation: scheme A, done in the order C then A.** One library base `StarLayerError` in a new dependency-free module; beneath it SHACL's `ShapeError` tree unchanged, one `ExecutionError` with a `kind` (SHACL's kinds plus a few new ones), and one `FormatError` with a `kind` for bad documents. 21 classes become 3 new public ones. About 125 raise sites, 12 catch clauses and 5 pyoxigraph boundary points change, in about 35 files, with about 64 test files and about 13 guide mentions to follow. Do the cheap, independent step first: fix the swallowing clauses and state the ValueError rule (about 12 sites, 6 files). Cost is real: it breaks every caller who catches `SyntaxError` or `ValueError` for a bad query or document, and with no aliases that is a clean break in one release.

## 1. Inventory

### Classes defined, by subpackage

"Exported" means in a package `__init__` or `__all__`; "guides" is the number of `docs/guides` notebooks that mention the name; "test files" is the number of test files that mention it (all of `packages/*/tests`, so it includes SHACL tests).

| Subpackage | Class | Base | Raised at (file, count) | Exported | Guides | Test files |
|---|---|---|---|---|---|---|
| graph | `EndpointError` | `OSError` | `endpoint.py` 5 (+ `status` attribute) | yes (`graph/__init__.py`) | 0 | 1 |
| graph | `SPARQL12ConformanceError` | `ValueError` | `execution/version_conformance.py` 2 (via `error_class`); caught in `sparql/check.py` | no | 1 | 4 |
| graph | `BasicEncodingError` | `ValueError` | `interop.py` 13 | no | 0 | 1 |
| graph | `ManchesterSyntaxError` | `SyntaxError` | `manchester/parser.py` 3, `starontology/manchester/__init__.py` 1 | yes (`graph/manchester`) | 1 | 7 |
| graph | `CanonicalizationComplexityError` | `RuntimeError` | `rdfc_native.py` 2 | no | 0 | 4 |
| sparql | `SparqlSyntaxError` | `ValueError` | `parse_sparql.py` 8, `srl.py` 1 | no | 0 | 11 |
| sparql | `InvalidTripleTermError` | `ValueError` | `triple_term.py` 1 | no | 0 | 2 |
| sparql | `SQEError` / `SQEValidationError` | `ValueError` / `SQEError` | `to_rdf.py` 1, `parse_sparql.py` 2 | no | 1 | 2 |
| sparql | `SqeTextTooDeepError` | `ValueError` | `sqe/to_text.py` 1 | no | 0 | 0 |
| sparql | `EntailmentRewriteError` | `NotImplementedError` | `sqe/entailment.py` 5 | no | 0 | 2 |
| sparql | `SRLError` | `ValueError` | base only | no | 0 | 6 |
| sparql | `SRLParseError` | `SRLError` | `srl.py` 2, `_srl_ast.py` 1, `parse_srl.py` 5 (via `_srl_error`) | no | 3 | 14 |
| sparql | `SRLDecodeError` | `SRLError` | `srl.py` 4 | no | 0 | 0 |
| sparql | `SRLImportError` | `SRLError` | `srl.py` 2 | no | 1 | 1 |
| sparql | `SRLEvalError` | `SRLError` | `srl_eval.py` 3 | no | 0 | 0 |
| sparql | `StratificationError` | `SRLEvalError` | `srl.py` 1, `srl_eval.py` 1 (raised at parse time too, `srl.py:290`) | no | 2 | 6 |
| sparql | `SRLImportsNotSupportedError` | `SRLEvalError` | `srl_eval.py` 1 | no | 1 | 2 |
| sparql | `SRLUnresolvedImportsWarning` | `UserWarning` | a warning, not raised | no | 1 | 1 |
| sparql | `_NotComputable`, `_InvalidInstance` | `Exception` | private control flow (11 + 1) | private | - | - |
| starontology | none | - | borrows `ManchesterSyntaxError`, plain `ValueError`, `AssertionError` | - | - | - |
| reasoning | `ReasoningTimeoutError` | `RuntimeError` | `_timeout.py` 2 | no (`__all__` lists two functions) | 0 | 7 |
| reasoning | `InconsistentOntologyError` | `RuntimeError` | `owl_dl.py` 1, `owl_dl_rustdl.py` 1 | no | 4 | 5 |
| kg | none | - | 1 `FileNotFoundError` | - | - | - |

Totals: 20 public-ish classes plus the 2 private ones, in 3 packages. For comparison SHACL has `ShapeError`, `ShapeCompileError`, `MetaShaclError` and `ExecutionError` (4), all exported from `starlayer.shacl`.

### Raise sites by class and subpackage (297 total)

`graph` includes `graph/manchester`, `graph/execution`, `graph/entailment`, `graph/rdflib_model`; `sparql` includes `sparql/sqe`.

| Class raised | graph | sparql | starontology | reasoning | kg / top | Total |
|---|---|---|---|---|---|---|
| `ValueError` | 81 | 4 | 5 | 2 | 0 | 92 |
| `TypeError` | 29 | 7 | 1 | 0 | 0 | 37 |
| `NotImplementedError` (incl. `raise NotImplementedError` without call) | 12 | 13 | 0 | 0 | 0 | 25 |
| `AttributeError` | 10 | 3 | 1 | 0 | 1 | 15 |
| `AssertionError` | 5 | 0 | 6 | 0 | 0 | 11 |
| `RuntimeError` | 0 | 0 | 0 | 4 | 0 | 4 |
| `KeyError`, `ImportError`, `FileNotFoundError`, `StopIteration`, `SyntaxError` | 9 | 0 | 1 | 0 | 1 | 11 |
| bare `raise` / `raise error` (re-raise) | 5 | 5 | 0 | 0 | 0 | 10 |
| library classes (table above), by raise | 25 + 7 `_refuse`/`refuse` helpers (ValueError) | 41 + 11 `_NotComputable` + 1 `_InvalidInstance` | 1 | 5 | 0 | about 100 |

(The library-class row counts raise sites of classes defined in the previous table; `_refuse`/`self.refuse` return a `ValueError`, so they are counted under `ValueError` in the classification below.)

## 2. Classification of every raise site outside `shacl/`

Buckets (counts are raise sites; 297 in total):

| Bucket | graph | sparql | starontology | reasoning | kg/top | Total |
|---|---|---|---|---|---|---|
| Bad argument (value or type at a public call) | 87 | 6 | 1 | 2 | 0 | **96** |
| Bad document or data (parse, encode, decode, malformed term or tree) | 37 | 27 | 4 | 0 | 0 | **68** |
| Unsupported feature or configuration | 27 | 15 | 0 | 0 | 0 | **42** |
| Failure while running (query, entailment, inference, backend, timeout, limit) | 7 | 12 | 0 | 5 | 0 | **24** |
| Python protocol (`__getattr__`, `__getitem__`, iterator end, immutability) | 14 | 3 | 2 | 0 | 1 | **20** |
| Internal assertion (a bug) | 5 | 2 | 6 | 0 | 0 | **13** |
| Private control flow (`_NotComputable`, `_InvalidInstance`) | 0 | 12 | 0 | 0 | 0 | **12** |
| Re-raise of a caught error | 5 | 5 | 0 | 0 | 0 | **10** |
| Missing optional package or environment | 3 | 0 | 0 | 4 | 1 | **8** |
| Wrong state of an object | 0 | 1 | 2 | 0 | 0 | **3** |
| Ambiguous lookup | 1 | 0 | 0 | 0 | 0 | **1** |

### 2.1 Bad argument (96): plain `ValueError`/`TypeError` is right

These stay as they are. The group is uniform: a check at the entry of a public call, a message that names the argument. 34 `TypeError` for a wrong type, about 62 `ValueError` for a wrong value. Examples:

- `graph/core.py:147` `ValueError('parse() needs exactly one of data=, source= or file=')`; `:574` `bnode_labels must be None or 'short'`; `:731` `recompute must be one of ['always', 'never', 'onChange']`.
- `graph/entailment/infer.py:168-194` eight checks of `mode`, `entailment`, `engine`, `timeout`, `target_graph` (also `imports.py:47-93`, `cache.py:131`: the same checks repeated, see part 4).
- `graph/inputs.py:45,49` `TypeError('an rdflib graph ... is not accepted ... convert it with StarLayerGraph.from_rdflib')`.
- `graph/bnode_align.py:209-213`, `graph/rdfc_native.py:62,68`, `graph/terms.py:89-94` (`literal()` with lang and datatype), `reasoning/owl_dl_delta.py:24`.
- `graph/ox_store.py` 7 `_refuse(...)` and `execution/update_scope.py` 3 `self.refuse(...)` (the wrapper refuses a call aimed at another graph): arguments, kept `ValueError`.

Sites in this group that I would still look at (not wrong, but inconsistent):

- `starontology/__init__.py:575` `KeyError` for an unknown ontology name; `graph/formats.py:53` raises `ValueError` for an unknown format name; `graph/qnames.py:46` `KeyError('no prefix is bound ...')`. Three ways to say "unknown name". Recommend `ValueError` for all three (a `KeyError` is a lookup protocol, and `get_ontology_graph` is not a mapping).
- `graph/execution/result.py:176,197,225` `TypeError('a SELECT result has no rows')`: a call on the wrong result kind. Acceptable as a bad call; a `ValueError` would also do. Leave.
- `graph/core.py:721` `query(entailment=bad)` raises `NotImplementedError`, while `infer()` raises `ValueError` for the same input. This is a bad argument; change to `ValueError` (part 4).

### 2.2 Bad document or data format (68)

The biggest custom-class group, and the one with the most classes:

| Class | Sites | Examples (file:line, message) |
|---|---|---|
| `SparqlSyntaxError` | 9 | `parse_sparql.py:239` `unexpected character 'x'`; `:267` `invalid string escape \q`; `:379` `<why> (found <tok>)`; `:1804,1828` `expression or pattern nested too deeply to parse`; `srl.py:442` `trailing text after the expression` |
| `SRLParseError` (3 direct + 5 via `_srl_error`) | 8 | `srl.py:270` `SRL: rule set is not well-formed per §4.2: ...`; `:855` `rule set does not conform to the srl: shapes`; `parse_srl.py:60,62,98` function or property path not in SRL (these three are an unsupported feature, see 2.3); `_srl_ast.py:81` a goal that is not one triple pattern |
| `SRLDecodeError` | 4 | `srl.py:444,510,516,553` the tree cannot be read as a rule set |
| `StratificationError` | 2 | `srl.py:290`, `srl_eval.py:251` (a wrong rule set: see 2.2 note) |
| `BasicEncodingError` | 13 | `interop.py:118` `input already uses the PropositionForm vocabulary`; `:232` `... has more than one rdf:type rdf:PropositionForm triple`; `:269` `cyclic proposition form` |
| `ManchesterSyntaxError` | 4 | `manchester/parser.py:295,532` (`why`); `:1693` `nested too deeply to parse`; `starontology/manchester/__init__.py:1122` `nested too deeply to render` |
| `SQEValidationError` | 3 | `parse_sparql.py:2247,2262`, `to_rdf.py:140`: the tree fails the `sqe:` shapes (message is the SHACL report text) |
| `InvalidTripleTermError` | 1 | `triple_term.py:80` nested triple term in subject |
| builtin `SyntaxError` | 2 | `execution/update_scope.py:165` (converts `SparqlSyntaxError` back into a builtin `SyntaxError`), `ntversion.py:52` `Parser error at line ... VERSION directive` |
| `SPARQL12ConformanceError` via `error_class` | 2 | `version_conformance.py:60,73` `declares unrecognized VERSION`, `declares VERSION '1.1' but uses ...` |
| plain `ValueError` | 20 | see the list below |

The 20 plain `ValueError` that are bad data, not bad arguments (I would change these):

- `graph/core.py:381` `cycle in the RDF list at <head>`; `:386` `<head> is not a well-formed list node (n rdf:first, m rdf:rest)`.
- `graph/rdflist.py:44` `the list has a cycle`; `:48` `<node> is not a list cell`.
- `graph/manchester/serializer.py:378,382,399,426,455,458,460,507,511` nine messages of "malformed rdf:List / cannot recognize <node> as a class expression / property expression / data range": the graph is not valid OWL-in-RDF. The parser side raises `ManchesterSyntaxError`; the serializer side raises `ValueError`.
- `graph/terms.py:150` `<text> is not a valid <kind>` (a literal's lexical form); `:177,183,185` `parse_term`: `not a term` / `not exactly one term` (these are text arguments, so arguably bad-argument; I put them here because the text is a document in term syntax).
- `starontology/manchester/__init__.py:716,753,774` `unrecognized property-expression / class-expression / data-range node`: a malformed Manchester tree.

Note on `StratificationError`: it is a wrong rule set found by analysis, the SRL counterpart of SHACL's `ShapeError` ("the document is wrong"), not a failure of running it. It subclasses `SRLEvalError` and so reads as a run failure. It should sit with the data/format group.

### 2.3 Unsupported feature or configuration (42)

- `NotImplementedError` as "this wrapper does not do that" (13): `graph/endpoint.py:323,330,341`, `graph/execution/run.py:70,74,130,185`, `graph/core.py:657,843,907,911` (bare `raise NotImplementedError`), `graph/core.py:721`. Python-idiomatic; the message tells the caller what to do instead. Keep as `NotImplementedError` (see question 5).
- `NotImplementedError` as "no rendering for this tree node" (14): `sparql/sqe/to_text.py:202,253,357,403,486`, `sparql/sqe/expr_text.py:156,239,260`, `sparql/srl.py:384,609,643`, `parse_sparql.py:1965` (`WHERE-clause element ... not modeled yet`), `sqe/entailment.py:123` (`query-time entailment supports ENTAILMENT.RDF and ENTAILMENT.RDFS, not <iri>`). These are either a feature gap or a damaged tree; the caller cannot tell which. I would change these to the format/execution family with a `kind` ("unsupported" for a modeled gap).
- Plain `ValueError` as unsupported (13): `sparql/relevant.py:120,122` (`relevant_subgraph does not support SERVICE`; needs a SELECT, ASK or CONSTRUCT), `graph/endpoint.py:158,242` (blank node in an endpoint update), `graph/interop.py:345,430` (`base-direction literal has no RDF 1.1 form`; format cannot hold named graphs), `graph/pretty.py:735` (data has named graphs), `execution/update_scope.py:160` (blank-node graph cannot be named), `execution/sparql_text.py:175` (`initBindings: could not find the query's WHERE group`), `core.py:534,1022` (`the document has named graphs; parse it into a StarLayerDataset`), `manchester/serializer.py:313,319,345,848,872` (no Manchester form for this node/axiom). All are "valid input the library cannot handle"; they are the closest thing to SHACL's `ShapeCompileError` ("asks for something unsupported").
- Process refusals: `CanonicalizationComplexityError` (2, a limit: RDFC-1.0 section 7.1 requires an early exception) and `SqeTextTooDeepError` (1) belong with run-time limits (2.4).
- `TypeError` `graph/core.py:929` (`cannot pickle ... opened with path=`): unsupported; keep `TypeError` (it is the pickle protocol's own convention).

### 2.4 Failure while running (24)

All custom classes, all different bases:

| Class | Sites | Examples |
|---|---|---|
| `EndpointError(OSError)` | 5 | `endpoint.py:91` `<url> answered HTTP 500: ...`; `:93` `cannot reach <url>`; `:111,120` unsupported content type; `:130` `this endpoint has no update URL` |
| `ReasoningTimeoutError(RuntimeError)` | 2 | `_timeout.py:163` `OWL-DL reasoning did not complete within Ns and was forcibly terminated`; `:156` the subprocess crashed (reported with the same class, as the message says "not a wall-clock timeout") |
| `InconsistentOntologyError(RuntimeError)` | 2 | `owl_dl.py:174`, `owl_dl_rustdl.py:301` |
| `SRLEvalError(ValueError)` | 3 | `srl_eval.py:741` head variable not bound by the body; `:869,871` DATA block invalid triple |
| `SRLImportError(ValueError)` | 2 | `srl.py:760` `cannot read the import <iri>: ...`; `:768` import is not a valid rule set |
| `SRLImportsNotSupportedError` | 1 | `srl_eval.py:857` IMPORTS not resolved (a configuration refusal: pass `imports_loader=`) |
| `EntailmentRewriteError(NotImplementedError)` | 5 | `sqe/entailment.py:136,143,151,241,246` |
| `CanonicalizationComplexityError(RuntimeError)` | 2 | `rdfc_native.py:175,182` |
| `SqeTextTooDeepError(ValueError)` | 1 | `to_text.py:151` |
| third party | 1 | `owl_dl_rustdl.py:140` `rustdl.UnsupportedAxiomError` raised by us from a pre-check |

Plain, uncategorised run failures that bypass the library classes, and that I would change: `reasoning/owl_dl.py:188` `RuntimeError('... found java on PATH, but it failed to run HermiT')` (a failed run, plain `RuntimeError`), and `reasoning/owl_dl.py:68,84`, `owl_dl_rustdl.py:158` `RuntimeError` for "needs the optional package / a Java runtime" (that is a configuration problem, see 2.9).

Within SHACL's scheme, `srl_eval.py:741` is `kind="rule"`, `rdfc_native.py:175` and `to_text.py:151` are `kind="nesting"` or a limit, and `endpoint.py` / `_timeout.py` are new kinds.

### 2.5 Python protocol (20), internal assertions (13), control flow (12), re-raises (10), state (3), ambiguous (1)

- **Protocol (20):** 15 `AttributeError` (module `__getattr__` for lazy names in `starlayer/__init__.py:28`, `sparql/__init__.py:26`, `sparql/sqe/__init__.py:63`, `sparql/srl.py:902`, `graph/namespaces.py:32`, `graph/entailment/__init__.py:62`, `starontology/__init__.py:173`, `graph/endpoint.py:269`, `graph/manchester/_ox_terms.py:37`; immutability in `rdflib_model/dirlangstring.py:46`, `rdflib_model/triple.py:86`; `ox_store.py:166,168`; `execution/result.py:57,61`), 2 `StopIteration`, `execution/result.py:48` `KeyError`, `graph/qnames.py:46`. Leave.
- **Internal assertion (13):** `AssertionError('unhandled class-expression tag ...')` at `graph/manchester/parser.py:993,1122`, `graph/manchester/serializer.py:577,601`, `starontology/manchester/__init__.py:358,395,454,786,966,988` (10); `graph/pretty.py:700` `pretty writer did not converge`; `TypeError` at `srl_eval.py:704`, `srl_semantic_checks.py:138` `unrecognized rule body element`. These are the engine's own "cannot happen". SHACL calls this `kind="internal"`. An `assert`-style `AssertionError` is stripped under `python -O`, and a `TypeError` for it is misleading (a caller would think they passed a wrong type). Change to the library error with `kind="internal"` (13 sites, 6 files).
- **Control flow (12):** `_NotComputable` (11, `sparql/relevant.py`) and `_InvalidInstance` (1, `srl_eval.py:325`): private, caught within the module. Leave.
- **Re-raises (10):** `graph/core.py:535`, `execution/run.py:47,57,159`, `terms.py:62`, `parse_sparql.py:2181`, `srl.py:291,549`, `sqe/to_rdf.py:123`, `srl_eval.py:371`. Reviewed as part of part 3.
- **State (3):** `srl_eval.py:1417` `ValueError('this Materialization is closed; refresh() runs the rules again')` (a use after close: `RuntimeError` is the Python convention, not `ValueError`); `starontology/manchester/__init__.py:531` (`graph holds no manch:Document node`) and `:560` (`already holds a manch:Document`): wrong state of the graph argument; a bad argument value in effect. Fix `srl_eval.py:1417` to `RuntimeError` or leave; low value.
- **Ambiguous (1):** `graph/core.py:371` `value()` `ValueError('more than one value')`. This is SHACL's `kind="ambiguous"` ("a lookup that must give exactly one result gave several"). It is not an argument error; today any `except ValueError` catches it, including a caller who meant the bad-argument errors of the same method (`:364`).

### 2.6 Missing optional package or environment (8)

`graph/_versions.py:25` `ImportError` (pyoxigraph too old); `graph/entailment/infer.py:47` and `graph/rdflib_bridge.py:40` `ImportError` (a package to install); `reasoning/owl_dl.py:68,84` and `owl_dl_rustdl.py:158` `RuntimeError` (a package or a Java runtime); `kg/__init__.py:21` `FileNotFoundError`. The first three use the Python-idiomatic class; the three in `starlayer-reasoning` do not, and the same condition is converted the other way at `owl_dl.py:67` / `owl_dl_rustdl.py:157` (catch `ImportError`, raise `RuntimeError`). Recommend `ImportError` for all (the message already says what to install), and keep `kg` as is (it is a file missing in a source checkout).

## 3. Catch clauses that swallow or convert

77 handlers. The ones that only re-raise the same error, or are narrow and local (a lookahead in the Manchester parser returning `None`, `_detached.py:32` `IndexError` on an empty deque, `_timeout.py:197` `ProcessLookupError`, `rdflib_model/triple.py:83,124` attribute fallbacks, `execution/result.py:47,60,67` protocol conversions, `graph/formats.py:52`, `terms.py:149,182` conversions that keep the cause) are left out. The rest:

| file:line | Catches | Does | Risk | Recommendation |
|---|---|---|---|---|
| `sparql/srl_eval.py:619` | `Exception` around `_pattern_term_text(value)` | returns `None` (the aggregate is "an error", no value) | Hides any bug in term rendering as a SPARQL aggregate error, and any other failure class. The comment says "a term the engine cannot take in a query". | Narrow to the exceptions `_pattern_term_text` raises for an unwritable term (it raises `ValueError`/`TypeError`; confirm) and let anything else propagate. |
| `sparql/srl_eval.py:624` | `Exception` around `_EVAL_STORE.query(text)` | returns `None` | The same as the SHACL custom-function wrapper: the engine's `RuntimeError` for a real failure (evaluation failure, unsupported function, resource limit) is turned into "no value". | Catch `RuntimeError` only, and only for a message that is an expression error (match the way `:367` does, in one helper); otherwise raise `ExecutionError(kind="rule")`. |
| `sparql/srl_eval.py:1085` | `RuntimeError` around `store.update(text)` | returns `False`: "the engine cannot evaluate this one" | Any `RuntimeError` (including a real failure) switches to the slow element-by-element path. A real failure then reappears (or not) in the slow path, at the cost of running the work twice; a limit error is lost. | Check the message as `_match` (`:367`) does, with one shared helper `engine_cannot_join_triple_terms(exc)`. |
| `sparql/srl_eval.py:1156`, `:1254` | `RuntimeError` around `store.update(...)` | `pass` then fall through to the slow path | The same as `:1085`. | The same helper. |
| `sparql/srl_eval.py:367` | `RuntimeError` | message test `'triple term that is not a valid'`, else `raise` | Correct shape (the only handler that re-raises other messages), but it depends on engine wording. | Keep; make it the one shared helper. |
| `graph/execution/run.py:55`, `:157` | `RuntimeError` | message test `'projection'`, else `raise` | Same pattern and the same dependence on engine wording. | Keep; test that a pyoxigraph upgrade changes the message (a test exists? not checked). |
| `sparql/check.py:139` | `Exception` around `StarLayerGraph(...).query(text, **functions)` | returns a `QueryProblem('engine', 'error', message)` | `check_query()` is meant to report problems, but `Exception` also turns a bug in StarLayer, or in a user function in `**functions`, into "the query has a problem". | Catch the families pyoxigraph reports (`SyntaxError`, `ValueError`, `RuntimeError`, `NotImplementedError`) and let others out. |
| `sparql/sqe/rewrite.py:68` | `(ImportError, SparqlSyntaxError, ValueError, KeyError, NotImplementedError, RecursionError, TypeError, AttributeError)` | returns the original text (an optimisation is skipped) | Only a performance risk (the engine then reports the real error), but `KeyError`, `TypeError`, `AttributeError` and `ImportError` here are bugs in the rewriter, silently turned into a slow query. | Keep `SparqlSyntaxError`, `NotImplementedError`, `RecursionError`; drop the four bug classes, or log them at debug level and add a test that fails on them. |
| `sparql/sqe/entailment.py:150` | the same 7-class tuple | raises `EntailmentRewriteError('the rewritten query could not be written out as SPARQL: ...')` | A bug (`TypeError`, `AttributeError`) is reported as an unsupported query. `from e` keeps the cause. | Keep for `NotImplementedError`, `SparqlSyntaxError`; let the rest propagate (they are `kind="internal"`). |
| `sparql/srl.py:550` | `(ValueError, KeyError, TypeError, AttributeError)` | raises `SRLDecodeError('the tree cannot be read as a rule set')` (after `except SRLError: raise`) | Documented: a damaged tree is the one error a reader of hand-edited trees catches. But it also catches a bug in the decoder. | Keep (the contract is deliberate); narrow the decoder to raise `SRLDecodeError` itself over time. |
| `sparql/srl.py:758` | `Exception` around the user's `imports_loader(iri)` | raises `SRLImportError('cannot read the import ...: <Type>: msg')` | The loader is user code, so any exception is a load failure; the type is kept in the message and `__cause__`. `KeyError` is "not found". | Keep; add `kind="import"` when moved to the new class. |
| `sparql/srl_eval.py:770` | `_InvalidInstance` | `continue`: the head triple is silently dropped | By design (a literal as a triple term subject produces no triple, like SPARQL CONSTRUCT). A `DATA` block raises (`:868`), a rule head skips. | Keep; document the asymmetry in the SRL guide if not already. |
| `reasoning/_timeout.py:139` | `Exception` around `queue.get(timeout=...)` | polls; on a dead child tries once more, then `break` | Intended `queue.Empty`. `Exception` also swallows a `pickle`/`EOFError`/`OSError` from a crashed child's pipe, which then becomes "exited without producing a result (likely crashed)". | Catch `queue.Empty` for the poll and `(EOFError, OSError)` for the broken pipe, separately. |
| `reasoning/_timeout.py:147` | `Exception` around the last `queue.get(timeout=0.5)` | `pass` | The same. | The same. |
| `graph/core.py:532` | builtin `SyntaxError` from the parser | message test `'named graph'`; converts to `ValueError`, else `raise` | A string match on pyoxigraph's text; it converts a data-format error (`SyntaxError`) into a bad-argument class (`ValueError`), unlike every other parse error from the same call. | Raise the library `FormatError` or `ValueError` consistently (part 4, row 2). |
| `graph/core.py:649` | `TypeError` from `destination.write(data)` | retries `write(raw.decode('utf-8'))` | A `TypeError` from the destination for another reason is retried and then raises again with a misleading second message. Low. | Test `isinstance` of `io.TextIOBase` instead of try/except. |
| `graph/execution/update_scope.py:164` | `SparqlSyntaxError` | raises builtin `SyntaxError(str(error))` | Converts the library error to pyoxigraph's class, losing `pos/line/col`. | Raise `SparqlSyntaxError` / `FormatError` with the same fields. |
| `graph/rdflist.py:71` | `ValueError` around `remove_list(graph, old)` | `pass` ("the value is a blank node but not a list") | `remove_list` raises `ValueError` both for "not a list cell" and "cycle". A cyclic list is silently left in place. | Test that the value is a list head first; or give the two cases different kinds. |
| `graph/bnodes.py:61` | `CanonicalizationComplexityError` | `canonical = None`: falls back to non-canonical labels | The caller asked for short labels and silently gets a different (non-canonical) labelling when the graph is too symmetric. Documented in the module? not verified. | Keep; consider a warning. |
| `graph/qnames.py:84` | `(KeyError, ValueError)` | returns `<iri>` | Designed (the docstring says an IRI no namespace fits stays `<iri>`). | Keep. |
| `sparql/_oxterms.py:47,65,91,99` | `ValueError` | returns a reversible stand-in term (`urn:starlayer:invalid-iri:...`) | Designed and documented in the module docstring; the `try` bodies are one call each. | Keep. |
| `graph/endpoint.py:89,92` | `HTTPError`; `(URLError, TimeoutError)` | `raise EndpointError(...) from exc` | The good pattern. It does not convert `http.client.HTTPException` (e.g. a dropped connection mid-read), `ConnectionResetError` after connect, or a JSON parse error of the body; not checked whether those occur. | Keep; extend to `OSError` and `HTTPException` if a test shows leakage. |
| `graph/entailment/infer.py:47`, `graph/rdflib_bridge.py:39` | `ImportError` | `raise ImportError('... pip install ...')` | None; re-raises the same class with an actionable message. | Keep. |
| `reasoning/owl_dl.py:67`, `owl_dl_rustdl.py:157` | `ImportError` | `raise RuntimeError('requires the optional package')` | Changes class; a caller who guards optional features with `except ImportError` misses it. | Raise `ImportError`. |
| `reasoning/owl_dl.py:123,126` | `owlready2.OwlReadyInconsistentOntologyError`, `OwlReadyJavaError` | puts a tagged tuple on the queue; the parent re-raises `InconsistentOntologyError` / `RuntimeError` | Correct (a process boundary), but the Java error becomes a plain `RuntimeError`. | Use the library error with a kind. |
| `sparql/relevant.py:136` | `_NotComputable` | falls back to a pattern-based approximation, `supported=False` | By design; the flag tells the caller. | Keep. |
| `graph/manchester/parser.py:550,618,884,1692` | `ValueError`, `RecursionError` | convert to `ManchesterSyntaxError` | Good pattern; narrow. | Keep. |
| `parse_sparql.py:1803,1827,2200`, `parse_srl.py:315`, `to_text.py:150`, `entailment.py:142`, `manchester/__init__.py:1120` | `RecursionError` | convert to a different class each time | Correct conversion (a stack limit), but 5 different classes (part 4, row 5). | One `kind="nesting"` (SHACL's word). |
| `shacl/meta_shapes.py:405` (outside scope, noted) | `(SparqlSyntaxError, ValueError)` | returns a message string | `SparqlSyntaxError` is a `ValueError`, so the tuple is redundant, and a bad-argument `ValueError` from the parser would be reported as "not valid SPARQL". | Narrow when `SparqlSyntaxError` stops being a `ValueError`. |

Catch clauses I found fine and did not list: 12 of the 77 re-raise the same class, 9 convert `RecursionError`, 5 handle `KeyError` for protocol or lookup defaults.

## 4. Where the classes do not agree

| # | The same kind of problem | Raised as | Verified |
|---|---|---|---|
| 1 | Malformed SPARQL query or update text | `graph.query()`, `graph.update()`: builtin `SyntaxError` from pyoxigraph, not wrapped. `parse_sparql()`, `parse_sparql_update()`, `check_query()`, `sqe_parse_to_tree()`: `SparqlSyntaxError(ValueError)` with `pos/line/col`. SRL text: `SRLParseError(SRLError(ValueError))`. `scope_update()`: `SparqlSyntaxError` converted back to builtin `SyntaxError` (`update_scope.py:164`). | yes, run: `g.query('SELEC ?x')` gives `SyntaxError`; `parse_sparql('SELEC')` gives `SparqlSyntaxError`; `parse_ruleset('RULE')` gives `SRLParseError` |
| 2 | Malformed RDF document | `graph.parse()`: builtin `SyntaxError` (pyoxigraph), except one case converted to `ValueError` by a string match (`core.py:532`). Manchester: `ManchesterSyntaxError(SyntaxError)`. N-Triples VERSION line: `SyntaxError` (`ntversion.py:52`). PropositionForm encoding: `BasicEncodingError(ValueError)`. Manchester tree in RDF and OWL-in-RDF: `ValueError`, `ManchesterSyntaxError`, `AssertionError`. Unknown format name: `ValueError`. | yes for `parse()` (Turtle and bad language tag give `SyntaxError`), Manchester gives `ManchesterSyntaxError` |
| 3 | Unsupported entailment regime | `graph.query(entailment=...)`: `NotImplementedError` (a `RuntimeError`); `infer(entailment=...)`: `ValueError`; `sqe.entailment.rewrite_for_entailment`: `NotImplementedError`; `rewrite` limits: `EntailmentRewriteError(NotImplementedError)` | yes (`query` gives `NotImplementedError`, `infer(entailment='nope')` gives `ValueError`) |
| 4 | An evaluation failure in a query | the engine's `RuntimeError` is let through by `query()` (e.g. `The custom function <urn:nope> is not supported`, verified); in an SRL run it is an `SRLEvalError(ValueError)` or silently swallowed (part 3); in SHACL it is `ExecutionError(kind="expression")` or "no value" | partly (query verified) |
| 5 | "Nested too deeply" | `SparqlSyntaxError` (parse and encode, `parse_sparql.py:1804,1828,2201`), `SRLParseError` (`parse_srl.py:315`), `SqeTextTooDeepError` (`to_text.py:151`), `EntailmentRewriteError` (`entailment.py:143`), `ManchesterSyntaxError` (`manchester/parser.py:1693`, `starontology/manchester/__init__.py:1122`); SHACL: `ExecutionError(kind="nesting")` | read |
| 6 | Missing optional dependency | `ImportError` (`infer.py:47`, `rdflib_bridge.py:40`, `_versions.py:25`), `RuntimeError` (`owl_dl.py:68,84`, `owl_dl_rustdl.py:158`), `FileNotFoundError` (`kg/__init__.py:21`) | read |
| 7 | A run failure in an external subsystem | `EndpointError(OSError)`, `ReasoningTimeoutError(RuntimeError)`, `InconsistentOntologyError(RuntimeError)`, `CanonicalizationComplexityError(RuntimeError)`, `SRLEvalError(ValueError)`, `SRLImportError(ValueError)`, plain `RuntimeError` (`owl_dl.py:188`). Two of them are `ValueError`, so they are caught by every `except ValueError`; three are `RuntimeError`, so they are caught by clauses that mean the engine's `RuntimeError` (part 3, `srl_eval.py:1085,1156,1254`, `run.py:55,157`) | read |
| 8 | Same argument checked in several places | `mode must be one of ...` and `target_graph is meaningless with mode='in-place'` appear in `entailment/infer.py:168,188` and `graph/imports.py:47,49`; `recompute must be one of` in `core.py:731` and `cache.py:131`; `engine=`/`timeout=` only for OWL-Direct in `core.py:726,728`, `infer.py:182,184` and SHACL's `_adapter` (`ValueError` in all). | read |
| 9 | An unwritable or unrenderable term/tree | `ValueError` (`manchester/serializer.py:313-511`), `NotImplementedError` (`sqe/to_text.py`, `expr_text.py`, `srl.py`), `AssertionError` (`parser.py`, `serializer.py`, `starontology/manchester`) | read |
| 10 | "More than one result / none" | `ValueError('more than one value')` (`core.py:371`) versus SHACL `ExecutionError(kind="ambiguous")` | read |

### Where SHACL's classes cross into the rest of the library

- **SRL checked inference** (`sparql/_srl_ast.py:533-545`, `RuleSet.infer(schema=...)`): constructs `StarShaclProcessor(shacl_graph=schema)` and calls `.validate(...)`. A wrong schema raises `ShapeCompileError` or `MetaShaclError`; a failed validation run raises `ExecutionError`. They escape unwrapped from `infer()`, beside `SRLParseError`, `SRLEvalError`, `StratificationError` and the engine's `RuntimeError`. The caller of one `infer(schema=)` call has to know four families. (An SRL conformance check also uses SHACL: `srl.py:855` raises `SRLParseError` from a validation report, and `srl.py:877`, `sqe/shapes.py:84` and `starontology/manchester/__init__.py:1278` call `validate_bounded`; an `ExecutionError(kind="nesting")` from `max_validation_depth=100` is not converted there.)
- **SHACL inference** (`shacl/engine/api.py:156`): `InconsistentOntologyError` and `ReasoningTimeoutError` "propagate" through `validate()` / `apply_rules()` when `inference=ENTAILMENT["OWL-Direct"]`. They are `RuntimeError`s, not `ExecutionError`, so a SHACL caller that catches `ExecutionError` will miss them.
- **`shacl/meta_shapes.py:405`** catches `(SparqlSyntaxError, ValueError)` from the SPARQL parser.
- **The dependency runs the other way too.** `graph/terms.py:35`, `graph/rdflib_bridge.py:17`, `graph/lexical.py:100`, `graph/core.py:831,1284`, `sparql/_oxterms.py:15`, `sparql/check.py:149`, `sparql/sqe/*` and `starontology/__init__.py:170,770,800` import from `starlayer.shacl.engine.*` (terms, graph views). The error classes are in `shacl/engine/plan.py` and `shacl/engine/meta.py`. A shared base class would have to be in a neutral module (for example `starlayer/errors.py`), and `shacl/errors.py` would re-export from there.

## 5. Proposal: one uniform scheme

The user's principles that decide this: (1) plain `ValueError` is only a bad argument at a public call; (2) a compile- or run-time problem is a library error with a cause; (3) not too granular: prefer one class plus a `kind`; (4) no aliases when anything is renamed. Principle 3 argues against per-subsystem class trees; principle 4 means every renamed class is a clean break.

### Option A: one library base, three families with `kind` (recommended)

New module `starlayer/errors.py` (no imports from `graph`, `sparql` or `shacl`), exported from `starlayer` and re-exported by `starlayer.shacl.errors`.

```
StarLayerError(Exception)                 base, never raised bare
 |- ShapeError(StarLayerError)            as now (see question 2 on ValueError)
 |   |- ShapeCompileError
 |   `- MetaShaclError
 |- FormatError(StarLayerError)           a document or data is malformed; kind: "sparql", "srl", "rdf", "manchester",
 |                                        "encoding", "rule-set"; optional pos/line/col (from SparqlSyntaxError)
 `- ExecutionError(StarLayerError)        a run failed; SHACL's kinds ("rule", "expression", "nesting", "recursion",
                                          "constraint-query", "ambiguous", "internal") plus "query", "endpoint",
                                          "inference", "inconsistent", "timeout", "limit", "import", "unsupported"
```

What the public classes become:

- 21 classes become 3 new public ones (`StarLayerError`, `FormatError`; `ExecutionError` is SHACL's, moved). `SparqlSyntaxError`, `SQEError`, `SQEValidationError`, `SRLError`, `SRLParseError`, `SRLDecodeError`, `SRLImportError`, `SRLEvalError`, `StratificationError`, `SRLImportsNotSupportedError`, `ManchesterSyntaxError`, `BasicEncodingError`, `InvalidTripleTermError`, `SPARQL12ConformanceError` (14) become `FormatError` with a kind; `EndpointError`, `ReasoningTimeoutError`, `InconsistentOntologyError`, `CanonicalizationComplexityError`, `EntailmentRewriteError`, `SqeTextTooDeepError` (6) become `ExecutionError` with a kind. `EndpointError.status` becomes an optional attribute of `ExecutionError`; `SRLUnresolvedImportsWarning` stays a warning.
- Both new classes derive from `Exception`, not `ValueError`, `SyntaxError` or `RuntimeError`: no `except ValueError` swallows them. `ShapeError` is currently a `ValueError` (the code's own docstring); making it a plain `StarLayerError` would complete the rule (question 2).
- Bad arguments stay plain `ValueError` / `TypeError` (96 sites, no change). Missing packages become `ImportError`. Internal failures are `ExecutionError(kind="internal")`.
- The pyoxigraph boundary (the 5 places where the wrapper calls `store.query`, `store.update`, `store.load`, `ox.parse`, `ox.serialize`, in `graph/execution/run.py` and `graph/core.py`) converts the engine's `SyntaxError` to `FormatError(kind="sparql"|"rdf")` and its `RuntimeError` to `ExecutionError(kind="query")`, `from` the original.

What changes for callers: `except SyntaxError` / `except ValueError` for a bad query, document, rule set or Manchester text no longer works and becomes `except FormatError`; `except RuntimeError` / `except OSError` around inference or an endpoint becomes `except ExecutionError`, with `error.kind` where a caller needs to tell timeout from inconsistency. One `except StarLayerError` catches everything the library raises on purpose. SHACL callers see no change except that `InconsistentOntologyError` and `ReasoningTimeoutError` now arrive as `ExecutionError` (kinds "inconsistent", "timeout") instead of escaping as `RuntimeError`.

Sites changed (my count, by bucket): 68 data/format (48 already custom, only the class changes; 20 plain `ValueError` become `FormatError`), 24 run failures, about 25 of the 42 unsupported (14 render-gap `NotImplementedError` and 11 `ValueError` become `FormatError` or `ExecutionError(kind="unsupported")`; the 13 wrapper `NotImplementedError` stay), 13 internal, about 4 missing-package and 1 ambiguous: about **125 raise sites in about 35 files**, plus 12 to 15 catch clauses (part 3) and 5 boundary points. Tests: 64 test files outside SHACL use `pytest.raises` on a builtin class (about 215 `raises` lines: 132 `ValueError`, 36 `TypeError`, 32 `SyntaxError`), of which I expect about a third to change; 13 guide notebooks mention the old names (guide edits go through staging).

Risks:
- A caller's `except SyntaxError` around `graph.parse()` stops working. This is the biggest break, and the only one that touches code written against pyoxigraph's behaviour (the guides and the workbench may do so; not checked).
- A `kind` string is typed by hand; a typo is caught only by a test. SHACL already guards this (`ExecutionError.__init__` raises on an unknown kind); copy that.
- Position information (`pos`, `line`, `col`) has to be carried by `FormatError` for all kinds, or only some (question 3).
- `ShapeError` and `FormatError` overlap in meaning: a malformed shapes graph is "bad data". The line is already drawn by the SHACL scheme (shapes graph is `ShapeError`); the same line must be written down for SRL rule sets (`kind="rule-set"` is a `FormatError`).

Migration without aliases: create `starlayer/errors.py` and move SHACL's four classes there (shacl `errors.py` re-exports, which is not an alias, the same class); do one subsystem per commit; delete the old classes in the same commit that changes their raise sites and their tests; update the guides in the staging flow, and put an entry in the release notes listing old name to new class and kind.

### Option B: per-subsystem bases following SHACL's pattern

`SparqlError` (with `SparqlSyntaxError`, `SparqlEvalError`), `SrlError` (kept: `SRLParseError`, `SRLEvalError`), `GraphError` (`EndpointError`, `EncodingError`), `ReasoningError` (`TimeoutError`, `InconsistentOntologyError`), plus SHACL's. Each base has its own subclasses or kinds.

- Public classes: about 5 bases and 15 to 20 subclasses (most of today's classes rebased). Callers: catch a subsystem base; no single catch-all (unless a common root is added, which makes it option A with more classes).
- Sites changed: about 100 (rebases and a few `ValueError` replacements; no kind rewrite). Risks: it keeps the granularity that the user's principle 3 rejects (SRL alone has 7 classes); it does not fix disagreement 3 to 7 (the same problem in two subsystems still gets two classes); the SHACL / SRL / reasoning crossing (part 4) is not solved, because each subsystem still raises its own family. Migration: lower, since most classes keep their names.

### Option C: leave the subsystems separate; fix only the swallowing clauses and the plain-`ValueError` rule

Fix the 12 to 15 clauses of part 3; change the 20 plain `ValueError` of bucket "bad data" and the 13 of "unsupported" to the existing custom classes (`ManchesterSyntaxError`, `BasicEncodingError`, `SparqlSyntaxError`); convert `AssertionError` / `TypeError` internal sites; state the rule in each `CLAUDE.md`; change the three `RuntimeError` for missing packages to `ImportError`.

- Public classes: no change (21 stay). Callers: nothing breaks except the 33 sites that stop being plain `ValueError`. Sites: about 45 raise sites in 14 files plus the clauses.
- Risks: the 14 `ValueError` subclasses remain and keep being swallowed by `except ValueError` (the risk the rule was meant to remove); disagreements 1, 3, 5, 6, 7 remain; "write the rule once" gets a rule that the classes themselves break.
- Cheapest, and the right first step in any case.

### Recommendation

**A, reached through C.** C is cheap, safe and independent; its part (fix the clauses, state the rule) is needed whichever option is chosen, so do it first and get the benefit now. Then A, one subsystem per commit. A fits the user's stated principles (one class plus a `kind`, not too granular, no aliases) and it is the only option that removes disagreements 1 to 7 and the SHACL crossing. B is the same work with the granularity kept. The honest cost of A is a one-time break of every `except SyntaxError` / `except ValueError` / `except RuntimeError` a caller wrote against the library (the guides, tests, and workbench included), and about a day of mechanical edits per subsystem.

## 6. Ordered work list, and the questions to decide

| Step | Work | Size (files / sites) |
|---|---|---|
| 1 | Write the rule once (plain `ValueError` only for a bad argument; a compile- or run-time problem is a library error with a cause) in `graph/CLAUDE.md`, `sparql/CLAUDE.md`, `shacl/CLAUDE.md` and the guides' error section | 3 files plus guide text (staging) |
| 2 | Fix the swallowing clauses: `srl_eval.py` (619, 624, 1085, 1156, 1254 and a shared helper for 367), `run.py` (55, 157), `_timeout.py` (139, 147), `check.py:139`, `sqe/rewrite.py:68`, `sqe/entailment.py:150` | about 12 clauses, 6 files, with a test per clause that a real failure is not swallowed |
| 3 | Decide the scheme (questions below) | decision |
| 4 | Create `starlayer/errors.py`; move SHACL's `ShapeError` tree and `ExecutionError` into it; `shacl/errors.py` re-exports; extend `ExecutionError.KINDS`; add `FormatError` | 4 files |
| 5 | Convert the internal assertions to `kind="internal"` (13 sites, 6 files) and the 3 missing-package `RuntimeError` to `ImportError` | 8 files, 16 sites |
| 6 | `reasoning` package: `ReasoningTimeoutError`, `InconsistentOntologyError`, the Java `RuntimeError` become `ExecutionError` kinds; SHACL's note in `api.py` updated | 4 files, 5 sites plus tests (12 test files mention the old names) |
| 7 | `graph/`: `EndpointError`, `CanonicalizationComplexityError`, `BasicEncodingError`, `SPARQL12ConformanceError`, `ManchesterSyntaxError` and the 20 plain `ValueError` of "bad data", the `ValueError` of "unsupported", `value()` ambiguous; wrap the pyoxigraph boundary | about 14 files, about 55 sites |
| 8 | `sparql/` (incl. `sqe/`): `SparqlSyntaxError`, `SQE*`, `SRL*`, `EntailmentRewriteError`, `SqeTextTooDeepError`, `InvalidTripleTermError`; nesting becomes one kind; `NotImplementedError` render gaps | about 14 files, about 60 sites |
| 9 | `starontology/`: 10 plain `ValueError`/`AssertionError` and the `KeyError` | 2 files, about 10 sites |
| 10 | SHACL crossing: `infer(schema=)` and `validate_bounded` callers document and test which error classes escape; remove `shacl/meta_shapes.py:405`'s `ValueError` | 4 files |
| 11 | Tests and guides: replace builtin-class `raises` and `except` in about 64 test files and about 13 guide notebooks | large but mechanical; the notebooks go through the staging flow |
| 12 | Update `docs/design/future_enhancements.md` (close the entry) and the "Remove the deprecation aliases" list if anything else turns up | 1 file |

Steps 1 to 2 are independent and worth doing now. Steps 4 to 9 depend on the answers to question 1 to 3 and should follow the order above (reasoning first: fewest sites and no callers inside the library).

### Questions for the user

1. **Scheme.** A (one base, three families with a `kind`), B (per-subsystem), or C only? The recommendation is C now, then A.
2. **Should `ShapeError` stay a `ValueError`?** Its docstring says it is, "never raised bare". If the rule "a plain `ValueError` is only a bad argument" is to hold everywhere, `ShapeError` should become a `StarLayerError` only (a break for anyone who catches a bad shapes graph as `ValueError`); the guides may rely on it.
3. **Does `FormatError` carry `pos/line/col`** for all kinds (`SparqlSyntaxError` does; Manchester has a `pos`), or only a `kind` and a message with the position in the text?
4. **The pyoxigraph boundary.** Should `graph.query()`, `update()`, `parse()` wrap the engine's `SyntaxError` / `RuntimeError` in the library classes? This is the largest behaviour change for callers, and the one that gives the real uniformity; leaving it means "malformed query" stays two classes (`SyntaxError` from the graph, `FormatError` from `parse_sparql`).
5. **`NotImplementedError`.** Keep it for the 13 wrapper refusals ("the wrapper runs query text, not a prepared Query object", "load into an endpoint-backed graph with graph.parse()"), or move them to `ExecutionError(kind="unsupported")`? I would keep the Python idiom for a method the object really does not have, and use the library error for a feature of a document.
6. **`StratificationError` and the SRL well-formedness errors**: a wrong rule set (`FormatError(kind="rule-set")`, the counterpart of `ShapeError`) or an execution failure? I put them with the bad data; today `StratificationError` is an `SRLEvalError`.
7. **Missing optional package**: `ImportError` everywhere (my recommendation), or a library error with `kind="missing-package"`?
8. **Order and scope.** Do all subsystems in one release (a single clean break), or one subsystem per release? With no aliases, doing them one at a time means callers update several times.

Not determined in this audit: whether the workbench (`graph-workbench`) or the guides catch `SyntaxError` or `ValueError` from `graph.parse()` and `graph.query()` (outside this repository's `packages/`); whether the `RuntimeError` message tests in `run.py` and `srl_eval.py` have a test that fails when pyoxigraph changes its wording; whether `bnodes.py:61` falls back to non-canonical labels with a documented warning.

## 7. The same cause must not change class or kind with the path (added 2026-11-25, all of `packages/starlayer` including `shacl/`)

Principle raised by the user: "the same error should not be presented differently based on its context". `shacl/` was read at 0be8208c, read-only. Line numbers are of that commit.

### 7.1 Cases found

| # | Cause | Path A | Path B | Legitimate context, or inconsistency? |
|---|---|---|---|---|
| 1 | A node expression cannot be evaluated or nests too deep | `validate()` and `evaluate()`: `ExecutionError` kind `"expression"` or `"nesting"` | Inside a `sh:rule`: `engine/rules.py:565-568` catches `Exception` around `evaluate(...)` for the rule's subject/predicate/object expression and raises `ExecutionError(kind="rule")`, so an `"expression"` or `"nesting"` failure is relabelled `"rule"`. Its `ShapeError` branch (`:565`) is relabelled `ShapeCompileError`, which is acceptable for a plain `ShapeError` but turns a `MetaShaclError` into a different class | **Inconsistency of kind.** The rule's name is context and is already in the message; the kind should stay the cause. |
| 2 | A SPARQL rule's CONSTRUCT fails to evaluate | `engine/rules.py:527` `except Exception` raises `kind="rule"`, which also covers an `ExecutionError` of kind `"expression"` raised by a custom function or `"nesting"` inside the query | the same failure in a `sh:sparql` constraint is `kind="constraint-query"` or `"expression"` | **Inconsistency**: `Exception` is wider than "the query did not evaluate"; an `ExecutionError` that already has a kind must pass through. A bare engine `RuntimeError` is a new kind (the pyoxigraph boundary of part 5). |
| 3 | Same failure while checking a rule's `sh:condition` | `:479` `_prefixed(exc, ...)` keeps the class and kind and adds the rule to the message | | **Correct.** This is the pattern to follow. |
| 4 | The rule set failed | `apply_rules` `:720-723` keeps the class and kind and adds the rule's location (`_renamed`); with `raise_on_failure=False` it records the message in `RuleResult.failures` and drops the class and kind | | Raising: correct. Recording: the kind is lost in the report (only text); acceptable if `failures` stays a list of messages, but a structured entry (message, class, kind) would follow the principle. |
| 5 | A node-expression failure inside a rule that derives values | `:599` `except Exception: continue` ("a failing expression derives no value") | the same expression in `validate()` raises | **Inconsistency, swallow.** Node Expressions 3.2 says an error is not an empty result; here a rule hides it. |
| 6 | Fragment extraction (`extract_subgraph`, `engine/subgraph.py:291,297,302`) | catches `(ExecutionError, ShapeError)` around `evaluate_expression` for `sh:expression` and `sh:values`-style expressions and `extract(...)`, and skips the value | `validate()` raises for the same expression | **Inconsistency, swallow.** The comment case ("a failing expression contributes nothing to the fragment") may be intended, but it makes the fragment of a graph the engine cannot validate silently incomplete, which breaks the Conformance Theorem's premise. `:230` (`except ShapeError: continue` for an unreadable second path) is the same. Needs a decision: raise (same as validate), or return the fragment plus a diagnostic. |
| 7 | A SPARQL custom function failed | previously swallowed inside the function wrapper | fixed by the other agent (now a kind) | Fixed; kept here for the list. Similar still open outside SHACL: `srl_eval.py:619,624` (part 3). |
| 8 | A malformed shapes graph | without `meta_shacl`: `ShapeCompileError` from the compiler | with `meta_shacl=True`: `MetaShaclError` from the meta check, before compiling | **Acceptable by design, and the scheme already says so.** Both are `ShapeError`; a caller who catches `ShapeError` sees one class for one cause. What differs is who found it (the report attributes of `MetaShaclError`), which is context, not cause. The only requirement is that the two are never disjoint in a way that makes a `ShapeError` handler miss one; they are not. Not a case to change. |
| 9 | `value()` with several matches | `RecordingGraph.value` (`engine/reads.py:118`): `ExecutionError(kind="ambiguous")` | `StarLayerGraph.value` (`graph/core.py:371`): plain `ValueError('more than one value')` | **Inconsistency of class.** It is the same cause, on two graph implementations the engine treats as one protocol. The graph layer should raise the library `ExecutionError(kind="ambiguous")` (needs the shared base of part 5; until then, the engine's own class would have to be imported into `graph/`, which inverts the dependency). Same for `rdflist.py:44,48` and `core.py:381,386` (a malformed list is `FormatError`) and the Manchester serializer. |
| 10 | Nested too deeply | five classes outside SHACL (part 4, row 5) and `"nesting"` in SHACL | | **Inconsistency** (one kind, `"nesting"`). |
| 11 | A malformed SPARQL text | builtin `SyntaxError` from the graph, `SparqlSyntaxError` from the parser, `SRLParseError` from SRL, `ShapeCompileError` from a `sh:select` | | A bad query in a shapes graph being a `ShapeError` is context (where it was found: a shapes graph), and is legitimate **as long as the original is `__cause__`** and a `kind="sparql"` `FormatError` is the cause. Disagreement is between the first three (part 4, row 1). |
| 12 | OWL-Direct reasoner fails during SHACL inference | `InconsistentOntologyError` / `ReasoningTimeoutError` escape as `RuntimeError` | the same call outside SHACL: the same classes | Same class on both paths (consistent) but outside the SHACL scheme; part 4. |
| 13 | A failure in the SHACL internal check `rules.py:643-644` | `ImportError` converted to `ExecutionError(kind="rule")` | | **Inconsistency**: a missing module of our own package is `kind="internal"`. |

Other places with the same shape found by grep for `raise ... from` and `_prefixed/_renamed`: `engine/rules.py:479`, `:720` keep the class (good); `:525-528`, `:565-568`, `:643` relabel (bad). No other re-labelling in `shacl/`; I did not read all of `shacl/engine/*` for relabelling in other modules, only `rules.py`, `subgraph.py`, `reads.py` and the places the grep found.

### 7.2 Context that is legitimate

Which rule, which shape, which focus node, which value, which call (`validate`, `apply_rules`, `extract_subgraph`), which store or endpoint, and who found a wrong shapes graph (compiler or meta check). These are facts about where; they answer "where do I look", not "what went wrong". The message already carries the rule and shape in prose (`locate(...)` and `_prefixed`).

### 7.3 Proposed principle

> **Class and `kind` name the cause and do not change with the path the error travels.** Where it happened (rule, shape, focus node, value, call) goes in the message and in optional attributes, never in a different class or kind. A handler may add context and re-raise the same object (`raise _prefixed(exc, ...)`), or raise a new error of the same class and kind `from` the old; it never relabels. A path that must not stop on an error (fragments, a rule that derives no value) either does not catch it, or reports it as a diagnostic that carries the class, the kind and the context; it does not drop it silently.

Mechanism: give `ExecutionError` (and `ShapeError`) an optional keyword `context` (a small immutable mapping or dataclass, for example `where="sh:rule ex:R1"`, `shape=`, `focus=`, `value=`), default `None`, shown after the message by `str()` only when set, and carried through pickle as `kind` already is. `_prefixed` and `_renamed` then add or replace `context` without rewriting the message. A name such as `where` or `context` is for the user to pick (question 9).

### 7.4 What would change to follow it

| Where | Change | Sites |
|---|---|---|
| `shacl/engine/rules.py:565-568` | catch `ShapeError` and `ExecutionError` separately: add the rule as context and re-raise the same class and kind (`_prefixed` pattern); catch a bare engine `Exception` only to wrap it as the new engine kind; remove the `ShapeCompileError` relabel of `MetaShaclError` | 1 clause (2 branches) |
| `shacl/engine/rules.py:525-528` | `except ExecutionError: raise` with context; wrap only the engine's own exceptions | 1 clause |
| `shacl/engine/rules.py:599` | stop swallowing; let the `ExecutionError` of the expression propagate with the rule as context (a behaviour change: a rule whose expression fails now fails the rule set; the "derives no value" case needs a decision) | 1 clause |
| `shacl/engine/rules.py:643-644` | `kind="internal"` | 1 site |
| `shacl/engine/rules.py:479, 720-723` | keep; `_prefixed` / `_renamed` set `context` (the `locate()` result) instead of rewriting `args` | 2 helpers |
| `shacl/engine/subgraph.py:291, 297, 302` (and `:230`) | decision: raise like `validate()`, or collect and return a diagnostic with class, kind and context | 4 clauses |
| `RuleResult.failures` | entries carry class, kind and context, not text only | 1 type, about 3 producers/consumers (not read in full) |
| `graph/core.py:371` `value()` | `ExecutionError(kind="ambiguous")` once the shared base exists (or a `ValueError` on both sides until then: change `reads.py:118` instead, with the argument that `value(any=False)` on a node with several values is "a lookup that must give one result" and not a bad call: this is the less consistent choice) | 1 site (+1 in `reads.py` if the other direction) |
| `ExecutionError` / `ShapeError` | add optional `context`; keep `kind` the only discriminator | 2 classes, `__reduce__` |

Total in `shacl/`: about 9 clauses or sites in 2 files plus the two classes, `RuleResult.failures` and tests (the existing tests that assert `kind == "rule"` for an expression failure in a rule would change; not counted). In the rest of the library the same principle adds the `value()` site and the nesting, syntax and unsupported groups already listed in parts 4 and 5.

### 7.5 Added question for the user

9. **Principle and mechanism.** Adopt "class and kind name the cause, never the path; where it happened is context in the message and in an optional attribute"? If yes: the attribute's name (`context` or `where`), whether the two swallowing paths (fragment extraction `subgraph.py:291-302`, and a rule that derives no value `rules.py:599`) should raise like `validate()` or report a diagnostic, and whether `RuleResult.failures` should become structured. And, for case 8, whether `ShapeCompileError` without `meta_shacl` and `MetaShaclError` with it is acceptable (my reading: yes, both are `ShapeError`, and the difference is who found it).
