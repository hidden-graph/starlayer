# StarLayer User Guide

StarLayer maintains the rdflib and pySHACL developer experience while extending the model to handle RDF 1.2, SPARQL 1.2 and SHACL 1.2 features. This guide walks through the relevant changes.  

> The RDF 1.2, SPARQL 1.2, and SHACL 1.2 specifications are still under active development at the W3C. StarLayer tracks the draft text and is updated as it evolves; this guide is current as of 22 August 2026.

## How to run this guide

1. Open [docs/user-guide-v1.ipynb](docs/user-guide-v1.ipynb) in VS Code or Jupyter.
2. Select the repository virtual environment as the notebook kernel.
3. Run cells from top to bottom so shared variables stay in scope.
4. If imports fail locally, run `pip install -e .` from the repository root in an activated virtual environment.
5. In Google Colab, the direct GitHub install works only if the repository is public.
6. If the repository is private, authenticate in Colab first and then install from a clone:

  ```python
  from google.colab import userdata
  token = userdata.get("GITHUB_TOKEN")
  !git clone https://{token}@github.com/hidden-graph/starlayer.git
  !pip install -e /content/starlayer
  ```

All examples below assume:

```python
from starlayergraph import StarLayerGraph, Namespace

EX = Namespace("http://example.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
```

## 1. Graph and literal semantics

The core graph layer understands new RDF 1.2 constructs.  

- Triple terms and statement resources
- Reification via `rdf:reifies` and related statement metadata
- Direction-tagged language strings such as `"hello"@en--ltr` and `"مرحبا"@ar--rtl`


This means the graph can carry these values as first-class data, not as one-off adapters or lossy conversions.

### Triple terms and reification

A triple term — RDF 1.2's `<<( s p o )>>` — is an ordinary Python value: construct one explicitly as `TripleTerm(s, p, o)`, or just write a plain 3-tuple in object position and StarLayer coerces it automatically (the guide leans on that shorthand elsewhere; this example spells it out).

`g.add_reification(reifier, triple_term)` is the dedicated helper for the reification pattern: it writes the `rdf:reifies` triple for you (accepting either a `TripleTerm` or a plain tuple) and makes the reifier a first-class node you can attach further metadata to, without asserting the underlying triple:

```python
from starlayergraph import TripleTerm

g = StarLayerGraph()
g.bind("ex", EX)

tt = TripleTerm(EX.bob, EX.knows, EX.carol)
g.add_reification(EX.claim, tt)
g.add((EX.claim, EX.source, EX.wikipedia))

print((EX.claim, RDF.reifies, tt) in g)

claim = g.cbd(EX.claim)
claim.bind("ex", EX)
print(claim.serialize(format="turtle12"))
```

Output:

```text
True
@version "1.2" .
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:claim ex:source ex:wikipedia ;
    rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
```

`add_reification()` assumes you already have a reifier node in hand (`EX.claim`, above). When you don't — and just want a fresh node to hang one annotation off of — `g.add_reifier_annotation(predicate, obj, name=None)` creates one (a `URIRef` if `name` is given, a `BNode` otherwise) and returns it; the node only becomes a real reifier once you pass it to `add_reification()`:

```python
from starlayergraph import Literal

r = g.add_reifier_annotation(EX.confidence, Literal("high"))   # BNode, no name given
g.add_reification(r, tt)

print(type(r).__name__)
print(g.has_triple_term(EX.bob, EX.knows, EX.carol))
```

Output:

```text
BNode
True
```

### Finding triple terms directly

A triple term can appear as a pattern's object, just like any other node — `g.triples()` matches it exactly, the same as it would a `URIRef` or `Literal`:

```python
g = StarLayerGraph()
g.bind("ex", EX)

g.add((EX.claim, RDF.reifies, (EX.bob, EX.knows, EX.carol)))
g.add((EX.other, RDF.reifies, (EX.bob, EX.likes, EX.dana)))

for s, p, o in g.triples((None, None, (EX.bob, EX.knows, EX.carol))):
    print(g.qname(s), g.qname(p), o)
```

Output:

```text
ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>>
```

When you don't know the exact triple term in advance — or want to search by only some of its components — `triple_terms()` and `has_triple_term()` are StarLayer additions with no rdflib equivalent, querying the triple terms themselves without needing a `rdf:reifies` triple or a SPARQL query:

```python
for tt in g.triple_terms(subject=EX.bob):
    print(tt)

print(g.has_triple_term(EX.bob, EX.knows, EX.carol))
print(g.has_triple_term(EX.bob, EX.knows, EX.dana))
```

Output:

```text
<<( ex:bob ex:knows ex:carol )>>
<<( ex:bob ex:likes ex:dana )>>
True
False
```

### Direction-tagged literals

