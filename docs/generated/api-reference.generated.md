# StarLayer API Reference (generated)

Generated directly from `tools/kg/codekg/codekg.trig` - every PublicAccess entity's own full signature and docstring, nothing hand-curated. See [api-overview.generated.md](api-overview.generated.md) for the headline-only index this expands on.

## `starlayer`

[Back to overview](api-overview.generated.md#starlayer)

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset"></a>
### `StarLayerDataset`  _(class)_

An RDF dataset where every named-graph context is a StarLayerGraph.

All RDF 1.2 triple-term handling (encoding, filtering, restoration) is
delegated to per-context StarLayerGraph instances.  The shared store holds
the tt: URIRef encoding triples; each StarLayerGraph's registry maps those
back to TripleTerm objects.

The default graph is an explicit, independent graph (``default_union=False``
per the RDF dataset spec and rdflib 7 default).  Pass
``default_union=True`` to make the default graph a union of all named graphs.

Public API additions vs Dataset:
    parse(format='trig12')      — load TriG 1.2 with triple-term support
    parse(format='nq12')        — load N-Quads 1.2 with triple-term support
    serialize(format='trig12')  — emit TriG 1.2 with triple-term support
    serialize(format='nq12')    — emit N-Quads 1.2 with triple-term support
    serialize(format='turtle12'/'longturtle12'/'nt12'/'rdfxml12')
                                — no multi-graph syntax exists for these,
                                  so every quad is flattened into one
                                  StarLayerGraph first (graph boundaries
                                  are lost)
    to_graph()                  — flatten every quad into one new
                                  StarLayerGraph (graph boundaries lost);
                                  same flattening serialize() uses above,
                                  exposed for querying/hashing/etc.
    get_context(identifier)     — returns StarLayerGraph (not plain Graph)
    contexts()                  — yields StarLayerGraph instances
    quads()                     — yields (s, p, o, StarLayerGraph) with
                                  TripleTerms restored; encoding triples filtered
    reifiers()/reifications()/reifier_annotations()/reified_triples()
                                — dataset-wide reification lookups; each
                                  returns a StarLayerDataset of the
                                  matching triples, still scoped to the
                                  named graph each one came from

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L76-L1226)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-add"></a>
### `StarLayerDataset.add`  _(method)_

```python
def add(self, triple) -> StarLayerDataset
```

Add a triple to the default graph, or a quad ``(s, p, o, graph)`` to the graph it names, with
TripleTerm-aware encoding - see this section's own module-level comment for why this override exists at all.

**Parameters:**

- `triple: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.add](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L423-L432)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-addN"></a>
### `StarLayerDataset.addN`  _(method)_

```python
def addN(self, quads) -> StarLayerDataset
```

Add multiple quads, each routed to its own target graph's real
StarLayerGraph context for TripleTerm-aware encoding - see this
section's own module-level comment.

Grouped by identifier regardless of whether every quad's graph
element is the same object (as rdflib's own ``Graph.__iadd__``
(``+=``) always passes it) or genuinely heterogeneous, matching
``StarLayerGraph.addN``'s own general handling - correct for a
direct multi-graph ``addN`` call too, not just the ``+=`` case.

Returns self, matching rdflib's own ConjunctiveGraph.addN() (and
StarLayerGraph.addN() above).

**Parameters:**

- `quads: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.addN](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L469-L490)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-cbd"></a>
### `StarLayerDataset.cbd`  _(method)_

```python
def cbd(self, resource, *, target_graph=None, include_reifications=True) -> StarLayerGraph
```

Computes the Concise Bounded Description of ``resource`` and
returns it as a ``StarLayerGraph``.

Scoped by ``self.default_union`` the same way ``triples()``/
``subjects()`` are (both are called internally by rdflib's own
``Graph.cbd()`` this delegates to) - see ``triples()``'s own
docstring.

Defaults ``target_graph`` to a new ``StarLayerGraph``, same as
``StarLayerGraph.cbd()`` - the inherited rdflib ``cbd()`` instead
hardcodes a plain ``rdflib.Graph()``, which crashes with
``AssertionError: Object ... must be an rdflib term`` the moment the
CBD'd data contains a real ``TripleTerm``, since ``Graph.add()``
asserts its object is an rdflib ``Node``.

**Parameters:**

- `resource: None` - The resource to compute the Concise Bounded Description for.
- `target_graph: None = None` - The graph to add the CBD's triples to. Must be a StarLayerGraph, since a plain rdflib.Graph cannot store TripleTerms that may appear in the results; defaults to a new one.
- `include_reifications: None = True` - Whether to include each matched triple's reification triples too.

**Returns:** `StarLayerGraph` - target_graph, populated with the CBD.

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.cbd](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L343-L382)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-close"></a>
### `StarLayerDataset.close`  _(method)_

```python
def close(self, commit_pending_transaction: bool=False) -> None
```

Close the underlying store, optionally committing pending writes.

**Parameters:**

- `commit_pending_transaction: bool = False`

**Returns:** `None`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.close](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L184-L186)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-contexts"></a>
### `StarLayerDataset.contexts`  _(method)_

```python
def contexts(self, triple=None) -> Generator[StarLayerGraph, None, None]
```

Yield a StarLayerGraph for every named graph in this dataset.

**Parameters:**

- `triple: None = None`

**Returns:** `Generator[StarLayerGraph, None, None]`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.contexts](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L229-L232)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-de_skolemize"></a>
### `StarLayerDataset.de_skolemize`  _(method)_

```python
def de_skolemize(self, new_graph=None, uriref=None) -> StarLayerGraph
```

Convert skolem IRIs back to blank nodes. Same bug class and same
fix as skolemize() above.

**Parameters:**

- `new_graph: None = None`
- `uriref: None = None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.de_skolemize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L397-L407)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-default_context"></a>
### `StarLayerDataset.default_context`  _(method)_

```python
def default_context(self) -> StarLayerGraph
```

Deprecated alias for default_graph (matches rdflib's own deprecation).

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.default_context](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L150-L158)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-default_graph"></a>
### `StarLayerDataset.default_graph`  _(method)_

```python
def default_graph(self) -> StarLayerGraph
```

The default graph context, re-resolved via get_context() on every
access - never cached as self._default_context directly.

parse() (via _load_context()/_register_sg()) can swap a brand-new
StarLayerGraph instance into _sg_cache without updating any
previously-cached reference to the old one. A cached snapshot would
silently go stale after a parse.

**Returns:** `StarLayerGraph` - The StarLayerGraph for the dataset's default graph.

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.default_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L135-L147)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-get_context"></a>
### `StarLayerDataset.get_context`  _(method)_

```python
def get_context(self, identifier, quoted: bool=False, base=None) -> StarLayerGraph
```

Return the StarLayerGraph for the named graph with the given identifier.

If the graph was populated via parse(), its TripleTerm registry is
already current.  If the context was added through other means, the
registry is rebuilt on first access.

**Parameters:**

- `identifier: None`
- `quoted: bool = False`
- `base: None = None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.get_context](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L209-L227)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-open"></a>
### `StarLayerDataset.open`  _(method)_

```python
def open(self, configuration, create: bool=False) -> StarLayerDataset
```

Open a persistent store and rebuild all per-context TripleTerm registries.
Returns self, not whatever status value rdflib's own Graph.open()
returns (fixed 2026-10-04 - same bug as StarLayerGraph.open()).

The store backend is not a StarLayer dependency — install and configure
it separately, then pass store='StoreName' to the constructor.

Example::

    ds = StarLayerDataset(store='Sleepycat')
    ds.open('/path/to/db', create=True)

**Parameters:**

- `configuration: None`
- `create: bool = False`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.open](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L164-L182)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-parse"></a>
### `StarLayerDataset.parse`  _(method)_

```python
def parse(self, source=None, publicID=None, format=None, location=None, file=None, data=None, **kwargs) -> StarLayerDataset
```

Parse RDF data into named-graph contexts.

format='turtle12' — Turtle 1.2; triples go into the default graph as a StarLayerGraph.
format='trig12'   — TriG 1.2; each GRAPH block becomes a StarLayerGraph.
                    Plain Turtle content (no GRAPH blocks) goes into the default graph.
format='nq12'     — N-Quads 1.2; each distinct graph name becomes a StarLayerGraph.
format='trix12'   — TriX 1.2 XML; each <graph> block becomes a StarLayerGraph.
format='longturtle12'/'nt12'/'rdfxml12'/'manchester' (alias 'omn') —
                    no multi-graph syntax exists for these (same reasoning
                    as turtle12 above, just without a GRAPH-block
                    superset to route through) - triples go straight
                    into the default graph as a StarLayerGraph.
format='n3'/'n3-12'/'text/n3' — aliased straight to 'turtle12', same
                    as on StarLayerGraph; must be valid Turtle/Turtle 1.2.
All other formats delegate to rdflib (no triple-term support).

**Parameters:**

- `source: None = None`
- `publicID: None = None`
- `format: None = None`
- `location: None = None`
- `file: None = None`
- `data: None = None`
- `kwargs: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.parse](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L528-L665)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-quads"></a>
### `StarLayerDataset.quads`  _(method)_

```python
def quads(self, triple=(None, None, None)) -> Generator[tuple, None, None]
```

Yield (s, p, o, StarLayerGraph) with encoding triples filtered out
and tt:HASH URIRefs restored to TripleTerm objects.

**Parameters:**

- `triple: None = (None, None, None)`

**Returns:** `Generator[tuple, None, None]`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.quads](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L263-L284)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-query"></a>
### `StarLayerDataset.query`  _(method)_

```python
def query(self, query_object, processor='sparql', result='sparql', initNs=None, initBindings=None, use_store_provided=True, **kwargs) -> Result
```

Execute a SPARQL query across all named graphs with SPARQL-star support.

SPARQL 1.2 syntax (``<<( )>>``, ``{| |}``, ``~``, SUBJECT/PREDICATE/
OBJECT/isTRIPLE) is parsed via starlayer.sparql's real grammar and
lowered to plain SPARQL 1.1 (tt:HASH encoding) before execution.
SELECT result rows are post-processed to restore tt:HASH URIRefs
back to TripleTerm objects.

Rewriting and parsing are cached (``prepare_query_cached``) on
(query text, effective namespaces, base) - not cleared on
parse()/update() unlike ``_raw_execution_graph``, since a query's
parse tree depends only on its own text, not on graph content.

For the native rdf-1.2 backend the query is routed through
``starlayer.graph.backends.native.native_query``, same as
``StarLayerGraph.query()`` (a native-backed dataset's contexts all
share one store, so it's the same underlying HTTP operation) -
``_build_raw_execution_graph()``'s plain-Graph-copy approach can't
represent real triple-term-valued bindings (rdflib's SPARQL JSON
result parsing doesn't understand "type":"triple"; see
starlayer.graph.backends.native's module docstring).

**Parameters:**

- `query_object: None`
- `processor: None = 'sparql'`
- `result: None = 'sparql'`
- `initNs: None = None`
- `initBindings: None = None`
- `use_store_provided: None = True`
- `kwargs: None`

**Returns:** `Result`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.query](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L915-L976)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-reduce_prefixes"></a>
### `StarLayerDataset.reduce_prefixes`  _(method)_

```python
def reduce_prefixes(self, *, keep=()) -> StarLayerDataset
```

A copy of this dataset whose namespace bindings are only the ones in use (see ``used_prefixes()``), plus any prefix named
in ``keep`` that this dataset has bound. Every graph keeps its triples and its name.

A copy, not a change to this dataset: rdflib cannot remove a binding from a store. The copy is an ordinary in-memory
``StarLayerDataset``, like the other datasets derived from this one (``reifiers()`` and the rest).

**Parameters:**

- `keep: None = ()` - Prefix names to keep even if nothing uses them.

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.reduce_prefixes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L817-L837)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-reifications"></a>
### `StarLayerDataset.reifications`  _(method)_

```python
def reifications(self, s=None, p=None, o=None) -> StarLayerDataset
```

Return a StarLayerDataset of the rdf:reifies triples for every
reified triple term matching the given s/p/o pattern, across every
graph in this dataset - see StarLayerGraph.reifications().

**Parameters:**

- `s: None = None`
- `p: None = None`
- `o: None = None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.reifications](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L860-L876)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-reified_triples"></a>
### `StarLayerDataset.reified_triples`  _(method)_

```python
def reified_triples(self, reifier) -> StarLayerDataset
```

Return a StarLayerDataset of the rdf:reifies triples for the given
reifier node, across every graph in this dataset - a reifier node
reused in more than one graph shows up as a separate match per
graph. See StarLayerGraph.reified_triples().

**Parameters:**

- `reifier: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.reified_triples](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L897-L913)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-reifier_annotations"></a>
### `StarLayerDataset.reifier_annotations`  _(method)_

```python
def reifier_annotations(self, TT) -> StarLayerDataset
```

Return a StarLayerDataset of annotation triples for every reifier
of TT, across every graph in this dataset.

Each result triple is (reifier, predicate, value), excluding
rdf:reifies itself - see StarLayerGraph.reifier_annotations().

**Parameters:**

- `TT: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.reifier_annotations](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L878-L895)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-reifiers"></a>
### `StarLayerDataset.reifiers`  _(method)_

```python
def reifiers(self, TT=None, predicate=None, object=None) -> StarLayerDataset
```

Return a StarLayerDataset of every matching reifier's full triples,
across every graph in this dataset.

Includes each reifier's rdf:reifies link(s) plus annotations - see
StarLayerGraph.reifiers() for filter semantics. Each reifier's
triples stay in the named graph they came from.

**Parameters:**

- `TT: None = None`
- `predicate: None = None`
- `object: None = None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.reifiers](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L839-L858)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-remove"></a>
### `StarLayerDataset.remove`  _(method)_

```python
def remove(self, triple) -> StarLayerDataset
```

Remove a triple, or a quad ``(s, p, o, graph)`` from the graph it names.

A bare triple is removed from the default graph, or from every graph when ``default_union`` is set, like
rdflib's own ``Dataset.remove()``; TripleTerm-aware encoding as above.

**Parameters:**

- `triple: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.remove](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L434-L449)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-remove_graph"></a>
### `StarLayerDataset.remove_graph`  _(method)_

```python
def remove_graph(self, g) -> StarLayerDataset
```

Remove a named graph and forget everything cached about it: the cached execution graph queries read kept
returning the removed graph's triples (GitHub issue #99).

**Parameters:**

- `g: None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.remove_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L460-L467)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-serialize"></a>
### `StarLayerDataset.serialize`  _(method)_

```python
def serialize(self, destination=None, format='trig12', **kwargs) -> str | StarLayerDataset
```

Serialize this dataset.

format='trig12' (default) — TriG 1.2 with GRAPH blocks and <<( )>> triple terms.
format='nq12'   — N-Quads 1.2 with <<( )>> triple terms; one quad per line.
format='trix12' — TriX 1.2 XML with <graph> blocks and <tripleTerm> elements.
format='turtle12'/'longturtle12'/'nt12'/'rdfxml12' — no
    multi-graph syntax exists for these, so every quad is flattened
    into one StarLayerGraph (see to_graph()) and serialized with
    that format; which named graph each triple came from is not
    preserved.
format='n3'/'n3-12'/'text/n3' — aliased straight to 'turtle12', same
    as on StarLayerGraph.
All other formats delegate to rdflib.

**Parameters:**

- `destination: None = None`
- `format: None = 'trig12'`
- `kwargs: None`

**Returns:** `str | StarLayerDataset`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.serialize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L1115-L1226)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-skolemize"></a>
### `StarLayerDataset.skolemize`  _(method)_

```python
def skolemize(self, new_graph=None, bnode=None, authority=None, basepath=None) -> StarLayerGraph
```

Convert blank nodes to skolem IRIs. Same bug class and same fix as
StarLayerGraph.skolemize() - see its own docstring. Defaults
new_graph to a new StarLayerGraph.

**Parameters:**

- `new_graph: None = None`
- `bnode: None = None`
- `authority: None = None`
- `basepath: None = None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.skolemize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L384-L395)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-to_graph"></a>
### `StarLayerDataset.to_graph`  _(method)_

```python
def to_graph(self) -> StarLayerGraph
```

Flatten every quad in this dataset into one new StarLayerGraph.

Which named graph each triple came from is not preserved - two
different graphs asserting the same triple collapse into one. This
is the same flattening serialize() uses for single-graph formats
(turtle12, longturtle12, nt12, rdfxml12, manchester); call this
directly when a real in-memory Graph is wanted - to query it, check
isomorphism, hash it, etc. - rather than a serialized string.

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.to_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L1100-L1113)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-triples"></a>
### `StarLayerDataset.triples`  _(method)_

```python
def triples(self, triple=(None, None, None), context=None) -> Generator[tuple, None, None]
```

Yield (s, p, o), scoped by ``self.default_union`` like rdflib's own Dataset. ``context`` (a graph or its identifier)
restricts the answer to that one graph, as rdflib's ``ConjunctiveGraph.triples`` does; ``(s, p, o) in dataset`` passes it.

default_union=False (the default): only the default graph's own triples,
matching this dataset's declared default-graph-isolation semantics.
default_union=True: the union of every graph, default and named alike.
A triple that is in several graphs is yielded once (the union is a set, as in rdflib's own Dataset).

Encoding triples are filtered; TripleTerms are restored either way.

**Parameters:**

- `triple: None = (None, None, None)`
- `context: None = None`

**Returns:** `Generator[tuple, None, None]`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.triples](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L286-L308)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-triples_choices"></a>
### `StarLayerDataset.triples_choices`  _(method)_

```python
def triples_choices(self, triple, context=None) -> Generator[tuple, None, None]
```

Iterate triples matching a choices pattern, scoped the same way
``triples()`` above is. Filters encoding triples; restores
TripleTerms.

This override exists because the inherited rdflib version queries
``self.store`` directly, bypassing each context's own per-context
TripleTerm registry - the raw ``tt:HASH`` encoding URIRef would
otherwise leak through unrestored.

**Parameters:**

- `triple: None` - A choices-pattern triple (see rdflib's own ``triples_choices()``).
- `context: None = None` - ``None`` with ``default_union=False`` (the default): only the default graph's own triples, matching ``triples()``'s own semantics above. ``None`` with ``default_union=True``: every graph, matching rdflib's own ``ConjunctiveGraph.triples_choices()`` - the same triple may appear more than once if it exists in multiple graphs (unlike ``triples()``, which yields each triple once). Given explicitly: scoped to that one named graph only, via the inherited ``_graph()`` helper (accepts an identifier, a ``Graph``, or another dataset).

**Returns:** `Generator[tuple, None, None]`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.triples_choices](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L310-L341)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-unbind"></a>
### `StarLayerDataset.unbind`  _(method)_

```python
def unbind(self, prefix: str) -> bool
```

Take the binding of ``prefix`` away; True if it was bound. rdflib has no such call: the binding is removed from the
store's own prefix map (in-memory and ``OxigraphStore`` stores; any other raises ``NotImplementedError``, copy with
``reduce_prefixes()`` there). Graphs that share this store lose the prefix too (GitHub issue #44).

**Parameters:**

- `prefix: str`

**Returns:** `bool`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.unbind](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L801-L807)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-update"></a>
### `StarLayerDataset.update`  _(method)_

```python
def update(self, update_object, processor='sparql', initNs=None, initBindings=None, use_store_provided=True, **kwargs) -> None
```

Execute a SPARQL UPDATE across named graphs with SPARQL-star support.

Triple-term patterns in WHERE clauses are rewritten to SPARQL 1.1
(rdf-1.1 backend only — see below). All cached per-graph registries
are rebuilt after execution so that newly added triple terms are
immediately visible.

Remote-store (Fuseki/Oxigraph) updates bypass rdflib's own
``Dataset(store=...).update()`` and go directly over HTTP instead
(see ``starlayer.graph.backends.native.native_update``), for both
backends: rdflib's ``SPARQLStore._is_contextual()`` treats any
string graph identifier other than the literal ``"__UNION__"`` as
needing a wrapping ``GRAPH { }`` block, so ``Dataset.update()``
would wrap the whole update text in an extra ``GRAPH { }`` block
that nests illegally around a plain ``INSERT DATA { GRAPH <uri>
{...} }`` against a real Oxigraph/Fuseki endpoint.

For the rdf-1.2 backend the update text is sent unmodified (the
endpoint understands ``<<( )>>`` natively); for rdf-1.1 it is
parsed and lowered to the tt:HASH encoding first (native_update
itself, via starlayer.sparql).

**Parameters:**

- `update_object: None`
- `processor: None = 'sparql'`
- `initNs: None = None`
- `initBindings: None = None`
- `use_store_provided: None = True`
- `kwargs: None`

**Returns:** `None`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.update](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L1006-L1086)

---

<a id="entity-starlayer-graph-graph-starlayer_dataset-StarLayerDataset-used_prefixes"></a>
### `StarLayerDataset.used_prefixes`  _(method)_

```python
def used_prefixes(self) -> list[tuple[str, URIRef]]
```

The namespace bindings of this dataset that matter: ``(prefix, namespace)`` pairs, sorted by prefix, for the namespaces an
IRI in any graph of the dataset is in, or a named graph's own name (TriG writes it). The default prefixes rdflib binds and
prefixes nothing uses are left out - see ``StarLayerGraph.used_prefixes()``.

**Returns:** `list[tuple[str, URIRef]]`

**Source:** [starlayer.graph.graph.starlayer_dataset.StarLayerDataset.used_prefixes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_dataset.py#L809-L815)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph"></a>
### `StarLayerGraph`  _(class)_

rdflib.Graph extended with RDF 1.2 triple-term support.

Triple terms are represented as Python 3-tuples or TripleTerm objects.
Internally they are encoded as content-addressed URIRefs under TT_NS in
the rdflib store; that encoding is completely hidden from callers.

All unoverridden rdflib.Graph methods (namespace management, SPARQL,
serialization, etc.) are inherited and work without modification.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L450-L3953)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-add"></a>
### `StarLayerGraph.add`  _(method)_

```python
def add(self, triple) -> StarLayerGraph
```

Add a triple. A TripleTerm (or plain 3-tuple) in the object position is
converted to its internal encoding automatically. Always returns self,
matching rdflib's own Graph.add() and enabling method chaining
(g.add(...).add(...)).

    g.add((s, p, o))              # plain triple
    g.add((s, p, TripleTerm(...))) # TripleTerm as object
    g.add((s, p, (a, b, c)))      # plain tuple treated as TripleTerm

**Parameters:**

