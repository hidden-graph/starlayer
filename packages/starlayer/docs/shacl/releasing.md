# Releasing

*Last reviewed: 2026-08-13*

Merges what used to be two overlapping documents (`release-checklist.md` and
`version-bump-workflow.md`) into one sequence.

## 1. Validate

```bash
pytest -q
pytest -q tests/integration
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

Record the benchmark output in `docs/benchmark-baselines.md`.

## 2. Verify the contract

- Confirm the graph contract is enforced: `StarLayerGraph` or plain `rdflib.Graph` accepted (auto-normalized), anything else rejected.
- Confirm diagnostics fields are present in validation/rules results.

## 3. Check docs are current

- `docs/implementation-plan.md`, `docs/compatibility.md`, and the architecture docs match current behavior.
- README examples still execute against the current API.

## 4. Choose the version bump

Per `docs/compatibility.md`'s semantic versioning policy:

- **MAJOR** for breaking contracts or behavior
- **MINOR** for backward-compatible features
- **PATCH** for fixes/docs/tests with no contract changes

Update the version in `pyproject.toml`.

## 5. Write release notes

Copy `docs/release-notes-template.md`, fill in all sections, and move `CHANGELOG.md`'s "Unreleased" section content under a new dated version heading.

## 6. Re-run validation

Re-run the commands from step 1 against the version-bumped tree.

## 7. Tag and publish

1. Commit the release changes.
2. Tag the release commit.
3. Push the branch and tag.
4. Publish release artifacts.
