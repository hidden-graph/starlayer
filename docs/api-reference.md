# StarLayer API Reference

*An organized index of names available in StarLayer.*


**Status**
- **New** StarLayer-only, no such name on the base class.
- **Modified** StarLayer overrides/extends the base class's own method of the same name.
- **Unchanged** inherited as-is from base class.

**Scope** — this document is curated for *external* use: a name appears here only if a developer using StarLayer as a dependency would plausibly call it directly. "Public" in the Python sense (no leading underscore) is necessary but not sufficient — several of StarLayer's own subpackages (`starlayer.graph`, `starlayer.shacl`) call into lower-level pieces of `starlayer.sparql` as part of their own internals; that cross-subpackage use doesn't by itself earn a name a place in this document. Each "Lower-level" section exists for the opposite case: a name that *is* genuinely useful to an external caller doing advanced/manual work, just not the common path — not a dumping ground for internal plumbing. A name used only by sibling modules within the same subpackage, or only by its own test file, isn't documented here at all, regardless of its underscore.

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
| `StarLayerShaclProcessor` | class | New | Also available from `starlayer.shacl` below |


---

## `starlayer.graph`

Wraps `rdflib` 7.6 (pinned `>=7.0`), by inheritance — `StarLayerGraph`/`StarLayerDataset` subclass `rdflib.Graph`/`Dataset` directly, so most of their own surface is either an override (**Modified**) or an untouched inherited method documented here for discoverability (**Unchanged**). RDFC-1.0 canonicalization (`starlayer.graph.rdfc`) is a from-scratch implementation of the W3C algorithm, not a wrapped/unmodified import of anything rdflib provides — not yet in this document; a separate content gap from the wrapping declaration above.

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

Construct with `StarLayerGraph()`. 

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

Construct with `StarLayerDataset()` 

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
- `object` can be any RDF term, including another `TripleTerm`. 


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

`from starlayer.sparql import ...`

Functions available from `starlayer.sparql`

| Name | Kind | Status | Description |
|---|---|---|---|
| `prepare_query_12()` | function | New | Takes SPARQL 1.2 query text and returns an executable `Query` |
| `prepare_update_12()` | function | New | Takes SPARQL 1.2 Update text and returns an executable `Update` |

### `SPARQL Query Engine`

SPARQL Query Engine (`sqe`) produces a human-readable, editable SPARQL query tree as an RDF graph.

`from starlayer.sparql import sqe`.

| Name | Kind | Status | Description |
|---|---|---|---|
| `sqe_parse_to_tree()` | function | New | Takes SPARQL query text and returns a `sqe:` encoded syntax tree (a `Graph`) |
| `sqe_tree_to_query()` | function | New | Takes a `sqe:` syntax tree and root element and returns an executable `Query` |
| `sqe_tree_to_text()` | function | New | Takes a `sqe:` syntax tree and root element and returns SPARQL text |
| `sqe_validate()` | function | New | Takes a `sqe:` syntax tree and validates it against the `sqe_shacl` shapes, returning a SHACL validation report |
| `SQE` | value | New | The `sqe:` namespace |



### SPARQL-Rules Language ("SRL")

SRL is a Datalog-style rules language over RDF graphs using SPARQL triple patterns and filter expressions.

`from starlayer.sparql import srl`.

#### Managing rule sets

Everything importable from `srl` for parsing, serializing, and running a rule set. `RuleSet.infer()`/`.query()` are the only way to run one — there's no separate `infer(ruleset, graph)`-style free function; everything SRL's own evaluation engine (`srl_eval.py`) does is private plumbing underneath these two methods.