RDF 1.2 literals can carry a base direction (`ltr`/`rtl`) alongside a language tag. In Python this is a `DirLangString(value, language, direction)`:

```python
from starlayergraph import DirLangString

g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.title, EX.value, DirLangString("مرحبا", "ar", "rtl")))

print(g.serialize(format="turtle12"))
```

Output:

```text
@version "1.2" .
@prefix ex: <http://example.org/> .

ex:title ex:value "مرحبا"@ar--rtl .
```

`DirLangString` is value-typed the same way `TripleTerm` is: two instances with the same `(value, language, direction)` compare equal regardless of how they were constructed, and no registry is involved — the encoding is a pure function of the value, decoded transparently wherever `StarLayerGraph` hands a result back to you.

## 2. SPARQL and query semantics

StarLayer also extends query behavior so that SPARQL can reason over RDF 1.2-style data instead of only the older RDF 1.1 model. This includes:

- RDF 1.2-aware expression evaluation over triple terms and direction-tagged literals
- SPARQL support for language-direction behavior
- RDF encoding of the SPARQL algebra using a dedicated ontology
- SHACL validation of the generated SPARQL RDF representation
- Compatibility with Turtle/SPARQL syntax parsing and serialization

### RDF 1.2 Turtle round-trip

`turtle12` parses and serializes `<<( )>>` triple terms and `@lang--dir` literals directly — no adapter layer:

```python
g = StarLayerGraph()
g.parse(data='''
    @prefix ex: <http://example.org/> .
    ex:note ex:text "مرحبا"@ar--rtl .
''', format='turtle12')

print(g.serialize(format='turtle12'))
```

Output:

```text
@version "1.2" .
@prefix ex: <http://example.org/> .

ex:note ex:text "مرحبا"@ar--rtl .
```

### Querying over a reified statement

`g.query()` accepts SPARQL 1.2 syntax directly, including `<<( s p o )>>` triple-term patterns in the WHERE clause:

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.claim, RDF.reifies, (EX.bob, EX.knows, EX.carol)))
g.add((EX.claim, EX.source, EX.wikipedia))

rows = g.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

    SELECT ?claim ?source WHERE {
      ?claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
      ?claim ex:source ?source .
    }
""")

for row in rows:
    print(g.qname(row.claim), g.qname(row.source))
```

Output:

```text
ex:claim ex:wikipedia
```

### Finding triple terms with `isTRIPLE`

`isTRIPLE(?x)` — the SPARQL 1.2 spec's own function name (§17.4.6) — tests whether a bound value is a triple term, useful when you don't know in advance which predicate carries one. (Use this exact spelling: `isTripleTerm` is not recognized by the query grammar.)

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.claim, RDF.reifies, (EX.bob, EX.knows, EX.carol)))

rows = g.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

    SELECT ?claim WHERE {
      ?claim rdf:reifies ?statement .
      FILTER( isTRIPLE(?statement) )
    }
""")

for row in rows:
    print(g.qname(row.claim))
```

Output:

```text
ex:claim
```

## 3. SHACL validation and rules

Once your graph works, the next step is checking it against a shapes graph. The validator sits on top of a normal rdflib/pySHACL workflow while extending it for RDF 1.2 values, node expressions, and SHACL 1.2 rule behavior. Key additions include:

- Validation over RDF 1.2 graphs containing triple terms, statement resources, and direction-tagged literals
- SHACL 1.2 node-expression and rule-based evaluation support
- Updated SHACL meta-shapes for SHACL 1.2 compatibility
- Formal SHACL 1.2 UI support for shape-driven interface generation
- Direction-aware uniqueness and datatype constraints for language-tagged values

### A conforming shape

```python
from starshacl import StarShaclValidator

data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ;
      ex:age 30 .
""", format="turtle")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    ex:PersonShape a sh:NodeShape ;
      sh:targetClass ex:Person ;
      sh:property [
        sh:path ex:age ;
        sh:minCount 1 ;
        sh:datatype xsd:integer ;
      ] .
""", format="turtle")

validator = StarShaclValidator()
result = validator.validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)
```

Output:

```text
True
```

### A violation, and its report

The same `PersonShape`, applied to data that's missing `ex:age`, produces a real `ValidationResult` with a human-readable report:

```python
data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:bob a ex:Person .
""", format="turtle")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    ex:PersonShape a sh:NodeShape ;
      sh:targetClass ex:Person ;
      sh:property [
        sh:path ex:age ;
        sh:minCount 1 ;
        sh:datatype xsd:integer ;
      ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)
print(result.report_text)
```

Output:

```text
False
Validation Report
Conforms: False
Results (1):
Constraint Violation in MinCountConstraintComponent (http://www.w3.org/ns/shacl#MinCountConstraintComponent):
	Severity: sh:Violation
	Source Shape: [ sh:datatype xsd:integer ; sh:minCount Literal("1", datatype=xsd:integer) ; sh:path ex:age ]
	Focus Node: ex:bob
	Result Path: ex:age
	Message: Less than 1 values on ex:bob->ex:age
```

### Direction-aware datatype constraints

`sh:datatype rdf:dirLangString` requires a value to carry both a language tag *and* a base direction — a plain string or an ordinary `@en` literal doesn't satisfy it:

```python
data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:n1 a ex:Note ;
      ex:label "hello"@en--ltr .
""", format="turtle12")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

    ex:NoteShape a sh:NodeShape ;
      sh:targetClass ex:Note ;
      sh:property [
        sh:path ex:label ;
        sh:datatype rdf:dirLangString ;
      ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)
