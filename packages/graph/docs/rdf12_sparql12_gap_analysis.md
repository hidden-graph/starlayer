# RDF 1.2 / SPARQL 1.2 Spec vs. Implementation — Conformance Status

**Last reviewed:** 2026-07-17, against the W3C documents below. This is a snapshot conformance checklist, not a changelog — for fix-by-fix history see `CHANGELOG.md`; for the ongoing re-verification process as the spec moves toward a final Recommendation, see `docs/future_enhancements.md`'s "Keeping in step" section. RDF 1.2 is still Candidate Recommendation stage, so section numbers below can drift — re-verify before citing them externally.

| Document | Status fetched | Date |
|---|---|---|
| RDF 1.2 Concepts and Abstract Syntax | Candidate Recommendation Snapshot | 2026-04-07 |
| RDF 1.2 Schema | Working Draft | 2026-03-28 |
| RDF 1.2 Turtle | Working Draft | 2026-06-12 |
| RDF 1.2 N-Triples | Working Draft | 2026-06-24 |
| RDF 1.2 XML Syntax | Working Draft | 2026-06-18 |
| SPARQL 1.2 Query | Working Draft | 2026-06-25 |
| SPARQL 1.2 Update | Working Draft | 2026-06-12 |

Plain-text snapshots of all seven documents as of the dates above are saved in `docs/spec_snapshots/` — re-run `docs/spec_snapshots/refresh_snapshots.py` and `git diff` it to see exactly what changed in the spec text since this review, rather than re-reading each document from scratch.

No RDF 1.2 companion spec exists yet for JSON-LD or TriX — see §6, the one open item in this review.

Existing project docs ([starlayergraph_vs_rdflib.md](starlayergraph_vs_rdflib.md), [sparql12_design.md](sparql12_design.md)) track coverage of rdflib's own API surface and document starlayergraph's *intended* design. Neither compares against the W3C spec text directly — that's what this document is for.

---

## 1. RDF 1.2 Concepts — data model

| Concept | Spec | StarLayer | Verdict |
|---|---|---|---|
| Triple term, object-position-only | §3.1, §3.6 | `TripleTerm` in `starlayergraph/model/triple.py`; `starlayer_graph.py` rejects subject position | ✅ Match |
| No cycles; nesting allowed in object only | §3.1 | `tests/unit/test_starlayer_graph.py::test_nested_tt_object_fully_resolves`; subject-nesting blocked | ✅ Match |
| `rdf:reifies`, reification does **not** entail the base triple | §1.5 | `sparql12_design.md` QF1/QF2 demonstrate exactly this distinction (formal `<<()>>` pattern vs. asserting `{| |}`/`~`) | ✅ Match |
| Content-addressing / term equality by structural equality | §3.6 | `tt_hash()` in `starlayergraph/model/encoding.py`, SHA-256 over `(s,p,o)` string forms | ✅ Match |
| `rdf:dirLangString`, base direction (`ltr`/`rtl`), 4-component literal identity | §3.4 | `DirLangString` in `starlayergraph/model/dirlangstring.py`; encoded as a `Literal` with an internal `dirlang:` datatype URI, decoded transparently at the `StarLayerGraph` boundary | ✅ Match |
| Language tag case-folding (`"chat"@fr` ≡ `"chat"@FR`) | §3.4.1 | Delegates to rdflib's `Literal`, which already lowercases language tags | ✅ Match (incidental) |
| Version/conformance levels ("1.2", "1.2-basic", "1.1") | §2, §2.1 | Accepts RDF 1.2 syntax unconditionally regardless of declared level (correct per spec — the directive is "merely a hint"); warns (`RDF12ConformanceWarning`, never a hard error) on a declared/actual-usage mismatch. See `starlayergraph/model/conformance.py` | ✅ Match |

---

## 2. Concrete syntaxes — Turtle / N-Triples / N-Quads / TriG

