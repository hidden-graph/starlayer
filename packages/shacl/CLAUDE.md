# CLAUDE.md

Project-specific instructions for Claude Code sessions working in this repo. See `docs/README.md` for the docs index (start with `docs/implementation-plan.md`).

## Testing discipline: verify coverage adversarially, not just by existence

Before marking a test - or a `docs/shacl12-gap-matrix.md` row - "done" for a native/patched behavior, don't stop at "a test exists and passes." Check whether it would still pass with the change reverted:

- **Fixture-based tests**: could the *old* form (whatever pySHACL, or whatever baseline, did before starshacl's change) already satisfy this exact test? Run the fixture through plain, unpatched `pyshacl.validate()` - no `StarShaclValidator`, no meta-shapes, no native component registration - and confirm it produces the *opposite* result from what starshacl produces. If it doesn't, the test isn't exercising starshacl's own code at all; it's redundant with pySHACL's existing behavior.
- **Meta-shacl well-formedness rules**: confirm a genuinely malformed value is actually rejected, not just that a well-formed value passes. "Passes when valid" and "rejects when invalid" are two different claims - a test covering one does not imply the other.

This is cheap (one throwaway script per feature, not a new test-writing methodology) and catches a real, repeated failure mode: a 2026-07-20 coverage audit found that `sh:ShapeClass` implicit-class-target coverage, `sh:values`'s "done" status, and 8 of the 11 new SHACL 1.2 predicates' malformed-usage tests had all passed review while quietly not testing what they claimed to (see `docs/shacl12-gap-matrix.md` for the specific fixes and reasoning). Every instance had the same root cause: the same pass that wrote the feature also wrote the test confirming it, without ever asking "would this fail if I deleted what I just added?"

**Don't treat a coverage audit's own findings as ground truth either** - verify audit claims against the actual test file before acting on them. The audit above also produced a false claim (that `owl:imports` cycle/loader-failure edge cases were untested, when they already were) - only the empirical check caught it.
