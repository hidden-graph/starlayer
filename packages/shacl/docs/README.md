# docs

*Last reviewed: 2026-08-13*

- `../CLAUDE.md`: project-specific instructions for Claude Code sessions (currently: the testing-coverage verification discipline)
- `../CHANGELOG.md`: what changed, grouped by theme
- implementation-plan.md: current status, architecture direction, and roadmap - start here
- shacl12-gap-matrix.md: SHACL 1.2 feature-by-feature status matrix across all six documents, including Meta-SHACL policy, gaps, and how to track upstream spec changes - see also `starshacl/assets/shacl12-*.ttl` (the meta-shapes themselves, reusable standalone - documented in `../README.md`'s "SHACL 1.2 Meta-Shapes" section)
- w3c-shacl12-test-suite-plan.md: plan for vendoring and running the W3C SHACL 1.2 test suite (`w3c/data-shapes` repo's `shacl12-test-suite/`), and the procedure for absorbing it as the Working Group keeps growing it
- shacl-presentation-content.md: human-editable draft of the meta-shapes' documentation/UI-hint content (predicate names/descriptions/examples, field groups, `shui:` widget metadata) - `starshacl/assets/shacl12-*.ttl` are hand-converted from this
- pyshacl-upstream-issues.md: bugs found in pySHACL (third-party dependency) to report to its maintainers
- w3c-shacl12-test-suite-issues.md: issues found in the W3C SHACL 1.2 test suite itself (fixtures whose own expected result doesn't follow from the spec) to report to `w3c/data-shapes`
- compatibility.md: graph contract, semantic versioning policy, compatibility statements
- benchmark-baselines.md: adapter encode/decode benchmark results over time
- starlayergraph-upstream-change-log.md: proposed/landed StarLayerGraph changes discovered during starshacl work
- releasing.md, release-notes-template.md: release process and release-notes template
