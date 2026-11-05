# StarLayer API Reference (generated)

Generated directly from `tools/kg/codekg/codekg.trig` - every PublicAccess entity's own full signature and docstring, nothing hand-curated. See [api-overview.generated.md](api-overview.generated.md) for the headline-only index this expands on.

## `starlayer`

[Back to overview](api-overview.generated.md#starlayer)

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset"></a>
### `StarLayerDataset`  _(class)_

The whole store. ``default_union`` (default True) makes ``triples`` / ``len`` / ``iter`` / SPARQL's default graph the
union of all graphs, as the engine's graph view does; False restricts them to the default graph (rdflib's ``Dataset``).

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L806-L991)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-clear"></a>
### `StarLayerDataset.clear`  _(method)_

```python
def clear(self) -> StarLayerDataset
```

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.clear](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L954-L957)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-copy"></a>
### `StarLayerDataset.copy`  _(method)_

```python
def copy(self) -> StarLayerDataset
```

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.copy](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L975-L982)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-default_graph"></a>
### `StarLayerDataset.default_graph`  _(method)_

```python
def default_graph(self) -> StarLayerGraph
```

A view of the dataset's default graph (re-made on each access; it shares this dataset's ``prefixes``).

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.default_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L887-L889)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-default_union"></a>
### `StarLayerDataset.default_union`  _(method)_

```python
def default_union(self) -> bool
```

**Returns:** `bool`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.default_union](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L840-L841)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-from_rdflib"></a>
### `StarLayerDataset.from_rdflib`  _(method)_

```python
def from_rdflib(cls, dataset: Any) -> StarLayerDataset
```

A new in-memory ``StarLayerDataset`` from an rdflib ``Dataset`` / ``ConjunctiveGraph`` / ``StarLayerDataset`` (every graph, empty
named graphs too, prefixes, ``default_union``) or from a plain graph (its triples go to the default graph). Terms as in
``StarLayerGraph.from_rdflib``. An ``StarLayerDataset`` is copied.

**Parameters:**

- `dataset: Any`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.from_rdflib](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L820-L829)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-graph"></a>
### `StarLayerDataset.graph`  _(method)_

```python
def graph(self, identifier: Any=None) -> StarLayerGraph
```

A view of one graph (created, empty, if it does not exist yet); shares this dataset's ``prefixes`` dict.

**Parameters:**

- `identifier: Any = None`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L926-L931)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-graph_names"></a>
### `StarLayerDataset.graph_names`  _(method)_

```python
def graph_names(self) -> list[Any]
```

**Returns:** `list[Any]`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.graph_names](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L937-L938)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-graphs"></a>
### `StarLayerDataset.graphs`  _(method)_

```python
def graphs(self) -> list[StarLayerGraph]
```

The default graph, then every named graph (empty ones included).

**Returns:** `list[StarLayerGraph]`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.graphs](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L933-L935)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-has_graph"></a>
### `StarLayerDataset.has_graph`  _(method)_

```python
def has_graph(self, identifier: Any) -> bool
```

**Parameters:**

- `identifier: Any`

**Returns:** `bool`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.has_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L940-L942)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-quads"></a>
### `StarLayerDataset.quads`  _(method)_

```python
def quads(self, pattern: tuple=(None, None, None, None)) -> Iterator[ox.Quad]
```

Quads matching ``(s, p, o[, graph])``; graph ``None`` is any graph (the default graph included).

**Parameters:**

- `pattern: tuple = (None, None, None, None)`

**Returns:** `Iterator[ox.Quad]`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.quads](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L852-L856)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-reifications"></a>
### `StarLayerDataset.reifications`  _(method)_

```python
def reifications(self, s: Any=None, p: Any=None, o: Any=None) -> StarLayerDataset
```

A dataset of the ``rdf:reifies`` triples of every reified triple term matching ``s p o``, per graph.

**Parameters:**

