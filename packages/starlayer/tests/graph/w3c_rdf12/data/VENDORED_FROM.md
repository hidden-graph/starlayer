# Vendored snapshot provenance

Do not hand-edit files in this directory.

- Source: https://github.com/w3c/rdf-tests/tree/d5d930b03ee6b63b388d0bb28fdb29ee78a59ec0/rdf/rdf12/
- Pinned commit SHA: `d5d930b03ee6b63b388d0bb28fdb29ee78a59ec0` (the commit `../../w3c_turtle12/data` is pinned to)
- Copied: 2026-11-04, whole directories `rdf-turtle`, `rdf-trig`, `rdf-n-triples`, `rdf-n-quads` and `rdf-xml`, byte for byte. To
  refresh, bump the SHA, replace these five directories from a tarball of that commit (`codeload.github.com/w3c/rdf-tests/tar.gz/<sha>`,
  subtree `rdf/rdf12/`) and update the expected count and `KNOWN_GAPS` in `../test_w3c_rdf12_oxigraph.py`.
- Not vendored: `rdf-semantics` (entailment, not syntax) and the RDF 1.1 suites (`rdf/rdf11`, 24 MB, mostly Turtle).

## License

The files are copied from the W3C `rdf-tests` repository, dual-licensed under the W3C 3-Clause BSD License and the W3C Test Suite
License (https://www.w3.org/Consortium/Legal/2008/04-testsuite-copyright.html). They are unaltered, so both licences apply.
No W3C logos or trademarks are used, and no conformance or certification claim is made.
