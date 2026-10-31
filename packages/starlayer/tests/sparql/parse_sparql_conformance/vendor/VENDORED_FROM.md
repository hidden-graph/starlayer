# Vendored: the SPARQL 1.2 Query grammar

- Source: https://www.w3.org/TR/sparql12-query/#sparqlGrammar - W3C Working Draft 25 October 2026
- Retrieved: 2026-10-31 (SHA-256 of the retrieved HTML is recorded in `sparql12-query-productions.json`)
- `sparql12-query-productions.json`: the 194 numbered productions of section 19.7 (the grammar table and the
  "Productions for terminals" table), machine-extracted as `[n] Name ::= body`, tags stripped. The HTML is not vendored.

The table is the spine of the production coverage matrix (`test_coverage_matrix.py`). To refresh: re-download the
draft into a clean directory, re-extract with the same two table scrapes, update the date and review the diff.
