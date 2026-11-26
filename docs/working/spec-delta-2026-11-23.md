# Spec delta, 2026-11-23

What moved upstream between the last review (2026-11-09 to 2026-11-11) and 2026-11-23, and what StarLayer did about it. The test-suite pin
for `w3c/data-shapes` is now `1ca8692` (was `47c6e078b`); `rdf-tests` is unchanged (`4158bca19`, 9 commits ahead, all editorial or
metadata: `dawgt:Proposed` markers, GSP base URI, a Service Description model, a federated-service feature marker).

## SPARQL-RL (SRL)

| Date | Change | Done |
|---|---|---|
| 2026-11-19 | `WHERE DATA` is `WHERE GROUND` and `NOT DATA` is `NOT GROUND`; a `DATA { }` block is unchanged. The spec's flag is `evalground` (was `evaldata`). | `parse_srl.py` reads `GROUND` only; `DATA` after `WHERE` or `NOT` is an error that names `GROUND`. The renderer writes `GROUND`. The Python field and the RDF properties were renamed on 2026-11-25 to `evalground`, `srl:ruleEvalground` and `srl:negationEvalground`, with no alias (a tree stored with `srl:ruleEvaldata` no longer decodes). |
| 2026-11-10 | New well-formedness condition: variable names are not reused in a rule (`inScope`, `inUse`; GH-690). Tests added 2026-11-18 (GH-1444). | `srl_semantic_checks._check_sequence` / `_check_group` follow the spec's definitions; new issue kind `variable_in_use`. |
| 2026-10-20 | `GROUP` and aggregation (`COUNT`, `MIN`, `MAX`, `SUM`); empty-group results (GH-1377), `COUNT(*)` is 0 for a bound key with no match, tests `eval-group-25` to `30` (2026-11-12). | Already supported; the new tests pass. |
| 2026-11-23 | BNF markup fix for `UCHAR`; eight-digit escape summary. | Vendored production table updated by hand (productions 11, 18, 127). |

Effects on StarLayer's own material: five rules in guide 04c and the corpus case `body-group-count` reused a variable and were refused by the new
condition; they now use their own names. The opt-in conformance test for non-stratifiable rule sets expected `parse_ruleset()` to succeed
(it has stratified since ec3612e8); it now expects the error from the parse.

## SHACL 1.2

- Node expressions (2026-11-16): `sparql:encode` is now `sparql:encode-for-uri`, with one argument (the vocabulary `shnex-sparql.ttl` and its test).
  `expressions.py` and `component_table.py` follow; `sparql:encode` is no longer recognised.
- `w3c-shacl.ttl` and `w3c-shacl-ui.ttl` still differ from upstream (core: `shacl.ttl` +28 lines; UI: `shui:parentGroup` for groups inside groups,
  `shui:defaultOrder`). Not yet reviewed or re-vendored.
- UI and Profiling specs changed (editorial plus the two UI terms); Core got a privacy warning (#685).

## RDF and SPARQL texts

Snapshots refreshed (`tests/graph/vendor/spec_snapshots/`). Substantive points: N-Triples and N-Quads accept lower-case hex in `\u` / `\U` escapes and say
"Unicode scalar values" (no surrogates); SPARQL Query and Update describe a `version` media-type parameter; RDF Schema no longer registers the
`rdfs:` vocabulary (a reference table instead). The rest is wording and link fixes. Not checked against StarLayer's parsers: lower-case hex
and surrogate escapes in N-Triples and N-Quads (Oxigraph parses these).
