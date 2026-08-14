# docs

*Last reviewed: 2026-08-13*

- `../CLAUDE.md`: project-specific instructions for Claude Code sessions - start here
- starlayergraph.md: architecture and design overview - core concepts, package structure
- starlayergraph_vs_rdflib.md: full method-by-method coverage tracker - what's overridden, what's inherited, what's StarLayer-only
- sparql12_design.md: SPARQL 1.2 query support, rewrite strategy, and query examples
- rdf12_sparql12_gap_analysis.md: RDF 1.2/SPARQL 1.2 feature-by-feature conformance tracking against the W3C spec text directly
- testing-strategy.md: the four test tiers, what each one actually checks, and known degradation points
- performance.md: full benchmark write-up and backend recommendations
- future_enhancements.md: deferred follow-ups and rationale behind non-obvious decisions
- rdflib-upstream-issues.md, oxigraph-upstream-issues.md, fuseki-upstream-issues.md: bugs found in third-party dependencies to report upstream
- `../tests/vendor/spec_snapshots/`: vendored W3C spec text snapshots used for conformance diffing (see its own README.md)
