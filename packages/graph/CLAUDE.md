# CLAUDE.md

Project-specific instructions for Claude Code sessions working in this repo. See `docs/README.md` for the docs index (start with `docs/starlayergraph.md`).

## Gotcha: don't let a lazy grammar import corrupt the SPARQL 1.2 grammar mid-run

SPARQL 1.2 query/update parsing goes through the sibling `starsparql` package's real grammar/algebra pipeline, installed editable (see `pyproject.toml`), not vendored code. Importing and installing that grammar lazily - i.e. letting the first test module that happens to touch it trigger the import - during pytest's assertion-rewrite-hook-active collection phase corrupts the grammar installation for the rest of the run. `tests/conftest.py` works around this by eagerly importing and installing the grammar at collection time, before any test module can trigger it lazily. If `TRIPLE()`-family syntax ever mysteriously stops parsing partway through a test run, that eager import is the first thing to check - see `docs/testing-strategy.md` tier 1 for the full account.
