# What the guides cover and what they do not (2026-11-13)

Method: every name in `starlayer.graph.__all__`, `starlayer.shacl.__all__` and `starlayer.sparql.__all__`, and every public method of `StarLayerGraph`, was searched for in the text and code of the 29 guides in `docs/guides`; the 49 capabilities in `tools/kg/codekg/curated/functionality.ttl` were checked for a notebook link (`notebook-links.ttl`, 41 links now) that demonstrates one of their implementing symbols. A name that appears only in a sentence counts as mentioned, not shown. All guides were run (`pytest --notebooks`): 28 of 29 pass; `05d` fails only on its fetch of a bundled file from `raw.githubusercontent.com`, whose paths are those of the repository as it will be after the next push (the reorganised layout is not on GitHub yet).

## Done in this review

Broken or wrong because of the reorganisation (packages, `graph/` flattened, `shacl/engine`, rdflib and OWL moved to `starlayer-reasoning`):

- `01`: the install cell installed the repository root, which is no longer a package; it installs `packages/starlayer` (and from GitHub with `#subdirectory=packages/starlayer`). It now also says what `starlayer-reasoning` adds.
- `02c`, `appendix-b2`: imported `InconsistentOntologyError` from `starlayer.graph.entailment.owl_dl`; now `starlayer_reasoning.owl_dl`.
- `06b`: imported `TripleTerm`, which is not in the core; the example uses `pyoxigraph.Triple`.
- `05c`: said a graph has no `set`; it has one now. `02b`, `03a`: say that OWL-RL needs `starlayer-reasoning`. `05`: a typo in a heading.
- Links from guide cells to code (`notebook-links.ttl`) and the curated functionality and upstream-issue files named symbols that no longer exist (`owl_dl`, `model.dirlangstring`, `skos`, `profiling` as a module, the `TripleTerm` workaround); the deferred code-KG tests, which CI runs and the day-to-day run does not, failed on them and pass now.

New sections for what was added to the library since the guides were written:

| Guide | Section | Shows |
|---|---|---|
| `02d` | Terms and Python values | `literal`, `to_python`, `parse_term` |
| `02d` | Lists, single values and walks | `add_list`, `set_list`, `remove_list`, `set`, `transitive_objects`, `transitive_subjects` |
| `02d` | Changes between graphs | `diff`, `GraphDelta` |
| `02d` | What a graph contains | `profile()` |
| `03` | 1.4 Your own functions and aggregates | `custom_functions`, `custom_aggregate_functions` |
| `03` | 3. Writing query results | `Result.serialize` (JSON, XML, CSV, TSV, RDF) |
| `04` | 5. Deriving shapes from data | `derive_shape()`, which no guide mentioned |
| `04d` | Why a widget was chosen | `explain_widgets` |
| `04e` | 1.3 Making a set of shapes self-contained | `referenced_shapes`, `rule_dependencies` |

## Covered well

RDF 1.2 terms, reifiers, annotations and directional literals (`02`); datasets and the store boundary (`02a`, `02d`); RDFS, OWL-RL and OWL-DL inference and query-time entailment (`02b`, `02c`, `03a`); SPARQL 1.2 query and update (`03`); SRL rules and their RDF form (`03b`, `05c`); the four SHACL processing modes, node expressions, SPARQL constraints, inference rules, UI widgets, profiling and shape fragments (`04` to `04f`); the bundled ontologies, Manchester syntax, `sqe:` trees and the registry (`05` to `05d`); formats, persistence, remote endpoints and canonical hashing (`06a` to `06c`).

## Not covered, and whether to fill it

Public names that no guide mentions at all, grouped by what they are for.

