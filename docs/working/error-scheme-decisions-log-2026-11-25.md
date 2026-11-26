
## Stage 3: SRL

Six SRL classes removed (no alias): each maps by cause. Data they carried goes in `context` (a string) and the message.

| Old | New | Reason |
|---|---|---|
| `SRLError(ValueError)` (base) | gone; `StarLayerError` is the base | A catch-all by path; the cause is in the class and kind now. It was a `ValueError`, which the scheme reserves for bad arguments. |
| `SRLDecodeError` | `FormatError(kind="srl", context="srl: tree")` | A damaged or hand-edited `srl:` tree is malformed data. An undefined child order stays `FormatError` kind `"rdf"` (graph/ordinals.py). |
| `SRLImportError`, loader failed | `ExecutionError(kind="import", context="IMPORTS <iri>")` | The document could not be loaded: a failure of running the import, not of the text. |
| `SRLImportError`, imported text not a rule set | `FormatError(kind="srl", context="IMPORTS <iri>")` | The text is malformed SRL (as the plan said). |
| `SRLImportsNotSupportedError` | `ExecutionError(kind="import", context="IMPORTS <a>, <b>")` | The rule set cannot be run until its imports are resolved (§4.5); the unresolved IRIs are in the context and message. |
| `StratificationError` | `ExecutionError(kind="rule", context="stratification")` | The rule set cannot be ordered, so it cannot be run (a maintainer guide for this stage; the plan had proposed `FormatError("srl")`). Existing kind "rule" ("the rule set failed as a whole"), no new kind; the cycle itself is not carried (the old class did not carry it either). |
| `SRLEvalError`, unbound head variable at instantiation | `FormatError(kind="srl", context="rule head")` | A §4.2 breach, as `srl_semantic_checks` already raises at run (normally caught before this point). |
| `SRLEvalError`, bad `DATA` triple (2 sites) | `FormatError(kind="srl", context="DATA")` | The `DATA` text is not a valid RDF triple. |

New kind: `ExecutionError.KINDS` gains `"import"` (the plan listed it): no existing kind says "a document the rule set needs could not be loaded or was never resolved". `only_kind(error, "rule")` is used where `srl_validate` turns a stratification failure into a report result.

