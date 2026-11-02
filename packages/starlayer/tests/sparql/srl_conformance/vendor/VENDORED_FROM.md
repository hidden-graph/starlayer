# Vendored: SPARQL 1.2 RL (SRL) grammar and examples

- Source: https://www.w3.org/TR/sparql12-rl/ - W3C Working Draft 14 October 2026
- Retrieved: 2026-10-18 (SHA-256 of the retrieved HTML is recorded in `sparql12-rl-productions.json`)
- `sparql12-rl-productions.json`: the 153 numbered grammar productions of section 7.6, machine-extracted from
  the grammar table (`[n] Name ::= body`), tags stripped. The HTML itself is not vendored.
- `spec-examples.json`: the 13 SRL code blocks of the draft (the `<pre>` blocks that contain rules or data),
  tags stripped. They use the prefixes `:`, `rdf:` and `xsd:` without declaring them; the tests add a prelude.

The table is the spine of the coverage matrix (`test_sr_coverage_matrix.py`). To refresh: re-download the draft
into a clean directory, re-extract, update the date and review the diff.
