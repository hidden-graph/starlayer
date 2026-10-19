# Snapshots of the Manchester tree ontology and shapes

Frozen copies of `starlayer/starontology/manchester-ast-ontology.ttl` and
`starlayer/starontology/manchester_shapes.ttl`. Refreshed 2026-10-18 when the tree-layer working copy
(`wip/`, now removed) was folded back into `starontology/`; before that they were the files as of commit
`773d5d0a48e059f94d9fec4698d756dc717d50ff`.

Purpose: the conformance suite's introspection tests compare the *live* files in `starontology/` against
these baselines, so every change to the tree vocabulary (new class, new property, loosened shape) shows
up in review as a deliberate snapshot refresh instead of drifting silently. Real fixes land in
`starontology/`; refresh a snapshot only after reviewing that diff.

| File | SHA-256 |
|---|---|
| manchester-ast-ontology.ttl | `14cb97672d847db8c4d399c99261432596120d2b725fba51ef018efe09039b45` |
| manchester_shapes.ttl | `cc8caeb2d3fc7c51d91f5748b677bf80b5516f0712556582b02c55c0b4717607` |
