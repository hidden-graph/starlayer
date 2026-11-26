# Snapshots of the Manchester tree ontology and shapes

Frozen copies of `starlayer/starontology/manchester/manchester-ast-ontology.ttl` and
`starlayer/starontology/manchester/manchester_shapes.ttl`. Refreshed 2026-11-25 (both: ordered children are tree:ord ordinals, not rdf:List; the 13 list shapes are gone, manch:values added); refreshed 2026-11-09 (manchester_shapes.ttl only: bug-hunt fixes for facet IRIs, property characteristics and list cells); refreshed 2026-10-18 when the tree-layer working copy
(`wip/`, now removed) was folded back into `starontology/`; before that they were the files as of commit
`773d5d0a48e059f94d9fec4698d756dc717d50ff`.

Purpose: the conformance suite's introspection tests compare the *live* files in `starontology/` against
these baselines, so every change to the tree vocabulary (new class, new property, loosened shape) shows
up in review as a deliberate snapshot refresh instead of drifting silently. Real fixes land in
`starontology/`; refresh a snapshot only after reviewing that diff.

| File | SHA-256 |
|---|---|
| manchester-ast-ontology.ttl | `22f6bb501f7f01619c182451290778f6c4fc20005a747479210c15f89f30f55e` |
| manchester_shapes.ttl | `20b6cdb0e28cf5c3fab3d9869c9f8772a59411da078f031d7ab27f1c40f95099` |
