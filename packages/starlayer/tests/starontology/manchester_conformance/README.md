# Manchester completeness suite

Answers one question: **is the Manchester Syntax parser, and the `manch:` tree built from it, complete?**
Triggered by the SQE finding that an RDF encoding of SPARQL could not express arbitrary queries.

Status: the suite found 14 gaps; all genuine defects are fixed in the parser, and the tree layer is fixed in
a working copy (`wip/`, see `WIP.md`) that is deliberately **not** merged into `starontology/` yet. What remains is
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
| `test_mc_shapes_mutation.py` | the shapes REJECT damaged trees; anything that validates must decode | mutation |
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

**Policy (decided 2026-10-18): stay consistent with the OWL API.** Four inputs the Note's grammar rejects
but OWL API accepts - a one-member `DisjointClasses:`, a one-member `DisjointUnionOf:`, a one-member
`SubPropertyChain:`, and `"x"@` (empty language tag) - are therefore accepted, and pinned as such in
`test_mc_negative.py` (`LENIENT_LIKE_OWLAPI`). The same rule decided the earlier cases where the oracle
and the Note disagree: where OWL API follows the OWL 2 RDF Mapping we match it; where it deviates from the
Mapping (F13, F14) the deviation is recorded and our spec-conformant output is kept.

### Can the shapes validate a Manchester document as an RDF tree?

Accepting every valid tree (above) shows the shapes are not too strict. To test that they are not too
lax, `tools/mutation_scan.py` damages the tree of every corpus case (remove a triple, swap a value for a
literal, add a second value, drop an `rdf:type`, break a list) once per distinct (node class, property,
operator): 430 mutants. First run: **390 rejected (91%), 30 survived and still decode, 10 passed
validation yet crashed the decoder.** Of the 30 survivors, all but three were legitimately optional
(annotations, an unqualified cardinality's filler, optional header parts) or a literal swapped for a
literal where literals are valid. The weaknesses:

| Weakness | Cause | Fix |
|---|---|---|
| A node with its `rdf:type` deleted still validated, then crashed the decoder (10 cases; also a tree with no `manch:Document`) | Validation runs with RDFS inference and several properties declare an `rdfs:domain` (`subject`/`clauses` -> `Frame`, `frames` -> `Document`, ...), so the missing type is inferred straight back and every shape is satisfied; the decoder reads *asserted* types | `manchester_validate` runs a pre-flight on the asserted graph: exactly one `Document`, every node with `manch:` properties has an asserted concrete type, every asserted `manch:` type exists |
| A list whose last `rdf:rest` was missing validated | `WellFormedListShape` checked that each cell has an `rdf:first`, not that the chain ends in `rdf:nil` | the shape now requires every cell to reach `rdf:nil` (no unterminated or cyclic lists); the 12 other list shapes inherit it |
| A cyclic list made the validator itself raise | pySHACL walks `rdf:rest` while cloning the data graph, before any shape runs | the pre-flight detects cycles and reports them without running SHACL |
| List items of the wrong kind validated (a literal as a prefix, a string as an import, ...) | five lists were checked only for being lists | typed item shapes: `PrefixDeclListShape`, `IriListShape` (imports, enumerated individuals), `LiteralListShape`, `FacetRestrictionListShape` |

After the fixes `test_mc_shapes_mutation.py` pins each weakness (30 tests, ~100 s, mostly the one that
removes every triple of a rich tree in turn and requires that whatever validates also decodes), and the
full scan was re-run: **408 of 430 mutants rejected (95%), 22 survivors, zero holes.** All 22 survivors are
benign - 17 remove something optional (annotations; an unqualified cardinality's filler; the header, its IRI,
version IRI or imports) and 5 replace a literal by a literal where a literal is valid.

What the shapes still do not do, by design: check that a tree means anything coherent beyond its structure
(they accept a `Min` with a cardinality of 3 and a filler, or a `Value` whose individual does not exist),
and they accept extra unknown triples on a node (the shapes are open, not `sh:closed`).

### Process finding

The conformance suite caught two regressions introduced by the fixes themselves within one run each: the
tree's nodeID encoding mistaking an `rdf:List` head for an individual, and the original tree module breaking
when the parser's recording hooks gained arguments. The second is why hook changes are now additive only
(see `WIP.md`).

## Next

1. When the other agent's `starontology` work is finished, compare and merge the working copy (`wip/`) into
   `starlayer/starontology/` (procedure in `WIP.md`). Nothing under `starontology/` has been changed yet.
2. Decide the four Note-versus-OWL-API strictness questions above.
3. Update `docs/graph/manchester_syntax_gap_analysis.md` (it still lists header annotations, `langRange`
   and Misc annotations as unsupported) and `docs/graph/CHANGELOG`.
4. Keep the Hypothesis generator growing: nodeIDs, annotations (including nested), header annotations and
   the remaining facets are not generated yet.
