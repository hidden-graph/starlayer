# Should the engine's inferred-triples overlay live in an Oxigraph store?

*Date: 2026-10-31. Branch: shacl-engine. Related: starlayer issue #190, `shacl-engine-feasibility.md` (Oxigraph literal normalization).*

## Recommendation

**Do not adopt.** Keep the Python `InferredView`. The overlay is not a bottleneck (a few percent of a validate-with-inference
run), the Oxigraph version is no faster and is slower on the lookups the engine does most, and it is only correct with a
fidelity guard that exists solely to work around the store. The prototype (`overlay_oxigraph.py`) stays in the tree as an
opt-in, tested, and documented experiment, so the question need not be re-measured. Revisit only if (a) the overlay
becomes large (millions of inferred triples, where Python sets cost memory), and (b) pyoxigraph ships oxigraph PR #2010
(literals stored as written), which would make the guard unnecessary.

## What was measured

`packages/starlayer/benchmarks-shacl/bench_overlay.py`: data from `bench_engine_vs_old.make_data` plus subClassOf,
subPropertyOf and domain/range axioms, and a rules shapes graph (a shape-level SPARQLRule, two global copying SPARQLRules,
a TripleRule). RDFS entailment, then rules, then validation. Python 3.10, rdflib, pyoxigraph 0.5.13, macOS, best of 3.
Absolute times are machine-dependent and the 5k Oxigraph run overlapped other work on the machine, so differences under
about 15% are noise.

| triples | stage | Python `InferredView` | `OxigraphOverlay` |
|---|---|---|---|
| 4,662 (RDFS delta 2,990; rules infer 1,428) | `entailed_view` | 2.98 s (owlrl 3.56 in a separate run, fill 0.04) | 4.64 s (owlrl 4.41, fill 0.20) |
| | `apply_rules` | 2.35 s | 3.20 s |
| | `validate` on the overlay | 0.54 s | 1.05 s |
| | full `validate(rdfs + rules)` | 5.38 s | 6.73 s |
| 18,577 (delta 11,669; rules infer 5,712) | `entailed_view` | 11.93 s (owlrl 11.10, copy 0.56, fill 0.19) | 12.37 s (owlrl 10.92, copy 0.93, fill 0.48) |
| | `apply_rules` | 7.61 s | 8.02 s |
| | `validate` on the overlay | 2.18 s | 2.48 s |
| | full `validate(rdfs + rules)` | 23.59 s | 23.46 s |

Same validation results in both (26 and 99 results). Lookup micro-benchmark on the finished overlay, microseconds per call
(18.6k triples): `objects(s,p)` 40.7 vs 65.2; `subjects(p,o)` 1728 vs 1118; `triples(s,?,?)` 169 vs 208; `__contains__`
7.3 vs 44.1. The Oxigraph overlay wins only on `subjects(p,o)` (a large-fan-in scan), and loses 2 to 6 times on point
lookups and membership, because every call converts rdflib terms to and from pyoxigraph terms. Filling the overlay is also
slower (0.48 s vs 0.19 s for 11.7k triples): each add checks the guard, checks three places for a duplicate, then inserts.

### Where the time goes (cProfile, validate with rdfs and rules, 18.6k triples, Python overlay)

Profiler-inflated total 70.7 s. Cumulative, overlapping:

* **owlrl closure (`StarLayerGraph.infer`): 34.1 s, 48%.** The top self-time entries are owlrl's `RDFSClosure.rules`
  and rdflib's in-memory store `triples` and namespace `bind` / `insert_trie`.
* **Rule SPARQL (`construct`, 2,860 calls): 25.1 s, 35%.** This is rdflib query evaluation on the materialised
  `StarLayerGraph`, one call per focus node for shape rules.
