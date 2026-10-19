# Vendored: OWL 2 Manchester Syntax grammar productions

`owl2-manchester-productions.json` is a machine-extracted table of the BNF productions in
the W3C Working Group Note *OWL 2 Web Ontology Language Manchester Syntax (Second Edition)*:

- Source: https://www.w3.org/TR/owl2-manchester-syntax/
- Retrieved: 2026-10-18
- SHA-256 of the retrieved HTML: `887309c393772c4bea40711154a158794d946c6071b66192494e1174e0249f22`
- Extraction: every `<p class="grammar">` block, tags stripped, split into `name ::= right-hand side`
  (71 productions). The HTML itself is not vendored, only this derived table.

The table is the spine of the coverage matrix (`test_mc_coverage_matrix.py`): every production must be
exercised by at least one corpus case. It is also the source the grammar-driven generators are written
from. The note's 13 *labelled alternatives* inside `description` and `restriction`
(`objectsome`, `objectonly`, `objectvalue`, `objectSelf`, `objectmin`, `objectmax`, `objectexactly` and the
`data*` counterparts) are not productions of their own in the note's markup, so `grammar.py` lists them
separately.

To refresh: re-download the note into a clean directory, re-run the extraction, update the retrieval
date and hash above, and review the diff of the table.
