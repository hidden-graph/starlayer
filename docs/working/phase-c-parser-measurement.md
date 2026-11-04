# Phase C0: W3C syntax suites against Oxigraph's parsers and serializers (2026-11-04)

Branch `mig-phase-c`, from `shacl-engine` at 1396753. pyoxigraph 0.5.13. Question: can the hand-written parsers and serializers
in `starlayer/graph/{parsers,serializers}` go, with Oxigraph (and the `OxGraph`/`OxDataset` wrapper) doing the work?

## Method

- **Suites**: W3C `rdf-tests`, the commit the repo already pins for the Turtle 1.2 suite (`d5d930b0`, see
  `tests/graph/w3c_turtle12/data/VENDORED_FROM.md`). The repo vendors only Turtle 1.2 (106 tests). For this measurement the whole
  `rdf/rdf12` and `rdf/rdf11` trees of that commit were read from a local tarball copy (not committed): Turtle, TriG,
  N-Triples, N-Quads and RDF/XML, positive syntax, negative syntax and evaluation tests (1,252 tests; 82 `PositiveC14N`
  serializer tests are counted separately below). `rdf12/rdf-semantics` and `rdf11/rdf-mt` are entailment suites, not parsers, so
  they are out of scope here. The harness is a throwaway script (manifest.ttl is read with pyoxigraph; no test code in the repo yet).
- **Evaluation tests** compare the parsed quads with the expected `.nt`/`.nq` by RDFC-1.0 isomorphism
  (`rdfc_native.isomorphic`, literals compared as terms, so `"04"^^xsd:integer` differs from `"4"^^xsd:integer`).
- **Columns**:
  - *Hand-written front door*: `StarLayerGraph`/`StarLayerDataset.parse(format='<fmt>12', publicID=<test base>)`, which is what
    callers use. Its output is converted to engine terms for comparison.
  - *Hand-written raw parser*: `StarLayerTurtleParser`, `parse_trig12`, `parse_ntriples12`, `parse_nquads12`, `parse_rdfxml12`
    called directly. For evaluation tests this column only checks that parsing succeeds (the raw output is the old `tt:` encoding).
  - *Oxigraph parser*: `pyoxigraph.parse(...)`, the parser itself, with the test base IRI.
  - *Wrapper*: `OxDataset.parse(...)`, i.e. the parser plus insertion into a store.
- Cells read `positive / negative / evaluation` as passed/total.

## Result

| Format | Suite | Positive / negative / eval tests | Hand-written front door | Hand-written raw (parse only for eval) | Oxigraph parser | Wrapper (store) |
|---|---|---|---|---|---|---|
| Turtle | RDF 1.2 | 41 / 33 / 32 | 41, 31, 32 = **104/106** | 41, 30, 32 = 103/106 | 41, 33, 32 = **106/106** | 41, 33, 30 = 104/106 |
| Turtle | RDF 1.1 | 74 / 94 / 145 | 73, 74, 140 = 287/313 | 73, 67, 141 = 281/313 | 74, 94, 145 = **313/313** | 74, 94, 135 = 303/313 |
| TriG | RDF 1.2 | 24 / 11 / 26 | 24, 8, 26 = 58/61 | 24, 8, 26 = 58/61 | 24, 11, 26 = **61/61** | 61/61 |
| TriG | RDF 1.1 | 99 / 115 / 143 | 86, 95, 120 = 301/357 | 86, 93, 121 = 300/357 | 99, 115, 143 = **357/357** | 99, 115, 133 = 347/357 |
| N-Triples | RDF 1.2 | 8 / 26 / - | 8, 23 = 31/34 | 8, 21 = 29/34 | 7, 26 = 33/34 | 33/34 |
| N-Triples | RDF 1.1 | 41 / 29 / - | 40, 29 = 69/70 | 69/70 | 41, 29 = **70/70** | 70/70 |
| N-Quads | RDF 1.2 | 7 / 20 / - | 7, 20 = 27/27 | 7, 19 = 26/27 | 7, 20 = **27/27** | 27/27 |
| N-Quads | RDF 1.1 | 53 / 34 / - | 52, 34 = 86/87 | 86/87 | 53, 34 = **87/87** | 87/87 |
| RDF/XML | RDF 1.2 | 0 / 2 / 29 | 2, 14 = 16/31 | 2, 26 = 28/31 | 2, 27 = 29/31 | 29/31 |
| RDF/XML | RDF 1.1 | 0 / 40 / 126 | 40, 105 = 145/166 | 40, 126 = 166/166 (parse only) | 40, 124 = 164/166 | 164/166 |
| **All** | | | 1,124/1,252 | 1,146/1,252 | **1,247/1,252** | 1,225/1,252 |

RDF 1.2 tests only: hand-written front door 236/259, Oxigraph parser 256/259, wrapper 254/259. (The RDF/XML parsers of the
front door with the plain names `xml`/`rdf-xml` go to rdflib and pass 2 of 29 RDF 1.2 evaluation tests, as rdflib knows no
triple terms or annotations.)

### Oxigraph failures (5 tests, 3 causes)

