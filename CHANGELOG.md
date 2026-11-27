# Changelog

All notable changes to StarLayer. The packages (`starlayer`, `starlayer-reasoning`, `starlayer-kg`) are released together under one tag.

## Unreleased (after the `v0.2.0` tag)

Changes from the error-scheme review of 2026-11-26. Several of them change what `v0.2.0` raises.

### Breaking

- **Error kinds merged.** `ExecutionError` kind `nesting` is now `limit`, and `FormatError` kind `term` is now `rdf`; the `context` says what was too deep or which term text was malformed. `nesting` and `term` no longer exist.
- **SHACL limits.** `max_iterations` and `max_triples` failures are `ExecutionError` kind `limit` (they were `rule`).
- **`max_iterations` is validated like `max_triples`.** It must be an `int` (not a `bool`), else `TypeError("max_iterations must be an int, not 'x'")`; a negative one is `ValueError`; zero is allowed (the first iteration then raises the `limit` error). `None` in the `StarShaclProcessor` constructor still means the default (1000); `None` on a call is a `TypeError` (it never meant "unlimited"). The limit message names the option: "rules did not reach a fixpoint within N iterations: raise max_iterations=".
- **`RuleResult.failures` (engine `apply_rules(raise_on_failure=False)`) holds the errors, not their messages.** Each item is the `ExecutionError` of a failed rule, with its `kind` and `context` (it was a list of strings). `ok` is unchanged; the public `RulesResult` never carried them.
- **`parse()` of a quad document into a single graph is decided by the quads, not by Oxigraph's message.** A TriG, N-Quads or JSON-LD document read into a `StarLayerGraph` is parsed whole first; if any quad is in a named graph it raises `ValueError("the document has named graphs; parse it into a StarLayerDataset")` and nothing of the document (its default-graph triples included) is added. A malformed document is still `FormatError` kind `rdf`. A quad document into a single graph is now held in memory while it is read.
- **One name for the imports loader: `imports_loader=`.** `loader=` of `graph.resolve_imports()` / `graph.resolved_imports()` / `starlayer.graph.imports` functions and `imports_loader=` of `validate()`, `validate_each()`, `apply_rules()`, `StarShaclProcessor` (constructor and methods), `evaluate()`, `target_nodes()`, `target_shapes()`, `extract_subgraph()`, `select_widgets()`, `close_shape()` and `derive_shape()` are renamed `imports_loader=`; SRL's `resolve_imports(ruleset, loader)` takes `imports_loader`. The old names are removed, with no alias. `ignore_imports=` is unchanged. The import error message names `imports_loader`.
- **Entailment names.** An entailment name that is not a registered regime is `ExecutionError` kind `unsupported` (it was `ValueError` or `NotImplementedError`), in `infer()`, `query()` and a shapes graph's `sh:entailment`. A value that is not text or an IRI is `TypeError`.
- **Valid input the library cannot handle is `unsupported`** (it was `ValueError`): `relevant_subgraph` given a `DESCRIBE` or a `SERVICE` query, writing a blank node that came from an endpoint, the `to_rdf11` direction policy `"error"`, and a triple term written as JSON-LD (it was an `OSError`).
- **A malformed rule body element** (a `RuleSet` built by hand) is `FormatError` kind `srl`.
- **A call on a closed `Materialization`** is `ValueError`.
- **One import rule on every path.** A graph, shapes graph or rule set that declares imports must resolve them or raise `ExecutionError` kind `import` (`error.unresolved` lists the IRIs). An import is satisfied when its IRI is a subject of the graph after resolution (present, a built-in registry ontology, loaded, or the `owl:versionIRI` of a present ontology; for SRL, when the loader produced a rule set). `StarLayerGraph.resolve_imports()` no longer skips an import with no loader or one the loader returns `None` for, and a loader that raises is wrapped (the original is `__cause__`); SHACL raises `ExecutionError` kind `import` (it was `ShapeCompileError`), no longer skips an import the loader returns `None` for, and also resolves `ont_graph`; `infer()` and `query(entailment=)` with an OWL regime raise for unresolved imports; `RuleSet.plan()` without a loader raises for a rule set with `IMPORTS`. `ignore_imports=True` (new on `resolve_imports()`, `infer()`, `query()`, `parse_ruleset()` and the `RuleSet` methods) loads and checks nothing.
- **`owl:imports` belongs to the graph.** A graph carries its own import settings, `StarLayerGraph(imports_loader=..., ignore_imports=...)` and the `imports_loader` / `ignore_imports` properties, and `graph.resolved_imports()` returns the triples its imports load (cached per store, dropped by any write, lazy: nothing is loaded until a consumer asks). Every consumer asks the graph: SHACL (`validate()`, `apply_rules()`, `evaluate()`, `target_nodes()`, `extract_subgraph()`, `close_shape()`, `select_widgets()`, `derive_shape()` ...), `infer()` and `query(entailment=)` for the OWL regimes, `resolve_imports()`. The per-call `loader=`, `imports_loader=`, `imports_loader=` and `ignore_imports=` override the graph's setting for one call. **Breaking:** the data graph of `validate()` (and of `evaluate()`, `target_nodes()`, `extract_subgraph()`, ...) is resolved too, so a data graph that declares an `owl:imports` that is not a subject of it, not built in and with no loader now raises `ExecutionError` kind `import` (set `ignore_imports=True` on the graph or the call, or give it a loader; its imported triples are visible to entailment only); `evaluate()`, `target_nodes()`, `target_shapes()`, `extract_subgraph()`, `close_shape()`, `select_widgets()` and `derive_shape()` resolve the imports of the graphs they read (they never did) and take `imports_loader=` and `ignore_imports=`; the `ignore_imports` parameters default to `None` (the graph's own setting) instead of `False`.
- **An `internal` error says so.** Its message starts "internal error (a bug in StarLayer, please report it at <address>)", and `error.report_url` holds the address.

