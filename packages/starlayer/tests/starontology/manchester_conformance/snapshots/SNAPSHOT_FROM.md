# Snapshots of the Manchester tree ontology and shapes

Frozen copies of `starlayer/starontology/manchester/manchester-ast-ontology.ttl` and
`starlayer/starontology/manchester/manchester_shapes.ttl`. Refreshed 2026-11-26 (both: the end-state vocabulary, renames only: OntologyDocument, PrefixDeclaration, spelled-out ObjectProperty/DataProperty/AnnotationProperty clause classes, Exactly, Self, Data* and DatatypeRestriction, Fact, Annotation, prefixName, namespace, ontologyIRI, versionIRI, datatype, facet, restrictionValue, annotationTarget); refreshed 2026-11-25 (both: ordered children are tree:ord ordinals, not rdf:List; the 13 list shapes are gone, manch:values added); refreshed 2026-11-09 (manchester_shapes.ttl only: bug-hunt fixes for facet IRIs, property characteristics and list cells); refreshed 2026-10-18 when the tree-layer working copy
(`wip/`, now removed) was folded back into `starontology/`; before that they were the files as of commit
`773d5d0a48e059f94d9fec4698d756dc717d50ff`.

Purpose: the conformance suite's introspection tests compare the *live* files in `starontology/` against
these baselines, so every change to the tree vocabulary (new class, new property, loosened shape) shows
up in review as a deliberate snapshot refresh instead of drifting silently. Real fixes land in
`starontology/`; refresh a snapshot only after reviewing that diff.

| File | SHA-256 |
|---|---|
| manchester-ast-ontology.ttl | `8ad40d51c9aed3153eeffbe3682ce8a365cbf24be132aa214c7f739ff8fcdc77` |
| manchester_shapes.ttl | `897b8ff7b1f246bc1a13030c0f5c7ce74505e3cbc9b2bd99bc2ad53f54c1ae65` |
