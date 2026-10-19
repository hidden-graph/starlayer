# Manchester completeness suite

Answers one question: **is the Manchester Syntax parser, and the `manch:` tree built from it, complete?**
Triggered by the SQE finding that an RDF encoding of SPARQL could not express arbitrary queries. Status:
**Part A (find the gaps) is done; no library code has been changed.** Every gap below is a strict xfail in
`known_failures.py` and flips to a failing XPASS the moment it is fixed.

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

## Findings (first run)

Codes are used in `known_failures.py`. "Oracle" = OWL API 5.1.20; "Note" = W3C Manchester Syntax Note.

| Code | Finding | Severity | Oracle agrees it is a defect? |
|---|---|---|---|
| F1 | **Top-level truncation**: a non-keyword token (IRI, string, `)`) at top level silently ends parsing and drops the rest of the document. `peek_word()` returns `None` for any non-WORD token and the top-level loop treats that as end of input. | **Critical, silent loss** | Yes (rejects all 5 truncation probes) |
| F2 | `Ontology: <iri> <versionIRI>`: no `owl:versionIRI`, and via F1 every following frame is dropped | High, silent loss | n/a (oracle accepts) |
| F3 | `Annotations:` in the `Ontology:` header refused | Medium | Oracle accepts |
| F4 | Quoted-string escapes `\"` `\\` not decoded | High, wrong value | Oracle decodes |
| F5 | `+7`, `+0.125` and **all floating-point literals** (`2f`, `.5f`, `1.5e3f`) parsed as IRIs, not literals | High, silent mis-parse | Oracle: integer/decimal/float literals |
| F6 | nodeID (`_:b1`) individuals unsupported (frame name, SameAs, Facts, enumeration, `value`, annotation target) | Medium | Oracle accepts in frames, rejects `value`/annotation target; Note allows all |
| F7 | **Data-range fillers use the class-expression path**: `d some xsd:integer[>= 5]` silently drops the facet; `d some {1,2}`/`not xsd:string`/`or` get `owl:Class` types and `owl:complementOf`; qualified data cardinalities use `owl:onClass` instead of `owl:onDataRange` | **High, silent loss + wrong OWL** | Yes |
| F8 | `langRange` facet unsupported | Low (documented) | Oracle accepts |
| F9 | Annotation-of-annotation (`Annotations: Annotations: ... `) unsupported | Medium | Oracle accepts |
| F10 | Inline `Annotations:` on the six Misc axioms unsupported | Medium (documented as deliberate) | Oracle accepts and maps |
| F11 | **Short datatype names** `integer`/`decimal`/`float`/`string` (allowed by the Note) are mis-parsed as `:integer` etc. in the default namespace | **High, silent wrong** | Oracle rejects them; Note allows |
| F12 | `[>=1,<10]` (no spaces) mis-tokenised | Low | Oracle accepts |
| F13 | Length facets: we emit `xsd:integer` values, oracle writes plain literals | **Unresolved**: needs the OWL 2 RDF-mapping check | — |
| F14 | Oracle writing quirks (annotated chain list typed `rdf:List`; annotated `sameAs` in both directions) | Pending W3C check | — |

Also recorded (not defects of the same kind): OWL API accepts `DisjointClasses: A`, a one-element
`SubPropertyChain:` and `"x"@` which the Note's grammar rejects (policy: Note vs OWL API parity).
Accepted-by-us, rejected-by-oracle cases where the Note allows the construct and our output is correct are
in `test_mc_note_only.py` (`p some q some B`, `p some not B`, `B that not p some C`, ...).

### What passed (and why it matters)

- **The tree layer is structurally sound.** Every corpus case the parser accepts passes all four tree
  checks, the ontology/encoder/shape vocabularies agree in both directions, and the generated documents
  hold the invariants (20 examples by default; a larger unseeded hunt is run before sign-off). The tree
  gaps are *inherited from the parser*: the tree faithfully records what the parser understood, including
  its mistakes (for F7 the dropped facet is dropped in the tree too).
- Of 252 corpus cases, 250 were put to the oracle: it accepted 232 and rejected 18. Of the 232, 194 match
  OWL API exactly and 38 are the gaps above.
- Coverage matrix: 96 of 97 rows exercised (only `entity` has no surface syntax; 97 = 71 productions
  minus 3 list templates, plus 13 labelled alternatives, plus 16 list instantiations).

## Next (Part B, awaiting review of this report)

Fix in dependency order, each starting from its xfail: F1 (and F2) first because they silently lose data;
F7 and F5/F11/F4 (wrong values); then F3/F9/F10/F6; then F8/F12; resolve F13/F14 against the W3C mapping.
Each fix flips its registry entries; regenerate derived files with `python scripts/build.py`.
