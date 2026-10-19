# Working copy of the Manchester tree layer

Why: another agent is changing `starlayer/starontology/` (and regenerating `starontology.trig`) on a
different branch. To avoid conflicts, fixes to the tree layer are made in `wip/`, not in the live files.

| Piece | Live (untouched) | Working copy (edited) | Merge base |
|---|---|---|---|
| tree module | `starlayer/starontology/manchester.py` | `wip/manchester.py` | git: commit `0ad1f74` |
| vocabulary | `starlayer/starontology/manchester-ast-ontology.ttl` | `wip/manchester-ast-ontology.ttl` | `snapshots/` |
| shapes | `starlayer/starontology/manchester_shapes.ttl` | `wip/manchester_shapes.ttl` | `snapshots/` |

The parser (`starlayer/graph/parsers/manchester_parser.py`) and serializer are not in `starontology/`
and are edited in place.

**Coupling hazard, and the one live edit.** The parser drives the tree layer through recording hooks
(`record_ontology_header`, `record_misc`, ...). Changing a hook's signature in the parser breaks the *live*
tree module until the merge. So `starlayer/starontology/manchester.py` carries a small compatibility shim:
those two hooks accept the new arguments and **refuse them with a clear error** (never silently drop
them). The merge replaces the whole file with `wip/manchester.py`, so the shim disappears. The same
reasoning is why the tree module's duplicated top-level loop was removed: `_run_top_level` now lives only
in the parser.

`test_snapshot_matches_live_file` fails if the live files change under us: that is the signal to rebase
the working copy on the new live version before merging.

## Merge procedure (when the work is done)
1. `diff snapshots/<f> starlayer/starontology/<f>` - what changed live meanwhile (expect nothing).
2. `diff snapshots/<f> wip/<f>` - what this work changed.
3. Three-way merge (`git merge-file live-copy snapshots/<f> wip/<f>`), review, copy into `starontology/`.
4. Change `wip/manchester.py`'s `from . import get_ontology_graph` back to the real loader, copy over
   `starontology/manchester.py`, regenerate `starontology.trig` with `python scripts/build.py`.
5. Point the tests back at `starlayer.starontology.manchester`, delete `wip/`, refresh the snapshots.
