# RDF 1.2 and SHACL 1.2 in StarLayer

StarLayer maintains the rdflib and pySHACL developer experience, while extending the model to handle RDF 1.2, SPAFRQL 1.2 and SHACL 1.2 features that are not available in rdflib and pyshacl.  

## 1. Graph and literal semantics

The core graph layer understands RDF 1.2 constructs.

- Triple terms and statement resources
- Reification via `rdf:reifies` and related statement metadata
- Direction-tagged language strings such as `"hello"@en--ltr` and `"hello"@ar--rtl`


This means the graph can carry these values as first-class data.

### Methods covered in this section
NOTE:  should we have StarLayerGraph ad StarlayerDataset here?
Classes: `TripleTerm(s, p, o)`, `DirLangString(value, language, direction)`.

Core graph methods (rdflib-overridden, RDF-1.2-aware): `g.add(triple)` / `(s, p, o) in g`, `g.triples((s, p, o))`, `g.cbd(resource)`, `g.serialize(format=...)`, `g.parse(format='turtle12')`.

StarLayer-only reification and triple-term methods (no rdflib equivalent): `g.add_reification()`, `g.add_reifier_annotation()`, `g.triple_terms()`, `g.has_triple_term()`, `g.reifiers()`, `g.reifications()`, `g.reifier_annotations()`, `g.reified_triples()`, `g.remove_reification()`, `g.from_rdflib()`, `g.isomorphic()`.

NOTE: how are get_context, quads, contexts different in stargraph?  Can they be core methods above>?
Multi-graph: `StarLayerDataset`, `ds.get_context()`, `ds.quads()`, `ds.contexts()`, `ds.parse(format='trig12')`, `ds.serialize(format='trig12')`.

All examples below assume:

```python
from starlayergraph import StarLayerGraph, Namespace

EX = Namespace("http://example.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
```

### Parsing RDF 1.2 Turtle

Triple-term syntax (`<<( )>>`) uses the `turtle12` parser.

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.parse(data="""
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:claim rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
""", format="turtle12")

for s, p, o in g:
    print(g.qname(s), g.qname(p), o)
```

Output:

```text
ex:claim rdf:reifies <<( ex:alice ex:knows ex:bob )>>
```

### Querying reifiers: `reifiers()`, `reifications()`, `reifier_annotations()`, `reified_triples()`

Four StarLayer-only methods answer the "what's been said about this statement" family of questions without writing SPARQL. They complement `triple_terms()`/`has_triple_term()` (which answer "does this triple term exist"): these four instead navigate the *reification* relationship — reifier ↔ triple term ↔ annotations.

```python
tt1 = (EX.bob, EX.knows, EX.carol)
tt2 = (EX.bob, EX.likes, EX.dana)

g = StarLayerGraph()
g.bind("ex", EX)
g.add_reification(EX.claim, tt1) //EX.claim reifies tt1
g.add((EX.claim, EX.source, EX.wikipedia)) 
g.add_reification(EX.other, tt2) //

# reifiers(): which reifier node(s) reify a given triple term?
print([g.qname(r) for r in g.reifiers(TT=tt1)])

# reifications(): which triple terms have at least one reifier?
for tt in g.reifications():
    print(tt)

# reifier_annotations(): a reifier's own annotation triples (excludes rdf:reifies itself)
for reifier, pred, val in g.reifier_annotations(tt1):
    print(g.qname(reifier), g.qname(pred), g.qname(val))

# reified_triples(): the triple term(s) a specific reifier reifies
for tt in g.reified_triples(EX.claim):
    print(tt)
```

Output:

```text
['ex:claim']
<<( ex:bob ex:knows ex:carol )>>
<<( ex:bob ex:likes ex:dana )>>
ex:claim ex:source ex:wikipedia
<<( ex:bob ex:knows ex:carol )>>
```

### Undoing reification: `remove_reification()`

Removes only the `rdf:reifies` triple — the reifier node and any annotations you attached to it (like `ex:source` above) are untouched, since they may still be meaningful on their own:

```python
g.remove_reification(EX.claim)
print((EX.claim, RDF.reifies, tt1) in g)         # False — no longer a reifier
print((EX.claim, EX.source, EX.wikipedia) in g)  # True — annotation survives
```

Output:

```text
False
True
```

### Importing a plain rdflib graph: `from_rdflib()`

A classmethod for bringing existing rdflib data into StarLayer's RDF 1.2 model. Any RDF-1.1-style reification already present (`rdf:subject`/`rdf:predicate`/`rdf:object`/`rdf:statement`) gets encoded into StarLayer's triple-term registry rather than staying as loose, unconnected triples:

```python
from rdflib import Graph

