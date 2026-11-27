# The error scheme: full summary for review (2026-11-26)

Step A, stages 0 to 6, finished 2026-11-26. This is the document to review: (a) the scheme, (b) every old class, (c) what stayed a plain `ValueError` / `TypeError`, (d) behaviour changes, (e) open questions, (f) the guide cells to change, (g) the workbench lines to change. Detail per stage is in `docs/working/error-scheme-decisions-log-2026-11-25.md` (stage 6 section appended today; stage 1 and 2 decisions are in their commit messages: 2d27b2d0, b02029ee). The rules for contributors are now in `AGENTS.md`; `tests/repo/test_error_scheme.py` pins them.

## (a) The scheme on one page

Everything the library raises on purpose derives from `StarLayerError(Exception)` (`starlayer/errors.py`, a leaf module: standard library only). None of them is a `ValueError`, `SyntaxError`, `RuntimeError` or `OSError`, except `EndpointError(StarLayerError, OSError)`. `except StarLayerError` means "the library said no".

```
StarLayerError
 |- ShapeError                a shapes graph, rule or setup is wrong          context
 |   |- ShapeCompileError     the engine cannot read or compile it
 |   `- MetaShaclError        the meta check found it                         problems, report_text, report_graph, scope
 |- FormatError               text or data is malformed                       kind, context, why, line, col, pos
 |- ExecutionError            running failed, or input the library cannot handle   kind, context
 `- EndpointError (+OSError)  a SPARQL endpoint was unreachable or answered with an error status   status
```

One class and a `kind`, never a class per case. The class and kind name the cause and never change with the path an error travels; where it happened is `context` (a short string, also in the message).

| `FormatError` kind | the malformed thing |
|---|---|
| `sparql` | SPARQL query or update text, an `sqe:` tree, a `VERSION` declaration (also a query handed to the entailment rewrite that is not a query) |
| `srl` | SRL text, an `srl:` tree, a bad `DATA` block, an imported text that is not a rule set, a §4.2 breach found when running, a hand-built rule set holding something that is not a body element, a goal pattern whose predicate SRL does not allow |
| `rdf` | an RDF document (`parse()`: `line`, `col` from the parser), an `rdf:List`, the PropositionForm encoding, an ordinal tie in a `tree:ord` tree |
(`term` was merged into `rdf` on 2026-11-26 (Q10): the `rdf` row also covers term text: IRI, language tag, CURIE, a lexical form for its datatype, `parse_term`, a nested triple term, an rdflib term Oxigraph rejects; `context` says it is a term.)
| `manchester` | Manchester Syntax text, a `manch:` tree, a SWRL `Rule:` frame |
| `owl` | RDF that is not valid OWL when written as Manchester |

