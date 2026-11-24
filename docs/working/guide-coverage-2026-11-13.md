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
| Reading a validation result, errors, `validate_each`, `target_nodes`, entailment during validation | `04` sections 5.1 to 5.3 (`ValidationReport`, `validate_each`, `ShapeError`, `MetaShaclError`, `inference=`, `sh:entailment`); the derive section is now 6 |
| Building on SHACL: `infer_types`, `shapes_graph_members`, `sparql_query_problems`, `path_values`, `is_inverse`, `evaluate_expression`, `node_expression_functions` / `operators`, `property_shapes_for_role`, `select_widget` | new guide `05g-building-on-shacl.ipynb` (README, `user-guide-version.json`) |
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

Every capability marked implemented now has a notebook link to a symbol that implements it (60 links in all). Nine of them were not demonstrated, or had no implementing symbol to link to:

- Prepared queries (`cap-sparql-4`) had no code cell at all: `03` section 1.6 shows `StarQuery`.
- The RDF 1.1 basic encoding (`cap-rdf-graph-13`) was shown only through `serialize(rdf_version="1.1")`: `02d` now shows `interop.to_basic` and `from_basic`.
- Capabilities that are shapes or data (`cap-shacl-3` meta-shapes, `cap-sparql-3` `sqe:` shapes, `cap-manchester-3` `manch:` shapes, `cap-other-3` SKOS shapes, `cap-shacl-9` entailment during validation) and the two SRL ones (`cap-srl-4`, `cap-srl-8`) had no `implementedByIdentifier`, so no link could name them; each now names the function that runs the shapes or rules (`MetaShaclError`, `sqe_validate`, `manchester_validate`, `get_ontology_graph`, `target_nodes`, `parse_ruleset`), which the guides already demonstrated.
- The `VERSION` directive warning (`cap-other-1`) is implemented in `query()`, which the cell in `03` section 1.3 calls.

Roadmap capabilities are not covered, correctly.

## What is left

Nothing from this review. The list of names that stay out of the guides on purpose is above; `05d` is run again after the next push, when the URLs it fetches exist.