- `triple: None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.add](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1260-L1289)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-addN"></a>
### `StarLayerGraph.addN`  _(method)_

```python
def addN(self, quads) -> StarLayerGraph
```

Add multiple quads, encoding all TripleTerms in one store.addN() call.

Unlike the default Graph.addN() → store.addN() path, this override
collects encoding triples (rdf:subject/predicate/object for each
TripleTerm) together with the main triples so that all inserts are
submitted to the store in a single batch. On transaction-aware
backends (SQLAlchemy, Sleepycat) this means one commit instead of
three per triple term, which is significantly faster for bulk loads.

**Parameters:**

- `quads: None` - An iterable of (subject, predicate, object, context) quads.

**Returns:** `StarLayerGraph` - self, enabling method chaining.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.addN](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1291-L1362)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-add_reification"></a>
### `StarLayerGraph.add_reification`  _(method)_

```python
def add_reification(self, reifier, triple_term) -> StarLayerGraph
```

Add reifier rdf:reifies triple_term, making the node an official
reifier.

**Parameters:**

- `reifier: None` - The node to make a reifier.
- `triple_term: None` - The TripleTerm to reify - a TripleTerm, or an (s, p, o) tuple to wrap into one.

**Returns:** `StarLayerGraph` - This graph, matching every other mutating method on this class (add()/remove()/addN()/etc), so calls can be chained.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.add_reification](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1756-L1783)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-add_reifier_annotation"></a>
### `StarLayerGraph.add_reifier_annotation`  _(method)_

```python
def add_reifier_annotation(self, predicate, obj, name=None) -> IdentifiedNode
```

Create a reifier node and add one annotation property to it.

The node is not yet a reifier until add_reification() is called::

    r = g.add_reifier_annotation(EX.confidence, Literal("0.9"), name=EX.stmt1)
    g.add_reification(r, (EX.bob, EX.knows, EX.carol))

    # or inline:
    g.add_reification(
        g.add_reifier_annotation(EX.reported, EX.NYTimes),
        triple_term
    )

**Parameters:**

- `predicate: None` - The annotation predicate.
- `obj: None` - The annotation value.
- `name: None = None` - If given, the reifier's URI; otherwise a fresh BNode is minted.

**Returns:** `IdentifiedNode` - The reifier node - a ``URIRef`` if ``name`` was given, otherwise a fresh ``BNode`` - ready to pass into ``add_reification()``.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.add_reifier_annotation](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1727-L1754)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-cbd"></a>
### `StarLayerGraph.cbd`  _(method)_

```python
def cbd(self, resource, *, target_graph=None, include_reifications=True) -> StarLayerGraph
```

Concise Bounded Description.

**Parameters:**

- `resource: None` - The resource to compute the CBD for.
- `target_graph: None = None` - Graph to add the CBD's triples to; defaults to a new StarLayerGraph.
- `include_reifications: None = True` - Whether to include reification triples.

**Returns:** `StarLayerGraph` - target_graph, populated with the CBD.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.cbd](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2928-L2951)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-close"></a>
### `StarLayerGraph.close`  _(method)_

```python
def close(self, commit_pending_transaction: bool=False) -> None
```

Close the underlying store, optionally committing pending writes.

**Parameters:**

- `commit_pending_transaction: bool = False`

**Returns:** `None`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.close](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1252-L1254)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-de_skolemize"></a>
### `StarLayerGraph.de_skolemize`  _(method)_

```python
def de_skolemize(self, new_graph=None, uriref=None) -> StarLayerGraph
```

Convert skolem IRIs back to blank nodes.

Overridden for the same reason, and with the same fix, as
skolemize() above - see its docstring.

**Parameters:**

- `new_graph: None = None` - Graph to add the de-skolemized triples to; defaults to a new StarLayerGraph.
- `uriref: None = None` - If given, only this skolem IRI is de-skolemized.

**Returns:** `StarLayerGraph` - new_graph, populated with the de-skolemized triples.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.de_skolemize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3004-L3029)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-derive_shape"></a>
### `StarLayerGraph.derive_shape`  _(method)_

```python
def derive_shape(self, template_shape=None, *, ignored_properties=None, use_default_ignored_properties: bool=True) -> StarLayerGraph
```

Infer a SHACL shape from self's own data and return it.

One ``sh:NodeShape`` per distinct ``rdf:type`` found (the simplest
option: derive shapes from classes, never per-node or heuristic
clustering), optionally reconciled against an existing template
shape.

Every returned shape is closed (``sh:closed true``) and is
self-checked to conform against self before being returned (a real
assertion, not just documentation - see ``shape_derivation.py``).
Goes through ``starlayer.shacl`` for all SHACL semantics, never bare
``pyshacl`` directly - self or template_shape may contain genuine
RDF 1.2 content (triple terms) that only starlayer.shacl understands.

**Parameters:**

- `template_shape: None = None` - If omitted, every returned NodeShape is built fresh from self's own data. If given (any Graph, including a StarLayerGraph with genuine RDF 1.2 content), its own constraints are validated against self and, wherever a principled data-driven fix exists (cardinality, datatype, class, node kind including ``sh:TripleTerm``, numeric-range bounds, string length, ``sh:languageIn``, additive ``sh:in`` widening), recomputed from the *true* current data rather than patched around a single violating value; constraint types with no generic fix (``sh:pattern``, cross-property comparisons like ``sh:equals``/ ``sh:lessThan``) are dropped with an ``rdfs:comment`` note; opaque ``sh:sparql``-based/custom constraint components are left untouched, also with a note, since there's no way to know whether a failure there is a real data problem or a genuinely important check. Any predicate observed in self with no matching ``sh:property`` on the relevant shape, and any class present in self with no shape at all, get freshly-derived additions - "extend any new properties" generalized to the whole graph.
- `ignored_properties: None = None` - Extra predicates to exclude from every derived ``sh:NodeShape``'s candidate-property scan (union'd into ``sh:ignoredProperties``, alongside the resolved default list below and, unconditionally, ``rdf:type`` itself - required for any closed shape to conform, since ``sh:closed`` doesn't exempt ``rdf:type`` automatically). A template's own existing ``sh:ignoredProperties`` is always carried forward too.
- `use_default_ignored_properties: bool = True` - When true (default), also excludes ``shape_derivation.DEFAULT_IGNORED_PROPERTIES`` (``rdfs:label``/``comment``, ``dcterms:created``/ ``modified``) - pass False to opt out of that built-in list entirely and rely only on ``ignored_properties=``.

**Returns:** `StarLayerGraph` - A StarLayerGraph (a real, standalone shapes graph) - wrapped via ``from_rdflib()`` for consistency with every other graph-returning method on this class, even though a derived shapes graph has no triple-term content of its own today.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.derive_shape](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3840-L3903)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-empty_like"></a>
### `StarLayerGraph.empty_like`  _(method)_

```python
def empty_like(self) -> StarLayerGraph
```

A new, empty graph of the same kind as this one, with the same
namespace bindings.

The rule for graphs derived from this one (``infer()``'s default
result, a native ``query()``'s CONSTRUCT result): they are created
*like their source*. A graph backed by an in-process Oxigraph yields a
fresh, independent in-process Oxigraph with the same representation;
any other kind - the default in-memory store, a remote endpoint (a new
remote database can't be minted), SQLAlchemy - yields an ordinary
in-memory ``StarLayerGraph``. Nothing global is consulted: the source
graph itself carries the choice, so internal scratch graphs elsewhere
are unaffected.

**Returns:** `StarLayerGraph` - A new empty StarLayerGraph.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.empty_like](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3338-L3359)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-from_rdflib"></a>
### `StarLayerGraph.from_rdflib`  _(method)_

```python
def from_rdflib(cls, source_graph) -> StarLayerGraph
```

Wrap a plain rdflib.Graph (e.g., from StarLayerTurtleParser).

Namespace bindings, triples, and the TripleTerm registry are all
copied from the source graph. If the source uses the intermediate
BNode TT encoding (with sl:TripleTerm type markers), it is converted
to content-addressed tt: URIRefs before copying.

``source_graph.identifier`` is preserved onto the new graph: a
graph with a real, caller-given identity (e.g. a named graph
retrieved from a ``Dataset``, which always carries its own real
IRI) keeps that identity through this conversion, rather than it
being replaced by an unrelated, meaningless one. Deliberately
**not** done when ``source_graph`` is itself a whole
``Dataset``/``ConjunctiveGraph`` (as opposed to one of its named
graphs) - a dataset has no single meaningful identity of its own
(``Dataset.identifier`` is itself deprecated in modern rdflib), so
there's nothing worth preserving there; this also avoids triggering
that deprecation warning on every dataset-to-graph conversion.

**Parameters:**

- `source_graph: None` - The graph to wrap. May also be a Dataset/ConjunctiveGraph: triples are read via its own ``.triples((None, None, None))``, which - like iterating the dataset directly - honors whatever ``default_union`` it was constructed with (rdflib default: False), so only its default graph is copied unless the caller explicitly opted into a unioned view. Named graphs are never selected implicitly; use ``dataset.get_context(identifier)`` first for a specific one.

**Returns:** `StarLayerGraph` - A new StarLayerGraph wrapping source_graph's content.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.from_rdflib](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3906-L3953)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-has_import_locally"></a>
### `StarLayerGraph.has_import_locally`  _(method)_

```python
def has_import_locally(self, iri: Any) -> bool
```

True iff ``iri`` (typically an ``owl:imports`` target) already
has at least one triple with it as subject already present in
this graph - i.e. its content is already co-located here, so no
loader is needed to resolve it.

Guards against a real false-positive case: two shapes-graphs that
mutually ``owl:imports`` each other, loaded together into one
graph, would otherwise trip both ``resolve_imports()``'s loader
call and ``validate()``'s unresolved-import check for an import
that's already fully satisfied right here. ``resolve_imports()``
checks this before ever calling ``loader`` for a given import - a
locally-satisfied import never reaches the loader at all.

**Parameters:**

- `iri: Any` - The import target to check.

**Returns:** `bool` - True if ``iri`` already has at least one triple as subject in this graph.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.has_import_locally](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3681-L3702)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-has_triple_term"></a>
### `StarLayerGraph.has_triple_term`  _(method)_

```python
def has_triple_term(self, subject, predicate, object) -> bool
```

Return True if a TripleTerm with these exact components exists in the graph.

**Parameters:**

- `subject: None` - The triple term's subject.
- `predicate: None` - The triple term's predicate.
- `object: None` - The triple term's object.

**Returns:** `bool` - True if a matching TripleTerm exists in the graph.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.has_triple_term](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1952-L1967)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-infer"></a>
### `StarLayerGraph.infer`  _(method)_

```python
def infer(self, entailment=ENTAILMENT.RDFS, *, mode: str='full', target_graph=None, engine: str='hermit', timeout=_OWL_DL_TIMEOUT_DEFAULT) -> StarLayerGraph
```

Materialize an RDFS/OWL-RL entailment closure.

By default this returns a NEW graph, never mutating self
(mode="in-place" is the deliberate exception - see below). Requires
the optional ``owlrl`` dependency
(``pip install starlayer[reasoning]``).

Any triple term in self is decomposed into its synthetic
blank-node reification form (the same one rdfc10_hash()/
isomorphic() use - see starlayer.graph.compare._decompose()) purely
so owlrl can run without crashing: its RDFS closure asserts "x
rdf:type rdfs:Resource" for every term seen anywhere in a triple,
including subject position, and a triple term is never legal there
under RDF 1.2 (see add()'s own "triple terms are not permitted in
subject position" guard). That decomposition never reaches the
returned graph for mode="full"/"delta", though: self's own triples
are copied in as-is (real TripleTerm objects intact, for a
non-native self), and only the *newly-entailed* portion (mode=
"delta"'s content, also included in mode="full") can still contain
a decomposed reification fragment instead of a real TripleTerm -
and only for a derived fact that isn't itself expressible with
one. This is structural, not a gap left open by choice: a rule
like rdfs4a/4b that types *every* term as rdfs:Resource inherently
wants to put a triple term in subject position, which RDF 1.2
never permits for any triple, entailed or asserted - there is no
legal real-TripleTerm form of that fact to recover. Nothing
rewires the delta's synthetic blank node back to the real triple
term self's own copied-in triples use, either - they're unrelated
objects in the output graph, not the same node re-described two
ways. mode="in-place" inherits this same caveat, with one
difference: there, a stray decomposed reification fragment lands
directly in the graph you're still working with, since there's no
disposable copy to contain it instead.

owlrl has no truth maintenance: retracting a fact from self later
does not retract anything this call already entailed from it.
Re-run infer() from the original facts after any edit, rather than
trying to patch a previous call's output.

For a native (backend='rdf-1.2') self, reading "self's own data"
(via plain iteration, same as _decompose()/for t in self) is scoped
to self.identifier - GRAPH <self.identifier> { ... } - unless
self.identifier is exactly rdflib.graph.DATASET_DEFAULT_GRAPH_ID
(see _native_scoped()). This is unrelated to query()/update(), which
send text straight through unscoped. A native StarLayerGraph
constructed with no explicit identifier= defaults to
DATASET_DEFAULT_GRAPH_ID automatically (see __init__), so the
common case already agrees with query()/update() by construction.
The one remaining case this doesn't cover: a caller who explicitly
passes a *different*, non-default identifier= that has no matching
named graph on the endpoint - infer() then correctly sees an empty
graph, same as any SPARQL query would against a real but
currently-empty named graph. That's expected behavior for a named
graph with no data yet, not a footgun.

**Parameters:**

- `entailment: None = ENTAILMENT.RDFS` - One real entailment regime IRI (``ENTAILMENT.RDF``, ``ENTAILMENT.RDFS``, ``ENTAILMENT["OWL-RDF-Based"]``, ``ENTAILMENT["OWL-Direct"]``), or an iterable of more than one to combine them into a single pass. ``ENTAILMENT.RDF`` combines freely with ``ENTAILMENT.RDFS``/ ``ENTAILMENT["OWL-RDF-Based"]``, in any subset including all three at once - the native RDF delta (see below) is unioned with whatever the other regime(s) entail, sound either way, though in practice RDFS/OWL-RL's own rules already produce everything RDF alone would (confirmed empirically) - the combination is supported for completeness/consistency, not because it adds coverage a caller would otherwise be missing. ``{ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}`` is genuinely more than ``ENTAILMENT["OWL-RDF-Based"]`` alone: e.g. universal rdfs:Resource typing and several rdfs:Datatype-related entailments are only present when RDFS's own rules run alongside OWL-RL's - see ``_resolve_owlrl_semantics()``. See ``starlayer.graph.graph.entailment_regimes``'s own module docstring for what each IRI means and which combinations are actually supported. ``ENTAILMENT["OWL-Direct"]`` alone selects full OWL 2 DL reasoning - a genuinely different computational model, tableau-based rather than forward-chaining rules, so it can derive disjunctive entailments owlrl structurally cannot, e.g. C subClassOf (A or B), not-A(x) |= B(x). Raises ``owl_dl.InconsistentOntologyError``, not a silent triple, if self's data is logically inconsistent - unlike the owlrl-backed regimes, whose consistency checking is partial and never raises. See `engine` below for which actual reasoner runs this. ``ENTAILMENT["OWL-Direct"]`` is never combinable with any other regime (raises ``ValueError``). ``ENTAILMENT.RDF`` is implemented natively (no ``owlrl`` dependency, no reasoner at all for its own portion of the work) - just rdfD2 (every predicate used is entailed ``rdf:type rdf:Property``) plus the small fixed set of RDF axiomatic triples actually relevant to self's data. Datatype literal value-space well-typing (rdfD1/rdfD1a) is a deliberate v1 scope reduction, not built - see ``_infer_rdf_before_and_delta()``'s own docstring.
- `mode: str = 'full'` - All three ultimately reach the same closure (self's own data plus everything entailed from it) - this chooses where that ends up and how much of it comes back as a distinct value. "full" (default) returns a NEW graph with the original triples plus everything newly entailed. "delta" returns a NEW graph with only the newly-entailed triples, none of the originals - the smaller artifact query()'s entailment=ENTAILMENT["OWL-RDF-Based"] caches and queries as a live union with self, rather than caching a full closure copy. "in-place" adds just the newly-entailed triples into self directly (self already has the originals) and returns self - works for any self, including native and triple-term-bearing ones (see the triple-term-fidelity paragraph above for the one narrow caveat it still doesn't avoid). target_graph must not be given together with it (raises ValueError - mutating self has no separate destination). See VALID_INFER_RETURN_MODES.
- `target_graph: None = None` - Only meaningful for mode="full"/"delta"; defaults to a new StarLayerGraph, or if given, entailed triples are added to it (never cleared first) - must be a StarLayerGraph, not a plain rdflib.Graph, same restriction as cbd() and for the same reason: consistency with the rest of this class's API.
- `engine: str = 'hermit'` - Only meaningful for entailment=ENTAILMENT["OWL-Direct"] (any other entailment regime combined with a non-default engine raises ValueError - fail loudly rather than let a caller believe it silently did something for an owlrl-backed regime). Picks which of two genuinely different reasoners runs the tableau reasoning above - neither is a strict replacement for the other, so this is a real tradeoff to make per call, not an implementation detail: "hermit" (default) is owlready2 + Java HermiT, sound *and* complete for all of OWL 2 DL (SROIQ) - the strongest guarantee either engine offers, but needs the optional `starlayer[hermit]` extra (`owlready2`) AND a real Java runtime reachable on PATH. "rustdl" is a pure-Rust reasoner (no JVM at all), needing only the optional `starlayer[rustdl]` extra - see ``owl_dl_rustdl.py``'s own module docstring for its full completeness fragment, known gaps, and `rustdl.UnsupportedAxiomError` cases; that file's docstring is the authoritative, current account, not restated here.
- `timeout: None = _OWL_DL_TIMEOUT_DEFAULT` - Only meaningful for entailment=ENTAILMENT["OWL-Direct"] (same ValueError contract as engine= above for any other entailment regime). Wall-clock budget in seconds for the actual reasoner call, shared by both engines - defense-in- depth against a hang neither engine has a known, structurally-detectable pattern for (RustDL's one *known* hang pattern is already caught separately, fast and pre-flight - see `engine=` above; this timeout is the backstop for everything else). Default `_timeout.DEFAULT_TIMEOUT_SECONDS` (120s); pass `None` to disable entirely (wait indefinitely). Implemented as a real subprocess/process-group kill, not a cooperative cancellation - see `starlayer.graph/graph/_timeout.py`'s own module docstring for why that's the only mechanism that reliably works against an opaque, uninterruptible reasoner call (a JVM subprocess for "hermit", an in-process native PyO3 call for "rustdl") - a raised `_timeout.ReasoningTimeoutError` is guaranteed to leave no orphaned JVM/native process still running behind it.

**Returns:** `StarLayerGraph` - A StarLayerGraph: `target_graph` for mode="full"/"delta", or self for mode="in-place".

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.infer](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3408-L3656)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-isomorphic"></a>
### `StarLayerGraph.isomorphic`  _(method)_

```python
def isomorphic(self, other) -> bool
```

Graph isomorphism, aware of TripleTerms.

Overridden because the inherited rdflib.Graph.isomorphic() is (a) a
crude approximation — see that method's own docstring: "only an
approximation ... very well could be a false positive" — and (b)
blind to BNodes embedded inside a TripleTerm's content-address,
which would otherwise compare as different, unrelated ground terms
across separately parsed graphs that are actually the same shape
(e.g. <<( _:x :p :o )>> vs <<( _:other :p :o )>>, both otherwise
identical). Delegates to rdflib.compare's real canonical-labeling
algorithm after unfolding each graph's TripleTerms back to native
BNode-based reification (_unfold_tt_encoding), which mirrors the
parser's own intermediate form before content-address skolemization
(see turtle_parser._skolemize_encoding) — so a BNode nested inside a
triple term is treated as relabelable, the same as any other BNode,
rather than baked into an opaque tt:HASH URIRef.

**Parameters:**

- `other: None` - The graph to compare against. Need not be a StarLayerGraph - the unfold works directly off raw triples, degrading to a no-op (plain rdflib isomorphism) for a graph with no tt: content at all.

**Returns:** `bool` - True if the two graphs are isomorphic.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.isomorphic](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3031-L3060)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-open"></a>
### `StarLayerGraph.open`  _(method)_

```python
def open(self, configuration, create: bool=False) -> StarLayerGraph
```

Open a persistent store and rebuild the TripleTerm registry.

Delegates to rdflib's Graph.open() then scans the store for any
existing tt:HASH encoding triples so TripleTerms are immediately
usable without a separate rebuild call. Always returns self, not
rdflib's own Graph.open() status value.

The store backend (e.g. Sleepycat, rdflib-sqlalchemy) is not a
StarLayer dependency — install and configure it separately, then
pass store='StoreName' to the constructor before calling open().

Example::

    sg = StarLayerGraph(store='Sleepycat')
    sg.open('/path/to/db', create=True)

**Parameters:**

- `configuration: None`
- `create: bool = False`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.open](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1230-L1250)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-owl_imports"></a>
### `StarLayerGraph.owl_imports`  _(method)_

```python
def owl_imports(self) -> tuple[Any, ...]
```

Every directly-declared object of this graph's own
``owl:imports`` triples, deduplicated, in first-seen order.

Purely a read of what's already asserted; resolves nothing,
fetches nothing, and doesn't recurse into whatever those IRIs
might themselves import (that only happens once
``resolve_imports()`` actually loads their content - this graph's
own triples are the only thing there is to read from here).

This is step 1 of the three-step shape this capability has:
discover what's declared (this method), decide whether a
particular loader can do anything with a given IRI
(``can_resolve_import()``, a plain function, not a method - it's
a question about the *loader*, not about this graph's own data),
then actually resolve/merge (``resolve_imports()`` below).

**Returns:** `tuple[Any, ...]` - The declared ``owl:imports`` targets, deduplicated, in first-seen order.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.owl_imports](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3658-L3679)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-parse"></a>
### `StarLayerGraph.parse`  _(method)_

```python
def parse(self, source=None, publicID=None, format=None, location=None, file=None, data=None, **kwargs) -> StarLayerGraph
```

Parse RDF data into the graph.

format='turtle12'  — Turtle 1.2 with <<( )>>, {| |}, ~ reifier syntax
format='nt12'      — N-Triples 1.2 with <<( )>> triple terms
format='nq12'      — N-Quads 1.2
format='trig12'    — TriG 1.2
format='trix12'    — TriX 1.2 XML
format='rdfxml12'  — RDF/XML 1.2 with rdf:parseType="Triple" and
                     rdf:annotation/rdf:annotationNodeID (RDF 1.2 XML Syntax)
format='manchester' (alias 'omn') — OWL 2 Manchester Syntax; see
                     starlayer.graph.parsers.manchester_parser's module
                     docstring for the supported subset
format='n3'/'n3-12'/'text/n3' — aliased straight to 'turtle12'.
                     Only the plain-triples subset N3 shares with
                     Turtle is supported, not real N3 — a formula
                     ('{ }'), a '=>' rule, or a '?x' variable raises
                     Turtle12SyntaxError, since those aren't Turtle
                     syntax at all. The input must be valid
                     Turtle/Turtle 1.2.

'nq12'/'trig12'/'trix12' above, and the bare (RDF 1.1) 'nquads'/
'trig'/'trix' handled by the fallback below, all name quad-shaped
(multi-graph-capable) formats being parsed into a single graph.
A document resolving to at most one distinct graph - including the
trivial case of everything being in the default graph - parses
normally (any explicit graph name is simply dropped). A document
genuinely spanning two or more distinct graphs raises
MultipleGraphsError instead of silently flattening them together -
use StarLayerDataset.parse() to keep each graph separate.

All other formats delegate to rdflib (no triple-term support) -
except bare 'nquads'/'trig'/'trix', which this project still routes
through the single-vs-multiple-graph check above (plain rdflib
delegation would otherwise silently yield zero triples the moment
any named graph appears at all, even just one).

**Parameters:**

- `source: None = None` - Input source, as accepted by rdflib's own parse().
- `publicID: None = None` - Base URI for relative-IRI resolution; see the per-format notes above.
- `format: None = None` - The format name - see the per-format notes above.
- `location: None = None` - A URL or file path to parse from.
- `file: None = None` - An open file-like object to parse from.
- `data: None = None` - A string or bytes containing the RDF data to parse. not listed above.
- `kwargs: None`

**Returns:** `StarLayerGraph` - This graph, with the parsed triples added.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.parse](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2010-L2265)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-print"></a>
### `StarLayerGraph.print`  _(method)_

```python
def print(self, format: str='turtle12', out=None) -> None
```

Print the graph to stdout (or `out`).

**Parameters:**

- `format: str = 'turtle12'` - Serialization format, passed through to serialize(). Defaults to 'turtle12' so TripleTerms display correctly.
- `out: None = None` - File-like object to print to; defaults to sys.stdout.

**Returns:** `None`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.print](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2917-L2926)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-qname_term"></a>
### `StarLayerGraph.qname_term`  _(method)_

```python
def qname_term(self, node) -> str
```

Prefixed n3 form of any term - URIRef, BNode, Literal, TripleTerm,
or DirLangString.

Unlike the inherited qname(), which only accepts a URI and raises on
anything else, this dispatches on whatever it's given: a caller
iterating over triples() often doesn't know in advance whether a
given position holds a plain node or a TripleTerm, and qname_term()
does the right thing either way without an isinstance check.

**Parameters:**

- `node: None` - The term to render.

**Returns:** `str` - The term's prefixed N3 form.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.qname_term](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1969-L1985)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-query"></a>
### `StarLayerGraph.query`  _(method)_

```python
def query(self, query_object, processor='sparql', result='sparql', initNs=None, initBindings=None, use_store_provided=True, entailment=None, infer: str='changed', engine: str='hermit', timeout=_OWL_DL_TIMEOUT_DEFAULT, **kwargs) -> Result
```

Execute a SPARQL query. Triple-term patterns are rewritten to SPARQL 1.1.

The rewritten query runs against a plain Graph view of the same store so
that encoding triples (rdf:subject/predicate/object on tt: URIRefs) are
visible to the SPARQL engine. TripleTerm/tuple values in ``initBindings``
are encoded to their internal tt:HASH URIRef first, the same way every
other read path in this class resolves triple terms before matching
against the store. Results are post-processed to restore tt:HASH
URIRefs back to TripleTerm objects.

For the native rdf-1.2 backend the query is routed through
starlayer.graph.backends.native.native_query, which uses the endpoint's
own triple-term syntax.

Unlike ``infer()``, which always materializes a new graph, every
``entailment=`` value here does its work at query time with no
copy of ``self``'s own data: a plain query rewrite for
``ENTAILMENT.RDF``/``ENTAILMENT.RDFS``, or a live union of ``self``
with a small cached delta (never a full copy of ``self``) for
``ENTAILMENT["OWL-RDF-Based"]``/``ENTAILMENT["OWL-Direct"]``.

**Parameters:**

- `query_object: None` - The SPARQL query text, or an already-prepared Query object. **Known gap, found 2026-10-14**: for ``entailment=ENTAILMENT.RDF``/``ENTAILMENT.RDFS`` specifically, the entailment-rewrite step only ever runs when this is a plain string (inside ``query_cache.prepare_query_cached``, only reached via the ``isinstance(query_object, str)`` branch below) - an already-prepared ``Query`` object's own algebra is used as-is, silently *without* the rewrite, for these two regimes only (``OWL-RDF-Based``/``OWL-Direct`` are unaffected - they union with a cached delta instead of rewriting the query at all). Pass the query as text if you need ``entailment=ENTAILMENT.RDF``/``RDFS`` together with a query you also want prepared once elsewhere - see ``starlayer.sparql.StarQuery``'s own module docstring for the full account and its own workaround.
- `processor: None = 'sparql'` - Passed through to the underlying rdflib/native query call.
- `result: None = 'sparql'` - Passed through to the underlying rdflib/native query call.
- `initNs: None = None` - Namespace bindings for the query; defaults to this graph's own bound namespaces.
- `initBindings: None = None` - Initial variable bindings. A TripleTerm or (s, p, o) tuple value is encoded to its internal tt:HASH URIRef first, the same way every other read path resolves triple terms before matching against the store.
- `use_store_provided: None = True` - Passed through to the underlying rdflib/ native query call.
- `entailment: None = None` - ``None`` (default, plain simple entailment), ``ENTAILMENT.RDF`` (query-time RDF entailment rewrite - see ``starlayer.sparql.entailment_rdf``; not available against the native backend), ``ENTAILMENT.RDFS`` (query-time RDFS rewrite - see ``starlayer.sparql.entailment_rdfs``; not available against the native backend), ``ENTAILMENT["OWL-RDF-Based"]`` (queries the live union of ``self`` and a small cached delta of just its newly-entailed triples - see ``infer(mode="delta")`` and the ``infer`` parameter below), ``ENTAILMENT["OWL-Direct"]`` (OWL 2 DL's counterpart to ``ENTAILMENT["OWL-RDF-Based"]`` - the SPARQL Entailment Regimes spec's own name for OWL-Direct-Semantics-backed querying: same live-union-with-a-cached-delta design, but the delta comes from ``infer(entailment=ENTAILMENT["OWL-Direct"], engine=..., mode="delta")`` - see ``infer()``'s own docstring for the full ``engine=``/``timeout=`` contract and what each engine guarantees. Tableau DL reasoning is routinely orders of magnitude slower than ``owlrl``'s forward-chaining, so ``infer="changed"`` bounds how *often* this cost is paid, not how *expensive* any single recomputation is - for a latency-sensitive caller, materialize once ahead of time via ``infer(entailment=ENTAILMENT["OWL-Direct"], mode="in-place"/"full")`` instead and query the result plainly; reserve this regime for when live freshness is genuinely worth the cost. Raises ``starlayer.graph.graph.owl_dl.InconsistentOntologyError`` uncaught if ``self``'s data is logically inconsistent, unlike ``ENTAILMENT["OWL-RDF-Based"]``'s partial/silent consistency checking), or ``"native"`` (only legal with ``backend='rdf-1.2'`` - a self-documenting label for "this endpoint is expected to handle entailment itself"; changes no behavior on that path, since ``native_query()`` already sends text straight through unmodified regardless of this value - see ``docs/fuseki-reasoning-setup.md`` for actually configuring an endpoint that makes it meaningful). A per-call choice, not a graph-level setting - the same graph can be queried with different (or no) entailment on different calls.
- `infer: str = 'changed'` - Only consulted when ``entailment=ENTAILMENT["OWL-RDF-Based"]`` or ``entailment=ENTAILMENT["OWL-Direct"]``; ignored otherwise. Controls reuse of ``self``'s cached entailment delta (``self._owl_rl_cache`` for ``ENTAILMENT["OWL-RDF-Based"]``; ``self._owl_dl_cache[engine]`` for ``ENTAILMENT["OWL-Direct"]``, keyed per engine so switching ``engine=`` between calls doesn't invalidate the other engine's cached slot) against ``self._mutation_generation`` (bumped by ``_on_mutated()`` on every real edit to ``self`` - see ``VALID_INFER_MODES``): ``"changed"`` (default) recomputes only if ``self`` was edited since the cache was last computed; ``"always"`` ignores the cache and always recomputes; ``"cached"`` reuses whatever is cached if anything is, computing only when there's no cache yet. When ``self`` is non-native and has no triple terms, ``self``'s own data is always queried live regardless of this setting - only the entailed delta is subject to it. When ``self`` is native-backed or has triple terms, a snapshot of ``self``'s own data is refreshed on this same cadence too (see the ``ENTAILMENT["OWL-RDF-Based"]`` branch's own comment for why).
- `engine: str = 'hermit'` - Only meaningful when ``entailment=ENTAILMENT["OWL-Direct"]``; passing a non-default value with any other ``entailment=`` raises ``ValueError`` (fail loudly rather than let a caller believe it silently did something for a different regime). ``"hermit"`` (default) or ``"rustdl"`` - see ``infer()``'s own docstring for the full ``engine=``/ ``timeout=`` contract.
- `timeout: None = _OWL_DL_TIMEOUT_DEFAULT` - Only meaningful when ``entailment=ENTAILMENT["OWL-Direct"]``; same validation and meaning as ``infer()``'s own ``timeout`` parameter - see ``infer()``'s own docstring for the full ``engine=``/ ``timeout=`` contract. query call.
- `kwargs: None`

**Returns:** `Result` - The query Result, with any tt:HASH URIRef restored to its TripleTerm.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.query](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2267-L2686)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-reduce_prefixes"></a>
### `StarLayerGraph.reduce_prefixes`  _(method)_

```python
def reduce_prefixes(self, *, keep=()) -> StarLayerGraph
```

A copy of this graph whose namespace bindings are only the ones in use (see ``used_prefixes()``), plus any prefix named in
``keep`` that this graph has bound.

A copy, not a change to this graph: rdflib has no way to remove a binding from a store, so the bindings of a graph can
only be reduced by building a new one. The copy is created like its source (see ``empty_like()``: an in-process Oxigraph
graph gives an in-process Oxigraph graph, anything else an in-memory one) and holds the same triples, triple terms
included.

**Parameters:**

- `keep: None = ()` - Prefix names to keep even if nothing uses them.

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.reduce_prefixes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3379-L3406)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-reifications"></a>
### `StarLayerGraph.reifications`  _(method)_

```python
def reifications(self, s=None, p=None, o=None) -> Generator[TripleTerm, None, None]
```

Yield TripleTerms that have at least one reifier and match the s/p/o pattern.

    g.reifications()                 # all reified triple terms
    g.reifications(p=EX.knows)       # reified TTs with that predicate

**Parameters:**

- `s: None = None` - Only triple terms with this subject.
- `p: None = None` - Only triple terms with this predicate.
- `o: None = None` - Only triple terms with this object.

**Returns:** `Generator[TripleTerm, None, None]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.reifications](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1833-L1865)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-reified_triples"></a>
### `StarLayerGraph.reified_triples`  _(method)_

