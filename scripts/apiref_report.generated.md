# StarLayer API Reference (generated from the apiref/codekg graphs)

Regenerated from the apiref: graph parsed out of docs/api-reference.md, cross-linked to packages/starlayer/starlayer/codekg/codekg.trig - exploratory, see scripts/explore_apiref_graph.py.

## `starlayer`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `StarLayerGraph` | class | New | Also available from `starlayer.graph` below | `starlayer.graph.graph.starlayer_graph.StarLayerGraph` |
| `StarLayerDataset` | class | New | Also available from `starlayer.graph` below | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset` |
| `StarShaclSchema` | class | New | Holds a SHACL shapes graph (plus optional ontology graph), to use with relevant SHACL methods, including validation, rule inferencing, or evaluation. | `starlayer.shacl.validator.StarShaclSchema` |

## `starlayer.conformance`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `declared_conformance()` | function | New | Returns a fresh graph (not shared/cached across calls) containing all three resources above, each asserting `dcterms:conformsTo` only the documents/regimes specific to that subpackage. `conformance.GRAPH_SUBJECT`/`conformance.SPARQL_SUBJECT` (and `RDF12_CORE_TR_URLS`/`SPARQL12_TR_URLS`/`GRAPH_EXTRA_TR_URLS`/`SPARQL_EXTRA_TR_URLS`) are also exposed directly, for a caller that wants to query one resource's own claims without re-deriving its IRI | _unresolved_ |
| `DOES_NOT_CONFORM_TO` | constant (`URIRef`) | New | `conformance:doesNotConformTo` — a project-minted predicate (no standard "does not conform" term exists in dx-prof/Dublin Core to reuse) for the narrow set of exclusions that have a real, dereferenceable IRI and are total, not scope-limited: `hg:shacl` doesNotConformTo the UI Profile, `starlayer.graph` doesNotConformTo SPARQL 1.2's D-Entailment regime. `conformance.CONFORMANCE` is the backing `Namespace` (`https://github.com/hidden-graph/starlayer/ns/conformance#`) | _unresolved_ |