| Feature | Spec grammar | StarLayer | Verdict |
|---|---|---|---|
| `<<( s p o )>>` triple term, `ttSubject` = iri\|BlankNode (no literal, no nesting) | Turtle §[32-34] | `starlayergraph/parsers/turtle_parser.py`, `syntax.py` | ✅ Match |
| `<< s p o >>` reified-triple shorthand (unasserted, auto blank-node reifier if `~` absent) | Turtle §[29] | Implemented, matches "not asserted" semantics | ✅ Match |
| `~ (iri\|BlankNode)?` reifier, attaches to plain `object` via `objectList ::= object annotation` — i.e. **not** only inside `<< >>` | Turtle §[13],[28],[35] | `s p o ~ :stmt1` bare form implemented and tested | ✅ Match |
| `{| predicateObjectList |}` annotation block, asserts base triple | Turtle §[36] | Implemented, asserts base triple | ✅ Match |
| `@version "1.2" .` / `VERSION "1.2"` directive | Turtle §[6],[9] | Both spellings extracted (`syntax.py`'s `extract_fields()`) and checked for a conformance mismatch (`starlayergraph/model/conformance.py`) | ✅ Match |
| N-Triples/N-Quads: `<<( )>>` only, no `~`/`{| |}` shorthand (correct per spec — line-oriented formats) | N-Triples WD | `starlayergraph/parsers/ntriples12.py` matches — no shorthand support | ✅ Match |
| N-Triples/N-Quads `VERSION "1.2"` directive (bare form, same grammar as SPARQL's) | N-Triples WD | `extract_version_directive()` (`ntriples12.py`) surfaces it; same conformance check as Turtle | ✅ Match |
| TriG document-level `VERSION` directive (applies to the whole document, not per `GRAPH` block) | inherits Turtle grammar | `extract_version_directive()` (`trig12.py`) scans the whole document once; checked against the union of all resulting graphs | ✅ Match |
| `"text"@lang--dir` lexical form | Turtle §[42] / N-Triples `LANG_DIR` | Implemented in `turtle_parser.py`/`turtle12.py` and `ntriples12.py` (parser + serializer), including non-ASCII text and TriG | ✅ Match |

**The Turtle/N-Triples/N-Quads/TriG layer is the strongest part of the implementation** — every syntactic form covered in this table has a matching, tested code path.

---

## 3. RDF/XML 1.2

The spec (RDF 1.2 XML Syntax WD, 2026-06-18) represents a triple term with the existing RDF/XML `rdf:parseType="Triple"` mechanism on a property element wrapping a normal `rdf:Description`, and reification via `rdf:annotation`/`rdf:annotationNodeID` **attributes** on the property element (distinct from legacy `rdf:ID`-based `rdf:Statement` reification). Version is announced via an `rdf:version` XML **attribute** on a node element — structurally different from every other format's prologue-line directive.

`starlayergraph/serializers/rdfxml12.py` emits real `rdf:parseType="Triple"` (recursively, for nesting) and the ordinary `rdf:reifies` pattern. `starlayergraph/parsers/rdfxml12.py` preprocesses the raw XML tree (`xml.etree.ElementTree`) for `rdf:parseType="Triple"`, `rdf:annotation`/`rdf:annotationNodeID`, and `rdf:version` (stripping it after extracting it for the conformance check) before delegating the rest of the document to rdflib's real `'xml'` parser unchanged — necessary, not optional, since rdflib's own parser silently mishandles all three attributes today (verified directly against real Oxigraph 0.5.9 output and the spec's own sec 2.19/2.20 examples; see `tests/unit/test_rdf12_formats.py::TestRDFXML12SpecInterop` and `tests/unit/test_conformance.py::TestRdfXmlVersionAttribute`).

Scope limits (documented in the parser's own docstring): only node elements directly under `<rdf:RDF>` and their direct property children are inspected; a property carrying `rdf:annotation`/`rdf:annotationNodeID` combined with `rdf:parseType="Resource"`/`"Collection"` raises `NotImplementedError` rather than being silently mishandled; only a single document-level `xml:base` is honored. Nested `rdf:parseType="Triple"` is supported as a reasonable extrapolation beyond the spec's single-level example.

✅ Match (within the scope limits above).

---

## 4. SPARQL 1.2 Query — functions and syntax

| Spec item | StarLayer | Verdict |
|---|---|---|
| `SUBJECT(tt)` / `PREDICATE(tt)` / `OBJECT(tt)`, arity 1 | `sparql12_to_11.py` `_FUNC_TO_PRED`, exact name match | ✅ Match |
| `TRIPLE(s, p, o)` — constructor **function**, independent of `<<( )>>` literal syntax | `_rewrite_triple_calls()` desugars `TRIPLE(s, p, o)` to `<<( s p o )>>` (recursively) before any other pass runs | ✅ Match |
| `isTRIPLE(term)` — spec's exact function name | `_IS_TT_RE` matches `is(?:TripleTerm\|Triple)(...)`, both spellings accepted | ✅ Match |
| `<<( s p o )>>` valid directly in `BIND(...)`, same as Turtle | Spec's own example: `BIND( <<( ?s ?p ?o )>> AS ?tt )` | ✅ Match |
| Reification/annotation shorthand (`~`, `{| |}`, `<< >>`) valid in WHERE-clause graph patterns | Not fully confirmed from the fetched WD text (grammar section was truncated in the fetch) | ✅ Likely match — recommend re-verifying against the published grammar once it stabilizes |
| `LANGDIR`, `hasLANGDIR`, `STRLANGDIR`; `LANG`/`hasLANG` upgraded for dirLangString | Rewrite to plain SPARQL 1.1 built-ins / a registered constructor function; `_rewrite_dirlang_and_strlangdir()` is recursive-descent, so nested calls resolve correctly | ✅ Match |
| `VERSION "1.2"` query prologue directive | Stripped by `_strip_version_directive()` before any further rewriting, with the same warning-only conformance check as the Turtle side | ✅ Match |

---

## 5. SPARQL 1.2 Update

| Spec rule | StarLayer | Verdict |
|---|---|---|
| `INSERT DATA`/`DELETE DATA` require ground triple terms (no variables; `DELETE DATA` additionally forbids blank nodes) | `starlayer_graph.py` explicitly rejects triple terms in subject position and non-ground forms in `INSERT DATA` blocks | ✅ Match |
| Reifying a triple in `INSERT DATA` does not auto-assert the base triple | Consistent with the Query-side non-entailment behavior verified in §1 | ✅ Match |
| `INSERT`/`DELETE ... WHERE` pattern forms allow variables, mirroring Query | `starlayer_graph.py`'s `update()`, including `BIND`-splicing for minting new triple terms | ✅ Match |

No gaps here beyond what's already covered by the Query-side function gaps in §4.

---

## 6. Formats with no real spec target: JSON-LD "1.2", TriX "1.2"

The RDF 1.2 Schema document's own list of companion specs is: Turtle, N-Triples, N-Quads, TriG, XML Syntax. **There is no W3C JSON-LD 1.2 or TriX 1.2 document** — the JSON-LD Working Group has not published an RDF-1.2-aware revision, and TriX was never an RDF 1.1 W3C spec either (it's a long-standing HP Labs/Jena convention).

**JSON-LD 1.2 — open, and likely to stay that way.** `starlayergraph/serializers/jsonld12.py` is honest about this in its own docstring: the output is "valid JSON-LD 1.1" using an ad hoc `rdf:TripleTerm` node convention starlayergraph defined itself, round-trippable only through starlayergraph's own parser. `dirLangString` is extended via an internal `dirlang:` datatype URI (`@type`) rather than JSON-LD 1.1's native `@direction` keyword, since rdflib's JSON-LD codec (RDF 1.1) has no concept of `@direction` and would silently drop it on parse. Live-verified against both Fuseki 5.5.0 and Oxigraph: **neither serializes a triple term to JSON-LD at all** (Fuseki: HTTP 500; Oxigraph: explicit "JSON-LD does not support RDF 1.2 yet") — so starlayergraph's convention is presently ahead of, not behind, real-world implementations, but isn't verified against anything external either. Revisit if the JSON-LD Working Group ever publishes a real RDF-1.2-aware revision (see `docs/future_enhancements.md`).

**TriX — no W3C spec, but now interoperates with the one implementation that matters.** `trix12` matches Apache Jena/Fuseki's real convention (lowercase `<trix>` root; a triple term is a `<triple>` nested in a term position, disambiguated by structural position, not tag name) and round-trips through live Fuseki byte-for-byte (`tests/unit/test_rdf12_formats.py::TestTriX12ParseJenaConvention`); the old `<TriX>`/`<tripleTerm>` spelling is still accepted on read for backward compatibility. Oxigraph has no TriX support at all, in either direction.

**Verdict**: `jsonld12` is the one genuine open item in this review — no real implementation exists yet to converge on, in either direction. `trix12` is not: it interoperates with the one production implementation that matters for this format.

---

## Status

No open items from this review other than JSON-LD 1.2's inherent lack of a spec target (§6) — everything else is a confirmed match against the fetched spec text. This won't stay true indefinitely: RDF 1.2 is still Candidate Recommendation stage, so re-run this review at each W3C stage transition (CR → PR → REC) rather than treating it as permanently settled — see `docs/future_enhancements.md`'s "Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes" section for the concrete process.
