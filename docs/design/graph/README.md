# docs

*Last reviewed: 2026-11-13*

- [Rules that bite and how the code is laid out](../../../packages/starlayer/starlayer/graph/CLAUDE.md) - start here
- rdf12_sparql12_gap_analysis.md: RDF 1.2/SPARQL 1.2 feature-by-feature conformance tracking against the W3C spec text directly
- manchester_syntax_gap_analysis.md: Manchester OWL Syntax parser conformance tracking against the real OWL API parser (not just the W3C REC)
- rdf_interop_gap_analysis.md: RDF 1.2 Interoperability spec (basic-encode/decode of triple terms) conformance tracking - still an Editor's Draft, not implementation-ready
- testing-strategy.md: the four test tiers, what each one actually checks, and known degradation points
- [future_enhancements.md](../future_enhancements.md): deferred follow-ups and rationale behind non-obvious decisions (one file for the whole project)
- `../../upstream-issues/`: bugs found in third-party dependencies (rdflib, Oxigraph, Fuseki) to report upstream
- [`../../tests/graph/vendor/spec_snapshots/`](../../../packages/starlayer/tests/graph/vendor/spec_snapshots/): vendored W3C spec text snapshots used for conformance diffing (see its own README.md)
- The notes on the old rdflib-based class (architecture, method coverage, Fuseki setup, performance, SPARQL 1.2 design, Protocol analysis) are in [`docs/working/archive/`](../../working/archive/README.md) as `design-graph-*`
