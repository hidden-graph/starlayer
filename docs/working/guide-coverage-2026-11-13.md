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

## Gaps filled in a second pass (same day)

| Gap | Where it is now |
|---|---|
| Reading a validation result, errors, `validate_each`, `target_nodes`, entailment during validation | `04` sections 5.1 to 5.3 (`ValidationResult`, `validate_each`, `ShapeError`, `MetaShaclError`, `inference=`, `sh:entailment`); the derive section is now 6 |
| Building on SHACL: `infer_types`, `shapes_graph_members`, `sparql_query_problems`, `path_values`, `is_inverse`, `evaluate_expression`, `node_expression_functions` / `operators`, `property_shapes_for_role`, `select_widget` | new guide `04g-building-on-shacl.ipynb` (README, `user-guide-version.json`) |
| Prefixes: `bind`, `unbind`, `used_prefixes`, `expand_curie`, `compute_qname`, `set_default_prefixes`, `DEFAULT_PREFIXES` | `02d` section "Prefixes" |
| `owl:imports` at the RDF level: `owl_imports`, `has_import_locally`, `resolve_imports(loader=)`, `can_resolve_import` | `02d` section "`owl:imports`" |
| `skolemize`, `de_skolemize`, `empty_like`, `cbd` | `02d` section "Blank nodes and copies" |
| `check_query`, `relevant_subgraph` | `03` section 1.5 |
| `02d` headings unnumbered, no "How to run" cell | numbered 1 to 14, "How to run this notebook" added |

Fourteen more notebook links (55 in all) tie these cells to the symbols they show.

## Still not covered

| Names | Why they stay out |
|---|---|
| `EntailmentSession` as a type, `EndpointError`, `config` | the methods that return them are shown; the types need no section |
| `DCAT`, `FOAF`, `PROV`, `SCHEMA` and the other vocabulary constants | a list would only repeat the module |
| `StarLayerGraphProtocol`, `MutableStarLayerGraphProtocol`, `normalize_*`, `ExecutionDiagnostics` (shown by its fields, not by name) | for library authors; the API reference has them |
| `addN`, `predicate_objects`, `subject_objects`, `subject_predicates`, `engine_view`, `sparql_query` | rdflib-style readers and engine hooks; not worth a section |

Capabilities marked implemented that still have no notebook link to their implementing symbols (all are covered in prose or in a cell, and only lack the link): `cap-shacl-3` (meta-shapes; `04` 5.2 shows `MetaShaclError`, linked to the error, not to the meta-shapes), `cap-sparql-4` (prepared queries, `StarQuery`), `cap-srl-4` and `cap-srl-8` (`03b`), `cap-other-1` (`03` section 1.3), `cap-rdf-graph-13` (the RDF 1.1 basic encoding in `02d`), `cap-manchester-3`, `cap-sparql-3`, `cap-other-3` (the shapes for `manch:`, `sqe:` and SKOS graphs). Roadmap capabilities are not covered, correctly.

## Structure and style (not changed)

`04d` mixes numbered and unnumbered headings; `02` opens with its section on `TripleTerm` semantics although the term helpers it names are gone (the text was reduced earlier, the title still reads like the old class). `05d` should be re-run after the next push, when the fetch URLs exist.

## What is left

Links for the nine capabilities above, and the headings of `04d`.
