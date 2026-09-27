# RDF 1.2 Interoperability Spec vs. Implementation — Conformance Status

**Reviewed:** 2026-09-27, against the editor's draft at `https://w3c.github.io/rdf-interop/spec/`, fetched in full — including its three example Turtle fixture files (`ex-basicenc-input.ttl`, `ex-basicenc-input2.ttl`, `ex-basicenc-output.ttl`), which the rendered page pulls in via ReSpec's `data-include` and are invisible unless fetched separately at their own URLs. Format follows `rdf12_sparql12_gap_analysis.md`.

## Document status, and why it matters

Unlike the seven documents tracked in `rdf12_sparql12_gap_analysis.md` (all published to `https://www.w3.org/TR/...`, Working Draft through Candidate Recommendation), this spec's own `respecConfig` declares `specStatus: "ED"` — Editor's Draft, the earliest pre-publication stage, no `/TR/` URL at all. It belongs to the RDF-star Working Group. Within the document itself: the entire `basic-decode` algorithm subsection is an unwritten stub whose only content is the literal editorial note "Write this algorithm," and there's an open issue asking "Should we go even further and aim to provide interoperability between *RDF 1.1* and RDF 1.2 Full?" — i.e. the Working Group hasn't decided whether RDF 1.1 interop (this project's own stated reason for existing) is even in scope here. Treat everything below as a design sketch, not a stable target.

## 1. What this spec actually covers

A short, entirely non-normative guidance document (its own words: "the methods and tools provided here are not normative") addressing one problem: RDF 1.2 defines two conformance classes, **RDF 1.2 Full** (triple terms allowed) and **RDF 1.2 Basic** (no triple term may appear anywhere), and a Basic-only implementation has no built-in way to represent or round-trip Full content. The answer is a reversible pair of transformations: **basic encoding** (Full→Basic) replaces every triple term with a fresh blank node plus four triples using vocabulary this spec introduces (`rdf:PropositionForm`, `rdf:propositionFormSubject`, `rdf:propositionFormPredicate`, `rdf:propositionFormObject`); **basic decoding** is the inverse. It is not about SPARQL, concrete syntax, or entailment, and — per the open issue above — not (yet) about RDF 1.1 interop at all.

That last point matters here specifically: this project's stated purpose (bridging RDF 1.2 to rdflib's RDF-1.1-only term model) sounds like exactly this spec's audience, but the Working Group hasn't committed to that scope. What *is* still practically relevant: the `rdf:PropositionForm` encoding produces plain triples with ordinary IRI predicates and a blank node — nothing about it requires RDF-1.2-specific syntax, so anything that can hold plain RDF (a vanilla `rdflib.Graph`, JSON-LD, an RDF-1.1-only reasoner) can hold basic-encoded content too, even though the spec only formally claims Full-vs-Basic (both-1.2) interop. That overlap is why several places in this codebase turn out to already be solving private, narrower versions of exactly this problem.

## 2. Section-by-section

**Introduction / Notation and Terminology.** The Full/Basic conformance-class distinction is already modeled as a first-class concept in `starlayergraph/model/conformance.py` — `VALID_VERSION_LABELS = frozenset({'1.2', '1.2-basic', '1.1'})`, citing RDF 1.2 Concepts §2.1 for exactly these three labels. Every other reused term (triple term, reifier, asserted triple) already has tested code (`TripleTerm` in `model/triple.py`; `add_reification()`/`reifiers()` in `graph/starlayer_graph.py`). ✅ concept already modeled.

**Design properties (information-preserving / idempotent / universal).** Non-independent design goals evaluated against the algorithms below; "universal" comes with a deliberate, stated exception (see Limitations). Nothing to implement on its own.

**From Full to Basic (`basic-encode`).** The operative half. Verbatim: pick a triple term `tt`, mint a fresh blank node `b`, replace all occurrences of `tt` with `b`, add `(b rdf:type rdf:PropositionForm)`, `(b rdf:propositionFormSubject s)`, `(b rdf:propositionFormPredicate p)`, `(b rdf:propositionFormObject o)`. The spec's own worked example:

```turtle
# Input (Full, VERSION "1.2")
<< ex:s ex:p ex:o >> ex:q "some value".
```
```turtle
# Output (Basic, VERSION "1.2-basic")
_:r1 rdf:reifies _:gen1.
_:r1 ex:q "some value".

_:gen1 a rdf:PropositionForm;
  rdf:propositionFormSubject ex:s;
  rdf:propositionFormPredicate ex:p;
  rdf:propositionFormObject ex:o.
```