plain = Graph()
plain.bind("ex", EX)
plain.add((EX.alice, EX.knows, EX.bob))

g = StarLayerGraph.from_rdflib(plain)
print(type(g).__name__)
print((EX.alice, EX.knows, EX.bob) in g)
```

Output:

```text
StarLayerGraph
True
```

### RDF-1.2-aware isomorphism: `isomorphic()`

Overrides `rdflib.Graph.isomorphic()` so two graphs that use different blank-node labels for the same shape — including blank nodes *inside* a triple term — still compare equal. 

```python
from starlayergraph import TripleTerm

g1 = StarLayerGraph()
g1.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

g2 = StarLayerGraph()
g2.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

g3 = StarLayerGraph()
g3.add_reification(EX.claim, TripleTerm(EX.bob, EX.likes, EX.carol))

print(g1.isomorphic(g2))
print(g1.isomorphic(g3))
```

Output:

```text
True
False
```

### Multiple graphs: `StarLayerDataset`

`StarLayerGraph` holds one graph. `StarLayerDataset` (a subclass of `rdflib.Dataset`) holds many named graphs, each its own `StarLayerGraph` with an independent triple-term registry — a triple term registered in one named graph isn't visible from another:

```python
from starlayergraph import StarLayerDataset, TripleTerm

ds = StarLayerDataset()
ds.bind("ex", EX)

g1 = ds.get_context(EX.graph1)
g1.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

g2 = ds.get_context(EX.graph2)
g2.add_reification(EX.other, TripleTerm(EX.alice, EX.knows, EX.dave))

# ds.contexts()/ds.quads() iterate in no guaranteed order — sort for stable output
rows = sorted(ds.quads((None, None, None)), key=lambda row: str(row[3].identifier))
for s, p, o, g in rows:
    print(ds.qname(g.identifier), "|", ds.qname(s), ds.qname(p), o)
```

Output:

```text
ex:graph1 | ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>>
ex:graph2 | ex:other rdf:reifies <<( ex:alice ex:knows ex:dave )>>
```

`ds.contexts()` yields each named graph as a `StarLayerGraph`; `ds.get_context(uri)` returns one specific named graph, creating it if it doesn't exist yet. Serializing the whole dataset needs a multi-graph format — see `trig12` under Section 4.

## 2. SPARQL and query semantics

StarLayer also extends query behavior so that SPARQL can reason over RDF 1.2-style data instead of only the older RDF 1.1 model.

This includes:

- RDF 1.2-aware expression evaluation over triple terms and direction-tagged literals
- SPARQL support for language-direction behavior
- RDF encoding of the SPARQL algebra using a dedicated ontology
- SHACL validation of the generated SPARQL RDF representation
- Compatibility with Turtle/SPARQL syntax parsing and serialization

### Methods covered in this section

Core query methods: `g.query()`, `g.update()`.

Functions usable inside a query (SPARQL 1.2 syntax extensions): `isTRIPLE()`, `TRIPLE()`, `SUBJECT()`/`PREDICATE()`/`OBJECT()`, `LANGDIR()`/`hasLANGDIR()`/`STRLANGDIR()`, `LANG()`/`hasLANG()`.

Turtle/SPARQL annotation shorthand (all desugar to `rdf:reifies` + `<<( )>>`; see `packages/graph/docs/sparql12_design.md`): `s p o ~ ?r`, `s p o {| ?pred ?val |}`, `<< s p o >> ?pred ?val`. These three are one of the most distinctive parts of the RDF 1.2/SPARQL 1.2 story — what most users will actually type day to day instead of the verbose formal `rdf:reifies`/`<<( )>>` pattern.

All examples below assume the same preamble as Section 1 (`StarLayerGraph`, `EX`, `RDF`).

### A note on the very first example in this outline

The original version of this example used plain `format="turtle"` for a direction-tagged literal, which fails the same way Section 1's did — `@lang--dir` syntax needs `turtle12` too:

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.parse(data="""
@prefix ex: <http://example.org/> .

ex:message ex:value "hello"@en--ltr .
""", format="turtle12")

for row in g.query("SELECT ?value WHERE { ?s ex:value ?value }"):
    print(row.value.n3())
```

Output:

