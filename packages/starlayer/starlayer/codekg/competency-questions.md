# Code Knowledge Graph — Competency Questions

A living list of the questions this knowledge graph (`codekg.trig`, built by `scripts/build_codekg.py`) should be able to answer. Each question is marked with its current status. When a question moves from "Roadmap" to "Answerable now," update its status here rather than deleting the history of how the graph's scope grew.

Status key: ✅ Answerable now · 🔜 Roadmap (not yet built) · 🗂️ Curated, not extracted (needs a human-maintained layer, not AST analysis) · ⛔ Out of scope (deliberately excluded)

## Structure / navigation

- ✅ What classes, functions, and methods does a given module define?
- ✅ What are a function/method's parameters — name, type, optional, default value?
- ✅ What does a function/method return, and what type?
- ✅ What does a class inherit from? What attributes/decorators does it have?
- ✅ What does a given module import (at the module level)?
- ✅ What's the cleaned docstring/summary for a given class/function/method/module?

## Relationships / call graph

Built 2026-10-14 (`slkg:calls`, Function→Function) - project-wide resolution via a whole-codebase symbol-index pre-pass (`codekg/extractor/symbol_index.py`), not scoped to same-file calls. Resolves bare-name calls (same-file nesting-scope-aware, with function-local lazy imports correctly taking priority over a same-named module-level function - see `visitor._local_import_table()`), `self`/`cls` method calls (walking the base-class chain, cross-file), and `module_alias.func()`/`ClassName.classmethod()` calls via the import table. Deliberately unresolved, by design, never guessed at: a call through a plain local variable (no type inference), a dynamic/computed call, any call on an unresolvable expression, and any call to something outside this project (stdlib/third-party - no `ExternalFunction` class was introduced, matching `importsModule`'s own precedent of not tracking specific external symbols).

- ✅ What functions/methods does function X call?
- ✅ What calls function X (reverse lookup)?
- ✅ If I change X's signature, what else might break (direct callers)?
- ✅ What's the call chain from entry point A down to low-level function B? — a `slkg:calls+` property-path query.
- ✅ Are there call cycles (A calls B calls A)? — a query over call edges, no separate extraction step.
- ✅ Which classes are ever instantiated, and from where? — `slkg:instantiates` (Function→Class), built 2026-10-14 as a separate property from `slkg:calls` rather than widening its range - "calls a function" and "constructs an instance" are different relationships. Resolved the same way bare/attribute calls are (same-file nesting, import table, module aliases), just checked against `classes_by_dotted_path` too. Verified against the real codebase: 1135 real `slkg:instantiates` edges, e.g. several modules' own helper functions constructing `TripleTerm(...)`, where the same call previously resolved to nothing at all.

## Inheritance

- ✅ Does method X on a subclass override a same-named method on a base class? — `slkg:overrides`, built 2026-10-14, originally scoped to same-file bases only, generalized project-wide the same day by reusing `SymbolIndex.resolve_method_in_chain()` (the identical cross-file walk already used for `self`/`cls` call resolution) instead of a separate same-file-only helper. Checked against the real codebase: 7 real cross-file override edges - `starontology/manchester.py`'s `_AstCursor` genuinely subclasses `graph/parsers/manchester_parser.py`'s `_Cursor` and overrides 7 of its methods - invisible under the earlier same-file-only scope, now surfaced. The handful of same-file inheritance pairs still redeclare no shared method names, consistent with this codebase's documented composition-over-inheritance style.

## Visibility / API surface

Built 2026-10-14 (`slkg:isPrivate`/`slkg:isDunder`, Class/Function/Method only - scoped out of Attribute/Parameter per direct decision).

- ✅ Is a given function/class/method public or private (leading-underscore convention)?
- ✅ What's the public API surface of a module/package (everything not underscore-prefixed)?
- ✅ Is a "private" function called from outside its own module anyway (a leaky abstraction)? — a query joining `isPrivate` with `slkg:calls`'s source module against the private entity's own module.
- ✅ Which public functions have no docstring? (already answerable via existing `rdfs:comment` presence/absence — doesn't need the public/private flag added, though the flag makes the query cleaner.)

## Dead code / unused surface

- ✅ Is this function ever called by anything, anywhere in the codebase? — zero incoming `slkg:calls` edges. **Caveat inherited directly from the call graph's own resolution limits**: zero incoming edges means "never called in a way this extractor could confidently resolve" - a function called only through a pattern it can't resolve (a local variable holding a function reference, a dynamic dispatch, a decorator-wrapped indirect call) will show as unreferenced even though it genuinely isn't dead. Treat a "zero callers" result as a lead to check, not a proof.
- 🔜 Is this parameter ever passed a non-default value anywhere? — harder than the rest: requires resolving real argument values at every call site (positional/keyword/splat), not just whether a call exists. Lower-fidelity, may not be worth building; revisit if it turns out to matter.

## Testing linkage

`tests/` is now extracted alongside source, built 2026-10-14 - `symbol_index.resolve_root()` dispatches each path to one of two known roots (source, dotted prefix `starlayer.`; tests, dotted prefix `tests.`, its own `TESTS_BLOB_BASE`), so a test file calling the function under test is just an ordinary `slkg:calls` edge across roots - no special "testedBy" relationship needed. Verified against the real codebase: all 181 real test files now appear as their own `slkg:Module`, with 484 real test→source `slkg:calls` edges, e.g. `test_entailment_rdf.py`'s own test calling `rewrite_algebra_for_rdf`.

- ✅ Does this function have a test that exercises it? — a `slkg:calls` edge from a `tests.`-prefixed function to it (same caveats as the rest of the call graph: a test that exercises a function only through an unresolvable indirection won't show up).
- ✅ Which functions have zero test coverage (by this graph's own definition)? — zero incoming `slkg:calls` edges from any `tests.`-prefixed caller.

## Architecture / coupling

- 🔜 Which starlayer modules import which other starlayer modules? — not answerable yet: `slkg:importsModule` only records imports of *external* modules (third-party and standard library); imports between this project's own modules are not extracted. Found 2026-10-19 while building the query library. Use the call graph (`slkg:calls`) for dependencies inside the project.
- ✅ Which two subpackages are most tightly coupled? — answered from the call graph (calls between subpackages), not from imports, because imports between this project's modules are not extracted (see the question above).
- ✅ Finer-grained coupling (which *function* in module A calls which *function* in module B) — now answerable directly via `slkg:calls`, subject to the same resolution-confidence caveats noted above.

## Known upstream bugs / workarounds

- 🗂️ Which functions exist specifically to work around a known upstream bug (rdflib/pyshacl/etc.), and which bug? — not derivable from the AST at all; this is a human judgment that only exists in a comment or a person's head. Needs a separate, curated mechanism: a small hand-maintained set of "known bug" entities (seeded from `docs/upstream-issues/rdflib-upstream-issues.md` and the scattered `xfail` comments flagged in this session's own `future_enhancements.md` entry), with an explicit link from each affected function to the bug it works around. Closer to the long-deferred "curated graph layered on top of the auto-generated one" idea than to anything the extractor computes.

## Specifications / standards grounding

- ⛔ Which functions cite a specific W3C spec section as their rationale? — deliberately out of scope for this graph (explicit decision); if wanted, build as a separate index outside `codekg`, not inside it.

---

## Roadmap sequencing note

Call-graph edges, method-override detection, and the public/private/dunder visibility flags were all built 2026-10-14 (`codekg/extractor/symbol_index.py` + `visitor.py`/`build.py` changes) - all computed fresh from the AST on every refresh, never written into any docstring (see this doc's own earlier reasoning, still valid: these are structural facts the code either has or doesn't, independent of what any docstring claims, so they're extracted the same way parameter types already are, not transcribed by hand). Verified against the real codebase, not just unit-tested in isolation - including a real resolution-priority bug found and fixed along the way (`shacl/validator.py::_default_validate()`'s own local `from pyshacl import validate` shadowing a same-named module-level function in the same file - confirmed live before the fix, confirmed gone after it).

Both gaps logged at the end of the prior phase were closed 2026-10-14: constructor-call resolution (`slkg:instantiates`) and extracting `tests/` as a second named root alongside source (closing the "Testing linkage" section). Both verified against the real codebase via direct SPARQL spot-checks (see each section above) and a full project test-suite run (3713 passed, 4 skipped, 41 xfailed - the one failure, `targetWhere-001`, is a pre-existing flake unrelated to this work, bisected to an earlier phase).

Also closed 2026-10-14, same day: `slkg:overrides` generalized from same-file-only to project-wide, by deleting its own bespoke same-file-filtered walk and delegating straight to `SymbolIndex.resolve_method_in_chain()` (the identical mechanism `self`/`cls` call resolution already used) - a real inconsistency once the call graph itself went project-wide, not a new capability. Surfaced 7 real cross-file override edges that were invisible before (`starontology/manchester.py`'s `_AstCursor` subclassing `graph/parsers/manchester_parser.py`'s `_Cursor`). Full suite re-run clean afterward (3715 passed - the 2 new override tests - 4 skipped, 41 xfailed, no `targetWhere-001` flake this run).

Every AST-derivable competency question in this doc is now ✅, except the explicitly low-value "non-default argument value" question (flagged above, not scheduled). Still 🔜: **a curated layer**, hand-maintained, not AST-derived - the "known upstream bugs" bucket. Separate effort, separate mechanism, not scheduled yet.
