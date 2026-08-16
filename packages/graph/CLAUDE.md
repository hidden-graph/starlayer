# CLAUDE.md

Project-specific instructions for Claude Code sessions working in this repo. See `docs/README.md` for the docs index (start with `docs/starlayergraph.md`).

## Gotcha: don't let a lazy grammar import corrupt the SPARQL 1.2 grammar mid-run

SPARQL 1.2 query/update parsing goes through the sibling `starsparql` package's real grammar/algebra pipeline, installed editable (see `pyproject.toml`), not vendored code. Importing and installing that grammar lazily - i.e. letting the first test module that happens to touch it trigger the import - during pytest's assertion-rewrite-hook-active collection phase corrupts the grammar installation for the rest of the run. `tests/conftest.py` works around this by eagerly importing and installing the grammar at collection time, before any test module can trigger it lazily. If `TRIPLE()`-family syntax ever mysteriously stops parsing partway through a test run, that eager import is the first thing to check - see `docs/testing-strategy.md` tier 1 for the full account.

## Tracking upstream spec changes (RDF 1.2 / SPARQL 1.2 are still pre-Recommendation)

Before starting any work that touches RDF 1.2/SPARQL 1.2 behavior specifically (not every routine change), check whether the upstream spec text has moved since this project last verified against it: run `python3 tests/vendor/spec_snapshots/refresh_snapshots.py` and `git diff tests/vendor/spec_snapshots/*.txt` - a non-empty diff is the trigger to re-run the relevant section of `docs/rdf12_sparql12_gap_analysis.md` against the new text. Full procedure and the 4-step "what to do as the spec progresses toward Recommendation" plan: `docs/future_enhancements.md`'s "Keeping in step with RDF 1.2/SPARQL 1.2 as the spec finalizes" section. No CI job watches the W3C TR-track automatically - this is a manual check, not something that happens on its own.