```text
"hello"@en--ltr
```

### `SELECT`/`ASK`/`CONSTRUCT` with triple-term patterns

`g.query()` accepts `<<( s p o )>>` directly in WHERE, and CONSTRUCT can build new triple terms:

```python
from starlayergraph import TripleTerm

g = StarLayerGraph()
g.bind("ex", EX)
g.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

rows = g.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?stmt WHERE {
      ?stmt rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
    }
""")
for row in rows:
    print(g.qname(row.stmt))
```

Output:

```text
ex:claim
```

### `g.update()` — SPARQL 1.2 UPDATE

`INSERT`/`DELETE ... WHERE` accept triple-term patterns exactly like `SELECT` does:

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.alice, EX.knows, EX.bob))

g.update("""
    PREFIX ex: <http://example.org/>
    INSERT { ?a ex:claims <<( ex:bob ex:knows ex:carol )>> }
    WHERE { ?a ex:knows ex:bob }
""")

for s, p, o in g.triples((EX.alice, EX.claims, None)):
    print(g.qname(s), g.qname(p), o)
```

Output:

```text
ex:alice ex:claims <<( ex:bob ex:knows ex:carol )>>
```

### `TRIPLE()`, and `SUBJECT()`/`PREDICATE()`/`OBJECT()`

`TRIPLE(s, p, o)` is the function-call spelling of `<<( s p o )>>` — useful when the components come from expressions rather than being written literally. `SUBJECT()`/`PREDICATE()`/`OBJECT()` go the other way, pulling the three components back out of an already-bound triple term:

```python
g = StarLayerGraph()
g.bind("ex", EX)

rows = g.query("""
    PREFIX ex: <http://example.org/>
    SELECT ?t ?s ?p ?o WHERE {
      BIND(TRIPLE(ex:bob, ex:knows, ex:carol) AS ?t)
      BIND(SUBJECT(?t)   AS ?s)
      BIND(PREDICATE(?t) AS ?p)
      BIND(OBJECT(?t)    AS ?o)
    }
""")
for row in rows:
    print(row.t)
    print(g.qname(row.s), g.qname(row.p), g.qname(row.o))
```

Output:

```text
<<( ex:bob ex:knows ex:carol )>>
ex:bob ex:knows ex:carol
```

### Direction functions: `LANGDIR()`, `hasLANGDIR()`, `STRLANGDIR()`, and direction-aware `LANG()`/`hasLANG()`

```python
from starlayergraph import DirLangString

g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.note, EX.label, DirLangString("hello", "en", "ltr")))

rows = g.query("""
    PREFIX ex: <http://example.org/>
    SELECT ?lang ?dir ?hasDir WHERE {
      ?s ex:label ?lit .
      BIND(LANG(?lit) AS ?lang)
      BIND(LANGDIR(?lit) AS ?dir)
      BIND(hasLANGDIR(?lit) AS ?hasDir)
    }
""")
for row in rows:
    print(row.lang, row.dir, row.hasDir)

# STRLANGDIR() constructs a DirLangString value directly from a plain string
rows = g.query('SELECT ?lit WHERE { BIND(STRLANGDIR("hi", "en", "ltr") AS ?lit) }')
for row in rows:
    print(row.lit.n3())
```

Output:

```text
en ltr true
"hi"@en--ltr
```

### Annotation shorthand: `~`, `{| |}`, `<< >>`

The formal `rdf:reifies <<( )>>` pattern is what these compile to internally, but it's rarely what anyone types by hand. Three shorthand forms cover the common cases — see `packages/graph/docs/sparql12_design.md` for the full expansion rules.

**`s p o ~ ?r`** — names the reifier and asserts the base triple:

```python
g = StarLayerGraph()
g.bind("ex", EX)
g.add((EX.bob, EX.knows, EX.carol))

g.update("""
    PREFIX ex: <http://example.org/>
    INSERT { ex:bob ex:knows ex:carol ~ ex:stmt1 . ex:stmt1 ex:confidence "0.9" }
    WHERE {}
""")

rows = g.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?p ?o WHERE { ex:stmt1 ?p ?o . FILTER(?p != rdf:reifies) }
""")
for row in rows:
    print(g.qname(row.p), row.o)

print("base triple asserted?", (EX.bob, EX.knows, EX.carol) in g)
```

Output:

```text
ex:confidence 0.9
base triple asserted? True
```

**`s p o {| ?pred ?val |}`** — anonymous reifier, inline; also asserts the base triple:

```python
g = StarLayerGraph()
g.bind("ex", EX)

g.update("""
    PREFIX ex: <http://example.org/>
    INSERT { ex:bob ex:likes ex:dana {| ex:since "2020" |} }
    WHERE {}
