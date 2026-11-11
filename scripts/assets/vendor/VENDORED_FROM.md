# Vendored snapshot: the W3C Data Shapes WG's SHACL-for-SHACL

`w3c-shacl-shacl.ttl` is a verbatim copy of the Working Group's meta-shapes for SHACL 1.2. It is the **base** of the
`shacl_shacl` graph (see `scripts/build_meta_shapes.py`). Never edit it: `build_meta_shapes.py` only *adds* to it, and a
test fails if the file changes without this record changing too.

- Source: https://github.com/w3c/data-shapes/blob/gh-pages/shacl12-vocabularies/shacl-shacl.ttl
- Upstream commit this copy matches: `a6ed26f` (2026-10-26, "Adding text for sh:dataGraph (#1366)", the latest commit that touches the file)
- Fetched: 2026-11-11
- SHA-256 of the file: `914051f59cec3d989fcd3f1f3f656357980f23b38dfb5c45df043d78877b2220`
- The file is headed "THIS VERSION IS UNDER DEVELOPMENT" and says it checks "a subset of the syntax rules". It is moving: from the
  2026-08-01 snapshot to the 2026-10-12 one it fixed `sh:closed sh:ByTypes` and gained `shsh:ValidationReportShape`; to this one it gained
  `shsh:DataGraphShape` (the object of `sh:dataGraph` is an IRI).

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
- Upstream commit this copy matches: `9d7caf1` (2026-11-11, "Role class defs (#1414)", the latest commit that touches the file)
- Fetched: 2026-11-11
- SHA-256 of the file: `63e0f9d813350bd9a15c1d153984fe34dfdbc657adceba3a49e56790f43978ce`
- Since the 2026-10-14 copy: `sh:dataGraph` (domain `sh:ShapesGraph`, range `sh:DataGraph`) and the role-class wording ("graphs acting in the role of").
- Headed "THIS VERSION IS UNDER DEVELOPMENT"; it is moving.


# Vendored snapshot: the W3C Data Shapes WG's SHACL UI vocabulary

`w3c-shacl-ui.ttl` is a verbatim copy of the Working Group's SHACL UI vocabulary (the `shui:` classes and properties: widgets, widget
matchers and scores, property roles, `shui:suggestedValues`). It is a base of the `shacl_vocabulary` graph (`scripts/build_starontology.py`),
next to `w3c-shacl.ttl`. Never edit it. The namespace is `http://www.w3.org/ns/shacl-ui/` (slash), as in the published SHACL UI draft.

- Source: https://github.com/w3c/data-shapes/blob/gh-pages/shacl12-vocabularies/shacl-ui.ttl
- Upstream commit this copy matches: `40231df` (2026-11-06, "[UI] initial text for shui:suggestedValues (#1338)", the latest commit that touches the file)
- Fetched: 2026-11-11
- SHA-256 of the file: `986903f9332547569cc1ebb09fbefef55e92c7f89909f46faf31e8649517fa29`
