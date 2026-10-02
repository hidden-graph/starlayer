# StarLayerGraph Performance

*Last reviewed: 2026-07-17*

## Executive Summary

### In-memory: the right starting point

The in-memory backend is where you start. No server, no configuration — load your data and query it. For everyday workloads, it is fast enough that performance is not a consideration.

The ceiling is RAM. Each annotated fact requires roughly four times the storage of a plain triple. On a typical 16 GB laptop, you start to feel memory pressure around 100K annotated facts and hit a hard limit near 1.5 million. Plain triples scale much higher — several million fit comfortably.

Query speed depends on what you ask. Looking up annotations about a specific subject or object is nearly instant at any scale. Asking for *all* annotations at once is slower: roughly 150ms at 50K facts, 800ms at 250K, 1.7 seconds at 500K. If your application regularly needs to scan the full annotation set, this becomes a limitation.

Data does not survive using in-memory. Every restart requires reloading from a file or other external source.

### SQLite: persistence without a server — with a catch

SQLite solves two weaknesses of in-memory mode. Data persists across restarts, and graphs can grow beyond available RAM — millions of plain triples fit in a single file with no memory pressure.

For simple lookups — find everything about this subject — SQLite works well at any scale, staying under 35ms for 5 million triples.

A challenge is complex queries over annotated facts. At 250K annotated triples, a query that scans all annotations takes 54 seconds in SQLite versus less than a second in memory — a 67× gap. The more patterns a query combines, the worse it gets. **SQLite is not a suitable backend for workloads that regularly query large numbers of annotated facts.**

### Fuseki (rdf-1.1): eliminating the query performance problem

Fuseki is an open-source RDF server that evaluates SPARQL queries natively. When StarLayerGraph sends a query to Fuseki, Fuseki handles the entire query at once rather than executing it piece by piece. This eliminates the performance problem that makes SQLite slow, and it also outperforms in-memory for broad queries — the same full-annotation scan that takes 903ms in memory at 250K facts takes 534ms via Fuseki, and 1.80 seconds versus 1.02 seconds at 500K. Data persists across restarts and is not limited by available RAM.

Fuseki requires running a server.

### Fuseki (rdf-1.2): further improvement through native storage

**`backend='rdf-star'` was removed 2026-07-16.** It targeted an older, pre-standardization Jena draft quoted-triple syntax (`<< s p o >>`); confirmed directly against a live Fuseki 5.5.0, that syntax no longer returns `"type":"triple"` in SPARQL JSON results (a plain blank node comes back instead), breaking triple-term round-tripping.

**Use `backend='rdf-1.2'` instead**, which speaks the final `<<( s p o )>>` syntax natively — confirmed working against Fuseki 5.5.0 (see `docs/future_enhancements.md`) and now separately re-benchmarked (2026-07-17) under this backend flag: storing annotated facts as native quoted triples cuts the data stored in Fuseki by 20% (300K physical triples versus 375K for the rdf-1.1 encoding-triples approach at 250K TTs) and gives a consistent 35–48% improvement in query speed over rdf-1.1 — the 250K full-annotation scan drops from 534ms to 340ms, and the combined scan-and-filter query drops from 437ms to 226ms.

### Oxigraph (rdf-1.2): the fastest backend

Oxigraph is a Rust-based RDF 1.2 store. Running in in-memory mode, it is the fastest backend for broad queries at every scale tested. At 250K annotated facts, the full-annotation scan takes 194ms — 4.7× faster than in-memory Python, 1.7× faster than rdf-1.2/Fuseki. The combined scan-and-filter query takes 147ms, versus 226ms on rdf-1.2/Fuseki and 1.53 seconds in memory. The advantage comes from Oxigraph's compiled Rust SPARQL engine, native RDF 1.2 quoted-triple storage, and zero JVM overhead.

The only case where Oxigraph does not outperform is single lookups (finding all annotations for a specific subject or object), where Python's in-memory dict lookup at ~2ms beats Oxigraph's 13–36ms HTTP round-trip. For workloads dominated by broad scans or joins, Oxigraph is the clear choice. Like Fuseki, it requires running a server.

Oxigraph also ships as `pyoxigraph`, a Python extension that embeds the Rust library in-process with no HTTP overhead. This was not benchmarked here: users choosing direct-mode Oxigraph will generally not be using rdflib or StarLayerGraph, since pyoxigraph exposes its own query API rather than the rdflib `Graph` interface.

*Numbers above are from `benchmarks/bench_scaling.py`, re-measured 2026-07-17 against live Fuseki 5.5.0 and Oxigraph 0.5.9 (median of 3 runs, 250K/500K TT scale, 10% reification rate). Full output for all three scales (50K/250K/500K) and all four backends (in-memory, rdf-1.1/Fuseki, rdf-1.2/Fuseki, rdf-1.2/Oxigraph) is reproducible by running that script against the Docker setup in `benchmarks/README.md`.*