| Gap | Names | Should it be filled? |
|---|---|---|
| Reading a validation result, and handling errors | `ValidationResult`, `ExecutionDiagnostics`, `validate_each`, `ShapeError`, `MetaShaclError`, `EvaluationFailure`, `target_nodes` | **Yes, first.** Guide 04 says what the four modes are and never shows what comes back or what goes wrong. One section on the result object, the report graph, a malformed shape, and validating each graph of a dataset. |
| Entailment during validation | `inference=`, `sh:entailment` | **Yes.** An implemented capability (`cap-shacl-9`) with no cell; belongs beside the result section. |
| Inspecting a shapes graph (what an application needs to build on SHACL) | `infer_types`, `path_values`, `is_inverse`, `shapes_graph_members`, `sparql_query_problems`, `parameter_value_shapes`, `evaluate_expression`, `node_expression_functions`, `node_expression_operators`, `property_shapes_for_role`, `select_widget` | **Yes, as one short guide** ("Building on SHACL", `04g`): it is the surface the workbench uses, and it is currently reachable only from the API reference. |
| `owl:imports` at the RDF level | `owl_imports`, `has_import_locally`, `can_resolve_import`, `resolve_imports` (named in text only) | **Yes, short.** A capability (`cap-rdf-graph-8`) with no demonstration; one section in `02d`. |
| Prefix handling | `DEFAULT_PREFIXES`, `set_default_prefixes`, `used_prefixes`, `expand_curie`, `compute_qname`, `unbind` | **Yes, short.** Every guide binds prefixes; none says how defaults work or how to list or drop them. One section in `02d`. |
| Query helpers | `check_query` (SPARQL), `relevant_subgraph` | Yes, a paragraph each in `03` or `05b`. |
| Blank nodes and copies | `de_skolemize`, `empty_like` (`skolemize` is mentioned) | Maybe: two lines in the `02d` set-operations section. |
| `EntailmentSession` as a type, `EndpointError`, `config` | | No: the methods that return them are shown; the types need no section. |
| Vocabulary constants | `DCAT`, `FOAF`, `PROV`, `SCHEMA` | No: a list in the `02d` terms section is enough, if anything. |
| Protocols and normalisers | `StarLayerGraphProtocol`, `MutableStarLayerGraphProtocol`, `normalize_*` | No: for library authors; the API reference has them. |

Capabilities marked implemented with no notebook link to their implementing symbols (some are covered in prose and only lack a link; adding the links is cheap):

- `cap-shacl-3` SHACL 1.2 meta-shapes for checking shapes graphs (`meta_shacl=True` is in the text; no cell shows a rejection).
- `cap-shacl-5` deriving a shape: now covered by `04` section 5, link added.
- `cap-shacl-9` entailment during validation (see above).
- `cap-sparql-4` prepared queries (`StarQuery` appears in the text).
- `cap-srl-4`, `cap-srl-8` triple terms and the worked example in SRL (`03b` has them; the link names other symbols).
- `cap-other-1` the `VERSION` directive warnings (`03` section 1.3 shows it; the link names another symbol).
- `cap-rdf-graph-8` imports with a loader, `cap-rdf-graph-13` the RDF 1.1 basic encoding (`02d` mentions `rdf_version="1.1"`).
- `cap-manchester-3`, `cap-sparql-3`, `cap-other-3` the SHACL shapes for `manch:`, `sqe:` and SKOS graphs: shown by validating, not linked.
- Roadmap items (`cap-shacl-10`, `-11`, `-12`, `cap-srl-9`, `cap-rdf-graph-10`, `-11`) are not covered, correctly.

## Structure and style (not changed)

`02d` uses unnumbered headings where the style guide asks for `## N.` numbering, and `04d` mixes both; `02` opens with its section on `TripleTerm` semantics although the term helpers it names are gone (the text was reduced earlier, the title still reads like the old class). `05d` should be re-run after the next push, when the fetch URLs exist.

## Suggested order

1. `04` section: reading results, errors and entailment during validation.
2. `04g` "Building on SHACL": the introspection functions an application needs.
3. `02d` sections: prefixes, `owl:imports`, `de_skolemize` / `empty_like`.
4. Links for the capabilities above; renumber `02d`.
