# StarLayerGraph vs rdflib.Graph — Method Coverage Tracker

*Last reviewed: 2026-07-17*

Summary of all public `rdflib.Graph` methods and status in `StarLayerGraph`.

**Status key**

✅ Done — explicitly overridden; TripleTerm coercion/filtering is correct
🔗 Inherited — not overridden; delegates through our `triples()` override and works correctly
⚠️ Partial — works for common cases but has documented caveats
➖ Not relevant — no TripleTerm handling required; plain rdflib behaviour is correct

---

## Core Mutation

TripleTerm as used below can refer to either a plain 3-tuple `(s, p, o)` in object position, or a `TripleTerm` instance created as `TT = TripleTerm(s, p, o)`. A `DirLangString(value, language, direction)` instance (RDF 1.2 base-direction-tagged literal, `"text"@lang--dir`) is accepted anywhere an object may appear, with the same read/write transparency as TripleTerm, but no tuple shorthand and no registry — see [StarLayer Classes](#starlayergraph-classes) below.

✅ `g.add(triple)` — Adds one triple. Allows triple term as an object.

✅ `g.remove(triple)` — Removes a triple. Allows triple term as an object.

🔗 `g.set(triple)` — Replaces all existing objects for the given subject+predicate with the new value. Allows triple term as an object.  

✅ `g.addN(quads)` — Adds multiple `(subject, predicate, object, graph)` quads in one call. Accepts TripleTerms in the object position.

---

## Core Traversal

TripleTerms can appear in the object position of a pattern. All traversal methods can return TripleTerms as first-class values.

✅ `g.triples((s, p, o))` — Yields all triples matching the pattern. Each position is a specific value or `None` (wildcard). Accepts a TripleTerm in the object position; returns TripleTerms as `TripleTerm` objects.

✅ `g.triples_choices((s, p, o))` — Like `g.triples()` but any position can be a list of values instead of a single value. Accepts TripleTerms in any object list entry.

🔗 `for (s, p, o) in g` — Iterates all triples in the graph. Delegates to `g.triples()`, so TripleTerms are returned correctly.

✅ `(s, p, o) in g` — Tests whether a specific triple is in the graph. Accepts a TripleTerm in the object position.

✅ `len(g)` — Returns the number of triples in the graph based on RDF 1.2 representation.

---

## Convenience Traversal

These are all rdflib wrappers over `g.triples()` and work correctly with TripleTerms without any override. Objects may be TripleTerms; TripleTerms are returned as `TripleTerm` objects.

🔗 `g.subjects(predicate, object)` — Yields subjects matching the given predicate and object.

🔗 `g.predicates(subject, object)` — Yields predicates matching the given subject and object.

🔗 `g.objects(subject, predicate)` — Yields objects for the given subject and predicate. May return TripleTerms.

🔗 `g.subject_objects(predicate)` — Yields `(subject, object)` pairs for the given predicate. May return TripleTerms as object.

🔗 `g.subject_predicates(object)` — Yields `(subject, predicate)` pairs for the given object.

🔗 `g.predicate_objects(subject)` — Yields `(predicate, object)` pairs for the given subject. May return TripleTerms as object.

🔗 `g.value(subject, predicate, object)` — Returns a single matching value, or `None`. Raises if multiple matches exist.

🔗 `g.all_nodes()` — Yields every subject and object node in the graph based on RDF 1.2 representation.  

---

## Namespace / Identifier

The following functions have no TripleTerm involvement.

➖ `g.bind(prefix, namespace)` — Registers a prefix/namespace pair.

➖ `g.namespaces()` — Yields all registered `(prefix, namespace)` pairs.

➖ `g.compute_qname(uri)` — Returns `(prefix, namespace, name)` for a URI.

➖ `g.qname(uri)` — Returns a qualified name string for a URI.

➖ `g.absolutize(uri)` — Resolves a relative URI against the graph's base.

➖ `g.n3(namespace_manager)` — Returns an N3-formatted string for the graph.

---

## Serialization / Parsing

All rdflib formats are supported. Eight additional RDF 1.2 formats add TripleTerm support.

✅ `g.parse(...)` — Eight additional RDF 1.2 formats supported: `turtle12`, `nt12`, `nq12`, `trig12`, `trix12`, `rdfxml12`, `jsonld12`, `longturtle12`.

✅ `g.serialize(...)` — All rdflib formats continue to work (e.g. ttl 1.1) but will expose internal encoding of triples. All eight RDF 1.2 formats serialize TripleTerms correctly.

✅ `g.print(...)` — Overridden to default to `turtle12`. Calling `g.print()` with no arguments produces clean RDF 1.2 output.

> **Not all eight are spec-backed.** `turtle12`, `nt12`, `nq12`, `trig12`, `longturtle12`, and `rdfxml12` target real W3C companion documents to RDF 1.2 (Turtle, N-Triples, N-Quads, TriG, XML Syntax — longturtle is a pretty-printed Turtle variant). **`jsonld12` and `trix12` are not** — there is no W3C JSON-LD 1.2 spec, and TriX was never a W3C spec at all (RDF 1.1 or otherwise), just a long-standing HP Labs/Jena convention. `jsonld12` extends non-RDF-1.2 JSON-LD with a starlayergraph-invented `rdf:TripleTerm` node shape and a `dirlang:` datatype URI for `dirLangString`, which round-trips only through starlayergraph's own JSON-LD parser/serializer, not through any external tool. `trix12`, by contrast, was updated 2026-07-16 to match Apache Jena's real (undocumented-but-empirically-confirmed) TriX convention — lowercase `<trix>` root, a nested `<triple>` element for a triple term — so it now round-trips triple terms through live Fuseki's own TriX support too; the old `<TriX>`/`<tripleTerm>` spelling is still accepted on read for backward compatibility. See `docs/rdf12_sparql12_gap_analysis.md` §6 and `docs/future_enhancements.md`'s "Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes" for what would need to change if either format ever does get a real spec target.

---

## SPARQL

SPARQL 1.2 syntax is fully supported. See [sparql12_design.md](sparql12_design.md) for full details.

✅ `g.query(...)` — Accepts SPARQL 1.2 queries including `<<( )>>` triple-term patterns, `{| |}` annotation blocks, `~?r` reifier binding, `TRIPLE(s,p,o)`, `isTripleTerm()`/`isTRIPLE()` (the SPARQL 1.2 spec's own name, accepted as an alias), and the base-direction functions `LANGDIR()`/`hasLANGDIR()`/`STRLANGDIR()` plus a `LANG()`/`hasLANG()` that also recognize a DirLangString. For the default rdf-1.1 backend, queries are rewritten to SPARQL 1.1 internally. For the native rdf-1.2 backend, queries go directly to the endpoint via HTTP. CONSTRUCT can return RDF 1.2 graph.

✅ `g.update(...)` — Accepts SPARQL 1.2 UPDATE with triple-term patterns in WHERE, INSERT, and DELETE clauses. For the default rdf-1.1 backend, triple terms are encoded before writing. For native backends, the update goes directly to the endpoint via HTTP.

---

## Graph Algorithms

All graph algorithms operate on the visible RDF 1.2 graph; encoding triples are filtered automatically.

🔗 `g.connected()` — Uses `subjects()`.

✅ `g.isomorphic(other)` — Overridden (previously just inherited `rdflib.Graph.isomorphic()`'s crude approximation, not `graph_diff` — that was a documentation error). Unfolds each graph's TripleTerms back to native BNode-based `rdf:subject`/`rdf:predicate`/`rdf:object` reification (mirroring the parser's own pre-skolemization intermediate form) before delegating to `rdflib.compare.isomorphic()`, the real canonical-labeling algorithm. A BNode embedded inside a TripleTerm is now treated as relabelable, the same as any other BNode, so two separately-parsed graphs that are the same shape but use different arbitrary BNode labels inside a triple term correctly isomorphize (previously didn't — see `CHANGELOG.md`).

✅ `g.cbd(resource, ...)` — Returns a `StarLayerGraph` containing all triples for the given resource. Raises `TypeError` if a plain `rdflib.Graph` is passed as `target_graph`.

➖ `g.transitiveClosure(func, arg)` — User-supplied function; no direct TripleTerm involvement.

➖ `g.transitive_objects(subject, predicate)` — Walks a chain following objects as subjects. A TripleTerm cannot be a subject.

➖ `g.transitive_subjects(predicate, object)` — Walks the chain in reverse, finding all subjects that eventually lead to the given object. A TripleTerm can be the starting object.  

---

## RDF Collections

🔗 `g.collection(identifier)` — Returns a `Collection` object for navigating an `rdf:first`/`rdf:rest` list. TripleTerms are valid list members and are returned correctly as `TripleTerm` objects.

🔗 `g.items(list)` — Iterates members of an RDF list. TripleTerms in the list are returned as `TripleTerm` objects.

---

## Store Lifecycle

These methods manage the underlying store connection and transactions. They have no TripleTerm involvement and are not overridden.

➖ `g.open(configuration, create)` — Opens the store (e.g. connects to a database).

➖ `g.close(commit_pending_transaction)` — Closes the store connection.

➖ `g.commit()` — Commits the current transaction.

➖ `g.rollback()` — Rolls back the current transaction.

➖ `g.destroy(configuration)` — Destroys the store (e.g. drops the database).

---

## Other rdflib Utilities

➖ `g.skolemize(...)` — Replaces blank nodes with stable URIs. No TripleTerm involvement.

➖ `g.de_skolemize(...)` — Reverses `skolemize()`. No TripleTerm involvement.

➖ `g.resource(identifier)` — Returns an `rdflib.Resource` view for navigating a node's properties. Not applicable to TripleTerms since they cannot be subjects — use `g.reifier_annotations(TT)` and `g.reified_triples()` instead.

➖ `g.toPython()` — No-op on graphs; no TripleTerm involvement.

---

## RDF 1.2 Additions (StarLayer-only)

These methods exist only in `StarLayerGraph` and have no rdflib equivalent.

✅ `g.add_reifier_annotation(predicate, obj, name=None)` — Creates a new annotation using named URIRef as subject if `name` given, BNode otherwise. The node becomes a reifier after `g.add_reification()` is called. Returns the subject node as reifier.

✅ `g.add_reification(reifier, triple_term)` — Adds `reifier rdf:reifies <<( s p o )>>`. Accepts a plain 3-tuple or `TripleTerm` for `triple_term`.

✅ `g.reifiers(TT=None, predicate=None, object=None)` — Yields reifier nodes. `TT` narrows by the TripleTerm being reified; `predicate`/`object` narrow by the reifier's own annotation properties. Any combination works.

✅ `g.reifications(s=None, p=None, o=None)` — Yields TripleTerms that have at least one reifier annotation, optionally filtered by the components `s`, `p`, `o` of the TripleTerm.

✅ `g.reifier_annotations(TT)` — Yields `(reifier, predicate, value)` annotation triples for all reifiers of the given TripleTerm. Excludes the `rdf:reifies` triple itself.

✅ `g.reified_triples(reifier)` — Yields the TripleTerms of the given reifier.  

✅ `g.triple_terms(subject=None, predicate=None, object=None)` — Yields all TripleTerms in the graph; any combination of `subject`, `predicate`, `object` filters the results.

✅ `g.has_triple_term(subject, predicate, object)` — Returns `True` if a TripleTerm with those exact components exists in the graph.

✅ `g.remove_reification(reifier)` — Removes the `rdf:reifies` triple for the given reifier.

✅ `g.from_rdflib(source_graph)` — Class method; imports a plain `rdflib.Graph` into a new `StarLayerGraph`, encoding any existing reification triples and rebuilding the TripleTerm registry.

---

## StarLayer Classes

New classes introduced by StarLayer with no direct rdflib equivalent.

### starlayergraph/model/triple.py

✅ `TripleTerm` — Represents an RDF 1.2 triple term `<<( s p o )>>` as a Python value. Two TripleTerms with the same components are equal regardless of how they were created. Accepts nested TripleTerms. A plain 3-tuple in object position is automatically treated as a TripleTerm. Implements `.n3()` so rdflib can format it as `<<( :bob :knows :carol )>>` wherever a node is expected.

### starlayergraph/model/dirlangstring.py

✅ `DirLangString(value, language, direction)` — Represents an RDF 1.2 base-direction-tagged literal `"text"@lang--dir`. Value-typed like `TripleTerm` (equal/hashable by `(value, language, direction)`; language tag case-folded per RDF 1.2). `direction` must be `'ltr'` or `'rtl'`. Implements `.n3()` (`"text"@lang--dir`). Unlike `TripleTerm`, has no tuple shorthand and needs no registry — `encode_dirlangstring()`/`decode_dirlangstring()` convert to/from the internal `Literal(text, datatype=<dirlang: URI>)` encoding as a pure function of the value itself.

### starlayergraph/graph/starlayergraph_graph.py

✅ `StarLayerGraph` — Subclass of `rdflib.Graph`; the main public API for single-graph RDF 1.2. Stores TripleTerms as content-addressed `tt:HASH` URIRefs internally and hides the encoding from all callers. See method tracker above.

```python
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from rdflib import URIRef, Literal

g = StarLayerGraph()                    # in-memory, default rdf-1.1 backend
g = StarLayerGraph(backend='rdf-1.2')  # native RDF 1.2 endpoint
```

### starlayergraph/graph/starlayergraph_dataset.py

✅ `StarLayerDataset` — Subclass of `rdflib.Dataset`; a multi-graph container where every named graph is a `StarLayerGraph`. Each named graph has its own independent TripleTerm registry — triple terms in graph A are not visible from graph B.

- `ds.get_context(uri)` — returns the named graph as a `StarLayerGraph` with its registry populated.

- `ds.quads((s, p, o))` — yields `(subject, predicate, object, graph)` across all named graphs, filtered by the optional `(s, p, o)` pattern (each position `None` matches anything). Encoding triples are hidden; TripleTerms are returned as `TripleTerm` objects. The fourth element is the `StarLayerGraph` the triple belongs to.

- `ds.contexts()` — yields each named graph as a `StarLayerGraph`.

- `ds.parse(format='trig12')` — loads a TriG 1.2 document, each named graph into its own `StarLayerGraph`.

- `ds.serialize(format='trig12')` — emits a TriG 1.2 document with `GRAPH <uri> { ... }` blocks.


### starlayergraph/parsers/turtle_parser.py

✅ `StarLayerTurtleParser` — Parses Turtle 1.2 text (including `<<( )>>`, `{| |}`, and `~ reifier` syntax) into an rdflib Graph with BNode-based triple-term encoding. Called by `StarLayerGraph.parse(format='turtle12')`.

➖ `_Expander` — Internal helper class used by the parser to resolve prefixes and base URIs during parsing. Not part of the public API.

### starlayergraph/parsers/ntriples12.py

✅ `parse_ntriples12(text)` — Parses N-Triples 1.2 text line-by-line; returns a list of `(s, p, o)` triples where subjects/objects may be `TripleTerm` instances. Handles full IRIs, blank nodes, plain/typed/language-tagged/direction-tagged (`"text"@lang--dir`) literals, and `<<( )>>` triple terms (including nested). Called by `StarLayerGraph.parse(format='nt12')`.

✅ `parse_nquads12(text)` — Parses N-Quads 1.2 text; returns a list of `(s, p, o, g)` quads. Called by `StarLayerGraph.parse(format='nq12')`; the graph component `g` is discarded when merging into a single-graph `StarLayerGraph`.

### starlayergraph/parsers/trig12.py

✅ `parse_trig12(text)` — Parses TriG 1.2 text by splitting the document into prefix declarations and named-graph content blocks, parsing each block as Turtle 1.2 via `StarLayerTurtleParser`, and merging all resulting triples. Called by `StarLayerGraph.parse(format='trig12')`.

### starlayergraph/serializers/ntriples12.py

✅ `serialize_ntriples12(g)` — Serializes a `StarLayerGraph` to N-Triples 1.2 text (one triple per line, full IRIs, `<<( )>>` for triple terms). Called by `StarLayerGraph.serialize(format='nt12')`.

✅ `serialize_nquads12(g, graph_uri=None)` — Serializes to N-Quads 1.2 text (N-Triples + graph name from `g.identifier`). Called by `StarLayerGraph.serialize(format='nq12')`.

### starlayergraph/serializers/trig12.py

✅ `serialize_trig12(g)` — Serializes to TriG 1.2 text. Named-graph identifiers (URIRef) produce a `GRAPH <uri> { ... }` block around Turtle 1.2 content; BNode identifiers produce plain Turtle 1.2 (default-graph convention). Called by `StarLayerGraph.serialize(format='trig12')`.

### starlayergraph/query/sparql12_to_11.py

✅ `rewrite_sparql12_to_11(query)` — Public entry point. Rewrites SPARQL 1.2 syntax to SPARQL 1.1: triple-term patterns `<<( )>>`, the `TRIPLE(s,p,o)` constructor (desugared to `<<( )>>`), annotation subjects `<< >>`, inline annotation blocks `{| |}`, reifier binding `~?r`, `SUBJECT()`/`PREDICATE()`/`OBJECT()` function calls, `isTripleTerm()`/`isTRIPLE()` filter, and the base-direction functions `LANGDIR()`/`hasLANGDIR()`/`STRLANGDIR()` plus a dirLangString-aware `LANG()`/`hasLANG()`. Passes plain queries through unchanged.

➖ `_RewriteState` — Internal counter for generating unique `?__ttN` variable names across a single rewrite pass. Not part of the public API.

---

## StarLayer Internal Functions

Module-level functions that are part of the internal encoding but not public API.

### starlayergraph/model/encoding.py

✅ `tt_hash(s, p, o)` — Produces a 16-hex-char (64-bit) SHA-256 content address for a triple term. Same inputs always produce the same hash, so identical triple terms map to the same internal `tt:HASH` URIRef. Widened from 8 to 16 hex chars 2026-07-17 to keep birthday-bound collision risk negligible for graphs with heavy reification (see `docs/future_enhancements.md`).

---

## Summary

✅ Done — 37 (14 rdflib.Graph methods overridden; 10 RDF 1.2 additions; 13 StarLayer classes/functions)
🔗 Inherited (works) — 13
➖ Not relevant — 20

No known caveats — the `isomorphic()` BNode-in-TripleTerm gap noted here previously is resolved (see the `isomorphic()` row above and `CHANGELOG.md`).
