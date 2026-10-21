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
