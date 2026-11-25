# 02.03 The Oxigraph-backed graph: material removed from the guide

Not part of the guide, and not run or linked. This is sections 5 (handing a graph to an RDF 1.1 consumer) and 4 (what the store keeps of a literal) of [02.03](02.03-oxigraph-wrapper.ipynb), removed because neither is about the store as such; each is a broader topic. It may become part of another user guide. The cell ids are the ids the cells had in the notebook. Section 3 of the guide points to `serialize(rdf_version="1.1")` and `starlayer.graph.interop` for the same conversion.

<!-- old cell b8985022, markdown -->

## 5. Handing a graph to an RDF 1.1 consumer

<!-- old cell 7551124b, markdown -->

**RDF 1.1 output.** The wrapper stores RDF 1.2 terms, including triple terms. To hand a graph to an RDF 1.1 consumer, serialise with `rdf_version="1.1"`: each triple term becomes the "basic encoding", a blank node typed `rdf:PropositionForm` with a subject, predicate and object property.

<!-- old cell af88e21b, code -->

```python
t = StarLayerGraph()
t.parse(data='''PREFIX ex: <http://example.org/>
ex:a ex:says <<( ex:b ex:knows ex:c )>> .''', format="turtle")
print(t.serialize(format="turtle", rdf_version="1.1", bnode_labels="short"))
```

Output:

```
@prefix ex: <http://example.org/> .
ex:a ex:says _:b0 .
_:b0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormObject> ex:c ;
	<http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormPredicate> ex:knows ;
	<http://www.w3.org/1999/02/22-rdf-syntax-ns#propositionFormSubject> ex:b ;
	a <http://www.w3.org/1999/02/22-rdf-syntax-ns#PropositionForm> .
```

<!-- old cell d9fdc947, markdown -->

`starlayer.graph.interop` does the same conversion in memory, on quads. `to_basic(quads)` replaces each triple term with its basic encoding, `from_basic(quads)` finds that structure and rebuilds the triple term, and `has_triple_terms(quads)` says whether there is one to replace. `to_rdf11(graph)` also encodes base-direction literals (`direction_policy="datatype"`, `"error"` or `"drop"`), and `export_rdf11(...)` writes the result in an RDF 1.1 format.

<!-- old cell 836207d8, code -->

```python
from starlayer.graph import interop

quads = list(t.store)
print("has a triple term:", interop.has_triple_terms(quads))
basic = interop.to_basic(quads)
print(len(quads), "quad ->", len(basic), "quads in the basic encoding; a triple term left:", interop.has_triple_terms(basic))
restored = interop.from_basic(basic)
print("round trip restores it:", {(q.subject, q.predicate, q.object) for q in restored} == {(q.subject, q.predicate, q.object) for q in quads})
```

Output:

```
has a triple term: True
1 quad -> 5 quads in the basic encoding; a triple term left: False
round trip restores it: True
```

# Section 4 of 02.03: what the store keeps of a literal

Parked 2026-11-15. Removed because the literal normalisation is not specific to the Oxigraph wrapper (see `docs/upstream-issues/oxigraph-upstream-issues.md`, starlayer issue #190). If a guide takes it up, open with what it costs: distinct terms merge (`"04"`, `"4"` and `"+4"` are one stored term), text-based checks see the stored form (`str(?o)`, `sh:pattern`), a round trip is not byte-identical, `rdfc10_hash` covers the stored form, and SHACL `sh:datatype` / `sh:sparql` can differ on ill-formed or non-canonical values (`StarLayerFidelityWarning`). Ill-formed values and plain strings are kept as written.

<!-- old cell 1ffd63ab, markdown -->

## 4. What the store keeps of a literal

**The store rewrites some literals on insert** (issue #190). A lexical form such as `"04"^^xsd:integer` is stored as `4`; the original text is not recoverable from the store. Ill-formed values and strings are kept as written.

<!-- old cell 7be81a16, code -->

```python
h = StarLayerGraph()
h.parse(data='<http://e/a> <http://e/age> "04"^^<http://www.w3.org/2001/XMLSchema#integer> .', format="turtle")
print([str(o) for o in h.objects()])
```

Output:

```
['"4"^^<http://www.w3.org/2001/XMLSchema#integer>']
```
