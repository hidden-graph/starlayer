# Spec drift review, 2026-11-09

What changed in the RDF 1.2, SPARQL 1.2 and SHACL 1.2 drafts since the versions StarLayer was built to, and a plan. Baselines come from `tests/graph/vendor/spec_snapshots/`, `docs/shacl/shacl12-gap-matrix.md` and the vendored test suites. Findings come from fetching the live drafts and reading the specification repositories' commit logs; a few items are unverified and marked so.

## Summary

| Area | Baseline | Current | Substantive change |
|---|---|---|---|
| RDF Concepts | CR 2026-04-07 | same | none |
| RDF Schema | WD 2026-03-28 | WD 2026-10-23 | datatype sections normative; no code impact |
| Turtle, N-Triples, RDF/XML | WD 2026-07-23 to 09-14 | WD 2026-11-05 | non-conformant input is now "undefined"; future-proofing rule for `VERSION`; no grammar change |
| N-Quads, TriG | none recorded | WD 2026-11-05 | the snapshot README says they have no documents; they do |
| RDF Semantics | CR 2026-04-07 | CR Draft 2026-09-24 | new RDFS rule rdfs14a (a blank node typed `rdfs:Proposition`) |
| RDF Interoperability | editor's draft read 2026-10-31 | same as 2026-07-23 Note | none |
| RDFC-1.0 | Rec 2024 | same | none |
| SPARQL Query | WD 2026-09-13 | WD 2026-11-01 | editorial only |
| SPARQL Update | WD 2026-06-12 | WD 2026-10-25 | examples only |
| SPARQL Rules (SRL) | WD 2026-10-14 (grammar); docstring says 2026-09-19 | WD 2026-11-09 | `GROUP [BY] { } [ ?n := COUNT(*) ... ]` aggregation in rule bodies; two productions renamed |
| SPARQL Entailment Regimes | no date recorded | WD 2026-04-09 | unknown; RDF 1.2 inconsistency handling and scoping graph |
| SPARQL test suite | rdf-tests d5d930b, 2026-10-12 | 13 commits ahead | manifest formatting only |
| SHACL Core | WD 2026-08-03 (docs) | WD 2026-11-02 | optional `sh:ShapeAssignment` report extension; `sh:dataGraph`; reifier-message maxCount rule removed |
| SHACL SPARQL, Node Expressions | 2026-08-28, 2026-07-21 | 2026-10-22, 2026-10-28 | function-argument evaluation reworded (unverified) |
| SHACL Inference Rules | WD 2026-10-28 | same | none |
| SHACL UI | WD 2026-05-26 | WD 2026-11-06 | `shui:suggestedValues`; `shui:searchQuery` substitution rules; new property roles |
| SHACL Profiling | WD 2026-07-02 | same TR; editor's draft changed | none for validators |
| SHACL test suite | data-shapes 59b38cd, 2026-08-15 | reorganised upstream | about 263 tests added, directories renamed, about 285 manifests gained `mf:requires sht:Core` |

## Plan, in order

1. **Re-sync the SHACL test suite** (medium). Set a new pinned commit in `scripts/sync_w3c_shacl12_suite.py`; teach `tests/shacl/w3c_shacl12/manifest.py` the new directory names (`sparql/rules` to `inference-rules`, `rules` to `sparql-rl`) and `mf:requires`; triage `known_failures.py`. This is the cheapest way to find real gaps.
2. **SHACL vocabulary** (small to medium). Add `sh:dataGraph` with `shsh:DataGraphShape`, and the optional `sh:ShapeAssignment`, `sh:assignment`, `sh:nodeAssignmentCount` with their shape, to `starontology/shacl12-shacl.ttl`; regenerate with `scripts/build.py`. Check that nothing enforces the removed one-`sh:message`-per-reifier rule. Decide separately whether to emit assignments in reports (optional in the spec).
3. **SHACL UI** (small to medium). Add `shui:suggestedValues`, check the property-role definitions against the 2026-10-27 vocabulary, and review `shui:searchQuery` substitution.
4. **SRL aggregation** (medium to large). Parse `GROUP`, evaluate it, stratify it, add well-formedness rules for group variables, refresh the vendored productions and examples, rename the matrix entries, and fix the baseline date mismatch. Read the semantics text first, since the agent compared only the grammar.
5. **Small items.** Re-sync the SPARQL test suite pin (small); decide on rdfs14a (optional, one entailment); update the spec snapshots and fix the README claim about N-Quads and TriG; check list-parameter function-argument semantics in `shacl_engine/expressions.py`.
6. **Unverified, to check:** Entailment Regimes changes (no baseline date); N-Quads and TriG text; Semantics text beyond the commit log; whether any SHACL-JS or compact-syntax document exists; the full SPARQL Query prose diff.