""")

rows = g.query("""
    PREFIX ex: <http://example.org/>
    SELECT ?since WHERE {
      ex:bob ex:likes ex:dana {| ex:since ?since |}
    }
""")
for row in rows:
    print(row.since)
```

Output:

```text
2020
```

**`<< s p o >> ?pred ?val`** — reification shorthand; does *not* assert the base triple:

```python
g = StarLayerGraph()
g.bind("ex", EX)

g.update("""
    PREFIX ex: <http://example.org/>
    INSERT { << ex:carol ex:knows ex:dave >> ex:certainty "low" }
    WHERE {}
""")

print("base triple asserted?", (EX.carol, EX.knows, EX.dave) in g)

rows = g.query("""
    PREFIX ex: <http://example.org/>
    SELECT ?certainty WHERE {
      << ex:carol ex:knows ex:dave >> ex:certainty ?certainty
    }
""")
for row in rows:
    print(row.certainty)
```

Output:

```text
base triple asserted? False
low
```

## 3. SHACL validation and rules

The SHACL layer is updated in the same spirit: it validates graphs that contain RDF 1.2 values and applies SHACL 1.2 features that were not present in the older pySHACL stack.

Key additions include:

- Validation over RDF 1.2 graphs containing triple terms, statement resources, and direction-tagged literals
- SHACL 1.2 node-expression and rule-based evaluation support
- Updated SHACL meta-shapes for SHACL 1.2 compatibility
- Formal SHACL 1.2 UI support for shape-driven interface generation
- Direction-aware uniqueness and datatype constraints for language-tagged values

### How starshacl relates to pySHACL

starshacl doesn't replace pySHACL or run a competing validation engine alongside it — it wraps `pyshacl.validate()` and expands pySHACL's *own* machinery in place. New SHACL 1.2 predicates (`sh:someValue`, `sh:subsetOf`, `sh:rootClass`, and the rest) are implemented as real subclasses of pySHACL's own `ConstraintComponent` base class and registered directly into pySHACL's internal constraint dispatch table, so pySHACL's generic shape-composition engine evaluates them exactly like any built-in predicate (`sh:minCount`, `sh:pattern`, etc.) — not through a separate code path. A handful of confirmed pySHACL bugs are fixed the same way, by patching pySHACL's own methods in place. See `packages/shacl/docs/compatibility.md` for the full contract, `packages/shacl/docs/shacl12-gap-matrix.md` for per-predicate/per-spec-document coverage, and the SHACL 1.2 Working Drafts themselves for the features this section only samples: `https://www.w3.org/TR/shacl12-core/` and its five companion documents (SPARQL Extensions, Node Expressions, Rules, User Interfaces, Profiling).

Practically, this means the public API surface to learn is small — `StarShaclValidator.validate()` and `.apply_rules()`, already shown above and below — and everything past that is standard SHACL/SHACL 1.2 shape syntax you write as Turtle, not a StarLayer-specific method to look up.

All examples below assume:

```python
from starlayergraph import StarLayerGraph
from starshacl import StarShaclValidator
```

### RDF 1.2-aware validation

The corrected form of this document's very first SHACL example (the original imported a top-level `validate()` function from `starshacl`, which doesn't exist — the real entry point is `StarShaclValidator().validate(...)`, used throughout this document):

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
    ex:LangShape a sh:NodeShape ;
      sh:targetClass ex:Note ;
      sh:property [ sh:path ex:label ; sh:datatype rdf:dirLangString ] .
""", format="turtle")

result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes)
print(result.conforms)
```

Output:

```text
True
```

### A violation, and its report

The same shape family, applied to data that fails it, produces a real, human-readable report via `.report_text` — this is ordinary pySHACL behavior, unaffected by anything RDF-1.2-specific:

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
      sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:datatype xsd:integer ] .
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

### SHACL rules: `apply_rules()`

`sh:rule`/`sh:TripleRule` derives new triples from existing data — a SHACL-AF feature, extended (per "How starshacl relates to pySHACL" above) to run under starshacl's RDF-1.2-aware engine:

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

from starlayergraph import Namespace
EX = Namespace("http://example.org/")
print((EX.alice, EX.inferred, EX.yes) in result.data_graph)
print(result.conforms)
```