`rdf:reifies` itself is untouched (core RDF 1.2 vocabulary, not introduced by this spec) — only the triple-term value it points at gets swapped.

**StarLayer has zero implementation of this exact transformation** — a full-repo grep for `PropositionForm`/`propositionForm` returns nothing. But three structurally close, functionally narrower analogs already exist, each solving a related problem differently:

1. **`starlayergraph/compare.py::_decompose()`.** Closest analog: replaces every `TripleTerm` with a fresh blank node, same as the spec — but with a **private namespace** (`_TT = Namespace("urn:starlayergraph:canon-tt#")`, giving `_TT.subject/predicate/object`) instead of `rdf:PropositionForm`, and **no decode step at all** — it exists purely to feed triple-term-bearing graphs into rdflib's unmodified isomorphism/canonicalization algorithm. Reused verbatim by `starlayergraph/rdfc.py` (RDFC-1.0 canonicalization) and both OWL 2 DL reasoner bridges, `owl_dl.py` and `owl_dl_rustdl.py` (neither reasoner understands triple terms as a term type). A private, narrower predecessor, not a spec implementation.

2. **`StarLayerGraph._intern_tt()`** (`graph/starlayer_graph.py`). The in-memory (`backend="rdf-1.1"`) storage encoding, needed because `Graph.add()` hard-requires a real `rdflib.term.Node` and `TripleTerm` isn't one. Almost the mirror image of the spec's choice: instead of a fresh blank node it mints a **content-addressed `URIRef`** in a private namespace (`TT_NS`, keyed by `tt_hash()`), and instead of `rdf:PropositionForm` it reuses the **classic RDF 1.0/1.1 reification vocabulary** — `RDF.subject`/`RDF.predicate`/`RDF.object` — which is exactly the vocabulary this spec's own "Limitations" section says it deliberately avoided reusing, citing real-world collision risk (Uniprot's use of `rdf:Statement`-style reification). StarLayer sidesteps that same collision risk differently (a private, content-addressed namespace rather than an ordinary blank node), but it's an independently-arrived-at answer to a closely related problem, not spec compliance. `_restore()` is this codebase's real decode-equivalent, but only for its own `tt:`-namespaced encoding, never for anything `rdf:PropositionForm`-shaped.

