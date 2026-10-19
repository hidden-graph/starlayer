# Snapshots of the Manchester tree ontology and shapes

Frozen copies of `starlayer/starontology/manchester-ast-ontology.ttl` and
`starlayer/starontology/manchester_shapes.ttl`, taken on branch `manchester` at commit
`773d5d0a48e059f94d9fec4698d756dc717d50ff` (2026-10-18).

Purpose: the conformance suite's introspection tests compare the *live* files in `starontology/` against
these baselines, so every change to the tree vocabulary (new class, new property, loosened shape) shows
up in review as a deliberate snapshot refresh instead of drifting silently. Real fixes land in
`starontology/`; refresh a snapshot only after reviewing that diff.

| File | SHA-256 |
|---|---|
| manchester-ast-ontology.ttl | `7fc5ac8d1907a4edc8aa1d0cbcb9fbd570c69aa510421e44a60337fabcc5441a` |
| manchester_shapes.ttl | `ea2ba26938c945aefe5086714f10996bb0f0cf9d02857a84051fbad7eb81f89d` |
