# starshacl ##

`starshacl` validates RDF data against SHACL shapes, with full support for **RDF 1.2** (e.g. triple terms, direction-tagged literals) and **SHACL 1.2 Core**.  Works as a wrappe on  [`pySHACL`](https://github.com/RDFLib/pySHACL), which works with  SHACL 1.1 and RDF 1.1.

Usin starlayergraph (add url ) RDF 1.2 values are transparently encoded into an RDF-1.1-compatible form before validation and decoded on retrieval.  , Every SHACL 1.2 predicate is registered as a pySHACL constraint component, so it composes correctly similar to built-in predicates.

## Features

- **Full SHACL 1.2 Core support** - every SHACL 1.2 predicate (`sh:someValue`, `sh:uniqueValuesFor`, `sh:reifierShape`, list-valued `sh:class`/`sh:datatype`, path-valued `sh:equals`/`sh:disjoint`, and more) validates correctly, including under composition.
- **RDF 1.2 as a first-class value type** - triple terms and `rdf:dirLangString` direction-tagged literals round-trip through validation and rule expansion.
- **SHACL-AF rule expansion** (`apply_rules()`) using pySHACL's advanced mode, including `sh:construct` rules with SPARQL 1.2 triple-term syntax.
- **SPARQL 1.2 support** in `sh:sparql` constraints and `sh:construct` rules (`<<( )>>` patterns, `isTripleTerm()`, `SUBJECT()`/`PREDICATE()`/`OBJECT()`) - works transparently.
- **Meta-shapes validation** - the shapes graph itself is expanded for new SHACL 1.2 predicates and checked for well-formedness before it's used to validate data.
- **Execution profiles** (`validation`, `rules`, `debug`) for common configuration presets, plus typed result objects with execution diagnostics.

## Install

Neither `starlayergraph` nor `rdflib-starshacl` is published to PyPI yet - install `starlayergraph` from source, then install this repository.  (note - give instructions on how to install.  )

```bash
pip install git+https://github.com/hidden-graph/starlayergraph.git
pip install -e .
pip install -e .[test]  # with test dependencies
```

Requires Python 3.10+.

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

You can also pass a plain `rdflib.Graph` for `data_graph`/`shacl_graph`/`ont_graph` - it's normalized to a `StarLayerGraph` automatically, so you don't need to construct one yourself. `starlayergraph` is a required dependency since that's the data model everything runs on internally.

## RDF 1.2 Triple Terms

Triple terms (`<<( subject predicate object )>>`) work as ordinary object values in both data and shapes:


(note: show a standard reifiers statement)

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



(note: I do not know what this is.)
By default, decoded triple-term values in results come back as starshacl's own lightweight `TripleTermValue`. If you want real `starlayergraph.model.triple.TripleTerm` objects instead (matching what `StarLayerGraph` itself produces elsewhere in your code), use the starlayergraph-aware adapter:

```python
from starshacl import StarShaclValidator, TripleTermAdapter

validator = StarShaclValidator(adapter=TripleTermAdapter.for_starlayergraph())
```

(note: refer to the SHACL 1.2 component as well.)
## Rules (SHACL-AF)

`apply_rules()` runs pySHACL's advanced mode, including `sh:construct` rules, and returns the expanded data graph alongside a validation report:

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


(note: this seems very advanced.  maybe we have an extras component below where we are explian in more depth.)
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
