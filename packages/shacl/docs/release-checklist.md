# Release Checklist

*Last reviewed: 2026-07-18*

## Pre-release Validation

1. Run full tests.

```bash
pytest -q
```

2. Run integration-only tests.

```bash
pytest -q tests/integration
```

3. Run benchmark smoke test.

```bash
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

4. Record benchmark baseline in `docs/benchmark-baselines.md`.

## Contract Verification

1. Confirm the graph contract is enforced: `StarLayerGraph` or plain `rdflib.Graph` accepted (auto-normalized), anything else rejected.
2. Confirm diagnostics fields are present in validation/rules results.

## Documentation

1. Ensure architecture, compatibility, and implementation plan docs match current behavior.
2. Ensure README examples still execute with current API.

## Packaging and Versioning

1. Determine version bump type (major/minor/patch) via `docs/compatibility.md` policy.
2. Update `pyproject.toml` version.
3. Create release notes from `docs/release-notes-template.md` summarizing behavior and contract changes.
4. Follow `docs/version-bump-workflow.md` for validation and publish sequencing.

## Final Gate

1. Ensure clean test run after version bump.
2. Tag release commit.
3. Push tag and publish release artifacts.
