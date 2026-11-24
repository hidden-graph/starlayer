# Vendored: SPARQL 1.2 RL (SRL) grammar and examples

- Source: https://www.w3.org/TR/sparql12-rl/ - W3C Working Draft 09 November 2026; updated 2026-11-23 by hand from the editor's draft at
  w3c/data-shapes `1ca8692` (`sparql12-rl/sparql-rl-grammar.bnf`) for the 2026-11-19 rename of `WHERE DATA` / `NOT DATA` to `GROUND` (productions 11
  and 18, the `UCHAR` markup in 127, and the one example that used it); the JSON has not been re-extracted from a published draft
- Retrieved: 2026-11-11 (SHA-256 of the retrieved HTML is recorded in `sparql12-rl-productions.json`)
- `sparql12-rl-productions.json`: the 161 numbered grammar productions of section 7.6, machine-extracted from
  the grammar table (`[n] Name ::= body`), tags stripped. The HTML itself is not vendored.
- `spec-examples.json`: the 14 SRL code blocks of the draft (the `<pre>` blocks that contain rules or data),
  tags stripped. They use the prefixes `:`, `rdf:` and `xsd:` without declaring them; the tests add a prelude.

The table is the spine of the coverage matrix (`test_sr_coverage_matrix.py`). To refresh: re-download the draft
into a clean directory, re-extract, update the date and review the diff.