| Name | Kind | Status | Description |
|---|---|---|---|
| `parse_ruleset()` | function | New | Takes SRL text and returns an executable `RuleSet` — also enforces §4.2 well-formedness (no unbound head/filter/assignment variable, no `SET(...)` reusing an already-bound variable), raising `SRLParseError` if violated, the same one-gate contract plain SPARQL's own `prepareQuery()` has. A `RuleSet` you get your hands on is always both syntactically valid and well-formed — there's no separate "validate an already-parsed ruleset" step |
| `ruleset_to_text()` | function | New | Takes a `RuleSet` and returns SRL text — the inverse of `parse_ruleset()` |
| `RuleSet` | class | New | A parsed rule set, returned by `parse_ruleset()` |
| `RuleSet.infer(base_graph)` | method | New | Runs the rule set against `base_graph` to a fixpoint (§4.1's `Infer`), returning the inferred-triples-only graph — never includes anything already in `base_graph` |
| `RuleSet.query(base_graph, goal_pattern)` | method | New | Runs `infer()` then returns every match of `goal_pattern` against `base_graph` ∪ inferred (§4.1's `Query`), one `dict[Variable, term]` solution per match |
| `TriplePattern` | class | New | A triple pattern/template — `subject`/`predicate`/`object`. Needed directly because it's `RuleSet.query()`'s own `goal_pattern` parameter type. Distinct from an RDF 1.2 *triple term* (`triple_term.TripleTermNode`, an atomic value that can fill a subject/object slot) — a `TriplePattern` is the 3-slot structure itself, never a term, though one of its slots can hold a triple term |

Everything else a rule set is built from (`Rule`, `Data`, `FilterElement`, `AssignmentElement`, `NegationElement`) is private — no public function or method takes or returns one; they only ever appear by walking `RuleSet.rules`/`Rule.head`/`Rule.body`, which is an inspection/editing concern this API doesn't cover yet.

#### Rule set as syntax tree graph

An SRL document can be encoded as its own RDF syntax tree graph using the starlayer-specific `srl:` namespace.

| Name | Kind | Status | Description |
|---|---|---|---|
| `srl_parse_to_tree()` | function | New | Takes SRL text and returns an `srl:`-encoded syntax tree graph. Composes `parse_ruleset()` + `ruleset_to_tree()` |
| `srl_tree_to_text()` | function | New | Takes an `srl:` syntax tree graph and returns SRL text. Composes `tree_to_ruleset()` + `ruleset_to_text()` |
| `ruleset_to_tree()` | function | New | Takes an executable `RuleSet` and returns an `srl:`-encoded syntax tree graph |
| `tree_to_ruleset()` | function | New | Takes an `srl:` syntax tree and returns an executable `RuleSet` |
| `srl_validate()` | function | New | Takes a `srl:` graph and validates it against `srl_shapes.ttl`, returning a SHACL validation report |
| `SRL` | value | New | The `srl:` namespace |

---

## `starlayer.shacl`

Wraps `pyshacl` 0.40.1 (pinned `>=0.40.1`), by composition rather than inheritance — `StarLayerShaclProcessor` calls into pyshacl's own functions rather than subclassing anything, so **Modified** below means "pyshacl exposes this same name," not "an overridden inherited method," and there's no **Unchanged** category at all. Covers SHACL 1.2's six specification documents: Core Validation, SPARQL Extensions, Node Expressions, Inference Rules, User Interfaces, and Profiling.

Classes, functions and values available from `starlayer.shacl`

`from starlayer.shacl import ...`

| Name | Kind | Status | Description |
|---|---|---|---|
| `StarLayerShaclProcessor` | class | New | Main entry point — see its own table below |
| `validate()` | function | **Modified** | Module-level convenience wrapping `StarLayerShaclProcessor().validate(...)` |
| `validate_each()` | function | **Modified** | Module-level convenience wrapping `StarLayerShaclProcessor().validate_each(...)` |
| `close_shape()` | function | New | Takes a shapes graph and a shape, and returns a closed copy of the shapes graph (`sh:closed true` + `sh:ignoredProperties`, recursively) |
| `ValidationResult` | class | New | `conforms`, `report_graph`, `report_text`, `data_graph`, `diagnostics` |
| `ExecutionDiagnostics` | class | New | Counters for one validation run (encode/decode calls, triple-term counts, ...) — reflects only the most recent call, not cumulative across several |

### `StarLayerShaclProcessor`

Construct with `StarLayerShaclProcessor(adapter=None, validate_fn=None)` — both optional; `adapter` defaults to a new `TripleTermAdapter()`. Its methods don't return `self`, so calls can't be chained.

| Name | Kind | Status | Description |
|---|---|---|---|
| `adapter` | attribute | New | The `TripleTermAdapter` this instance encodes/decodes triple terms with — set at construction, read afterward for `.diagnostics_snapshot()`/`.export_registry()` |
| `validate()` | method | **Modified** | Takes a data graph (and optional shapes/ontology graphs) and returns a `ValidationResult`, in place of pyshacl's own bare `(conforms, report_graph, report_text)` tuple |
| `validate_each()` | method | **Modified** | Validates each of several data graphs against one shared shapes/ontology graph, returning `dict[int, ValidationResult]` |
| `apply_rules()` | method | **Modified** | Takes a data graph and shapes graph and returns a `RulesResult` — rule execution (`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, plus SHACL 1.2's own `sh:RuleSet`/`sh:sourceRule` provenance) |
| `evaluate()` | method | New | Takes a data graph and shapes graph and returns an `EvaluationResult` — SHACL 1.2 Node Expressions |
| `extract_subgraph()` | method | New | Takes a data graph, shapes graph, shape, and focus node, and returns a `SubgraphExtractionResult` — the subgraph of real, stored triples that shape's constraints covered for that node |
| `target_nodes()` | method | New | Takes a data graph, shapes graph, and shape node, and returns the shape's own target nodes in the data graph |
| `evaluate_component()` | method | New | Takes a component/focus node/value nodes and evaluates one native `ConstraintComponent` directly |
| `build_report()` | method | New | Takes component results and builds a `sh:ValidationReport` graph from them |

### SHACL 1.2 Inference Rules

`from starlayer.shacl import shacl_inference`

Run via `StarLayerShaclProcessor.apply_rules()` — see its own table above.

| Name | Kind | Status | Description |
|---|---|---|---|
| `shacl_inference.RulesResult` | class | New | `data_graph`, `report_graph`, `report_text`, `conforms`, `diagnostics` |

### SHACL 1.2 Node Expressions

`from starlayer.shacl import shacl_node_expr`. Run via `StarLayerShaclProcessor.evaluate()` — see its own table above.

| Name | Kind | Status | Description |
|---|---|---|---|
| `shacl_node_expr.eval_expr()` | function | New | Evaluates one node expression directly against a single focus node, independent of `evaluate()`'s own per-shape orchestration |
| `shacl_node_expr.EvaluationResult` | class | New | Result of `evaluate()` |

### Subgraph extraction (not part of any SHACL 1.2 document — this project's own addition)

`from starlayer.shacl import subgraph_extraction`. Run via `StarLayerShaclProcessor.extract_subgraph()` — see its own table above.

| Name | Kind | Status | Description |
|---|---|---|---|
| `subgraph_extraction.extract_subgraph()` | function | New | Same operation as a free function |
| `subgraph_extraction.SubgraphExtractionResult` | class | New | Result of `extract_subgraph()` |

### SHACL 1.2 Profiling

`from starlayer.shacl import shacl_profiling`

| Name | Kind | Status | Description |
|---|---|---|---|
| `shacl_profiling.ValidationProfile` | class | New | `(name, options)` — a SHACL 1.2 Profiling profile |
| `shacl_profiling.available_profiles()` | function | New | Returns the list of built-in validation profiles |
| `shacl_profiling.get_profile()` | function | New | Takes a profile name and returns the matching `ValidationProfile` |
| `shacl_profiling.resolve_profile_options()` | function | New | Takes a profile and caller overrides, and returns the resolved options |
| `shacl_profiling.declared_conformance_profile()` | function | New | Returns a fresh copy of starlayer.shacl's bundled self-declared SHACL 1.2 conformance graph |
| `shacl_profiling.derive_conforms_to()` | function | New | Takes a validation report and returns the `sh:conformsTo` triples derived from it |

### RDF 1.2 / triple-term adaptation (cross-cutting — every section above runs through this)

| Name | Kind | Status | Description |
|---|---|---|---|
| `TripleTermAdapter` | class | New | Encodes/decodes triple terms so pySHACL can process RDF-1.1-compatible graphs |
| `TripleTermGraph` | class | New | A simple graph-like container that can hold triple-term objects directly |
| `TripleTermValue` | class | New | `(subject, predicate, object)` value type for the adapter layer |
| `normalize_to_starlayer_graph()` | function | New | Takes any graph-like input and returns it normalized to a `StarLayerGraph` |
| `normalize_graph_inputs()` | function | New | Takes a data/shapes/ontology graph in any of the shapes callers may pass, and returns them normalized |
| `StarLayerGraphProtocol` | class | New | Structural protocol every graph-like input must satisfy |
| `MutableStarLayerGraphProtocol` | class | New | `StarLayerGraphProtocol` plus mutation methods |

### Native component evaluation engine (lower-level — most callers want `validate()`, not this)

`from starlayer.shacl import engine`. The machinery `validate()` uses internally to run new SHACL 1.2 predicates as real pySHACL `ConstraintComponent`s. `target_nodes()`/`evaluate_component()`/`build_report()` are the same operations as `StarLayerShaclProcessor`'s own methods of the same names (see its table above), callable here as free functions without constructing an instance.

| Name | Kind | Status | Description |
|---|---|---|---|
| `engine.ComponentRequest` | class | New | `(component, focus_node, value_nodes, options)` — one native-component evaluation request |
| `engine.ComponentEvaluationResult` | class | New | `(conforms, violations)` — one native-component evaluation result |
| `engine.STSH` | value | New | The starlayer.shacl-native-extensions namespace |
| `engine.target_nodes()` | function | New | Free-function form of `target_nodes()` above |
| `engine.evaluate_component()` | function | New | Free-function form of `evaluate_component()` above |
| `engine.build_report()` | function | New | Free-function form of `build_report()` above |

---

## `starlayer.starontology`

Allows access to owl ontology and shacl files as `StarLayerGraph` objects. 

`from starlayer import starontology`

| Name | Kind | Status | Description |
|---|---|---|---|
| `get_ontology_list()` | function | New | Returns every registered entry's metadata (`name`, `description`, `type`), sorted by name — see below |
| `get_ontology_graph()` | function | New | Takes a registered name and returns a fresh `StarLayerGraph` of that entry |
| `OntologyInfo` | class | New | One registry entry: `name`, `description`, `type` (`"shacl"` / `"ast-graph"` / `"owl"`) |

List of registered names (via `get_ontology_list()`):

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