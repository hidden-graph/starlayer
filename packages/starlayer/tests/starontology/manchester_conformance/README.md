# Manchester completeness suite

Answers one question: **is the Manchester Syntax parser, and the `manch:` tree built from it, complete?**
Triggered by the SQE finding that an RDF encoding of SPARQL could not express arbitrary queries.

Status: the suite found 14 gaps; all genuine defects are fixed in the parser, and the tree layer is fixed in
a working copy (`wip/`, see `WIP.md`) that still has to be merged into `starontology/`. What remains is
listed in the Findings table below; every remaining exception is a strict xfail or a documented oracle
deviation in `known_failures.py` and breaks loudly if its status changes.

## What it checks

| File | Property | Oracle |
|---|---|---|
| `test_mc_coverage_matrix.py` | every W3C grammar production (71 + 13 labelled alternatives + list instantiations) is exercised by a corpus case | the W3C Note's BNF, `vendor/` |
| `test_mc_differential.py` | `parse_manchester` output is OWL-equivalent to OWL API 5.1.20 | committed goldens (`goldens/`), no JVM at test time |
| `test_mc_note_only.py` | constructs the Note allows but OWL API rejects produce the structure the Note implies | the Note |
| `test_mc_tree.py` | tree validates; tree→OWL ≅ direct parse; render re-parses; second pass stable | the parser itself |
| `test_mc_negative.py` | malformed input raises `ManchesterSyntaxError` (incl. truncation probes) | OWL API for the "genuine defect" ones |
| `test_mc_introspection.py` | ontology, encoder and shapes agree; snapshots match live files | structural |
| `test_mc_generated.py` | Hypothesis: random valid documents hold the tree invariants | the parser itself |

Marker: `manchester_conformance`. Run: `pytest packages/starlayer/tests/starontology/manchester_conformance`.
The tree tests take about 2.5 minutes (SHACL validation per case); everything else runs in seconds.

## Regenerating the OWL API goldens (offline, needs a JVM)

```
python tests/starontology/manchester_conformance/tools/regen_owlapi_goldens.py \
    --jar "/path/to/manchester-owl-parser.jar"
```

Each golden records the jar's SHA-256. The goldens in the repo were produced on 2026-10-18 from a jar
bundling OWL API 5.1.20. The harness's Turtle writer drops the `#` from the default prefix, repaired in
`helpers.owlapi_graph_from_golden`.

## Findings

Codes are used in `known_failures.py`. "Oracle" = OWL API 5.1.20; "Note" = W3C Manchester Syntax Note;
"Mapping" = W3C OWL 2 RDF Mapping. Status is as of the last commit on this branch.

| Code | Finding | Status |
|---|---|---|
| F1 | **Top-level truncation**: a non-keyword token (IRI, string, `)`, `[`) at top level silently ended parsing and dropped the rest of the document (`peek_word()` returned `None`, which the loop took for end of input). It also hid F7's dropped facet. | **Fixed.** |
| F1b | The tree module kept its own copy of the top-level loop, so every parser fix would have missed it. | **Fixed**: one shared `_run_top_level`. |
| F2 | `Ontology: <iri> <versionIRI>`: no `owl:versionIRI`, and (via F1) every following frame dropped | **Fixed** |
| F3 | `Annotations:` in the `Ontology:` header refused; an anonymous ontology produced no `owl:Ontology` node and dropped its imports | **Fixed** (header annotations, blank ontology node) |
| F4 | Quoted-string escapes `\"` `\\` not decoded (the serializer already encoded them) | **Fixed** |
| F5 | `+7`, `+0.125` and every floating-point literal (`2f`, `.5f`, `1.5e3f`) parsed as IRIs | **Fixed** |
| F6 | nodeID (`_:b1`) individuals unsupported (frame name, SameAs, Facts, enumeration, `value`, annotation target) | **Fixed** |
| F7 | Data-property restrictions used the class-expression path: wrong OWL types, `owl:onClass` for qualified data cardinalities, `d some xsd:integer[>= 5]` dropped its facet | **Fixed**: the parser classifies each restriction as data or object from the property's declaration anywhere in the document, else from the filler's shape |
| F8 | `langRange` facet unsupported | **Fixed** |
| F9 | Annotation-of-annotation unsupported | **Fixed** (`owl:Axiom` for a frame-level assertion, `owl:Annotation` otherwise) |
| F10 | Inline `Annotations:` on the six Misc axioms unsupported (documented as deliberate) | **Fixed** (pairwise triples reified, n-ary `AllDisjoint*`/`AllDifferent` nodes carry them) |
| F11 | **Short datatype names** `integer`/`decimal`/`float`/`string` mis-parsed as `:integer` etc. | **Fixed** |
| F12 | `[>=1,<10]` mis-tokenised | **Fixed** |
| F13 | Length facets: we keep the literal as written (`"5"^^xsd:integer`), the oracle writes a plain literal | **Resolved: oracle deviation.** The Mapping's rule `_:y_i F_i lt_i` uses the literal as given. Spec-derived check in `test_mc_note_only.py`. |
| F14 | Oracle writing quirks: annotated `sameAs` in both directions; annotated chain list typed `rdf:List` | **Resolved: oracle deviations.** Mapping section 2.3.2 repeats annotations per pairwise triple; Table 1 builds lists without `rdf:type rdf:List`. |
| F15 | **The Note's own facet table looks erroneous**: it maps `<=` to `xsd:minInclusive`, `<` to `minExclusive`, `>=` to `maxInclusive`, `>` to `maxExclusive`. We and the oracle follow the meaning (`>=` is the minimum). | **Noted, not followed.** Worth reporting upstream. |
| N | `Characteristics: Transitive` (etc.) accepted on a data property; the Note allows only `Functional` | **Fixed** |

**Open policy question (4 strict xfails):** OWL API accepts four inputs the Note's grammar rejects: a
one-member `DisjointClasses:`, a one-member `DisjointUnionOf:`, a one-member `SubPropertyChain:`, and
`"x"@` (empty language tag). The suite pins the current behaviour; decide whether to follow the Note
(reject) or the oracle (accept). Not defects either way.

### Process finding

The conformance suite caught two regressions introduced by the fixes themselves within one run each: the
tree's nodeID encoding mistaking an `rdf:List` head for an individual, and the live tree module breaking
when the parser's recording hooks gained arguments (see `WIP.md`, "Coupling hazard").

## Next

1. Merge the tree-layer working copy back into `starlayer/starontology/` (procedure in `WIP.md`), then
   regenerate `starontology.trig` with `python scripts/build.py`. Check whether `manchester_shapes.ttl` is
   generated or hand-maintained before editing it there.
2. Decide the four Note-versus-OWL-API strictness questions above.
3. Update `docs/graph/manchester_syntax_gap_analysis.md` (it still lists header annotations, `langRange`
   and Misc annotations as unsupported) and `docs/graph/CHANGELOG`.
4. Keep the Hypothesis generator growing: nodeIDs, annotations (including nested), header annotations and
   the remaining facets are not generated yet.
