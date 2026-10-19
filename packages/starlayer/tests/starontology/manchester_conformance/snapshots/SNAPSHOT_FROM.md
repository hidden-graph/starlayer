# Snapshots of the Manchester tree ontology and shapes

Copies of `starlayer/starontology/manchester-ast-ontology.ttl` and `starlayer/starontology/manchester_shapes.ttl`
as merged from the completeness work (2026-10-18, on top of commit `ef6ef0de314ed97cb51b6501ff1d82a5e30ca051`).

Purpose: `test_snapshot_matches_live_file` compares the *live* files against these, so every later change to
the tree vocabulary (new class, new property, loosened shape) shows up in review as a deliberate snapshot
refresh instead of drifting silently. Refresh a snapshot only after reviewing that diff.

History: the original pre-completeness files (the merge base) are in git at commit
`773d5d0a48e059f94d9fec4698d756dc717d50ff`.

| File | SHA-256 |
|---|---|
| manchester-ast-ontology.ttl | `14cb97672d847db8c4d399c99261432596120d2b725fba51ef018efe09039b45` |
| manchester_shapes.ttl | `ec52506011dde76671d1126e1e25f30860aad0fac35ea3cfcf55bbd4b81823a9` |
