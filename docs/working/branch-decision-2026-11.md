# One line or two: `main` and `shacl-engine`

Decision memo, 2026-11-11. The question: do we maintain `main` (rdflib and pyshacl) and `shacl-engine` (Oxigraph and the native
validator) side by side, or converge on one? The answer decides whether the spec-drift work in
`spec-drift-2026-11-09.md` is done in one place or two.

## Recommendation

**Converge on `shacl-engine`.** Treat it as the one line, port the features only `main` has, move the workbench over, and put
`main` on a fixed sunset (fixes only, no features). Do the spec-drift work once, on `shacl-engine`.

## What the two branches are

| | `main` | `shacl-engine` |
|---|---|---|
| Graph classes | rdflib based | `pyoxigraph.Store` wrappers (`StarLayerGraph`, `StarLayerDataset`) |
| SHACL | wraps `pyshacl`, plus StarLayer's native components (`native_components.py`, `component_cache.py`, `constraint_annotations.py`) | its own engine (`shacl_engine/`), no `pyshacl` |
| Core dependencies | `rdflib`, `pyshacl`, `requests` | `pyoxigraph`; rdflib, owlrl, owlready2 are optional extras |
| Used by | the workbench (through the `../starlayer-main` worktree) | nothing yet (workbench integration is handoff Phase E) |
| Since 2026-11-02 | 6 commits (SHACL features #201 to #204) | 464 commits, including this month's hunt |

The merge base is 2026-11-02. `git diff main shacl-engine` touches 1983 files (+84,903 / −83,620). A conventional merge is not an
option, and not a realistic goal: the two branches are different implementations that share a name and a vocabulary.

## What "two places" costs

- **Features and fixes on `main` cannot be cherry-picked.** The six commits since the merge base change
  `constraint_annotations.py`, `native_components.py`, `component_cache.py` and two test files that do not exist on
  `shacl-engine`. Each one has to be re-implemented against `shacl_engine/`. (`shacl_engine/builder.py` already reads per-triple
  `sh:deactivated` and `sh:severity` from reifiers, so #201 may be partly there under another shape; that is to be checked, not assumed.)
- **The hunt does not carry over.** About 200 fixes and the regression tests landed on `shacl-engine` only. `main` has none of
  them, and several concern code `main` does not have (the engine, the Oxigraph wrapper), so `main` has its own undiscovered
  bugs, found by a different method or not at all.
- **Most of the spec-drift plan lands in code that differs between the branches.** Roughly:
  - Done once, because it is data or scripts shared in spirit: the W3C SHACL test-suite sync script and its manifest
    loader, the SPARQL test-suite pin, the spec snapshots and their README, the vocabulary and UI terms in the `.ttl` sources
    (`sh:dataGraph`, `sh:ShapeAssignment`, `shui:suggestedValues`). Even these regenerate `starontology.trig`, which differs.
  - Done twice, because the code differs: the validator changes (the new `sh:` terms, the removed reifier-message rule), and
    SRL `GROUP` aggregation (parser, shapes, evaluator). The test-suite re-sync also yields different failing sets on each.
- **Two dependency stories, two release lines, two sets of docs.** The guides now describe the Oxigraph classes; `main` still
  needs the older text.

## What converging costs

1. **Port the `main`-only features** (#201 to #204: per-constraint annotations on any parameter triple, node-expression
   `sh:deactivated`, `extract_subgraph` using `validate()`'s evaluation, the `sh:values` / `sh:defaultValue` meta-shapes rule). First
   task: find out which of them `shacl-engine` already covers.
2. **Move the workbench** to `shacl-engine` (Phase E of `handoff-next-steps.md`). This is the real blocker. The workbench uses the
   StarLayer API through `main`, and about ten names it imports no longer exist on `shacl-engine` (the hunt rejected that as a
   bug because the workbench is documented as not yet supporting the branch; it is the migration list).
3. **Decide what happens to rdflib users.** `shacl-engine` keeps rdflib as an optional bridge (`from_rdflib` / `to_rdflib`).
   Code that expects `StarLayerGraph` to be an `rdflib.Graph` breaks; that was a deliberate choice in the migration.
4. **Name the sunset.** For example: `main` takes only fixes for a stated period after the workbench moves, then is archived
   with a tag and a note in the README.

## If you keep both anyway

Then say so explicitly and bound it: freeze `main` to fixes and the `#201`-style SHACL features already in flight, do **all** spec-drift
work on `shacl-engine` only, and list what `main` will not get (the new SHACL 1.2 terms, SRL `GROUP`, the hunt fixes). Without
that boundary the spec-drift plan runs twice and `main` drifts from the spec snapshots it is tested against.

## Open questions

- Which of #201 to #204 does `shacl-engine` already implement, and which need porting? (A day of comparison, not a guess.)
- How long can the workbench stay on `main`? That sets the sunset date.
- Are there users of `main` other than the workbench (the `starlayer-apps` repo, the older demos)? I found stale imports in
  `starlayer-apps` during the hunt, which suggests it is already behind.
- Version numbering and the package name if `shacl-engine` becomes the line: a major version bump is the honest signal, since the
  graph classes changed.

## Suggested order

1. Compare #201 to #204 against `shacl-engine` and list the gaps.
2. Run the spec-drift plan on `shacl-engine` only (the shared pieces first, so they are in either way).
3. Port the gaps from step 1.
4. Workbench Phase E.
5. Sunset `main`.