```python
def reified_triples(self, reifier) -> Generator[TripleTerm, None, None]
```

Yield the TripleTerms reified by the given reifier node.

**Parameters:**

- `reifier: None` - The reifier node to look up.

**Returns:** `Generator[TripleTerm, None, None]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.reified_triples](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1892-L1911)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-reifier_annotations"></a>
### `StarLayerGraph.reifier_annotations`  _(method)_

```python
def reifier_annotations(self, TT) -> Generator[tuple, None, None]
```

Yield (reifier, predicate, value) annotation triples for all reifiers of TT.

Excludes the rdf:reifies triple itself.

**Parameters:**

- `TT: None` - The triple term whose reifiers' annotations to yield.

**Returns:** `Generator[tuple, None, None]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.reifier_annotations](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1867-L1890)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-reifiers"></a>
### `StarLayerGraph.reifiers`  _(method)_

```python
def reifiers(self, TT=None, predicate=None, object=None) -> Generator[IdentifiedNode, None, None]
```

Yield reifier nodes matching the given filters.

Filters combine: reifiers(TT=t, predicate=p, object=o) returns
reifiers that reify t AND have (reifier, p, o) in the graph.

**Parameters:**

- `TT: None = None` - Only reifiers that rdf:reifies this triple term.
- `predicate: None = None` - Only reifiers that have (reifier, predicate, ?) in the graph.
- `object: None = None` - Only reifiers that have (reifier, ?, object) in the graph.

**Returns:** `Generator[IdentifiedNode, None, None]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.reifiers](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1785-L1831)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-remove"></a>
### `StarLayerGraph.remove`  _(method)_

```python
def remove(self, triple) -> StarLayerGraph
```

Remove a triple matching the pattern. Always returns self, matching
rdflib's own Graph.remove() - including when a TripleTerm in the
pattern is not registered, in which case this is a no-op.

**Parameters:**

- `triple: None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.remove](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1408-L1434)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-remove_reification"></a>
### `StarLayerGraph.remove_reification`  _(method)_

```python
def remove_reification(self, reifier, triple_term=None) -> StarLayerGraph
```

Remove the rdf:reifies triple(s) for the given reifier.

With triple_term=None (default), removes every rdf:reifies triple
the reifier has. Pass a specific triple_term (a TripleTerm, or a
plain (s, p, o) tuple) to unlink only that one reifier<->triple
pair, leaving any other triple(s) the same reifier reifies - and
all of its annotation triples - untouched. Delegates to remove()
(rather than duplicating its native/non-native and TripleTerm
encoding handling here), so a triple_term that isn't registered in
this graph is a safe no-op, same as remove() everywhere else.

**Parameters:**

- `reifier: None` - The reifier node to remove rdf:reifies triple(s) from.
- `triple_term: None = None` - If given, unlink only this triple term; otherwise remove every rdf:reifies triple the reifier has.

**Returns:** `StarLayerGraph` - This graph, matching every other mutating method on this class, so calls can be chained.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.remove_reification](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1987-L2008)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-resolve_imports"></a>
### `StarLayerGraph.resolve_imports`  _(method)_

```python
def resolve_imports(self, *, loader: Callable[[Any], Any | None] | None=None, mode: str='full', target_graph=None) -> StarLayerGraph
```

Follow this graph's own ``owl:imports`` (and, transitively,
whatever each imported graph itself further imports) and merge
the result.

Recursive by construction, not an opt-in extra - that's what
"import" actually means (§3.4's imports closure). Cycle protection:
an IRI already fetched, or a graph whose own ``owl:versionIRI``
already matched something already imported, is never
fetched/merged twice - when a fetched graph declares the IRI it
was fetched under as its own ``owl:versionIRI``, further imports
are followed from that graph's own *base* IRI (the subject of the
``owl:versionIRI`` triple), not the version IRI itself, so
importing a versioned module and importing its unversioned base
both correctly converge on one shared identity for deduplication.
This mirrors ``_resolve_shapes_graph_imports()``'s own
``^owl:versionIRI?/owl:imports`` handling, which this generalizes.

**Parameters:**

- `loader: Callable[[Any], Any | None] | None = None` - Given an import IRI, returns a graph for it, or ``None`` if it can't be resolved (skipped, not an error). ``None`` (the default) means "don't attempt any external resolution at all" - every declared import that isn't already satisfied by ``has_import_locally()`` is then simply skipped, same as an unresolvable one. This is a genuine, safe default, not a relaxation of the "never decide retrieval policy for the caller" rule: it doesn't silently reach anywhere, it just resolves whatever's already co-located in self. For a genuinely external import, this library still never decides on your behalf how to fetch it - that policy is entirely the caller's, via whatever ``loader`` they supply when one is needed.
- `mode: str = 'full'` - Matches ``infer()``'s own three-way ``mode=`` contract exactly: "full" (default) returns a NEW graph with self's own triples plus every resolved import merged in; "delta" returns a NEW graph with only the newly-pulled-in triples (a true set difference against self - anything an import happens to also assert that self already has is not "new"); "in-place" adds just the delta into self directly and returns self. target_graph must not be given together with "in-place" (raises ValueError).
- `target_graph: None = None` - Only meaningful for mode="full"; defaults to a new StarLayerGraph, or if given, entailed triples are added to it (never cleared first) - must be a StarLayerGraph, not a plain rdflib.Graph.

**Returns:** `StarLayerGraph` - A StarLayerGraph: a new graph for mode="full"/"delta", or self for mode="in-place".

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.resolve_imports](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3704-L3838)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-serialize"></a>
### `StarLayerGraph.serialize`  _(method)_

```python
def serialize(self, destination=None, format='turtle12', **kwargs) -> str | bytes | StarLayerGraph
```

Serialize the graph.

**Parameters:**

- `destination: None = None` - A file path/file-like object to write to, or None to return the serialized text instead.
- `format: None = 'turtle12'` - One of: - ``'turtle12'`` (default) — Turtle 1.2 with ``<<( )>>`` triple terms. - ``'longturtle12'`` — Turtle 1.2, one triple per line (no grouping). - ``'nt12'`` — N-Triples 1.2 with ``<<( )>>`` triple terms. - ``'nq12'`` — N-Quads 1.2 (graph name from ``self.identifier``). - ``'trig12'`` — TriG 1.2 (GRAPH block wrapper around Turtle 1.2). - ``'trix12'`` — TriX 1.2 XML (``<graph>`` block with ``<triple>`` elements). - ``'manchester'`` (alias ``'omn'``) — OWL 2 Manchester Syntax; see ``starlayer.graph.serializers.manchester``'s module docstring for the supported subset and known round-tripping limitations. - ``'n3'``/``'n3-12'``/``'text/n3'`` — aliased straight to ``'turtle12'``; only the plain-triples subset N3 shares with Turtle is supported, not real N3 (formulas, ``'=>'`` rules, ``'?x'`` variables) - see ``parse()``'s own note. - Any other format (e.g. ``'turtle'``, ``'xml'``) delegates to rdflib using the internal tt:HASH encoding - triple terms appear as opaque URIRefs.
- `kwargs: None`

**Returns:** `str | bytes | StarLayerGraph` - The serialized text (or bytes, for a format that produces them) when ``destination`` is None; otherwise ``self``, matching rdflib's own ``Graph.serialize()`` contract.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.serialize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2768-L2859)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-skolemize"></a>
### `StarLayerGraph.skolemize`  _(method)_

```python
def skolemize(self, new_graph=None, bnode=None, authority=None, basepath=None) -> StarLayerGraph
```

Convert blank nodes to skolem IRIs, including those inside triple terms.

Overridden because rdflib's inherited skolemize() hardcodes a plain
rdflib.Graph() as the default target - the same bug class as cbd()'s
own (see that method's docstring): it crashes with AssertionError
the moment self contains a real TripleTerm, since plain Graph.add()
rejects it as "not an rdflib term".

**Parameters:**

- `new_graph: None = None` - Graph to add the skolemized triples to; defaults to a new StarLayerGraph.
- `bnode: None = None` - If given, only this BNode is skolemized.
- `authority: None = None` - Authority component of the generated skolem IRIs.
- `basepath: None = None` - Base path component of the generated skolem IRIs.

**Returns:** `StarLayerGraph` - new_graph, populated with the skolemized triples.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.skolemize](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2972-L3002)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-triple_terms"></a>
### `StarLayerGraph.triple_terms`  _(method)_

```python
def triple_terms(self, subject=None, predicate=None, object=None) -> Generator[TripleTerm, None, None]
```

Yield all TripleTerms registered in this graph, with optional filters.

Any combination of subject, predicate, object narrows the results:
    g.triple_terms()                        # all triple terms
    g.triple_terms(predicate=EX.knows)      # all TTs with that predicate
    g.triple_terms(EX.bob, EX.knows, None)  # any TT with that s and p

**Parameters:**

- `subject: None = None` - Only triple terms with this subject.
- `predicate: None = None` - Only triple terms with this predicate.
- `object: None = None` - Only triple terms with this object.

