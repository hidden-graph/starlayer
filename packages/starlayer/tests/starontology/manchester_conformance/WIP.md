# Working copy of the Manchester tree layer (NOT merged into starontology)

Another agent is changing `starlayer/starontology/` on a different branch. To keep the two independent,
**nothing under `starlayer/starontology/` is changed by this work** - those files are byte-identical to the
base commit `773d5d0` - and the tree-layer changes live in `wip/` as copies, to be compared and merged
once the other agent has finished.

| Piece | Live (untouched) | Working copy (edited) | Merge base |
|---|---|---|---|
| tree module | `starlayer/starontology/manchester.py` | `wip/manchester.py` | git: `773d5d0` |
| vocabulary | `starlayer/starontology/manchester-ast-ontology.ttl` | `wip/manchester-ast-ontology.ttl` | `snapshots/` |
| shapes | `starlayer/starontology/manchester_shapes.ttl` | `wip/manchester_shapes.ttl` | `snapshots/` |
| bundle | `starlayer/starontology/starontology.trig` | not regenerated | git: `773d5d0` |

`manchester_shapes.ttl` is hand-edited (confirmed), so it merges like any source file. `starontology.trig`
is generated: after merging, do not merge its bytes, run `python scripts/build_starontology.py`.

The parser (`starlayer/graph/parsers/manchester_parser.py`) and serializer are not in `starontology/` and
are edited in place on this branch.

## How the live module keeps working with the changed parser

The parser drives the tree layer through recording hooks. Changing an existing hook's signature would break
the live tree module until both change together, so hook changes here are **additive only**: existing
signatures are unchanged and new information arrives through new no-op hooks
(`record_ontology_extras`, `record_misc_annotations`) that the live module does not override. The live
module's own tests (`tests/graph/unit/test_manchester_ast*.py`) pass against the changed parser.

Consequence, to know before relying on the live tree layer: it ignores what only the new hooks carry (an
ontology version IRI, header `Annotations:`, `Annotations:` on top-level axioms), and raises on constructs
it has no class for (data-property restrictions, nodeIDs). Both are the live module's pre-existing limits,
fixed in `wip/`. The duplicated top-level loop in the live module is also still its own copy; in `wip/` it
delegates to the parser's `_run_top_level`.

## Merge procedure (when the other agent is done)
1. Fetch the other agent's branch. `diff snapshots/<f> starlayer/starontology/<f>` for the three files above:
   what changed live meanwhile.
2. `diff snapshots/<f> wip/<f>`: what this work changed.
3. Three-way merge each file (`git merge-file <live-copy> snapshots/<f> wip/<f>`), review the result.
4. In `wip/manchester.py` the line `from . import get_ontology_graph` already matches the real loader.
5. Regenerate the bundle: `python scripts/build_starontology.py`; then `python scripts/build.py --check --skip codekg`.
6. Point the suite back at `starlayer.starontology.manchester` (`wip/` imports in `test_mc_tree.py`,
   `test_mc_generated.py`, `test_mc_shapes_mutation.py`, `tools/mutation_scan.py`; `WIP` paths in
   `test_mc_introspection.py`), delete `wip/`, refresh `snapshots/`.
