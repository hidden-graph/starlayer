# Vendored snapshot provenance

Do not hand-edit files in this directory: regenerate with `python ../download_w3c_rdf12_tests.py` after bumping `PINNED_SHA` there.

- Source: https://github.com/w3c/rdf-tests/tree/4158bca195a29fe1fd90f92698170bc7cc385273/rdf/rdf12/
- Pinned commit SHA: `4158bca195a29fe1fd90f92698170bc7cc385273` (the commit `../../w3c_turtle12/data` is pinned to)
- Copied: 2026-11-11, whole directories `rdf-turtle`, `rdf-trig`, `rdf-n-triples`, `rdf-n-quads`, `rdf-xml`, byte for byte, except the `reports` directories (EARL implementation reports, which nothing reads). 539 files.
- Not vendored: `rdf-semantics` (entailment, not syntax) and the RDF 1.1 suites (`rdf/rdf11`, 24 MB, mostly Turtle).

## License

The files are copied from the W3C `rdf-tests` repository, dual-licensed under the W3C 3-Clause BSD License and the W3C Test Suite
License (https://www.w3.org/Consortium/Legal/2008/04-testsuite-copyright.html). They are unaltered, so both licences apply.
No W3C logos or trademarks are used, and no conformance or certification claim is made.
