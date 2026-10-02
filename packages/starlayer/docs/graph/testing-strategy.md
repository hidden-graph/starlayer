# Testing Strategy

*Last reviewed: 2026-08-11*

Four tiers, each answering a different question. Run the first two on every
change; the rest when you're touching something they specifically cover.

## 1. Unit + W3C conformance — correctness, in-memory

**Question:** does the code do what it's supposed to?

```bash
pytest tests/ -m "not integration" -v
```

Runs on every push/PR (`.github/workflows/test.yml`, Python 3.10–3.13). Covers:

- `tests/unit/` — component-level tests against the default in-memory backend.
- `tests/w3c_sparql12/` — the W3C SPARQL 1.2 conformance suite, evaluated against the in-memory backend and (parametrized, self-skipping) live Oxigraph/Fuseki when reachable.

No server required; this is the tier every contribution must pass.

SPARQL 1.2 query/update parsing goes through the sibling `starsparql`
package's real grammar/algebra pipeline (`starlayergraph/query/query_cache.py`,
`starlayergraph/query/sparql_api.py`) — a real, editable-installed dependency
(see `pyproject.toml`), not vendored code. A pytest/pyparsing interaction
that could corrupt that package's grammar installation when run alongside
other test modules was found and fixed during the migration off starlayergraph's
old text-based rewriter: `tests/conftest.py` eagerly imports and installs
the grammar at collection time, before any test module can trigger the
import lazily (the actual trigger — confirmed by direct A/B testing — since
lazy first-import during pytest's assertion-rewrite-hook-active collection
phase is what caused the corruption, regardless of which test exercised
the grammar). If `TRIPLE()`-family syntax ever mysteriously stops parsing
partway through a run again, that's the first thing to check.

## 2. Integration — real backends, real stores

**Question:** does behavior actually hold once a real store is in the loop, not just rdflib's own in-memory graph?

```bash
pytest tests/ -m "integration" -v
```

Covers three backend families, each in its own file under `tests/integration/`:

| File | Backend | Needs |
|---|---|---|
| `test_fuseki_backend.py` | Apache Jena Fuseki, `rdf-1.1` and `rdf-1.2` modes | `docker run ... atomgraph/fuseki` — see the file's own docstring |
| `test_oxigraph_backend.py` | Oxigraph, native `rdf-1.2` | `docker run ... ghcr.io/oxigraph/oxigraph` — see the file's own docstring |
| `test_sqlalchemy_backend.py` | SQLite via `rdflib-sqlalchemy`, `rdf-1.1` | the `sqlalchemy` extra (`pip install -e ".[sqlalchemy]"`) — no server |

Every test class self-skips (`skipif`) when its backend isn't reachable, so this is safe to run with only some backends up — each file's docstring has the exact command for the one it needs.

**In CI**: Oxigraph runs as a GitHub Actions service container (its default image already serves on `:7878`, no config needed) alongside the SQLite tests, which need no server at all. **Fuseki does not run in CI** — its image needs dataset-creation arguments at startup that a service container can't supply — so Fuseki coverage is manual-only for now; this was a deliberate scope call, not an oversight, and may change later.

## 3. Cross-backend parity — same query, same answer, everywhere

**Question:** does the same operation produce the same observable result regardless of which backend is running it? This is the project's core value proposition.

```bash
pytest tests/integration/test_cross_backend_parity.py -v
```

Technically part of tier 2 (same marker, same CI wiring) but called out separately because it's checking something the other integration tests don't: not "does backend X work," but "does backend X agree with backend Y and with in-memory." Each backend's scenarios skip independently if that backend isn't reachable.

## 4. Benchmarks — where to expect degradation

**Question:** not "is it correct" but "how does it degrade as data grows, and which backend should I pick for this workload." These are timing scripts, not pass/fail tests — no `pytest` marker, run directly:

```bash
python benchmarks/bench_inmemory.py   # no server needed
python benchmarks/bench_http.py       # Fuseki and/or Oxigraph — skips whichever isn't reachable
python benchmarks/bench_scaling.py    # same
```

See `benchmarks/README.md` for setup and what each script measures. Run these manually before a release, or after any change likely to affect performance (encoding scheme, query rewriting, backend dispatch) — not on every commit; results are noisy on shared CI runners and there's no fixed pass/fail threshold to gate on.

**Known degradation points**, from the last full run (`docs/performance.md`, re-measured 2026-07-17 — re-run `bench_scaling.py` before trusting these numbers on a materially different codebase or dataset shape):

- **In-memory**: fine up to ~100K annotated facts; memory pressure sets in around there, hard ceiling near 1.5M. Full-annotation scans (not single lookups, which stay near-instant) slow from ~150ms at 50K to ~1.7s at 500K.
- **SQLite**: single-subject/object lookups stay fast (<35ms) even at millions of plain triples, but a full annotation scan is **67× slower than in-memory** at 250K annotated facts (54s vs <1s) — not a suitable backend for workloads that regularly query large numbers of annotated facts.
- **Fuseki (`rdf-1.1`)**: eliminates SQLite's scan problem and beats in-memory on broad scans past ~250K facts, at the cost of running a server.
- **Fuseki (`rdf-1.2`)**: same server cost, but native triple-term storage cuts stored triples ~20% and query time 35–48% versus `rdf-1.1` encoding.
- **Oxigraph (`rdf-1.2`)**: fastest backend for broad scans/joins at every scale tested (194ms full-scan at 250K, 4.7× faster than in-memory); the one place it loses is single-subject/object lookup, where in-memory's plain dict lookup (~2ms) beats Oxigraph's HTTP round-trip (13–36ms).

For the full write-up and backend recommendations, see `docs/performance.md`.
