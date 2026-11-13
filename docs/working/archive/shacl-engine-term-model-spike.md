# Engine term model spike: pyoxigraph terms inside the engine

Branch `shacl-engine-terms` (a copy of `shacl-engine` at 135b603), 2026-10-31. Question: should the engine's internal term model be
pyoxigraph's `NamedNode` / `BlankNode` / `Literal` / `Triple` instead of rdflib `URIRef` / `BNode` / `Literal` plus starlayer's `TripleTerm`
and `DirLangString`? Answer measured below: **the whole engine was ported and is green**, so this is a measured result, not an estimate.

## What was built

1. `shacl_engine/xsd_values.py` (488 lines, pure Python, no rdflib, standard library only): the XSD value space over pyoxigraph literals.
   `parse(literal) -> Value | None`, `well_formed`, `compare(a, b) -> -1 | 0 | 1 | None`, `value_equal`, `term_equal`, `ebv`, `numeric`,
   `known_datatype`. Covers `xsd:integer` and all 12 derived integer types with range facets, decimal, float (binary32 rounding), double,
   INF/NaN, boolean (`true`/`false`/`1`/`0`), the string types, hexBinary/base64Binary, anyURI, dateTime/dateTimeStamp/date/time/gYear/
   gYearMonth/gMonth/gMonthDay/gDay with the XSD 1.1 timezone partial order (a pair with and without a timezone is ordered only when more
   than 14 hours apart, else incomparable) and `24:00:00`, and duration/yearMonthDuration/dayTimeDuration with the four-reference-date
   partial order. Every function names its spec clause. This file is the single place a Rust port re-implements value logic.
   Tests: `tests/shacl_engine/test_xsd_values.py` (268 cases), including a cross-check against rdflib's own values for every well-formed
   case and for all datatyped literals of the vendored W3C SHACL 1.2 fixtures (rdflib is the oracle; where rdflib is laxer, e.g. `int()`
   accepting `"1_0"` or no range facet on `xsd:byte`, only our well-formed side is cross-checked). It found one real bug in my first
   version (Decimal vs NaN raising `InvalidOperation`).
2. `shacl_engine/terms.py` (337 lines): the term model and its boundary. `NS` namespaces of `NamedNode` constants (`SH`, `RDF`, ...),
   `to_engine` / `from_engine` (lexical form kept both ways; `Literal(..., normalize=False)` outward), `RdflibTermView(graph)` (a `GraphView`
   yielding pyoxigraph terms over an rdflib / StarLayerGraph), `LegacyTermView(view)` (the inverse, rdflib terms over an engine view),
   `engine_view(graph)` (the seam: `Plan` and `Context` call it, so every entry point accepts either kind of graph).
   `OxigraphGraph` now yields store terms directly (`engine_terms = True`); its cache-and-convert code (`to_ox` / `from_ox`) became aliases.
3. The port of every engine module. rdflib terms remain only at the boundary: `Outcome.results` and `report_graph` (converted back), the
   caller's graphs, the entailment closure (`StarLayerGraph.infer`), the SPARQL query layer, `text.py`, and four modules that read and
   write the caller's graphs directly (`shapes_graphs`, `modules`, `imports`, `meta`), which keep an rdflib `SH`.

## Results

