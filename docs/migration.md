# Moving from the original main to the Oxigraph line

The original `main` (an rdflib graph with pySHACL behind `starlayer.shacl`) was replaced by the `shacl-engine` line: graphs are Oxigraph stores, SHACL runs on a native SHACL 1.2 engine, and SPARQL runs in Oxigraph. This page lists what went away, what replaces it and what behaves differently. It was made by importing both versions and comparing their public names and signatures, then checking behaviour by running both.

The rule for apps: import from `starlayer`, `starlayer.graph`, `starlayer.shacl`, `starlayer.sparql` and `starlayer.starontology` only, never a submodule.

## Graphs and terms

| Before | Now | Why |
|---|---|---|
| `StarLayerGraph(*args, backend="rdf-1.1", **kwargs)` | `StarLayerGraph(store=None, path=None, identifier=None, *, prefixes=None, endpoint=None, max_age=None, pull=True)` | One backend. `backend=` raises `TypeError`. |
| `StarLayerDataset(*args, backend=..., bind_namespaces=...)` | `StarLayerDataset(store=None, path=None, default_union=True, *, prefixes=None, endpoint=None, max_age=None, pull=True)` | `path=` opens an on-disk Oxigraph store; `endpoint=` holds the dataset in a SPARQL endpoint (below). |
| rdflib terms out of a graph (`URIRef`, `Literal`, `BNode`) | pyoxigraph terms (`NamedNode`, `Literal`, `BlankNode`, `Triple`) | The engine's term model. Comparing a result with an rdflib term is `False`, not an error. |
| `from starlayer.graph import BNode, Literal, URIRef, Namespace, RDF, RDFS, XSD, Graph, Dataset, Variable, Collection` | `pyoxigraph` terms, or `from rdflib import ...` if you installed the `rdflib` extra | The graph package no longer re-exports rdflib. A native `Namespace` and vocabulary constants are proposed, not built. |
| `starlayer.graph.graph.starlayer_graph.StarLayerGraph` | `from starlayer import StarLayerGraph` | The module is gone. |
| rdflib store plugins (SQLAlchemy, BerkeleyDB), `SPARQLStore` | `path=` (on-disk Oxigraph), `endpoint=` (Oxigraph server, Fuseki) | See "Where the data lives". |
| `parseQuery`, `parseUpdate`, `prepareQuery`, `prepareUpdate`, `processUpdate` | `StarQuery` (a query checked once, bound per call), `starlayer.sparql.check_query`, `graph.query()` / `graph.update()` | SPARQL runs in Oxigraph. |
| `used_prefixes` | `graph.serialize(..., only_used=True)` | |
| rdflib `Graph` / `Dataset` as arguments | still accepted, copied into a `StarLayerGraph`; convert explicitly with `StarLayerGraph.from_rdflib()` and `.to_rdflib()` | rdflib is an optional extra. |

Behaviour that differs even when the call is the same:

