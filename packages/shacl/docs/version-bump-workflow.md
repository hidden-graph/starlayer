# Version Bump Workflow

*Last reviewed: 2026-07-18*

This workflow standardizes how version updates are prepared and validated.

## 1. Choose Bump Type

Use `docs/compatibility.md` semantic versioning rules.

- MAJOR for breaking contracts or behavior
- MINOR for backward-compatible features
- PATCH for fixes/docs/tests with no contract changes

## 2. Update Version

Edit `pyproject.toml` and change the project version.

## 3. Prepare Release Notes Draft

Copy `docs/release-notes-template.md` and fill all sections. Also move the `CHANGELOG.md` "Unreleased" section's content under a new dated version heading.

## 4. Run Validation Gates

```bash
pytest -q
pytest -q tests/integration
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

Record benchmark output in `docs/benchmark-baselines.md`.

## 5. Final Review

- Verify docs are aligned:
  - `CHANGELOG.md`
  - `docs/implementation-plan.md`
  - `docs/compatibility.md`
- Confirm release checklist items in `docs/release-checklist.md` are complete.

## 6. Tag And Publish

- Commit release changes.
- Create version tag.
- Push branch and tag.
- Publish release artifacts.