Output:

```text
True
True
```

For everything past these three examples — the rest of SHACL 1.2 Core, node expressions, SPARQL extensions, and the `shui:` vocabulary noted in this section's intro bullets — the shape syntax itself is the thing to read up on; `packages/shacl/docs/shacl12-gap-matrix.md` and the W3C Working Drafts linked above are the place to start.

## 4. Backend graph-store and format support

StarLayer is designed to work across different RDF backends and storage models instead of forcing a single implementation choice.

This includes:

- Compatibility with RDF graph backends such as Oxigraph, Jena/Fuseki, and SQL-backed stores
- Read/write support for RDF 1.2-aware formats such as Turtle and related RDF serializations
- Dual-mode operation across RDF 1.1 and RDF 1.2 semantics
- Use of backend SPARQL 1.2 capabilities when available, while preserving compatibility with older stores

In practice, the same conceptual workflow works whether the data comes from a local in-memory graph, a remote SPARQL endpoint, or a SQL-backed RDF store.

### Methods covered in this section

`StarLayerGraph()` (default backend), `StarLayerGraph(backend='rdf-1.2')` (native backend), `StarLayerGraph(store=...)` (generic rdflib Store interop, e.g. SQL-backed via `rdflib-sqlalchemy`), all eight RDF 1.2 formats, `StarLayerDataset.parse()`/`.serialize(format='trig12')`.

All examples below assume the same preamble as Section 1 (`StarLayerGraph`, `EX`, `RDF`).

### The two named backends

```python
g = StarLayerGraph()                     # default: in-memory, rdf-1.1 backend
g = StarLayerGraph(backend='rdf-1.2')    # native RDF 1.2 endpoint (Fuseki, Oxigraph, ...)
```

With the native backend, triple terms and direction-tagged literals are sent to the endpoint in their real syntax — no `tt:HASH` content-addressed encoding, and no query rewriting. This needs a running endpoint to actually connect, so it's shown for illustration only, not executed here.

### Any rdflib `Store` plugin works too — including SQL-backed stores