- `s: Any = None`
- `p: Any = None`
- `o: Any = None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.reifications](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L913-L915)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-reified_triples"></a>
### `StarLayerDataset.reified_triples`  _(method)_

```python
def reified_triples(self, reifier: Any) -> StarLayerDataset
```

A dataset of the ``reifier rdf:reifies <triple term>`` triples of ``reifier``, per graph.

**Parameters:**

- `reifier: Any`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.reified_triples](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L921-L923)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-reifier_annotations"></a>
### `StarLayerDataset.reifier_annotations`  _(method)_

```python
def reifier_annotations(self, TT: Any) -> StarLayerDataset
```

A dataset of the annotation triples ``(reifier, predicate, value)`` of every reifier of ``TT``, per graph.

**Parameters:**

- `TT: Any`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.reifier_annotations](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L917-L919)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-reifiers"></a>
### `StarLayerDataset.reifiers`  _(method)_

```python
def reifiers(self, TT: Any=None, predicate: Any=None, object: Any=None) -> StarLayerDataset
```

A dataset of every matching reifier's triples (its ``rdf:reifies`` links and annotations), each kept in the graph it
came from. ``list(reification.reifiers(ds))`` gives the reifier nodes alone.

**Parameters:**

- `TT: Any = None`
- `predicate: Any = None`
- `object: Any = None`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.reifiers](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L908-L911)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-remove"></a>
### `StarLayerDataset.remove`  _(method)_

```python
def remove(self, pattern: tuple) -> StarLayerDataset
```

**Parameters:**

- `pattern: tuple`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.remove](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L878-L884)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-remove_graph"></a>
### `StarLayerDataset.remove_graph`  _(method)_

```python
def remove_graph(self, identifier: Any) -> StarLayerDataset
```

Remove a named graph with its triples (the default graph is emptied).

**Parameters:**

- `identifier: Any`

**Returns:** `StarLayerDataset`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.remove_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L944-L952)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerDataset-to_graph"></a>
### `StarLayerDataset.to_graph`  _(method)_

```python
def to_graph(self) -> StarLayerGraph
```

Every triple of every graph merged into one new in-memory ``StarLayerGraph`` (provenance by graph is lost; equal triples
collapse). It is a copy: it can be queried or compared on its own.

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerDataset.to_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L891-L896)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerGraph"></a>
### `StarLayerGraph`  _(class)_

One graph of a store: the default graph (``identifier=None``) or the named graph ``identifier`` (a ``NamedNode``,
``BlankNode``, or an IRI string).

**Source:** [starlayer.graph.oxgraph.core.StarLayerGraph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L713-L803)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerGraph-clear"></a>
### `StarLayerGraph.clear`  _(method)_

```python
def clear(self) -> StarLayerGraph
```

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerGraph.clear](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L776-L779)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerGraph-copy"></a>
### `StarLayerGraph.copy`  _(method)_

```python
def copy(self) -> StarLayerGraph
```

An independent in-memory copy of this graph (same identifier, own copy of the prefixes). ``copy.copy`` and
``copy.deepcopy`` do the same, also for a graph opened with ``path=``.

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerGraph.copy](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L787-L794)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerGraph-from_rdflib"></a>
### `StarLayerGraph.from_rdflib`  _(method)_

```python
def from_rdflib(cls, graph: Any) -> StarLayerGraph
```

A new in-memory ``StarLayerGraph`` with the triples, prefixes and (when it is an IRI) identifier of an rdflib ``Graph`` or an
old-style ``StarLayerGraph``; a ``TripleTerm`` becomes a triple term, a directional literal in its datatype-IRI form
(what ``to_rdflib`` writes) is restored, and the basic encoding is left as triples (``interop.from_basic`` decodes it).
A term RDF does not allow raises ``TermError`` (``term_policy("lenient")`` stores a stand-in). An ``StarLayerGraph`` is copied.
For an rdflib dataset's named graphs use ``StarLayerDataset.from_rdflib``.

**Parameters:**

- `graph: Any`

**Returns:** `StarLayerGraph`

**Source:** [starlayer.graph.oxgraph.core.StarLayerGraph.from_rdflib](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L724-L737)

---

<a id="entity-starlayer-graph-oxgraph-core-StarLayerGraph-identifier"></a>
### `StarLayerGraph.identifier`  _(method)_

```python
def identifier(self) -> Any
```

**Returns:** `Any`

**Source:** [starlayer.graph.oxgraph.core.StarLayerGraph.identifier](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/core.py#L740-L741)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema"></a>
### `StarShaclSchema`  _(class)_

A shapes graph (and optionally an ontology graph, a default data graph, a scoring graph and an entailment regime), bound once,
to validate, run rules against, or evaluate node expressions over any number of data graphs.

Construct one per shapes set (``PersonSchema = StarShaclSchema(person_shapes)``), then call ``validate`` / ``apply_rules`` /
``evaluate`` with whatever data graph you are checking. ``select_widgets`` needs no data graph: it chooses SHACL 1.2 UI widgets
from the shapes graph alone. Shape-driven subgraph extraction is the plain function ``starlayer.shacl.extract_subgraph()``.

``inference`` is an entailment regime IRI (``ENTAILMENT.RDFS``) or an iterable of them, applied to the data graph of every call
together with the shapes graph's own ``sh:entailment``.

**Source:** [starlayer.shacl.validator.StarShaclSchema](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L224-L504)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-apply_rules"></a>
### `StarShaclSchema.apply_rules`  _(method)_

```python
def apply_rules(self, data_graph: Any | None=None, include_source_rule_provenance: bool=False, rule_set: Any | None=None, shapes_graph_resource: Any | None=None, **kwargs: Any) -> RulesResult
```

Runs the rules of the bound shapes graph over ``data_graph`` (default: the bound one); see :func:`apply_rules`.
``shapes_graph_resource`` selects a named ``sh:ShapesGraph`` module of the bound shapes graph.

**Parameters:**

- `data_graph: Any | None = None`
- `include_source_rule_provenance: bool = False`
- `rule_set: Any | None = None`
- `shapes_graph_resource: Any | None = None`
- `kwargs: Any`

**Returns:** `RulesResult`

**Source:** [starlayer.shacl.validator.StarShaclSchema.apply_rules](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L388-L407)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-close_shape"></a>
### `StarShaclSchema.close_shape`  _(method)_

```python
def close_shape(self, shape: Any, *, shapes_graph_resource: Any | None=None) -> Any
```

The bound shapes graph reduced to ``shape`` and every shape it references (directly or through ``sh:property``,
``sh:node``, ``sh:and``/``sh:or``/``sh:xone``/``sh:not``, ``sh:qualifiedValueShape`` ...): a self-contained shapes graph.

**Parameters:**

- `shape: Any`
- `shapes_graph_resource: Any | None = None`

**Returns:** `Any`

**Source:** [starlayer.shacl.validator.StarShaclSchema.close_shape](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L483-L491)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-data_graph"></a>
### `StarShaclSchema.data_graph`  _(method)_

```python
def data_graph(self) -> Any | None
```

The default data graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.data_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L286-L288)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-evaluate"></a>
### `StarShaclSchema.evaluate`  _(method)_

```python
def evaluate(self, data_graph: Any | None=None, *, shapes_graph_resource: Any | None=None, focus_nodes: Any | None=None, properties: Any | None=None, rules_entailment: bool=False) -> Any
```

Computes the ``sh:values`` / ``sh:defaultValue`` virtual properties of the bound shapes graph over ``data_graph``
(default: the bound one); see :func:`evaluate`.

**Parameters:**

- `data_graph: Any | None = None`
- `shapes_graph_resource: Any | None = None`
- `focus_nodes: Any | None = None`
- `properties: Any | None = None`
- `rules_entailment: bool = False`

**Returns:** `Any`

**Source:** [starlayer.shacl.validator.StarShaclSchema.evaluate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L409-L429)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-extract_shapes_graph"></a>
### `StarShaclSchema.extract_shapes_graph`  _(method)_

```python
def extract_shapes_graph(self, shapes_graph_iri: Any, *, include_referenced: bool=False) -> Any | None
```

Extracts the ``sh:ShapesGraph`` named ``shapes_graph_iri`` as a standalone graph (its members, with their blank-node
closures and the declared prefixes), or ``None`` when the bound shapes graph has no such resource.

With ``include_referenced=True`` the extract also holds every shape the members reference, so it can be validated on its
own; without it, the extract is exactly the module's members, and a ``sh:property`` link to a property shape left behind is
dangling.

**Parameters:**

- `shapes_graph_iri: Any`
- `include_referenced: bool = False`

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.extract_shapes_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L493-L504)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-ont_graph"></a>
### `StarShaclSchema.ont_graph`  _(method)_

```python
def ont_graph(self) -> Any | None
```

The ontology graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.ont_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L277-L279)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-scoring_graph"></a>
### `StarShaclSchema.scoring_graph`  _(method)_

```python
def scoring_graph(self) -> Any | None
```

The scoring graph of ``shui:WidgetScore`` entries, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.scoring_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L295-L297)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-select_widgets"></a>
### `StarShaclSchema.select_widgets`  _(method)_

```python
def select_widgets(self, *, shape_node: Any, focus_node: Any | None=None, role: str, data_graph: Any | None=None, scoring_graph: Any | None=None, shapes_graph_resource: Any | None=None, per: str='node') -> dict[Any, Any]
```

Chooses a SHACL 1.2 UI widget for each property of the node shape ``shape_node``, using the bound shapes graph.

Delegates to :func:`starlayer.shacl.select_widgets`; this method supplies the bound shapes graph, the bound
``scoring_graph`` and (when a ``focus_node`` is given) the bound ``data_graph``. Each can be overridden per call.

**Parameters:**

- `shape_node: Any` - A ``sh:NodeShape`` of the shapes graph; its ``sh:property`` values are walked.
- `focus_node: Any | None = None` - Optional node whose data a matcher's ``shui:dataGraphShape`` is checked against.
- `role: str` - ``"editor"`` or ``"viewer"``.
- `data_graph: Any | None = None` - The graph holding ``focus_node``; only needed when ``focus_node`` is given.
- `scoring_graph: Any | None = None` - Catalog of ``shui:WidgetScore`` / ``shui:WidgetAcceptMatcher`` entries (default: the bound one; pass an empty graph to ignore a bound catalog for one call).
- `shapes_graph_resource: Any | None = None` - A named ``sh:ShapesGraph`` module of the bound shapes graph.
- `per: str = 'node'` - ``"node"`` (the default) or ``"shape"``: with ``"shape"`` the answer is once per property shape, a ``WidgetChoice`` each, to finish per node with ``choice.resolve(focus_node, data_graph)``.

**Returns:** `dict[Any, Any]` - ``{property_shape: widget}``, with ``None`` for a property that has no widget (or ``{property_shape: WidgetChoice}``).

**Source:** [starlayer.shacl.validator.StarShaclSchema.select_widgets](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L431-L481)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-shacl_graph"></a>
### `StarShaclSchema.shacl_graph`  _(method)_

```python
def shacl_graph(self) -> Any | None
```

The shapes graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

**Returns:** `Any | None`

**Source:** [starlayer.shacl.validator.StarShaclSchema.shacl_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L268-L270)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-target_nodes"></a>
### `StarShaclSchema.target_nodes`  _(method)_

```python
def target_nodes(self, *, data_graph: Any | None=None, shape_node: Any, shapes_graph_resource: Any | None=None) -> tuple[Any, ...]
```

The nodes ``shape_node`` targets in ``data_graph`` (default: the bound one), as ``validate()`` resolves them.

**Parameters:**

- `data_graph: Any | None = None`
- `shape_node: Any`
- `shapes_graph_resource: Any | None = None`

**Returns:** `tuple[Any, ...]`

**Source:** [starlayer.shacl.validator.StarShaclSchema.target_nodes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L329-L339)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-validate"></a>
### `StarShaclSchema.validate`  _(method)_

```python
def validate(self, data_graph: Any | None=None, *, mode: str | ValidationMode | None=None, shapes_graph_loader: Callable[[Any], Any | None] | None=None, ignore_imports: bool=False, meta_shapes_extra: Iterable[Any]=(), data_graph_iri: Any | None=None, shapes_graph_resource: Any | None=None, include_used_configuration: bool=False, **kwargs: Any) -> ValidationResult
```

Validates ``data_graph`` (default: the bound data graph) against the bound shapes graph; see :func:`validate`.

``inference`` is bound at construction, not per call (``TypeError`` here). ``shapes_graph_resource`` validates against a
named ``sh:ShapesGraph`` module of the bound shapes graph.

**Parameters:**

- `data_graph: Any | None = None`
- `mode: str | ValidationMode | None = None`
- `shapes_graph_loader: Callable[[Any], Any | None] | None = None`
- `ignore_imports: bool = False`
- `meta_shapes_extra: Iterable[Any] = ()`
- `data_graph_iri: Any | None = None`
- `shapes_graph_resource: Any | None = None`
- `include_used_configuration: bool = False`
- `kwargs: Any`

**Returns:** `ValidationResult`

**Source:** [starlayer.shacl.validator.StarShaclSchema.validate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L341-L378)

---

<a id="entity-starlayer-shacl-validator-StarShaclSchema-validate_each"></a>
### `StarShaclSchema.validate_each`  _(method)_

```python
def validate_each(self, data_graphs: Iterable[Any] | None=None, **kwargs: Any) -> dict[int, ValidationResult]
```

Validates each graph of ``data_graphs`` (default: just the bound data graph) with :meth:`validate`; the shapes are parsed
once for the whole batch. Returns ``{index: ValidationResult}``.

**Parameters:**

- `data_graphs: Iterable[Any] | None = None`
- `kwargs: Any`

**Returns:** `dict[int, ValidationResult]`

**Source:** [starlayer.shacl.validator.StarShaclSchema.validate_each](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L380-L386)

---

## `starlayer.graph`

[Back to overview](api-overview.generated.md#starlayergraph)

<a id="entity-starlayer-graph-rdfc_native-CanonicalizationComplexityError"></a>
### `CanonicalizationComplexityError`  _(class)_

The dataset has a highly symmetric blank-node structure that RDFC-1.0 would take exponential time on (RDFC-1.0
section 7.1, "Dataset Poisoning": implementations MUST terminate early with an exception).

**Source:** [starlayer.graph.rdfc_native.CanonicalizationComplexityError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc_native.py#L33-L35)

---

<a id="entity-starlayer-graph-model-dirlangstring-DirLangString"></a>
### `DirLangString`  _(class)_

An RDF 1.2 directional language-tagged string literal.

Value-typed: two instances with the same (value, language, direction) are
equal and have the same hash. Per RDF 1.2 Concepts sec 3.4.1, a language
tag's case does not participate in the abstract syntax - it is folded to
lowercase here, mirroring rdflib.Literal's existing behaviour for lang=.

**Source:** [starlayer.graph.model.dirlangstring.DirLangString](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/dirlangstring.py#L21-L62)

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

**Source:** [starlayer.graph.model.dirlangstring.DirLangString.n3](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/dirlangstring.py#L54-L56)

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

**Source:** [starlayer.graph.model.triple.TripleTerm](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/triple.py#L30-L130)

---

<a id="entity-starlayer-graph-model-triple-TripleTerm-n3"></a>
### `TripleTerm.n3`  _(method)_

```python
def n3(self, namespace_manager=None)
```

Returns the N3/Turtle-1.2 (``<<( s p o )>>``) text form.

**Parameters:**

- `namespace_manager: None = None`

**Source:** [starlayer.graph.model.triple.TripleTerm.n3](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/model/triple.py#L107-L110)

---

<a id="entity-starlayer-graph-parsers-errors-Turtle12SyntaxError"></a>
### `Turtle12SyntaxError`  _(class)_

Malformed Turtle 1.2 input that the parser cannot recognize as any
valid token or statement form.

**Source:** [starlayer.graph.parsers.errors.Turtle12SyntaxError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/parsers/errors.py#L19-L56)

---

<a id="entity-starlayer-graph-oxgraph-helpers-imports-can_resolve_import"></a>
### `can_resolve_import`  _(function)_

```python
def can_resolve_import(iri: Any, *, loader: Callable[[Any], Any | None]) -> bool
```

Whether ``loader(iri)`` returns a graph (it is called once; there is no cheaper way to ask).

**Parameters:**

- `iri: Any`
- `loader: Callable[[Any], Any | None]`

**Returns:** `bool`

**Source:** [starlayer.graph.oxgraph.helpers.imports.can_resolve_import](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/oxgraph/helpers/imports.py#L22-L24)

---

<a id="entity-starlayer-graph-compare-isomorphic"></a>
### `isomorphic`  _(function)_

```python
def isomorphic(graph1: Any, graph2: Any) -> bool
```

True if the two graphs or datasets (``StarLayerGraph``, ``StarLayerDataset``, ``pyoxigraph.Store``, or rdflib ``Graph`` /
``Dataset``) are equal up to blank-node relabelling: equal canonical N-Quads (RDFC-1.0). Datasets are compared as datasets,
graph names included; a dataset against a plain graph compares the dataset's quads with the graph's triples in the default
graph.

Raises:
    starlayer.graph.rdfc_native.CanonicalizationComplexityError: a highly symmetric blank-node structure that the
        canonicaliser could not finish (see ``rdfc_native``).

**Parameters:**

- `graph1: Any`
- `graph2: Any`

**Returns:** `bool`

**Source:** [starlayer.graph.compare.isomorphic](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/compare.py#L48-L60)

---

<a id="entity-starlayer-graph-rdfc-rdfc10_hash"></a>
### `rdfc10_hash`  _(function)_

```python
def rdfc10_hash(graph: Any, hash_algorithm: str='sha256') -> str
```

The hex digest of ``graph``'s canonical N-Quads text, stable under blank-node relabelling.

Raises:
    ValueError: a hash algorithm other than ``"sha256"`` or ``"sha384"``.
    CanonicalizationComplexityError: a highly symmetric blank-node structure.

**Parameters:**

- `graph: Any`
- `hash_algorithm: str = 'sha256'`

**Returns:** `str`

**Source:** [starlayer.graph.rdfc.rdfc10_hash](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc.py#L36-L43)

---

<a id="entity-starlayer-graph-rdfc-to_canonical_nquads"></a>
### `to_canonical_nquads`  _(function)_

```python
def to_canonical_nquads(graph: Any, hash_algorithm: str='sha256') -> str
```

The canonical N-Quads text of ``graph`` (RDFC-1.0 section 4.4.3 step 7): blank nodes labelled ``c14n0``, ``c14n1``, ...,
lines sorted. ``hash_algorithm`` is ``"sha256"`` or ``"sha384"`` (the two the specification names); it also drives the
canonical labelling.

Raises:
    ValueError: another hash algorithm.
    CanonicalizationComplexityError: a highly symmetric blank-node structure.

**Parameters:**

- `graph: Any`
- `hash_algorithm: str = 'sha256'`

**Returns:** `str`

**Source:** [starlayer.graph.rdfc.to_canonical_nquads](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/graph/rdfc.py#L24-L33)

---

## `starlayer.shacl`

[Back to overview](api-overview.generated.md#starlayershacl)

<a id="entity-starlayer-shacl_engine-expressions-EvaluationFailure"></a>
### `EvaluationFailure`  _(class)_

A node expression has no result for this data (Node Expressions 3.3), as opposed to an empty result.

**Source:** [starlayer.shacl_engine.expressions.EvaluationFailure](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl_engine/expressions.py#L46-L47)

---

<a id="entity-starlayer-shacl-results-ExecutionDiagnostics"></a>
### `ExecutionDiagnostics`  _(class)_

Counters of one validation run: the type of ``ValidationResult.diagnostics``. The engine handles RDF 1.2 triple terms
natively, so the encode/decode counters stay 0 (kept so code that reads them keeps working). Not a type you'd construct
directly.

**Source:** [starlayer.shacl.results.ExecutionDiagnostics](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L8-L23)

---

<a id="entity-starlayer-shacl_engine-meta-MetaShaclError"></a>
### `MetaShaclError`  _(class)_

The shapes graph does not validate against the meta-shapes; the message starts with the old preflight's text.

**Source:** [starlayer.shacl_engine.meta.MetaShaclError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl_engine/meta.py#L23-L24)

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

<a id="entity-starlayer-shacl_engine-rules-RuleError"></a>
### `RuleError`  _(class)_

A rule failed, or the rules graph is ill-formed or needs something unsupported (the rule set fails as a whole).

**Source:** [starlayer.shacl_engine.rules.RuleError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl_engine/rules.py#L59-L60)

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

**Source:** [starlayer.shacl.results.RulesResult](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L44-L72)

---

<a id="entity-starlayer-shacl_engine-plan-ShapeError"></a>
### `ShapeError`  _(class)_

The shapes graph is malformed (the W3C suite's ``sht:Failure`` cases).

**Source:** [starlayer.shacl_engine.plan.ShapeError](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl_engine/plan.py#L19-L20)

---

<a id="entity-starlayer-shacl-types-StarLayerGraphProtocol"></a>
### `StarLayerGraphProtocol`  _(class)_

Structural protocol every graph-like input to this package must
satisfy: a bound ``namespace_manager`` plus iterability over triples.

**Source:** [starlayer.shacl.types.StarLayerGraphProtocol](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/types.py#L7-L15)

---

<a id="entity-starlayer-shacl-results-ValidationResult"></a>
### `ValidationResult`  _(class)_

Result of ``validate()``: whether the data conforms, the validation report as a graph and as text.

``data_graph`` is only populated when the call used ``inplace=True``
(the ``"rules"`` mode's own default) - the caller's own data graph,
mutated with any in-place changes decoded back; ``None`` otherwise,
not an error. ``diagnostics`` is an ``ExecutionDiagnostics``.

**Source:** [starlayer.shacl.results.ValidationResult](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/results.py#L27-L40)

---

<a id="entity-starlayer-shacl-validator-apply_rules"></a>
### `apply_rules`  _(function)_

```python
def apply_rules(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, include_source_rule_provenance: bool=False, rule_set: Any | None=None, **kwargs: Any) -> RulesResult
```

Executes the SHACL rules of ``shacl_graph`` against a working copy of ``data_graph``, then validates the result.

Covers ``sh:TripleRule`` and ``sh:SPARQLRule`` (shape-attached, in rule sets, or global) and ``sh:sourceRule`` provenance.
``data_graph`` is never changed.

**Parameters:**

- `data_graph: Any` - The data the rules run over: an Oxigraph-backed graph (an rdflib / old-style ``StarLayerGraph`` is copied into one).
- `shacl_graph: Any | None = None` - The shapes graph holding the rules; ``None`` reads them from ``data_graph``.
- `ont_graph: Any | None = None` - An optional ontology graph, visible to entailment only.
- `include_source_rule_provenance: bool = False` - Record, for every inferred triple, a reifier ``_:r rdf:reifies <<( s p o )>>`` with ``_:r sh:sourceRule <rule>`` (Inference Rules section 9).
- `rule_set: Any | None = None` - Run only the rules of this ``sh:RuleSet`` (an IRI, or an iterable of IRIs). ``max_iterations`` (default 1000: more iterations than that without reaching a fixpoint raise ``RuleError``) and ``max_triples`` (stop when more triples than that are inferred).
- `kwargs: Any`

**Returns:** `RulesResult` - A ``RulesResult``: ``inferred_graph`` holds only the triples the rules produced (and the ``sh:sourceRule`` reifiers); ``validation`` is the ``ValidationResult`` over the complete evaluation graph: base, inferred and entailed triples.

**Source:** [starlayer.shacl.validator.apply_rules](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L133-L168)

---

<a id="entity-starlayer-shacl-profiling-declared_conformance_profile"></a>
### `declared_conformance_profile`  _(function)_

```python
def declared_conformance_profile() -> Any
```

A fresh copy of starlayer.shacl's self-declared SHACL 1.2
conformance statement (S3) - the starlayer.shacl resource in the
library's one conformance file. Parses the bundled asset fresh on every
call rather than caching - matching this project's convention
elsewhere (see starontology/__init__.py::_file_graph) of never
sharing one mutable graph object across callers.

**Returns:** `Any` - A fresh ``StarLayerGraph`` containing the bundled conformance statement.

**Source:** [starlayer.shacl.profiling.declared_conformance_profile](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/profiling.py#L102-L118)

---

<a id="entity-starlayer-shacl-profiling-derive_conforms_to"></a>
### `derive_conforms_to`  _(function)_

```python
def derive_conforms_to(report_graph: Any, *, data_graph: Any | None=None, shapes_graph: Any | None=None, specification_graph: Any | None=None, conforms_only: bool=False) -> Any
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
- `data_graph: Any | None = None` - The data graph as an RDF resource - an IRI or IRI-like string, using whatever identity scheme the caller's application already uses (a dataset-catalog IRI, a named-graph IRI - there is no single right default). Optional: if the report was produced by ``validate(..., data_graph_iri=..., shapes_graph_resource=...)``, the matching ``sh:usedDataGraph`` triple is already on the report and is read from there when this is omitted.
- `shapes_graph: Any | None = None` - The shapes graph as an RDF resource, same optionality and fallback as ``data_graph`` (read from the report's own ``sh:usedShapesGraph`` when omitted).
- `specification_graph: Any | None = None` - A graph relating ``shapes_graph`` to what it profiles - either ``prof:isProfileOf`` on ``shapes_graph`` itself, or a ``prof:Profile`` that lists it as a ``role:validation`` ``prof:hasResource`` artifact (e.g. ``starontology.get_conformance_profiles()``) - to additionally derive ``dcterms:conformsTo`` triples via S5.5's second rule (see above). Read, never mutated. ``None`` (the default) skips this second rule entirely.
- `conforms_only: bool = False` - If ``True``, the returned graph contains *only* the ``sh:conformsTo``/``dcterms:conformsTo`` triples themselves - not ``report_graph``, and not even the ``sh:validationReport`` link this function otherwise adds (that link exists to justify the conformance claim with a path back to the report, which ``conforms_only`` says isn't wanted) - useful when a caller only cares about the conformance claims themselves, e.g. to merge into a dataset catalog entry that has no reason to reference a SHACL validation report at all. If ``False`` (the default), the returned graph is ``report_graph`` merged with whatever got newly derived - a self-contained, immediately printable/serializable result, where the added ``sh:validationReport`` link resolves to a real, fully-described node rather than a dangling blank-node reference.

**Returns:** `Any` - A new ``StarLayerGraph``. ``report_graph``/``specification_graph`` are read, never mutated.

**Source:** [starlayer.shacl.profiling.derive_conforms_to](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/profiling.py#L148-L277)

---

<a id="entity-starlayer-shacl-validator-evaluate"></a>
### `evaluate`  _(function)_

```python
def evaluate(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, *, inference: Any | None=None, focus_nodes: Any | None=None, properties: Any | None=None, rules_entailment: bool=False) -> Any
```

Computes the ``sh:values`` / ``sh:defaultValue`` virtual properties of ``shacl_graph`` and returns a shape-driven subgraph.

The returned graph holds, for each property shape with a simple ``sh:path``, its stored values for the shape's own focus nodes
with the computed values unioned in (``sh:defaultValue`` only when there is no stored value), never the whole of
``data_graph``. ``data_graph`` is not changed, and the result is not meant to be persisted: virtual values are computed on
demand.

**Parameters:**

- `data_graph: Any` - The RDF data to evaluate over.
- `shacl_graph: Any | None = None` - The shapes graph; ``None`` reads the shapes from ``data_graph``.
- `ont_graph: Any | None = None` - An optional ontology graph, visible to entailment only.
- `inference: Any | None = None` - An entailment regime IRI (or an iterable of them), applied together with the shapes graph's own ``sh:entailment`` before evaluating.
- `focus_nodes: Any | None = None` - Restrict evaluation to these focus nodes (``None``: every node the shapes target).
- `properties: Any | None = None` - Restrict evaluation to property shapes with one of these ``sh:path`` IRIs (``None``: all).
- `rules_entailment: bool = False` - Also run the rules the shapes graph names in ``sh:entailment`` first.

**Returns:** `Any`

**Source:** [starlayer.shacl.validator.evaluate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L95-L130)

---

<a id="entity-starlayer-shacl-node_expression_api-evaluate_expression"></a>
### `evaluate_expression`  _(function)_

```python
def evaluate_expression(shapes_graph: Any, data_graph: Any, expression: Any, focus: Any=None, *, scope: Mapping[Any, Any] | None=None) -> list
```

The nodes ``expression`` gives for ``focus`` over ``data_graph``, in order.

``shapes_graph`` holds the expression and what it refers to (shapes, declared functions). ``scope`` binds variables
(``shnex:var "name"``) by name to a term or a list of terms, and the arguments of a function call by position (``0``, ``1``,
...); ``focusNode`` is the focus node unless given. An expression that has an evaluation failure raises
``EvaluationFailure`` (SHACL 1.2 Node Expressions 3.2). A ``sh:targetNode`` expression is evaluated with the shape as the focus node
(Core 3.1.3.1): pass the shape.

**Parameters:**

- `shapes_graph: Any`
- `data_graph: Any`
- `expression: Any`
- `focus: Any = None`
- `scope: Mapping[Any, Any] | None = None`

**Returns:** `list`

**Source:** [starlayer.shacl.node_expression_api.evaluate_expression](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/node_expression_api.py#L19-L55)

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

``shacl_graph`` and ``data_graph`` are never changed.

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
- `focus_node: Any | None = None` - Restrict to this one focus node. Omit to discover every real target of each candidate shape (declared and implicit targets).
- `inference: Any | None = None` - An ``ENTAILMENT.*`` regime IRI, or an iterable of them.
- `include_targets: bool = True` - Also return the triples that make each focus node a target of its shape (``sh:targetClass``: its ``rdf:type`` and ``rdfs:subClassOf`` triples; ``sh:targetSubjectsOf`` / ``sh:targetObjectsOf``: the triples with that predicate). The Shape Fragments paper includes them (the shape is conjoined with its target), and without them the fragment no longer says why its nodes were chosen: validating it against the same shapes treats those nodes as no longer targeted and passes vacuously. ``sh:targetNode`` has no such triple. Default ``True``.

**Returns:** `Any` - A new graph - the union of every conforming ``(shape, focus_node)`` pair's own extraction. Empty (never ``None``) if nothing conforms.

**Source:** [starlayer.shacl.subgraph_extraction.extract_subgraph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/subgraph_extraction.py#L114-L178)

---

<a id="entity-starlayer-shacl-shape_types-infer_types"></a>
### `infer_types`  _(function)_

```python
def infer_types(shapes_graph: Any) -> Any
```

The ``rdf:type`` triples ``shapes_graph``'s structure entails and it does not already state, as an ``StarLayerGraph``.

``shapes_graph`` is read as data and left unchanged. Needs the optional ``owlrl`` dependency (for the RDFS step).

**Parameters:**

- `shapes_graph: Any`

**Returns:** `Any`

**Source:** [starlayer.shacl.shape_types.infer_types](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/shape_types.py#L50-L94)

---

<a id="entity-starlayer-shacl-paths-is_inverse"></a>
### `is_inverse`  _(function)_

```python
def is_inverse(shapes_graph: Any, path: Any) -> bool
```

Whether ``path`` is an inverse path (``[ sh:inversePath <p> ]``) at its top level. A sequence or alternative that contains
one is not.

**Parameters:**

- `shapes_graph: Any`
- `path: Any`

**Returns:** `bool`

**Source:** [starlayer.shacl.paths.is_inverse](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/paths.py#L30-L34)

---

<a id="entity-starlayer-shacl-node_expression_api-node_expression_functions"></a>
### `node_expression_functions`  _(function)_

```python
def node_expression_functions() -> list[str]
```

The SPARQL functions and operators a node expression can call (``[ sparql:concat ( ... ) ]``), as IRIs, sorted.

**Returns:** `list[str]`

**Source:** [starlayer.shacl.node_expression_api.node_expression_functions](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/node_expression_api.py#L58-L62)

---

<a id="entity-starlayer-shacl-node_expression_api-node_expression_operators"></a>
### `node_expression_operators`  _(function)_

```python
def node_expression_operators() -> list[str]
```

The SHACL node expression operators (``shnex:filterShape``, ``shnex:pathValues``, ``shnex:if``, ...), as IRIs, sorted.

**Returns:** `list[str]`

**Source:** [starlayer.shacl.node_expression_api.node_expression_operators](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/node_expression_api.py#L65-L69)

---

<a id="entity-starlayer-shacl-normalization-normalize_graph_inputs"></a>
### `normalize_graph_inputs`  _(function)_

```python
def normalize_graph_inputs(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None) -> tuple[Any, Any | None, Any | None]
```

Normalizes a data/shapes/ontology graph, in any shape a caller may
pass, to an Oxigraph-backed graph (or ``None``) via ``normalize_to_starlayer_graph()``.

**Parameters:**

- `data_graph: Any`
- `shacl_graph: Any | None = None`
- `ont_graph: Any | None = None`

**Returns:** `tuple[Any, Any | None, Any | None]`

**Source:** [starlayer.shacl.normalization.normalize_graph_inputs](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/normalization.py#L45-L60)

---

<a id="entity-starlayer-shacl-normalization-normalize_to_starlayer_graph"></a>
### `normalize_to_starlayer_graph`  _(function)_

```python
def normalize_to_starlayer_graph(value: Any, *, name: str, force_default_union: bool=False) -> Any
```

Normalize an input graph to an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``).

An ``StarLayerGraph`` or ``StarLayerDataset`` is returned as it is; a bare ``pyoxigraph.Store`` becomes an ``StarLayerDataset`` over it. A plain
``rdflib.Graph`` or an old-style ``StarLayerGraph`` is converted to an ``StarLayerGraph`` copy (``from_rdflib``: a supported input;
literals Oxigraph normalises on insert, such as ``"04"^^xsd:integer``, come out normalised).

**Parameters:**

- `value: Any` - The graph to normalize.
- `name: str` - The parameter name to use in a TypeError message, so callers get an error naming their own argument.
- `force_default_union: bool = False` - Whether a dataset's named graphs must all be visible (the ontology graph: its axioms count wherever they sit). An ``StarLayerDataset`` without ``default_union`` is viewed through one that has it (the caller's object is not changed); a rdflib dataset has ``default_union`` set on it, as before.

**Returns:** `Any`

**Source:** [starlayer.shacl.normalization.normalize_to_starlayer_graph](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/normalization.py#L6-L42)

---

<a id="entity-starlayer-shacl-meta_shapes-parameter_value_shapes"></a>
### `parameter_value_shapes`  _(function)_

```python
def parameter_value_shapes(shapes_graph: Any) -> Any
```

Shapes that check what a shapes graph gives for the parameters of its constraint components, as an ``StarLayerGraph``.

SPARQL Extensions 4.2.1: "Shapes that do not conform with the constraints declared for the parameters are ill-formed." A parameter
of a ``sh:ConstraintComponent`` is a property shape (``sh:datatype``, ``sh:nodeKind``, ``sh:class``, ``sh:in``, ...) for the values a
shape gives that property. This returns a graph holding each such parameter as a property shape that targets the subjects of its
``sh:path``, so validating ``shapes_graph`` against it (alone or added to the meta-shapes) reports a shape whose value for the property
breaks the parameter's own constraints, for example text given for an ``xsd:integer`` parameter. The engine does not check this: a
query comparing text with a number silently finds nothing.

Only a parameter whose path is an IRI is used; the parameter's own triples (and what hangs from its blank nodes) are copied, so the
returned graph shares no blank node with ``shapes_graph`` beyond the parameter's own label.

**Parameters:**

- `shapes_graph: Any`

**Returns:** `Any`

**Source:** [starlayer.shacl.meta_shapes.parameter_value_shapes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/meta_shapes.py#L54-L141)

---

<a id="entity-starlayer-shacl-paths-path_values"></a>
### `path_values`  _(function)_

```python
def path_values(data_graph: Any, focus: Any, path: Any, shapes_graph: Any | None=None) -> frozenset[Any]
```

The value nodes at the end of ``path``, followed from ``focus`` through ``data_graph``, as pyoxigraph terms.

``path`` is a predicate IRI or the root of a path expression written in ``shapes_graph`` (default: ``data_graph``).
Repetition paths stop on a cycle. Raises ``ShapeError`` for a path expression that is malformed.

**Parameters:**

- `data_graph: Any`
- `focus: Any`
- `path: Any`
- `shapes_graph: Any | None = None`

**Returns:** `frozenset[Any]`

**Source:** [starlayer.shacl.paths.path_values](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/paths.py#L18-L27)

---

<a id="entity-starlayer-shacl-ui_widget_selection-select_widget"></a>
### `select_widget`  _(function)_

```python
def select_widget(*, shape_node: Any, focus_node: Any | None=None, data_graph: Any | None=None, shapes_graph: Any, scoring_graph: Any | None=None, role: Role) -> Any | None
```

Select the ``shui:editor``/``shui:viewer`` widget ``shape_node``
should use for ``focus_node``, per the spec's own Section 3.2 "Select
Function" procedure:

1. Prepare the scores (SHACL UI 4.3): for each widget ``shape_node`` names with ``shui:editor``/``shui:viewer`` that no
   ``shui:WidgetScore`` of ``scoring_graph`` is for, add a score of ``default_widget_score`` (the ``shui:defaultWidgetScore`` of the
   configuration in ``shapes_graph``, else 40). A widget the scoring graph scores at all keeps only its own scores, whether or not they
   cover this shape (the draft says so).
2. Collect every ``shui:WidgetScore`` in ``scoring_graph`` with both a ``shui:widget`` and a ``shui:score``, with those added,
   ranked highest-score-first and then by widget IRI.
3. Walk that ranked list and return the first entry whose conditions hold: the
   ``shui:shapesGraphShape`` / ``shui:dataGraphShape`` written on the score itself (none means it applies
   to everything, as an added score does for this shape), and then, if its widget has a ``shui:WidgetAcceptMatcher``, that matcher too.
   Conditions on a score are local to it, so a catalog layered on top can add a score for a widget another
   layer conditioned without having to remove anything; a per-widget matcher is shared by every layer.

Returns ``None`` if nothing matches at all. ``data_graph``/
``shapes_graph``/``scoring_graph`` may be the same object - the spec
doesn't require them to be separate graphs, just separate *roles*.

``focus_node`` and ``data_graph`` are optional. They are used only to
check a matcher's ``shui:dataGraphShape``. With no ``focus_node`` a matcher
that has only a data condition rejects its widget (Section 3.4 step 1),
while one with a ``shui:shapesGraphShape`` is decided by that alone, so
the choice is per shape rather than per node. Passing a ``focus_node``
without a ``data_graph`` raises ``ValueError``.

**``role`` limits the candidates in the scoring catalog to that role.** The draft's Select Function
(Section 3.2) takes a widget predicate and its Score Function (Section 3.5) lists every ``shui:WidgetScore``
without a type, but Sections 4.1 and 4.2 say an editor is chosen for ``shui:editor`` and a viewer for
``shui:viewer``. A widget counts as an editor if it is one of the draft's built-in editors (Section 9.1) or the
catalog or shapes graph types it ``shui:Editor`` (or ``shui:SingleEditor``/``shui:MultiEditor``), and as a
viewer likewise (Section 9.2). A widget with no known role, such as a custom one, is a candidate for both. A
widget the shape names itself with ``shui:editor``/``shui:viewer`` is not checked. So a property with only
viewers in the catalog gets ``None`` for ``role="editor"`` (GitHub issue #9).

``scoring_graph`` is optional: omit it (or pass ``None``) when widgets
are fixed in the shapes graph and there is no scoring catalog - an
explicit ``shui:editor``/``shui:viewer`` is then accepted outright, and a
property with none gets ``None``.

**Parameters:**

- `shape_node: Any`
- `focus_node: Any | None = None`
- `data_graph: Any | None = None`
- `shapes_graph: Any`
- `scoring_graph: Any | None = None`
- `role: Role`

**Returns:** `Any | None`

**Source:** [starlayer.shacl.ui_widget_selection.select_widget](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/ui_widget_selection.py#L356-L411)

---

<a id="entity-starlayer-shacl-ui_widget_selection-select_widgets"></a>
### `select_widgets`  _(function)_

```python
def select_widgets(*, shape_node: Any, focus_node: Any | None=None, data_graph: Any | None=None, shapes_graph: Any, scoring_graph: Any | None=None, role: Role, per: Literal['node', 'shape']='node') -> dict[Any, Any]
```

Batch sibling of :func:`select_widget` - walks ``shape_node``'s own
``sh:property`` list and runs :func:`select_widget` once per property,
returning ``{property_shape: widget}`` for the given ``role``
(``"editor"`` or ``"viewer"``). Every ``sh:property`` of ``shape_node``
is a key.

``shape_node`` is a ``sh:NodeShape`` here (unlike :func:`select_widget`,
whose own ``shape_node`` is a single property shape) - its
``sh:property`` list is exactly what's walked.

A property for which :func:`select_widget` returns ``None`` maps to
``None``, so the dict always lists every property of the shape.

``focus_node``, ``data_graph`` and ``scoring_graph`` are optional, as
for :func:`select_widget`.

**``per="shape"``** (GitHub issue #14) answers once per property shape instead of once per node, for a UI that
shows many nodes of the same shape. It returns ``{property_shape: WidgetChoice}``; the expensive checks (a
condition's ``shui:shapesGraphShape``) are done once, and ``choice.resolve(focus_node, data_graph)`` finishes the
choice for one node by validating only the conditions that read its data. ``choice.needs_data`` False means one
answer (``choice.widget_without_data``) serves every node. The result of ``resolve`` is the same as
``select_widget`` with that node. ``focus_node`` and ``data_graph`` are not accepted with ``per="shape"``.

**Parameters:**

- `shape_node: Any`
- `focus_node: Any | None = None`
- `data_graph: Any | None = None`
- `shapes_graph: Any`
- `scoring_graph: Any | None = None`
- `role: Role`
- `per: Literal['node', 'shape'] = 'node'`

**Returns:** `dict[Any, Any]`

**Source:** [starlayer.shacl.ui_widget_selection.select_widgets](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/ui_widget_selection.py#L545-L602)

---

<a id="entity-starlayer-shacl-shapes_graphs-shapes_graph_members"></a>
### `shapes_graph_members`  _(function)_

```python
def shapes_graph_members(graph: Any, shapes_graph: Any) -> frozenset[Any] | None
```

The elements that belong to ``shapes_graph`` by ``rdfs:member``, ``rdfs:isDefinedBy`` or ``owl:imports`` (see the module
docstring): every kind of element, not only shapes (a property group or a constraint component says ``rdfs:isDefinedBy`` too).

``None`` when ``shapes_graph`` is not typed ``sh:Graph``, one of its roles or a declared subclass in ``graph``: not every graph
declares this optional metadata, and a mistyped IRI should not look like an empty module. The graph nodes themselves are not
members. Raises ``ValueError`` for an ``owl:imports`` target that is not such a graph in ``graph`` (see ``module_nodes``).

**Parameters:**

- `graph: Any`
- `shapes_graph: Any`

**Returns:** `frozenset[Any] | None`

**Source:** [starlayer.shacl.shapes_graphs.shapes_graph_members](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/shapes_graphs.py#L48-L55)

---

<a id="entity-starlayer-shacl-meta_shapes-sparql_query_problems"></a>
### `sparql_query_problems`  _(function)_

```python
def sparql_query_problems(shapes_graph: Any) -> Iterator[tuple[Any, Any, str]]
```

Each defect of an embedded query as ``(the node that holds it, sh:select/sh:ask/sh:construct, what is wrong)``: text that is not SPARQL,
a query of another form than the predicate says (a SELECT in ``sh:construct``), or one that fails the SPARQL structure check (see
``check_sparql_query_text``, which raises the first). A tool shows these next to the other problems of a shapes graph.

**Parameters:**

- `shapes_graph: Any`

**Returns:** `Iterator[tuple[Any, Any, str]]`

**Source:** [starlayer.shacl.meta_shapes.sparql_query_problems](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/meta_shapes.py#L396-L441)

---

<a id="entity-starlayer-shacl-validator-target_nodes"></a>
### `target_nodes`  _(function)_

```python
def target_nodes(*, data_graph: Any, shacl_graph: Any | None=None, shape_node: Any, ont_graph: Any | None=None, inference: Any | None=None) -> tuple[Any, ...]
```

The nodes ``shape_node`` targets in ``data_graph``, in declaration order and without duplicates: the nodes ``validate()``
reports on for that shape (``sh:targetNode``, including a node expression, ``sh:targetClass`` with subclasses,
``sh:targetSubjectsOf``, ``sh:targetObjectsOf``, ``sh:targetWhere``, data-graph ``sh:shape`` and implicit class targets).

``shacl_graph=None`` reads the shapes from ``data_graph``. The shapes graph's own ``sh:entailment`` and ``inference`` (an
entailment regime IRI or an iterable of them) are applied first, over the data graph and ``ont_graph``, without changing
either.

**Parameters:**

- `data_graph: Any`
- `shacl_graph: Any | None = None`
- `shape_node: Any`
- `ont_graph: Any | None = None`
- `inference: Any | None = None`

**Returns:** `tuple[Any, ...]`

**Source:** [starlayer.shacl.validator.target_nodes](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L171-L188)

---

<a id="entity-starlayer-shacl-validator-validate"></a>
### `validate`  _(function)_

```python
def validate(data_graph: Any, shacl_graph: Any | None=None, ont_graph: Any | None=None, *, mode: str | ValidationMode | None=None, shapes_graph_loader: Callable[[Any], Any | None] | None=None, ignore_imports: bool=False, meta_shapes_extra: Iterable[Any]=(), data_graph_iri: Any | None=None, shapes_graph_resource: Any | None=None, shapes_graph_iri: Any | None=None, specification_graph: Any | None=None, include_used_configuration: bool=False, **kwargs: Any) -> ValidationResult
```

Validates ``data_graph`` against ``shacl_graph`` per SHACL 1.2 and returns a ``ValidationResult``.

**Parameters:**

- `data_graph: Any` - The RDF data to validate: an ``StarLayerGraph`` / ``StarLayerDataset`` (used as it is) or an rdflib / old-style ``StarLayerGraph`` (copied into an ``StarLayerGraph``). It is never changed unless ``inplace=True``.
- `shacl_graph: Any | None = None` - The shapes graph. ``None`` reads the shapes from ``data_graph`` itself.
- `ont_graph: Any | None = None` - An optional ontology graph. Its axioms (``rdfs:domain``, ``rdfs:subClassOf`` ...) are visible to entailment, but its triples are never copied into ``data_graph``.
- `mode: str | ValidationMode | None = None` - A named preset of options (``"validation"``, ``"rules"`` or ``"debug"``); any of its options can be overridden per call through ``**kwargs``.
- `shapes_graph_loader: Callable[[Any], Any | None] | None = None` - Resolves the shapes graph's ``owl:imports``. With no loader, an import that is not already in the graph raises ``ValueError`` unless ``ignore_imports=True``.
- `ignore_imports: bool = False` - Do not complain about imports that cannot be resolved.
- `meta_shapes_extra: Iterable[Any] = ()` - Extra graphs for the shapes-about-shapes check when ``meta_shacl=True``. to the graph's own identifier when that is an IRI.
- `data_graph_iri: Any | None = None`
- `shapes_graph_resource: Any | None = None` - Validate against a named ``sh:ShapesGraph`` module of ``shacl_graph`` (its IRI becomes ``sh:usedShapesGraph``), or, for an IRI that is not a module of it, only tag the report with that IRI.
- `shapes_graph_iri: Any | None = None`
- `specification_graph: Any | None = None` - Lets Profiling derive ``dcterms:conformsTo`` from the derived ``sh:conformsTo``.
- `include_used_configuration: bool = False` - Also record the options in effect on the report. ``inplace``, ``meta_shacl``, ``advanced`` (False: do not run rules), ``allow_warnings``, ``allow_infos``, ``abort_on_first``, ``max_validation_depth``, ``invalid_terms`` (``"lenient"``: process terms that are not RDF terms, such as a relative IRI, as opaque stand-ins instead of raising ``TermError``). An unknown option is a ``TypeError``.
- `kwargs: Any`

**Returns:** `ValidationResult` - A ``ValidationResult``: ``conforms``, ``report_graph`` (an ``StarLayerGraph``) and ``report_text``, ``data_graph`` (the caller's graph when ``inplace=True``, else ``None``) and ``diagnostics``.

**Source:** [starlayer.shacl.validator.validate](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L20-L80)

---

<a id="entity-starlayer-shacl-validator-validate_each"></a>
### `validate_each`  _(function)_

```python
def validate_each(data_graphs: Iterable[Any], shacl_graph: Any | None=None, ont_graph: Any | None=None, **kwargs: Any) -> dict[int, ValidationResult]
```

Validates each graph of ``data_graphs`` against the same ``shacl_graph`` / ``ont_graph``; the shapes are parsed once for the
whole batch. ``kwargs`` are those of :func:`validate`. Returns ``{index: ValidationResult}``.

**Parameters:**

- `data_graphs: Iterable[Any]`
- `shacl_graph: Any | None = None`
- `ont_graph: Any | None = None`
- `kwargs: Any`

**Returns:** `dict[int, ValidationResult]`

**Source:** [starlayer.shacl.validator.validate_each](https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/shacl/validator.py#L83-L92)

---
