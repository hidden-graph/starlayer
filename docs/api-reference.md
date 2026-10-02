# StarLayer API Reference

*Companion to [`functionality-overview.md`](functionality-overview.md) — an organized index of the names exposed by StarLayer.*

**Columns**: **Kind** — method / property / attribute / function / class / value. **Status** (classes that extend an underlying library only) — **New** (StarLayer-only, no such name on the base class), **Modified** (StarLayer overrides/extends the base class's own method of the same name), **Unchanged** (inherited as-is).

**Package hierarchy**: `starlayer` is the primary installable package (`pip install starlayer`). `starontology` is installable as a separate package, for users interested in the ontology files (OWL ontologies + SHACL shapes) on their own.

---

## `starlayer`

The full top-level surface of `starlayer`.   Uee (`from starlayer import ...`).  



| Name | Kind | Defined in | Description |
|---|---|---|---|
| `StarLayerGraph` | class | `starlayer.graph` | See the `starlayer.graph` section below |
| `StarLayerDataset` | class | `starlayer.graph` | See the `starlayer.graph` section below |
| `TripleTerm` | class | `starlayer.graph` | See the `starlayer.graph` section below |
| `DirLangString` | class | `starlayer.graph` | See the `starlayer.graph` section below |
| `StarLayerShacl` | class | `starlayer.shacl` | See the `starlayer.shacl` section below |
| `Graph` | class | `starlayer.graph` (rdflib re-export) | Plain `rdflib.Graph` |
| `Dataset` | class | `starlayer.graph` (rdflib re-export) | Plain `rdflib.Dataset` |
| `BNode` / `Literal` / `URIRef` / `Variable` | class | `starlayer.graph` (rdflib re-export) | rdflib's own term types |
| `Namespace` | class | `starlayer.graph` (rdflib re-export) | rdflib's "generate URIRefs with a common prefix" helper |
| `RDF` / `RDFS` / `XSD` | value | `starlayer.graph` (rdflib re-export) | rdflib's own bound namespaces |


---

## `starlayer.graph`

### Top-level (`from starlayer.graph import ...`)

| Name | Kind | Status | Description |
|---|---|---|---|
| `StarLayerGraph` | class | New | `rdflib.Graph` extended with RDF 1.2 triple-term support — see its own table below |
| `StarLayerDataset` | class | New | `rdflib.Dataset` extended with RDF 1.2 triple-term support An RDF dataset where every named-graph context is a `StarLayerGraph` — see its own table below |
| `TripleTerm` | class | New | An RDF 1.2 triple term used as a resource — see its own table below |
| `DirLangString` | class | New | An RDF 1.2 directional language-tagged string literal — see its own table below |
| `Turtle12SyntaxError` | class | New | Malformed Turtle 1.2 input the parser can't recognize as any known production |
| `parseQuery` | function | Modified | Parse a SPARQL 1.2 SELECT/ASK/CONSTRUCT/DESCRIBE query string |
| `prepareQuery` | function | Modified | Parse + translate SPARQL 1.2 query text into a prepared query object, ready to pass to `.query()` |
| `parseUpdate` | function | Modified | Parse a SPARQL 1.2 Update request string |
| `prepareUpdate` | function | Modified | Parse + translate SPARQL 1.2 Update text into a prepared update object, ready to pass to `.update()` |
| `processUpdate` | function | Modified | Execute a SPARQL 1.2 Update against a graph |
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

### `StarLayerGraph` — full member surface

| Name | Kind | Status | Returns | Description |
|---|---|---|---|---|
| `add(triple)` | method | Modified | None | Add a triple — a `TripleTerm` (or plain 3-tuple) in object position is encoded transparently |
| `addN(quads)` | method | Modified | StarLayerGraph | Add multiple quads, encoding all `TripleTerm`s in one `store.addN()` call |
| `add_reification(reifier, triple_term)` | method | New | None | `reifier rdf:reifies triple_term` — make a node an official reifier |
| `add_reifier_annotation(predicate, obj, name=None)` | method | New | IdentifiedNode | Create a reifier node and add one annotation property to it |
| `all_nodes()` | method | Unchanged | Set[Node] | All nodes (subjects, predicates, and objects) in the graph |
| `bind(prefix, namespace, override=True, ...)` | method | Unchanged | None | Bind a prefix to a namespace |
| `cbd(resource, *, target_graph=None, include_reifications=True)` | method | Modified | StarLayerGraph | Concise Bounded Description; defaults `target_graph` to a new `StarLayerGraph` |
| `close(commit_pending_transaction=False)` | method | Modified | None | Close the underlying store, optionally committing pending writes |
| `collection(identifier)` | method | Unchanged | Collection | Create a new `Collection` instance |
| `commit()` | method | Unchanged | self (same graph/dataset) | Commit active transactions |
| `compute_qname(uri, generate=True)` | method | Unchanged | Tuple[str, URIRef, str] | Compute the `(prefix, namespace, localname)` qname tuple for a URI |
| `connected()` | method | Unchanged | bool | Check whether the graph is connected |
| `de_skolemize(new_graph=None, uriref=None)` | method | Modified | StarLayerGraph | Convert skolem IRIs in the graph back to blank nodes; defaults `new_graph` to a new `StarLayerGraph` (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `derive_shape(template_shape=None, *, ignored_properties=None, use_default_ignored_properties=True)` | method | New | Graph | Infer a SHACL shape from the graph's own data (one `sh:NodeShape` per class) |
| `destroy(configuration)` | method | Unchanged | self (same graph/dataset) | Destroy the identified store, if the backend supports it |
| `from_rdflib(source_graph)` | class method | New | StarLayerGraph | Wrap a plain `rdflib.Graph`  as a `StarLayerGraph` |
| `has_triple_term(subject, predicate, object)` | method | New | bool | `True` if a `TripleTerm` with these exact components exists in the graph |
| `identifier` | property | Unchanged | URIRef \| BNode | The graph's own identifier (`URIRef`/`BNode`) |
| `infer(profile='rdfs', *, mode='full', target_graph=None, ...)` | method | New | StarLayerGraph | Materialize an RDF/RDFS/OWL-RL/OWL-DL entailment closure |
| `isomorphic(other)` | method | Modified | bool | RDF-1.2-aware (triple-term-aware) graph isomorphism |
| `items(list)` | method | Unchanged | Generator[Node, None, None] | Generator over items of an `rdf:List` resource |
| `n3(namespace_manager=None)` | method | Unchanged | str | An n3 identifier for the graph |
| `namespace_manager` | property | Unchanged | NamespaceManager | This graph's namespace manager |
| `namespaces()` | method | Unchanged | Generator[Tuple[str, URIRef], None, None] | Generator over `(prefix, namespace)` bindings |
| `objects(subject=None, predicate=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of (optionally unique) objects matching subject/predicate |
| `open(configuration, create=False)` | method | Modified | StarLayerGraph | Open a persistent store and rebuild the `TripleTerm` registry |
| `parse(source=None, publicID=None, format=None, ...)` | method | Modified | StarLayerGraph | Parse RDF data into the graph — all RDF 1.1/1.2 formats this project supports |
| `predicate_objects(subject=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(predicate, object)` tuples |
| `predicates(subject=None, object=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of predicates matching subject/object |
| `print(format='turtle12', out=None)` | method | Modified | None | Print the graph to stdout — defaults to `turtle12` so `TripleTerm`s display correctly |
| `qname(uri)` | method | Unchanged | str | Compute the qname string for a URI |
| `qname_term(node)` | method | New | str | Prefixed n3 form of any term — `URIRef`, `BNode`, `Literal`, `TripleTerm`, `DirLangString` |
| `query(query_object, processor='sparql', result='sparql', ...)` | method | Modified | Result | Execute a SPARQL query. |
| `reifications(s=None, p=None, o=None)` | method | New | Generator[TripleTerm, None, None] | Yield `TripleTerm`s that have at least one reifier and match an s/p/o pattern |
| `reified_triples(reifier)` | method | New | Generator[TripleTerm, None, None] | Yield the `TripleTerm`s reified by a given reifier node |
| `reifier_annotations(TT)` | method | New | Generator[tuple, None, None] | Yield `(reifier, predicate, value)` annotation triples for a `TripleTerm`'s reifiers |
| `reifiers(TT=None, predicate=None, object=None)` | method | New | Generator[IdentifiedNode, None, None] | Yield reifier nodes matching the given filters |
| `remove(triple)` | method | Modified | None | Remove a triple; no-ops immediately if a pattern's `TripleTerm` isn't registered |
| `remove_reification(reifier, triple_term=None)` | method | New | None | Remove the `rdf:reifies` triple(s) for a given reifier |
| `resource(identifier)` | method | Unchanged | Resource | Create a new `Resource` instance |
| `rollback()` | method | Unchanged | self (same graph/dataset) | Roll back active transactions |
| `serialize(destination=None, format='turtle12', ...)` | method | Modified | str \| bytes \| StarLayerGraph | Serialize the graph — all RDF 1.1/1.2 formats this project supports |
| `set(triple)` | method | Unchanged | self (same graph) | Retract every existing `(subject, predicate, *)` triple, then assert exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation |
| `skolemize(new_graph=None, bnode=None, authority=None, ...)` | method | Modified | StarLayerGraph | Convert blank nodes in the graph to skolem IRIs; defaults `new_graph` to a new `StarLayerGraph` (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `store` | property | Unchanged | Store | The underlying rdflib `Store` instance |
| `subject_objects(predicate=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(subject, object)` tuples |
| `subject_predicates(object=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(subject, predicate)` tuples |
| `subjects(predicate=None, object=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of (optionally unique) subjects matching predicate/object |
| `toPython()` | method | Unchanged | self (a Graph is its own Python-value form) | Return `self` (a `Graph` is its own Python-value form) |
| `transitiveClosure(func, arg, seen=None)` | method | Unchanged | Generator[Node, None, None] | Transitive closure of a user-supplied function over the graph |
| `transitive_objects(subject, predicate, remember=None)` | method | Unchanged | Generator[Optional[Node], None, None] | Transitively generate objects along a predicate |
| `transitive_subjects(predicate, object, remember=None)` | method | Unchanged | Generator[Optional[Node], None, None] | Transitively generate subjects along a predicate |
| `triple_terms(subject=None, predicate=None, object=None)` | method | New | Generator[TripleTerm, None, None] | Yield all `TripleTerm`s registered in this graph, with optional filters |
| `triples(triple)` | method | Modified | Generator[tuple, None, None] | Iterate triples matching a pattern;  |
| `triples_choices(triple, context=None)` | method | Modified | Generator[tuple, None, None] | Iterate triples matching a choices pattern; restores `TripleTerm`s |
| `update(update_object, processor='sparql', initNs=None, ...)` | method | Modified | None | Execute a SPARQL Update |
| `value(subject=None, predicate=..., object=None, ...)` | method | Unchanged | Optional[Node] | Get a value for a pair of criteria (subject/predicate, or predicate/object) |

### `StarLayerDataset` — full member surface

| Name | Kind | Status | Returns | Description |
|---|---|---|---|---|
| `add(triple)` | method | Modified | StarLayerDataset | Add a triple to the default graph, `TripleTerm`-aware |
| `addN(quads)` | method | Modified | None | Add multiple quads, each routed to its own target graph's real store |
| `add_graph(g)` | method | Unchanged | StarLayerGraph | Alias of `graph()`, for consistency with rdflib's own naming |
| `all_nodes()` | method | Unchanged | Set[Node] | All nodes in the dataset |
| `bind(prefix, namespace, override=True, ...)` | method | Unchanged | None | Bind a prefix to a namespace |
| `cbd(resource, *, target_graph=None, include_reifications=True)` | method | Modified | StarLayerGraph | Concise Bounded Description of a resource; defaults `target_graph` to a new `StarLayerGraph` (plain rdflib's own default crashes if the result contains a `TripleTerm`) |
| `close(commit_pending_transaction=False)` | method | Modified | None | Close the underlying store, optionally committing pending writes |
| `collection(identifier)` | method | Unchanged | Collection | Create a new `Collection` instance |
| `commit()` | method | Unchanged | self (same graph/dataset) | Commit active transactions |
| `compute_qname(uri, generate=True)` | method | Unchanged | Tuple[str, URIRef, str] | Compute the qname tuple for a URI |
| `connected()` | method | Unchanged | bool | Check whether the graph is connected |
| `context_id(uri, context_id=None)` | method | Unchanged | URIRef | `URI#context` — a context identifier helper |
| `contexts(triple=None)` | method | Modified | Generator[StarLayerGraph, None, None] | Yield a `StarLayerGraph` for every named graph in this dataset |
| `de_skolemize(new_graph=None, uriref=None)` | method | Modified | StarLayerGraph | Convert skolem IRIs back to blank nodes; defaults `new_graph` to a new `StarLayerGraph` (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `default_context` | property | Unchanged | StarLayerGraph | The dataset's default graph context — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.default_context is deprecated, use Dataset.default_graph instead`, confirmed live); use `default_graph` below |
| `default_graph` | property | Unchanged | StarLayerGraph | The dataset's default graph |
| `destroy(configuration)` | method | Unchanged | self (same graph/dataset) | Destroy the identified store, if supported |
| `get_context(identifier, quoted=False, base=None)` | method | Modified | StarLayerGraph | Return the `StarLayerGraph` for the named graph with the given identifier |
| `get_graph(identifier)` | method | Unchanged | Optional[StarLayerGraph] | Return the graph identified by a given identifier — **rdflib's own type hint says `Optional`, but the real implementation never returns `None`: a missing identifier raises `IndexError` instead** (confirmed live — a pre-existing rdflib bug, not a StarLayer one); `get_context()` below never raises either, but for a different reason — it's get-or-create, silently returning a fresh empty graph for a missing identifier rather than distinguishing "exists" from "doesn't" |
| `graph(identifier=None, base=None)` | method | Unchanged | StarLayerGraph | Get-or-create a named graph context |
| `graphs(triple=None)` | method | Unchanged | Generator[StarLayerGraph, None, None] | Generator over all graph contexts |
| `identifier` | property | Unchanged | URIRef \| BNode | The dataset's own identifier — **deprecated by rdflib itself** (emits `DeprecationWarning: Dataset.identifier is deprecated and will be removed in future versions`, confirmed live) |
| `isomorphic(other)` | method | Unchanged | bool | Check isomorphism against another graph |
| `items(list)` | method | Unchanged | Generator[Node, None, None] | Generator over items of an `rdf:List` resource |
| `n3(namespace_manager=None)` | method | Unchanged | str | An n3 identifier for the graph |
| `namespace_manager` | property | Unchanged | NamespaceManager | This dataset's namespace manager |
| `namespaces()` | method | Unchanged | Generator[Tuple[str, URIRef], None, None] | Generator over `(prefix, namespace)` bindings |
| `objects(subject=None, predicate=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of (optionally unique) objects matching subject/predicate |
| `open(configuration, create=False)` | method | Modified | StarLayerDataset | Open a persistent store and rebuild every per-context `TripleTerm` registry |
| `parse(source=None, publicID=None, format=None, ...)` | method | Modified | StarLayerDataset | Parse RDF data into named-graph contexts |
| `predicate_objects(subject=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(predicate, object)` tuples |
| `predicates(subject=None, object=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of predicates matching subject/object |
| `print(format='turtle', encoding='utf-8', out=None)` | method | Unchanged | None | Print the graph to stdout |
| `qname(uri)` | method | Unchanged | str | Compute the qname string for a URI |
| `quads(triple=(None, None, None))` | method | Modified | Generator[tuple, None, None] | Yield `(s, p, o, StarLayerGraph)` with internal encoding triples filtered out |
| `query(query_object, processor='sparql', result='sparql', ...)` | method | Modified | Result | Execute a SPARQL query across all named graphs, with SPARQL-star support |
| `reifications(s=None, p=None, o=None)` | method | New | StarLayerDataset | A `StarLayerDataset` of the `rdf:reifies` triples for every matching `TripleTerm` |
| `reified_triples(reifier)` | method | New | StarLayerDataset | A `StarLayerDataset` of the `rdf:reifies` triples for a given reifier |
| `reifier_annotations(TT)` | method | New | StarLayerDataset | A `StarLayerDataset` of `(reifier, predicate, value)` annotation triples |
| `reifiers(TT=None, predicate=None, object=None)` | method | New | StarLayerDataset | A `StarLayerDataset` of every matching reifier's own triples |
| `remove(triple)` | method | Modified | StarLayerDataset | Remove a triple from the default graph, `TripleTerm`-aware |
| `remove_context(context)` | method | Unchanged | None | Remove the given context from the dataset |
| `remove_graph(g)` | method | Unchanged | self (same dataset) | Remove a named graph |
| `resource(identifier)` | method | Unchanged | Resource | Create a new `Resource` instance |
| `rollback()` | method | Unchanged | self (same graph/dataset) | Roll back active transactions |
| `serialize(destination=None, format='trig', ...)` | method | Modified | str \| None | Serialize this dataset |
| `set(triple)` | method | Unchanged | self (same graph) | Retract every existing `(subject, predicate, *)` triple, then assert exactly one `(subject, predicate, object)` — for "this predicate should have exactly one value," not a true in-place mutation |
| `skolemize(new_graph=None, bnode=None, authority=None, ...)` | method | Modified | StarLayerGraph | Convert blank nodes to skolem IRIs; defaults `new_graph` to a new `StarLayerGraph` (plain rdflib's own default crashes if `self` contains a `TripleTerm`) |
| `store` | property | Unchanged | Store | The underlying rdflib `Store` instance |
| `subject_objects(predicate=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(subject, object)` tuples |
| `subject_predicates(object=None, unique=False)` | method | Unchanged | Generator[Tuple[Node, Node], None, None] | Generator of (optionally unique) `(subject, predicate)` tuples |
| `subjects(predicate=None, object=None, unique=False)` | method | Unchanged | Generator[Node, None, None] | Generator of (optionally unique) subjects matching predicate/object |
| `toPython()` | method | Unchanged | self (a Graph is its own Python-value form) | Return `self` |
| `to_graph()` | method | New | StarLayerGraph | Flatten every quad in this dataset into one new `StarLayerGraph` |
| `transitiveClosure(func, arg, seen=None)` | method | Unchanged | Generator[Node, None, None] | Transitive closure of a user-supplied function |
| `transitive_objects(subject, predicate, remember=None)` | method | Unchanged | Generator[Optional[Node], None, None] | Transitively generate objects along a predicate |
| `transitive_subjects(predicate, object, remember=None)` | method | Unchanged | Generator[Optional[Node], None, None] | Transitively generate subjects along a predicate |
| `triples(triple=(None, None, None))` | method | Modified | Generator[tuple, None, None] | Yield `(s, p, o)`, scoped by `default_union` like rdflib's own `Dataset` |
| `triples_choices(triple, context=None)` | method | Unchanged | Generator[Triple, None, None] | Iterate triples across the entire dataset matching a choices pattern |
| `update(update_object, processor='sparql', initNs=None, ...)` | method | Modified | None | Execute a SPARQL Update across named graphs, with SPARQL-star support |
| `value(subject=None, predicate=..., object=None, ...)` | method | Unchanged | Optional[Node] | Get a value for a pair of criteria |

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

When using the above formats with StarLayerDataset.parse() the default graph of the dataset is populated. When using the formats with StarLayerDataset.serialize, the different graphs are flattened into a single output, discarding graph-name information.

**Dataset formats**

| Format | File extension | Description |
|---|---|---|
| `nquads` / `nq12` | `.nq` | N-Quads — like N-Triples, but a 4th term per line names which graph that triple belongs to |
| `trig` / `trig12` | `.trig` | TriG — like Turtle, but wraps each named graph's triples in a `GRAPH <name> { ... }` block |
| `trix` / `trix12` | `.trix` | TriX — XML syntax; each graph is a `<graph>` element (optionally named by a `<uri>` child) containing `<triple>` elements |

When using the above formats with StarLayerGraph.parse() all named graphs are merged into a single graph, discarding graph-name information. When using the above formats with StarLayerGraph.serialize(), the triples are assigned to a graph named by the graph's own identifier.  

### `TripleTerm`

| Name | Kind | Status | Description |
|---|---|---|---|
| `subject` | attribute | New | The triple term's subject |
| `predicate` | attribute | New | The triple term's predicate |
| `object` | attribute | New | The triple term's object |
| `n3(namespace_manager=None)` | method | New | N3/Turtle-1.2 (`<<( s p o )>>`) text form |

### `DirLangString`

| Name | Kind | Status | Description |
|---|---|---|---|
| `value` | attribute | New | The string's own text value |
| `language` | attribute | New | The BCP47 language tag |
| `direction` | attribute | New | The base direction (`ltr`/`rtl`) |
| `n3(namespace_manager=None)` | method | New | N3/Turtle-1.2 (`"text"@lang--dir`) text form |

### Manchester Syntax

| Name | Description |
|---|---|
| `starlayer.graph.parsers.manchester_parser.parse_manchester(text, base=None)` | Text → plain triples (`owl:Restriction`/`rdf:List` bnodes, `owl:Axiom` reification for annotations) |
| `starlayer.graph.serializers.manchester.serialize_manchester(...)` | Triples → Manchester syntax text |
| `starlayer.ontology.to_ast_rdf.parse_manchester_ast(text, base=None)` | Text → `manch:` RDF directly, `(graph, root)` |
| `starlayer.ontology.to_ast_rdf.rdf_ast_to_manchester_ast(graph, root)` | `manch:` RDF → `Document` AST |
| `starlayer.ontology.to_ast_rdf.manchester_ast_to_text(document)` | `Document` AST → Manchester syntax text |

---

## `starlayer.ontology`

The ontology/SHACL-shapes registry — one catalog spanning everything the whole stack ships (manch:/skos:/salg:/srl:, plus the SHACL 1.2 meta-shapes). Lives at the `starlayer` top level, not nested under `.graph`/`.sparql`/`.shacl`, because it genuinely cuts across all three — not reachable through any one of them alone. Reachable right after a plain `import starlayer` (`starlayer.ontology.list_ontologies()`), same as `starlayer.graph`/`.sparql`/`.shacl` themselves — not in the curated top-level `__all__`, but not hidden either.

| Name | Kind | Description |
|---|---|---|
| `list_ontologies()` | function | Names of every registered ontology/shapes file, sorted |
| `get_ontology(name)` | function | Look up one registered entry (`Ontology`) by name — raises `KeyError` naming the valid choices |
| `Ontology` | class | The registry entry dataclass: `name`, `description`, `namespace`, `kind` (`"owl"`/`"shacl"`), `graph()`, `validate()` |
| `ontology_graph()` | function | The `manch:` RDFS ontology |
| `skos_ontology_graph()` | function | The `skos:` OWL/RDFS ontology |
| `manchester_shapes.shapes_graph()` / `.validate(data_graph)` | function | `manch:` SHACL shapes + validator |
| `skos_shapes.shapes_graph()` / `.validate(data_graph)` | function | `skos:` SHACL shapes + validator |

Registered entry names (via `list_ontologies()`) — the same nine `starontology` registers (see its own table below):

| Name | Kind | Description |
|---|---|---|
| `manchester_owl` | owl | Ontology for Manchester Syntax internal AST (`manch:`) |
| `manchester_shacl` | shacl | SHACL shapes validating a `manch:` AST graph |
| `skos_owl` | owl | W3C SKOS Reference's formal axioms for the `skos:` namespace |
| `skos_shacl` | shacl | SHACL shapes validating SKOS's integrity conditions against a `skos:` data graph |
| `sparql_owl` | owl | A SPARQL 1.2 query/update's own algebra as RDF (`salg:`) |
| `sparql_shacl` | shacl | SHACL shapes validating a `salg:` algebra graph's own structural well-formedness |
| `srl_owl` | owl | SRL/SPARQL-RL's own rule-set abstract syntax as RDF (`srl:`) |
| `srl_shacl` | shacl | SHACL shapes validating an `srl:` rule-set graph's own structural well-formedness |
| `shacl_meta` | shacl | The SHACL 1.2 meta-shapes themselves (`starlayer.shacl`'s own shapes-about-shapes, validating a shapes graph's own well-formedness) — generated Python, not a static `.ttl` file, and has no `shacl_owl` sibling entry (no separate OWL ontology exists for SHACL's own vocabulary) — but *is* also registered in `starontology` (see its own table below), which wraps the same generator |

`Ontology.kind` only distinguishes `"owl"` vs `"shacl"` (two values) — coarser than `starontology.OntologyInfo.type`'s three (`"shacl"`/`"ast-graph"`/`"owl"`), which separates genuine semantic ontologies (`skos_owl`) from syntax-trees-as-RDF (`manchester_owl`/`sparql_owl`/`srl_owl`) that this registry's own `kind` field doesn't. The `sparql_*`/`srl_*` entries' own `.validate()` delegate to `starlayer.sparql.validate_query()`/`starlayer.sparql.srl_shapes.validate_ruleset()` respectively — see the `starlayer.sparql` section below.

---

## `starlayer.sparql`

### Top-level (`from starlayer.sparql import ...`)

| Name | Kind | Status | Description |
|---|---|---|---|
| `prepare_query_12` | function | New | SPARQL 1.2 text → executable `Query` (real triple terms, annotation syntax) |
| `prepare_update_12` | function | New | SPARQL 1.2 Update text → executable `Update` |
| `translate_algebra_12` | function | New | SPARQL 1.2 algebra → SELECT/CONSTRUCT text |
| `query_to_rdf` | function | New | Encode a prepared `Query` as `salg:` RDF, `(graph, root)` |
| `rdf_to_query` | function | New | Decode `salg:` RDF back into a real `Query` |
| `update_to_rdf` | function | New | Encode a prepared `Update` as `salg:` RDF |
| `rdf_to_update` | function | New | Decode `salg:` RDF back into a real `Update` |
| `queries_to_collection` | function | New | Encode a list of independent queries as one `salg:QueryCollection` graph |
| `rdf_to_collection` | function | New | Decode a `salg:QueryCollection` back into a list of `Query` objects |
| `ontology_graph` | function | New | The `salg:` RDFS ontology |
| `shapes_graph` | function | New | The `salg:` SHACL shapes *(needs `pyshacl`)* |
| `validate_query` | function | New | Validate a `salg:` graph against the shapes above *(needs `pyshacl`)* |
| `find_unbound_projected_variables` | function | New | Cross-referential check: a `Project`'s `PV` naming a variable never bound in its own pattern |
| `UnboundProjectedVariable` | class | New | One issue found by the check above — `project_node`, `variable`, `projected_vars` |
| `SALG` | value | New | The `salg:` namespace |

### SRL/SPARQL-RL — *not yet re-exported at the `starlayer.sparql` top level*

| Name | Kind | Description |
|---|---|---|
| `srl_grammar.parse_ruleset(text, base=None)` | function | SRL text → `srl_ast.RuleSet` |
| `srl_grammar.SRLParseError` | class | Raised for malformed SRL text |
| `srl_to_text.ruleset_to_text(ruleset, namespace_manager=None)` | function | `RuleSet` → SRL text, no RDF involved |
| `srl_to_rdf.ruleset_to_rdf(ruleset, graph=None)` | function | `RuleSet` → `srl:` RDF, `(graph, root)` |
| `srl_from_rdf.rdf_to_ruleset(graph, root)` | function | `srl:` RDF → `RuleSet` |
| `srl_from_rdf.SRLDecodeError` | class | Raised for an `srl:` graph shape that doesn't decode |
| `srl_semantic_checks.check_ruleset(ruleset)` | function | §4.2 well-formedness over every rule in a rule set |
| `srl_semantic_checks.check_rule(rule)` | function | §4.2 well-formedness for one rule |
| `srl_semantic_checks.SRLWellFormednessIssue` | class | One violation — `rule`, `kind`, `variable`, `context` |
| `srl_eval.srl_infer(base_graph, ruleset)` | function | Run the rule set to a fixpoint; returns the inferred-triples-only graph |
| `srl_eval.srl_query(base_graph, ruleset, goal_pattern)` | function | `srl_infer` + match a goal pattern against base ∪ inferred |
| `srl_eval.build_dependency_graph(ruleset)` | function | §4.3.2 — the rule dependency graph (open/closed edges) |
| `srl_eval.stratify(ruleset)` | function | §4.4.2 — stratification into `(once, general)` layers |
| `srl_eval.is_run_once(rule)` | function | Does this rule have an assignment element or a blank node in its head? |
| `srl_eval.eval_rule(rule, g, gd)` | function | §6.4 — evaluate one rule |
| `srl_eval.eval_rule_elements(elements, seq, g, gd)` | function | §6.4 — evaluate a body-element sequence against a solution sequence |
| `srl_eval.evaluate_ruleset(base_graph, ruleset)` | function | §6.5 — full rule-set evaluation algorithm (`srl_infer`'s own implementation) |
| `srl_eval.StratificationError` | class | §4.4.1's condition violated — no well-defined evaluation outcome |
| `srl_eval.SRLImportsNotSupportedError` | class | A rule set has `IMPORTS`, which this implementation rejects (§4.5) |
| `srl_eval.SRLEvalError` | class | Base class for the two errors above |
| `srl_eval.DependencyEdge` | class | One dependency-graph edge — `source`, `target`, `label` (`"open"`/`"closed"`) |
| `srl_vocab.SRL` | value | The `srl:` namespace |
| `srl_shapes.shapes_graph()` | function | The `srl:` SHACL shapes *(needs `pyshacl`)* |
| `srl_shapes.validate_ruleset(data_graph)` | function | Validate an `srl:` graph against the shapes above *(needs `pyshacl`)* |

### `srl_ast` — the AST dataclasses (no methods; fields only)

| Name | Fields | Description |
|---|---|---|
| `RuleSet` | `rules`, `data`, `imports` | §4.1 "Rule set" |
| `Rule` | `head`, `body`, `data`, `id` | §4.1 "Rule" |
| `Data` | `triples` | §4.1 "Data block" — ground triples only |
| `TriplePattern` (aka `TripleTemplate`) | `subject`, `predicate`, `object` | Same shape used for both rule heads and bodies |
| `FilterElement` | `expr` | `FILTER(...)` — `expr` is a real rdflib `Expr` tree |
| `AssignmentElement` | `var`, `expr` | `SET (?var := expr)` |
| `NegationElement` | `inner`, `data` | `NOT DATA? { ... }` |

### Lower-level (used internally, or when finer control is needed)

| Name | Description |
|---|---|
| `starlayer.sparql.grammar12` | RDF 1.2/`TRIPLE()` pyparsing extension spliced into rdflib's grammar (`install()`) |
| `starlayer.sparql.parse12.parse_query_12` / `parse_update_12` | Parse without the `prepare_*` translate step |
| `starlayer.sparql.lower_rdf11.rdf11_to_query` / `rdf11_to_update` | 1.2 algebra → runnable 1.1 algebra, no text involved |
| `starlayer.sparql.serialize12` | SELECT/CONSTRUCT text serialization internals |
| `starlayer.sparql.triple_term.TripleTermNode` / `InvalidTripleTermError` | The algebra-tree triple-term node and its validation error |
| `starlayer.sparql.ssyn_to_text.render_expr_text(expr)` | Render one expression tree to text — shared by SRL and `ssyn:` rendering |
| `starlayer.sparql.to_ssyn_rdf` / `starlayer.sparql.ssyn_to_text` | The syntax-level (`ssyn:`) query projection (encode/decode/render) |
| `starlayer.sparql.to_ast_rdf` / `starlayer.sparql.from_ast_rdf` | The raw-parse-tree (`sast:`) query projection |

---

## `starlayer.shacl`

### Top-level (`from starlayer.shacl import ...`)

| Name | Kind | Description |
|---|---|---|
| `StarLayerShacl` | class | Main entry point — see its own table below |
| `validate` | function | Module-level convenience wrapping `StarLayerShacl().validate(...)` |
| `close_shape` | function | Return a closed copy of a shapes graph (`sh:closed true` + `sh:ignoredProperties`, recursively) |
| `TripleTermAdapter` | class | Encode/decode triple terms so pySHACL can process RDF-1.1-compatible graphs |
| `TripleTermGraph` | class | Simple graph-like container that can hold triple-term objects directly |
| `TripleTermValue` | class | `(subject, predicate, object)` value type for the adapter layer |
| `ComponentRequest` | class | `(component, focus_node, value_nodes, options)` — one native-component evaluation request |
| `ComponentEvaluationResult` | class | `(conforms, violations)` — one native-component evaluation result |
| `STSH` | value | The starlayer.shacl-native-extensions namespace |
| `target_nodes` | function | Resolve a shape's target nodes in a data graph |
| `evaluate_component` | function | Evaluate one native `ConstraintComponent` against a request |
| `build_report` | function | Build a `sh:ValidationReport` graph from component results |
| `normalize_to_starlayer_graph` | function | Normalize an input graph to a `StarLayerGraph` |
| `normalize_graph_inputs` | function | Normalize the various graph-input shapes callers may pass |
| `ExecutionDiagnostics` | class | Counters for one validation run (encode/decode calls, triple-term counts, ...) |
| `ValidationResult` | class | `conforms`, `report_graph`, `report_text`, `data_graph`, `diagnostics` |
| `RulesResult` | class | Result of `apply_rules()` — `data_graph`, `report_graph`, `report_text`, `conforms`, `diagnostics` |
| `EvaluationResult` | class | Result of `evaluate()` — SHACL 1.2 Node Expressions |
| `SubgraphExtractionResult` | class | Result of `extract_subgraph()` |
| `ValidationProfile` | class | `(name, options)` — a SHACL 1.2 Profiling profile |
| `available_profiles` | function | List the built-in validation profiles |
| `get_profile` | function | Look up one profile by name |
| `resolve_profile_options` | function | Resolve a profile's options against caller overrides |
| `declared_conformance_profile` | function | A fresh copy of starlayer.shacl's bundled self-declared SHACL 1.2 conformance |
| `derive_conforms_to` | function | Derive `sh:conformsTo` triples from a validation report |
| `StarLayerGraphProtocol` | class | Structural protocol every graph-like input must satisfy |
| `MutableStarLayerGraphProtocol` | class | `StarLayerGraphProtocol` + mutation methods |

### `StarLayerShacl` — own methods (no base class — wraps pyshacl by composition, not inheritance)

| Name | Kind | Description |
|---|---|---|
| `validate(data_graph, shacl_graph=None, ont_graph=None, ...)` | method | SHACL validation |
| `apply_rules(data_graph, shacl_graph, ont_graph=None, ...)` | method | SHACL-AF rule execution (`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`) |
| `evaluate(data_graph, shacl_graph, ont_graph=None)` | method | SHACL 1.2 Node Expressions — a third, independent processing mode |
| `extract_subgraph(data_graph, shacl_graph, shape, ...)` | method | SHACL-driven subgraph extraction — a fourth, independent processing mode |
| `evaluate_component(*, component, focus_node, value_nodes, ...)` | method | Lower-level: evaluate one native `ConstraintComponent` directly |
| `build_report(*, events, graph_context, options=None)` | method | Lower-level: build a `sh:ValidationReport` graph directly |
| `target_nodes(*, data_graph, shacl_graph, shape_node)` | method | Lower-level: resolve a shape's target nodes directly |

### Underlying `pyshacl` surface `StarLayerShacl` wraps

*No inheritance relationship exists (`StarLayerShacl` is `object`-derived), so there's no "modified pyshacl method" table the way there is for rdflib — this project calls these as a library, by composition.*

| Name | Description |
|---|---|
| `pyshacl.validate(...)` | The plain-pySHACL function `StarLayerShacl.validate()` wraps, adding RDF 1.2/triple-term adaptation around it |
| `pyshacl.rules.shacl_rule.SHACLRule` | The rule-execution machinery `apply_rules()` drives |
| `pyshacl.constraints.constraint_component.ConstraintComponent` | The base class starlayer.shacl's own native constraint components (e.g. `srl`/`salg`-specific ones) subclass |

---

## `starontology`

Allows access to ontology and shacl files, both as `StarLayerGraph` objects and as Turtle 1.2 text. Depends on `starlayer.graph` (returns `StarLayerGraph` graphs) and `starlayer.shacl`.

| Name | Kind | Returns | Description |
|---|---|---|---|
| `get_ontology_list()` | function | tuple[OntologyInfo, ...] | Every registered entry's metadata (`name`, `description`, `type`), sorted by name — see below |
| `get_ontology_graph(name)` | function | StarLayerGraph | A fresh `StarLayerGraph` of the named entry — raises `KeyError` naming the valid choices for an unknown name |
| `get_ontology_turtle12(name)` | function | str | The named entry, serialized as Turtle 1.2 text — `get_ontology_graph(name).serialize(format='turtle12')` |
| `OntologyInfo` | class | — | One registry entry: `name`, `description`, `type` (`"shacl"` / `"ast-graph"` / `"owl"`) |

Registered names (via `get_ontology_list()`):

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
