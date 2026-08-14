# CLAUDE.md

Project-specific instructions for Claude Code sessions working in this repo. See `docs/README.md` for the docs index (start with `docs/implementation-plan.md`).

## Testing discipline: verify coverage adversarially, not just by existence

Before marking a test - or a `docs/shacl12-gap-matrix.md` row - "done" for a native/patched behavior, don't stop at "a test exists and passes." Check whether it would still pass with the change reverted:

- **Fixture-based tests**: could the *old* form (whatever pySHACL, or whatever baseline, did before starshacl's change) already satisfy this exact test? Run the fixture through plain, unpatched `pyshacl.validate()` - no `StarShaclValidator`, no meta-shapes, no native component registration - and confirm it produces the *opposite* result from what starshacl produces. If it doesn't, the test isn't exercising starshacl's own code at all; it's redundant with pySHACL's existing behavior.
- **Meta-shacl well-formedness rules**: confirm a genuinely malformed value is actually rejected, not just that a well-formed value passes. "Passes when valid" and "rejects when invalid" are two different claims - a test covering one does not imply the other.

This is cheap (one throwaway script per feature, not a new test-writing methodology) and catches a real, repeated failure mode: a 2026-07-20 coverage audit found that `sh:ShapeClass` implicit-class-target coverage, `sh:values`'s "done" status, and 8 of the 11 new SHACL 1.2 predicates' malformed-usage tests had all passed review while quietly not testing what they claimed to (see `docs/shacl12-gap-matrix.md` for the specific fixes and reasoning). Every instance had the same root cause: the same pass that wrote the feature also wrote the test confirming it, without ever asking "would this fail if I deleted what I just added?"

**Don't treat a coverage audit's own findings as ground truth either** - verify audit claims against the actual test file before acting on them. The audit above also produced a false claim (that `owl:imports` cycle/loader-failure edge cases were untested, when they already were) - only the empirical check caught it.

## Stale references after a rename: a real, cheap-to-catch failure mode

A 2026-08 sweep found `sh:sparql` fixtures calling `isTripleTerm(...)` - a function name only the old, since-removed `sparql12_to_11.py` text-rewriter ever supported (the current grammar only recognizes `isTRIPLE`) - and the shipped meta-shapes (`starshacl/assets/*.ttl`) still declaring `stsh:` under the pre-rename `pyshacl-starlight` namespace instead of `starshacl`. Both shipped silently for a long time: nothing checks that a fixture's embedded query text, or a namespace prefix, still refers to something that actually exists in the current codebase after a rename.

`tests/unit/test_fixture_sparql_syntax.py` now guards the first half of this (parses every `sh:select`/`sh:ask`/`sh:construct` string in `starshacl/assets/*.ttl` and `tests/fixtures/shapes/*.ttl` against the real grammar - would have caught `isTripleTerm` immediately). No automated guard exists yet for the namespace half; if another rename happens, grep the whole repo (not just `.py` - `.ttl` fixtures and shipped assets too) for the old name/namespace and confirm zero hits before considering the rename done.
