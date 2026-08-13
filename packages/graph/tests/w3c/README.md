# Instructions for the W3C Turtle Test Suite Integration

*Last reviewed: 2026-07-17*

This folder contains the local parser test harness (`test_w3c_turtle.py`) plus the full set of W3C RDF 1.2 Turtle conformance tests it runs against (triple terms, reified-triple annotations, `{| |}` annotation syntax), organized as follows. (test data as of 2026-07-17, pulled from both the `eval/` and `syntax/` manifests W3C publishes — see `download_w3c_turtle_tests.py`)

- `data/` — all .ttl and .nt files, direct copies from the official W3C test suite, plus `data/manifest.csv` listing all tests, their types, and expected results.
- `test_w3c_turtle.py` — the pytest harness; run with `pytest tests/w3c/`.
- `download_w3c_turtle_tests.py` — re-fetches `data/` from both live W3C manifests; safe to re-run any time (skips files that already exist).

103 tests across three types, one test function per type in `test_w3c_turtle.py`:
- `rdft:TestTurtleEval` (29) — .ttl input, .nt expected output; parser output must match via graph isomorphism (`test_w3c_turtle_eval`).
- `rdft:TestTurtlePositiveSyntax` (41) — .ttl input must parse without raising; result content not checked (`test_w3c_turtle_positive_syntax`).
- `rdft:TestTurtleNegativeSyntax` (33) — .ttl input must fail to parse (`test_w3c_turtle_negative_syntax`).

(`rdft:TestTurtleNegativeEval` is a fourth type the `rdft:` vocabulary defines generally, but neither W3C manifest for RDF 1.2 Turtle currently has any tests of that type — nothing to pull in.)

For more details, see: https://w3c.github.io/rdf-tests/rdf/rdf12/rdf-turtle/index.html

## License

The files in `data/` are copied and subsetted from the W3C `rdf-tests` repository (https://github.com/w3c/rdf-tests), which is dual-licensed under the W3C 3-Clause BSD License and the W3C Test Suite License (https://www.w3.org/Consortium/Legal/2008/04-testsuite-copyright.html). Because this subset is altered (`manifest.csv` is a reformatted, merged derivative of the original manifest.ttl files from both the `eval/` and `syntax/` manifests), it is used here under the **W3C 3-Clause BSD License** terms specifically — the W3C Test Suite License option prohibits modification. Per W3C's required notice:

> Distributed under both the W3C test suite license and the W3C 3-clause BSD license.

No W3C logos or trademarks are used, and no conformance/certification claims are made against this modified subset — see the note in the top-level `README.md`.
