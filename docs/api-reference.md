# StarLayer API Reference

*An organized index of names available in StarLayer.*


**Status**
- **New** StarLayer-only, no such name on the base class.
- **Modified** StarLayer overrides/extends the base class's own method of the same name.
- **Unchanged** inherited as-is from base class.


---

## `starlayer`

`starlayer` consists of one installable package with four subpackages:

| Subpackage | Holds |
|---|---|
| `starlayer.graph` | Management of RDF 1.2 graphs — the rdflib wrapper |
| `starlayer.sparql` | Query of RDF 1.2 graphs |
| `starlayer.shacl` | SHACL 1.2 over graphs — the pyshacl wrapper |
| `starlayer.starontology` | Access ontology files |

A limited number of top-level classes are available from `starlayer`.

`from starlayer import ...`

| Name | Kind | Status | Description |
|---|---|---|---|
| `StarLayerGraph` | class | New | Also available from `starlayer.graph` below |
| `StarLayerDataset` | class | New | Also available from `starlayer.graph` below |
| `StarLayerShacl` | class | New | Also available from `starlayer.shacl` below |


---

## `starlayer.graph`

Imports rdflib.

Classes, functions and values available from `starlayer.graph`

`from starlayer.graph import ...`

| Name | Kind | Status | Description |
|---|---|---|---|
| `StarLayerGraph` | class | New | `rdflib.Graph` extended with RDF 1.2 triple-term support |
| `StarLayerDataset` | class | New | `rdflib.Dataset` extended with RDF 1.2 triple-term support — an RDF dataset where every named-graph context is a `StarLayerGraph` |
| `TripleTerm` | class | New | An RDF 1.2 triple term used as a resource |
| `DirLangString` | class | New | An RDF 1.2 directional language-tagged string literal |
| `parseQuery()` | function | Modified | Takes SPARQL 1.2 SELECT/ASK/CONSTRUCT/DESCRIBE query text and returns its raw parse tree, a pyparsing `ParseResults` — not yet a compiled `Query` object |
| `prepareQuery()` | function | Modified | Takes SPARQL 1.2 query text and returns a prepared `Query` object, ready to pass to `.query()` |
| `parseUpdate()` | function | Modified | Takes SPARQL 1.2 Update text and returns its raw parse tree, a pyparsing `ParseResults` — not yet a compiled `Update` object |
| `prepareUpdate()` | function | Modified | Takes SPARQL 1.2 Update text and returns a prepared `Update` object, ready to pass to `.update()` |
| `processUpdate()` | function | Modified | Takes a graph and SPARQL 1.2 Update text, executes the update directly against the graph, and returns nothing |
| `BNode` | class | Unchanged | rdflib's own blank node term type |
| `Literal` | class | Unchanged | rdflib's own literal term type |
| `URIRef` | class | Unchanged | rdflib's own IRI term type |
| `Variable` | class | Unchanged | rdflib's own SPARQL variable type |
| `Namespace` | class | Unchanged | rdflib's own "generate URIRefs with a common prefix" helper |
| `RDF` | value | Unchanged | rdflib's bound `RDF:` namespace |
| `RDFS` | value | Unchanged | rdflib's bound `RDFS:` namespace |
| `XSD` | value | Unchanged | rdflib's bound `XSD:` namespace |
| `Graph` | class | Unchanged | Plain `rdflib.Graph` (re-exported for convenience) |
| `Dataset` | class | Unchanged | Plain `rdflib.Dataset` (re-exported for convenience) |
| `Collection` | class | Unchanged | rdflib's own `rdf:List` wrapper |

### `StarLayerGraph`

Construct with `StarLayerGraph(store='default', identifier=None, namespace_manager=None, base=None, bind_namespaces='rdflib', backend='rdf-1.1')` — the same arguments as `rdflib.Graph`, plus: 
- `backend` must be `'rdf-1.1'` or `'rdf-1.2'`. 

