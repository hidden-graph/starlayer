# Vendored snapshot: the W3C Data Shapes WG's SHACL-for-SHACL

`w3c-shacl-shacl.ttl` is a verbatim copy of the Working Group's meta-shapes for SHACL 1.2. It is the **base** of the
`shacl_shacl` graph (see `scripts/build_meta_shapes.py`). Never edit it: `build_meta_shapes.py` only *adds* to it, and a
test fails if the file changes without this record changing too.

- Source: https://github.com/w3c/data-shapes/blob/gh-pages/shacl12-vocabularies/shacl-shacl.ttl
- Upstream commit this copy matches: `8c9d0f6a2` (2026-10-12, "#1298: Used Claude to apply Claude's suggestions (#1305)")
- Fetched: 2026-10-21
- SHA-256 of the file: `05a35fff992003bb92c8940540b2cc2e52a372158857fbb4080c8867b69906fa`
- The file is headed "THIS VERSION IS UNDER DEVELOPMENT" and says it checks "a subset of the syntax rules". It is moving: from the
  2026-08-01 snapshot to this one it fixed `sh:closed sh:ByTypes` and gained `shsh:ValidationReportShape`.

## Keeping it current

1. `python scripts/check_wg_shacl_shacl.py` fetches the upstream file and reports whether this copy is still the latest.
2. To update: replace the file, set the commit, date and SHA-256 above, run `python scripts/build.py --only starontology`, then run the
   tests. `test_wg_overrides.py` tells you which of our additions upstream has made unnecessary.


# Vendored snapshot: the W3C Data Shapes WG's SHACL 1.2 vocabulary

`w3c-shacl.ttl` is a verbatim copy of the Working Group's SHACL vocabulary (the `sh:` classes and properties, with their
`rdfs:domain`, `rdfs:range` and `rdfs:subClassOf`). It is the base of the `shacl_vocabulary` graph (`scripts/build_starontology.py`),
which anything that reasons about the types of SHACL terms reads (the graph workbench infers the type of each entity of a shapes file
from it). Never edit it; additions go in their own file. It replaces the SHACL 1.0 copy that ships with pySHACL, which lacks
`sh:ShapesGraph`, `sh:RulesGraph`, the node-expression classes and others.

- Source: https://github.com/w3c/data-shapes/blob/gh-pages/shacl12-vocabularies/shacl.ttl
- Upstream commit this copy matches: `e77709e45` (2026-10-14, the latest commit that touches the file)
- Fetched: 2026-10-23
- SHA-256 of the file: `9fee4fcd40d7f39d878cfcd244e2a428e9231821755504543fc52ac3f58fdeaf`
- Headed "THIS VERSION IS UNDER DEVELOPMENT"; it is moving.
