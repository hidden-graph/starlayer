# Merged

The tree-layer working copy that lived in `wip/` was merged into `starlayer/starontology/` on 2026-10-18
(`manchester.py`, `manchester-ast-ontology.ttl`, `manchester_shapes.ttl`), `wip/` was deleted, and these
tests now exercise `starlayer.starontology.manchester` directly. `starontology.trig` was regenerated with
`python scripts/build_starontology.py`.

Lessons kept from the exercise:

- The parser (`starlayer/graph/parsers/manchester_parser.py`) drives the tree layer through recording hooks
  (`record_ontology_header`, `record_misc`, ...). Changing a hook's signature in the parser breaks the tree
  module until both change together; keep them in one commit.
- The top-level loop lives only in the parser (`_run_top_level`); the tree module delegates to it.