Left alone on purpose (not argument errors, but not SRL-specific classes): 3 `NotImplementedError` render gaps in `srl.py` (the plan puts them in stage 6, kind `"unsupported"`), `TypeError` for an unrecognised body element in `srl_eval.py` and `srl_semantic_checks.py` (plan: stage 6 `"internal"`), and `ValueError("this Materialization is closed")` in `srl_eval.py` (a call on a closed object, not a bad argument: maintainer to decide; proposed `ExecutionError` kind `"rule"` or keep). The internal `except RuntimeError` clauses around Oxigraph in `srl_eval.py` keep catching on purpose (they test the engine's message and fall back).

## Stage 5: Manchester and OWL

| Old | New | Reason |
|---|---|---|
| `ManchesterSyntaxError(SyntaxError)` | `FormatError(kind="manchester")`, same message text, `why`, `line`; `col`/`pos` set only where the tokenizer knows the document offset (cursor errors have only a token's local text, so `pos`/`col` are `None` rather than a wrong number) | Malformed text. Class and `graph/manchester/errors.py` removed, no alias. |
| SWRL `Rule:` rejection | `FormatError(kind="manchester", context="SWRL Rule: unsupported")` | The W3C Manchester grammar has no rules, so for the language the text is malformed; message unchanged. |
| `run_guarded` / render `RecursionError` | `ExecutionError(kind="nesting")` | As stage 2. |
| tree decoders: unrecognized property-expression / class-expression / data-range node | `FormatError(kind="manchester", context="manch: tree")` | A malformed tree is malformed data; kind `manchester` (the `manch:` vocabulary), `rdf` stays for ordinal ties. |
| "graph holds no manch:Document", "already holds a manch:Document" | stay `ValueError` | The graph argument of a public call is the wrong one. |
| serializer: unrecognized blank node as name / class expression / data range / property expression, restriction without onProperty or matching shape, qualified cardinality without filler, facet without predicate, cyclic or malformed rdf:List (10 sites) | `FormatError(kind="owl")`, context names the node | The input graph is not valid OWL-in-RDF. |
| serializer: non-IRI name (triple term), base-direction literal, subclass axiom between two class expressions, version IRI on an anonymous ontology (4 sites) | `ExecutionError(kind="unsupported")` | Well-formed graph Manchester syntax has no form for. New kind `"unsupported"` added to `ExecutionError.KINDS` here (commit 569adb89; stage 6 can reuse it). |

## Stage 4: RDF documents and terms

Commit 53eaf705. Classified by cause; the context goes in `context` and the message; no new kind (the two kinds `"rdf"` and `"term"` existed).

| Old | New | Reason |
|---|---|---|
| Oxigraph `SyntaxError` from `parse()` (all formats, also through a dataset) | `FormatError(kind="rdf", context=<path or URL, else "<format> document">, line=lineno, col=offset)` | A malformed document. `lineno` / `offset` are attributes of Oxigraph's error (None for RDF/XML, which gives none); nothing is read out of the message. Only the exact `SyntaxError` class is converted, so a `FormatError` / `ExecutionError` raised by a format plugin (Manchester, stage 5) passes through. |
| `ntversion` bad `VERSION` line (`SyntaxError` built by hand) | `FormatError(kind="rdf", context="N-Triples VERSION", line, col)` | Raised directly with the position the code knows; `str()` keeps the old "Parser error at line N column M: ..." text. |
| `ValueError("the document has named graphs; parse it into an StarLayerDataset")` (core.py, string-matched on Oxigraph's message, and `_retarget`) | unchanged `ValueError` | The document is fine; the target is wrong (a bad argument for this call). The string match stays (noted in the plan for a later pre-check by format). |
| unknown `format` / `rdf_version` / `bnode_labels`, `parse()` with no or two sources, `data=5` | unchanged `ValueError` / `TypeError` | Bad arguments at the entry of a public call. |
| missing or unreadable file (`FileNotFoundError`) | unchanged `OSError` | An I/O failure: there is no document to be malformed. (The brief said "OSError-from-parse"; I found none that is about the document: Oxigraph reports bad bytes as `SyntaxError`.) |
| `graph.items()` / `rdflist.list_cells` cycle or bad node (`ValueError`) | `FormatError(kind="rdf", context="rdf:List at <head>")` | Data that is not a well-formed list (plan: `core.py:381,386`, `rdflist.py:44,48`). `set_list` swallows only `FormatError` now. |
| `BasicEncodingError` (13 raises in `interop.py`, `from_basic` and `to_basic`) | `FormatError(kind="rdf", context="rdf:PropositionForm encoding")` via a private `_encoding_error()`; class removed, not exported | The data is not a valid encoding (or already uses the vocabulary). Nothing caught it in the library. |
| `to_python` bad lexical form (`ValueError`) | `FormatError(kind="term", context="xsd:<type> literal")` | Text that is not valid for its datatype. A non-literal stays `TypeError`. |
| `parse_term` not exactly one term (`ValueError`) | `FormatError(kind="term")` | Malformed term text. A non-`str` argument is now `TypeError` (was "not a term" `ValueError`); empty text is `FormatError`. |
| `literal()` invalid language tag or datatype IRI (Oxigraph `ValueError`), `graph_name("a b")`, `expand_curie` (not a CURIE, bad IRI) | `FormatError(kind="term")` through a new helper `terms.to_iri(text, context)` | Rule I chose: an argument whose value is term text that the RDF syntax rejects (IRI, language tag, CURIE) is `term`, so code that takes such text from a person or a document catches one class. |
| `literal()` with `lang` and a datatype, `direction` not `ltr` / `rtl`, `direction` without `lang` | unchanged `ValueError` | A wrong combination or choice of arguments. |
| `rdflib_bridge.foreign_to_engine` (a relative IRI, bad bnode id or language tag of an rdflib term; `ValueError`) | `FormatError(kind="term", context="rdflib term")` | It is data from another library, not an argument; `from_rdflib` / `graph_from_rdflib` surface it. |
| `InvalidTripleTermError(ValueError)` (`triple_term.py`, one raise in `TripleTermNode.validate()`) | `FormatError(kind="term", context="triple term")`; class removed | A triple term nested in subject or predicate is a malformed term. The class docstring's rules moved into the `validate()` docstring. |

Left alone on purpose: `sparql/_oxterms.py` and the manchester parser catch Oxigraph's own `ValueError` from `NamedNode(...)` directly (they call the engine, not the helpers); `interop.py:345,422,430` and `endpoint.py` ValueErrors belong to stage 6; `rdflib_model/*` constructor `ValueError`s are bad arguments; `bind()` / `pretty.py` prefix and base checks are bad arguments. The `except SyntaxError` of `execution/run.py` is stage 2.

Effect on SRL (not edited): `TripleTermNode.validate()` is called from `srl.py` `_decode_term` (line ~400), inside `_decode_rule`; `srl.py` lines ~484-488 do `except FormatError: raise` before `except (ValueError, ...)`, so a hand-edited `srl:` tree with a nested triple term in subject position now surfaces as kind `"term"` (before: `InvalidTripleTermError` -> kind `"srl"`, context `"srl: tree"`). No test in `tests/sparql` covers it (1534 srl/error/format tests pass). The SRL owner may re-wrap it in `_tree_error`.

Open: (1) the IRI / language-tag-as-argument rule above (alternative: keep `ValueError` for every argument of `literal()` / `graph_name()`); (2) `FileNotFoundError` stays `OSError` (alternative: wrap as `rdf`); (3) `test_custom_functions::test_the_functions_apply_to_that_call_only` and two `test_renumber_guides` tests fail at HEAD, not from this stage.

## Stage 6: everything left (2026-11-26)

Decisions made by the implementer (the maintainer reviews them in `docs/working/error-scheme-summary-2026-11-26.md`). Rule applied throughout: a refusal of the call's own argument (fixed by changing the argument) stays a plain `ValueError` / `TypeError`; well-formed input inside a document, tree or query that the library cannot represent or render is `ExecutionError` kind `"unsupported"`; an impossible internal state is kind `"internal"`.

| Old | New | Reason |
|---|---|---|
| `CanonicalizationComplexityError(RuntimeError)` (`rdfc_native.py`, 2 raises) | `ExecutionError(kind="limit", context="RDFC-1.0 canonicalisation")` through a private `_too_complex()`; class and its exports (`rdfc`, `rdfc_native.__all__`) removed | A cap of the library was reached (RDFC-1.0 §7.1). New kind `"limit"` (commit 3d5edbcf, alone). `bnodes.short_bnode_labels` falls back only on `only_kind(error, "limit")`. SHACL's `max_iterations` / `max_triples` stay kind `"rule"` (open question: the plan proposed moving them to `"limit"`; the same cause then has two kinds today). |
| `EntailmentRewriteError(NotImplementedError)`: "SELECT * / DESCRIBE * with no variable", "could not be written out as SPARQL" | `ExecutionError(kind="unsupported", context="entailment rewrite")` | Well-formed query with no exact rewrite. Message text unchanged. |
| the same, "nested too deeply for the entailment rewrite" | `ExecutionError(kind="nesting")` | As stages 2 and 5. |
| the same, "needs a query, not an update" | `FormatError(kind="sparql", context="entailment rewrite")` | The text is not a query, the same cause as `graph.query(<update>)`, which Oxigraph reports as a syntax error. |
| `NotImplementedError` for a regime the wrapper does not take (`core.py` `query(entailment=)`, `rewrite_for_entailment`) | `ValueError` | A bad value of an argument at a public entry, fixed by changing the argument; it is not "a method the object does not have". Guide 03.04 changes. |
| `SqeTextTooDeepError(ValueError)` (`to_text.py`) | `ExecutionError(kind="nesting", context="sqe: tree to text")`; class removed | As the other "nested too deeply" cases. `sqe_validate` (`shapes.py`) catches the kinds nesting and unsupported to report "cannot be written out as SPARQL text", as it did for `SqeTextTooDeepError`. |
| 7 `NotImplementedError` render gaps in `sqe/to_text.py` (5), `sqe/expr_text.py` (2) and the unmodelled WHERE element in `parse_sparql.py` | `ExecutionError(kind="unsupported", context="sqe: tree to text" / "sqe: tree encoding")` via one helper `expr_text._no_text()` | Well-formed tree the renderer has no form for. `sqe/rewrite.py` and the entailment rewrite catch kinds nesting and unsupported (they had caught `NotImplementedError`). |
| 3 `NotImplementedError` in `srl.py` (no encoding for a body element, no text for a term, no text for a body element) | `ExecutionError(kind="unsupported", context="srl: tree encoding" / "srl: text rendering")` | As the plan said. |
| `TypeError("unrecognized rule body element")` in `srl_eval.py` and `srl_semantic_checks.py` | `ExecutionError(kind="internal")` | `srl_ast.BodyElement` is exhaustive: reaching it is a bug. |
| `ValueError("this Materialization is closed")` | `ExecutionError(kind="rule", context="Materialization")` | A call on an object in the wrong state, not a bad argument. Closest existing kind; no new kind for one site. |
| `AssertionError("pretty writer did not converge")` (`pretty.py`) | `ExecutionError(kind="internal")` | An impossible state, reported as a bug in StarLayer. |
| `ValueError` "a blank node has no form in a SPARQL update that an endpoint would keep; it is skolemized first" (`endpoint._term`) | `ExecutionError(kind="internal")` | The caller skolemizes before it; reaching it is a bug. |
| `ValueError` "could not find the query's WHERE group" (`sparql_text.py`, initBindings) | `ExecutionError(kind="unsupported", context="initBindings")` | The query text is accepted by the engine; the text scan cannot place the binding. |
| `EndpointError(OSError)` | `EndpointError(StarLayerError, OSError)`, still an `OSError` | `except StarLayerError` now means "the library said no" without exceptions; `except OSError` for a network failure keeps working (guides, workbench). |
| `test_the_functions_apply_to_that_call_only` expected `RuntimeError` | now `raises_kind("query")` | The stage 2 boundary is right; the test followed. |

Kept on purpose (all decided by the rule above): every `ValueError` / `TypeError` of a public entry (about 130 sites in graph, shacl, sparql, starontology, reasoning, tools); the 11 `NotImplementedError` wrapper refusals (`endpoint.py` 3, `execution/run.py` 4, `core.py` 4) and `check.py`'s `except (ValueError, NotImplementedError)` for them; `ImportError` for a missing optional package; `AttributeError` / `KeyError` / `StopIteration` in dunder and lookup methods (`qnames` `KeyError` "no prefix is bound", `starontology` registry, `codekg`); the "refused for this object" `ValueError`s (`endpoint` writing another graph or a blank node that came from the endpoint, `update_scope`, `relevant_subgraph` for DESCRIBE or SERVICE, `interop` direction policy `"error"` and a named-graph dataset in a one-graph format, `value_check` literal on an inverse path); `OSError` from Oxigraph's `serialize()` (JSON-LD with RDF 1.2 content; a refusal of the engine, not converted); private control-flow classes `_NotComputable` and `_InvalidInstance`; `StarLayerFidelityWarning`. The SHACL `except Exception` clauses with a stated reason (step C) were not touched.

Not done: 10 `AssertionError("unhandled ... tag/kind")` in `graph/manchester/parser.py` (2), `graph/manchester/serializer.py` (2) and `starontology/manchester/__init__.py` (6): they are kind `"internal"` by the scheme, but the files belong to the concurrent Manchester vocabulary work; one mechanical edit remains (`future_enhancements.md` lists it).

Tests and docs: `tests/repo/test_error_scheme.py` gains `REMOVED_CLASSES` (19 names across stages 1 to 6; fails when one is found in the package, reasoning or tools source, `.py` or `.ttl`), a check that every `kind=` literal of `ExecutionError(` / `FormatError(` and every `only_kind(` argument is declared, and that every declared kind is raised somewhere. The curated knowledge graph (`tools/kg/codekg/curated`) named two removed classes in comments and one in `functionality.ttl`; changed. AGENTS.md carries the scheme, how to choose and the catch-clause rule; `shacl`, `graph` and `sparql` `CLAUDE.md` follow.