**Returns:** `Generator[TripleTerm, None, None]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.triple_terms](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1913-L1950)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-triples"></a>
### `StarLayerGraph.triples`  _(method)_

```python
def triples(self, triple) -> Generator[tuple, None, None]
```

Iterate triples matching the pattern. Filters internal encoding triples.

TripleTerms in results are returned as TripleTerm objects, not raw URIRefs.
Yields nothing if a TripleTerm in the pattern is not registered in this graph.

Wildcard triple-term patterns - tuples containing None - are supported in
subject and object positions. ``(None, None, None)`` matches any triple
term; ``(EX.alice, None, None)`` matches only triple terms whose subject
is EX.alice. The fan-out is O(k) where k is the number of registered
triple terms that match the pattern.

**Parameters:**

- `triple: None` - The (subject, predicate, object) pattern to match; any position may be None, and subject/object may be a TripleTerm or a wildcard tuple.

**Returns:** `Generator[tuple, None, None]` - A generator of matching (subject, predicate, object) triples.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.triples](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1466-L1522)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-triples_choices"></a>
### `StarLayerGraph.triples_choices`  _(method)_

```python
def triples_choices(self, triple, context=None) -> Generator[tuple, None, None]
```

Iterate triples matching a choices pattern. Filters encoding triples; restores TripleTerms.

Each position may be None (wildcard), a single node, or a list of nodes.
TripleTerms not registered in this graph are silently dropped from lists;
an unregistered single TripleTerm causes the method to yield nothing.

**Parameters:**

- `triple: None` - The (subject, predicate, object) choices pattern.
- `context: None = None` - Passed through to the non-native base implementation.

**Returns:** `Generator[tuple, None, None]` - A generator of matching (subject, predicate, object) triples.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.triples_choices](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L1606-L1630)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-unbind"></a>
### `StarLayerGraph.unbind`  _(method)_

```python
def unbind(self, prefix: str) -> bool
```

Take the binding of ``prefix`` away; True if it was bound. rdflib has no such call: the binding is removed from the
store's own prefix map (in-memory and ``OxigraphStore`` stores; any other raises ``NotImplementedError``, copy with
``reduce_prefixes()`` there). Graphs that share this store lose the prefix too (GitHub issue #44).

**Parameters:**

- `prefix: str`

**Returns:** `bool`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.unbind](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3361-L3367)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-update"></a>
### `StarLayerGraph.update`  _(method)_

```python
def update(self, update_object, processor='sparql', initNs=None, initBindings=None, use_store_provided=True, **kwargs) -> None
```

Execute a SPARQL UPDATE.

For the native rdf-1.2 backend, the update is forwarded to the
endpoint via HTTP unchanged (see
``starlayer.graph.backends.native.native_update``).

Otherwise, SPARQL 1.2 text is parsed via starlayer.sparql's real
grammar (``prepare_update_12``), lowered to a plain SPARQL 1.1
algebra (tt:HASH encoding), and serialized back to real SPARQL 1.1
Update text before executing - every shape (triple-term WHERE
patterns, ground triple terms in INSERT/DELETE DATA, triple terms in
INSERT/DELETE templates) is handled natively by that lowering, with
no post-processing needed here.

Always passes text, never a pre-parsed ``Update`` object, to the
underlying ``Graph.update()``: a remote store's
``SPARQLUpdateStore.update()`` hard-``assert``s on a plain string,
since all it can do is POST text over HTTP, whereas the default
in-memory store's generic processor accepts either.

**Parameters:**

- `update_object: None`
- `processor: None = 'sparql'`
- `initNs: None = None`
- `initBindings: None = None`
- `use_store_provided: None = True`
- `kwargs: None`

**Returns:** `None` - None.

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.update](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L2688-L2766)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-StarLayerGraph-used_prefixes"></a>
### `StarLayerGraph.used_prefixes`  _(method)_

```python
def used_prefixes(self) -> list[tuple[str, URIRef]]
```

The namespace bindings of this graph that matter: ``(prefix, namespace)`` pairs, sorted by prefix, for the namespaces an
IRI of the graph is in (a subject, predicate or object, a literal's datatype, any part of a triple term). The ~29 default
prefixes rdflib binds to every graph, and prefixes the source declared but never used, are left out; ``rdf:type`` as a
predicate does not count, since Turtle writes it ``a``. This is the rule the Turtle writers use to decide which
``@prefix`` lines to write.

**Returns:** `list[tuple[str, URIRef]]`

**Source:** [starlayer.graph.graph.starlayer_graph.StarLayerGraph.used_prefixes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L3369-L3377)

---

<a id="entity-starlayer-sparql-star_query-StarQuery"></a>
### `StarQuery`  _(class)_

A SPARQL query, prepared once, bound with the options
``StarLayerGraph.query()`` otherwise takes per call - run it against as
many graphs as you like via :meth:`run`.

**Source:** [starlayer.sparql.star_query.StarQuery](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/star_query.py#L62-L155)

---

<a id="entity-starlayer-sparql-star_query-StarQuery-run"></a>
### `StarQuery.run`  _(method)_

```python
def run(self, graph: Any, **overrides: Any) -> Result
```

Run the bound query against ``graph``.

Any option bound at construction can be overridden for just this
one call via ``**overrides`` - the bound value itself is never
changed.

**Parameters:**

- `graph: Any` - The graph to query (a ``StarLayerGraph``, or anything else ``StarLayerGraph.query()``'s own ``query_object`` parameter already accepts a prepared ``Query`` against). ``infer``/``engine``/``timeout``/``processor``/``result``/ ``use_store_provided``, overriding the bound value (or ``StarLayerGraph.query()``'s own default) for this call only.
- `overrides: Any`

**Returns:** `Result` - Whatever ``graph.query()`` itself returns for this query.

**Source:** [starlayer.sparql.star_query.StarQuery.run](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/star_query.py#L114-L155)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema"></a>
### `StarShaclSchema`  _(class)_

A SHACL schema: a bound shapes graph plus an optional ontology
graph, to validate, infer rules against, or evaluate node
expressions over any number of data graphs.

``self.shacl_graph``/``self.ont_graph`` are each a reference to
their own separate graph - this class does not itself *hold* triples
the way ``StarLayerGraph`` does. Composition, not inheritance: there
is no real "is-a" relationship available between it and any
existing rdflib/pyshacl class - pySHACL's own main entry point,
``validate()``, is a stateless one-shot function, not a long-lived
object to subclass, and this class unifies several independent
capabilities (``validate``/``apply_rules``/``evaluate``) rather than
specializing any one of them. Construct one per distinct shapes-set
(``PersonSchema = StarShaclSchema(person_shapes)``,
``ProductSchema = StarShaclSchema(product_shapes)``, ...), then call
``validate``/``apply_rules``/``evaluate`` against whatever data graph
you're checking. ``select_widgets`` is the one method that needs no data
graph at all - it chooses SHACL 1.2 UI widgets from the shapes graph alone. Shape-driven subgraph extraction is a separate, plain
function (``starlayer.shacl.extract_subgraph()``), not a method here -
see its own docstring, and the subgraph-extraction guide, for why.

Adds RDF 1.2/triple-term adaptation around pySHACL, which understands
neither triple terms nor SHACL 1.2's own predicates natively.

**Source:** [starlayer.shacl.validator.StarShaclSchema](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L92-L2238)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-apply_rules"></a>
### `StarShaclSchema.apply_rules`  _(method)_

```python
def apply_rules(self, data_graph: Any | None=None, include_source_rule_provenance: bool=False, rule_set: Any | None=None, shapes_graph_resource: Any | None=None, **kwargs: Any) -> RulesResult
```

Executes SHACL rules against ``data_graph``, using this
instance's own bound ``shacl_graph``/``ont_graph``.

Delegates to the module-level :func:`apply_rules`, which holds
the real implementation (mirroring pyshacl's own
``shacl_rules()`` entry point) - this method exists only to
avoid repeating ``shacl_graph``/``ont_graph`` on every call.

**Parameters:**

- `data_graph: Any | None = None` - The data graph to run rules against. Optional - falls back to ``self.data_graph`` (see :meth:`__init__`) if omitted; raises ``ValueError`` if neither is given.
- `include_source_rule_provenance: bool = False` - If ``True``, annotate each rule-produced triple with ``sh:sourceRule`` provenance pointing back at the rule that materialized it.
- `rule_set: Any | None = None` - Optional ``sh:RuleSet`` node (or iterable of them) restricting which rule set(s) actually run, instead of every rule declared in the shapes graph.
- `shapes_graph_resource: Any | None = None` - Selects a named ``sh:ShapesGraph`` module within the bound ``shacl_graph`` to run rules against, or - if the bound ``shacl_graph`` doesn't contain it as a module - is used purely as report-provenance metadata. See :meth:`_resolve_shacl_graph`. ``inference`` may not be passed here - it is always taken from ``self.inference``, bound at construction; passing it raises ``TypeError`` (Python's own "multiple values for keyword argument", since it is already supplied explicitly below).
- `kwargs: Any`

**Returns:** `RulesResult` - The ``RulesResult`` produced by the module-level :func:`apply_rules` call.

**Source:** [starlayer.shacl.validator.StarShaclSchema.apply_rules](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L1747-L1799)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-build_report"></a>
### `StarShaclSchema.build_report`  _(method)_

```python
def build_report(self, *, events: tuple[dict[str, Any], ...], graph_context: Any, options: dict[str, Any] | None=None) -> Any
```

Builds a ``sh:ValidationReport`` graph from component ``events``.

**Parameters:**

- `events: tuple[dict[str, Any], ...]`
- `graph_context: Any`
- `options: dict[str, Any] | None = None`

**Returns:** `Any`

**Source:** [starlayer.shacl.validator.StarShaclSchema.build_report](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L457-L465)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-close_shape"></a>
### `StarShaclSchema.close_shape`  _(method)_

```python
def close_shape(self, shape: Any, *, shapes_graph_resource: Any | None=None) -> Any
```

Returns a closed copy of ``shacl_graph``, closing ``shape`` and
every shape it recursively references.

``shape`` is a node identifier already in this instance's own
``shacl_graph``. Every shape reached in a way that describes a
value node's *complete* property set - ``sh:node``,
``sh:qualifiedValueShape``, every ``sh:and``/``sh:or``/``sh:xone``
member - is closed (``sh:closed true``) with any
``sh:ignoredProperties`` stripped. The original ``shacl_graph`` is
never mutated. See the module-level ``_close_shape`` in
``subgraph_extraction.py`` for the full algorithm/rationale -
turning a shape's normal production form (which often tolerates a
few properties via ``sh:ignoredProperties``) into the strict,
no-exemptions form ``extract_subgraph()``'s acceptance test needs,
without hand-maintaining a second, drift-prone copy of the shape.

Unlike ``validate()``/``apply_rules()``/``evaluate()``, this
doesn't take a ``data_graph`` at all - it operates purely on the
bound ``shacl_graph`` itself.

**Parameters:**

- `shape: Any` - The shape node to close, already present in the bound ``shacl_graph``.
- `shapes_graph_resource: Any | None = None` - Selects a named ``sh:ShapesGraph`` module within the bound ``shacl_graph`` to close against, instead of the whole bound graph. See :meth:`_resolve_shacl_graph`.

**Returns:** `Any` - A closed copy of the relevant ``shacl_graph`` (or module).

**Source:** [starlayer.shacl.validator.StarShaclSchema.close_shape](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L2070-L2110)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-data_graph"></a>
### `StarShaclSchema.data_graph`  _(method)_

```python
def data_graph(self) -> Any | None
```

The bound default data graph (see :attr:`shacl_graph`).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.data_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L238-L240)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-evaluate"></a>
### `StarShaclSchema.evaluate`  _(method)_

```python
def evaluate(self, data_graph: Any | None=None, *, shapes_graph_resource: Any | None=None, focus_nodes: Any | None=None, properties: Any | None=None, rules_entailment: bool=False) -> Any
```

Computes every ``sh:values``-declared virtual property across
``shacl_graph`` and returns the result as a shape-driven subgraph.

A third, independent processing mode alongside ``validate()``
(checks conformance, never mutates) and ``apply_rules()``
(executes ``sh:rule``, materializes real triples). Every focus
node a property shape applies to gets its own real, stored
``sh:path`` values, plus any computed virtual values layered on
top - never the whole of ``data_graph``. The caller's own
``data_graph`` is never mutated, and the returned graph is not
meant to be persisted: SHACL 1.2 Node Expressions' own framing
for virtual values is that they are computed "only on demand",
never creating real triples in the data graph or shapes graph.

This is a genuinely separate concern from ``apply_rules()``, not an
overlapping one: a ``sh:values``-declared virtual property is
invisible to ordinary node-expression path resolution
(``shnex:pathValues``/pySHACL's own ``value_nodes_from_path``) the
same way it's invisible to a plain ``sh:path`` read - a ``sh:rule``
that tries to *read* a virtual property this way finds nothing, and
only ever produces a real triple for that same computation if the
rule *recomputes* it itself via the identical node expression.
``sh:values`` is wired only into ``Shape.value_nodes()`` (pySHACL's
constraint-evaluation path, patched by
``_patch_shape_value_nodes_for_sh_values``), never into rule
execution - so nothing here needs to coordinate with
``apply_rules()`` at all, or worry about double-materializing
anything it already produces.

Only handles a property shape's simple, single-predicate ``sh:path``
(the form every worked example in the spec uses) - a property path
expression (sequence/inverse/etc.) is silently skipped, matching
this module's general "shallow but broad" tolerance elsewhere for
forms not worth a full path-grammar evaluation here.

**Unions with any real, already-stored value for the same
predicate - does not remove or replace it.** SHACL 1.2 Core's own
"Value Nodes of Property Shapes" algorithm is explicit and
unambiguous about this: real path-based values and ``sh:values``-
computed values are both unconditionally *added* to the same set
(only ``sh:defaultValue`` is conditional, on the set still being
empty) - see ``_patch_shape_value_nodes_for_sh_values``'s own
docstring for the exact quoted algorithm. Every property shape with
a real ``sh:path`` is visited for this, not only ones that also
happen to declare ``sh:values``.

**Entailment feeds the whole computation uniformly here** - unlike
``apply_rules()``, where entailment is a pure computational device
that is never persisted into its returned inference graph, this
method deliberately treats entailed triples as ordinary stored
values: SHACL Core's own value-nodes algorithm makes no distinction
between asserted and entailed triples, so neither does this method.

``self.shacl_graph is None`` (this schema was constructed with no
shapes graph of its own) falls back to ``data_graph`` itself as the
source of ``sh:values`` declarations - matching ``validate()``'s
own "data graph doubles as shapes graph" allowance.

**Parameters:**

- `data_graph: Any | None = None` - The data graph to compute virtual values over. Optional - falls back to ``self.data_graph`` if omitted.
- `shapes_graph_resource: Any | None = None` - Selects a named ``sh:ShapesGraph`` module within the bound ``shacl_graph`` to read ``sh:values``/``sh:defaultValue`` declarations from, or is a no-op if the bound ``shacl_graph`` doesn't contain it as a module. See :meth:`_resolve_shacl_graph`. ``inference`` is not a parameter here - it is always taken from ``self.inference``, bound at construction.
- `focus_nodes: Any | None = None` - Restrict evaluation to these focus nodes (an iterable of nodes). ``None`` (the default) evaluates every node the shapes target; a node that is not one of a shape's targets is not evaluated for it. Only the per-node work (reading stored values and computing ``sh:values``/``sh:defaultValue``) is limited; the shapes' own targets are still resolved over ``data_graph``.
- `properties: Any | None = None` - Restrict evaluation to property shapes whose ``sh:path`` is one of these predicates (an iterable of IRIs). ``None`` evaluates every property shape.
- `rules_entailment: bool = False` - Also run the rules the shapes graph names in ``sh:entailment`` (``sh:RulesEntailment`` or a rule set, Inference Rules section 6) before evaluating, as ``validate()`` does, so targets and values that depend on an inferred triple see it. Off by default: evaluating is not validating, and running the rules costs a full ``apply_rules`` pass. The inferred triples are used for the evaluation only and are not in the result unless a property shape reads them.

**Returns:** `Any` - A plain graph: the real, stored values of every property shape with a simple ``sh:path``, for its own target focus nodes, with any ``sh:values``/``sh:defaultValue``-computed values unioned in.

**Source:** [starlayer.shacl.validator.StarShaclSchema.evaluate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L1801-L1996)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-evaluate_component"></a>
### `StarShaclSchema.evaluate_component`  _(method)_

```python
def evaluate_component(self, *, component: Any, focus_node: Any, value_nodes: tuple[Any, ...], options: dict[str, Any] | None=None) -> Any
```

Evaluates one native ``ConstraintComponent`` directly against
``component``/``focus_node``/``value_nodes``.

**Parameters:**

- `component: Any`
- `focus_node: Any`
- `value_nodes: tuple[Any, ...]`
- `options: dict[str, Any] | None = None`

**Returns:** `Any`

**Source:** [starlayer.shacl.validator.StarShaclSchema.evaluate_component](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L438-L455)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-extract_shapes_graph"></a>
### `StarShaclSchema.extract_shapes_graph`  _(method)_

```python
def extract_shapes_graph(self, shapes_graph_iri: Any, *, include_referenced: bool=False) -> Any | None
```

Extracts the ``sh:ShapesGraph``-typed resource named by
``shapes_graph_iri`` as a standalone graph.

``shapes_graph_iri`` must be declared within this instance's own
bound ``shacl_graph``. The inverse of SHACL 1.2 Profiling §2's
packaging convention: rather than reading a single shapes
graph's own self-declared metadata, this pulls one *named*
module back out of a larger graph that bundles several
``sh:ShapesGraph`` modules together side by side.

A shape counts as a member of ``shapes_graph_iri``'s module via
any of the three mechanisms SHACL 1.2 Profiling §2 documents,
and all three are honored here:

- ``<shapes_graph_iri> rdfs:member <Shape>`` - the ShapesGraph
  declares its own members (forward direction).
- ``<Shape> rdfs:isDefinedBy <shapes_graph_iri>`` - a shape
  declares *itself* part of the ShapesGraph (inverse direction).
- ``owl:imports`` - if ``shapes_graph_iri`` imports another
  ``sh:ShapesGraph`` node that's *already present in this same
  ``shacl_graph``*, that other module's own members (via either
  direction above) count as part of this module's result too,
  transitively. Only locally co-located modules are chased, the
  same "no implicit network/loader access" scope
  ``has_import_locally()``/``resolve_imports()`` already
  establish elsewhere - this method takes no ``loader=``
  parameter at all.

  **Unlike the dangling-member case below, an unresolvable
  ``owl:imports`` target raises ``ValueError`` rather than being
  silently skipped** - whether the imported IRI has no triples
  describing it in ``shacl_graph`` at all, or is present but
  simply isn't itself typed ``a sh:ShapesGraph``. A shapes graph
  that declares ``owl:imports`` on a ``sh:ShapesGraph`` node is
  asserting a real dependency on another packaging module, not
  offering optional metadata - call ``resolve_imports(loader=...)``
  on ``shacl_graph`` first if the target genuinely needs fetching
  from elsewhere before extracting.

The result contains every involved ``sh:ShapesGraph`` node's own
Concise Bounded Description (``StarLayerGraph.cbd()`` - its
``rdf:type sh:ShapesGraph``/``rdfs:member``/``owl:imports``
triples, plus anything hanging off it via a blank node) **and**
every member shape's own CBD too - CBD alone on a ShapesGraph
node would include the bare ``rdfs:member`` triples themselves
(each member is an ordinary named IRI, not a blank node, so CBD
doesn't follow it further on its own) but not the member shapes'
own content, which is why each one gets its own explicit CBD call
here, the same way ``sh:property``'s own near-universally-blank-
node shapes already come along for free via CBD's own blank-
node-following behavior.

Deliberately does **not** recurse into a member's own structural
references (``sh:property``/``sh:node``/``sh:qualifiedValueShape``/
etc.) to pull in whatever *named* shape they point at - only each
direct member's own CBD. SHACL 1.2 Profiling itself gives no
completeness rule here at all (§2.7, "Calculating Dependencies,"
is a literal ``TODO`` in the published Working Draft; §2.3-2.5's
``rdfs:member``/``rdfs:isDefinedBy`` language is flat and
non-transitive), so there's no spec basis for choosing a closure
over this narrower scope. A member shape's own named structural
reference is deliberately left dangling if its target isn't
*itself* a direct member too - this lets a caller extract one
shape, then inject their own (possibly different) definition for
whatever it references, without the extraction silently dragging
along a stale copy that would conflict with the injected one.
If the caller wants a fully self-contained, ready-to-validate
module instead, they're responsible for making sure every
referenced named shape is also a declared member (or for
injecting one themselves after extraction) - this method won't
infer it on their behalf.

With ``include_referenced=True`` the result is self-contained: the named shapes the members refer to (and the ones
those refer to, see ``shapes_graphs.referenced_shapes``) are copied too, whether or not another module defines
them, so the result validates on its own. It is off by default, which keeps the behaviour above: the use case
for the default is injecting your own definition of a referenced shape, and a copied definition would conflict with it
(GitHub issue #19).

**Parameters:**

- `shapes_graph_iri: Any` - The IRI of the ``sh:ShapesGraph``-typed resource to extract.
- `include_referenced: bool = False` - Also copy the named shapes the members refer to, transitively.

**Returns:** `Any | None` - A standalone graph containing just that resource's module, or ``None`` if ``shapes_graph_iri`` isn't actually typed ``a sh:ShapesGraph`` in ``shacl_graph`` at all - not every graph bothers with this optional packaging metadata, and a typo'd IRI shouldn't silently return an empty-but-valid-looking graph.

**Source:** [starlayer.shacl.validator.StarShaclSchema.extract_shapes_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L2112-L2238)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-ont_graph"></a>
### `StarShaclSchema.ont_graph`  _(method)_

```python
def ont_graph(self) -> Any | None
```

The bound ontology graph (see :attr:`shacl_graph`).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.ont_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L229-L231)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-scoring_graph"></a>
### `StarShaclSchema.scoring_graph`  _(method)_

```python
def scoring_graph(self) -> Any | None
```

The bound widget scoring catalog (see :attr:`shacl_graph`).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.scoring_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L247-L249)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-select_widgets"></a>
### `StarShaclSchema.select_widgets`  _(method)_

```python
def select_widgets(self, *, shape_node: Any, focus_node: Any | None=None, role: str, data_graph: Any | None=None, scoring_graph: Any | None=None, shapes_graph_resource: Any | None=None, per: str='node') -> dict[Any, Any]
```

Chooses a SHACL 1.2 UI widget for each property of the node
shape ``shape_node``, using this instance's own bound
``shacl_graph`` as the shapes graph.

Delegates to
:func:`starlayer.shacl.ui_widget_selection.select_widgets`, which
holds the real implementation and its full semantics - this method
only supplies the bound shapes graph, the bound ``scoring_graph``
and (when a ``focus_node`` is given) the bound ``data_graph``, so
none of them is repeated per call. Each can be overridden per call.

**Parameters:**

- `shape_node: Any` - A ``sh:NodeShape`` in the shapes graph; its ``sh:property`` list is what is walked.
- `focus_node: Any | None = None` - Optional node whose data a matcher's ``shui:dataGraphShape`` is checked against.
- `role: str` - ``"editor"`` or ``"viewer"``.
- `data_graph: Any | None = None` - The graph holding ``focus_node``. Falls back to ``self.data_graph``; only needed (and only required) when ``focus_node`` is given.
- `scoring_graph: Any | None = None` - Optional catalog of ``shui:WidgetScore`` / ``shui:WidgetAcceptMatcher`` entries. Falls back to ``self.scoring_graph``; to ignore a bound catalog for one call, pass an empty graph.
- `shapes_graph_resource: Any | None = None` - Selects a named ``sh:ShapesGraph`` module within the bound ``shacl_graph``, as for :meth:`apply_rules`.
- `per: str = 'node'` - ``"node"`` (the default) or ``"shape"``. ``"shape"`` answers once per property shape and returns a ``WidgetChoice`` for each, to finish per node with ``choice.resolve(focus_node, data_graph)``; see :func:`starlayer.shacl.ui_widget_selection.select_widgets`.

**Returns:** `dict[Any, Any]` - ``{property_shape: widget}``, with ``None`` for a property that has no widget (or ``{property_shape: WidgetChoice}`` for ``per="shape"``).

**Source:** [starlayer.shacl.validator.StarShaclSchema.select_widgets](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L1998-L2068)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-shacl_graph"></a>
### `StarShaclSchema.shacl_graph`  _(method)_

```python
def shacl_graph(self) -> Any | None
```

The bound shapes graph, as a ``StarLayerGraph``: the caller's own object when it is one, otherwise a fresh
conversion of the current content of the graph passed in.

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.shacl_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L219-L222)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-target_nodes"></a>
### `StarShaclSchema.target_nodes`  _(method)_

```python
def target_nodes(self, *, data_graph: Any | None=None, shape_node: Any, shapes_graph_resource: Any | None=None) -> tuple[Any, ...]
```

Return the tuple of nodes this shape targets.

``data_graph`` is optional, falling back to ``self.data_graph``;
``inference`` is not a per-call parameter here - this instance's
own bound ``self.inference`` is always used instead (see
``__init__``'s own docstring). Also threads this instance's own
``self.ont_graph`` through, matching every other method on this
class - see ``engine.target_nodes()``'s own docstring for the
full entailment design.

**Parameters:**

- `data_graph: Any | None = None` - The data graph to resolve targets against, or ``None`` to use ``self.data_graph``.
- `shape_node: Any` - The shape whose targets to resolve.
- `shapes_graph_resource: Any | None = None` - A named ``sh:ShapesGraph`` module's IRI to resolve ``shape_node`` within - see :meth:`_resolve_shacl_graph`.

**Returns:** `tuple[Any, ...]` - The tuple of target nodes.

**Source:** [starlayer.shacl.validator.StarShaclSchema.target_nodes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L401-L436)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-validate"></a>
### `StarShaclSchema.validate`  _(method)_

```python
def validate(self, data_graph: Any | None=None, *, mode: str | ValidationMode | None=None, decode_report: bool=True, rdfs_subclass_reasoning_includes_shapes_graph: bool=False, shapes_graph_loader: Callable[[Any], Any | None] | None=None, ignore_imports: bool=False, meta_shapes_extra: Iterable[Any]=(), data_graph_iri: Any | None=None, shapes_graph_resource: Any | None=None, include_used_configuration: bool=False, **kwargs: Any) -> ValidationResult
```

Validate ``data_graph`` against this schema's bound
``shacl_graph``/``ont_graph``, with RDF 1.2/triple-term adaptation
and the SHACL 1.2 Core/Node-Expressions/Profiling patches this
module applies around pySHACL.

**Parameters:**

- `data_graph: Any | None = None` - The data graph to validate. Optional, falling back to ``self.data_graph`` (see ``__init__``'s own docstring) when omitted.
- `mode: str | ValidationMode | None = None` - A validator option preset (``"validation"``/``"rules"``/ ``"debug"``, or a ``ValidationMode``) resolved via ``resolve_mode_options()``; any of pySHACL's own options (e.g. ``advanced``, ``inplace``, ``meta_shacl``, ``allow_warnings``, ``allow_infos``) can be overridden through ``**kwargs``.
- `decode_report: bool = True` - Whether to decode the raw pySHACL report graph back through the triple-term adapter (and humanize its report text) before returning it. ``False`` returns the adapter-encoded report as pySHACL produced it.
- `rdfs_subclass_reasoning_includes_shapes_graph: bool = False` - Whether ``sh:rootClass``'s own ``rdfs:subClassOf`` reasoning should also consult the shapes graph's own ``rdfs:subClassOf`` triples, not just the data graph's - SHACL 1.2 Core's "SHACL Type" definition explicitly allows this to be implementation-parameterized. When enabled, the shapes graph's own ``rdfs:subClassOf`` triples are injected into a copy of ``data_graph`` handed to pySHACL (the only channel available, since pySHACL constructs the ``sh:rootClass`` component itself with no room for extra constructor arguments) and removed again afterward.
- `shapes_graph_loader: Callable[[Any], Any | None] | None = None` - Resolves one ``owl:imports`` target IRI to the graph it names, or ``None`` if it can't be resolved - used to follow ``shacl_graph``'s own ``owl:imports`` (optionally redirected through ``owl:versionIRI``) before validating. This library never decides retrieval policy on its own, so no loader is used unless one is given.
- `ignore_imports: bool = False` - If ``shacl_graph`` declares ``owl:imports`` that aren't already locally satisfied (see ``has_import_locally()``) and no ``shapes_graph_loader`` was given, ``validate()`` raises ``ValueError`` by default rather than silently proceeding with a possibly incomplete shapes graph. Pass ``True`` to opt out explicitly - e.g. because the imports were already resolved into ``shacl_graph`` beforehand (``resolve_imports()`` doesn't strip the ``owl:imports`` triple once resolved, so its mere presence can't otherwise distinguish "already handled" from "genuinely missing").
- `meta_shapes_extra: Iterable[Any] = ()` - Extra graphs merged into the meta-shapes graph used for the ``meta_shacl=True`` preflight check (see ``starlayer.shacl.meta_shapes``). Ignored unless ``meta_shacl`` is enabled via ``mode``/``**kwargs``.
- `data_graph_iri: Any | None = None` - The data graph's identity, recorded on the report as ``sh:usedDataGraph``. Falls back to ``data_graph.identifier`` when that's a real ``URIRef`` (not the random ``BNode`` every plain ``rdflib.Graph`` otherwise gets) and this is left ``None``.
- `shapes_graph_resource: Any | None = None` - One value with two possible meanings, depending on what's actually true of this instance's own bound ``shacl_graph`` - see ``_resolve_shapes_graph_and_provenance()``'s own docstring for the full design. If it names a real ``a sh:ShapesGraph`` module within ``shacl_graph``, that module alone is validated against, and its own IRI becomes the report's ``sh:usedShapesGraph`` identity. If ``shacl_graph`` is bound but doesn't contain it as a module, it's used purely as the report's ``sh:usedShapesGraph`` identity, and the whole bound ``shacl_graph`` is validated against unchanged. Raises if given with no bound ``shacl_graph`` at all. Falls back to ``shacl_graph.identifier`` the same way ``data_graph_iri`` falls back to ``data_graph.identifier``, when left ``None``.
- `include_used_configuration: bool = False` - Whether to also record the resolved validator options (``mode``, ``rdfs_subclass_reasoning_includes_shapes_graph``, etc.) on the report. overrides=kwargs)`` as option overrides on top of whatever ``mode`` preset resolves to (e.g. ``advanced``, ``inplace``, ``meta_shacl``, ``allow_warnings``, ``allow_infos``). ``inference=`` is rejected with ``TypeError`` here - it's bound once at construction instead (``StarShaclSchema(inference=...)``); construct a second ``StarShaclSchema`` for a different regime.
- `kwargs: Any`

**Returns:** `ValidationResult` - A ``ValidationResult`` with ``conforms``, ``report_graph``, ``report_text``, ``data_graph`` (the mutated data graph when ``inplace`` is enabled in the resolved options, else ``None``), and ``diagnostics``.

**Source:** [starlayer.shacl.validator.StarShaclSchema.validate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L467-L997)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-validate_each"></a>
### `StarShaclSchema.validate_each`  _(method)_

```python
def validate_each(self, data_graphs: Iterable[Any] | None=None, **kwargs: Any) -> dict[int, ValidationResult]
```

Validate each of ``data_graphs`` independently against this
instance's own bound ``shacl_graph``/``ont_graph``, mirroring
pyshacl's own ``validate_each(data_graphs, ...)`` entry point.

Implemented as a loop calling :meth:`validate` once per data graph,
rather than driving pyshacl's own ``validate_each``/multi-data-graph
path directly: that path knows nothing about RDF 1.2 triple terms,
SHACL 1.2's new predicates, or any of this project's other runtime
patches, so using it would silently run a different, unpatched
pipeline per graph instead of the one real ``validate()`` path this
class otherwise always goes through.

**Parameters:**

- `data_graphs: Iterable[Any] | None = None` - The data graphs to validate, each independently. ``None`` falls back to a single-element ``(self.data_graph,)`` - :meth:`validate` itself raises if that is also ``None``, so no separate check is needed here. (e.g. ``shapes_graph_resource``, ``mode``, ``inference``).
- `kwargs: Any`

**Returns:** `dict[int, ValidationResult]` - A dict mapping each data graph's index in ``data_graphs`` to its own :class:`ValidationResult` - this project's own richer result type, not pyshacl's bare ``dict[int, (conforms, report_graph, report_text)]`` tuple, the same "wrap the tuple" convention :meth:`validate` itself already follows.

**Source:** [starlayer.shacl.validator.StarShaclSchema.validate_each](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L999-L1033)

---

## `starlayer.graph`

[Back to overview](api-overview.generated.md#starlayergraph)

<a id="entity-starlayer-graph-rdfc-CanonicalizationComplexityError"></a>
### `CanonicalizationComplexityError`  _(class)_

Raised when canonicalizing would require exploring more permutations
than the configured budget.

The RDFC-1.0 spec's own required defense against "Dataset Poisoning"
(section 7.1): "Implementations MUST defend against potential
denial-of-service attacks by raising suitable exceptions and
terminating early." Confirmed live that without this, the official
test suite's own poisoning fixture (test074, a 10-node blank-node
clique) hangs indefinitely rather than raising anything.

**Source:** [starlayer.graph.rdfc.CanonicalizationComplexityError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc.py#L82-L91)

---

<a id="entity-starlayer-graph-model-dirlangstring-DirLangString"></a>
### `DirLangString`  _(class)_

An RDF 1.2 directional language-tagged string literal.

Value-typed: two instances with the same (value, language, direction) are
equal and have the same hash. Per RDF 1.2 Concepts sec 3.4.1, a language
tag's case does not participate in the abstract syntax - it is folded to
lowercase here, mirroring rdflib.Literal's existing behaviour for lang=.

**Source:** [starlayer.graph.model.dirlangstring.DirLangString](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/dirlangstring.py#L26-L67)

---

<a id="entity-starlayer-graph-model-dirlangstring-DirLangString-n3"></a>
### `DirLangString.n3`  _(method)_

```python
def n3(self, namespace_manager=None) -> str
```

Returns the N3/Turtle-1.2 (``"text"@lang--dir``) text form.

**Parameters:**

- `namespace_manager: None = None`

**Returns:** `str`

**Source:** [starlayer.graph.model.dirlangstring.DirLangString.n3](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/dirlangstring.py#L59-L61)

---

<a id="entity-starlayer-graph-model-triple-TripleTerm"></a>
### `TripleTerm`  _(class)_

An RDF 1.2 triple term — a triple used as a resource.

Value-typed: two instances with the same (s, p, o) are equal and have the
same hash. A plain Python 3-tuple is coerced to TripleTerm wherever the
StarLayerGraph API expects a node.

_namespace_manager is set by StarLayerGraph._restore() when returning a
TripleTerm from a query result so that __str__ can emit prefixed names.
It is excluded from equality and hashing.

**Source:** [starlayer.graph.model.triple.TripleTerm](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/triple.py#L10-L109)

---

<a id="entity-starlayer-graph-model-triple-TripleTerm-n3"></a>
### `TripleTerm.n3`  _(method)_

```python
def n3(self, namespace_manager=None)
```

Returns the N3/Turtle-1.2 (``<<( s p o )>>``) text form.

**Parameters:**

- `namespace_manager: None = None`

**Source:** [starlayer.graph.model.triple.TripleTerm.n3](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/triple.py#L86-L89)

---

<a id="entity-starlayer-graph-parsers-errors-Turtle12SyntaxError"></a>
### `Turtle12SyntaxError`  _(class)_

Malformed Turtle 1.2 input that the parser cannot recognize as any
valid token or statement form.

**Source:** [starlayer.graph.parsers.errors.Turtle12SyntaxError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/parsers/errors.py#L19-L56)

---

<a id="entity-starlayer-graph-graph-starlayer_graph-can_resolve_import"></a>
### `can_resolve_import`  _(function)_

```python
def can_resolve_import(iri: Any, *, loader: Callable[[Any], Any | None]) -> bool
```

Returns whether ``loader`` can resolve ``iri``.

A question about the *loader*'s own knowledge, not about any
particular graph's data, which is why this is a plain function
rather than a ``StarLayerGraph`` method the way
``owl_imports()``/``resolve_imports()`` are.

Implemented the only honest way this can be answered: by actually
calling ``loader(iri)`` and checking whether it returned a graph
instead of ``None``. For a loader that only ever consults an
already-known local registry (e.g. ``starontology``'s own), this is
free - a dict lookup. For a loader that makes a real network
request, this has the *exact same* cost and side effects as actually
resolving would - there is no cheaper way to ask "would this work"
short of trying it, since only the loader itself knows what it can
reach.

**Parameters:**

- `iri: Any` - The import target to test.
- `loader: Callable[[Any], Any | None]` - Resolves an IRI to a graph, or ``None`` if it can't.

**Returns:** `bool` - True if ``loader(iri)`` returns a graph rather than ``None``.

**Source:** [starlayer.graph.graph.starlayer_graph.can_resolve_import](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/starlayer_graph.py#L130-L155)

---

<a id="entity-starlayer-graph-compare-graph_diff"></a>
### `graph_diff`  _(function)_

```python
def graph_diff(g1: Any, g2: Any)
```

RDF-1.2-aware replacement for ``rdflib.compare.graph_diff``.

Operates on (and returns) the *decomposed* graphs - the returned
"in first only"/"in second only" graphs describe differences in terms of
the synthetic reification fragments, not the original triple terms, so
this is meant for programmatic use (e.g. ``len(in_first) == 0``), not for
display back to a user.

Raises:
    TypeError: for a dataset (a diff of named graphs is not defined
        here; use ``isomorphic()`` or ``rdfc.to_canonical_nquads``).

**Parameters:**

- `g1: Any`
- `g2: Any`

**Source:** [starlayer.graph.compare.graph_diff](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/compare.py#L238-L252)

---

<a id="entity-starlayer-graph-compare-isomorphic"></a>
### `isomorphic`  _(function)_

```python
def isomorphic(graph1: Any, graph2: Any) -> bool
```

RDF-1.2-aware replacement for ``rdflib.compare.isomorphic`` - correct
for graphs containing triple terms (including ones with nested blank
nodes), identical to the original for graphs that don't. Also RDF
1.1-correct for simple-literal-vs-explicit-``xsd:string`` (see module
docstring): a plain ``Literal("x")`` and ``Literal("x", datatype=XSD.string)``
compare equal here, unlike in plain ``rdflib.compare.isomorphic``.

Datasets (``Dataset``, ``ConjunctiveGraph``, ``StarLayerDataset``) are
compared as datasets: equal canonical N-Quads (RDFC-1.0), so graph names
count. A dataset and a plain graph are compared as the dataset's quads
against the graph's triples (default graph only).

**Parameters:**

- `graph1: Any`
- `graph2: Any`

**Returns:** `bool`

**Source:** [starlayer.graph.compare.isomorphic](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/compare.py#L211-L235)

---

<a id="entity-starlayer-graph-query-sparql_api-parseQuery"></a>
### `parseQuery`  _(function)_

```python
def parseQuery(q: str) -> ParseResults
```

Parse a SPARQL 1.2 SELECT/ASK/CONSTRUCT/DESCRIBE query string.

A leading ``VERSION "label"`` prologue directive (SPARQL 1.2 Query sec
4.3) is stripped first - not real SPARQL grammar at all, same handling
``StarLayerGraph.query()`` already gives it (see
``version_directive.py``'s own module docstring).

**Parameters:**

- `q: str` - The SPARQL 1.2 query string to parse.

**Returns:** `ParseResults` - A pyparsing ``ParseResults`` tree — same type as ``rdflib.plugins.sparql.parser.parseQuery`` — with genuine ``TripleTermNode`` nodes wherever ``<<( s p o )>>``/ ``TRIPLE(s, p, o)`` appears, constructed directly by the grammar (see module docstring), not reassembled from a text-level encoding.

**Source:** [starlayer.graph.query.sparql_api.parseQuery](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/query/sparql_api.py#L62-L86)

---

<a id="entity-starlayer-graph-query-sparql_api-parseUpdate"></a>
### `parseUpdate`  _(function)_

```python
def parseUpdate(q: str) -> CompValue
```

Parse a SPARQL 1.2 Update request string.

A leading ``VERSION "label"`` directive is stripped first - see
``parseQuery``'s own docstring.

**Parameters:**

- `q: str` - The SPARQL 1.2 update request string to parse.

**Returns:** `CompValue` - An rdflib ``CompValue`` — same type as ``rdflib.plugins.sparql.parser.parseUpdate`` — with genuine ``TripleTermNode`` nodes preserved (same strategy as ``parseQuery``).

**Source:** [starlayer.graph.query.sparql_api.parseUpdate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/query/sparql_api.py#L120-L140)

---

<a id="entity-starlayer-graph-query-sparql_api-prepareQuery"></a>
### `prepareQuery`  _(function)_

```python
def prepareQuery(queryString: str, initNs=None, base=None) -> Query
```

Parse and translate a SPARQL 1.2 query string to an rdflib ``Query`` object.

The compiled algebra is plain SPARQL 1.1 (triple terms lowered to
starlayer.graph's own ``tt:`` content-addressed encoding); the lowering is
transparent at execution time.

A leading ``VERSION "label"`` directive is stripped first - see
``parseQuery``'s own docstring.

**Parameters:**

- `queryString: str` - The SPARQL 1.2 query string to parse and compile.
- `initNs: None = None` - Optional namespace prefix bindings, as accepted by ``rdflib.plugins.sparql.prepareQuery``.
- `base: None = None` - Optional base IRI for relative-IRI resolution.

**Returns:** `Query` - A compiled, directly executable ``Query`` object, usable with ``StarLayerGraph.query()`` or ``rdflib.Graph.query()``.

**Source:** [starlayer.graph.query.sparql_api.prepareQuery](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/query/sparql_api.py#L89-L117)

---

<a id="entity-starlayer-graph-query-sparql_api-prepareUpdate"></a>
### `prepareUpdate`  _(function)_

```python
def prepareUpdate(updateString: str, initNs=None, base=None) -> Update
```

Parse and translate a SPARQL 1.2 Update request string to an rdflib ``Update`` object.

The compiled form is plain SPARQL 1.1, same lowering as ``prepareQuery``.

A leading ``VERSION "label"`` directive is stripped first - see
``parseQuery``'s own docstring.

**Parameters:**

- `updateString: str` - The SPARQL 1.2 update request string to parse and compile.
- `initNs: None = None` - Optional namespace prefix bindings, as accepted by ``rdflib.plugins.sparql.prepareUpdate``.
- `base: None = None` - Optional base IRI for relative-IRI resolution.

**Returns:** `Update` - A compiled, directly executable ``Update`` object, usable with ``StarLayerGraph.update()`` or ``rdflib.Graph.update()``.

**Source:** [starlayer.graph.query.sparql_api.prepareUpdate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/query/sparql_api.py#L143-L170)

---

<a id="entity-starlayer-graph-query-sparql_api-processUpdate"></a>
### `processUpdate`  _(function)_

```python
def processUpdate(graph, updateString: str, initBindings=None, initNs=None, base=None) -> None
```

Execute a SPARQL 1.2 Update against a graph.

This is the SPARQL 1.2-aware replacement for
``rdflib.plugins.sparql.processUpdate``. The rdflib original calls
``parseUpdate()`` directly, bypassing any ``graph.update()`` override.

For ``StarLayerGraph``/``StarLayerDataset`` instances, this delegates
the *original* SPARQL 1.2 text straight to ``graph.update()`` so that
graph's own full update pipeline runs unmodified (registry rebuild,
``_invalidate_callback``, native-backend routing, INSERT/DELETE
template-position triple-term handling — all of which is specific to
those classes' own ``.update()``, not something to reimplement or
bypass here). For a plain ``rdflib.Graph`` (which has no notion of
SPARQL 1.2 syntax at all), ``updateString`` is first compiled via this
module's own ``prepareUpdate`` into a directly executable, already-
SPARQL-1.1 ``Update`` object, then handed to ``graph.update()`` — the
same general entry point, not the more narrowly-typed
``rdflib.plugins.sparql.processUpdate`` function, since ``Graph.update()``
already accepts a prepared object or text uniformly.

Checks via attribute (``_tt_registry``/``_sg_cache``) rather than
``isinstance`` to avoid a circular import.

**Parameters:**

- `graph: None` - The graph to update - a ``StarLayerGraph``/ ``StarLayerDataset`` or a plain ``rdflib.Graph``.
- `updateString: str` - The SPARQL 1.2 update request string, or an already- prepared ``Update`` object.
- `initBindings: None = None` - Optional initial variable bindings.
- `initNs: None = None` - Optional namespace prefix bindings.
- `base: None = None` - Optional base IRI for relative-IRI resolution.

**Returns:** `None`

**Source:** [starlayer.graph.query.sparql_api.processUpdate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/query/sparql_api.py#L173-L220)

---

<a id="entity-starlayer-graph-rdfc-rdfc10_hash"></a>
### `rdfc10_hash`  _(function)_

```python
def rdfc10_hash(graph: Any, hash_algorithm: str='sha256', permutation_budget: int=_DEFAULT_PERMUTATION_BUDGET) -> str
```

Returns a single hex digest for ``graph``'s canonical N-Quads form.

The portable, spec-compliant equivalent of
``starlayer.graph.compare.to_canonical_hash()`` (which uses rdflib's
own, different digest algorithm and returns a plain Python ``int``,
not a hex string).

**Parameters:**

- `graph: Any`
- `hash_algorithm: str = 'sha256'`
- `permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET`

**Returns:** `str`

**Source:** [starlayer.graph.rdfc.rdfc10_hash](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc.py#L401-L410)

---

<a id="entity-starlayer-graph-serializers-turtle12-serialize_longturtle12"></a>
### `serialize_longturtle12`  _(function)_

```python
def serialize_longturtle12(graph, base=None) -> str
```

Serialize a StarLayerGraph to longturtle 1.2 — one triple per line.

Identical to turtle12 but with no subject/predicate grouping: every triple
is emitted as ``s p o .`` on its own line.  Prefix declarations and the
``@version`` directive are emitted the same way as turtle12.

**Parameters:**

- `graph: None` - The graph to serialize - a StarLayerGraph, or a plain rdflib.Graph wrapped via StarLayerGraph.from_rdflib().
- `base: None = None`

**Returns:** `str` - The longturtle 1.2 serialization of graph.

**Source:** [starlayer.graph.serializers.turtle12.serialize_longturtle12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/turtle12.py#L829-L895)

---

<a id="entity-starlayer-graph-serializers-ntriples12-serialize_nquads12"></a>
### `serialize_nquads12`  _(function)_

```python
def serialize_nquads12(g, graph_uri=None, _include_header: bool=True) -> str
```

Serialize a StarLayerGraph to N-Quads 1.2 text.

One quad per line: ``subject predicate object graph .``
If *graph_uri* is None the graph's own identifier is used.

**Parameters:**

- `g: None` - The StarLayerGraph to serialize.
- `graph_uri: None = None` - The term to use as each quad's graph name. Defaults to g's own identifier. A BNode value (the default for an unnamed graph) is treated as the default graph - no graph term is emitted, and the output is N-Triples-shaped quads-without-a- graph-term.
- `_include_header: bool = True` - Whether to emit the leading ``VERSION "1.2"`` header when the graph's content requires it.

**Returns:** `str` - The N-Quads 1.2 serialization of g.

**Source:** [starlayer.graph.serializers.ntriples12.serialize_nquads12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/ntriples12.py#L132-L168)

---

<a id="entity-starlayer-graph-serializers-ntriples12-serialize_ntriples12"></a>
### `serialize_ntriples12`  _(function)_

```python
def serialize_ntriples12(g) -> str
```

Serialize a StarLayerGraph to N-Triples 1.2 text.

One triple per line: ``subject predicate object .``
Triple terms are written as ``<<( s p o )>>``.

**Parameters:**

- `g: None` - The StarLayerGraph to serialize.

**Returns:** `str` - The N-Triples 1.2 serialization of g.

**Source:** [starlayer.graph.serializers.ntriples12.serialize_ntriples12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/ntriples12.py#L113-L129)

---

<a id="entity-starlayer-graph-serializers-rdfxml12-serialize_rdfxml12"></a>
### `serialize_rdfxml12`  _(function)_

```python
def serialize_rdfxml12(graph) -> str
```

Serialize a StarLayerGraph to RDF/XML 1.2 text.

Triple terms in object position → ``rdf:parseType="Triple"`` wrapping a
single ``<rdf:Description>`` (RDF 1.2 XML Syntax sec 2.19). Reification is
the ordinary ``rdf:reifies`` predicate with a triple-term-valued object -
the same "formal pattern" used as the canonical form everywhere else in
this codebase, not the ``rdf:annotation``/``rdf:annotationNodeID``
shorthand (which the parser accepts for reading, but this serializer
never emits).

**Parameters:**

- `graph: None` - The graph to serialize - a StarLayerGraph, or a plain rdflib.Graph wrapped via StarLayerGraph.from_rdflib().

**Returns:** `str` - The RDF/XML 1.2 serialization of graph.

**Source:** [starlayer.graph.serializers.rdfxml12.serialize_rdfxml12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/rdfxml12.py#L149-L177)

---

<a id="entity-starlayer-graph-serializers-trig12-serialize_trig12"></a>
### `serialize_trig12`  _(function)_

```python
def serialize_trig12(g, base=None) -> str
```

Serialize *g* to TriG 1.2 text.

Named graph identifier → ``GRAPH <uri> { ... }``
BNode identifier        → plain Turtle 1.2 (default graph in TriG)

**Parameters:**

- `g: None` - The graph to serialize.
- `base: None = None` - A base IRI: written as ``@base``, IRIs under it are written relative to it.

**Returns:** `str` - The TriG 1.2 serialization of g.

**Source:** [starlayer.graph.serializers.trig12.serialize_trig12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/trig12.py#L47-L83)

---

<a id="entity-starlayer-graph-serializers-trix12-serialize_trix12"></a>
### `serialize_trix12`  _(function)_

```python
def serialize_trix12(g) -> str
```

Serialize a StarLayerGraph to TriX 1.2 XML text.

Named graph identifier → <uri> as first child of <graph>.
BNode identifier        → anonymous <graph> (default/unnamed graph).
Triple terms emitted as a nested <triple> (Jena convention), not a
distinct <tripleTerm> tag.

**Parameters:**

- `g: None` - The StarLayerGraph to serialize.

**Returns:** `str` - The TriX 1.2 XML serialization of g.

**Source:** [starlayer.graph.serializers.trix12.serialize_trix12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/trix12.py#L106-L131)

---

<a id="entity-starlayer-graph-serializers-trix12-serialize_trix12_dataset"></a>
### `serialize_trix12_dataset`  _(function)_

```python
def serialize_trix12_dataset(ds) -> str
```

Serialize a StarLayerDataset to TriX 1.2 XML text.

Each non-empty named graph becomes a separate <graph> block.

**Parameters:**

- `ds: None` - The StarLayerDataset to serialize.

**Returns:** `str` - The TriX 1.2 XML serialization of ds.

**Source:** [starlayer.graph.serializers.trix12.serialize_trix12_dataset](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/trix12.py#L134-L163)

---

<a id="entity-starlayer-graph-serializers-turtle12-serialize_turtle12"></a>
### `serialize_turtle12`  _(function)_

```python
def serialize_turtle12(graph, base=None) -> str
```

Serialize a StarLayerGraph or rdflib.Graph (with SL encoding) to Turtle 1.2 (see ``render_turtle12``).

**Parameters:**

- `graph: None`
- `base: None = None`

**Returns:** `str`

**Source:** [starlayer.graph.serializers.turtle12.serialize_turtle12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/serializers/turtle12.py#L623-L625)

---

<a id="entity-starlayer-graph-compare-to_canonical_hash"></a>
### `to_canonical_hash`  _(function)_

```python
def to_canonical_hash(graph: Any) -> int
```

A single canonical digest for ``graph``, stable under blank-node
relabeling and correct for triple terms (including nested blank nodes).

Not yet a spec-compliant RDFC-1.0 digest (see module docstring) - two
graphs get equal digests here if and only if ``isomorphic()`` (this
module's version) says they're isomorphic, which is the property this
is actually needed for today; ``rdfc.rdfc10_hash`` is the portable,
standards-compliant digest. For a dataset the digest is the RDFC-1.0
hash read as an integer.

**Parameters:**

- `graph: Any`

**Returns:** `int`

**Source:** [starlayer.graph.compare.to_canonical_hash](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/compare.py#L267-L282)

---

<a id="entity-starlayer-graph-rdfc-to_canonical_nquads"></a>
### `to_canonical_nquads`  _(function)_

```python
def to_canonical_nquads(graph: Any, hash_algorithm: str='sha256', permutation_budget: int=_DEFAULT_PERMUTATION_BUDGET) -> str
```

The canonical N-Quads serialization of ``graph`` (spec section 5),
correct for triple terms and directional language strings.

``graph`` is decomposed first (triple terms unstarred into synthetic
blank-node reification, directional language strings re-encoded) - see
module and ``starlayer.graph.compare`` docstrings.

**Parameters:**

- `graph: Any`
- `hash_algorithm: str = 'sha256'`
- `permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET`

**Returns:** `str`

**Source:** [starlayer.graph.rdfc.to_canonical_nquads](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc.py#L375-L398)

---

<a id="entity-starlayer-graph-compare-to_isomorphic"></a>
### `to_isomorphic`  _(function)_

```python
def to_isomorphic(graph: Any)
```

RDF-1.2-aware replacement for ``rdflib.compare.to_isomorphic`` -
doesn't crash on a triple-term-valued term. Returns an
``IsomorphicGraph`` over the *decomposed* graph (see module docstring);
use ``to_canonical_hash()`` if you just want a single digest value.

Raises:
    TypeError: for a dataset (use ``rdfc.to_canonical_nquads``).

**Parameters:**

- `graph: Any`

**Source:** [starlayer.graph.compare.to_isomorphic](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/compare.py#L255-L264)

---

<a id="entity-starlayer-graph-graph-prefixes-used_prefixes"></a>
### `used_prefixes`  _(function)_

```python
def used_prefixes(graph: Any) -> list[tuple[str, URIRef]]
```

The prefixes of a graph or dataset that are in use, as ``(prefix, namespace)`` pairs sorted by prefix.

Use it for a graph that arrives with rdflib's default prefixes bound, to offer or write only the ones that matter. A prefix the
file declared but never used is not returned (the writers drop it as well). This is what the Turtle 1.2 writer writes as
``@prefix`` lines (it is the writer's own answer, so the two cannot disagree: ``rdf:reifies`` folded into ``{| |}`` or ``~``,
``rdf:first`` / ``rdf:rest`` folded into ``( )`` and a bare ``1`` do not make ``rdf`` or ``xsd`` count; a prefix that is not a
valid ``PN_PREFIX`` is shown as the ``pfxN`` the writer renames it to). For a dataset the triples of every graph count, and so do
the names of the named graphs, so the answer is the prefixes the whole dataset needs.

**Parameters:**

- `graph: Any`

**Returns:** `list[tuple[str, URIRef]]`

**Source:** [starlayer.graph.graph.prefixes.used_prefixes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/graph/prefixes.py#L69-L95)

---

## `starlayer.sparql`

[Back to overview](api-overview.generated.md#starlayersparql)

<a id="entity-starlayer-sparql-parse12-prepare_query_12"></a>
### `prepare_query_12`  _(function)_

```python
def prepare_query_12(text: str, base: str | None=None, initNs: Mapping[str, Any] | None=None) -> Query
```

Parses and translates SPARQL 1.2 query text into a real,
executable-shaped rdflib ``Query``.

``query.algebra`` contains genuine ``TripleTermNode`` nodes in
triple-pattern position, not a lowered SPARQL-1.1-equivalent shape.

``base``/``initNs`` are threaded straight through to ``translateQuery``
— same two parameters, same precedence, as plain rdflib's own
``prepareQuery(queryString, initNs=None, base=None)``: ``initNs`` seeds
the query's Prologue first, then any ``BASE``/``PREFIX`` declaration
actually written in ``text`` is applied after and overrides it (per
``rdflib.plugins.sparql.algebra.translatePrologue``'s own source —
``initNs`` binds first, the parsed prologue's own declarations are
applied in a loop afterward).

**Parameters:**

- `text: str` - The SPARQL 1.2 query text to parse and translate.
- `base: str | None = None` - Optional base IRI, passed through to ``translateQuery``.
- `initNs: Mapping[str, Any] | None = None` - Optional namespace prefix bindings seeded into the query's Prologue before its own ``BASE``/``PREFIX`` declarations are applied.

**Returns:** `Query` - The translated, executable-shaped ``Query``, with ``CONSTRUCT WHERE`` shorthand canonicalized and triple-term pattern-subject use rejected.

**Source:** [starlayer.sparql.parse12.prepare_query_12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/parse12.py#L153-L187)

---

<a id="entity-starlayer-sparql-parse12-prepare_update_12"></a>
### `prepare_update_12`  _(function)_

```python
def prepare_update_12(text: str, base: str | None=None, initNs: Mapping[str, Any] | None=None) -> Update
```

``prepare_query_12``'s counterpart for SPARQL 1.2 Update text — same
``base``/``initNs`` passthrough to ``translateUpdate``.

**Parameters:**

- `text: str` - The SPARQL 1.2 Update text to parse and translate.
- `base: str | None = None` - Optional base IRI, passed through to ``translateUpdate``.
- `initNs: Mapping[str, Any] | None = None` - Optional namespace prefix bindings seeded into the request's Prologue before its own ``BASE``/``PREFIX`` declarations are applied.

**Returns:** `Update` - The translated, executable-shaped ``Update``.

**Source:** [starlayer.sparql.parse12.prepare_update_12](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/parse12.py#L190-L215)

---

<a id="entity-starlayer-sparql-to_rdf-queries_to_collection"></a>
### `queries_to_collection`  _(function)_

```python
def queries_to_collection(queries: list[Query], graph: Graph | None=None) -> tuple[Graph, BNode]
```

Encodes a list of independent, prepared rdflib ``Query`` objects as
one RDF ``salg:QueryCollection``.

The collection-of-independent-queries counterpart of
``update_to_rdf``'s single-request ``salg:operations`` list - see
``vocab.QUERY_COLLECTION``. Unlike an Update's operations, which
share one Prologue across the whole request, each query keeps its
own — ``query_to_rdf`` already encodes it per query, so nothing extra
is needed here for that.

**Parameters:**

- `queries: list[Query]` - The independent queries to encode.
- `graph: Graph | None = None` - The graph to add the encoding triples to; a fresh ``StarLayerGraph`` (see ``_new_starlayer_graph``) if omitted.

**Returns:** `tuple[Graph, BNode]` - ``(graph, root)`` — ``root`` is a dedicated container node holding ``salg:queries`` (an ``rdf:List`` of the member queries' own ``salg:Query``-typed roots, in the order given — order isn't semantically meaningful for a collection, but is preserved anyway since ``rdf:List`` is ordered regardless).

**Source:** [starlayer.sparql.to_rdf.queries_to_collection](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/to_rdf.py#L202-L233)

---

<a id="entity-starlayer-sparql-to_rdf-query_to_rdf"></a>
### `query_to_rdf`  _(function)_

```python
def query_to_rdf(query: Query, graph: Graph | None=None) -> tuple[Graph, BNode]
```

Encode a prepared rdflib ``Query`` (from ``prepareQuery``/``translateQuery``,
starlayer.graph's SPARQL-1.2-aware variants included) as RDF triples.

``root`` is the node for ``query.algebra``, additionally typed
``salg:Query`` (see ``vocab.QUERY``) so encoded queries in a larger
store can always be found via ``?q a salg:Query`` regardless of query
form.

**Parameters:**

- `query: Query` - The prepared query to encode.
- `graph: Graph | None = None` - The graph to add the encoding triples to; a fresh ``StarLayerGraph`` (see ``_new_starlayer_graph``) if omitted.

**Returns:** `tuple[Graph, BNode]` - ``(graph, root)``.

**Source:** [starlayer.sparql.to_rdf.query_to_rdf](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/to_rdf.py#L136-L160)

---

<a id="entity-starlayer-sparql-from_rdf-rdf_to_collection"></a>
### `rdf_to_collection`  _(function)_

```python
def rdf_to_collection(graph: Graph, root: BNode) -> list[Query]
```

Decode ``root`` (as produced by ``to_rdf.queries_to_collection``)
back into a list of independent, directly executable rdflib ``Query``
objects, in the same order they were encoded.

Each member is decoded via ``rdf_to_query`` individually — not the
generic ``_decode`` walker an ordinary ``rdf:List`` goes through
elsewhere in this module — since each member needs that function's own
per-query handling (recomputed ``_vars``/``lazy`` bookkeeping via
``_addVars``/``analyse``, its own reconstructed Prologue), the same
reason ``rdf_to_update`` doesn't reuse plain ``_decode`` for its own
operations list's *individual members* either (only the list structure
itself goes through the generic walker there).

**Parameters:**

- `graph: Graph` - The graph holding the encoded collection.
- `root: BNode` - The collection's root node, as returned by ``to_rdf.queries_to_collection``.

**Returns:** `list[Query]` - The member queries, in the order they were encoded.

**Source:** [starlayer.sparql.from_rdf.rdf_to_collection](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/from_rdf.py#L215-L238)

---

<a id="entity-starlayer-sparql-from_rdf-rdf_to_query"></a>
### `rdf_to_query`  _(function)_

```python
def rdf_to_query(graph: Graph, root: BNode) -> Query
```

Decode ``root`` (as produced by ``to_rdf.query_to_rdf``) back into an
rdflib ``Query`` — same type ``prepareQuery``/``translateQuery`` return.

The returned ``Query``'s ``Prologue`` is reconstructed from
``salg:base``/``salg:prologuePrefix`` on ``root`` (see vocab.py's
"Prologue (BASE/PREFIX)" section) — this fixes real evaluation-time
behavior (``BASE``-relative ``IRI()``/``URI()`` builtin resolution), but
does *not* make ``algebra.translateAlgebra`` emit prefixed names: that
function never reads ``query.prologue`` at all, confirmed empirically,
so its output stays full-IRI-only regardless.

**Parameters:**

- `graph: Graph` - The graph holding the encoded query.
- `root: BNode` - The query's root node, as returned by ``to_rdf.query_to_rdf``.

**Returns:** `Query` - A fully reconstructed, evaluator-ready ``Query``.

**Source:** [starlayer.sparql.from_rdf.rdf_to_query](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/from_rdf.py#L135-L174)

---

<a id="entity-starlayer-sparql-from_rdf-rdf_to_update"></a>
### `rdf_to_update`  _(function)_

```python
def rdf_to_update(graph: Graph, root: BNode) -> Update
```

Decode ``root`` (as produced by ``to_rdf.update_to_rdf``) back into an
rdflib ``Update`` — same type ``prepareUpdate``/``translateUpdate``
return, runnable via ``rdflib.plugins.sparql.update.evalUpdate``.

Unlike a Query's algebra, an Update operation's WHERE clause (Modify)
never gets the _vars/lazy bookkeeping pass in stock rdflib either —
``translateUpdate`` never calls ``_addVars``/``analyse`` the way
``translateQuery`` does for a SELECT/etc. — so there's nothing to
recompute here to match. The request's single shared Prologue (see
``update_to_rdf``) is reconstructed the same way as a Query's, and
assigned to every operation — ``evalUpdate`` reads ``u.prologue`` off
each operation individually, even though it's the same object for all
of them in a real ``prepareUpdate`` result too.

**Parameters:**

- `graph: Graph` - The graph holding the encoded update.
- `root: BNode` - The update's root node, as returned by ``to_rdf.update_to_rdf``.

**Returns:** `Update` - A fully reconstructed ``Update``.

**Source:** [starlayer.sparql.from_rdf.rdf_to_update](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/from_rdf.py#L177-L212)

---

<a id="entity-starlayer-sparql-entailment_rdf-rewrite_algebra_for_rdf"></a>
### `rewrite_algebra_for_rdf`  _(function)_

```python
def rewrite_algebra_for_rdf(algebra: Any) -> Any
```

Return ``algebra`` with every BGP rewritten for RDF entailment (see
module docstring for exactly which rule). Mutates and returns the same
tree (matching ``rdflib.plugins.sparql.algebra.traverse``'s own
contract) - idempotent, since every triple this rewrite produces uses a
fresh ``__starlayer_rdf_N`` variable in a slot that never matches the
``p == RDF.type and o == RDF.Property`` trigger a second time (the
fresh predicate variable is never literally ``rdf:Property``).

**Parameters:**

- `algebra: Any` - The root of an already-lowered plain SPARQL 1.1 algebra tree.

**Returns:** `Any` - The same tree, mutated in place, with every BGP rewritten.

**Source:** [starlayer.sparql.entailment_rdf.rewrite_algebra_for_rdf](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/entailment_rdf.py#L120-L151)

---

<a id="entity-starlayer-sparql-entailment_rdfs-rewrite_algebra_for_rdfs"></a>
### `rewrite_algebra_for_rdfs`  _(function)_

```python
def rewrite_algebra_for_rdfs(algebra: Any) -> Any
```

Return ``algebra`` with every BGP rewritten for RDFS entailment (see
module docstring for exactly which rules). Mutates and returns the
same tree (matching ``rdflib.plugins.sparql.algebra.traverse``'s own
contract, already relied on elsewhere in this codebase's lowering
passes) - idempotent, since every triple this rewrite produces uses
either a ``Path`` object or a fresh ``__starlayer_rdfs_N`` variable in
predicate position, neither of which matches the ``p == RDF.type`` /
``isinstance(p, URIRef)`` checks that trigger rewriting on a second
pass.

**Parameters:**

- `algebra: Any` - The root of an already-lowered plain SPARQL 1.1 algebra tree.

**Returns:** `Any` - The same tree, mutated in place, with every BGP rewritten.

**Source:** [starlayer.sparql.entailment_rdfs.rewrite_algebra_for_rdfs](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/entailment_rdfs.py#L255-L289)

---

<a id="entity-starlayer-sparql-to_rdf-update_to_rdf"></a>
### `update_to_rdf`  _(function)_

```python
def update_to_rdf(update: Update, graph: Graph | None=None) -> tuple[Graph, BNode]
```

Encode a prepared rdflib ``Update`` (from ``prepareUpdate``/
``translateUpdate``) as RDF triples.

``update.algebra`` is a ``List[CompValue]`` — one operation per
semicolon-separated request in the Update string, executed in that
order. ``root`` is a dedicated container node (not itself a CompValue,
typed ``salg:Update`` — see ``vocab.UPDATE``) holding ``salg:operations``
(an ``rdf:List`` of the encoded operations — order matters and must
survive the round-trip) plus the request's shared Prologue
(``salg:base``/``salg:prologuePrefix`` — SPARQL Update has one Prologue
per request, not one per operation, unlike a Query). Each operation node
is additionally typed ``salg:UpdateOperation`` (see
``vocab.UPDATE_OPERATION``).

**Parameters:**

- `update: Update` - The prepared update to encode.
- `graph: Graph | None = None` - The graph to add the encoding triples to; a fresh ``StarLayerGraph`` (see ``_new_starlayer_graph``) if omitted.

**Returns:** `tuple[Graph, BNode]` - ``(graph, root)``.

**Source:** [starlayer.sparql.to_rdf.update_to_rdf](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/to_rdf.py#L163-L199)

---

## `starlayer.sparql.salg`

[Back to overview](api-overview.generated.md#starlayersparqlsalg)

<a id="entity-starlayer-sparql-salg-semantic_checks-UnboundProjectedVariable"></a>
### `UnboundProjectedVariable`  _(class)_

One `Project` node whose `PV` names a variable never bound anywhere
in its own pattern subtree.

Attributes:
    project_node: The `Project` node this finding is about.
    variable: The unbound variable named in `PV`.
    projected_vars: The node's full `PV`, for context.

**Source:** [starlayer.sparql.salg.semantic_checks.UnboundProjectedVariable](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/salg/semantic_checks.py#L86-L98)

---

<a id="entity-starlayer-sparql-salg-semantic_checks-find_unbound_projected_variables"></a>
### `find_unbound_projected_variables`  _(function)_

```python
def find_unbound_projected_variables(data_graph: Graph) -> list[UnboundProjectedVariable]
```

Returns every ``UnboundProjectedVariable`` finding in ``data_graph``.

Finds every ``salg:Project`` node in ``data_graph`` (a ``salg:``
algebra graph, as produced by ``to_rdf.query_to_rdf``/``update_to_rdf``
- ``Project`` nodes can appear for a Query or an Update alike) whose
``PV`` names a variable that's never actually bound anywhere in its
own pattern subtree.

A plain, standalone function for a caller who wants this one check
directly - the same check also runs automatically as a real SHACL
constraint whenever ``starlayer.sparql.validate()`` validates a graph whose
``salg:Project`` nodes activate it (see this module's own docstring).

**Parameters:**

- `data_graph: Graph` - The ``salg:`` algebra graph to scan.

**Returns:** `list[UnboundProjectedVariable]` - One `UnboundProjectedVariable` per offending `PV` variable, across every `Project` node in `data_graph` (empty if none).

**Source:** [starlayer.sparql.salg.semantic_checks.find_unbound_projected_variables](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/salg/semantic_checks.py#L179-L203)

---

<a id="entity-starlayer-sparql-salg-sparql_ontology-ontology_graph"></a>
### `ontology_graph`  _(function)_

```python
def ontology_graph() -> Graph
```

Build a fresh graph: the RDFS ontology in ``salg-ontology.ttl``
merged with ``spexpr-ontology.ttl`` (lives in the ``starontology``
package).

The merge is required, not cosmetic: ``salg:Expression``/
``salg:Variable``/``salg:Path`` and their subclasses live in the
``spexpr:`` vocabulary (see ``starlayer/sparql/vocab.py``'s own
``SPEXPR`` definition for why), so the RDFS subclass axioms
``ExpressionShape``'s ``sh:class spexpr:Expression`` check depends on
for entailment live there too - without this merge, that entailment
would not fire and every expression/variable/path check this module's
own shapes rely on would fail. ``salg-ontology.ttl`` on its own has no
opinion about expressions/variables/paths at all - entirely
``spexpr:``'s concern.

**Returns:** `Graph` - A fresh ``rdflib.Graph`` combining both ontologies (callers get their own copy, not a shared module-level instance).

**Source:** [starlayer.sparql.salg.sparql_ontology.ontology_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/salg/sparql_ontology.py#L120-L142)

---

## `starlayer.sparql.sqe`

[Back to overview](api-overview.generated.md#starlayersparqlsqe)

<a id="entity-starlayer-sparql-sqe-to_rdf-SQEError"></a>
### `SQEError`  _(class)_

Base class for every ``sqe:``-specific exception
(``SQEValidationError`` here) - gives a caller two real catch
granularities, "this specific failure" vs. "any ``sqe:`` failure",
the same two-tier shape ``srl.py``'s own ``SRLError``/
``SRLParseError`` already established for the identical reason.

**Source:** [starlayer.sparql.sqe.to_rdf.SQEError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/sqe/to_rdf.py#L152-L157)

---

<a id="entity-starlayer-sparql-sqe-to_rdf-SQEValidationError"></a>
### `SQEValidationError`  _(class)_

Raised by :func:`sqe_parse_to_tree` when the text parses fine but
the resulting ``sqe:`` tree fails ``sqe:``'s own SHACL shapes (most
notably the unbound-projected-variable check) - "this text doesn't
produce a usable ``sqe:`` tree", matching the same "succeed with a
usable object, or raise" contract ``prepareQuery()``/
``srl.parse_ruleset()`` already give their own callers, rather than
handing back a tree that's already known to be unusable and leaving
it to the caller to remember to check.

Carries the full validation report as attributes, not just a
message, so a caller who wants the structured detail doesn't have to
re-run :func:`sqe_validate` themselves to get it.

Attributes:
    report_graph: The full ``sh:ValidationReport`` graph.
    report_text: The same report, rendered as text (this
        exception's own ``str()`` is a short prefix plus this text).

**Source:** [starlayer.sparql.sqe.to_rdf.SQEValidationError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/sqe/to_rdf.py#L160-L183)

---

<a id="entity-starlayer-sparql-sqe-to_rdf-sqe_parse_to_tree"></a>
### `sqe_parse_to_tree`  _(function)_

```python
def sqe_parse_to_tree(text: str, graph: Graph | None=None, root: IdentifiedNode | None=None) -> tuple[Graph, IdentifiedNode]
```

Encode SPARQL ``SELECT``/``ASK``/``CONSTRUCT`` query text as
``sqe:`` RDF, and validate the result. The one public encoding entry
point - parses ``text`` with the same ``parseQuery`` every other
SPARQL 1.2 entry point in this package uses, delegates to
``_query_to_sqe_rdf`` below, then validates via :func:`sqe_validate`
before returning - a caller only ever gets back a tree already
confirmed to satisfy ``sqe:``'s own shapes (including the
unbound-projected-variable check), never one silently known to fail.

Validation only runs here, at creation time - it has no way to see,
and does not re-run for, any edit made to the tree afterward (see
the guide notebook's own section on this). Call :func:`sqe_validate`
yourself again after editing a tree directly.

**Parameters:**

- `text: str` - The SPARQL query text to encode.
- `graph: Graph | None = None` - The graph to add the ``sqe:`` RDF to. Defaults to a fresh ``StarLayerGraph`` (see ``to_rdf._new_starlayer_graph``).
- `root: IdentifiedNode | None = None` - The node to use as the query's own root - any ``URIRef``/ ``BNode``. Defaults to a fresh ``BNode()``. Give a real ``URIRef`` to make the query findable by that identity later (e.g. ``graph.value(my_iri, RDF.type, SQE.Query)``), rather than only via the ``root`` value this function itself returns - useful once a graph accumulates more than one encoded query (via repeated calls sharing one ``graph=``), where a bare `?s a sqe:Query` lookup can no longer tell them apart on its own.

**Returns:** `tuple[Graph, IdentifiedNode]` - A ``(graph, root)`` tuple.

**Source:** [starlayer.sparql.sqe.to_rdf.sqe_parse_to_tree](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/sqe/to_rdf.py#L186-L241)

---

<a id="entity-starlayer-sparql-sqe-from_rdf-sqe_tree_to_query"></a>
### `sqe_tree_to_query`  _(function)_

```python
def sqe_tree_to_query(graph: Graph, root) -> Query
```

Decode ``root`` (one of ``sqe:SelectQuery``/``sqe:AskQuery``/
``sqe:ConstructQuery``, as produced by
``to_rdf.sqe_parse_to_tree``) back into a real rdflib ``Query``.

The returned ``Query``'s own ``.prologue`` is empty (rdflib's default,
no prefixes) — execution never needs prefixes once every term is
already a resolved ``URIRef``. The *original* preserved prefixes live
on ``root`` itself (``salg:prologuePrefix``, via ``to_rdf.py``'s
``_encode_prologue``) and are read directly by ``to_text.py`` for
prefix-aware rendering, not threaded through here.

**Parameters:**

- `graph: Graph` - The ``sqe:`` RDF graph containing ``root``.
- `root: None` - The query root node to decode.

**Returns:** `Query` - A real, executable rdflib ``Query``.

**Source:** [starlayer.sparql.sqe.from_rdf.sqe_tree_to_query](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/sqe/from_rdf.py#L98-L119)

---

<a id="entity-starlayer-sparql-sqe-to_text-sqe_tree_to_text"></a>
### `sqe_tree_to_text`  _(function)_

```python
def sqe_tree_to_text(graph: Graph, root) -> str
```

Render ``root`` (as produced by ``to_rdf.sqe_parse_to_tree``) back
into SPARQL query text, re-abbreviating terms using the ``PREFIX``
declarations preserved on ``root`` wherever one matches.

**Parameters:**

- `graph: Graph` - The ``sqe:`` RDF graph containing ``root``.
- `root: None` - The query root node to render.

**Returns:** `str` - The rendered SPARQL query text.

**Source:** [starlayer.sparql.sqe.to_text.sqe_tree_to_text](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/sparql/sqe/to_text.py#L83-L103)

---

## `starlayer.shacl`

[Back to overview](api-overview.generated.md#starlayershacl)

<a id="entity-starlayer-shacl-engine-contracts-ComponentRequest"></a>
### `ComponentRequest`  _(class)_

One native-component evaluation request - ``evaluate_component()``'s
own sole argument.

**Source:** [starlayer.shacl.engine.contracts.ComponentRequest](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/contracts.py#L8-L16)

---

<a id="entity-starlayer-shacl-results-ExecutionDiagnostics"></a>
### `ExecutionDiagnostics`  _(class)_

Internal adapter bookkeeping for the RDF 1.2 triple-term adaptation
layer - not general-purpose validation statistics.

The type of ``ValidationResult.diagnostics``. Not a type you'd
construct directly.

**Source:** [starlayer.shacl.results.ExecutionDiagnostics](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L8-L26)

---

<a id="entity-starlayer-shacl-types-MutableStarLayerGraphProtocol"></a>
### `MutableStarLayerGraphProtocol`  _(class)_

``StarLayerGraphProtocol`` plus mutation methods - ``add()``/
``remove()``.

**Source:** [starlayer.shacl.types.MutableStarLayerGraphProtocol](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/types.py#L19-L32)

---

<a id="entity-starlayer-shacl-types-MutableStarLayerGraphProtocol-add"></a>
### `MutableStarLayerGraphProtocol.add`  _(method)_

```python
def add(self, triple: tuple[Any, Any, Any]) -> Any
```

Adds ``triple`` to the graph.

**Parameters:**

- `triple: tuple[Any, Any, Any]`

**Returns:** `Any`

**Source:** [starlayer.shacl.types.MutableStarLayerGraphProtocol.add](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/types.py#L24-L26)

---

<a id="entity-starlayer-shacl-types-MutableStarLayerGraphProtocol-remove"></a>
### `MutableStarLayerGraphProtocol.remove`  _(method)_

```python
def remove(self, triple_pattern: tuple[Any, Any, Any]) -> Any
```

Removes every triple matching ``triple_pattern`` from the
graph.

**Parameters:**

- `triple_pattern: tuple[Any, Any, Any]`

**Returns:** `Any`

**Source:** [starlayer.shacl.types.MutableStarLayerGraphProtocol.remove](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/types.py#L28-L32)

---

<a id="entity-starlayer-shacl-results-RulesResult"></a>
### `RulesResult`  _(class)_

Result of ``apply_rules()``.

``apply_rules()`` executes ``sh:rule``/``sh:SPARQLRule`` against a
private working copy of the caller's ``data_graph`` (never mutated
in place) and returns what the rules produced.

``inferred_graph`` is strictly the SHACL 1.2 Inference Rules spec's own
"inference graph" - only the triples rule execution itself produced
(shape-attached ``sh:rule``, global ``sh:SPARQLRule``/``sh:RuleSet``,
and ``sh:sourceRule`` provenance reifiers). It contains neither the
original base triples nor anything an entailment regime
(``sh:entailment`` or ``inference=``) added - entailment is purely a
computational device for correct rule matching and conformance
checking here, never persisted into the result.

``validation`` is the result of one real ``validate()`` call
``apply_rules()`` makes internally, over the *complete* evaluation
graph: base ∪ every rule-produced triple ∪ every entailed triple.
``validation.conforms``/``.report_graph``/``.report_text`` correctly
reflect everything that was true during execution, even though
entailment's own triples don't appear in ``inferred_graph`` itself.
``validation.data_graph`` is always ``None`` in this context (that
internal call always uses the ``"validation"`` mode's own
``inplace=False`` default) - harmless, just not meaningful here.

**Source:** [starlayer.shacl.results.RulesResult](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L49-L77)

---

<a id="entity-starlayer-shacl-types-StarLayerGraphProtocol"></a>
### `StarLayerGraphProtocol`  _(class)_

Structural protocol every graph-like input to this package must
satisfy: a bound ``namespace_manager`` plus iterability over triples.

**Source:** [starlayer.shacl.types.StarLayerGraphProtocol](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/types.py#L7-L15)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter"></a>
### `TripleTermAdapter`  _(class)_

Encode/decode triple terms so pySHACL can process RDF 1.1-compatible graphs.

**Source:** [starlayer.shacl.adapters.TripleTermAdapter](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L290-L715)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-clear_registry"></a>
### `TripleTermAdapter.clear_registry`  _(method)_

```python
def clear_registry(self) -> None
```

Drop every registered triple-term mapping, forward and reverse.

**Returns:** `None`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.clear_registry](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L346-L349)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-decode_graph"></a>
### `TripleTermAdapter.decode_graph`  _(method)_

```python
def decode_graph(self, graph: Iterable[tuple[Any, Any, Any]])
```

Returns the inverse of ``encode_graph()``: a copy of ``graph``
with every encoded term resolved back to its real form.

Every registered ``tt:HASH`` URIRef is resolved back to a real
triple term, and a dirlang-encoded Literal back to a
``DirLangString``. Drops the
``rdf:subject``/``rdf:predicate``/``rdf:object`` encoding triples
``encode_graph()`` added for each registered term - those are
internal bookkeeping, not part of the decoded graph's own
content.

**Parameters:**

- `graph: Iterable[tuple[Any, Any, Any]]` - The triples to decode.

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.decode_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L490-L520)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-decode_term"></a>
### `TripleTermAdapter.decode_term`  _(method)_

```python
def decode_term(self, value: Any) -> Any
```

Decodes a single term the same way ``decode_graph`` decodes one
node.

No target graph is involved, so a decoded triple term always
comes back as a ``term_factory`` instance, never a plain tuple -
see ``_decode_node``.

**Parameters:**

- `value: Any`

**Returns:** `Any`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.decode_term](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L548-L556)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-diagnostics_snapshot"></a>
### `TripleTermAdapter.diagnostics_snapshot`  _(method)_

```python
def diagnostics_snapshot(self) -> dict[str, int]
```

Return a copy of the current diagnostic counters
(``encode_graph_calls``, ``decode_graph_calls``,
``encoded_triple_terms``, ``decoded_triple_terms``).

**Returns:** `dict[str, int]`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.diagnostics_snapshot](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L332-L337)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-encode_graph"></a>
### `TripleTermAdapter.encode_graph`  _(method)_

```python
def encode_graph(self, graph: Iterable[tuple[Any, Any, Any]]) -> Graph
```

Returns a flat, RDF-1.1-compatible copy of ``graph`` with every
triple term and DirLangString literal flattened to plain terms.

The result is a ``_SparqlAwareEncodedGraph``: every triple-term
node, in any position, is replaced by its content-addressed
``tt:HASH`` URIRef, and a DirLangString literal is replaced by
its internal encoded datatype form.

Every triple term encountered anywhere in ``graph`` is registered
in this adapter's registry (see ``_encode_node()``), and the
resulting graph also carries that registry's own
``rdf:subject``/``rdf:predicate``/``rdf:object`` triples for every
term registered so far (not just the ones from this one call), so
a consumer with no access to the adapter itself (e.g. plain
pySHACL machinery) can still see each encoded term's components
as ordinary triples.

**Parameters:**

- `graph: Iterable[tuple[Any, Any, Any]]` - The triples to encode - any iterable of ``(s, p, o)``.

**Returns:** `Graph` - A new ``_SparqlAwareEncodedGraph`` bound to this adapter.

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.encode_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L450-L488)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-encode_term"></a>
### `TripleTermAdapter.encode_term`  _(method)_

```python
def encode_term(self, value: Any) -> Any
```

Encodes a single term the same way ``encode_graph`` encodes one
node - see ``_encode_node``.

**Parameters:**

- `value: Any`

**Returns:** `Any`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.encode_term](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L542-L546)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-export_registry"></a>
### `TripleTermAdapter.export_registry`  _(method)_

```python
def export_registry(self) -> dict[str, Any]
```

Serializes the current registry to a plain JSON-able dict.

For persisting or transferring it - see ``import_registry()``.

**Returns:** `dict[str, Any]` - A dict with ``"namespace"`` (this adapter's namespace, as a string) and ``"entries"`` (one dict per registered triple term, its encoded URI and its subject/predicate/object each in N3 form).

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.export_registry](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L351-L375)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-for_starlayer_graph"></a>
### `TripleTermAdapter.for_starlayer_graph`  _(method)_

```python
def for_starlayer_graph(cls) -> TripleTermAdapter
```

Creates an adapter whose decoded triple terms are real
``starlayer.graph.model.triple.TripleTerm`` instances.

Instead of the default, dependency-free ``TripleTermValue`` - for
use wherever the decoded graph needs to interoperate with
``StarLayerGraph``.

Raises:
    RuntimeError: ``starlayer.graph`` is not installed.

**Returns:** `TripleTermAdapter`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.for_starlayer_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L431-L448)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-import_registry"></a>
### `TripleTermAdapter.import_registry`  _(method)_

```python
def import_registry(self, payload: dict[str, Any], *, merge: bool=False, strict_namespace: bool=True) -> None
```

Load a registry previously produced by ``export_registry()``.

**Parameters:**

- `payload: dict[str, Any]` - A dict in ``export_registry()``'s own format.
- `merge: bool = False` - If ``False`` (default), clears the existing registry first; if ``True``, adds to it, checking each incoming entry against the current entries for conflicts.
- `strict_namespace: bool = True` - If ``True`` (default), raises ``ValueError`` when ``payload``'s own namespace doesn't match this adapter's.

**Returns:** `None`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.import_registry](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L377-L428)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-replace_graph"></a>
### `TripleTermAdapter.replace_graph`  _(method)_

```python
def replace_graph(self, target: Any, source: Iterable[tuple[Any, Any, Any]]) -> Any
```

Replaces every triple in ``target`` with the triples from
``source``, in place.

Mutates via ``target``'s own ``remove``/``add`` methods, not a
reassignment - so any identity a caller holds to ``target``
itself stays valid.

**Parameters:**

- `target: Any` - The graph to empty and refill, mutated in place.
- `source: Iterable[tuple[Any, Any, Any]]` - The triples to add after ``target`` is cleared.

**Returns:** `Any` - ``target``, for convenience chaining.

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.replace_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L522-L540)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-reset_diagnostics"></a>
### `TripleTermAdapter.reset_diagnostics`  _(method)_

```python
def reset_diagnostics(self) -> None
```

Reset the call/encode/decode counters returned by
``diagnostics_snapshot()`` back to zero, without touching the
encode/decode registry itself.

**Returns:** `None`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.reset_diagnostics](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L320-L330)

---

<a id="entity-starlayer-shacl-adapters-TripleTermAdapter-support_triple_count"></a>
### `TripleTermAdapter.support_triple_count`  _(method)_

```python
def support_triple_count(self) -> int
```

Return the number of ``rdf:subject``/``rdf:predicate``/
``rdf:object`` encoding triples this adapter's registry would add
to a graph - 3 per registered triple term.

**Returns:** `int`

**Source:** [starlayer.shacl.adapters.TripleTermAdapter.support_triple_count](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L339-L344)

---

<a id="entity-starlayer-shacl-adapters-TripleTermGraph"></a>
### `TripleTermGraph`  _(class)_

Simple graph-like container that can hold triple-term objects directly.

**Source:** [starlayer.shacl.adapters.TripleTermGraph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L246-L287)

---

<a id="entity-starlayer-shacl-adapters-TripleTermGraph-add"></a>
### `TripleTermGraph.add`  _(method)_

```python
def add(self, triple: tuple[Any, Any, Any]) -> TripleTermGraph
```

Adds ``triple`` if not already present, and returns this graph.

**Parameters:**

- `triple: tuple[Any, Any, Any]`

**Returns:** `TripleTermGraph`

**Source:** [starlayer.shacl.adapters.TripleTermGraph.add](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L262-L266)

---

<a id="entity-starlayer-shacl-adapters-TripleTermGraph-remove"></a>
### `TripleTermGraph.remove`  _(method)_

```python
def remove(self, pattern: tuple[Any, Any, Any]) -> TripleTermGraph
```

Removes every triple matching ``pattern`` and returns this graph.

Any ``None`` component of ``pattern`` matches anything; an
all-``None`` pattern clears every triple.

**Parameters:**

- `pattern: tuple[Any, Any, Any]`

**Returns:** `TripleTermGraph`

**Source:** [starlayer.shacl.adapters.TripleTermGraph.remove](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L268-L287)

---

<a id="entity-starlayer-shacl-adapters-TripleTermValue"></a>
### `TripleTermValue`  _(class)_

The default, dependency-free decoded triple-term value type.

**Source:** [starlayer.shacl.adapters.TripleTermValue](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/adapters.py#L238-L243)

---

<a id="entity-starlayer-shacl-results-ValidationResult"></a>
### `ValidationResult`  _(class)_

Result of ``validate()`` - a richer replacement for pyshacl's own
bare ``(conforms, report_graph, report_text)`` tuple.

``data_graph`` is only populated when the call used ``inplace=True``
(the ``"rules"`` mode's own default) - the caller's own data graph,
mutated with any in-place changes decoded back; ``None`` otherwise,
not an error. ``diagnostics`` is internal adapter bookkeeping (see
``ExecutionDiagnostics``), not general-purpose validation statistics.

**Source:** [starlayer.shacl.results.ValidationResult](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L30-L45)

---

<a id="entity-starlayer-shacl-validator-apply_rules"></a>
### `apply_rules`  _(function)_

```python
def apply_rules(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, include_source_rule_provenance: bool=False, rule_set: Any | None=None, **kwargs: Any) -> RulesResult
```

Executes SHACL rules against a private working copy of
``data_graph``, then validates the resulting evaluation graph.

Covers ``sh:rule``/``sh:TripleRule``/``sh:SPARQLRule``, plus SHACL
1.2's own ``sh:RuleSet``/``sh:sourceRule`` provenance. Mirrors
pyshacl's own module-level ``shacl_rules()`` entry point - this is
the real implementation; ``StarShaclSchema.apply_rules()`` delegates
here, binding its own ``shacl_graph``/``ont_graph``.

The caller's own ``data_graph`` object is never mutated - every
step (rule execution, entailment, the final conformance re-check)
runs against a fresh working copy instead. ``data_graph`` must be a
``StarLayerGraph`` (the working copy is built via
``type(data_graph)()``, and only a ``StarLayerGraph`` round-trips
RDF-1.2 triple terms through rule execution correctly).

Processing order: (1) the "before rules" entailment/``inference=``
pass; (2) shape-attached rule execution, via an internal
``validate(..., mode="rules")`` call; (3) the separate global
``sh:SPARQLRule``/``sh:RuleSet`` pass; (4) entailment is re-applied,
since global rules may have produced triples a declared regime
should also close over; (5) a final re-validation with
``mode="validation"`` (not ``"rules"`` again - rules have already
run), whose conformance result is what's actually returned.

**Parameters:**

- `data_graph: Any` - The data graph rules execute against. Must be a ``StarLayerGraph``; raises ``TypeError`` otherwise.
- `shacl_graph: Any | None = None` - The shapes graph declaring the rules (and, when ``rule_set`` is given, the ``sh:RuleSet``s to select from). ``None`` falls back to ``data_graph`` itself, so an unattached global ``sh:SPARQLRule`` living directly in the data graph is still discovered.
- `ont_graph: Any | None = None` - An optional ontology graph, visible to entailment the same way as in ``validate()``/``evaluate()``.
- `include_source_rule_provenance: bool = False` - When ``True``, every triple produced by rule execution (shape-attached or global) gets a reifier recording which rule produced it, per SHACL 1.2 Inference Rules section 9's ``sh:sourceRule``: ``_:id rdf:reifies <<( s p o )>> . _:id sh:sourceRule <rule> .``
- `rule_set: Any | None = None` - When given, restricts rule execution to only the rules belonging to the named ``sh:RuleSet``(s) (resolved via ``_rule_set_members()`` against the normalized shapes graph). the rule-execution pass and the final re-validation), after being merged into the ``"rules"``/``"validation"`` mode presets respectively via ``resolve_mode_options()``. ``inference`` is read directly out of ``kwargs`` for the explicit before/after-rules entailment passes described above.
- `kwargs: Any`

**Returns:** `RulesResult` - A ``RulesResult`` with two fields: ``inferred_graph`` - strictly the triples rule execution itself produced (shape-attached and global rules, plus any ``sh:sourceRule`` provenance reifiers); neither the original base triples nor anything any entailment regime added are included, since entailment is purely a computational device here, never persisted. ``validation`` - the full ``ValidationResult`` from the final re-validation pass, whose ``conforms``/ ``report_graph``/``report_text`` reflect the complete evaluation graph (base ∪ rules ∪ entailment); its own ``data_graph`` field is always ``None`` in this context (the internal call uses the ``"validation"`` mode's own ``inplace=False`` default).

**Source:** [starlayer.shacl.validator.apply_rules](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L4041-L4129)

---

<a id="entity-starlayer-shacl-engine-core-build_report"></a>
### `build_report`  _(function)_

```python
def build_report(*, events: tuple[dict[str, Any], ...], graph_context: Any, options: dict[str, Any] | None=None) -> Any
```

Builds a ``sh:ValidationReport`` graph from component ``events``.

**Parameters:**

- `events: tuple[dict[str, Any], ...]`
- `graph_context: Any`
- `options: dict[str, Any] | None = None`

**Returns:** `Any`

**Source:** [starlayer.shacl.engine.core.build_report](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/core.py#L176-L214)

---

<a id="entity-starlayer-shacl-profiling-declared_conformance_profile"></a>
### `declared_conformance_profile`  _(function)_

```python
def declared_conformance_profile() -> StarLayerGraph
```

A fresh copy of starlayer.shacl's self-declared SHACL 1.2
conformance statement (S3) - the starlayer.shacl resource in the
library's one conformance file. Parses the bundled asset fresh on every
call rather than caching - matching this project's convention
elsewhere (see starontology/__init__.py::_file_graph) of never
sharing one mutable graph object across callers.

Returns a ``StarLayerGraph``, not a plain ``rdflib.Graph`` - this is a
public, caller-facing result meant to be inspected/serialized/merged,
not internal plumbing fed straight to pySHACL.

**Returns:** `StarLayerGraph` - A fresh StarLayerGraph containing the bundled conformance statement.

**Source:** [starlayer.shacl.profiling.declared_conformance_profile](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/profiling.py#L103-L130)

---

<a id="entity-starlayer-shacl-profiling-derive_conforms_to"></a>
### `derive_conforms_to`  _(function)_

```python
def derive_conforms_to(report_graph: Any, *, data_graph: str | URIRef | None=None, shapes_graph: str | URIRef | None=None, specification_graph: Any | None=None, conforms_only: bool=False) -> StarLayerGraph
```

Derive ``sh:conformsTo`` triples from a validation report, per
SHACL 1.2 Profiling S5.5.

Only conforming reports (``sh:conforms true``) produce a
``sh:conformsTo`` triple, matching the rule's own WHERE clause - a
non-conformant report derives nothing.

If ``specification_graph`` is given, the second S5.5 rule also runs
once the first has fired, additionally deriving ``dcterms:conformsTo``
triples to whatever ``shapes_graph`` is declared a profile of (the S5.5
rule), and also - StarLayer's extension - to the ``prof:Profile`` that
lists ``shapes_graph`` as a ``role:validation`` resource and to every
specification or profile that profile ``prof:isProfileOf``, however
many steps up. This is not the same relationship
``declared_conformance_profile()`` records (that one is *this
library's* own conformance to named SHACL 1.2 feature profiles, a
different resource than ``shapes_graph``) - pass a graph relating
``shapes_graph`` itself to whatever it profiles.

**Parameters:**

- `report_graph: Any` - A plain SHACL validation report graph (e.g. ``ValidationResult.report_graph``). Read, never mutated.
- `data_graph: str | URIRef | None = None` - The data graph as an RDF resource - an IRI or IRI-like string, using whatever identity scheme the caller's application already uses (a dataset-catalog IRI, a named-graph IRI - there is no single right default). Optional: if the report was produced by ``validate(..., data_graph_iri=..., shapes_graph_resource=...)``, the matching ``sh:usedDataGraph`` triple is already on the report and is read from there when this is omitted.
- `shapes_graph: str | URIRef | None = None` - The shapes graph as an RDF resource, same optionality and fallback as ``data_graph`` (read from the report's own ``sh:usedShapesGraph`` when omitted).
- `specification_graph: Any | None = None` - A graph relating ``shapes_graph`` to what it profiles - either ``prof:isProfileOf`` on ``shapes_graph`` itself, or a ``prof:Profile`` that lists it as a ``role:validation`` ``prof:hasResource`` artifact (e.g. ``starontology.get_conformance_profiles()``) - to additionally derive ``dcterms:conformsTo`` triples via S5.5's second rule (see above). Read, never mutated. ``None`` (the default) skips this second rule entirely.
- `conforms_only: bool = False` - If ``True``, the returned graph contains *only* the ``sh:conformsTo``/``dcterms:conformsTo`` triples themselves - not ``report_graph``, and not even the ``sh:validationReport`` link this function otherwise adds (that link exists to justify the conformance claim with a path back to the report, which ``conforms_only`` says isn't wanted) - useful when a caller only cares about the conformance claims themselves, e.g. to merge into a dataset catalog entry that has no reason to reference a SHACL validation report at all. If ``False`` (the default), the returned graph is ``report_graph`` merged with whatever got newly derived - a self-contained, immediately printable/serializable result, where the added ``sh:validationReport`` link resolves to a real, fully-described node rather than a dangling blank-node reference.

**Returns:** `StarLayerGraph` - A new ``StarLayerGraph``. ``report_graph``/``specification_graph`` are read, never mutated.

**Source:** [starlayer.shacl.profiling.derive_conforms_to](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/profiling.py#L176-L329)

---

<a id="entity-starlayer-shacl-validator-evaluate"></a>
### `evaluate`  _(function)_

```python
def evaluate(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, *, inference: Any | None=None, focus_nodes: Any | None=None, properties: Any | None=None, rules_entailment: bool=False) -> Any
```

Computes every ``sh:values``/``sh:defaultValue``-declared virtual
property across ``shacl_graph`` and returns the result as a
shape-driven subgraph.

A third, independent processing mode alongside ``validate()``
(checks conformance, never mutates) and ``apply_rules()`` (executes
``sh:rule``, materializes real triples). ``StarShaclSchema.evaluate()``
keeps its own, separate copy of this body for now - see
``validate()``'s own docstring.

The returned graph contains every property shape's real, stored
``sh:path`` values for its own target focus nodes (not just the
ones also declaring ``sh:values``/``sh:defaultValue``), plus the
computed virtual values layered on top - never the whole of
``data_graph``. Only a property shape's simple, single-predicate
``sh:path`` is handled; a property path expression (sequence/
inverse/etc.) is silently skipped. A computed value is unioned
with any real, already-stored value for the same predicate, never
replacing it (SHACL 1.2 Core's "Value Nodes of Property Shapes"
algorithm unconditionally adds both real path-based values and
``sh:values``-computed values to the same set; only
``sh:defaultValue`` is conditional, on that set still being empty).
The caller's own ``data_graph`` is never mutated, and the returned
graph is not meant to be persisted - the SHACL 1.2 Node Expressions
spec's own framing for virtual values is that they are computed
"only on demand", never creating real triples in the data or
shapes graph.

**Parameters:**

- `data_graph: Any` - The RDF data to evaluate virtual properties over.
- `shacl_graph: Any | None = None` - The shapes graph declaring ``sh:values``/ ``sh:defaultValue``. ``None`` falls back to ``data_graph`` itself, matching ``validate()``'s own "data graph doubles as shapes graph" allowance.
- `ont_graph: Any | None = None` - An optional ontology graph, visible to entailment the same way as in ``validate()``/``apply_rules()``.
- `inference: Any | None = None` - A real ``ENTAILMENT.*`` IRI, or an iterable of them, merged with ``shacl_graph``'s own declared ``sh:entailment`` regime(s) and applied once, up front, onto a private, non-mutating copy of ``data_graph``. Every later step (target resolution, ``sh:values``/ ``sh:defaultValue`` computation, and what counts as a "real, stored" value) runs against that entailed copy. Unlike ``apply_rules()``'s "inference graph" exclusion, an entailed triple here is treated exactly like an asserted one and can appear in the returned subgraph - a deliberate choice, since Core's own value-nodes algorithm itself never distinguishes asserted from entailed triples.
- `focus_nodes: Any | None = None` - Restrict evaluation to these focus nodes (an iterable of nodes). ``None`` (the default) evaluates every node the shapes target; a node that is not one of a shape's targets is not evaluated for it. Only the per-node work (reading stored values and computing ``sh:values``/``sh:defaultValue``) is limited; the shapes' own targets are still resolved over ``data_graph``.
- `properties: Any | None = None` - Restrict evaluation to property shapes whose ``sh:path`` is one of these predicates (an iterable of IRIs). ``None`` evaluates every property shape.
- `rules_entailment: bool = False` - Also run the rules ``shacl_graph`` names in ``sh:entailment`` (``sh:RulesEntailment`` or a rule set, Inference Rules section 6) before evaluating, as ``validate()`` does. Off by default: evaluating is not validating, and the rules cost a full ``apply_rules`` pass.

**Returns:** `Any` - A plain graph object (the same type as ``data_graph``) containing the shape-driven subgraph described above.

**Source:** [starlayer.shacl.validator.evaluate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L3842-L3998)

---

<a id="entity-starlayer-shacl-engine-core-evaluate_component"></a>
### `evaluate_component`  _(function)_

```python
def evaluate_component(request: ComponentRequest) -> _ComponentEvaluationResult
```

Evaluates one native ``ConstraintComponent`` directly against
``request``'s own focus/value nodes, dispatched by component name.

**Parameters:**

- `request: ComponentRequest`

**Returns:** `_ComponentEvaluationResult`

**Source:** [starlayer.shacl.engine.core.evaluate_component](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/core.py#L137-L173)

---

<a id="entity-starlayer-shacl-subgraph_extraction-extract_subgraph"></a>
### `extract_subgraph`  _(function)_

```python
def extract_subgraph(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, *, shape: Any | None=None, focus_node: Any | None=None, inference: Any | None=None, include_targets: bool=True) -> Any
```

Returns the subgraph covered by one shape+focus_node pair, or by
every real entry point a whole shapes graph declares.

Like ``StarLayerGraph.cbd()``, but the reachability rule is a SHACL
shape's own constraints instead of blank-node adjacency. See the
module docstring for the full design this follows, including the
four filter combinations and the unified return contract.

``shacl_graph`` is a raw shapes graph (already normalized by the caller,
matching ``evaluate()``'s own calling convention) - wrapped here into a
``pyshacl.ShapesGraph`` so ``lookup_shape_from_node``/shape harvesting
work the same way they do for ``_shape_conforms`` elsewhere in this
codebase. Wrapped over a *copy*, never the caller's own object:
``pyshacl.ShapesGraph.__init__``/``.shapes`` mutates whatever graph it's
given in place (injecting a couple of RDFS/OWL class-hierarchy axiom
triples for its own implicit-class-target support), which would
otherwise silently pollute the caller's ``shacl_graph`` as an unrelated
side effect of calling this function.

``shacl_graph=None`` falls back to ``data_graph`` itself - matching
``validate()``'s own "data graph doubles as shapes graph" allowance,
for a data file carrying its own embedded shapes.

``ont_graph``/``inference=``: entailment feeds the conformance re-check
and the extraction walk, but the returned triples are intersected back
against the real, pre-entailment ``data_graph`` before returning, so an
entailed-only triple never appears in the output - see the module
docstring's entailment section for the full design.

**Parameters:**

- `data_graph: Any` - The full data graph - not a pre-narrowed candidate, since multi-hop paths/nested shapes mean the traversal's real reach can't be known in advance.
- `shacl_graph: Any | None = None` - The shapes graph. Defaults to ``data_graph``.
- `ont_graph: Any | None = None` - Optional ontology graph feeding entailment.
- `shape: Any | None = None` - Restrict to this one shape's own entry point(s). Omit to consider every (non-deactivated) shape in ``shacl_graph``.
- `focus_node: Any | None = None` - Restrict to this one focus node. Omit to discover every real target ``pySHACL``'s own ``Shape.focus_nodes()`` resolves for each candidate shape (declared/implicit targets, including SPARQL-based ``sh:target``).
- `inference: Any | None = None` - An ``ENTAILMENT.*`` regime IRI, or an iterable of them.
- `include_targets: bool = True` - Also return the triples that make each focus node a target of its shape (``sh:targetClass``: its ``rdf:type`` and ``rdfs:subClassOf`` triples; ``sh:targetSubjectsOf`` / ``sh:targetObjectsOf``: the triples with that predicate). The Shape Fragments paper includes them (the shape is conjoined with its target), and without them the fragment no longer says why its nodes were chosen: validating it against the same shapes treats those nodes as no longer targeted and passes vacuously. ``sh:targetNode`` has no such triple. Default ``True``.

**Returns:** `Any` - A new graph - the union of every conforming ``(shape, focus_node)`` pair's own extraction. Empty (never ``None``) if nothing conforms.

**Source:** [starlayer.shacl.subgraph_extraction.extract_subgraph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/subgraph_extraction.py#L525-L642)

---

<a id="entity-starlayer-shacl-engine-normalization-normalize_graph_inputs"></a>
### `normalize_graph_inputs`  _(function)_

```python
def normalize_graph_inputs(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None) -> tuple[Any, Any | None, Any | None]
```

Normalizes a data/shapes/ontology graph, in any shape a caller may
pass, to ``StarLayerGraph`` (or ``None``) via ``normalize_to_starlayer_graph()``.

**Parameters:**

- `data_graph: Any`
- `shacl_graph: Any | None = None`
- `ont_graph: Any | None = None`

**Returns:** `tuple[Any, Any | None, Any | None]`

**Source:** [starlayer.shacl.engine.normalization.normalize_graph_inputs](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/normalization.py#L59-L74)

---

<a id="entity-starlayer-shacl-engine-normalization-normalize_to_starlayer_graph"></a>
### `normalize_to_starlayer_graph`  _(function)_

```python
def normalize_to_starlayer_graph(value: Any, *, name: str, force_default_union: bool=False) -> Any
```

Normalize input graph to StarLayerGraph.

A plain rdflib.Graph is always converted. Existing StarLayerGraph
instances are returned as-is.

**Parameters:**

- `value: Any` - The graph to normalize - a StarLayerGraph, a plain rdflib.Graph, or an rdflib.Dataset/StarLayerDataset.
- `name: str` - The parameter name to use in a TypeError message, so callers get an error naming their own argument rather than this helper's.
- `force_default_union: bool = False` - When ``value`` is an ``rdflib.Dataset`` (or ``StarLayerDataset``, a subclass), setting this mutates ``value.default_union = True`` before conversion - matching pySHACL's own native behavior when given a raw ``Dataset`` directly as ``ont_graph`` (``pyshacl/validator.py``: ``if isinstance(self.ont_graph, rdflib.Dataset): self.ont_graph.default_union = True``), so ontology triples across all named graphs are visible for inference regardless of how the caller constructed the dataset. Not used for ``data_graph``/``shacl_graph`` - pySHACL doesn't auto-union those either, only ``ont_graph``.

**Returns:** `Any` - The normalized StarLayerGraph.

**Source:** [starlayer.shacl.engine.normalization.normalize_to_starlayer_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/normalization.py#L8-L56)

---

<a id="entity-starlayer-shacl-engine-core-target_nodes"></a>
### `target_nodes`  _(function)_

```python
def target_nodes(*, data_graph: Any, shacl_graph: Any | None=None, shape_node: Any, ont_graph: Any | None=None, inference: Any | None=None) -> tuple[Any, ...]
```

Resolve ``shape_node``'s SHACL targets against ``data_graph``.

``shacl_graph=None`` falls back to ``data_graph`` itself - matching
``validate()``'s own "data graph doubles as shapes graph" allowance,
for a data file carrying its own embedded shapes.

``shacl_graph``'s own declared ``sh:entailment`` regime(s) (SHACL 1.2
Core sec 1.4), plus the optional ``inference=`` keyword (same
``ENTAILMENT.*`` vocabulary), are applied once, up front, onto a
private, non-mutating copy of ``data_graph`` - computed over
``data_graph`` union ``ont_graph`` when given (so an axiom declared
only in ``ont_graph``, e.g. ``rdfs:domain``, actually widens
``sh:targetClass`` membership), but only the newly-entailed delta is
materialized - ``ont_graph``'s own raw triples are never copied in.
Neither ``data_graph`` nor ``ont_graph`` is mutated. A no-op when
neither is declared nor passed (the common case).

**Parameters:**

- `data_graph: Any` - The graph to resolve targets against.
- `shacl_graph: Any | None = None` - The graph holding ``shape_node``'s own target declarations. Falls back to ``data_graph`` when ``None``.
- `shape_node: Any` - The shape whose targets to resolve: ``sh:targetNode`` (an IRI, a literal, a ``sh:select`` or a node expression), ``sh:targetClass`` (subclasses included), ``sh:targetSubjectsOf``, ``sh:targetObjectsOf``, ``sh:targetWhere``, ``sh:target`` (SPARQLTarget, via pySHACL's advanced mode), data-graph ``sh:shape`` and implicit class targets. The nodes are the ones ``validate()`` reports on, because the dynamic forms are resolved by the validator's own code (GitHub issue #66).
- `ont_graph: Any | None = None` - An optional ontology graph unioned in for entailment only (see above) - never copied into the result.
- `inference: Any | None = None` - An optional ``ENTAILMENT.*`` IRI (or iterable of them) to apply alongside any regime(s) ``shacl_graph`` itself declares.

**Returns:** `tuple[Any, ...]` - The resolved target nodes, in declaration order, deduplicated.

**Source:** [starlayer.shacl.engine.core.target_nodes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/engine/core.py#L26-L134)

---

<a id="entity-starlayer-shacl-validator-validate"></a>
### `validate`  _(function)_

```python
def validate(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, *, adapter: TripleTermAdapter | None=None, validate_fn: Callable[..., tuple[bool, Graph, str]] | None=None, mode: str | ValidationMode | None=None, decode_report: bool=True, rdfs_subclass_reasoning_includes_shapes_graph: bool=False, shapes_graph_loader: Callable[[Any], Any | None] | None=None, ignore_imports: bool=False, meta_shapes_extra: Iterable[Any]=(), data_graph_iri: Any | None=None, shapes_graph_resource: Any | None=None, shapes_graph_iri: Any | None=None, specification_graph: Any | None=None, include_used_configuration: bool=False, **kwargs: Any) -> ValidationResult
```

Validates ``data_graph`` against ``shacl_graph`` per SHACL 1.2
Core, and returns a ``ValidationResult``.

Applies every SHACL 1.2 pattern this project supports natively first
- entailment, new target types, node expressions, native component
registration, and so on. ``StarShaclSchema.validate()`` keeps its
own, separate copy of this body for now rather than delegating here
- see this module's "two-step flip" note.

**Parameters:**

- `data_graph: Any` - The RDF data to validate. Normalized via ``normalize_graph_inputs`` (any rdflib-compatible graph becomes a ``StarLayerGraph``).
- `shacl_graph: Any | None = None` - The shapes graph. ``None`` lets pySHACL look for shapes embedded directly in ``data_graph`` itself (pySHACL's own "data graph doubles as shapes graph" allowance).
- `ont_graph: Any | None = None` - An optional ontology graph. Its own axioms (e.g. ``rdfs:domain``/``range``) are visible to entailment and to pySHACL's own validation run, but its triples are never copied into ``data_graph``, and it is never mutated.
- `adapter: TripleTermAdapter | None = None` - The ``TripleTermAdapter`` used to encode RDF-1.2 triple terms into the plain RDF-1.1 form pySHACL understands, and decode its report/data back afterward. Defaults to a fresh ``TripleTermAdapter()``.
- `validate_fn: Callable[..., tuple[bool, Graph, str]] | None = None` - The callable actually invoked to perform validation, taking ``data_graph=``/``shacl_graph=``/ ``ont_graph=`` (already encoded) plus every resolved option as keyword arguments, and returning ``(conforms, report_graph, report_text)``. Defaults to ``_default_validate`` (a thin wrapper around ``pyshacl.validate``).
- `mode: str | ValidationMode | None = None` - Selects a named preset bundle of pySHACL options (e.g. ``"validation"``/``"rules"``/``"debug"``) via ``resolve_mode_options()``; any of its options can be overridden per call via ``**kwargs``.
- `decode_report: bool = True` - Whether to decode ``report_graph``'s triple-term encoding back into real RDF-1.2 triple terms, and humanize ``report_text`` to match, before returning. ``False`` returns both in their raw, pySHACL-native encoded form.
- `rdfs_subclass_reasoning_includes_shapes_graph: bool = False` - When ``True``, ``sh:rootClass``'s ``rdfs:subClassOf`` lookups also consult ``shacl_graph``'s own subclass triples (injected into a copy of ``data_graph`` for the duration of the call), not just ``data_graph``'s.
- `shapes_graph_loader: Callable[[Any], Any | None] | None = None` - A loader resolving ``shacl_graph``'s declared ``owl:imports`` (via ``StarLayerGraph.resolve_imports()``). When given, imports are resolved before validation; when omitted, any import that isn't already locally satisfied raises ``ValueError`` unless ``ignore_imports=True``.
- `ignore_imports: bool = False` - Suppresses the "unresolved ``owl:imports``" error above when no ``shapes_graph_loader`` is given - for a ``shacl_graph`` whose imports were already resolved by the caller beforehand (or are deliberately being left unresolved).
- `meta_shapes_extra: Iterable[Any] = ()` - Extra graphs passed through to ``starlayer.shacl.meta_shapes.meta_validate()`` when the resolved options enable ``meta_shacl``.
- `data_graph_iri: Any | None = None` - Recorded on the report as ``sh:usedDataGraph``. Falls back to ``data_graph.identifier`` when that's a real ``URIRef`` (not an anonymous ``BNode``) and no explicit value was given.
- `shapes_graph_resource: Any | None = None` - A named ``sh:ShapesGraph`` module of ``shacl_graph`` to validate against (its IRI becomes ``sh:usedShapesGraph``), or an IRI that is not a module of it, used only as the report's provenance tag. Raises ``ValueError`` when ``shacl_graph`` is ``None``. Same meaning as ``StarShaclSchema.validate()``.
- `shapes_graph_iri: Any | None = None` - Recorded on the report as ``sh:usedShapesGraph``, with the same ``.identifier`` fallback as ``data_graph_iri``.
- `specification_graph: Any | None = None` - Passed to ``starlayer.shacl.profiling.derive_conforms_to()`` so SHACL 1.2 Profiling's second rule can additionally derive a ``dcterms:conformsTo`` triple from an already-derived ``sh:conformsTo`` one - a no-op unless both ``data_graph_iri`` and ``shapes_graph_iri`` resolve to something.
- `include_used_configuration: bool = False` - Whether ``_annotate_used_graphs_and_configuration()`` also records which validation options were in effect, alongside ``sh:usedDataGraph``/``sh:usedShapesGraph``. options (e.g. ``advanced``, ``inplace``, ``meta_shacl``, ``allow_warnings``, ``allow_infos``, ``inference``, ``debug``), forwarded to ``validate_fn``. With the default ``validate_fn`` an option name pySHACL does not know raises ``TypeError`` (pySHACL itself ignores it silently).
- `kwargs: Any`

**Returns:** `ValidationResult` - A ``ValidationResult``: ``conforms`` (bool), ``report_graph``/ ``report_text`` (the validation report, decoded unless ``decode_report=False``), ``data_graph`` (the mutated original when the resolved options include ``inplace=True``, otherwise ``None``), and ``diagnostics`` (an ``ExecutionDiagnostics`` snapshot of adapter encode/decode activity for this call).

**Source:** [starlayer.shacl.validator.validate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L3392-L3810)

---

<a id="entity-starlayer-shacl-validator-validate_each"></a>
### `validate_each`  _(function)_

```python
def validate_each(data_graphs: Iterable[Any], shacl_graph: Any | None=None, ont_graph: Any | None=None, **kwargs: Any) -> dict[int, ValidationResult]
```

Validate each graph in ``data_graphs`` against the same
``shacl_graph``/``ont_graph``, by calling the module-level
``validate()`` function above once per item.
``StarShaclSchema.validate_each()`` keeps its own, separate copy of
this body for now (see ``validate()``'s own docstring).

**Parameters:**

- `data_graphs: Iterable[Any]` - The data graphs to validate, one at a time.
- `shacl_graph: Any | None = None` - The shapes graph shared by every call - see ``validate()``'s own docstring for its ``None`` fallback and every other behavior detail.
- `ont_graph: Any | None = None` - The ontology graph shared by every call - see ``validate()``'s own docstring. (e.g. ``mode``, ``inference``, ``data_graph_iri``, ...).
- `kwargs: Any`

**Returns:** `dict[int, ValidationResult]` - A ``dict`` mapping each item's index in ``data_graphs`` (via ``enumerate``) to its own ``ValidationResult``.

**Source:** [starlayer.shacl.validator.validate_each](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L3813-L3839)

---
