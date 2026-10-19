# docs

*Last reviewed: 2026-08-13*

- [Rules that bite](../../starlayer/shacl/CLAUDE.md) (with design history, including the testing-coverage discipline)
- implementation-plan.md: current status, architecture direction, and roadmap - start here
- shacl12-gap-matrix.md: SHACL 1.2 feature-by-feature status matrix across all six documents, including Meta-SHACL policy, gaps, and how to track upstream spec changes - see also [`shacl12-shacl.ttl`](../../starlayer/starontology/shacl12-shacl.ttl) (the meta-shapes themselves, built by `scripts/build.py` and reusable standalone)
- w3c-shacl12-test-suite-plan.md: plan for vendoring and running the W3C SHACL 1.2 test suite (`w3c/data-shapes` repo's `shacl12-test-suite/`), and the procedure for absorbing it as the Working Group keeps growing it
- (archived 2026-10-17) the presentation content and `shacl12-presentation-shapes.ttl` now live in the repo-root `docs/working/shacl-presentation/` - see its README.md
- `../../../../docs/upstream-issues/pyshacl-upstream-issues.md`: bugs found in pySHACL (third-party dependency) to report to its maintainers
- w3c-shacl12-test-suite-issues.md: issues found in the W3C SHACL 1.2 test suite itself (fixtures whose own expected result doesn't follow from the spec) to report to `w3c/data-shapes`
- compatibility.md: graph contract, semantic versioning policy, compatibility statements
- benchmark-baselines.md: adapter encode/decode benchmark results over time
- starlayergraph-upstream-change-log.md: proposed/landed StarLayerGraph changes discovered during starshacl work
- releasing.md, release-notes-template.md: release process and release-notes template
