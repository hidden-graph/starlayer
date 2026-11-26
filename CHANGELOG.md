# Changelog

All notable changes to StarLayer. The packages (`starlayer`, `starlayer-reasoning`, `starlayer-kg`) are released together under one tag.

## Unreleased (after the `v0.2.0` tag)

Changes from the error-scheme review of 2026-11-26. Several of them change what `v0.2.0` raises.

### Breaking

- **Error kinds merged.** `ExecutionError` kind `nesting` is now `limit`, and `FormatError` kind `term` is now `rdf`; the `context` says what was too deep or which term text was malformed. `nesting` and `term` no longer exist.
- **SHACL limits.** `max_iterations` and `max_triples` failures are `ExecutionError` kind `limit` (they were `rule`).
- **Entailment names.** An entailment name that is not a registered regime is `ExecutionError` kind `unsupported` (it was `ValueError` or `NotImplementedError`), in `infer()`, `query()` and a shapes graph's `sh:entailment`. A value that is not text or an IRI is `TypeError`.
- **Valid input the library cannot handle is `unsupported`** (it was `ValueError`): `relevant_subgraph` given a `DESCRIBE` or a `SERVICE` query, writing a blank node that came from an endpoint, the `to_rdf11` direction policy `"error"`, and a triple term written as JSON-LD (it was an `OSError`).
- **A malformed rule body element** (a `RuleSet` built by hand) is `FormatError` kind `srl`.
- **A call on a closed `Materialization`** is `ValueError`.
- **An `internal` error says so.** Its message starts "internal error (a bug in StarLayer, please report it at <address>)", and `error.report_url` holds the address.

### Added

- `ISSUES_URL` and `ExecutionError.report_url` in `starlayer.errors`.

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
