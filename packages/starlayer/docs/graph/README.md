# docs

*Last reviewed: 2026-09-27*

- [Rules that bite and how the code is laid out](../../starlayer/graph/CLAUDE.md) - start here
- starlayergraph.md (historical): design of the old rdflib-based class
- starlayergraph_vs_rdflib.md (historical): full method-by-method coverage tracker - what's overridden, what's inherited, what's StarLayer-only
- sparql12_design.md (historical): SPARQL 1.2 query support, rewrite strategy, and query examples
- rdf12_sparql12_gap_analysis.md: RDF 1.2/SPARQL 1.2 feature-by-feature conformance tracking against the W3C spec text directly
- manchester_syntax_gap_analysis.md: Manchester OWL Syntax parser conformance tracking against the real OWL API parser (not just the W3C REC)
- sparql12_protocol_gap_analysis.md: SPARQL 1.2 Protocol conformance tracking for the deleted HTTP client `backends/native.py` (historical)
- rdf_interop_gap_analysis.md: RDF 1.2 Interoperability spec (basic-encode/decode of triple terms) conformance tracking - still an Editor's Draft, not implementation-ready
- testing-strategy.md: the four test tiers, what each one actually checks, and known degradation points
- performance.md (historical): full benchmark write-up and backend recommendations
- [future_enhancements.md](../future_enhancements.md): deferred follow-ups and rationale behind non-obvious decisions (one file for the whole project)
- `../../../../docs/upstream-issues/`: bugs found in third-party dependencies (rdflib, Oxigraph, Fuseki) to report upstream
- [`../../tests/graph/vendor/spec_snapshots/`](../../tests/graph/vendor/spec_snapshots/): vendored W3C spec text snapshots used for conformance diffing (see its own README.md)