* Everything the overlay does itself: `add` 1.05 s, `triples` 2.20 s (mostly the base graph's own lookups), `objects`
  1.27 s, `subjects` 0.21 s, `__contains__` 0.17 s, total under 5 s, **about 6%**. Building the materialised
  `StarLayerGraph` for SPARQL (`materialised`, 4,288 calls, most of them cache hits): 2.2 s, 3%.

So of the three costs you asked about, closure computation and rule SPARQL are about 83% and the overlay and its SPARQL
materialisation about 9%. Making the overlay infinitely fast saves under 10%. The Oxigraph overlay cannot touch the two big
costs either: the closure is computed by owlrl on a `StarLayerGraph`, and rule SPARQL still has to run on a union that
holds the source literals exactly (below).

## Fidelity analysis

Verified against pyoxigraph 0.5.13:

* Rewritten on insert: `"04"^^xsd:integer` to `"4"`, `"1"^^xsd:boolean` to `"true"`, `"4.0"^^xsd:decimal` to `"4"`,
  `"1.0E0"^^xsd:double` to `"1"`, `"5"^^xsd:unsignedByte` to `"5"^^xsd:integer`, `"x"^^xsd:string` to the simple literal `"x"`,
  `"hi"@en-US` to `"hi"@en-us`. Ill-formed values (`"abc"^^xsd:integer`) are kept as written.
* **Reads are lossy too**: `quads_for_pattern` with the un-normalised `"04"^^xsd:integer` matches a stored `"4"`. A pattern
  by an unsafe literal therefore finds the wrong triples, not just returns the wrong lexical form.
* The sources of the problem are real. A derived triple carries a source literal whenever `rdfs:subPropertyOf` copies a value,
  or a `CONSTRUCT { ?s ex:q ?o }` rule copies `?o`. Notably rdflib itself normalises on parse (`Literal("04", datatype=XSD.integer)`
  becomes `"4"`); the test data therefore uses `normalize=False`, the way `OxigraphGraph` users get `"04"` in at all.

The guard in `overlay_oxigraph.py`:

1. `literal_survives_store(term)`: round-trips the literal through a scratch store once per (lexical, datatype, language,
   direction), caches the verdict, and compares the result exactly (type, string, datatype, language; rdflib's `==` ignores
   the case of a language tag, so it is not used alone). `xsd:string`-typed literals are always unsafe because the engine's
   `from_ox` returns a simple literal.
2. A triple whose subject or object is unsafe (triple terms are checked part by part), or that pyoxigraph cannot hold at all,
   is kept in the inherited Python storage; the rest go to the store.
3. A lookup by an unsafe term never consults the store, so it cannot hit the normalised twin.
4. SPARQL (`construct`, `sparql_query`) still runs on a materialised `StarLayerGraph` copy of base plus inferred, which holds
   source literals exactly. A native Oxigraph union store for rule SPARQL would normalise the base too, so it is not offered.

Result: `tests/shacl_engine/test_overlay_oxigraph.py` (8 tests, parametrised over both overlays where relevant) proves that
`"04"^^xsd:integer`, `"1"^^xsd:boolean`, `"5"^^xsd:unsignedByte` (and `"4.0"^^xsd:decimal`) survive a `subPropertyOf`
entailment, a global copying SPARQLRule and a shape rule with `$this` unchanged through the Oxigraph overlay; that
unsafe triples sit Python-side and safe ones in the store; that the un-normalised lookup does not hit the normalised twin; and
that the two overlays give the same answers on triples, subjects, objects, predicate_objects and `inferred`. With the guard
the Oxigraph overlay is faithful. Without it, those three literals would come back as `"4"`, `"true"` and an `xsd:integer`
`"5"`, i.e. a silent change of the data the shapes see (datatype and pattern checks would pass or fail wrongly).

## Suites

Engine suites with the overlay selected (`STARLAYER_SHACL_OVERLAY=oxigraph`, or `rules.use_oxigraph_overlay(True)`),
including `test_w3c_engine_rules.py`, `tests/shacl_engine/test_rules.py` and `test_entailment.py`: 1334 passed, 1 skipped,
4 xfailed, 1 failed, identical to the default overlay and to the baseline (the one failure is the known
`seconds-example` fixture defect). The count is above the earlier 1005 because the command now includes all of
`tests/shacl_engine` and the 8 new overlay tests. Ruff is clean for the new and changed files (the repo has 85 pre-existing errors elsewhere).

## Why not adopt

* Not a bottleneck: the overlay is about 6% of a validate-with-inference run; owlrl and rule SPARQL are about 83%.
* Not faster: equal at the stage level, slower on point lookups and membership (the engine's common operations), slower to fill.
* Not simpler: it needs the guard, the Python-side side set, a duplicate-check against three places, and a SPARQL path that
  stays on `StarLayerGraph` anyway. Two storage paths per overlay is more code and more risk than one set with three indexes.
* Memory is the one theoretical gain (store terms are interned), but at 12k inferred triples the Python sets are not a problem
  and this was not measured.

What would actually speed things up (not done here): a native or incremental closure instead of owlrl over a copied graph, and
running rule SPARQL natively without copying the base on each overlay change.

## Files

* `packages/starlayer/benchmarks-shacl/bench_overlay.py` (`--overlay python|oxigraph`, `--profile N`)
* `packages/starlayer/starlayer/shacl_engine/overlay_oxigraph.py`
* `packages/starlayer/tests/shacl_engine/test_overlay_oxigraph.py`
* switch only, in `rules.py` (`use_oxigraph_overlay`, `new_overlay`, env `STARLAYER_SHACL_OVERLAY`) and `entailment.py` (uses `new_overlay`)
