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
- 🔜 Which classes are ever instantiated, and from where? — **checked empirically, not assumed**: a bare constructor call (`Thing()`) does NOT currently resolve to anything - `_resolve_call_target()`'s bare-`Name` branch only checks `functions_by_dotted_path`, never `classes_by_dotted_path`, so `ClassName()` silently produces no edge at all. An earlier version of this doc claimed this "falls out for free" - confirmed wrong via a direct test before writing this entry. Fixing it needs a real design decision first (should a constructor call be `slkg:calls` pointing at the class itself, widening that property's range beyond `slkg:Function`, or a new, separate `slkg:instantiates` property?) - not scheduled yet.

## Inheritance

- ✅ Does method X on a subclass override a same-named method on a base class? — `slkg:overrides`, built 2026-10-14, **same-file only** (the base class must be defined in the same file as the overriding method - a real override of a cross-file base method gets no edge in this version, a deliberately narrower scope than `slkg:calls`'s own project-wide resolution). Checked against the real codebase: only 5 same-file class-to-class inheritance pairs exist in the whole project, and none of them happen to redeclare a shared method name - confirmed via direct inspection, not assumed, so `slkg:overrides` currently has zero real instances. A true negative, not a bug: this codebase's own documented architectural preference is composition over inheritance almost everywhere (see e.g. `StarShaclSchema`'s own `CLAUDE.md` history).

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

- 🔜 Does this function have a test that exercises it? — the call-graph machinery needed for this is done; still needs `tests/` pointed at the same extractor (see `build.py::refresh()`'s own hard-coded single-source-root assumption, flagged as a separate follow-on below). Once that's done, a test file calling the function under test is just an ordinary `slkg:calls` edge - no special "testedBy" relationship needed.
- 🔜 Which functions have zero test coverage (by this graph's own definition)? — same dependency as above.

## Architecture / coupling

- ✅ Which modules import which other modules? (already captured via `importsModule`.)
- ✅ Which two subpackages are most tightly coupled (most cross-import edges)? — a query over existing data, no extractor change needed.
- ✅ Finer-grained coupling (which *function* in module A calls which *function* in module B) — now answerable directly via `slkg:calls`, subject to the same resolution-confidence caveats noted above.

## Known upstream bugs / workarounds

- 🗂️ Which functions exist specifically to work around a known upstream bug (rdflib/pyshacl/etc.), and which bug? — not derivable from the AST at all; this is a human judgment that only exists in a comment or a person's head. Needs a separate, curated mechanism: a small hand-maintained set of "known bug" entities (seeded from `docs/graph/rdflib-upstream-issues.md` and the scattered `xfail` comments flagged in this session's own `future_enhancements.md` entry), with an explicit link from each affected function to the bug it works around. Closer to the long-deferred "curated graph layered on top of the auto-generated one" idea than to anything the extractor computes.

## Specifications / standards grounding

- ⛔ Which functions cite a specific W3C spec section as their rationale? — deliberately out of scope for this graph (explicit decision); if wanted, build as a separate index outside `codekg`, not inside it.

---

## Roadmap sequencing note

Call-graph edges, method-override detection, and the public/private/dunder visibility flags were all built 2026-10-14 (`codekg/extractor/symbol_index.py` + `visitor.py`/`build.py` changes) - all computed fresh from the AST on every refresh, never written into any docstring (see this doc's own earlier reasoning, still valid: these are structural facts the code either has or doesn't, independent of what any docstring claims, so they're extracted the same way parameter types already are, not transcribed by hand). Verified against the real codebase, not just unit-tested in isolation - including a real resolution-priority bug found and fixed along the way (`shacl/validator.py::_default_validate()`'s own local `from pyshacl import validate` shadowing a same-named module-level function in the same file - confirmed live before the fix, confirmed gone after it).

Still 🔜, in two different kinds:

1. **Extracting `tests/` too** - the one remaining piece needed for the "Testing linkage" rows. `build.py::refresh()` hard-codes a single source root (`packages/starlayer/starlayer`) for every target path's dotted-path computation; pointing it at `packages/starlayer/tests/` needs that generalized to a second root with its own prefix. Not scheduled yet.
2. **A curated layer**, hand-maintained, not AST-derived: the "known upstream bugs" bucket. Separate effort, separate mechanism, not scheduled yet.

One real, confirmed gap, not yet resolved either way: constructor calls (`ClassName()`) don't resolve to anything at all right now (see the "Relationships / call graph" section above) - needs a design decision (widen `slkg:calls`'s range, or add a separate `slkg:instantiates`) before it can be built.