- **A shapes graph's `sh:entailment` naming an unregistered regime** (a typo, D-Entailment) is `ExecutionError` kind `unsupported`, context `entailment regime`, with the message of `infer()` (it was `ShapeCompileError`).
- **`export_rdf11` of named graphs to Turtle, N-Triples or RDF/XML** is `ExecutionError` kind `unsupported` (it was `ValueError`); the message is the same.
- **`compute_qname()` / `qname()` of an IRI that cannot be written as a prefixed name** is `FormatError` kind `rdf`, context `prefixed name` (it was `ValueError`). `compute_qname(generate=False)` with no bound prefix is still a `KeyError`.
- **An OWL regime reaching the RDF/RDFS query rewrite** is `ExecutionError` kind `internal` (it was `ValueError`); `query()` answers the OWL regimes through the entailed copy, so only a bug in StarLayer gets there.
- **`.rows`, `.bindings` or `.triples` of a result of the wrong query form** (rows of an ASK, triples of a SELECT) is `ValueError` (it was `TypeError`).

### Added

- `ExecutionError.KINDS` and `FormatError.KINDS` map each kind to a one-line meaning (iterating them still gives the kind names).
- `ISSUES_URL` and `ExecutionError.report_url` in `starlayer.errors`.
- `starlayer.graph.unresolved_imports(graph)`, `ExecutionError.unresolved`, `imports_loader=` on `infer()` and `query()`.
- `StarLayerGraph(imports_loader=, ignore_imports=)` (and `StarLayerDataset`), the properties of the same names, `graph.resolved_imports()`, `graph.clear_imports_cache()`, `imports_loader=` / `ignore_imports=` on `evaluate()`, `target_nodes()`, `target_shapes()`, `extract_subgraph()`, `close_shape()`, `select_widgets()`, `derive_shape()` and the matching `StarShaclProcessor` methods.

## 0.2.0

### Breaking