## `starlayer.graph`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `StarLayerGraph` | class | New | `rdflib.Graph` extended with RDF 1.2 triple-term support | `starlayer.graph.graph.starlayer_graph.StarLayerGraph` |
| `StarLayerDataset` | class | New | `rdflib.Dataset` extended with RDF 1.2 triple-term support — an RDF dataset where every named-graph context is a `StarLayerGraph` | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset` |
| `TripleTerm` | class | New | An RDF 1.2 triple term used as a resource | `starlayer.graph.model.triple.TripleTerm` |
| `DirLangString` | class | New | An RDF 1.2 directional language-tagged string literal | `starlayer.graph.model.dirlangstring.DirLangString` |
| `can_resolve_import()` | function | New | Takes an `owl:imports` target IRI and a `loader=`, and returns whether that loader can resolve it — calls `loader(iri)` once and checks for a non-`None` result, since there's no cheaper way to know short of trying | `starlayer.graph.graph.starlayer_graph.can_resolve_import` |
| `parseQuery()` | function | Modified | Takes SPARQL 1.2 SELECT/ASK/CONSTRUCT/DESCRIBE query text and returns its raw parse tree, a pyparsing `ParseResults` — not yet a compiled `Query` object | `starlayer.graph.query.sparql_api.parseQuery` |
| `prepareQuery()` | function | Modified | Takes SPARQL 1.2 query text and returns a prepared `Query` object, ready to pass to `.query()` | `starlayer.graph.query.sparql_api.prepareQuery` |
| `parseUpdate()` | function | Modified | Takes SPARQL 1.2 Update text and returns its raw parse tree, a pyparsing `ParseResults` — not yet a compiled `Update` object | `starlayer.graph.query.sparql_api.parseUpdate` |
| `prepareUpdate()` | function | Modified | Takes SPARQL 1.2 Update text and returns a prepared `Update` object, ready to pass to `.update()` | `starlayer.graph.query.sparql_api.prepareUpdate` |
| `processUpdate()` | function | Modified | Takes a graph and SPARQL 1.2 Update text, executes the update directly against the graph, and returns nothing | `starlayer.graph.query.sparql_api.processUpdate` |
| `BNode` | class | Unchanged | rdflib's own blank node term type | _unresolved_ |
| `Literal` | class | Unchanged | rdflib's own literal term type | _unresolved_ |
| `URIRef` | class | Unchanged | rdflib's own IRI term type | _unresolved_ |
| `Variable` | class | Unchanged | rdflib's own SPARQL variable type | _unresolved_ |
| `Namespace` | class | Unchanged | rdflib's own "generate URIRefs with a common prefix" helper | _unresolved_ |
| `RDF` | value | Unchanged | rdflib's bound `RDF:` namespace | _unresolved_ |
| `RDFS` | value | Unchanged | rdflib's bound `RDFS:` namespace | _unresolved_ |
| `XSD` | value | Unchanged | rdflib's bound `XSD:` namespace | _unresolved_ |
| `Graph` | class | Unchanged | Plain `rdflib.Graph` (re-exported for convenience) | _unresolved_ |
| `Dataset` | class | Unchanged | Plain `rdflib.Dataset` (re-exported for convenience) | _unresolved_ |
| `Collection` | class | Unchanged | rdflib's own `rdf:List` wrapper | _unresolved_ |
| `add()` | method | Modified | Takes a triple `(subject, predicate, object)` , adds to the graph and returns this graph | _unresolved_ |
| `addN()` | method | Modified | Takes an iterable of `(subject, predicate, object, context)` 4-tuples, adds them all at once, and returns this graph. `context` is expected to be this graph itself — a mismatched context is silently dropped, not added | _unresolved_ |
| `add_reification()` | method | New | Takes a reifier node and a `TripleTerm`, asserts `reifier rdf:reifies triple_term` to make the node an official reifier, and returns this graph | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.add_reification` |
| `add_reifier_annotation()` | method | New | Takes an annotation predicate and value (`predicate`, `obj`) and an optional `name`, creates a reifier node (a `URIRef` if `name` is given, otherwise a fresh `BNode`), adds the one annotation property to it, and returns the new reifier node — ready to pass straight into `add_reification()` | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.add_reifier_annotation` |
| `all_nodes()` | method | Unchanged | Returns the set of all subjects and objects in the graph, as a plain Python `set`. | _unresolved_ |
| `bind()` | method | Unchanged | Binds a prefix to a namespace; returns nothing | _unresolved_ |
| `cbd()` | method | Modified | Takes a resource and computes its Concise Bounded Description, returning it as a `StarLayerGraph`. The optional `target_graph` is the *output* — the graph the CBD results get added to, not a copy the resource is read from — and defaults to a new `StarLayerGraph` if not given; it must itself be a `StarLayerGraph` (a plain `Graph` can't store `TripleTerm`s) | _unresolved_ |
| `close()` | method | Modified | Closes the underlying store, optionally committing pending writes first; returns nothing | _unresolved_ |
| `collection()` | method | Unchanged | Takes an identifier (the list's head node) and returns a `Collection` — a thin Python object (not a graph itself) that holds a reference to this graph plus that identifier, and reads/writes the `rdf:List` as ordinary triples in this graph; mutating the `Collection` (e.g. `+=`) mutates this graph directly, nothing is stored on the `Collection` itself | _unresolved_ |
| `commit()` | method | Unchanged | Commits active transactions and returns this graph. | _unresolved_ |
| `compute_qname()` | method | Unchanged | Takes a URI and returns its `(prefix, namespace, localname)` qname tuple, resolved against this graph's own bound namespaces (its `namespace_manager`) | _unresolved_ |
| `connected()` | method | Unchanged | Returns whether the graph is connected when treated as an undirected graph of nodes — every node reachable from every other via some triple. Unrelated to any backend store connection | _unresolved_ |
| `de_skolemize()` | method | Modified | Converts skolem IRIs in the graph back to blank nodes and returns the result as a `StarLayerGraph`. Takes an optional `new_graph` (the target to write into, defaulting to a fresh `StarLayerGraph`) and `uriref` (limit the conversion to one specific skolem IRI). Overridden because rdflib's own inherited version hardcodes a plain `rdflib.Graph()` as that default target, which crashes with `AssertionError` the moment the graph being de-skolemized contains a real `TripleTerm` (plain `Graph.add()` rejects it outright) | _unresolved_ |
| `derive_shape()` | method | New | Infers a SHACL shape from the graph's own data (one `sh:NodeShape` per class) and returns it as a `StarLayerGraph` | _unresolved_ |
| `destroy()` | method | Unchanged | Destroys the identified store, if the backend supports it; returns this graph | _unresolved_ |
| `from_rdflib()` | class method | **Modified** | Takes a plain `rdflib.Graph` and returns it  as a `StarLayerGraph`. Preserves the source graph's own `.identifier` (2026-10-09, previously silently replaced with a fresh random `BNode`) — except when `source_graph` is itself a whole `Dataset`/`ConjunctiveGraph` (not one of its named graphs), which has no single meaningful identity of its own and is left with a default `BNode` identifier as before | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.from_rdflib` |
| `has_triple_term()` | method | New | Takes a subject/predicate/object and returns `True` if a `TripleTerm` with these exact components exists in the graph | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.has_triple_term` |
| `identifier` | property | Unchanged | The graph's own identifier (a `URIRef` or `BNode`) | _unresolved_ |
| `infer()` | method | New | Takes `entailment=` — a real entailment regime IRI from `ENTAILMENT` (`ENTAILMENT.RDF`, `ENTAILMENT.RDFS`, `ENTAILMENT["OWL-RDF-Based"]`, `ENTAILMENT["OWL-Direct"]`) or an iterable of more than one to combine into a single pass — plus `mode=` (`"full"`/`"delta"`/`"in-place"`), materializes that closure, and returns it as a `StarLayerGraph`. (2026-10-08: renamed from `profile=`, matching `query()`'s own already-established `entailment=` parameter for the identical vocabulary — see `starlayer/graph/CLAUDE.md`'s dated entry.) | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.infer` |
| `isomorphic()` | method | Modified | Takes another graph and returns a boolean whether the two are isomorphic | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.isomorphic` |
| `items()` | method | Unchanged | Takes an `rdf:List` resource and yields its items one at a time, as a generator, rather than returning them all as a single list | _unresolved_ |
| `n3()` | method | Unchanged | Returns an n3 identifier for the graph | _unresolved_ |
| `namespace_manager` | property | Unchanged | Returns this graph's namespace manager | _unresolved_ |
| `namespaces()` | method | Unchanged | Yields every `(prefix, namespace)` binding on this graph, one `(str, URIRef)` pair at a time | _unresolved_ |
| `objects()` | method | Unchanged | Yields objects matching the given subject/predicate (optionally unique only), one term at a time as a generator | _unresolved_ |
| `open()` | method | Modified | Opens a persistent store and returns this graph | _unresolved_ |
| `owl_imports()` | method | New | Returns every object of this graph's own direct `owl:imports` triples, deduplicated, in first-seen order — a pure read, resolves/fetches nothing. See `resolve_imports()` below | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.owl_imports` |
| `parse()` | method | Modified | Takes RDF data — from `source` (a file path, URL, or file-like object), or explicitly via `location`/`file`/`data` — plus a `format=` string (any RDF 1.1/1.2 format this project supports), parses it into the graph, and returns this graph. For a multi-graph-capable format (`nquads`/`trig`/`trix`/`nq12`/`trig12`/`trix12`), raises `MultipleGraphsError` if the data spans more than one distinct graph — see `format=` below | _unresolved_ |
| `predicate_objects()` | method | Unchanged | Yields `(predicate, object)` tuples for the given subject, one pair at a time as a generator (optionally unique only) | _unresolved_ |
| `predicates()` | method | Unchanged | Yields predicates matching the given subject/object | _unresolved_ |
| `print()` | method | Modified | Prints the graph to stdout — defaults to `turtle12`. Returns nothing | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.print` |
| `qname()` | method | Unchanged | Takes a URI and returns its qname string | _unresolved_ |
| `qname_term()` | method | New | Takes any term (`URIRef`, `BNode`, `Literal`, `TripleTerm`, `DirLangString`) and returns its prefixed n3 form | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.qname_term` |
| `query()` | method | Modified | Takes a SPARQL query (text or a prepared object) and returns a `Result` | _unresolved_ |
| `reifications()` | method | New | Yields every `TripleTerm` that has at least one reifier and matches the given s/p/o pattern | _unresolved_ |
| `reified_triples()` | method | New | Takes a reifier node and yields the `TripleTerm`s it reifies | _unresolved_ |
| `reifier_annotations()` | method | New | Takes a `TripleTerm` and yields `(reifier, predicate, value)` annotation triples for its reifiers | _unresolved_ |
| `reifiers()` | method | New | Yields reifier nodes matching the given filters — `TT` (only reifiers of this triple term), `predicate`/`object` (only reifiers with that `(reifier, predicate, object)` triple present); filters combine with AND | _unresolved_ |
| `remove()` | method | Modified | Removes a triple and returns this graph; no-ops immediately — nothing removed, this graph returned unchanged — if a pattern's `TripleTerm` isn't registered | _unresolved_ |
| `remove_reification()` | method | New | Removes the `rdf:reifies` triple(s) for a given reifier and returns this graph | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.remove_reification` |
| `resolve_imports()` | method | New | Takes an optional `loader=` (an IRI → graph function, `None` if unresolvable; omit entirely if every declared import turns out to be locally satisfied — see `has_import_locally()` below) plus `mode=` (`"full"`/`"delta"`/`"in-place"`, same contract as `infer()`), and follows this graph's own `owl:imports` transitively (cycle-safe, with the same `^owl:versionIRI?/owl:imports` canonical-ID handling SHACL's own shapes-graph import resolution uses) — generalizes `validator.py`'s own `_resolve_shapes_graph_imports()` into a plain graph capability. Never calls `loader` for an import `has_import_locally()` already finds satisfied. See `starlayer.starontology.local_loader()` for a loader that only ever reads this project's own bundled files | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.resolve_imports` |
| `has_import_locally()` | method | New | Takes an `owl:imports` target IRI and returns whether this graph already has its own content for it (at least one triple with that IRI as subject) — the common case when two shapes-graph "modules" that import each other have simply been loaded together into one graph, with nothing external to fetch at all. `resolve_imports()` checks this before ever calling `loader` | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.has_import_locally` |
| `resource()` | method | Unchanged | Takes an identifier and returns a new `Resource` instance | _unresolved_ |
| `rollback()` | method | Unchanged | Rolls back active transactions and returns this graph | _unresolved_ |
| `serialize()` | method | Modified | Serializes the graph (any RDF 1.1/1.2 format this project supports). Returns the serialized text/bytes when no `destination` is given; when `destination` is given, writes to that path instead and returns this graph — matching rdflib's own `serialize()` contract | _unresolved_ |
| `set()` | method | Unchanged | Retracts every existing `(subject, predicate, *)` triple, then asserts exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation; returns this graph | _unresolved_ |
| `skolemize()` | method | Modified | Converts blank nodes in the graph to skolem IRIs and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) | _unresolved_ |
| `store` | property | Unchanged | The underlying rdflib `Store` instance | _unresolved_ |
| `subject_objects()` | method | Unchanged | Yields `(subject, object)` tuples for the given predicate | _unresolved_ |
| `subject_predicates()` | method | Unchanged | Yields `(subject, predicate)` tuples for the given object | _unresolved_ |
| `subjects()` | method | Unchanged | Yields subjects matching the given predicate/object | _unresolved_ |
| `toPython()` | method | Unchanged | Returns this graph itself — a `Graph` is its own Python-value form | _unresolved_ |
| `transitiveClosure()` | method | Unchanged | Takes a user-supplied function and a starting node, and yields its transitive closure over the graph | _unresolved_ |
| `transitive_objects()` | method | Unchanged | Takes a subject and predicate and transitively yields objects along that predicate | _unresolved_ |
| `transitive_subjects()` | method | Unchanged | Takes a predicate and object and transitively yields subjects along that predicate | _unresolved_ |
| `triple_terms()` | method | New | Yields every `TripleTerm` registered in this graph, with optional subject/predicate/object filters | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.triple_terms` |
| `triples()` | method | Modified | Takes an s/p/o pattern and yields matching triples, with any `TripleTerm`s restored to real objects | _unresolved_ |
| `triples_choices()` | method | Modified | Takes a choices pattern (any position may be a list of alternatives) and yields matching triples, with any `TripleTerm`s restored to real objects | _unresolved_ |
| `update()` | method | Modified | Takes a SPARQL Update (text or a prepared object), executes it against the graph, and returns nothing | _unresolved_ |
| `value()` | method | Unchanged | Takes a pair of criteria (subject/predicate, or predicate/object) and returns the matching value, or `None` if there isn't one | _unresolved_ |
| `add()` | method | Modified | Adds a triple to the default graph (`TripleTerm`-aware) and returns this dataset | _unresolved_ |
| `addN()` | method | Modified | Adds multiple quads, each routed to its own target graph's real store, and returns this dataset | _unresolved_ |
| `add_graph()` | method | Unchanged | Takes a `StarLayerGraph` and adds it as a named graph — an alias of `graph()`, for consistency with rdflib's own naming | _unresolved_ |
| `all_nodes()` | method | Unchanged | Returns the set of all nodes in the dataset | _unresolved_ |
| `bind()` | method | Unchanged | Binds a prefix to a namespace; returns nothing | _unresolved_ |
| `cbd()` | method | Modified | Computes the Concise Bounded Description of a resource and returns it as a `StarLayerGraph` — defaults `target_graph` to a new one (plain rdflib's own default crashes if the result contains a `TripleTerm`) | _unresolved_ |
| `close()` | method | Modified | Closes the underlying store, optionally committing pending writes first; returns nothing | _unresolved_ |
| `collection()` | method | Unchanged | Takes an identifier and returns a new `Collection` instance for it | _unresolved_ |
| `commit()` | method | Unchanged | Commits active transactions and returns this dataset | _unresolved_ |
| `compute_qname()` | method | Unchanged | Takes a URI and returns its qname tuple | _unresolved_ |
| `connected()` | method | Unchanged | Returns whether the graph is connected | _unresolved_ |
| `context_id()` | method | Unchanged | Takes a URI (and optional context ID) and returns a `URI#context` identifier | _unresolved_ |
| `contexts()` | method | Modified | Yields a `StarLayerGraph` for every named graph in this dataset | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.contexts` |
| `de_skolemize()` | method | Modified | Converts skolem IRIs back to blank nodes and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) | _unresolved_ |
| `default_context` | property | Unchanged | The dataset's default graph context — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.default_context is deprecated, use Dataset.default_graph instead`, confirmed live); use `default_graph` below instead | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.default_context` |
| `default_graph` | property | Unchanged | The dataset's default graph | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.default_graph` |
| `destroy()` | method | Unchanged | Destroys the identified store, if supported; returns this dataset | _unresolved_ |
| `get_context()` | method | Modified | Takes an identifier and returns the `StarLayerGraph` for the named graph with that identifier | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.get_context` |
| `get_graph()` | method | Unchanged | Takes an identifier and returns the graph with that identifier — **rdflib's own type hint says this can return `None`, but the real implementation never does: a missing identifier raises `IndexError` instead** (confirmed live — a pre-existing rdflib bug, not a StarLayer one); `get_context()` above never raises either, but for a different reason — it's get-or-create, silently returning a fresh empty graph for a missing identifier rather than distinguishing "exists" from "doesn't" | _unresolved_ |
| `graph()` | method | Unchanged | Takes an identifier and gets-or-creates that named graph context, returning it | _unresolved_ |
| `graphs()` | method | Unchanged | Yields every graph context in the dataset | _unresolved_ |
| `identifier` | property | Unchanged | The dataset's own identifier — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.identifier is deprecated and will be removed in future versions`, confirmed live) | _unresolved_ |
| `isomorphic()` | method | Unchanged | Takes another graph and returns whether the two are isomorphic | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.isomorphic` |
| `items()` | method | Unchanged | Takes an `rdf:List` resource and yields its items one at a time | _unresolved_ |
| `n3()` | method | Unchanged | Returns an n3 identifier for the graph | _unresolved_ |
| `namespace_manager` | property | Unchanged | This dataset's namespace manager | _unresolved_ |
| `namespaces()` | method | Unchanged | Yields every `(prefix, namespace)` binding on this dataset | _unresolved_ |
| `objects()` | method | Unchanged | Yields objects matching the given subject/predicate | _unresolved_ |
| `open()` | method | Modified | Opens a persistent store, rebuilds every per-context `TripleTerm` registry, and returns this dataset | _unresolved_ |
| `parse()` | method | Modified | Parses RDF data into named-graph contexts and returns this dataset | _unresolved_ |
| `predicate_objects()` | method | Unchanged | Yields `(predicate, object)` tuples for the given subject | _unresolved_ |
| `predicates()` | method | Unchanged | Yields predicates matching the given subject/object | _unresolved_ |
| `print()` | method | Unchanged | Prints the graph to stdout; returns nothing | `starlayer.graph.graph.starlayer_graph.StarLayerGraph.print` |
| `qname()` | method | Unchanged | Takes a URI and returns its qname string | _unresolved_ |
| `quads()` | method | Modified | Yields `(s, p, o, StarLayerGraph)` for every triple in the dataset, with internal encoding triples filtered out and `TripleTerm`s restored | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.quads` |
| `query()` | method | Modified | Takes a SPARQL query (text or a prepared object) and returns a `Result`, searching across all named graphs with SPARQL-star support | _unresolved_ |
| `reifications()` | method | New | Returns a `StarLayerDataset` of the `rdf:reifies` triples for every `TripleTerm` matching the given s/p/o pattern | _unresolved_ |
| `reified_triples()` | method | New | Takes a reifier node and returns a `StarLayerDataset` of the `rdf:reifies` triples for it | _unresolved_ |
| `reifier_annotations()` | method | New | Takes a `TripleTerm` and returns a `StarLayerDataset` of its `(reifier, predicate, value)` annotation triples | _unresolved_ |
| `reifiers()` | method | New | Returns a `StarLayerDataset` of every reifier's own triples matching the given filters | _unresolved_ |
| `remove()` | method | Modified | Removes a triple from the default graph (`TripleTerm`-aware) and returns this dataset | _unresolved_ |
| `remove_context()` | method | Unchanged | Removes the given context from the dataset; returns nothing | _unresolved_ |
| `remove_graph()` | method | Unchanged | Takes a named graph and removes it from the dataset, returning this dataset | _unresolved_ |
| `resource()` | method | Unchanged | Takes an identifier and returns a new `Resource` instance for it | _unresolved_ |
| `rollback()` | method | Unchanged | Rolls back active transactions and returns this dataset | _unresolved_ |
| `serialize()` | method | Modified | Serializes this dataset — returns the serialized text if no `destination` is given, or this dataset if one is | _unresolved_ |
| `set()` | method | Unchanged | Retracts every existing `(subject, predicate, *)` triple, then asserts exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation; returns this dataset | _unresolved_ |
| `skolemize()` | method | Modified | Converts blank nodes to skolem IRIs and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) | _unresolved_ |
| `store` | property | Unchanged | The underlying rdflib `Store` instance | _unresolved_ |
| `subject_objects()` | method | Unchanged | Yields `(subject, object)` tuples for the given predicate | _unresolved_ |
| `subject_predicates()` | method | Unchanged | Yields `(subject, predicate)` tuples for the given object | _unresolved_ |
| `subjects()` | method | Unchanged | Yields subjects matching the given predicate/object | _unresolved_ |
| `toPython()` | method | Unchanged | Returns this dataset itself | _unresolved_ |
| `to_graph()` | method | New | Flattens every quad in this dataset into one new `StarLayerGraph` and returns it | `starlayer.graph.graph.starlayer_dataset.StarLayerDataset.to_graph` |
| `transitiveClosure()` | method | Unchanged | Takes a user-supplied function and a starting node, and yields its transitive closure | _unresolved_ |
| `transitive_objects()` | method | Unchanged | Takes a subject and predicate and transitively yields objects along that predicate | _unresolved_ |
| `transitive_subjects()` | method | Unchanged | Takes a predicate and object and transitively yields subjects along that predicate | _unresolved_ |
| `triples()` | method | Modified | Yields `(s, p, o)` triples, scoped by `default_union` like rdflib's own `Dataset` (the default graph only, unless `default_union=True`) | _unresolved_ |
| `triples_choices()` | method | Modified | Takes a choices pattern and yields matching triples across the dataset, scoped the same way `triples()` is, with any `TripleTerm`s restored to real objects | _unresolved_ |
| `update()` | method | Modified | Takes a SPARQL Update (text or a prepared object), executes it across named graphs with SPARQL-star support, and returns nothing | _unresolved_ |
| `value()` | method | Unchanged | Takes a pair of criteria (subject/predicate, or predicate/object) and returns the matching value, or `None` if there isn't one | _unresolved_ |
| `subject` | attribute | New | The triple term's subject | _unresolved_ |
| `predicate` | attribute | New | The triple term's predicate | _unresolved_ |
| `object` | attribute | New | The triple term's object | _unresolved_ |
| `n3()` | method | New | Returns the N3/Turtle-1.2 (`<<( s p o )>>`) text form | _unresolved_ |
| `value` | attribute | New | The string's own text value | _unresolved_ |
| `language` | attribute | New | The BCP47 language tag | _unresolved_ |
| `direction` | attribute | New | The base direction (`ltr`/`rtl`) | _unresolved_ |
| `n3()` | method | New | Returns the N3/Turtle-1.2 (`"text"@lang--dir`) text form | _unresolved_ |