3. **`starlayergraph/serializers/jsonld12.py`** — the one place where the actual outcome this spec enables (letting Full content pass through a Basic-only consumer) is a live, named, currently-unsolved problem rather than a hypothetical. JSON-LD has no RDF 1.2 companion spec at all (confirmed against both Fuseki 5.5.0, HTTP 500, and Oxigraph's explicit "does not support RDF 1.2 yet" - see `rdf12_sparql12_gap_analysis.md` §6). Current deliberate design: `_find_rdf12_content()` detects a triple term or `dirLangString` and `serialize_jsonld12()` raises `ValueError` rather than inventing a private encoding, matching what both reference engines do. This spec's `basic-encode` is exactly the tool that would let this module do something other than refuse. **This is the one real, worth-considering gap** — see §4.

**From Basic to Full (`basic-decode`).** The spec text for this direction is currently just an unwritten stub. The adjacent prose is complete enough to derive an implementation from (locate each asserted `(b rdf:type rdf:PropositionForm)`, gather its three companion properties, remove all four triples, substitute the reconstructed triple term everywhere `b` appeared, including two named error conditions: missing/duplicated property on `b`; simultaneous real-triple-term-and-asserted-PropositionForm-triple on the same `b`) — but no formal algorithm exists yet, one further reason this isn't implementation-ready in the normative sense the other seven tracked documents already are. StarLayer has no code decoding `rdf:PropositionForm` fragments.

**Limitations.** The spec's stated non-universality (refuses a graph containing both a real triple term and an asserted `rdf:PropositionForm` triple on the same blank node) is a non-issue today: nothing in this codebase, or in any real-world data it's likely to see, uses this vocabulary at all. The "hybrid graph" merge-safety warning is likewise inapplicable today — it would only become live if the `jsonld12.py` recommendation below were implemented and some caller merged the encoded output back into a live Full graph without decoding it first.

**Algorithms.** Pseudocode is given in full detail for `basic-encode`/`basic-encode-triple-term` (explicit recursion into nested triple terms, explicit error-exit points for both conflict conditions) but `basic-decode` is left as the unwritten stub noted above.

## 3. Not planned, and why

- **Retrofitting `_decompose()` (compare.py/rdfc.py/owl_dl.py/owl_dl_rustdl.py) onto the real `rdf:PropositionForm` vocabulary.** All four call sites discard the encoded fragment before it could ever be observed externally — it's input to a canonicalizer or a reasoner's temp-file bridge, never returned to a caller. Spending real, potentially-collidable `rdf:` vocabulary on something guaranteed to never leave the function would only introduce the exact hybrid-graph risk the spec itself warns against, for no benefit.
- **Retrofitting `_intern_tt()`'s in-memory encoding onto blank nodes + `rdf:PropositionForm`.** It solves a different problem (content-addressing so two occurrences of the same ground triple-term value collapse to one stored node, plus a decode that runs at essentially every read boundary via `_restore()`) the spec's fresh-blank-node-per-occurrence design doesn't provide directly. Rebuilding this hot-path internal storage layer around a spec whose own decode algorithm isn't written yet would be high-risk for a purely internal detail no external consumer ever observes.
- **Full RDF 1.1 ↔ RDF 1.2 Full interoperability**, as raised but left unresolved by the spec's own open issue. Not newly this project's problem: explicitly not yet in the spec's own scope, and this project already has its own extensive, independent solution (every parser/serializer/model class under `starlayergraph/`) that long predates this spec.
- **Ingesting arbitrary third-party `rdf:PropositionForm` data "from the wild."** Nothing published uses it yet, per the spec's own text. Revisit only if a real dataset or another RDF 1.2 engine starts emitting it.
- **Adding this document to the same re-verify-at-every-stage-transition cadence as the seven CR/WD documents** (`future_enhancements.md`'s "Keeping in step" section). No stage to transition from yet — it's an ED with no WD publication. Revisit once (if) it reaches WD.

## 4. If we picked this up: concrete, file-level changes

1. **New module** (e.g. `starlayergraph/interop/basic_encoding.py`): define the four new IRIs as plain `URIRef` constants against the `rdf:` namespace — confirmed live that rdflib's bundled `RDF` `DefinedNamespace` doesn't know these terms (`RDF.PropositionForm` raises `AttributeError`, as does even `RDF.reifies` itself against this project's installed rdflib), matching the existing pattern of hand-defining `RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')` in `turtle_parser.py` and `starlayer_graph.py`. Implement `basic_encode(graph)` by porting the spec's pseudocode fairly directly, reusing `TripleTerm`'s recursive-nesting shape the way `compare.py::_decompose()` already does; implement `basic_decode(graph)` from the spec's prose (no reference algorithm exists yet), including both named error conditions with a dedicated exception type.
2. **`starlayergraph/serializers/jsonld12.py`**: add an opt-in parameter (default preserves today's `ValueError` behavior) that runs the graph through `basic_encode()` before rdflib's JSON-LD writer instead of refusing, and symmetrically `basic_decode()`s on parse. Update the module's docstring and the cross-references in `rdf12_sparql12_gap_analysis.md` §6 and `future_enhancements.md`.
3. **New `tests/unit/test_rdf_interop.py`** using the spec's own three fixtures (quoted above) as golden files, plus idempotence and round-trip (`basic_decode(basic_encode(g))` isomorphic to `g` via `starlayergraph.compare.isomorphic()`) property tests, plus both named error conditions.
4. **`tests/vendor/spec_snapshots/refresh_snapshots.py`** fetches only `/TR/<slug>/` URLs, which this spec doesn't have — either add a small ED-URL fetch variant, or (more defensible given the spec's immaturity) wait until/if it reaches WD and add it to the existing `SPECS` list normally.

**Bottom line:** not entirely out of scope, but not close to something to implement wholesale either — a two-function, non-normative encode/decode utility, half-written (decode is a stub), at the earliest possible draft stage, whose only genuinely live payoff for this project today is letting `jsonld12.py` stop refusing RDF 1.2 content outright. Everything else it touches, this project has already independently and differently solved for its own internal purposes.

## Files read in full for this analysis

- `https://w3c.github.io/rdf-interop/spec/` (full document, plus its three linked Turtle fixtures)
- `packages/graph/docs/rdf12_sparql12_gap_analysis.md` (template/model document)
- `packages/graph/starlayergraph/model/conformance.py`, `model/triple.py`, `compare.py`, `rdfc.py`, `graph/starlayer_graph.py`, `graph/owl_dl.py`, `graph/owl_dl_rustdl.py`, `serializers/jsonld12.py`, `parsers/turtle_parser.py`
