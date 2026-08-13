# Benchmarks

*Last reviewed: 2026-07-17*

Performance benchmarks for starshacl's triple-term encode/decode adapter (`starshacl/adapters.py::TripleTermAdapter`) - the boundary layer that translates between RDF 1.2 triple terms and the RDF-1.1-only term model pySHACL understands.

## Scripts

| Script | Scope | Requires |
| --- | --- | --- |
| `bench_adapter.py` | In-memory only: `encode_graph`/`decode_graph` wall-clock time and generated support-triple count, for a configurable triple count and triple-term nesting depth | No server - runs standalone |

## Running

```bash
python benchmarks/bench_adapter.py --triples 1000 --nested-depth 1
```

Flags:
- `--triples` (default 1000): number of triples in the generated test graph.
- `--nested-depth` (default 1): how deeply nested the generated triple terms are (`1` = flat triple-term objects; higher values nest a triple term inside another's object position).

Deeper nesting stresses the recursive parts of `_encode_node`/`_decode_node` specifically:

```bash
python benchmarks/bench_adapter.py --triples 2000 --nested-depth 3
```

Output:
- total encode time (ms)
- total decode time (ms)
- generated support-triple count (the `rdf:subject`/`rdf:predicate`/`rdf:object` triples the adapter emits per encoded triple term, so pySHACL's own report/rule machinery can still see the decomposed structure)

## What this doesn't cover

This measures the adapter's own encode/decode cost in isolation, not full `StarShaclValidator.validate()`/`apply_rules()` performance - `sh:construct` rule-iteration performance (dominated by `_SparqlAwareEncodedGraph.query()`'s decode cost, not the adapter's `encode_graph`/`decode_graph`) is a related but separate cost, currently only measured ad hoc via manual profiling (see `docs/implementation-plan.md`'s "Next Steps" for the known remaining bottlenecks there). Worth a dedicated script here if that becomes a recurring need.

## Results

See [`docs/benchmark-baselines.md`](../docs/benchmark-baselines.md) for recorded baselines over time.