- **One error scheme.** Everything the library raises on purpose derives from `StarLayerError`. The classes are `FormatError` (text or data is malformed), `ExecutionError` (the work could not be done), `ShapeError` with `ShapeCompileError` and `MetaShaclError` (the shapes are wrong), and `EndpointError` (also an `OSError`). `FormatError` and `ExecutionError` have a `kind` and an optional `context`. See Appendix D of the user guide.
- **`ShapeError` is no longer a `ValueError`.** Code that wrote `except ValueError` around shape code must catch `ShapeError`.
- **Removed error classes, with no aliases:** `SparqlSyntaxError`, `SQEError`, `SQEValidationError`, `SPARQL12ConformanceError`, `SRLError`, `SRLParseError`, `SRLDecodeError`, `SRLEvalError`, `SRLImportError`, `SRLImportsNotSupportedError`, `StratificationError`, `ManchesterSyntaxError`, `InvalidTripleTermError`, `BasicEncodingError`, `CanonicalizationComplexityError`, `EntailmentRewriteError`, `SqeTextTooDeepError`, `ReasoningTimeoutError` and `InconsistentOntologyError`, and the warning `SRLUnresolvedImportsWarning`. The table in section 8 of Appendix D gives what to catch instead.
- **Engine errors are converted.** A malformed document or query from `parse()`, `query()` or `update()` is `FormatError` (it was `SyntaxError`), and an engine failure is `ExecutionError` kind `query` (it was `RuntimeError`).
- **Parsing returns a tree and validation reports.** `sparql_to_tree()` and `parse_ruleset()` return a tree or rule set for any text the grammar accepts; problems are reported by `validate_sparql_tree()` and by running. `SQEValidationError` and the `validate=` parameters are gone.
- **Validators return a `ValidationReport`**, not a `(conforms, report_graph, report_text)` tuple: `meta_validate`, `validate_sparql_tree` and `validate_manchester_tree`.
- **Functions renamed**, with no aliases. `sqe_parse_to_tree` and `srl_parse_to_tree` are `sparql_to_tree`; `sqe_tree_to_text` and `srl_tree_to_text` are `tree_to_sparql`; `sqe_validate` and `srl_validate` are `validate_sparql_tree`; `manchester_parse_to_tree`, `manchester_tree_to_text`, `manchester_tree_to_owl` and `manchester_validate` are `manchester_to_tree`, `tree_to_manchester`, `tree_to_owl` and `validate_manchester_tree`. The tree functions take `tree_graph=`.
- **Syntax trees store order with `tree:ord`**, not `rdf:List`, in a new shared `tree:` vocabulary (`tree:ord`, `tree:Item`, `tree:value`). A named node is held in a `tree:Item`; a blank node may have only one parent. Stored trees from `0.1.0` do not load. `graph.ordinals` has the helpers (`append`, `insert_at`, `remove_at`, `replace_at`, `renumber_dense`).
- **Vocabularies renamed to the grammar names.** `spexpr:` built-ins and aggregates lose their `Builtin_` and `Aggregate_` prefixes, `spexpr:vars` is `spexpr:expr`, `sqe:PrefixBinding` is `sqe:PrefixDecl`, `Exists` and `NotExists` are two classes, `IN` values are `spexpr:args`, the `srl:` flag is `evalground`, and 44 `manch:` names are spelled out (`OntologyDocument`, `PrefixDeclaration`, and others).
- **`SRL` rule sets are not validated at parse time.** `validate_sparql_tree()` reports the §4.2 conditions, an unorderable rule set and unresolved imports (a warning).

### Added

- `sparql_to_tree()` reads SPARQL queries, updates and SRL rule sets.
- `FormatError`, `ExecutionError` kinds `import`, `unsupported` and `limit`, and `only_kind()`.
- `derive_shape(template_graph=)`, a public `max_triples` for rule inference, and built-in `owl:imports` for the registry's ontologies.
- User guide changes: a new Appendix C (Manchester Syntax reference) and Appendix D (error classification), chapter 06 reorganised (06.02 SPARQL queries, updates and rules as RDF; 06.03 Manchester syntax as RDF; 06.04 the registry), and 02.08 for the Manchester notation.

### Changed

- The `starlayer`, `starlayer-reasoning` and `starlayer-kg` packages are version 0.2.0, and `starlayer-reasoning` needs `starlayer>=0.2.0`.
