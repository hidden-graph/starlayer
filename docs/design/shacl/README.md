# docs

*Last reviewed: 2026-08-13*

- [Rules that bite](../../../packages/starlayer/starlayer/shacl/CLAUDE.md) (with design history, including the testing-coverage discipline)
- shacl12-gap-matrix.md: SHACL 1.2 feature-by-feature status matrix across all six documents, including Meta-SHACL policy, gaps, and how to track upstream spec changes - see also [`shacl12-shacl.ttl`](../../../packages/starlayer/starlayer/starontology/shacl/shacl12-shacl.ttl) (the meta-shapes themselves, built by `scripts/build.py` and reusable standalone)
- (archived 2026-10-17) the presentation content and `shacl12-presentation-shapes.ttl` now live in the repo-root `docs/working/archive/shacl-presentation/` - see its README.md
- `../../upstream-issues/pyshacl-upstream-issues.md`: bugs found in pySHACL (third-party dependency) to report to its maintainers
- w3c-shacl12-test-suite-issues.md: issues found in the W3C SHACL 1.2 test suite itself (fixtures whose own expected result doesn't follow from the spec) to report to `w3c/data-shapes`
- compatibility.md: graph contract, semantic versioning policy, compatibility statements
- benchmark-baselines.md: adapter encode/decode benchmark results over time
- releasing.md, release-notes-template.md: release process and release-notes template
- The starshacl-era implementation plan, the W3C test-suite integration plan and the upstream change log are in [`docs/working/archive/`](../../working/archive/README.md) as `design-shacl-*`
