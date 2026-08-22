# Contributing to StarLayer

Thanks for contributing to StarLayer.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/graph -e packages/sparql -e packages/shacl
pip install pytest hypothesis ruff
```

## Testing

Run the package-specific suites from the repo root or from each package directory:

```bash
cd packages/graph && pytest tests/ -m "not integration" -v
cd packages/sparql && pytest tests/ -q
cd packages/shacl && pytest tests/ -q
```

For the full repository validation flow, see [.github/workflows/test.yml](.github/workflows/test.yml).

## Linting

```bash
ruff check packages/
```

## Pull requests

- keep scope narrow and well described
- add or update tests for behavior changes
- note any compatibility caveats or upstream dependencies
- prefer small, reviewable changes

## Coding expectations

- follow the existing style of the package you are editing
- avoid committing generated build artifacts or editor metadata
- do not add secrets, credentials, or local environment files to the repo

## Project structure

The repository is a monorepo with three Python packages:

- [packages/graph](packages/graph)
- [packages/sparql](packages/sparql)
- [packages/shacl](packages/shacl)

Each package has its own tests and README. Prefer package-local changes unless the work clearly spans the full stack.
