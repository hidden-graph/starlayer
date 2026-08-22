# starshacl

`starshacl` adds SHACL 1.2 validation to the StarLayer stack.

It is designed for RDF data that needs the richer validation capabilities of SHACL 1.2, including support for RDF 1.2 data values such as triple terms and direction-tagged literals. The package builds on `pyshacl` while extending the data model so SHACL constraints and rules can work with RDF 1.2 concepts without losing compatibility with the normal SHACL validation workflow.

This makes it useful for validating graphs that include reified statements, triple terms, and other RDF 1.2 constructs, while also supporting the broader SHACL 1.2 feature set used for graph validation and rule-driven data processing.

## Install

This package is not yet published to PyPI. For local development, install it from the repository checkout together with the graph and SPARQL packages:

```bash
pip install -e packages/graph -e packages/sparql -e packages/shacl
```



## What it does

- **Validates RDF data with SHACL 1.2** — checks whether a graph conforms to a shapes graph using the richer SHACL 1.2 feature set.
- **Supports RDF 1.2 values** — works with triple terms, reified statements, and direction-tagged literals.
- **Handles advanced SHACL constraints** — supports the richer predicate and validation patterns introduced in SHACL 1.2.
- **Works with RDF 1.2-aware graph data** — integrates directly with the StarLayer graph layer supporting  RDF 1.2 graphs.
- **Provides structured results** — exposes validation outcomes and diagnostics.

## Quick Start

```python
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ; ex:age 30 .
    ex:bob a ex:Person .
""", format="turtle")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    ex:PersonShape a sh:NodeShape ;
      sh:targetClass ex:Person ;
      sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:datatype xsd:integer ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)

print(result.conforms)      # False - ex:bob has no ex:age
print(result.report_text)   # human-readable SHACL validation report
```

You can also pass a plain `rdflib.Graph` for `data_graph`, `shacl_graph`, or `ont_graph`; it is normalized to a `StarLayerGraph` automatically.

## Advanced features

These features are useful when working with RDF 1.2 data or advanced SHACL workflows.

### RDF 1.2 Triple Terms

Triple terms (`<<( subject predicate object )>>`) work as ordinary object values in both data and shapes.

### Rule expansion

`apply_rules()` expands SHACL rules and returns the updated graph alongside a validation report. This is useful when rule-based graph generation is part of the workflow.

## More detail

The deeper implementation notes and technical references live in the docs folder:

- [docs/implementation-plan.md](docs/implementation-plan.md)
- [docs/shacl12-gap-matrix.md](docs/shacl12-gap-matrix.md)
- [docs/compatibility.md](docs/compatibility.md)
- [CHANGELOG.md](CHANGELOG.md)

These are intended for maintainers and contributors rather than the main package audience.

## RDF 1.2 Triple Terms

Triple terms (`<<( subject predicate object )>>`) work as ordinary object values in both data and shapes:

```python
data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice ex:claims <<( ex:bob ex:age 42 )>> .
""", format="turtle12")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:ClaimShape a sh:NodeShape ;
      sh:targetSubjectsOf ex:claims ;
      sh:property [ sh:path ex:claims ; sh:minCount 1 ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)  # True
```

Reified statements (`subject predicate object {| annotations |}`) can be required and validated with `sh:reifierShape`/`sh:reificationRequired`:

```python
data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
""", format="turtle12")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:ReificationShape a sh:NodeShape ;
      sh:targetNode ex:alice ;
      sh:property [
        sh:path ex:value ;
        sh:reificationRequired true ;
      ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
print(result.conforms)  # True - ex:alice's ex:value statement has a reifier ({| ex:source ... |})
```

By default, decoded triple-term values in results come back as starshacl's own lightweight `TripleTermValue`. If you want real `starlayergraph.model.triple.TripleTerm` objects instead (matching what `StarLayerGraph` itself produces elsewhere in your code), use the starlayergraph-aware adapter:

```python
from starshacl import StarShaclValidator, TripleTermAdapter

validator = StarShaclValidator(adapter=TripleTermAdapter.for_starlayergraph())
```

## Rules

`apply_rules()` executes SHACL 1.2 rule processing and returns the updated data graph alongside a validation report. Rule bodies can use SPARQL 1.2 triple-term syntax (`<<( )>>`).:

```python
data = StarLayerGraph()
data.parse(data='''
    @prefix ex: <http://example.org/> .
    ex:alice ex:parent ex:carol .
''', format="turtle")

shapes = StarLayerGraph()
shapes.parse(data='''
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:AncestorRule a sh:NodeShape ;
      sh:targetSubjectsOf ex:parent ;
      sh:rule [
        a sh:SPARQLRule ;
        sh:construct """
          PREFIX ex: <http://example.org/>
          CONSTRUCT { $this ex:ancestor ?a }
          WHERE { $this ex:parent ?a }
        """ ;
      ] .
''', format="turtle")

result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)

for triple in result.data_graph:
    print(triple)  # includes the rule-derived ex:alice ex:ancestor ex:carol
```

## Meta-Shapes and Well-Formedness

Shapes graphs are checked for their own well-formedness before being used to validate data (`meta_shacl=True`, the default) - including SHACL 1.2 predicates. Pass your own additional shape rules with `meta_shapes_extra`:

```python
result = StarShaclValidator().validate(
    data_graph=data,
    shacl_graph=shapes,
    meta_shapes_extra=[my_org_conventions_graph],
)
```

## Execution Profiles

Three built-in profiles cover common configurations - pass `profile=` to `validate()`/`apply_rules()`, or override individual options as keyword arguments:

| Profile | Use case |
| --- | --- |
| `validation` (default) | Plain SHACL validation |
| `rules` | SHACL-AF rule expansion (`advanced=True`, `iterate_rules=True`) |
| `debug` | Validation with verbose diagnostics |

## Results and Diagnostics

`validate()` returns a `ValidationResult` (`conforms`, `report_graph`, `report_text`, `data_graph`, `diagnostics`); `apply_rules()` returns a `RulesResult` with the same shape plus the expanded `data_graph`. `diagnostics` (`ExecutionDiagnostics`) reports encode/decode call counts and triple-term counts, useful for understanding the cost of the RDF 1.2 adaptation layer on a given graph.

## Benchmarks

```bash
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

Measures the triple-term encode/decode adapter's own cost in isolation. See `benchmarks/README.md` for details and `docs/benchmark-baselines.md` for recorded results over time.

## Further Documentation

- `docs/implementation-plan.md` - current status and roadmap
- `docs/shacl12-gap-matrix.md` - SHACL 1.2 feature-by-feature coverage
- `docs/compatibility.md` - graph contract, versioning policy, internal pipeline
- `CHANGELOG.md` - what changed, by release

## License

MIT - see `LICENSE`.
Requires Python 3.10+.