### Tests
- Engine suite command: **1613 passed, 1 skipped, 4 xfailed, 1 failed** (the failure is the known `seconds-example` fixture defect). That
  includes the 268 new `xsd_values` tests; the 1005-passed baseline in the task brief predates the plan_json and later suites, which
  the same command counts here. The 4 strict xfails (Oxigraph literal normalization, oxigraph#526) are unchanged: **the store still normalizes,
  so they do not move**, and none became a pass or a new failure.
- Native-mode tier (`STARLAYER_SHACL_ENGINE=native`, `tests/shacl` minus the W3C and engine directories, through the old API's
  adapter): **1586 passed, 152 failed, 12 skipped, 2 deselected**, identical to the recorded pre-port numbers in
  `shacl-engine-native-mode-run.md` (1586 / 152). The adapter path is therefore not worse.
- `ruff check packages/ tools/`: clean. No new xfail shims.

### Lines changed (against the merge base 135b603)
Production code, 32 files: **+474 / -456** excluding the two new files, plus `xsd_values.py` +488 and `terms.py` +337.
Tests: 17 files, **+420 / -58**, of which `test_xsd_values.py` is +293; the 16 existing test files changed by +127 / -58.

| file | + | - | note |
|---|---:|---:|---|
| `components/core_value.py` | 31 | 62 | `_NUMERIC`/`_ORDERED` sets, `_ordered_value`, `DirLangString` branches gone; ranges via `xv.compare` |
| `components/core_string_pair.py` | 26 | 56 | `_comparable` (with its `type(val).__name__` date sniffing) replaced by 4 lines on `xv.compare` |
| `components/core_shape_based.py` | 33 | 23 | `Triple` for reifiers, `.value` for lexical checks |
| `oxigraph_view.py` | 21 | 93 | conversion code and caches removed; view returns store terms |
| `expressions.py` | 75 | 56 | `sum` / `orderBy` / EBV now on `xsd_values`; `sparql:` calls convert at the query layer |
| `report.py` | 32 | 24 | closure copy converts to the report graph |
| `api.py` | 38 | 5 | `engine_view` at entry, `legacy_result` at exit |
| `rules.py` | 35 | 16 | overlay is term-agnostic; conversion at SPARQL materialisation, `CONSTRUCT` results, `RuleResult.inferred` |
| `plan_json.py` | 33 | 26 | `term_to_json` is simpler (no DirLangString branch) |
| `sparql_support.py` | 24 | 21 | conversion in `starlayer_sparql_query`, custom-function bridge |
| `entailment.py` | 21 | 10 | closure in rdflib terms, delta converted in |
| `components/extensions.py` | 24 | 5 | `legacy_adapter` for components written against rdflib (salg) |
| the other 20 files | 105 | 75 | imports, `str(x)` -> `.value`, isinstance swaps |

Mechanical swaps (imports, `isinstance`) are about half of the churn. The behavioural edits are `xsd_values`-related and boundary-related.

### Benchmarks (`bench_engine_vs_old.py --sizes 5000,20000 --repeat-max 5000`, best of 3 up to 5000)
Two interleaved runs per side on a noisy machine (the unchanged old validator, `old-slg`, moved from 1.96 s to 2.70 s between runs, so
differences under about 35% are noise). Seconds, best-of per run, "run 1 / run 2".

| triples | config | before (rdflib terms) | after (pyoxigraph terms) | peak RSS MB before / after |
|---:|---|---:|---:|---:|
| 4657 | old-slg (unchanged) | 1.96 / 2.56 | 2.58 / 2.70 | 85, 77 / 77 |
| 4657 | new-slg | 0.90 / 1.55 | 1.50 / 1.06 | 53, 52 / 52, 51 |
| 4657 | new-ox | 0.38 / 0.61 | 0.59 / 0.51 | 57, 56 / 56, 56 |
| 18572 | old-slg (unchanged) | 8.10 / 11.64 | 10.84 / 11.01 | 121 / 121 |
| 18572 | new-slg | 4.60 / 6.09 | 6.21 / 4.56 | 68, 71 / 71, 68 |
| 18572 | new-ox | 2.27 / 2.13 | 2.66 / 2.33 | 84, 83 / 84, 85 |

Reading: **StarLayerGraph input is unchanged** (means 5.35 s vs 5.39 s at 18.5k triples; the per-triple `RdflibTermView` conversion is
hidden by the term caches). **Oxigraph input is not faster**; if anything about 10% slower at 18.5k (2.20 s vs 2.50 s mean), inside the
noise. I expected the removed `from_ox` conversion to help; it does not show here, plausibly because this workload spends its time in
the SPARQL constraint and pattern/regex checks, and because `xsd_values.parse` (an `lru_cache`d lookup) replaced rdflib's cached
`.value`. Memory is flat. No benchmark of the value-heavy paths (range checks over many numerics) was run; that is where `xsd_values`
could differ most.

## What got simpler
- **Value logic has one home.** The engine had four ad hoc value paths (`core_value._ordered_value`, `core_string_pair._comparable`, `sum`,
  `rules._number`) each leaning on rdflib's `.value` / `.toPython()` / `.ill_typed`; they are now calls into `xsd_values`. A Rust port
  re-implements 488 lines, not four scattered idioms.
- **`sh:datatype` well-formedness is a real range check** (`"300"^^xsd:byte` is ill-formed). rdflib has no range facets, so this was
  wrong before and no test noticed. Ordering is now the XSD 1.1 partial order, so mixed-timezone comparisons are incomparable rather
  than a caught `TypeError`.
- **No `DirLangString` / `TripleTerm` special cases**: base-direction literals and triple terms are ordinary `ox.Literal` / `ox.Triple`
  (about 12 `isinstance` branches deleted in `core_value`, `core_string_pair`, `plan_json`, `oxigraph_view`).
- **Lexical forms are exact by construction**, so the `normalize=False` discipline (the `or-datatypes-001` bug) cannot be forgotten on the
  engine side; there is nothing to forget.
- **Oxigraph input needs no conversion** and `OxigraphGraph` lost about 70 lines.
- The EBV used by `sparql:if` / `logical-or` no longer imports `rdflib.plugins.sparql.operators`.

## What got harder
- **`str(term)` changes meaning silently.** `str(ox.NamedNode)` is `<http://...>`, `str(ox.Literal)` is the N-Triples form. Every message,
  `f"{x}"`, `.split("#")` and sort-by-str had to be found and rewritten to `.value` or `terms.text()`. Missed ones are runtime wrong
  strings, not exceptions. Of the 16 test files that needed edits, 7 were this.
- **Inputs can now fail to convert.** pyoxigraph validates on construction. `to_engine(URIRef("a"))` (relative), `URIRef("http://x/a b")`
  and `URIRef("")` raise `ValueError`; rdflib accepts all of them. A caller graph with one such IRI used to validate and now raises at the
  seam. A policy is needed (reject with a clear error, or map to a placeholder IRI). rdflib `Variable` terms (the SPARQL-algebra graphs,
  `salg`) have no oxrdf counterpart; they cross as `urn:starlayer:variable:<name>` IRIs and back.
- **Four conversion points at the query layer**, which still returns rdflib terms: `starlayer_sparql_query` (bindings out, rows in), the
  `InferredView` materialisation and `CONSTRUCT`, the `sh:ListParameterExpressionFunction` bridge, and the `sparql:` function scratch
  query. Native Oxigraph SPARQL needs none. This is the permanent cost until the query layer can speak oxrdf terms.
- **Out-of-tree components must adapt.** `components.registry.component()` now normalises rdflib IRIs; a component function that reads
  `ctx.data` / `params` in rdflib terms must go behind `extensions.legacy_adapter` (done for `salg`, whose `register()` was changed).
- **Internal APIs changed type.** Tests (and any caller) that drive `evaluate_expression`, `eval_path`, `focus_nodes`, `InferredView`,
  `entailed_view` or `RuleResult.view` with rdflib terms need wrappers: 16 test files, +127 / -58 lines. The public entry points
  (`validate`, `validate_each`, `evaluate`, `extract_subgraph`, `apply_rules`, report graph, `Outcome.results`) are unchanged for callers.
- `SH` exported from `plan` is now a pyoxigraph namespace. Code that used it against rdflib graphs (the native adapter, three tests, the
  differential plugin) needed its own rdflib `SH`.
- Equality semantics differ in two places the tests exposed: pyoxigraph treats `"x"` and `"x"^^xsd:string` as one term (as rdflib does not),
  and `ox.Literal` equality is exact lexical/datatype/language/direction equality (as `term_equal` documents).

## Key risks
1. **Invalid-IRI inputs** (above). Decide the policy before adopting.
2. **Silent `str()` regressions** in future code: nothing stops a contributor writing `f"{term}"`. A lint rule (ban `str(` on terms in
   `shacl_engine`) or a `Term.__str__` is impossible (the types are final), so reviewers carry it.
3. **Query-layer boundary cost** grows with SPARQL-heavy shapes (see benchmarks); removing it needs the query layer to emit oxrdf terms.
4. **Two worlds in one package** (`LegacyTermView`, `legacy_adapter`, rdflib `SH` in four modules) is a standing source of confusion
   until `shapes_graphs`, `modules`, `imports`, `meta` and `text.py` are ported too (they were left on rdflib deliberately: they operate
   on the caller's graphs and have no performance reason to change).
5. **`xsd_values` is new code** with a cross-check only against rdflib where rdflib is laxer or has no opinion (gMonth/gDay ordering,
   durations, range facets, `24:00`). The XSD 1.1 partial order and the duration order are implemented from the spec text, not from a second
   implementation. Add a W3C XSD test-suite run, or compare with `oxsdatatypes` (Rust) when porting.
6. Oxigraph still normalizes on storage: nothing here helps with oxigraph#526. The term model removes the engine-side loss only.

## Recommendation
**Adopt, with three conditions, for the whole engine (not core only).**

Why:
- The full port was done in one pass and is green on every oracle: engine suite, W3C engine suites, 4 strict xfails unchanged, native-mode
  tier identical (1586 / 152). The production diff is net-neutral (+474 / -456 plus 825 lines of new, well-tested code), so the term model
  is not the large risk the cost list suggested.
- It buys what the task asked for: exact lexical forms by construction, one-to-one oxrdf types for the Rust port, native triple terms and
  base direction, no conversion on Oxigraph input, and value logic collected in a single re-implementable file (`xsd_values.py`) that is
  stricter than rdflib (range facets, XSD 1.1 partial orders).
- Performance is neutral on rdflib/StarLayerGraph input and, at worst, slightly slower on Oxigraph input within noise: there is no
  speed argument for it and none against.
- "Core only" is not a stable middle: `expressions`, `rules`, `sparql_support` and `report` all sit on the executor's `Context` and the
  `Plan`, so a half-ported engine needs the bridge in both directions. The spike's boundaries (`engine_view`, `LegacyTermView`,
  `legacy_adapter`) are the right size only because the engine core is entirely on one side.

Conditions before merging this into `shacl-engine`:
1. **Decide the invalid-IRI policy** at `to_engine` (relative IRIs, IRIs with spaces, empty IRI, blank node ids, language tags): raise a
   `ShapeError`/`ValueError` with the offending term, or map to a placeholder. Today it is an uncaught `ValueError` from pyoxigraph.
2. **Ban `str(term)` in `shacl_engine`** (a ruff `flake8-forbidden`-style check or a code-review rule): the silent `<iri>` formatting is the main
   regression class.
3. **Validate `xsd_values` against a second implementation** (the XSD 1.1 test suite or `oxsdatatypes`) before it is the source of truth;
   the rdflib cross-check is weak exactly where the new code is stricter.

What remains (not done, deliberately): `shapes_graphs`, `modules`, `imports`, `meta` and `text.py` still work in rdflib terms on the
caller's graphs (no reason to move them until the Rust port); the SPARQL query layer still returns rdflib terms (four conversion points);
`xsd_values` has no cross-check for gMonth/gDay/duration beyond its own tests; no value-heavy benchmark was run.

## Adoption outcome (branch `shacl-engine-terms-merge`, 2026-10-31)

The owner approved adoption. `shacl-engine-terms` was merged into a branch from `shacl-engine` (merge commit, no rebase). Conflicts were
only in `rules.py` and `entailment.py`, where `shacl-engine` had added `new_overlay` (the opt-in Oxigraph overlay) and the term branch had
added the `engine_view` / `to_engine` boundary; both survive. The overlay prototype was ported to engine terms and got simpler: engine
terms are store terms, so `overlay_oxigraph.py` no longer converts anything (its fidelity guard shrank: `"x"^^xsd:string` and
lower-cased language tags are now identical at the engine level, so only lexical-form and derived-datatype rewrites remain). It stays
opt-in (`STARLAYER_SHACL_OVERLAY=oxigraph`); not the default, as measured. Porting it exposed one bug the old tests missed (a materialised
union fed rdflib-incompatible terms); `test_add_after_materialise_keeps_the_materialised_union_in_step` pins it.

### Condition 1: the ill-formed-term policy
pyoxigraph rejects terms rdflib accepts: relative or empty IRIs, IRIs with spaces or `<>{}|`, blank node ids with spaces or empty, language
tags such as `e` or `en-abcdefghi`, and an invalid datatype IRI. **One policy**, `terms.TermError` (a `ValueError`):
- *Why an error.* SHACL 1.2 validates RDF graphs, in which an IRI is an absolute IRI and a language tag is BCP47. A graph with such a term
  is not an RDF graph, so the specification defines no report for it: it is not a `sh:nodeKind` question (what kind is a non-term?) and not
  a validation result (there is no focus node or value node to report). The engine's other rules agree: the shapes graph is also parsed
  strictly (a malformed list or a non-integer `sh:minCount` is a `ShapeError`, not a result). So the default fails, early and once.
- *Where.* Every entry point (`validate`, `validate_each`, `evaluate`, `extract_subgraph`, `apply_rules`) scans the data, shapes and ontology
  graphs before doing anything (`terms.check_graphs`; a graph is scanned once per size) and raises one aggregate `TermError` listing every
  offender (first 100) with its graph (`data graph` / `shapes graph`), position (subject / predicate / object / datatype of the object) and
  first triple. `OxigraphGraph.from_graph`, `add` and pattern lookups raise too. `RdflibTermView` no longer swallows `ValueError`.
- *Lenient opt-in.* `invalid_terms="lenient"` on the entry points (or `with terms.term_policy("lenient")`) maps each offender to an opaque,
  reversible stand-in: `urn:starlayer:invalid-iri:<percent-encoded text>` (also as a literal datatype), a blank node
  `starlayer-invalid-bnode-<hex>`, and for a bad language tag a literal of datatype `urn:starlayer:invalid-lang:<tag>`. Every result and the
  report graph map back to the original rdflib term; the offenders are listed on `Outcome.invalid_terms`. An ill-formed IRI is still an IRI
  for `sh:nodeKind` (as rdflib says) but text constraints see the stand-in text; a bad-tag literal is not `rdf:langString`. Stand-ins are not
  cached in the strict conversion cache, and a lenient view stays lenient when read after the block (lazy `report_text`).
- *Native adapter* (`starlayer/shacl/native_adapter.py`): the old API accepted these graphs and pySHACL defines their result, so
  `validate` and `apply_rules` **fall back to the pySHACL path** with `engine_fallback_reason = "ill-formed RDF term (...)"`. `evaluate`,
  `extract_subgraph`, `close_shape` and `extract_shapes_graph` have no inline fallback; they surface the clear `TermError`.
- *Differential harness* (`tests/shacl/differential_plugin.py`): a `TermError` from the engine is recorded as `skipped` with
  `skip_options: ["ill_formed_term"]` and the message.
- Tests: `tests/shacl_engine/test_ill_formed_terms.py` (61: ten term kinds through `to_engine`, round trip, strict and lenient `validate`
  on `Graph` and `StarLayerGraph`, every entry point, the views, `OxigraphGraph`, adapter fallback, harness skip).

### Condition 2: no `str(term)` in `shacl_engine`
`terms.py` gained `lexical`, `iri_text`, `n3` (the one sanctioned `str()` of a term, for an N-Triples rendering) next to `text`.
`tests/shacl_engine/test_no_str_of_terms.py` walks the AST of every module and fails on `str(x)`, an f-string field, `%` formatting,
`.format()` and `key=str` / `map(str, ...)` whose argument is not provably plain (literals, f-strings, `.value`, `len`/`int`, the text
helpers, string methods, constants, names with plain suffixes). `!r` is allowed (explicit repr). Reviewed lines carry
`# str-ok: <reason>`; `text.py`, `meta.py`, `shapes_graphs.py` carry `# str-ok-file:` because they hold only rdflib terms, and a second test
holds those files to it (no pyoxigraph, no engine term constants). The checker itself is tested on 15 flagged and 12 accepted snippets.
It found real silent bugs: `builder.py` (`f"{node}"` printed `<iri>`), `sh:hasValue` ("Missing required value <iri>"), parameter names in
five `ShapeError`/`RuleError` messages, `entailment.py` (`sorted(map(str, ...))`), the rule-type message. 46 candidates at first run,
all fixed or marked.

### Condition 3: cross-check against Oxigraph (`oxsdatatypes`)
`tests/shacl_engine/test_xsd_values_vs_oxigraph.py` (corpus in `xsd_oracle_corpus.py`, about 1,500 lexical forms over 16 datatypes
plus all 13 integer types at and beyond their bounds, 14 pairwise value families, 200 EBV cases). Oracle: Oxigraph's casts
(`xsd:T("lex")` bound or not), `<` `=` `>` (SHACL asks only whether a comparison is true, so SPARQL error and false are the same), and
`IF(?x, ...)` for EBV. Derived integer types have no Oxigraph cast; their oracle is the XSD 1.1 facet table. Result: 59 well-formedness,
1,196 comparison and 163 EBV disagreements at first run, reduced to the decisions below. The test fails on any unexplained disagreement and
on any documented one that stops occurring.

**xsd_values was wrong (fixed):**
1. Cross-type numeric comparison was exact; SPARQL 17.3 maps `=` / `<` to `op:numeric-*`, which promote integer < decimal < float < double
   (F&O 3.1 6.2): `0.1` decimal = `0.1e0` double, `9007199254740993` = `9007199254740992e0`. Now promoted (SHACL range checks use `<`).
2. `xsd:time` `24:00:00` was the end of day (> `00:00:00`); XSD 1.1 3.3.14 normalises hour 24 to 0 for `time` (equal). dateTime keeps next-day.
3. EBV of an ill-formed boolean or numeric was an error; SPARQL 1.1 17.2.2: false. Other ill-typed datatypes remain errors.
4. Duration seconds `PT.5S`, `PT1.S` are valid (`unsignedDecimalPtNumeral`); were rejected.
5. `hexBinary` / `anyURI` ordering `=` was value equality; SPARQL `=` is RDFterm-equal there (the same term), so `"0A"` and `"0a"` are not
   equal (`compare` gives `None`). Boolean `<` stays supported (17.3 `op:boolean-less-than`).

**Oxigraph is wrong or narrower (documented, asserted, in the test as rules):**
- `whitespace-collapse`: `" 12 "^^xsd:integer` etc. are valid (XSD 1.1 4.3.6); Oxigraph rejects (11 cases).
- `arbitrary-precision`: integers, decimals, seconds with 19+ digits are valid (XSD requires only 18); Oxigraph's types are fixed width. Its
  comparisons with such operands are errors (1,188 pairs).
- `float-special-spellings`: Oxigraph accepts `inf`, `Infinity`, `nan`, `-NaN`, `+inf` (Rust `f64`); XSD 1.1 allows only `INF`, `+INF`, `-INF`, `NaN`.
- `duration-empty-time-part`: Oxigraph accepts `P1DT`, `P1YT` (XSD 1.1 duTimeFrag needs a component).
- `gMonthDay-feb-29`: Oxigraph rejects `--02-29`; XSD 1.1 accepts it (leap-year reference).
- `boolean-less-than`: Oxigraph errors on `false < true`; SPARQL 17.3 defines it.
- `ebv-of-unrepresentable-literal`, `derived-integer-range-facets`: Oxigraph errors on an ill-formed or too-wide numeric's EBV (spec:
  false) and has no range facets for `xsd:byte` etc. (`"128"^^xsd:byte` is true there).
Agreement elsewhere includes the XSD 1.1 timezone partial order (with/without timezone more than 14h apart decided, else incomparable),
the four-reference-date duration order, NaN, signed zeros, leading zeros, exponent forms, `INF`, leap years, `24:00:00` dateTime.

### Verification
Engine suites: 1768 passed, 1 skipped, 4 xfailed, 1 failed (the known `seconds-example` fixture defect). Default SHACL tier: 1738 passed, 12 skipped (baseline).
Native-mode tier: 1586 passed, 152 failed (baseline, same categories).