| Name | Kind | Status | Description |
|---|---|---|---|
| `add()` | method | Modified | Takes a triple `(subject, predicate, object)` , adds to the graph and returns this graph |
| `addN()` | method | Modified | Takes an iterable of `(subject, predicate, object, context)` 4-tuples, adds them all at once, and returns this graph. `context` is expected to be this graph itself — a mismatched context is silently dropped, not added |
| `add_reification()` | method | New | Takes a reifier node and a `TripleTerm`, asserts `reifier rdf:reifies triple_term` to make the node an official reifier, and returns this graph |
| `add_reifier_annotation()` | method | New | Takes an annotation predicate and value (`predicate`, `obj`) and an optional `name`, creates a reifier node (a `URIRef` if `name` is given, otherwise a fresh `BNode`), adds the one annotation property to it, and returns the new reifier node — ready to pass straight into `add_reification()` |
| `all_nodes()` | method | Unchanged | Returns the set of all subjects and objects in the graph, as a plain Python `set`.|
| `bind()` | method | Unchanged | Binds a prefix to a namespace; returns nothing |
| `cbd()` | method | Modified | Takes a resource and computes its Concise Bounded Description, returning it as a `StarLayerGraph`. The optional `target_graph` is the *output* — the graph the CBD results get added to, not a copy the resource is read from — and defaults to a new `StarLayerGraph` if not given; it must itself be a `StarLayerGraph` (a plain `Graph` can't store `TripleTerm`s) |
| `close()` | method | Modified | Closes the underlying store, optionally committing pending writes first; returns nothing |
| `collection()` | method | Unchanged | Takes an identifier (the list's head node) and returns a `Collection` — a thin Python object (not a graph itself) that holds a reference to this graph plus that identifier, and reads/writes the `rdf:List` as ordinary triples in this graph; mutating the `Collection` (e.g. `+=`) mutates this graph directly, nothing is stored on the `Collection` itself |
| `commit()` | method | Unchanged | Commits active transactions and returns this graph. |
| `compute_qname()` | method | Unchanged | Takes a URI and returns its `(prefix, namespace, localname)` qname tuple, resolved against this graph's own bound namespaces (its `namespace_manager`) |
| `connected()` | method | Unchanged | Returns whether the graph is connected when treated as an undirected graph of nodes — every node reachable from every other via some triple. Unrelated to any backend store connection |
| `de_skolemize()` | method | Modified | Converts skolem IRIs in the graph back to blank nodes and returns the result as a `StarLayerGraph`. Takes an optional `new_graph` (the target to write into, defaulting to a fresh `StarLayerGraph`) and `uriref` (limit the conversion to one specific skolem IRI). Overridden because rdflib's own inherited version hardcodes a plain `rdflib.Graph()` as that default target, which crashes with `AssertionError` the moment the graph being de-skolemized contains a real `TripleTerm` (plain `Graph.add()` rejects it outright) |
| `derive_shape()` | method | New | Infers a SHACL shape from the graph's own data (one `sh:NodeShape` per class) and returns it as a `StarLayerGraph` |
| `destroy()` | method | Unchanged | Destroys the identified store, if the backend supports it; returns this graph|
| `from_rdflib()` | class method | New | Takes a plain `rdflib.Graph` and returns it  as a `StarLayerGraph` |
| `has_triple_term()` | method | New | Takes a subject/predicate/object and returns `True` if a `TripleTerm` with these exact components exists in the graph |
| `identifier` | property | Unchanged | The graph's own identifier (a `URIRef` or `BNode`) |
| `infer()` | method | New | Takes a `profile` string naming the entailment regime to run (`"rdfs"`, `"owl-rl"`, `"rdfs+owl-rl"`, or `"owl-dl"`), materializes that closure, and returns it as a `StarLayerGraph` |
| `isomorphic()` | method | Modified | Takes another graph and returns a boolean whether the two are isomorphic |
| `items()` | method | Unchanged | Takes an `rdf:List` resource and yields its items one at a time, as a generator, rather than returning them all as a single list |
| `n3()` | method | Unchanged | Returns an n3 identifier for the graph |
| `namespace_manager` | property | Unchanged | Returns this graph's namespace manager |
| `namespaces()` | method | Unchanged | Yields every `(prefix, namespace)` binding on this graph, one `(str, URIRef)` pair at a time |
| `objects()` | method | Unchanged | Yields objects matching the given subject/predicate (optionally unique only), one term at a time as a generator |
| `open()` | method | Modified | Opens a persistent store and returns this graph |
| `parse()` | method | Modified | Takes RDF data — from `source` (a file path, URL, or file-like object), or explicitly via `location`/`file`/`data` — plus a `format=` string (any RDF 1.1/1.2 format this project supports), parses it into the graph, and returns this graph. For a multi-graph-capable format (`nquads`/`trig`/`trix`/`nq12`/`trig12`/`trix12`), raises `MultipleGraphsError` if the data spans more than one distinct graph — see `format=` below |
| `predicate_objects()` | method | Unchanged | Yields `(predicate, object)` tuples for the given subject, one pair at a time as a generator (optionally unique only) |
| `predicates()` | method | Unchanged | Yields predicates matching the given subject/object |
| `print()` | method | Modified | Prints the graph to stdout — defaults to `turtle12`. Returns nothing |
| `qname()` | method | Unchanged | Takes a URI and returns its qname string |
| `qname_term()` | method | New | Takes any term (`URIRef`, `BNode`, `Literal`, `TripleTerm`, `DirLangString`) and returns its prefixed n3 form |
| `query()` | method | Modified | Takes a SPARQL query (text or a prepared object) and returns a `Result` |
| `reifications()` | method | New | Yields every `TripleTerm` that has at least one reifier and matches the given s/p/o pattern |
| `reified_triples()` | method | New | Takes a reifier node and yields the `TripleTerm`s it reifies |
| `reifier_annotations()` | method | New | Takes a `TripleTerm` and yields `(reifier, predicate, value)` annotation triples for its reifiers |
| `reifiers()` | method | New | Yields reifier nodes matching the given filters — `TT` (only reifiers of this triple term), `predicate`/`object` (only reifiers with that `(reifier, predicate, object)` triple present); filters combine with AND |
| `remove()` | method | Modified | Removes a triple and returns this graph; no-ops immediately — nothing removed, this graph returned unchanged — if a pattern's `TripleTerm` isn't registered |
| `remove_reification()` | method | New | Removes the `rdf:reifies` triple(s) for a given reifier and returns this graph |
| `resource()` | method | Unchanged | Takes an identifier and returns a new `Resource` instance |
| `rollback()` | method | Unchanged | Rolls back active transactions and returns this graph |
| `serialize()` | method | Modified | Serializes the graph (any RDF 1.1/1.2 format this project supports). Returns the serialized text/bytes when no `destination` is given; when `destination` is given, writes to that path instead and returns this graph — matching rdflib's own `serialize()` contract |
| `set()` | method | Unchanged | Retracts every existing `(subject, predicate, *)` triple, then asserts exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation; returns this graph |
| `skolemize()` | method | Modified | Converts blank nodes in the graph to skolem IRIs and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `store` | property | Unchanged | The underlying rdflib `Store` instance |
| `subject_objects()` | method | Unchanged | Yields `(subject, object)` tuples for the given predicate |
| `subject_predicates()` | method | Unchanged | Yields `(subject, predicate)` tuples for the given object |
| `subjects()` | method | Unchanged | Yields subjects matching the given predicate/object |
| `toPython()` | method | Unchanged | Returns this graph itself — a `Graph` is its own Python-value form |
| `transitiveClosure()` | method | Unchanged | Takes a user-supplied function and a starting node, and yields its transitive closure over the graph |
| `transitive_objects()` | method | Unchanged | Takes a subject and predicate and transitively yields objects along that predicate |
| `transitive_subjects()` | method | Unchanged | Takes a predicate and object and transitively yields subjects along that predicate |
| `triple_terms()` | method | New | Yields every `TripleTerm` registered in this graph, with optional subject/predicate/object filters |
| `triples()` | method | Modified | Takes an s/p/o pattern and yields matching triples, with any `TripleTerm`s restored to real objects |
| `triples_choices()` | method | Modified | Takes a choices pattern (any position may be a list of alternatives) and yields matching triples, with any `TripleTerm`s restored to real objects |
| `update()` | method | Modified | Takes a SPARQL Update (text or a prepared object), executes it against the graph, and returns nothing |
| `value()` | method | Unchanged | Takes a pair of criteria (subject/predicate, or predicate/object) and returns the matching value, or `None` if there isn't one |

### `StarLayerDataset` — full member surface

Construct with `StarLayerDataset(store='default', default_union=False, default_graph_base=None, backend='rdf-1.1')` — the same arguments as `rdflib.Dataset`, plus: 
- `backend` must be `'rdf-1.1'` or `'rdf-1.2'`. 

| Name | Kind | Status | Description |
|---|---|---|---|
| `add()` | method | Modified | Adds a triple to the default graph (`TripleTerm`-aware) and returns this dataset |
| `addN()` | method | Modified | Adds multiple quads, each routed to its own target graph's real store, and returns this dataset |
| `add_graph()` | method | Unchanged | Takes a `StarLayerGraph` and adds it as a named graph — an alias of `graph()`, for consistency with rdflib's own naming |
| `all_nodes()` | method | Unchanged | Returns the set of all nodes in the dataset |
| `bind()` | method | Unchanged | Binds a prefix to a namespace; returns nothing |
| `cbd()` | method | Modified | Computes the Concise Bounded Description of a resource and returns it as a `StarLayerGraph` — defaults `target_graph` to a new one (plain rdflib's own default crashes if the result contains a `TripleTerm`) |
| `close()` | method | Modified | Closes the underlying store, optionally committing pending writes first; returns nothing |
| `collection()` | method | Unchanged | Takes an identifier and returns a new `Collection` instance for it |
| `commit()` | method | Unchanged | Commits active transactions and returns this dataset |
| `compute_qname()` | method | Unchanged | Takes a URI and returns its qname tuple |
| `connected()` | method | Unchanged | Returns whether the graph is connected |
| `context_id()` | method | Unchanged | Takes a URI (and optional context ID) and returns a `URI#context` identifier |
| `contexts()` | method | Modified | Yields a `StarLayerGraph` for every named graph in this dataset |
| `de_skolemize()` | method | Modified | Converts skolem IRIs back to blank nodes and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `default_context` | property | Unchanged | The dataset's default graph context — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.default_context is deprecated, use Dataset.default_graph instead`, confirmed live); use `default_graph` below instead |
| `default_graph` | property | Unchanged | The dataset's default graph |
| `destroy()` | method | Unchanged | Destroys the identified store, if supported; returns this dataset |
| `get_context()` | method | Modified | Takes an identifier and returns the `StarLayerGraph` for the named graph with that identifier |
| `get_graph()` | method | Unchanged | Takes an identifier and returns the graph with that identifier — **rdflib's own type hint says this can return `None`, but the real implementation never does: a missing identifier raises `IndexError` instead** (confirmed live — a pre-existing rdflib bug, not a StarLayer one); `get_context()` above never raises either, but for a different reason — it's get-or-create, silently returning a fresh empty graph for a missing identifier rather than distinguishing "exists" from "doesn't" |
| `graph()` | method | Unchanged | Takes an identifier and gets-or-creates that named graph context, returning it |
| `graphs()` | method | Unchanged | Yields every graph context in the dataset |
| `identifier` | property | Unchanged | The dataset's own identifier — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.identifier is deprecated and will be removed in future versions`, confirmed live) |
| `isomorphic()` | method | Unchanged | Takes another graph and returns whether the two are isomorphic |
| `items()` | method | Unchanged | Takes an `rdf:List` resource and yields its items one at a time |
| `n3()` | method | Unchanged | Returns an n3 identifier for the graph |
| `namespace_manager` | property | Unchanged | This dataset's namespace manager |
| `namespaces()` | method | Unchanged | Yields every `(prefix, namespace)` binding on this dataset |
| `objects()` | method | Unchanged | Yields objects matching the given subject/predicate |
| `open()` | method | Modified | Opens a persistent store, rebuilds every per-context `TripleTerm` registry, and returns this dataset |
| `parse()` | method | Modified | Parses RDF data into named-graph contexts and returns this dataset |
| `predicate_objects()` | method | Unchanged | Yields `(predicate, object)` tuples for the given subject |
| `predicates()` | method | Unchanged | Yields predicates matching the given subject/object |
| `print()` | method | Unchanged | Prints the graph to stdout; returns nothing |
| `qname()` | method | Unchanged | Takes a URI and returns its qname string |
| `quads()` | method | Modified | Yields `(s, p, o, StarLayerGraph)` for every triple in the dataset, with internal encoding triples filtered out and `TripleTerm`s restored |
| `query()` | method | Modified | Takes a SPARQL query (text or a prepared object) and returns a `Result`, searching across all named graphs with SPARQL-star support |
| `reifications()` | method | New | Returns a `StarLayerDataset` of the `rdf:reifies` triples for every `TripleTerm` matching the given s/p/o pattern |
| `reified_triples()` | method | New | Takes a reifier node and returns a `StarLayerDataset` of the `rdf:reifies` triples for it |
| `reifier_annotations()` | method | New | Takes a `TripleTerm` and returns a `StarLayerDataset` of its `(reifier, predicate, value)` annotation triples |
| `reifiers()` | method | New | Returns a `StarLayerDataset` of every reifier's own triples matching the given filters |
| `remove()` | method | Modified | Removes a triple from the default graph (`TripleTerm`-aware) and returns this dataset |
| `remove_context()` | method | Unchanged | Removes the given context from the dataset; returns nothing |
| `remove_graph()` | method | Unchanged | Takes a named graph and removes it from the dataset, returning this dataset |
| `resource()` | method | Unchanged | Takes an identifier and returns a new `Resource` instance for it |
| `rollback()` | method | Unchanged | Rolls back active transactions and returns this dataset |
| `serialize()` | method | Modified | Serializes this dataset — returns the serialized text if no `destination` is given, or this dataset if one is |
| `set()` | method | Unchanged | Retracts every existing `(subject, predicate, *)` triple, then asserts exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation; returns this dataset |
| `skolemize()` | method | Modified | Converts blank nodes to skolem IRIs and returns the result as a `StarLayerGraph` — defaults `new_graph` to a new one (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `store` | property | Unchanged | The underlying rdflib `Store` instance |
| `subject_objects()` | method | Unchanged | Yields `(subject, object)` tuples for the given predicate |
| `subject_predicates()` | method | Unchanged | Yields `(subject, predicate)` tuples for the given object |
| `subjects()` | method | Unchanged | Yields subjects matching the given predicate/object |
| `toPython()` | method | Unchanged | Returns this dataset itself |
| `to_graph()` | method | New | Flattens every quad in this dataset into one new `StarLayerGraph` and returns it |
| `transitiveClosure()` | method | Unchanged | Takes a user-supplied function and a starting node, and yields its transitive closure |
| `transitive_objects()` | method | Unchanged | Takes a subject and predicate and transitively yields objects along that predicate |
| `transitive_subjects()` | method | Unchanged | Takes a predicate and object and transitively yields subjects along that predicate |
| `triples()` | method | Modified | Yields `(s, p, o)` triples, scoped by `default_union` like rdflib's own `Dataset` (the default graph only, unless `default_union=True`) |
| `triples_choices()` | method | Modified | Takes a choices pattern and yields matching triples across the dataset, scoped the same way `triples()` is, with any `TripleTerm`s restored to real objects |
| `update()` | method | Modified | Takes a SPARQL Update (text or a prepared object), executes it across named graphs with SPARQL-star support, and returns nothing |
| `value()` | method | Unchanged | Takes a pair of criteria (subject/predicate, or predicate/object) and returns the matching value, or `None` if there isn't one |

### Supported `format=` values for `parse()`/`serialize()`

**Graph formats**

| Format | File extension | Description |
|---|---|---|
| `turtle` / `turtle12` | `.ttl` | Turtle — compact, human-readable RDF syntax |
| `longturtle12` | `.ttl` | Turtle, one triple per line, no subject grouping |
| `nt` / `nt12` | `.nt` | N-Triples — one fully-written-out triple per line, no prefixes |
| `xml` / `rdfxml12` | `.rdf` | RDF/XML |
| `json-ld` | `.jsonld` | JSON-LD, RDF 1.1 only — no RDF 1.2 companion spec exists. |
| `manchester` (alias `omn`) | `.omn` | OWL 2 Manchester Syntax |
| `n3` / `n3-12` | `.n3` | Parses and serializes as Turtle. Must be valid Turtle or Turtle 1.2 — real N3 (formulas, `=>` rules, `?x` variables) is not supported |
| any other rdflib-recognized format | — | Not supported by StarLayer. Unpredictable results. |

When using the above formats with `StarLayerDataset.parse()` the default graph of the dataset is populated. When using the formats with `StarLayerDataset.serialize()`, the different graphs are flattened into a single output, discarding graph-name information.

`manchester` here compiles straight to OWL semantics not to be confused with Manchester text as its own syntax tree (`manch:` RDF, independent of the OWL semantics), which is `starlayer.starontology.manchester`, a separate section below.

**Dataset formats**

| Format | File extension | Description |
|---|---|---|
| `nquads` / `nq12` | `.nq` | N-Quads — like N-Triples, but a 4th term per line names which graph that triple belongs to |
| `trig` / `trig12` | `.trig` | TriG — like Turtle, but wraps each named graph's triples in a `GRAPH <name> { ... }` block |
| `trix` / `trix12` | `.trix` | TriX — XML syntax; each graph is a `<graph>` element (optionally named by a `<uri>` child) containing `<triple>` elements |

These are best used with `StarLayerDataset`. `StarLayerGraph.parse()` raises `MultipleGraphsError` unless all triples resolve to a single graph. `StarLayerGraph.serialize()` assignins the triples to a graph named by the graph's own identifier.

### `TripleTerm`

Construct with `TripleTerm(subject, predicate, object)`. 
- `subject` must be a `URIRef` or `BNode`; 
- `predicate` must be a `URIRef`; 
- `object` can be any RDF term, including another `TripleTerm` (for nesting). 

| Name | Kind | Status | Description |
|---|---|---|---|
| `subject` | attribute | New | The triple term's subject |
| `predicate` | attribute | New | The triple term's predicate |
| `object` | attribute | New | The triple term's object |
| `n3()` | method | New | Returns the N3/Turtle-1.2 (`<<( s p o )>>`) text form |

### `DirLangString`

Construct with `DirLangString(value, language, direction)`. 
- `language` must be a non-empty tag; 
- `direction` must be `'ltr'` or `'rtl'`. 

| Name | Kind | Status | Description |
|---|---|---|---|
| `value` | attribute | New | The string's own text value |
| `language` | attribute | New | The BCP47 language tag |
| `direction` | attribute | New | The base direction (`ltr`/`rtl`) |
| `n3()` | method | New | Returns the N3/Turtle-1.2 (`"text"@lang--dir`) text form |

---

## `starlayer.sparql`

### Top-level (`from starlayer.sparql import ...`)

| Name | Kind | Status | Description |
|---|---|---|---|
| `prepare_query_12()` | function | New | Takes SPARQL 1.2 query text and returns an executable `Query` (real triple terms, annotation syntax) |
| `prepare_update_12()` | function | New | Takes SPARQL 1.2 Update text and returns an executable `Update` |
| `translate_algebra_12()` | function | New | Takes SPARQL 1.2 algebra and returns SELECT/CONSTRUCT text |
| `query_to_rdf()` | function | New | Takes a prepared `Query` and encodes it as `salg:` RDF, returning `(graph, root)` |
| `rdf_to_query()` | function | New | Takes `salg:` RDF (a graph and root node) and decodes it back into a real `Query` |
| `update_to_rdf()` | function | New | Takes a prepared `Update` and encodes it as `salg:` RDF, returning `(graph, root)` |
| `rdf_to_update()` | function | New | Takes `salg:` RDF (a graph and root node) and decodes it back into a real `Update` |
| `queries_to_collection()` | function | New | Takes a list of independent queries and encodes them as one `salg:QueryCollection` graph |
| `rdf_to_collection()` | function | New | Takes `salg:` RDF (a graph and root node) and decodes it back into a list of `Query` objects |
| `ontology_graph()` | function | New | Returns the `salg:` RDFS ontology |
| `shapes_graph()` | function | New | Returns the `salg:` SHACL shapes *(needs `pyshacl`)* |
| `validate_query()` | function | New | Takes a `salg:` data graph and validates it against the shapes above, returning `(conforms, report_graph, report_text)` *(needs `pyshacl`)* |
| `find_unbound_projected_variables()` | function | New | Takes a `salg:` data graph and returns every unbound-projected-variable issue found — a `Project`'s `PV` naming a variable never bound in its own pattern |
| `UnboundProjectedVariable` | class | New | One issue found by the check above — has `project_node`, `variable`, `projected_vars` fields |
| `SALG` | value | New | The `salg:` namespace |

### SPARQL-Rules Language ("SRL")

SRL is a Datalog-style rules language over RDF graphs using SPARQL triple patterns and filter expressions.

SRL is importable as `from starlayer.sparql import srl`.

#### Parsing rule sets

Parsing/serializing a rule set as its own `RuleSet` object. Returns a `srl_ast.RuleSet` — see its own table below for fields.

| Name | Kind | Status | Description |
|---|---|---|---|
| `parse_ruleset()` | function | New | Takes SRL text and returns an executable `RuleSet` |
| `ruleset_to_text()` | function | New | Takes a `RuleSet` and returns SRL text |
| `SRLParseError` | class | New | Raised for malformed SRL text |

#### Rule set as syntax tree graph

An SRL document can be encoded as its own RDF syntax tree graph using the `srl:` namespace.

| Name | Kind | Status | Description |
|---|---|---|---|
| `srl_parse_to_tree()` | function | New | Takes SRL text and returns an `srl:`-encoded syntax tree graph, `(graph, root)` |
| `srl_tree_to_text()` | function | New | Takes an `srl:` syntax tree graph and returns SRL text |
| `ruleset_to_tree()` | function | New | Takes a `RuleSet` and returns an `srl:`-encoded syntax tree graph, `(graph, root)` |
| `tree_to_ruleset()` | function | New | Takes an `srl:` syntax tree and returns an executable `RuleSet` |
| `srl_validate()` | function | New | Takes a `srl:` graph and validates it against `srl_shapes.ttl`, returning `(conforms, report_graph, report_text)` |
| `SRLDecodeError` | class | New | Raised for an `srl:` graph shape that doesn't decode |
| `SRL` | value | New | The `srl:` namespace |

#### Well-formedness checks

Available via `from starlayer.sparql import srl_semantic_checks`. Cross-referential checks a SHACL shape can't express (an unbound head/filter/assignment variable, `SET(...)` reusing an already-bound variable) — same reasoning as `semantic_checks.find_unbound_projected_variables` for `salg:`. Works on a `RuleSet` directly, not RDF.

| Name | Kind | Status | Description |
|---|---|---|---|
| `srl_semantic_checks.check_ruleset()` | function | New | Takes a `RuleSet` and returns every §4.2 well-formedness issue found across every rule in it |
| `srl_semantic_checks.check_rule()` | function | New | Takes one rule and returns every §4.2 well-formedness issue found for it |
| `srl_semantic_checks.SRLWellFormednessIssue` | class | New | One §4.2 violation — has `rule`, `kind`, `variable`, `context` fields |

#### Rule execution

Available via `from starlayer.sparql import srl_eval`. Running an already-valid `RuleSet` against a base graph — a separate concern from the tree pipeline above (no RDF involved at all; takes the `RuleSet` object directly), and the one place an extra input (the base graph being reasoned over) is unavoidable.

| Name | Kind | Status | Description |
|---|---|---|---|
| `srl_eval.srl_infer()` | function | New | Takes a base graph and a ruleset, runs the rule set to a fixpoint, and returns the inferred-triples-only graph |
| `srl_eval.srl_query()` | function | New | Takes a base graph, a ruleset, and a goal pattern — runs `srl_infer` then returns every match of the goal pattern against base ∪ inferred |
| `srl_eval.evaluate_ruleset()` | function | New | §6.5's full rule-set evaluation algorithm (`srl_infer`'s own implementation) |
| `srl_eval.build_dependency_graph()` | function | New | Takes a ruleset and returns its §4.3.2 rule dependency graph (open/closed edges) |
| `srl_eval.stratify()` | function | New | Takes a ruleset and returns its §4.4.2 stratification into `(once, general)` layers |
| `srl_eval.is_run_once()` | function | New | Takes a rule and returns whether it has an assignment element or a blank node in its head |
| `srl_eval.eval_rule()` | function | New | §6.4 — evaluates one rule |
| `srl_eval.eval_rule_elements()` | function | New | §6.4 — evaluates a body-element sequence against a solution sequence |
| `srl_eval.StratificationError` | class | New | Raised when §4.4.1's condition is violated — no well-defined evaluation outcome |
| `srl_eval.SRLImportsNotSupportedError` | class | New | Raised when a rule set has `IMPORTS`, which this implementation rejects (§4.5) |
| `srl_eval.SRLEvalError` | class | New | Base class for the two errors above |
| `srl_eval.DependencyEdge` | class | New | One dependency-graph edge — has `source`, `target`, `label` (`"open"`/`"closed"`) fields |

### `srl_ast` — the AST dataclasses (no methods; fields only)

`from starlayer.sparql import srl_ast`, then `srl_ast.RuleSet`/etc — the `RuleSet` named as a return type throughout the tables above is this one.

| Name | Fields | Description |
|---|---|---|
| `srl_ast.RuleSet` | `rules`, `data`, `imports` | §4.1 "Rule set" |
| `srl_ast.Rule` | `head`, `body`, `data`, `id` | §4.1 "Rule" |
| `srl_ast.Data` | `triples` | §4.1 "Data block" — ground triples only |
| `srl_ast.TriplePattern` (aka `TripleTemplate`) | `subject`, `predicate`, `object` | Same shape used for both rule heads and bodies |
| `srl_ast.FilterElement` | `expr` | `FILTER(...)` — `expr` is a real rdflib `Expr` tree |
| `srl_ast.AssignmentElement` | `var`, `expr` | `SET (?var := expr)` |
| `srl_ast.NegationElement` | `inner`, `data` | `NOT DATA? { ... }` |

### Lower-level (used internally, or when finer control is needed)

| Name | Kind | Description |
|---|---|---|
| `starlayer.sparql.grammar12` | module | RDF 1.2/`TRIPLE()` pyparsing extension spliced into rdflib's grammar (`install()`) |
| `starlayer.sparql.parse12.parse_query_12()` / `parse_update_12()` | function | Same as `prepare_query_12()`/`prepare_update_12()` above, but skips the `prepare_*` translate step |
| `starlayer.sparql.lower_rdf11.rdf11_to_query()` / `rdf11_to_update()` | function | Takes 1.2 algebra and returns runnable 1.1 algebra, no text involved |
| `starlayer.sparql.serialize12` | module | SELECT/CONSTRUCT text serialization internals |
| `starlayer.sparql.triple_term.TripleTermNode` / `InvalidTripleTermError` | class | The algebra-tree triple-term node and its validation error |
| `starlayer.sparql.ssyn_to_text.render_expr_text()` | function | Takes one expression tree and returns its text form — shared by SRL and `ssyn:` rendering |
| `starlayer.sparql.to_ssyn_rdf` / `starlayer.sparql.ssyn_to_text` | module | The syntax-level (`ssyn:`) query projection (encode/decode/render) |
| `starlayer.sparql.to_ast_rdf` / `starlayer.sparql.from_ast_rdf` | module | The raw-parse-tree (`sast:`) query projection |

---

## `starlayer.shacl`

### Top-level (`from starlayer.shacl import ...`)

| Name | Kind | Status | Description |
|---|---|---|---|
| `StarLayerShacl` | class | New | Main entry point — see its own table below |
| `validate()` | function | New | Module-level convenience wrapping `StarLayerShacl().validate(...)` |
| `close_shape()` | function | New | Takes a shapes graph and a shape, and returns a closed copy of the shapes graph (`sh:closed true` + `sh:ignoredProperties`, recursively) |
| `TripleTermAdapter` | class | New | Encodes/decodes triple terms so pySHACL can process RDF-1.1-compatible graphs |
| `TripleTermGraph` | class | New | A simple graph-like container that can hold triple-term objects directly |
| `TripleTermValue` | class | New | `(subject, predicate, object)` value type for the adapter layer |
| `ComponentRequest` | class | New | `(component, focus_node, value_nodes, options)` — one native-component evaluation request |
| `ComponentEvaluationResult` | class | New | `(conforms, violations)` — one native-component evaluation result |
| `STSH` | value | New | The starlayer.shacl-native-extensions namespace |
| `target_nodes()` | function | New | Takes a data graph, shapes graph, and shape node, and returns the shape's own target nodes in the data graph |
| `evaluate_component()` | function | New | Takes a `ComponentRequest` and returns the result of evaluating that one native `ConstraintComponent` against it |
| `build_report()` | function | New | Takes component results and returns a `sh:ValidationReport` graph built from them |
| `normalize_to_starlayer_graph()` | function | New | Takes any graph-like input and returns it normalized to a `StarLayerGraph` |
| `normalize_graph_inputs()` | function | New | Takes a data/shapes/ontology graph in any of the shapes callers may pass, and returns them normalized |
| `ExecutionDiagnostics` | class | New | Counters for one validation run (encode/decode calls, triple-term counts, ...) |
| `ValidationResult` | class | New | `conforms`, `report_graph`, `report_text`, `data_graph`, `diagnostics` |
| `RulesResult` | class | New | Result of `apply_rules()` — `data_graph`, `report_graph`, `report_text`, `conforms`, `diagnostics` |
| `EvaluationResult` | class | New | Result of `evaluate()` — SHACL 1.2 Node Expressions |
| `SubgraphExtractionResult` | class | New | Result of `extract_subgraph()` |
| `ValidationProfile` | class | New | `(name, options)` — a SHACL 1.2 Profiling profile |
| `available_profiles()` | function | New | Returns the list of built-in validation profiles |
| `get_profile()` | function | New | Takes a profile name and returns the matching `ValidationProfile` |
| `resolve_profile_options()` | function | New | Takes a profile and caller overrides, and returns the resolved options |
| `declared_conformance_profile()` | function | New | Returns a fresh copy of starlayer.shacl's bundled self-declared SHACL 1.2 conformance graph |
| `derive_conforms_to()` | function | New | Takes a validation report and returns the `sh:conformsTo` triples derived from it |
| `StarLayerGraphProtocol` | class | New | Structural protocol every graph-like input must satisfy |
| `MutableStarLayerGraphProtocol` | class | New | `StarLayerGraphProtocol` plus mutation methods |

### `StarLayerShacl` — own methods (no base class — wraps pyshacl by composition, not inheritance)

Construct with `StarLayerShacl(adapter=None, validate_fn=None)` — both optional; `adapter` defaults to a new `TripleTermAdapter()`.

Verified live: `StarLayerShacl.validate()`'s own source does call through to `pyshacl.validate(...)`, confirming the delegation the next table describes. None of these methods are documented as returning `self` (there's no base class to chain through), so the "silently returns the wrong thing" bug class found repeatedly on `StarLayerGraph`/`StarLayerDataset` doesn't apply here.

| Name | Kind | Description |
|---|---|---|
| `validate()` | method | Takes a data graph (and optional shapes/ontology graphs) and returns a `ValidationResult` — SHACL validation |
| `apply_rules()` | method | Takes a data graph and shapes graph and returns a `RulesResult` — SHACL-AF rule execution (`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`) |
| `evaluate()` | method | Takes a data graph and shapes graph and returns an `EvaluationResult` — SHACL 1.2 Node Expressions, a third, independent processing mode |
| `extract_subgraph()` | method | Takes a data graph, shapes graph, and shape, and returns a `SubgraphExtractionResult` — SHACL-driven subgraph extraction, a fourth, independent processing mode |
| `evaluate_component()` | method | Lower-level: takes a component/focus node/value nodes and evaluates one native `ConstraintComponent` directly |
| `build_report()` | method | Lower-level: takes component events and builds a `sh:ValidationReport` graph directly |
| `target_nodes()` | method | Lower-level: takes a data graph, shapes graph, and shape node, and resolves the shape's target nodes directly |

### Underlying `pyshacl` surface `StarLayerShacl` wraps

*No inheritance relationship exists (`StarLayerShacl` is `object`-derived), so there's no "modified pyshacl method" table the way there is for rdflib — this project calls these as a library, by composition.*

| Name | Kind | Description |
|---|---|---|
| `pyshacl.validate()` | function | The plain-pySHACL function `StarLayerShacl.validate()` wraps, adding RDF 1.2/triple-term adaptation around it |
| `pyshacl.rules.shacl_rule.SHACLRule` | class | The rule-execution machinery `apply_rules()` drives |
| `pyshacl.constraints.constraint_component.ConstraintComponent` | class | The base class starlayer.shacl's own native constraint components (e.g. `srl`/`salg`-specific ones) subclass |

---

## `starlayer.starontology`

Allows access to ontology and shacl files as `StarLayerGraph` objects. Importable as `from starlayer import starontology`.

| Name | Kind | Status | Description |
|---|---|---|---|
| `get_ontology_list()` | function | New | Returns every registered entry's metadata (`name`, `description`, `type`), sorted by name — see below |
| `get_ontology_graph()` | function | New | Takes a registered name and returns a fresh `StarLayerGraph` of that entry |
| `OntologyInfo` | class | New | One registry entry: `name`, `description`, `type` (`"shacl"` / `"ast-graph"` / `"owl"`) |

Registered names (via `get_ontology_list()`):

CLAUDE: rather than ast-graph can we call these tree-graph

| Name | Type | Description |
|---|---|---|
| `manchester_owl` | ast-graph | Ontology for Manchester Syntax internal AST (`manch:`) |
| `manchester_shacl` | shacl | SHACL shapes validating a `manch:` graph |
| `skos_owl` | **owl** | W3C SKOS Reference's formal axioms for the `skos:` namespace |
| `skos_shacl` | shacl | SHACL shapes validating a `skos:` graph |
| `sparql_owl` | ast-graph | Ontology for SPARQL 1.2 query/update's internal AST (`salg:`) |
| `sparql_shacl` | shacl | SHACL shapes validating a `salg:` graph |
| `srl_owl` | ast-graph | Ontology for SPARQL-RL internal AST (`srl:`) |
| `srl_shacl` | shacl | SHACL shapes validating an `srl:` graph |
| `shacl_meta` | shacl | The SHACL 1.2 meta-shapes as SHACL shapes |

### `starlayer.starontology.manchester`

Managing an OWL 2 Manchester Syntax document as its own rdf syntax tree using the starlayer specific `manch:` namespace. Used to edit a Manchester document independent of the OWL semantics it compiles to.

| Name | Kind | Status | Description |
|---|---|---|---|
| `manchester_parse_to_tree()` | function | New | Takes Manchester text and returns a `manch:`-encoded syntax tree (a `Graph`) |
| `manchester_tree_to_text()` | function | New | Takes a `manch:` syntax tree and returns Manchester text |
| `manchester_tree_to_owl()` | function | New | Takes a `manch:` syntax tree and returns the compiled OWL graph (a `StarLayerGraph`) |
| `manchester_validate()` | function | New | Takes a `manch:` graph and validates it against `manchester_shapes.ttl`, returning `(conforms, report_graph, report_text)` |

Obtain the `manch:` ontology and shapes graphs from the registry using `starontology.get_ontology_graph("manchester_owl")` and `starontology.get_ontology_graph("manchester_shacl")` (`starontology` here meaning `starlayer.starontology`, per the section above).

### `starlayer.starontology.skos`

Validating a SKOS thesaurus against the W3C SKOS Reference's own formal axioms and numbered integrity conditions.

| Name | Kind | Status | Description |
|---|---|---|---|
| `skos_validate()` | function | New | Takes a `skos:` graph and validates it against `skos_shapes.ttl`, returning `(conforms, report_graph, report_text)` |

Obtain the `skos:` ontology and shapes graphs from the registry using `starontology.get_ontology_graph("skos_owl")` and `starontology.get_ontology_graph("skos_shacl")`.