| `ExecutionError` kind | what failed |
|---|---|
| `rule` | a rule failed or the rule set as a whole (unorderable, a foreign exception out of a rule's query) |
| `expression` | a node expression cannot be evaluated |
(`nesting` was merged into `limit` on 2026-11-26 (Q9): a depth limit of the path, expressions, query text, tree, Manchester or entailment rewrite is `limit`, `context` says what was too deep.)
| `recursion` | a shape reaches itself through `sh:not` |
| `constraint-query` | a `sh:sparql` query reported `?failure true` |
| `internal` | an impossible state: a bug in StarLayer, to be reported; the message starts "internal error (a bug in StarLayer, please report it at https://github.com/hidden-graph/starlayer/issues)" and `error.report_url` is that URL (Q7) |
| `timeout`, `inconsistent`, `inference` | OWL-DL reasoning: wall-clock budget; data inconsistent under OWL 2 DL; the reasoner could not run or died |
| `query` | Oxigraph failed to evaluate a query or update whose text parsed |
| `import` | a declared import is not resolved, on every path (`owl:imports` of a graph, shapes graph or ontology graph, SRL `IMPORTS`): no loader, a loader that returned nothing or a graph without the IRI, or a loader that raised (wrapped); `error.unresolved` lists the IRIs |
| `unsupported` | valid input the library or the target notation cannot handle, nobody's mistake (Manchester serializer, `sqe:`/SRL text rendering, entailment rewrite, `initBindings` text scan, an entailment name that is not a registered regime, `relevant_subgraph` with DESCRIBE or SERVICE, an endpoint-origin blank node, direction policy `"error"`) |
| `limit` | a size or complexity cap of the library (RDFC-1.0 symmetric blank-node structure; the SHACL `max_iterations` and `max_triples`) |

When to use which (the ladder the maintainer decided on 2026-11-26): (1) the wrong Python type is `TypeError`; (2) a thing in a defined format (text, document, tree, term, rule set) whose content cannot be read is `FormatError`, even when it is an argument; a parsed value is `FormatError`, a chosen or combined one `ValueError` (a bad direction passed to `literal()` is `ValueError`, the same text in a parsed document is `FormatError`); (3) a parameter or object the call cannot use as it stands (a value outside the choices the call defines, contradictory options, a wrong target, an object in a state the call refuses such as a closed `Materialization`) is `ValueError`; otherwise the arguments are fine and the work could not be done: `ExecutionError` by cause (`unsupported`: valid input nobody did wrong; `internal`: the library's own bug; `limit`: a cap).

- A bad argument at the entry of a public call (value, combination, a graph or term this object refuses): plain `ValueError`; a wrong Python type: `TypeError`. Test: it is fixed by changing the argument.
- A missing optional package: `ImportError`. A wrapper method the object does not have: `NotImplementedError`.
- A document, text, tree or term that is malformed: `FormatError`. A shapes graph that is wrong: `ShapeError`.
- Everything that failed while running, or well-formed input the library cannot handle: `ExecutionError`, kind by cause.
- An engine exception (pyoxigraph `SyntaxError`, `RuntimeError`) is converted once, at `parse()`, `query()` and `update()`.
- A catch clause names what it guards against; an `except ExecutionError` that handles some kinds calls `reraise_unless(error, ...)` first.

**Later decisions of 2026-11-26 (Q7 to Q10, see the decisions log):** Q7 internal errors say they are a bug and give `report_url`; Q8 the JSON-LD writer's `OSError` for a triple term is `ExecutionError` kind `unsupported`, context `JSON-LD serialize` (other file and OS errors unchanged); Q9 `nesting` is merged into `limit`; Q10 `term` is merged into `rdf`.

## (b) Every old class

Stage 0 (de21b3a7): `StarLayerError` is new. `ShapeError`, `ShapeCompileError`, `MetaShaclError`, `ExecutionError` moved to `starlayer/errors.py` (same objects, re-exported by `starlayer.shacl`); `ShapeError` stopped being a `ValueError` (the breaking change that matters most to callers).

| Old class (old base) | Stage | New | Reason |
|---|---|---|---|
| `ReasoningTimeoutError(RuntimeError)` | 1 | `ExecutionError` kind `timeout` (a crashed reasoner subprocess: `inference`) | The old class reported a crash as a timeout. |
| `InconsistentOntologyError(RuntimeError)` | 1 | `ExecutionError` kind `inconsistent` | One class and a kind. |
| `RuntimeError` for missing `owlready2` / rustdl | 1 | `ImportError`; a broken Java runtime is `ExecutionError` kind `inference` | A missing package is not a run failure. |
| `SparqlSyntaxError(SyntaxError)` | 2 | `FormatError` kind `sparql` (`why`, `line`, `col`, `pos` set by the parser, never parsed from a message) | Malformed text. |
| `SQEError`, `SQEValidationError` | 2 (and 0da83084) | `FormatError` kind `sparql`; shape problems of a tree are reported by `sqe_validate()` in a `ValidationReport` | A tree is data; `sqe_parse_to_tree` no longer validates. |
| `SPARQL12ConformanceError` | 2 | `FormatError` kind `sparql`, context `VERSION` | A bad `VERSION` declaration. |
| pyoxigraph `SyntaxError` / `RuntimeError` at `query()`, `update()` | 2 | `FormatError` kind `sparql` / `ExecutionError` kind `query` | One class for a malformed query, whichever layer found it. |
| "nested too deeply" (`RecursionError`, several classes) | 2, 5, 6 | `ExecutionError` kind `nesting` | The cause is the limit, not the document. |
| `SRLError` (base, `ValueError`) | 3 | gone; `StarLayerError` is the base | Catch-all by path. |
| `SRLParseError` | 3 (de211be6) | `FormatError` kind `srl` | Malformed SRL text. |
| `SRLDecodeError` | 3 | `FormatError` kind `srl`, context `srl: tree` | Damaged tree. |
| `SRLEvalError` | 3 | `FormatError` kind `srl` (unbound head variable; bad `DATA` triple) | §4.2 breach or bad data text. |
| `StratificationError` | 3 | `ExecutionError` kind `rule`, context `stratification` | The rule set cannot be run (a maintainer guide at the time; the plan proposed `FormatError`). |
| `SRLImportError` | 3 | `ExecutionError` kind `import` (loader failed); `FormatError` kind `srl` (text is not a rule set) | Two causes, two classes of result. |
| `SRLImportsNotSupportedError` | 3 | `ExecutionError` kind `import` | Imports never resolved at run. |
| `SRLUnresolvedImportsWarning` | removed before step A (c986705a, de211be6) | an `sh:Warning` in `srl_validate()` | Not an error scheme matter; listed because a guide cell still prints it. |
| `BasicEncodingError` | 4 | `FormatError` kind `rdf`, context `rdf:PropositionForm encoding` | Damaged encoding. |
| `InvalidTripleTermError(ValueError)` | 4 | `FormatError` kind `term`, context `triple term` | Malformed term. |
| `ManchesterSyntaxError(SyntaxError)` | 5 | `FormatError` kind `manchester` (`why`, `line`; `col`/`pos` only where the tokenizer knows them) | Malformed text; `graph/manchester/errors.py` removed. |
| `CanonicalizationComplexityError(RuntimeError)` | 6 | `ExecutionError` kind `limit` | A cap was reached; new kind. |
| `EntailmentRewriteError(NotImplementedError)` | 6 | `ExecutionError` kind `unsupported` (no exact rewrite) / `nesting`; "not a query" is `FormatError` kind `sparql` | Well-formed query, no exact rewrite. |
| `SqeTextTooDeepError(ValueError)` | 6 | `ExecutionError` kind `nesting` | As the other depth limits. |
| `EndpointError(OSError)` | 6 | kept, now `(StarLayerError, OSError)` | A network failure is an I/O error; callers catch `OSError`. |
| `StarLayerFidelityWarning`, `_NotComputable`, `_InvalidInstance` | - | kept | A warning, and private control flow caught in its module. |
| 23 other raise sites (render gaps, internal states, a closed object) | 6 | see (b2) | By cause. |

(b2) Stage 6 builtin raises converted: 7 `NotImplementedError` render gaps in `sqe/to_text.py`, `sqe/expr_text.py` and the unmodelled WHERE element in `parse_sparql.py`, plus 3 in `srl.py`, all `ExecutionError` kind `unsupported`; the unrecognised rule body element (`srl_eval.py`, `srl_semantic_checks.py`, `TypeError`) and two impossible states (`pretty.py` `AssertionError`, `endpoint._term` `ValueError`), all kind `internal`; `ValueError("this Materialization is closed")` kind `rule`. (Review of 2026-11-26 changed three of these: the five body-element sites, the three render gaps in `srl.py` and the two `internal` ones, are now `FormatError` kind `srl`, context `rule body element`; the closed `Materialization` is a plain `ValueError` again; see "Review decisions Q1-Q6" in the decisions log.) "could not find the query's WHERE group" kind `unsupported`; an unknown entailment regime `NotImplementedError` to `ValueError`.

Still to convert (not done, the files belong to the concurrent Manchester vocabulary work): 10 `AssertionError("unhandled ... tag/kind")` in `graph/manchester/parser.py` (2), `graph/manchester/serializer.py` (2), `starontology/manchester/__init__.py` (6): kind `internal`, one mechanical edit (a `re.sub` of `raise AssertionError(f'unhandled ...')` to `raise ExecutionError(f'unhandled ...', kind="internal", context="Manchester parser")`; the three files already import `ExecutionError`).

## (c) Raise sites that stayed plain `ValueError` / `TypeError` (and other builtins), and why

The audit (an `ast` walk of the package, the reasoning package and `tools/`) leaves 127 `ValueError`, 53 `TypeError`, 18 `AttributeError`, 7 `KeyError`, 11 `NotImplementedError`, 6 `ImportError`, 2 `StopIteration` and the 10 Manchester `AssertionError`. Each group:

- **A bad argument at a public entry** (the large majority): unknown `format` / `rdf_version` / `bnode_labels` / `mode` / `recompute` / `role` / `per` / `engine` / `timeout` combinations, `parse()` with no or two sources, wrong-typed graphs (`TypeError` naming `from_rdflib`), `literal()` with `lang` and a datatype or a `direction` without `lang`, `bind()` / pretty-printer prefix checks, `derive_shape` / `candidate_values` / `select_widgets` / `form_model` arguments, `align_blank_nodes`, `rdfc` algorithm names, `OrderedItems` index, codekg `queries.py`, `notebook_links.py`, `symbol_index.py`. Fixed by changing the argument.
- **A call refused by this object**, also fixed by changing what you pass: `StarLayerGraph` writing a quad of another graph, `update()` naming another graph or scoped to a blank-node graph (`update_scope.py`), `EndpointBackedStore` clear/add of another graph, a call on a closed `Materialization`, a named-graph dataset into a one-graph format, `pretty` of a dataset, `value()` finding more than one match (step C), "the document has named graphs; parse it into a StarLayerDataset" (string-matched on Oxigraph's message, `core.py`), "the graph holds no / already holds a `manch:OntologyDocument`", `value_check` literal on an inverse path. (Moved to `unsupported` on 2026-11-26: writing a blank node that came from the endpoint, `relevant_subgraph` given a DESCRIBE or a SERVICE query, `to_rdf11` direction policy `"error"`, an unregistered entailment name.)
- **`NotImplementedError` (11)**: the wrapper methods that do not exist on this object: `endpoint.py` 3, `execution/run.py` 4 (a prepared query object, initBindings with a blank node), `core.py` 4 (`Graph` protocol stubs). `check.py` catches them with `ValueError` for the engine check.
- **`ImportError` (6)**: missing `rdflib`, `owlready2`, rustdl, `starlayer-reasoning`, an old pyoxigraph.
- **`AttributeError`, `KeyError`, `StopIteration`**: `__getattr__` of modules and lazy objects, `Result.__getitem__`, `qnames.compute_qname(generate=False)` ("no prefix is bound"), the ontology registry lookup, `TreeIndex` and detached iterators, `codekg` lookups.
- **`OSError` from Oxigraph's `serialize()`** (JSON-LD with RDF 1.2 content) and `FileNotFoundError` from `parse()`: I/O, not converted.
- **`assert`-style impossible states**: none are left in `starlayer/` other than the 10 Manchester ones above.

## (d) Behaviour changes callers will notice

1. `except ValueError` no longer catches a wrong shapes graph (`ShapeError` family): name `ShapeError`.
2. `parse()`, `query()`, `update()`: a malformed document or query is `FormatError` (kind `rdf` / `sparql`), not `SyntaxError`; an engine failure is `ExecutionError` kind `query`, not `RuntimeError`. A missing file is still `FileNotFoundError`.
3. `parse_term`, `to_python` (bad lexical form), `literal()` / `graph_name()` / `expand_curie` with invalid IRI, language tag or CURIE: `FormatError` kind `term`, not `ValueError`. `parse_term(5)` is `TypeError`. `graph.items()` of a bad list: `FormatError` kind `rdf`.
4. OWL-DL reasoning: `ExecutionError` kinds `inconsistent`, `timeout`, `inference`; a missing `owlready2` is `ImportError`, not `RuntimeError`; a crashed reasoner is no longer reported as a timeout.
5. SRL: an unorderable rule set is `ExecutionError` kind `rule`; an unresolved or unloadable import is kind `import`; text, tree, `DATA` and §4.2 problems are `FormatError` kind `srl`; `parse_ruleset` does not validate (earlier change).
6. Manchester: `FormatError` kind `manchester` / `owl`; the module `starlayer.graph.manchester.errors` is gone; a graph Manchester cannot write is `ExecutionError` kind `unsupported`.
7. An `entailment=` name that is not a registered regime (text or IRI; D-Entailment included): `ExecutionError` kind `unsupported`, context `entailment regime`, the message lists the regimes and the closest name (was `NotImplementedError`); a value that is neither text nor an IRI is `TypeError`; `ValueError` stays for an empty collection, OWL-Direct combined with another regime, `engine=`/`timeout=` without OWL-Direct, a bad `recompute` or `engine`. A query-time entailment with no exact rewrite: `ExecutionError` kind `unsupported`.
8. RDFC-1.0 symmetric structure: `ExecutionError` kind `limit` (was `RuntimeError`); `rdfc.CanonicalizationComplexityError` is no longer importable.
9. `sqe_tree_to_text` and the SRL renderers raise `ExecutionError` kind `unsupported` where they raised `NotImplementedError`; `sqe_validate()` now reports such a tree instead of raising.
10. A call on a closed `Materialization`: `ValueError`, as before the scheme. `max_iterations` and `max_triples` failures: `ExecutionError` kind `limit` (was `rule`). `relevant_subgraph` with DESCRIBE or SERVICE, an endpoint-origin blank node written back, and `export_rdf11(direction_policy="error")`: `ExecutionError` kind `unsupported` (were `ValueError`). A hand-built rule set with something that is not a body element, and a goal pattern whose predicate is a literal, blank node or triple term: `FormatError` kind `srl`.
11. `EndpointError` is also a `StarLayerError`.
12. Earlier, outside the stages (bd2fd7c0): `meta_validate`, `sqe_validate`, `srl_validate`, `manchester_validate` return a `ValidationReport`, not a tuple.
13. `except StarLayerError` is available as one catch-all.

## (e) Open questions and judgment calls to review

1. **SHACL caps.** DECIDED 2026-11-26 (Q1): `max_iterations` / `max_triples` failures are kind `limit`, as the RDFC-1.0 cap; `timeout` stays its own kind.
2. **Term text as an argument** (stage 4). DECIDED 2026-11-26 (Q2): term text given as an argument stays `FormatError` kind `term`; a choice (a direction) stays `ValueError`; pinned by a test.
3. **Unknown entailment regime.** DECIDED 2026-11-26 (Q3): `ExecutionError` kind `unsupported`. Open: a `sh:entailment` in a shapes graph that names no registered regime is still `ShapeCompileError` (`declared_regimes`), because the shapes graph is the wrong thing; say if it should be `unsupported` too.
4. **The test "fixed by changing the argument".** DECIDED 2026-11-26 (Q4): valid input the library cannot handle is `unsupported`; a value outside a closed choice, contradictory options or a wrong target stay `ValueError`. Changed: `relevant_subgraph` (DESCRIBE, SERVICE), the endpoint blank-node refusal, `interop` direction policy `"error"`. Kept: `update()` naming another graph, blank-node-graph scoping, a quad of another graph, `EndpointBackedStore` clear/add of another graph.
5. **An unrecognised rule body element.** DECIDED 2026-11-26 (Q5): `FormatError` kind `srl`, context `rule body element` (a rule set built or edited by hand; the parser cannot produce one), at all five sites.
6. **`Materialization` closed.** DECIDED 2026-11-26 (Q6): plain `ValueError`.
7. **`internal` for guard states** (pretty writer, endpoint skolemization): reported as a bug in StarLayer; no `assert`.
8. **`FileNotFoundError` and Oxigraph's serialize `OSError`** are not wrapped.
9. **Deep nesting is `ExecutionError` `nesting`, not `FormatError`** (plan question 9): a caller who catches `FormatError` for a hostile query misses it.
10. **Kinds `manchester` / `owl`, `rdf` / `term`, `import`**: could merge; `import` now serves every import path (see section (h)).
11. **`EndpointError` has two bases**; the alternative was `ExecutionError` kind `endpoint` plus a `status`.
12. **Free-text `context`.** Context strings are not a registry; a reader can only match on text.
13. **Generated API docs** (`docs/generated/api-*.generated.md`) still name `CanonicalizationComplexityError`; regenerate with `scripts/generate_api_docs.py` in its own commit (AGENTS.md: generated files separately). I did not.
14. **Pre-existing failures, not from this work**: `tests/repo/test_renumber_guides.py` two tests (fail at the parent commit too).
15. **Guides and the workbench** are not edited (instructions); the lists below are what remains for them.

## (f) Guide cells that must change

Verified against the current notebooks on 2026-11-26 (`docs/guides/*.ipynb`, grepped for every removed class name, for `except` clauses and for printed exception names). Guides do not run under the new library until these change (the failing ones are marked **code**). 03.02 and 03.03 are done.

**02.04-graph-content**

- `27fceecb` (markdown, section 02.04.1). Old: "It raises `ValueError` when `.value` is not valid for the datatype (`abc` for `xsd:integer`), and `TypeError` for a `NamedNode` or `BlankNode`." New: "It raises `FormatError` (kind `"term"`) when `.value` is not valid for the datatype (`abc` for `xsd:integer`), and `TypeError` for a `NamedNode` or `BlankNode`." Old: "Text that is not exactly one RDF term raises `ValueError`." New: "Text that is not exactly one RDF term raises `FormatError` (kind `"term"`)." (`literal("5", XSD.integer, lang="sv")` stays `ValueError`: leave that sentence.) Optional addition: "An invalid IRI or language tag raises `FormatError` (kind `"term"`) too."
- `0e389edf` (**code**). Old: `except (ValueError, TypeError) as error:` with `from starlayer.graph import XSD, literal, parse_term, to_python`. New: add `from starlayer.errors import FormatError` and `except (FormatError, TypeError) as error:`. Output line "ValueError: 'abc' is not a valid integer" becomes "FormatError: 'abc' is not a valid integer" (`TypeError: only a literal has a Python value, not NamedNode` unchanged).
- `a2e50002` (markdown). Old: "It raises `ValueError` for a list that is not well formed: a cycle, or a list node without exactly one `rdf:first` and one `rdf:rest`." New: "It raises `FormatError` (kind `"rdf"`) for a list that is not well formed: a cycle, or a list node without exactly one `rdf:first` and one `rdf:rest`."

**02.07-owl-dl-reasoning** (new in this list)

- `ae0d6817` (markdown). Old: "OWL 2 DL reasoning raises `InconsistentOntologyError`." New: "OWL 2 DL reasoning raises `ExecutionError` of kind `\"inconsistent\"`."
- `b87b0ce5` (**code**). Old: `from starlayer_reasoning.owl_dl import InconsistentOntologyError` ... `except InconsistentOntologyError as e:` ... `print("OWL-Direct raises InconsistentOntologyError:\n", e)`. New: `from starlayer.errors import ExecutionError`; `except ExecutionError as e:` followed by `if e.kind != "inconsistent": raise`; `print("OWL-Direct raises ExecutionError (kind inconsistent):\n", e)`. The output header "OWL-Direct raises InconsistentOntologyError:" changes the same way; the message text is unchanged.

**02.08-manchester-syntax**

- `709876ac` (markdown). Old heading "## 02.08.4 `ManchesterSyntaxError`"; New: "## 02.08.4 Manchester syntax errors". Old: "raises a `ManchesterSyntaxError`." New: "raises a `FormatError` (kind `\"manchester\"`; `why` is the reason and `line` the line where it is known)." Old: "are each rejected with a `ManchesterSyntaxError`." New: "are each rejected with a `FormatError`." (`ManchesterSyntaxError` also in `06.05` `b2d88339`, below.)
- `a4e85f77` (**code**). Old: `from starlayer.graph.manchester.errors import ManchesterSyntaxError` and two `except ManchesterSyntaxError as e:`. New: `from starlayer.errors import FormatError` and `except FormatError as e:` (the two `print(f"Rejected as expected: {e.why}")` lines and their outputs are unchanged). The cell is also affected by the in-progress Manchester work; recheck after it.

**03.04-sparql-entailment** (new)

- `7a0e5d05` (markdown). Old: "any other value (such as `ENTAILMENT.D`, which is a recognized regime IRI but not implemented) raises `NotImplementedError` rather than returning an answer that ignores the regime." New: "... raises `ValueError` rather than returning an answer that ignores the regime."
- `7d8d5b33` (**code**, output). Old: `except (NotImplementedError, ValueError) as error:`; output "entailment=D:                  NotImplementedError: entailment must be one of ..." New: `except ValueError as error:`; the output line starts "entailment=D:                  ValueError: entailment must be one of ...".
- `a1c2e304` (markdown). Old: "`ENTAILMENT['OWL-Direct']` raises `InconsistentOntologyError` instead." New: "`ENTAILMENT['OWL-Direct']` raises `ExecutionError` of kind `\"inconsistent\"` instead."

**04.02-srl-running-rule-sets**

- `e1000006` (markdown). Old: "They reject a rule set that has no valid order by raising `StratificationError`." and "so StarLayer rejects them with `StratificationError`." New: "... by raising `ExecutionError` (kind `\"rule\"`)." and "... rejects them with `ExecutionError` (kind `\"rule\"`)."
- `c0a10006` (**code**). Old: `from starlayer.sparql.srl_eval import StratificationError` and `except StratificationError:` with `print(f"{label:48} StratificationError")`. New: `from starlayer.errors import ExecutionError, reraise_unless`; `except ExecutionError as error: reraise_unless(error, "rule")` then `print(f"{label:48} ExecutionError (kind rule)")`. In the printed output the four rejected rows read "ExecutionError (kind rule)" instead of "StratificationError" (accepted rows unchanged). Widen the column if "ExecutionError (kind rule)" does not fit.
- `e1000007` (markdown table, section 04.02.6). Old rows: "`StratificationError`" for "a cycle goes through a `NOT { }`..."; "`SRLImportError`" for "an import cannot be read, or is not a valid rule set"; "`SRLImportsNotSupportedError`" for "a rule set that still has `IMPORTS` is run". New: "`ExecutionError` (kind `\"rule\"`)"; split the import row: "an import cannot be read" is "`ExecutionError` (kind `\"import\"`)" and "an import is not a valid rule set" is "`FormatError` (kind `\"srl\"`)"; "`ExecutionError` (kind `\"import\"`)" for the unresolved-imports run.
- `d9a10006` (**code**, output). Old: `except StratificationError as e:` and `print("Case 3 - ...cannot be ordered:", type(e).__name__)`; this cell needs the import of `StratificationError` from `c0a10006`. New: `except ExecutionError as e:` and `print("Case 3 - the same rule with a plain NOT cannot be ordered:", type(e).__name__, f"(kind {e.kind})")`; the output ends "ExecutionError (kind rule)" instead of "StratificationError".
- `a6b6c602` (**code**). Old: `from starlayer.sparql.srl_eval import SRLImportsNotSupportedError` ... `except SRLImportsNotSupportedError as error:`. New: `from starlayer.errors import ExecutionError` ... `except ExecutionError as error:` (message unchanged). The comment "# Parse without a loader: this warns that the imports are not resolved" and the stored stderr output with `SRLUnresolvedImportsWarning` are stale (the warning class was removed earlier): the parse does not warn; `srl_validate()` reports the unresolved imports.

**04.03-srl-more-features**

- `n12-group-md` (markdown). Old: "A rule that groups over its own output cannot be ordered and is rejected with a `StratificationError`." New: "... is rejected with an `ExecutionError` (kind `\"rule\"`)."

**06.05-manchester-syntax-as-rdf**

- `b2d88339` (markdown). Old: "raises `ManchesterSyntaxError` (see section 02.08.4 ...)". New: "raises `FormatError` (kind `\"manchester\"`; see section 02.08.4 ...)". (`6b2e0001` / `6b2e0002`: a second document into a graph is `ValueError`; unchanged.)

**appendix-b2-dl-reasoning-examples** (new)

- `1af6f1ac` (markdown). Old: "If `owlready2` is not installed, `infer()` raises a `RuntimeError` that says so, and the cells that depend on it fail with it." New: "... raises an `ImportError` that says so ...". The sentence "If Java isn't found or isn't configured correctly, an error message is raised." becomes "... `infer()` raises an `ExecutionError` of kind `\"inference\"`."
- `8447c470` (**code**): `from starlayer_reasoning.owl_dl import InconsistentOntologyError` becomes `from starlayer.errors import ExecutionError`.
- `319385b0`, `0cfb6b13` (**code**): `except InconsistentOntologyError:` becomes `except ExecutionError as error:` with `reraise_unless(error, "inconsistent")` (import `reraise_unless` from `starlayer.errors`) before `return False`, so a timeout is not read as "inconsistent".
- `497e70e3` (**code**, output): `except InconsistentOntologyError as e:` and `status = f"InconsistentOntologyError (expected): {e}"` become `except ExecutionError as e:` (check `e.kind == "inconsistent"`) and `status = f"ExecutionError, kind inconsistent (expected): {e}"`; the output line changes the same way.
- `181958f0` (markdown). Old: "`InconsistentOntologyError` fires on the *whole* problem" New: "An `ExecutionError` of kind `\"inconsistent\"` fires on the *whole* problem".

**Cells that need no change** (checked): `02.03` `6c0dccde` and `03.01` `e5a7c9db` (`ValueError` for a graph that acts on another graph), `05.02` `e9020030`/`e9020031`, `05.06`, `05.08` `ed000012` (`ValueError`: no data graph), `06.05` `6b2e0002`, `07.01` `ba3d53f0` (`OSError` for JSON-LD, still raised), `07.02` `252791c5` (`OSError`: `ConnectionRefusedError` from the SERVICE call, still raised), `02.04` `a2e50007` (`KeyError`).

## (g) `../graph-workbench` lines that need changes

Verified against the current source on 2026-11-26. I ran the workbench's unit tests (not `tests/browser`) from a copy in the scratchpad, with its own virtualenv and the current StarLayer on `PYTHONPATH`, and applied the changes below to the copy: with them, `tests/test_paths.py` and `tests/test_validation_scoped.py` (3 tests) pass; before them those 4 tests failed. (Three other failures and the demos errors in the copy are missing directories of the copy, not StarLayer.) The workbench itself was not touched.

All in `src/graph_workbench/_starlayer.py` unless stated:

1. **Lines 716 and 730** (`check_shapes`, `check_shapes_after`): `meta_validate` returns a `ValidationReport`, not a tuple. `conforms, report, _text = meta_validate(shapes)` becomes `result = meta_validate(shapes)` and, after the `except MetaShaclError` clause, `return result.conforms, result.report_graph`; in `check_shapes_after` the same inside the `try` (`result = meta_validate(before, add=added, remove=removed)`, then `conforms, report = result.conforms, result.report_graph`).
2. **Line 612** (`shapes_graph_members` call in `shapes_graph_members`-wrapper): `except ValueError:` becomes `except ShapeError:` (the library raises `ShapeCompileError` for an unresolvable `owl:imports`; `ShapeError` is already imported at line 34).
3. **Line 215** (`_to_python(term)`): `except ValueError:` becomes `except FormatError:` (bad lexical form is `FormatError` kind `term`; add `from starlayer.errors import FormatError` near line 34).
4. **Lines 1178 and 1192** (`parse_literal`, `parse_term`: `_parse_term(text)`): `except ValueError as error:` becomes `except FormatError as error:`; the wrappers still raise `ValueError` for the callers.
5. **`edits.py` ~183, `nodeexpr.py` ~291, `web/app.py` ~1466 and ~1795** (`except ValueError` around `sl.parse_term(...)`): no change once item 4 is made, because `sl.parse_term` is the workbench's own wrapper and keeps raising `ValueError`. (They break only if the wrapper is changed to let `FormatError` through.) The same holds for `edits.py` ~168 (`sl.expand_name`, the workbench's own `ValueError`) and `evaluation.py` ~119 (`sl.walk_path`, the workbench's own `NotImplementedError`).
6. **`tests/test_paths.py` line 83**: `with pytest.raises(ValueError):` (comment "a ShapeError, which is a ValueError") becomes `with pytest.raises(sl.ShapeError):` with the comment "StarLayer refuses with a ShapeError, which is not a ValueError".
7. **Nothing else found.** No workbench file names a removed class (grepped for all 20 names); the `except Exception` clauses with a stated reason (about 25) work unchanged with `FormatError` / `ExecutionError` (they show `str(error)`); no `except SyntaxError` or `except RuntimeError` exists; `tests/test_shapes_tab.py:5055` and `tests/test_forms.py` catch the workbench's own `ValueError`.

## (h) Imports: one rule on every path (2026-11-26, maintainer decision)

A graph, shapes graph or rule set that declares imports must resolve them or raise `ExecutionError` kind `import` (`error.unresolved`: the IRIs; `context` `owl:imports <iri>`). An import is satisfied when its IRI is a subject of the graph after resolution (present, a built-in registry ontology, or loaded; the `owl:versionIRI` of a present ontology counts; for SRL, when the loader produced a rule set). No loader, a loader that returns `None` or a graph without the IRI: the error (no silent skip). A loader that raises: wrapped, the original is `__cause__`. `ignore_imports=True` loads and checks nothing. One implementation, `graph/imports.py::resolve_or_raise`; `starlayer.graph.unresolved_imports(graph)` lets an application load what is missing and call again.

Applied to: `StarLayerGraph.resolve_imports()` (`loader=`, new `ignore_imports=`), SHACL `validate()`, `validate_each()`, `apply_rules()` and `StarShaclProcessor` for the shapes graph and `ont_graph` (`shapes_graph_loader=`; was `ShapeCompileError` with no loader and a skip for `None`), SRL `resolve_imports()`, `parse_ruleset()`, `infer()`, `query()`, `plan()`, `materialize()` (`imports_loader=`, new `ignore_imports=`), and `infer()` / `query(entailment=)` for the OWL regimes (new `imports_loader=`, `ignore_imports=`). Not applied (listed in the decisions log): the data graph of `validate()`, `evaluate()`, `target_nodes()`, `extract_subgraph()`, `derive_shape()`, `meta_validate()`, `parse_ruleset()` without a loader. A non-IRI `owl:imports` object is `FormatError` kind `owl` for a graph and `ShapeCompileError` for a shapes graph.

**On the graph (2026-11-26, step 2).** The loader and the flag now belong to the graph: `StarLayerGraph(imports_loader=..., ignore_imports=...)` and the properties of the same names; `graph.resolved_imports()` is the one accessor every consumer calls (cached per store, dropped by any write, lazy). The data graph of `validate()` is resolved too (its imported triples go to entailment only); `evaluate()`, `target_nodes()`, `target_shapes()`, `extract_subgraph()`, `close_shape()`, `select_widgets()` and `derive_shape()` resolve the graphs they read and take `shapes_graph_loader=` and `ignore_imports=`. The per-call parameters override the graph's setting (`ignore_imports=None`: the graph's own). Details: the decisions log, `## Imports on the graph (2026-11-26)`.

Open questions: the loader parameter has four names (`loader=`, `shapes_graph_loader=`, `imports_loader=`, SRL's positional `loader`); whether the other shapes-graph readers listed above should take a loader and resolve too; whether `plan()` without a loader should keep raising.

Guide cells that describe the old import behaviour (not edited): 02.05 `eefe3036` ("An import that is already present, or that the loader cannot retrieve, is skipped": now an error; a document with no header is unresolved, not "fetched each time"); 02.05 `f1925477` (no change: the loader's graph has the header); 04.02 `a6b6c601` / `a6b6c602` (the unresolved rule set still cannot run; add that a loader that returns `None` is the same error and that `ignore_imports=True` runs the document's own rules), `a8b8c801` (add `materialize()` and `ignore_imports=`), `d9a10026` ("`plan(imports_loader=...)`": `plan()` without a loader now raises); 05.02 `e9020010` ("raises a `ShapeCompileError`" becomes `ExecutionError` kind `"import"`; a loader that returns `None` is no longer skipped; the imported graph must have the IRI as a subject) and `e9020011` (`from starlayer.shacl import ShapeCompileError` and `except ShapeCompileError` become `ExecutionError`, from `starlayer.errors`, test `error.kind == "import"`); 05.02 `c0f90001` (the settings table row for `ignore_imports`, `shapes_graph_loader`); appendix-d `a3ebda5c` and `8b73eda0` already describe the rule.