**This corrects a claim made earlier while building the user guide** (`docs/user-guide-v1.md`'s Section 4 currently says "no SQL-backed store integration exists" — that turned out to be wrong). `StarLayerGraph` is an ordinary `rdflib.Graph` subclass, so any rdflib-compatible `Store` plugin works transparently under the default `rdf-1.1` (encoding) backend — not just the built-in in-memory store. `packages/graph/examples/sqlalchemy_store_demo.py` and `packages/graph/tests/integration/test_sqlalchemy_backend.py` demonstrate this against a real SQLite database via `rdflib-sqlalchemy` (`pip install -e ".[sqlalchemy]"`):

```python
import tempfile
import rdflib_sqlalchemy
from starlayergraph import TripleTerm

rdflib_sqlalchemy.registerplugins()

db_path = tempfile.mktemp(suffix=".sqlite")
uri = f"sqlite:///{db_path}"

writer = StarLayerGraph(store="SQLAlchemy", identifier=EX.main)
writer.open(uri, create=True)
writer.bind("ex", EX)
writer.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))
writer.commit()
writer.close()

# fresh process/graph, same database file
reader = StarLayerGraph(store="SQLAlchemy", identifier=EX.main)
reader.open(uri, create=False)
reader.bind("ex", EX)

rows = reader.query("""
    PREFIX ex: <http://example.org/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?stmt WHERE { ?stmt rdf:reifies <<( ex:bob ex:knows ex:carol )>> }
""")
for row in rows:
    print(reader.qname(row.stmt))

reader.close()
```

Output:

```text
ex:claim
```

The rest of the API (`add`, `parse`, `query`, `serialize`, every StarLayer-only method from Section 1) works identically regardless of which `Store` backs the graph — nothing in this example is SQL-specific beyond the `store="SQLAlchemy"` constructor argument and the `open()`/`commit()`/`close()` lifecycle calls (all plain rdflib, not StarLayer additions).

### All eight RDF 1.2 formats

`turtle12`/`nt12` are already used throughout this document; here are the other six, serializing the same graph:

```python
from starlayergraph import TripleTerm

g = StarLayerGraph()
g.bind("ex", EX)
g.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

print(g.serialize(format="nq12"))
```

Output:

```text
VERSION "1.2"
<http://example.org/claim> <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( <http://example.org/bob> <http://example.org/knows> <http://example.org/carol> )>> .
```

```python
print(g.serialize(format="trig12"))
```

Output:

```text
@version "1.2" .
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
```

```python
print(g.serialize(format="trix12"))
```

Output:

```text
<?xml version="1.0" encoding="UTF-8"?>
<trix xmlns="http://www.w3.org/2004/03/trix/trix-1/">
  <graph>
    <triple>
      <uri>http://example.org/claim</uri>
      <uri>http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies</uri>
      <triple>
        <uri>http://example.org/bob</uri>
        <uri>http://example.org/knows</uri>
        <uri>http://example.org/carol</uri>
      </triple>
    </triple>
  </graph>
</trix>
```

```python
print(g.serialize(format="rdfxml12"))
```

Output:

```text
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:ex="http://example.org/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="http://example.org/claim">
    <rdf:reifies rdf:parseType="Triple">
      <rdf:Description rdf:about="http://example.org/bob">
        <ex:knows rdf:resource="http://example.org/carol" />
      </rdf:Description>
    </rdf:reifies>
  </rdf:Description>
</rdf:RDF>
```

```python
print(g.serialize(format="jsonld12"))
```

Output:

```text
{
  "@context": {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "tt": "https://github.com/hidden-graph/starlayergraph/ns/tt#"
  },
  "@graph": [
    {
      "@id": "tt:e65284ee54cb3e7c",
      "@type": [
        "rdf:TripleTerm"
      ],
      "http://www.w3.org/1999/02/22-rdf-syntax-ns#subject": [
        {
          "@id": "http://example.org/bob"
        }
      ],
      "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate": [
        {
          "@id": "http://example.org/knows"
        }
      ],
      "http://www.w3.org/1999/02/22-rdf-syntax-ns#object": [
        {
          "@id": "http://example.org/carol"
        }
      ]
    },
    {
      "@id": "http://example.org/claim",
      "rdf:reifies": [
        {
          "@id": "tt:e65284ee54cb3e7c"
        }
      ]
    }
  ]
}
```

The `tt:e65284ee54cb3e7c` id is the same content-addressed hash discussed in `packages/graph/docs/starlayergraph.md` — a pure function of `(subject, predicate, object)`, stable across runs and processes. `jsonld12` and `trix12` are the two formats in this list without a real W3C RDF 1.2 spec target (see Section 4's intro bullets and `packages/graph/docs/starlayergraph_vs_rdflib.md` for the caveat); the other six do.

```python
print(g.serialize(format="longturtle12"))
```

Output:

```text
@version "1.2" .
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>> .
```

`longturtle12` is a pretty-printed Turtle variant — for a graph this small it's byte-identical to plain `turtle12`; the difference shows up on larger graphs with more triples to lay out.

### Multi-graph round-trip: `ds.serialize(format='trig12')` → `ds.parse(format='trig12')`

`trig12` is the only one of the eight that's inherently multi-graph — it needs `StarLayerDataset`, not `StarLayerGraph` (see Section 1's dataset example for `ds.get_context()`/`ds.quads()`):

```python
from starlayergraph import StarLayerDataset, TripleTerm

ds = StarLayerDataset()
ds.bind("ex", EX)
g1 = ds.get_context(EX.graph1)
g1.add_reification(EX.claim, TripleTerm(EX.bob, EX.knows, EX.carol))

trig_text = ds.serialize(format="trig12")

ds2 = StarLayerDataset()
ds2.parse(data=trig_text, format="trig12")
reloaded = ds2.get_context(EX.graph1)

for s, p, o in reloaded.triples((EX.claim, None, None)):
    print(reloaded.qname(s), reloaded.qname(p), o)
```

Output:

```text
ex:claim rdf:reifies <<( ex:bob ex:knows ex:carol )>>
```

`ds2` never called `.bind("ex", EX)` itself — the `@prefix ex: ...` declaration embedded in `trig_text` by the first serialize is enough for `ds2.parse()` to pick the binding up automatically, the same way a plain `g.parse()` does (see Section 1).

## Summary

StarLayer provides a practical bridge from the older rdflib/pySHACL stack to the newer RDF 1.2 and SHACL 1.2 world:

- richer graph semantics
- SPARQL support for RDF 1.2 constructs
- SHACL validation and rules for modern RDF data
- backend interoperability across storage engines and RDF serializations

This keeps the user experience familiar while making the more advanced RDF 1.2 and SHACL 1.2 features available in a working implementation.