| Test | Cause | Class |
|---|---|---|
| `ntriples-version-1` (N-Triples 1.2) | The `VERSION "1.2"` directive is read by Oxigraph's Turtle and TriG parsers but not by its N-Triples/N-Quads parsers. **Resolved in the wrapper (2026-11-04)**: `OxGraph/OxDataset.parse` validates the directive itself (`oxgraph/ntversion.py`) and hands Oxigraph the text with the directive line emptied, line numbers kept; the four `ntriples-version-bad-*` negatives are rejected for their own reasons (wrong case and `@version` are not directives and stay Oxigraph's errors; a numeric or IRI specifier fails the directive check). | Fixed in the wrapper |
| `rdf12-xml-an-13`, `rdf12-xml-an-14` (RDF/XML 1.2, `rdf:annotation` with `parseType="Literal"`) | The XMLLiteral keeps the in-scope namespace declarations (`<br xmlns:rdf=... xmlns:eg=...></br>`) instead of the exclusive canonical form `<br></br>`. | Oxigraph bug (exclusive XML canonicalisation missing) |
| `xml-canon-test001`, `xml-canon-test002` (RDF/XML 1.1) | The same defect. The hand-written front door fails the same two tests. | Oxigraph bug |

All other tests pass on the parser itself: 41/41 and 33/33 on Turtle 1.2, every negative syntax test on every format.

### Wrapper-only failures (20 tests, one cause)

`OxGraph.parse`/`OxDataset.parse` fail 20 evaluation tests that the parser alone passes (Turtle 1.2: `turtle12-rt-09`, `turtle12-tt-05`;
Turtle 1.1 and TriG 1.1: `bareword_decimal`, `bareword_double`, `double_lower_case_e`, `positive_numeric`,
`numeric_with_leading_0`, `*-subm-11`, `-17`, `-19`, `-20`, `-26`). Cause: **lexical-fidelity normalisation on insert** (Oxigraph
issue #190, already recorded in `oxigraph-upstream-issues.md`): the store rewrites `"01"^^xsd:integer`, `"+1"`, `"1.0e0"` and the like to
canonical forms. Checked for each of the 20: after passing the expected graph through a store too, the two are isomorphic. In
`turtle-subm-26` the normalisation also merges three pairs of triples (22 parsed, 19 stored). This is the documented give-up, not a
parser defect; applications that need to keep lexical forms read with `pyoxigraph.parse` into a `Dataset` or use the wrapper's
fidelity mode.

### What the hand-written parsers get wrong (for the record)

Front door, RDF 1.2 and RDF 1.1 together: 40 negative tests accepted that should be rejected (Turtle 1.1 20, TriG 1.1 20, TriG 1.2 3,
Turtle 1.2 2, N-Triples 1.2 3), 36 TriG 1.1 positive/eval tests rejected (a graph block that opens a document with `{`, `\u`
escapes in IRIs, IRIs containing `'`), 21 RDF/XML 1.1 evaluation failures (19 of them: `rdf:ID` and relative IRIs are not
resolved against `publicID`), 15 RDF/XML 1.2 failures (`rdf:annotation` combined with `parseType`, base direction dropped).
Two of the Turtle 1.2 negative tests (`turtle12-bad-2`, `-4`) are accepted by the parser when it is given a `base` and rejected when it
is not, so the existing vendored suite (which passes no base) shows 106/106 while the same input with a base is accepted.

## Serializers

| Check | Oxigraph (`pyoxigraph.serialize`) | Hand-written (`graph.serialize(format='...12')`) |
|---|---|---|
| W3C N-Triples 1.2 canonical-form suite (`rdf12/rdf-n-triples/c14n`, 41 tests, exact text) | **41/41** | 7/41 (explicit `^^xsd:string`, `\u0008` for `\b`, `@EN` case, `VERSION` line placement, blank-node labels) |
| W3C N-Quads 1.2 canonical-form suite (41 tests) | **41/41** | 8/41 (same causes) |
| Round trip, plain RDF 1.1 data from the expected graphs of the evaluation tests: N-Triples / N-Quads / Turtle / TriG / RDF/XML | 250/250, 347/347, 250/250, 347/347, 250/250 | 250/250, 345/347, 249/250, 339/347, 235/250 |
| Round trip, graphs with triple terms or base direction (65 or 84 graphs): the same five formats | 65/65, 84/84, 65/65, 84/84, 65/65 | all 100 percent |
| Pretty Turtle / TriG (`oxgraph/pretty.py`, nested blank nodes, lists, annotations), same corpora | 250/250 and 347/347 plain; 65/65 and 84/84 with triple terms | n/a |

(Round trip: serialize the expected graph of every evaluation test, parse it back, compare by isomorphism. Oxigraph's RDF/XML
writer handles triple terms, so RDF 1.2 round trips through RDF/XML.) **Pretty Turtle already lives over pyoxigraph terms in
`starlayer/graph/oxgraph/pretty.py`**; the hand-written `serializers/turtle12.py` is therefore replaceable too, once the old class that
imports it is removed (it is the old class's writer, plus `WriterNamespaces`, which `graph/prefixes.py` and the SQE text writers use).

## Verdict

- Oxigraph passes the W3C gate for every format on the parser itself (1,247/1,252; the five misses are listed above) where the
  hand-written parsers pass 1,124 by their front door. No hand-written parser is better than Oxigraph on any suite except the
  N-Triples 1.2 `VERSION` directive.
- **Decisions for the owner**: (1) N-Triples/N-Quads `VERSION`: accept the gap, or have the wrapper strip a leading `VERSION` line;
  (2) the XMLLiteral canonicalisation bug: report upstream (it fails 4 W3C tests, as the old path does too) or accept;
  (3) whether the Oxigraph W3C suites become repo tests before the hand-written ones go. They would have to be vendored: only
  Turtle 1.2 is today (and its harness uses the old parser). Not done here.
- Manchester Syntax stays hand-written (no Oxigraph equivalent); so do the SPARQL results/query serializers that are not RDF syntaxes.
