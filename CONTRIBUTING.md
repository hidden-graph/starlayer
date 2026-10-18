# Contributing to StarLayer

Thanks for contributing. Working with an AI agent? [AGENTS.md](AGENTS.md) is its entry point.

## Layout

One Python package, `starlayer`, with its `pyproject.toml` at the repository root and its source in `packages/starlayer/starlayer/` (`graph/`, `sparql/`, `shacl/`, `starontology/`). Tests are in `packages/starlayer/tests/`, guides in `docs/guides/`, build scripts in `scripts/`. The [docs map](docs/README.md) lists everything else.

## Set up

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pip install ruff
```

## Tests

From `packages/starlayer`:

```bash
pytest tests -m "not integration"        # the fast tier
pytest tests -m integration              # needs local Oxigraph and Fuseki servers; skips without them
pytest tests --store-matrix              # W3C suites through every store (slow, opt-in)
pytest tests --srl-stratification        # extended SRL stratification checks (opt-in)
```

`STARLAYER_RUN_ENGINE_ABORT_TESTS=1` also runs the tests that really crash Oxigraph's engine (opt-in, because they file a crash report). CI runs the fast and integration tiers on Python 3.10 to 3.13; see [.github/workflows/test.yml](.github/workflows/test.yml).

## Lint

```bash
ruff check packages/
```

CI runs the same command and it must pass. Formatting is not enforced, so do not reformat files you are not changing.

## Generated files

Some files are built, not written: `docs/generated/*.generated.md`, the code knowledge graph (`codekg.trig`), and in `starontology/` the `.trig`, `shacl12-shacl.ttl` and `skos-ontology.ttl`. Edit the source and run:

```bash
python scripts/build.py          # rebuild everything
python scripts/build.py --check --skip codekg   # what CI runs
```

CI fails when a committed generated file is out of date. The same command runs `scripts/check_docs.py`, which fails on a broken relative link or anchor in any Markdown file or guide, and on a guide missing from `docs/guides/README.md` or `docs/user-guide-version.json`. The code knowledge graph is not checked in CI; rebuild it with `python scripts/build.py --only codekg apidocs` after larger code changes.

## Pull requests

- Keep the change focused and describe what it does and why.
- Add or update tests. For a fix, check that the new test fails without it. For SHACL and SPARQL behaviour, compare against plain pySHACL or rdflib.
- Note compatibility effects and upstream dependencies.
- Do not commit build output, editor files, secrets or local environment files.
- Follow the style of the code around you. Docstrings give the reason, not what the signature already shows.

## Reporting a bug

Open a GitHub issue with a minimal example, the commit or version, and the backend (in-memory, Oxigraph, Fuseki). Bugs in rdflib, pySHACL and Oxigraph that we work around are written up, with repros, in [docs/upstream-issues/](docs/upstream-issues/).