- **Literal lexical forms are normalised** by Oxigraph: `"04"^^xsd:integer` reads back as `4`. Meaning and datatype are kept, the spelling is not (starlayer #190).
- **Formats.** TriX, HexTuples and `longturtle` are not available. `n3` is read and written as Turtle. JSON-LD, TriG, N-Quads, N-Triples, RDF/XML and Turtle work.
- **RDF 1.2 is native**: triple terms and `rdf:dirLangString` need no encoding, and `serialize(rdf_version="1.1")` exports the RDF 1.1 form.
- **A dataset's `default_union`** decides what `query()` sees; for SHACL a dataset is always its union (below).

## SHACL (`starlayer.shacl`)

| Before | Now | Why |
|---|---|---|
| `TripleTermAdapter`, `TripleTermGraph`, `TripleTermValue`, `validate(adapter=...)` | removed | Triple terms are native; there is nothing to encode. |
| `validate(**pyshacl_options)` | a closed set: `inference`, `inplace`, `meta_shacl`, `advanced`, `debug`, `allow_warnings`, `allow_infos`, `abort_on_first`, `abort_on_error`, `max_validation_depth`, `invalid_terms`; any other keyword is a `TypeError` | A misspelt option used to be ignored. |
| pySHACL-only options `validate_fn`, `decode_report`, `js`, `iterate_rules`, `sparql_mode`, `do_owl_imports`, `*_format`, `serialize_*`, `use_shapes` | removed | Pick shapes by passing a shapes graph (`shacl_graph=`) or `shapes_graph_resource=` (a named `sh:ShapesGraph` module). `focus_nodes` exists on `evaluate`, not on `validate`. |
| `inference="rdfs"` / `"owlrl"` | `inference=ENTAILMENT.RDFS` and the other regime IRIs (or `sh:entailment` in the shapes) | The old strings are rejected on purpose. |
| `validate_each([...])` keyed by position | the same, plus a mapping (keys kept) and a `StarLayerDataset` (each graph alone, keyed by graph name, `None` for a default graph that holds triples) | |
| `ValidationResult.report_text` a string | a string or a callable that makes it | Built when read. |
| `StarShaclSchema` | the same class; it binds a shapes graph at construction | `validate(inference=...)` on a schema is a `TypeError`. |
| new | `evaluate`, `extract_subgraph`, `target_nodes`, `select_widget(s)`, `evaluate_expression`, `node_expression_functions`, `infer_types`, `path_values`, `shapes_graph_members`, `sparql_query_problems` and the error classes `ShapeError`, `RuleError`, `MetaShaclError`, `EvaluationFailure` | Exported from `starlayer.shacl`. |

Behaviour that differs:

- **SHACL 1.2, not SHACL-AF.** The engine follows the 1.2 drafts. A shapes graph that uses `sh:target`, `sh:SPARQLTarget`, `sh:SPARQLTargetType` or `sh:SPARQLFunction` is a `ShapeError` (SPARQL-Related Features, Appendix F), and the meta-shapes flag them. pySHACL ran them; the first version of this engine ignored the targets and reported `conforms=True`. Use `sh:targetNode [ sh:select "..." ]` and `sh:ListParameterExpressionFunction`.
- **Legacy node expressions** (`sh:this`, a bare `sh:path` as an expression, `sh:union`, `sh:intersection`, `sh:filterShape`) are not supported; use `[ shnex:var "focusNode" ]`, `shnex:pathValues`, `shnex:filterShape`.
- **DASH is not supported.** A `dash:` property on a shape is ignored, as SHACL says, so such a constraint is not checked (pySHACL does not check it either).
- **A dataset is its union.** `validate` sees all graphs of a `StarLayerDataset` as one data graph whatever its `default_union` says, as pySHACL does. `extract_subgraph` and `relevant_subgraph` raise `TypeError` for a dataset: a fragment would not say which graph a triple came from.
- **Ill-formed shapes raise `ShapeError`**; a term that is not an RDF term (a relative IRI) raises `TermError` unless `invalid_terms="lenient"`.
- **`owl:imports`** that are not in the shapes graph raise unless you pass `shapes_graph_loader=` or `ignore_imports=True`. Nothing is fetched on its own.
- **`meta_shacl` is off by default**; turn it on for a shapes graph you did not write.
- **Messages** are processor-defined. Read `sh:sourceConstraintComponent`, `sh:resultPath`, `sh:value` and `sh:sourceShape`, not the text.
- **Per-constraint annotations**: `sh:severity`, `sh:message` and `sh:deactivated` (a boolean or a node expression) on the reifier of any constraint triple.

## SPARQL (`starlayer.sparql`)

| Before | Now |
|---|---|
| `SALG`, `query_to_rdf`, `rdf_to_query`, `update_to_rdf`, `rdf_to_update`, `queries_to_collection`, `rdf_to_collection` | the `sqe:` "query as RDF" form: `from starlayer.sparql import sqe` (`sqe_parse_to_tree`, `sqe_tree_to_text`, `sqe_validate`) |
| `prepare_query_12`, `prepare_update_12` | `StarQuery`; `check_query` says whether a text is valid SPARQL 1.2 |
| new | `relevant_subgraph(graph, query)`: the triples a query's answer depends on (SELECT, ASK, CONSTRUCT), every derivation kept, reproducible; `SERVICE` and a dataset raise |

## Where the data lives

- **In memory** (the default): about 500 to 650 bytes a triple, so roughly 25 to 30 million triples in 16 GB.
- **On disk**: `StarLayerGraph(path=...)` / `StarLayerDataset(path=...)`: an Oxigraph store in a directory, about 70 bytes a triple on disk and a small, fixed amount of memory; one writer process at a time.
- **A SPARQL endpoint** (Oxigraph server, Fuseki): `StarLayerGraph(endpoint=Endpoint(query_url, update_url), identifier=...)` or `StarLayerDataset(endpoint=...)`. The object keeps a full copy, pulled as a stream, in memory or on disk (add `path=`). Reads are local; a write goes to the endpoint first, then the copy. Blank nodes in a write are skolemized. A query can also read an endpoint with `SERVICE`. Details and limits: `starlayer/graph/oxgraph/endpoint.py`, guide 06b.

## Decisions still open

- Whether to keep accepting rdflib *terms* as arguments. Today a graph takes rdflib terms in but gives pyoxigraph terms out, so `graph.value(s, p) == EX.b` is `False`. The proposal: ship a native `Namespace` and vocabulary constants (`RDF`, `RDFS`, `XSD`, `OWL`, `SH`), keep `from_rdflib` / `to_rdflib` for whole graphs and datasets, and deprecate rdflib terms as arguments.
- The workbench has 19 files that import rdflib; how many pass rdflib objects into StarLayer has not been counted.