## `starlayer.sparql`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `prepare_query_12()` | function | New | Takes SPARQL 1.2 query text and returns an executable `Query` | `starlayer.sparql.parse12.prepare_query_12` |
| `prepare_update_12()` | function | New | Takes SPARQL 1.2 Update text and returns an executable `Update` | `starlayer.sparql.parse12.prepare_update_12` |
| `StarQuery` | class | New | Binds a SPARQL query (prepared once via `prepare_query_12()`) plus every option `StarLayerGraph.query()` otherwise takes per call (`entailment`, `initNs`, `initBindings`, `infer`, `engine`, `timeout`) — construct once, call `.run(graph, **overrides)` against as many graphs as needed, with any bound option overridable for one call without disturbing what's bound. Mirrors `StarShaclSchema`'s own "bind once, call repeatedly" shape. See its own module docstring for a real, pre-existing `StarLayerGraph.query()` gap found while building this (`entailment=ENTAILMENT.RDF`/`RDFS` silently has no effect when `query_object` is an already-prepared `Query` rather than text) and how `.run()` works around it | _unresolved_ |
| `sqe_parse_to_tree()` | function | New | Takes SPARQL query text and returns a `sqe:` encoded syntax tree (a `Graph`) | `starlayer.sparql.sqe.to_rdf.sqe_parse_to_tree` |
| `sqe_tree_to_query()` | function | New | Takes a `sqe:` syntax tree and root element and returns an executable `Query` | `starlayer.sparql.sqe.from_rdf.sqe_tree_to_query` |
| `sqe_tree_to_text()` | function | New | Takes a `sqe:` syntax tree and root element and returns SPARQL text | `starlayer.sparql.sqe.to_text.sqe_tree_to_text` |
| `sqe_validate()` | function | New | Takes a `sqe:` syntax tree and validates it against the `sqe_shacl` shapes, returning a SHACL validation report | `starlayer.sparql.sqe.shapes.sqe_validate` |
| `SQE` | value | New | The `sqe:` namespace | _unresolved_ |
| `parse_ruleset()` | function | New | Takes SRL text and returns an executable `RuleSet` — also enforces §4.2 well-formedness (no unbound head/filter/assignment variable, no `SET(...)` reusing an already-bound variable), raising `SRLParseError` if violated, the same one-gate contract plain SPARQL's own `prepareQuery()` has. A `RuleSet` you get your hands on is always both syntactically valid and well-formed — there's no separate "validate an already-parsed ruleset" step | `starlayer.sparql.srl.parse_ruleset` |
| `ruleset_to_text()` | function | New | Takes a `RuleSet` and returns SRL text — the inverse of `parse_ruleset()` | `starlayer.sparql.srl.ruleset_to_text` |
| `RuleSet` | class | New | A parsed rule set, returned by `parse_ruleset()` | `starlayer.sparql._srl_ast.RuleSet` |
| `RuleSet.infer(base_graph, *, inference=None, schema=None)` | method | **Modified** | Runs the rule set against `base_graph` to a fixpoint (§4.1's `Infer`), returning the inferred-triples-only graph — never includes anything already in `base_graph`. `inference=` (an `ENTAILMENT.*` regime, or iterable) pre-entails `base_graph` before the rule set runs, same spirit as SHACL's own `sh:entailment`-before-rules. `schema=` (a `StarShaclSchema` instance, or a bare shapes graph — either works) validates the inferred result; when given, the return becomes a `starlayer.shacl.RulesResult(inferred_graph, validation)` instead of a bare graph — omitting `schema=` (the default) keeps the original bare-graph return exactly as before | _unresolved_ |
| `RuleSet.query(base_graph, goal_pattern, *, inference=None)` | method | **Modified** | Runs `infer()` then returns every match of `goal_pattern` against `base_graph` ∪ inferred (§4.1's `Query`), one `dict[Variable, term]` solution per match. `inference=` pre-entails `base_graph` the same way `infer()`'s own does; no `schema=` here — this returns rows, not a graph, so there's nothing to validate | _unresolved_ |
| `TriplePattern` | class | New | A triple pattern/template — `subject`/`predicate`/`object`. Needed directly because it's `RuleSet.query()`'s own `goal_pattern` parameter type. Distinct from an RDF 1.2 *triple term* (`triple_term.TripleTermNode`, an atomic value that can fill a subject/object slot) — a `TriplePattern` is the 3-slot structure itself, never a term, though one of its slots can hold a triple term | `starlayer.sparql._srl_ast.TriplePattern` |
| `srl_parse_to_tree()` | function | New | Takes SRL text and returns an `srl:`-encoded syntax tree graph. Composes `parse_ruleset()` + `ruleset_to_tree()` | `starlayer.sparql.srl.srl_parse_to_tree` |
| `srl_tree_to_text()` | function | New | Takes an `srl:` syntax tree graph and returns SRL text. Composes `tree_to_ruleset()` + `ruleset_to_text()` | `starlayer.sparql.srl.srl_tree_to_text` |
| `ruleset_to_tree()` | function | New | Takes an executable `RuleSet` and returns an `srl:`-encoded syntax tree graph | `starlayer.sparql.srl.ruleset_to_tree` |
| `tree_to_ruleset()` | function | New | Takes an `srl:` syntax tree and returns an executable `RuleSet` | `starlayer.sparql.srl.tree_to_ruleset` |
| `srl_validate()` | function | New | Takes a `srl:` graph and validates it against `srl_shapes.ttl`, returning a SHACL validation report | `starlayer.sparql.srl.srl_validate` |
| `SRL` | value | New | The `srl:` namespace | _unresolved_ |

## `starlayer.shacl`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `StarShaclSchema` | class | New | Holds a SHACL shapes graph (plus optional ontology graph), to use with relevant SHACL methods, including validation, rule inferencing, or evaluation. See its own table below | `starlayer.shacl.validator.StarShaclSchema` |
| `validate()` | function | **Modified** | Takes a data graph, an optional shapes graph, an optional ontology graph, and an optional `inference=` keyword, and returns a `ValidationResult`. Raises `ValueError` if `shacl_graph` declares `owl:imports` and neither `shapes_graph_loader=` (resolves them) nor `ignore_imports=True` (proceeds anyway) is given — see the `owl:imports`/packaging note under `StarShaclSchema`'s own table below | _unresolved_ |
| `validate_each()` | function | **Modified** | Takes an iterable of data graphs, an optional shapes graph, an optional ontology graph, and an optional `inference=` keyword, and returns a dictionary of `ValidationResult`s | _unresolved_ |
| `evaluate()` | function | New | Takes a data graph, an optional shapes graph, an optional ontology graph, and an optional `inference=` keyword, and returns a plain graph object — SHACL 1.2 Node Expressions | _unresolved_ |
| `apply_rules()` | function | New | Takes a data graph, an optional shapes graph, an optional rule set IRI, and an optional `inference=` keyword, and returns a `RulesResult` | _unresolved_ |
| `extract_subgraph()` | function | **Modified** | Takes a data graph, an optional shapes graph, an optional ontology graph, optional `shape=`/`focus_node=` filters, and an optional `inference=` keyword, and returns the union of every conforming `(shape, focus_node)` pair's own extraction - empty (never `None`) if nothing conforms. Omit both filters to discover every real entry point the whole shapes graph declares; either alone narrows the search; both reproduces the original single-pair behavior | _unresolved_ |
| `target_nodes()` | function | New | Takes a data graph, a shape node, an optional shapes graph, an optional ontology graph, and an optional `inference=` keyword, and returns the shape's own target nodes in the data graph | _unresolved_ |
| `validate()` | method | **Modified** | Takes an optional data graph (falls back to the bound `data_graph`) and returns a `ValidationResult`, in place of pyshacl's own bare `(conforms, report_graph, report_text)` tuple. Same `shapes_graph_loader=`/`ignore_imports=` requirement as the top-level function when the bound `shacl_graph` declares `owl:imports` | _unresolved_ |
| `validate_each()` | method | **Modified** | Takes an optional iterable of data graphs (falls back to `(data_graph,)`) and returns `dict[int, ValidationResult]`, keyed by position, against this instance's own bound shapes graph | _unresolved_ |
| `apply_rules()` | method | **Modified** | Takes an optional data graph and returns a `RulesResult` — rule execution (`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, plus SHACL 1.2's own `sh:RuleSet`/`sh:sourceRule` provenance) | _unresolved_ |
| `evaluate()` | method | New | Takes an optional data graph and returns a plain graph object — SHACL 1.2 Node Expressions | _unresolved_ |
| `target_nodes()` | method | New | Takes an optional data graph and a required shape node, and returns the shape's own target nodes in the data graph | _unresolved_ |
| `evaluate_component()` | method | New | Takes a component/focus node/value nodes and evaluates one native `ConstraintComponent` directly | _unresolved_ |
| `close_shape()` | method | New | Takes a shape and returns a closed copy of this instance's own bound shapes graph — closes that shape and every shape it recursively references via `sh:node`/`sh:qualifiedValueShape`/`sh:and`/`sh:or`/`sh:xone` (not plain `sh:property`), stripping `sh:ignoredProperties` on each | `starlayer.shacl.validator.StarShaclSchema.close_shape` |
| `build_report()` | method | New | Takes component results and builds a `sh:ValidationReport` graph from them | _unresolved_ |
| `extract_shapes_graph()` | method | New | Takes the IRI of one `sh:ShapesGraph`-typed resource declared in this instance's own bound shapes graph, and returns just that resource's own "module" as a standalone graph (or `None` if the IRI isn't typed `a sh:ShapesGraph`) — the inverse of SHACL 1.2 Profiling §2's packaging convention. Honors all three documented membership mechanisms: `rdfs:member` (forward), `rdfs:isDefinedBy` (inverse), and `owl:imports` among already-co-located `sh:ShapesGraph` nodes (transitive) — raises `ValueError` if an `owl:imports` target isn't itself a `sh:ShapesGraph` already present in `shacl_graph` (missing entirely, or present but untyped), rather than silently skipping it; call `resolve_imports(loader=...)` on `shacl_graph` first if it needs fetching from elsewhere. Does **not** recurse into a member's own `sh:property`/`sh:node`/etc. to pull in a *named* shape it references — Profiling gives no completeness rule for this (§2.7 is an unwritten `TODO`), so a dangling reference is left as-is, letting a caller inject their own replacement for it without a stale copy riding along | `starlayer.shacl.validator.StarShaclSchema.extract_shapes_graph` |
| `node_expressions.eval_expr()` | function | New | Evaluates one node expression directly against a single focus node, independent of `evaluate()`'s own per-shape orchestration | `starlayer.shacl.node_expressions.eval_expr` |
| `asset_urls.get_raw_url()` | function | New | Takes `"conformance_profile"` and returns a real `raw.githubusercontent.com` URL for that bundled SHACL asset file — all three are already real, standalone files on disk, so this is pure URL-minting (unlike `starlayer.starontology.get_raw_url()`'s own entries, which needed a publish step first — see that function's own docs). `None` for an unrecognized name | _unresolved_ |
| `shacl_profiling.declared_conformance_profile()` | function | New | Returns a fresh copy of starlayer.shacl's bundled self-declared SHACL 1.2 conformance graph (§3 — which named feature-profiles this library implements) | _unresolved_ |
| `shacl_profiling.derive_conforms_to()` | function | New | Takes a validation report and derives `sh:conformsTo` from it (§5.5) — optionally also `dcterms:conformsTo` if a `specification_graph=` declaring `prof:isProfileOf` is supplied (see `starlayer.starontology.get_profile_graph()` for a ready-made one). Returns `report_graph` merged with whatever got derived by default (2026-10-11) — self-contained and immediately printable, so the `sh:validationReport` link it adds resolves to a real node rather than a dangling blank reference; pass `conforms_only=True` for just the `sh:conformsTo`/`dcterms:conformsTo` triples themselves — not `report_graph`, and not even that `sh:validationReport` link | _unresolved_ |
| `validation_modes.ValidationMode` | class | New | `(name, options)` — one named option preset | `starlayer.shacl.validation_modes.ValidationMode` |
| `validation_modes.available_modes()` | function | New | Returns the list of built-in preset names (`"validation"`, `"rules"`, `"debug"`) | `starlayer.shacl.validation_modes.available_modes` |
| `validation_modes.get_mode()` | function | New | Takes a preset name and returns the matching `ValidationMode` | `starlayer.shacl.validation_modes.get_mode` |
| `validation_modes.resolve_mode_options()` | function | New | Takes a mode and caller overrides, and returns the resolved options dict | `starlayer.shacl.validation_modes.resolve_mode_options` |
| `TripleTermAdapter` | class | New | Encodes/decodes triple terms so pySHACL can process RDF-1.1-compatible graphs | `starlayer.shacl.adapters.TripleTermAdapter` |
| `TripleTermGraph` | class | New | A simple graph-like container that can hold triple-term objects directly | `starlayer.shacl.adapters.TripleTermGraph` |
| `TripleTermValue` | class | New | `(subject, predicate, object)` value type for the adapter layer | `starlayer.shacl.adapters.TripleTermValue` |
| `normalize_to_starlayer_graph()` | function | New | Takes any graph-like input and returns it normalized to a `StarLayerGraph` | `starlayer.shacl.engine.normalization.normalize_to_starlayer_graph` |
| `normalize_graph_inputs()` | function | New | Takes a data/shapes/ontology graph in any of the shapes callers may pass, and returns them normalized | `starlayer.shacl.engine.normalization.normalize_graph_inputs` |
| `StarLayerGraphProtocol` | class | New | Structural protocol every graph-like input must satisfy | `starlayer.shacl.types.StarLayerGraphProtocol` |
| `MutableStarLayerGraphProtocol` | class | New | `StarLayerGraphProtocol` plus mutation methods | `starlayer.shacl.types.MutableStarLayerGraphProtocol` |
| `engine.ComponentRequest` | class | New | `(component, focus_node, value_nodes, options)` — one native-component evaluation request, `evaluate_component()`'s own sole argument | _unresolved_ |
| `engine.evaluate_component()` | function | New | Takes a `ComponentRequest` and evaluates one native `ConstraintComponent` directly | _unresolved_ |
| `engine.build_report()` | function | New | Takes component results and builds a `sh:ValidationReport` graph from them | _unresolved_ |
| `engine.STSH` | value | New | The starlayer.shacl-native-extensions namespace | _unresolved_ |

## `starlayer.starontology`

| Name | Kind | Status | Description | codekg identifier |
|---|---|---|---|---|
| `get_ontology_list()` | function | New | Returns every registered entry's metadata (`name`, `description`, `type`), sorted by name — see below | `starlayer.starontology.__init__.get_ontology_list` |
| `get_ontology_graph()` | function | New | Takes a registered name and returns a fresh `StarLayerGraph` of that entry | `starlayer.starontology.__init__.get_ontology_graph` |
| `OntologyInfo` | class | New | One registry entry: `name`, `description`, `type` (`"shacl"` / `"ast-graph"` / `"owl"`) | `starlayer.starontology.__init__.OntologyInfo` |
| `get_conformance_profiles()` | function | New | Returns every registered shapes graph's real relationship to its specification, as one fresh `StarLayerGraph` — loads the bundled `ontology-shapes-profiles.ttl` by default; pass `url=` to load a different local path or `http(s)://` location instead (a newer canonical copy, a local override for testing). A real, persisted third document relating both endpoints, not synthesized from a Python dict on every call (2026-10-09). Each shapes graph is `prof:isProfileOf` the real external specification it implements (SPARQL, SKOS, Manchester Syntax, SPARQL-RL) — corrected 2026-10-10; the original design wrongly made the bundled ontology/AST graph the object of `isProfileOf` instead, which is now one of that same real spec's own `prof:hasResource`/`prof:ResourceDescriptor` entries (`role:schema`, a sibling of the shapes graph's own `role:validation` descriptor) — see `get_profile_graph()`'s own docstring for the full account. Returned a plain `rdflib.Graph` until 2026-10-10 — fixed to match this registry's own stated "every loader returns a `StarLayerGraph`" convention, found via a real `.serialize(format="turtle12")` failure (that format is a `StarLayerGraph.serialize()` override, not a real rdflib plugin, so it never worked on this one function's result) | `starlayer.starontology.__init__.get_conformance_profiles` |
| `get_profile_graph()` | function | New | Takes a registered shapes-entry name (e.g. `"skos_shacl"`) and an optional `url=` (forwarded to `get_conformance_profiles()`), and returns a small `StarLayerGraph` with that entry's own `prof:isProfileOf` triple against the real specification, plus the full `prof:hasResource`/`prof:ResourceDescriptor` structure describing both the shapes graph (`role:validation`) and its paired ontology/AST graph (`role:schema`) as resources *of* that same spec — discovered via a breadth-first walk from the shapes graph's own resource IRI, not a hardcoded hop count. `None` for `"shacl_meta"` or an unregistered name; an *empty* graph (not `None`) if the name is registered but the loaded document simply has nothing to say about it (e.g. a sparse `url=` override). Ready to pass as `shacl_profiling.derive_conforms_to()`'s own `specification_graph=` | `starlayer.starontology.__init__.get_profile_graph` |
| `get_resource_iri()` | function | New | Takes any registered name and returns the stable resource IRI `get_profile_graph()` uses for it — pass this as `validate(..., shapes_graph_resource=...)` when validating against one of this registry's own shapes graphs, so `derive_conforms_to()`'s second rule can actually match it. `None` for `"shacl_meta"` or an unregistered name | `starlayer.starontology.__init__.get_resource_iri` |
| `get_raw_url()` | function | New | Takes any registered name, plus `"ontology_shapes_profiles"` (the profiles-mapping document itself, which has no `get_resource_iri()` entry), and returns a real `raw.githubusercontent.com` URL — actually fetchable content, unlike `get_resource_iri()`'s GitHub blob URL (which renders an HTML viewer page to a plain HTTP GET, not the file's bytes). Only real once `scripts/publish_starontology_files.py`'s own output has been committed (2026-10-14) — see that script's own docstring. `None` for an unrecognized name | _unresolved_ |
| `local_loader()` | function | New | A `StarLayerGraph.resolve_imports()`-compatible loader (IRI → graph, `None` if not registered) that only ever reads this package's own bundled files — never the network. Resolves against each shapes entry's own *real* `sh:ShapesGraph` node (what its `owl:imports` triples actually point at) — a different IRI than `get_resource_iri()`'s own GitHub-blob-URL scheme, see the note below | `starlayer.starontology.__init__.local_loader` |
| `manchester_parse_to_tree()` | function | New | Takes Manchester text and returns a `manch:`-encoded syntax tree (a `Graph`) | `starlayer.starontology.manchester.manchester_parse_to_tree` |
| `manchester_tree_to_text()` | function | New | Takes a `manch:` syntax tree and returns Manchester text | `starlayer.starontology.manchester.manchester_tree_to_text` |
| `manchester_tree_to_owl()` | function | New | Takes a `manch:` syntax tree and returns the compiled OWL graph (a `StarLayerGraph`) | `starlayer.starontology.manchester.manchester_tree_to_owl` |
| `manchester_validate()` | function | New | Takes a `manch:` graph and validates it against `manchester_shapes.ttl`, returning `(conforms, report_graph, report_text)` | `starlayer.starontology.manchester.manchester_validate` |
| `skos_validate()` | function | New | Takes a `skos:` graph and validates it against `skos_shapes.ttl`, returning `(conforms, report_graph, report_text)` | `starlayer.starontology.skos.skos_validate` |
