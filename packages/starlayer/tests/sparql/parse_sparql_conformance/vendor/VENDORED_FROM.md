# Vendored: the SPARQL 1.2 Query grammar

- Source: https://www.w3.org/TR/sparql12-query/#sparqlGrammar - W3C Working Draft 01 November 2026
- Retrieved: 2026-11-11 (SHA-256 of the retrieved HTML is recorded in `sparql12-query-productions.json`)
- `sparql12-query-productions.json`: the 194 numbered productions of section 19.7 (the grammar table and the
  "Productions for terminals" table), machine-extracted as `[n] Name ::= body`, tags stripped. The HTML is not vendored.

The table is the spine of the production coverage matrix (`test_coverage_matrix.py`). To refresh: re-download the
draft into a clean directory, re-extract with the same two table scrapes, update the date and review the diff.

Re-extracted 2026-11-11 from the draft of 2026-11-01: the 194 productions are identical to the ones of 2026-10-25 (same text, same numbers); only the document date and the HTML hash changed.
