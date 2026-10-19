# starlayergraph — Architecture & Design

*Last reviewed: 2026-09-13*

## What is it

starlayergraph is an extension layer over [rdflib](https://rdflib.readthedocs.io/) that adds first-class support for **RDF 1.2**, including triple terms, `rdf:reifies` reification, and SPARQL 1.2 syntax.

It is not a replacement for rdflib. It wraps rdflib's RDF 1.1 storage and execution engine with a translation layer that hides the internal RDF 1.1 encoding.

---

## Terminology

"Backend" has been used loosely, in this doc and elsewhere, to mean three genuinely different, independent things. Use these three names instead:

| Axis | What it controls | Values | Where it actually lives in code |
|---|---|---|---|
| **Representation** | How a triple term is stored | `rdf-1.1` (synthetic `tt:HASH` encoding) / `rdf-1.2` (genuine native triple-term storage) | the real, shipped `StarLayerGraph(backend=...)` parameter - its *only* job; `_is_native` is `True` exactly when representation is `rdf-1.2` |
| **Transport** | Where the store physically lives relative to this process | `in-process` (Python `Memory` dict, or Oxigraph via `oxrdflib`'s `OxigraphStore`) / `remote` (HTTP to a separate Fuseki/Oxigraph server) | which concrete `Store` class is plugged in via `store=` |
| **Persistence** | Whether a store writes to disk | `ephemeral` / `persisted` | a property of one store's own configuration (e.g. `OxigraphStore(store=pyoxigraph.Store(path))`), not a mode selected at the `StarLayerGraph()` call site the way the other two are |

These three are independent, not degrees of one axis - confirmed concretely, not assumed: a remote Fuseki/Oxigraph server can be run `--mem` (ephemeral), and `OxigraphStore(store=pyoxigraph.Store(path))` is in-process yet persisted to a real RocksDB directory. Neither Transport value implies a Persistence value.

**"Native"** is shorthand for Representation = `rdf-1.2` specifically. It says nothing about Transport - a native graph can be in-process (`OxigraphStore`) or remote (`SPARQLUpdateStore` against a real server); both are real, supported configurations.

The real, shipped `backend=` constructor parameter means Representation only - that's its one job, and it is not being renamed (a parameter rename is a separate, much larger breaking-change effort, same discipline as the historical `profile=`→`entailment=` rename - see `starlayer/graph/CLAUDE.md`). Elsewhere in this document, "backend" is retired in favor of the specific axis meant.

---

## Core Concepts

**TripleTerm** — An RDF 1.2 triple term `<<( s p o )>>` in object position. In Python, represented as a `TripleTerm(s, p, o)` instance. A plain 3-tuple in object position is automatically promoted to a TripleTerm.

**Content-addressed encoding** — TripleTerms are stored internally as `tt:HASH` URIRefs, where the hash is a SHA-256 content address of the triple's components. The same triple term always maps to the same URI, enabling identity comparison without a central registry. The encoding is invisible to all public APIs.

**DirLangString** — An RDF 1.2 base-direction-tagged literal `"text"@lang--dir` (e.g. `"مرحبا"@ar--rtl`). In Python, represented as a `DirLangString(value, language, direction)` instance. Internally it's a plain `rdflib.Literal` whose `datatype=` URI packs `(language, direction)` — `Literal(text, lang="en--rtl")` itself raises in rdflib, but validation never fires for `datatype=`. Unlike TripleTerm, no registry is needed: the encoding is a pure function of the value, so decoding happens wherever `StarLayerGraph` already restores a result to the caller.

**StarLayerGraph** — The main entry point. A subclass of `rdflib.Graph` that intercepts reads and writes to encode/decode TripleTerms transparently. All rdflib traversal methods (`subjects()`, `objects()`, iteration, etc.) inherit correct TripleTerm behaviour automatically because they all funnel through the overridden `triples()` method.

**StarLayerDataset** — A subclass of `rdflib.Dataset` for multi-graph RDF 1.2. Each named graph is a `StarLayerGraph` with its own TripleTerm registry.

**Representation** — The default (`rdf-1.1`) representation stores triples via the `tt:HASH` encoding and rewrites SPARQL 1.2 queries to SPARQL 1.1 before execution, regardless of Transport. The native (`rdf-1.2`) representation bypasses rdflib's SPARQL stack entirely and sends queries through unmodified in whatever syntax the underlying engine itself understands - over HTTP to a real SPARQL endpoint (confirmed against Fuseki 5.5+ and Oxigraph), or in-process to a `pyoxigraph.Store` wrapped by `oxrdflib`'s `OxigraphStore`, with no HTTP at all - native representation is independent of Transport, not synonymous with "talks to a remote endpoint." An earlier `rdf-star` representation targeting an older, pre-standardization Jena draft syntax was removed 2026-07-16 after live testing found it broken against current Fuseki — see `docs/future_enhancements.md`.

**Blank nodes against a remote store** — both representations support ordinary read/write of blank-node content when `store=` is a real remote endpoint (`rdflib.plugins.stores.sparqlstore.SPARQLUpdateStore`, e.g. Oxigraph or Fuseki), confirmed live 2026-09-13 against both. This needed dedicated handling in each representation, since rdflib's own `SPARQLUpdateStore` refuses outright to serialize *any* blank node into query/update text (`_node_to_sparql()`: `"SPARQLStore does not support BNodes!"`) — a deliberate, spec-driven rdflib policy (SPARQL 1.1 query-pattern blank-node syntax is a fresh, existentially-scoped variable with no portable guarantee of naming a specific pre-existing node - see the note the exception itself links to), not a bug in either rdflib or the endpoint. Fuseki/Oxigraph both store and serve blank nodes for plain storage with zero issue; what's unstandardized is how each server labels that internal identity when it comes back in a *separate* later query's results (Oxigraph: stable, content-derived; Fuseki: a simple per-query counter that resets each request — confirmed live, two different stored nodes both labeled `"b0"` across two separate queries).

- **Native (`rdf-1.2`) representation**: `StarLayerGraph._native_triples()` resolves a bound blank node via a *provenance-tracked join* — the first time a blank node is yielded from a free-variable slot, its single-hop discovery pattern (the triple's other, concrete parts) is recorded keyed by Python object `id()` (not the node's own value - two `BNode`s can be `==` equal by label while denoting different stored nodes, confirmed on Fuseki). A later bound-BNode query re-derives the same node via a real SPARQL join against that recorded anchor, never by comparing labels across separate requests - correct regardless of how either server labels results.
- **Default (`rdf-1.1`, tt:HASH-encoded) representation**: simpler fix, via `StarLayerGraph._needs_bnode_skolemization` (true whenever `self.store` is a `SPARQLUpdateStore`) - always skolemize a blank node on write, always deskolemize on read, via the same deterministic `skolemize_bnode()`/`deskolemize_bnode()` mapping the native representation already uses for its own single-triple `add()` path. Simpler than the native fix because skolemizing is a pure function of the BNode's own label, so no provenance tracking is needed - but the trade-off (accepted only here, not for native representation) is that a real blank node's own term-kind (`isBLANK()`/`ORDER BY` fidelity) isn't preserved once round-tripped, consistent with this representation already being an encoded *simulation* of RDF 1.2 rather than a wire-faithful one.

See `packages/starlayer/docs/shacl/compatibility.md`'s "Backend Compatibility" section for what this means for `starshacl` specifically - both representations now fully support SHACL validation and rule execution against a remote store, `meta_shacl` on or off.

---

## Package Structure

| Module | Responsibility |
|---|---|
| `starlayergraph/model/` | `TripleTerm`/`DirLangString` classes, `tt_hash()` content-address encoding, and RDF 1.2 VERSION-directive conformance checking (`conformance.py`) |
| `starlayergraph/graph/` | `StarLayerGraph` and `StarLayerDataset` — the public API |
| `starlayergraph/parsers/` | Format-specific RDF 1.2 parsers: Turtle 1.2/LongTurtle 1.2, N-Triples 1.2, N-Quads 1.2, TriG 1.2, RDF/XML 1.2, TriX 1.2 (`jsonld12` was removed as a recognized format entirely, 2026-10-02 — see `packages/starlayer/docs/graph/rdf12_sparql12_gap_analysis.md` §6) |
| `starlayergraph/serializers/` | Format-specific RDF 1.2 serializers for the same formats |
| `starlayergraph/query/` | SPARQL 1.2 → SPARQL 1.1 rewriter (`sparql12_to_11.py`) and parse-tree helpers (`sparql_api.py`) for the default (`rdf-1.1`) representation |
| `starlayergraph/backends/` | Transport utilities for the native (`rdf-1.2`) representation - both remote (HTTP) and in-process Oxigraph (`native_oxigraph.py`) |

---

## Conformance Warnings

A document or query can declare a VERSION label (`"1.2"`, `"1.2-basic"`, or `"1.1"` — see RDF 1.2 Concepts sec 2.1 / SPARQL 1.2 Query sec 4.3). StarLayer checks the declared label against what's actually used (triple terms, `DirLangString`) and warns on a mismatch (never a hard error, matching the spec's own permissive framing) — `RDF12ConformanceWarning` for an RDF document (Turtle, TriG, N-Triples/N-Quads, RDF/XML), `SPARQL12ConformanceWarning` for a SPARQL query/update's own VERSION directive, per the spec's own distinction that the two label sets check different kinds of conformance. See `starlayergraph/model/conformance.py`.

---

## Further Reading

- [starlayergraph_vs_rdflib.md](starlayergraph_vs_rdflib.md) — full method-by-method coverage tracker: what is overridden, what is inherited, what is StarLayer-only
- [sparql12_design.md](sparql12_design.md) — SPARQL 1.2 query support, rewrite strategy, and query examples
- [rdf12_sparql12_gap_analysis.md](rdf12_sparql12_gap_analysis.md) — RDF 1.2/SPARQL 1.2 feature-by-feature conformance tracking
- [future_enhancements.md](../future_enhancements.md) — design history, deferred follow-ups, and rationale behind non-obvious decisions
