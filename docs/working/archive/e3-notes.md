# E3 notes: Manchester syntax on pyoxigraph terms (branch `mig-e3-manchester`)

Goal: `graph/parsers/manchester_parser.py`, `graph/serializers/manchester.py` and `starontology/manchester.py` import no rdflib. Terms are
pyoxigraph terms, graphs are `StarLayerGraph`. D4 follow-up 6.

## What changed

- New `graph/parsers/_ox_terms.py`: `URIRef = NamedNode`, `BNode = BlankNode`, `Literal = ox.Literal`, the `OWL` / `RDF` / `RDFS` / `XSD`
  vocabularies as `Vocab` objects (`OWL.Class` is a `NamedNode`; `node in OWL` tests the namespace), `lexical(value, datatype, lang)` for
  the literals rdflib built from Python values, and `is_valid_langtag`. Shared by the three files (and the tests).
- `parse_manchester` returns `(NamedNode | BlankNode, NamedNode, term)` triples. `StarLayerGraph.parse(format="manchester")` and
  `.serialize(format="manchester")` call the parser and writer directly (the serializer no longer goes through `to_rdflib_graph`).
- `serialize_manchester(graph)` accepts a `StarLayerGraph`, a `StarLayerDataset` (its default graph), a `pyoxigraph.Store`, or an rdflib graph
  (converted through `_rdflib_bridge.to_oxgraph`, which imports rdflib only then).
- `starontology/manchester.py`: the `manch:` tree is built in a `StarLayerGraph`; `rdflib.collection.Collection` is replaced by a list walker;
  `manchester_parse_to_tree(graph=...)` still accepts an rdflib graph as the target (merged through the bridge).
- The `import starlayer._needs_rdflib` guards of the three files are gone. `import starlayer.starontology.manchester` works without rdflib.
- Tests migrated to pyoxigraph terms: `test_manchester_{parser,serializer,ast,ast_shapes,hunt3}.py`, `test_graph_core_round4.py`, and the
  `--manchester-conformance` suite (`helpers.py`, `test_mc_note_only.py`, `test_mc_shapes_mutation.py`, `test_mc_introspection.py`,
  `tools/mutation_scan.py`). `tests/test_core_without_rdflib.py` gains a Manchester parse / serialize round trip and a tree round trip under
  blocked rdflib, and Manchester work in `test_nothing_in_the_core_imports_rdflib`.

## Behaviour that differs from the rdflib version

1. **Lexical forms are kept as written.** rdflib normalised `"+5"^^xsd:integer`, `"01"^^xsd:integer` and similar when a literal carried a
   datatype (the parser built them with its default `normalize=True`); a pyoxigraph `Literal` keeps the lexical form (the store, when the
   triples are added to a `StarLayerGraph`, normalises as for every other format: starlayer #190).
2. **A plain literal and `"x"^^xsd:string` are the same term** (RDF 1.1 / 1.2). The writer renders both as `"x"`; it used to write
   `"x"^^xsd:string` for an explicit datatype. The text round-trips to the same term.
3. **An IRI pyoxigraph rejects is a `ManchesterSyntaxError`** (a relative IRI with no `Ontology:` IRI or base to resolve it, an IRI with a
   space): rdflib's `URIRef` accepted anything. A `_:label` the store cannot hold as a blank node identifier is kept distinct as `b<hex of the label>`.
4. **The writer declares `owl:`, `rdf:`, `rdfs:` and `xsd:`** when the graph binds neither the prefix nor the namespace, as the parser does by
   default. An rdflib graph came with those bound; a `StarLayerGraph` does not.
5. **`manchester_validate` needs rdflib** (RDFS inference, `inference=ENTAILMENT.RDFS`, runs `owlrl` on an rdflib copy through the bridge): it
   raises the clear `ImportError` naming `starlayer[rdflib]`. Everything else in `starontology/manchester.py` runs without rdflib.
   `ENTAILMENT` is now the pyoxigraph-term one (`oxgraph/helpers/entailment.py`).

## Tests changed, and how

No test was skipped, xfailed or weakened. Mechanical changes: rdflib `Graph()` is `StarLayerGraph()`; `Literal(...)` calls use
`_ox_terms.lexical`; rdflib `Collection` edits are explicit `rdf:first` / `rdf:rest` edits; `str(term)` is `term.value`;
`isomorphic` is given `StarLayerGraph`s, not lists of triples. `test_ox_results.py` keeps one call that passes an rdflib graph as the target of
`manchester_parse_to_tree` (the bridge case). `srl_conformance/tools/mutation_scan.py` (SRL, not Manchester) is untouched.