```

Output:

```text
True
```

Change `ex:label` to a plain `"hello"` (no `@en--ltr`) and re-run — `result.conforms` becomes `False`, since the value no longer satisfies `rdf:dirLangString`.

### SHACL rules

`sh:rule`/`sh:TripleRule` derives new triples from existing data. `apply_rules()` runs the rule set and returns the augmented graph alongside a conformance report:

```python
data = StarLayerGraph()
data.parse(data="""
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person .
""", format="turtle")

shapes = StarLayerGraph()
shapes.parse(data="""
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .

    ex:PersonRule a sh:NodeShape ;
      sh:targetClass ex:Person ;
      sh:rule [
        a sh:TripleRule ;
        sh:subject sh:this ;
        sh:predicate ex:inferred ;
        sh:object ex:yes ;
      ] .
""", format="turtle")

result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes)

print((EX.alice, EX.inferred, EX.yes) in result.data_graph)
print(result.conforms)
```

Output:

```text
True
True
```

## 4. Backend graph-store and format support

StarLayer is designed to work across storage models instead of forcing a single implementation choice:

- An in-memory default backend (`backend='rdf-1.1'`) that stores triples in rdflib's own store and rewrites SPARQL 1.2 syntax to SPARQL 1.1 before execution — everything in this guide runs against it
- A native backend (`backend='rdf-1.2'`) that talks SPARQL 1.2 directly over HTTP to a live endpoint that already speaks the triple-term syntax natively, confirmed against Apache Jena Fuseki 5.5+ and Oxigraph 0.5.9
- Eight RDF 1.2-aware read/write formats: `turtle12`, `nt12`, `nq12`, `trig12`, `trix12`, `rdfxml12`, `jsonld12`, `longturtle12` — the first six and `rdfxml12` target real W3C companion documents; `jsonld12` and `trix12` don't have a W3C RDF 1.2 spec to converge on yet, but `trix12` matches Apache Jena/Fuseki's real convention and round-trips through it
- Dual-mode operation: ordinary RDF 1.1 formats and plain SPARQL 1.1 queries keep working unchanged alongside the RDF 1.2 additions

### Format round-trip

The same graph serializes to any of the eight formats:

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.alice, EX.claims, (EX.bob, EX.knows, EX.carol)))

print(g.serialize(format="turtle12"))
print("---")
print(g.serialize(format="nt12"))
```

Output:

```text
@version "1.2" .
@prefix ex: <http://example.org/> .

ex:alice ex:claims <<( ex:bob ex:knows ex:carol )>> .

---
VERSION "1.2"
<http://example.org/alice> <http://example.org/claims> <<( <http://example.org/bob> <http://example.org/knows> <http://example.org/carol> )>> .
```

### Switching to the native backend

Pointing at a live SPARQL 1.2 endpoint is a constructor argument — the rest of the API (`add`, `parse`, `query`, `serialize`) stays the same:

```python
g = StarLayerGraph()                     # default: in-memory, rdf-1.1 backend
g = StarLayerGraph(backend='rdf-1.2')    # native RDF 1.2 endpoint (Fuseki, Oxigraph, ...)
```

With the native backend, triple terms and direction-tagged literals are sent to the endpoint in their real syntax — no `tt:HASH` content-addressed encoding, and no query rewriting. This snippet requires a running endpoint to actually connect, so it isn't executed as part of this guide.

## Summary

StarLayer provides a practical bridge from the older rdflib/pySHACL stack to the newer RDF 1.2 and SHACL 1.2 world:

- richer graph semantics — triple terms, reification, and direction-tagged literals as first-class values
- SPARQL support for RDF 1.2 constructs, including triple-term patterns and the `isTRIPLE` filter
- SHACL validation and rules for modern RDF data, including direction-aware datatype constraints
- an in-memory backend for everyday use and a native backend for talking directly to a real RDF 1.2 SPARQL endpoint

This keeps the user experience familiar while making the more advanced RDF 1.2 and SHACL 1.2 features available in a working implementation.
