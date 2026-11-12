# What `main` changed since 2026-11-02, and what `shacl-engine` needs from it

Review of 2026-11-11. `main` has 11 commits since the merge base (`040868fe`, 2026-11-02), all in SHACL: the issues #201 to #205 and an
`evaluate(validate=True)` option. They are in files that `shacl-engine` does not have (`constraint_annotations.py`, `native_components.py`,
`component_cache.py`: the pyshacl-era layer), so none of them can be cherry-picked. The question for each is whether `shacl-engine`
**behaves** the same, so I ran `main`'s new and changed tests against `shacl-engine` (a scratch worktree, with `main`'s files copied in and
adapted: pyoxigraph terms for rdflib terms, no `pyshacl` import). The adaptations are mechanical and listed at the end; what still fails is a
behaviour difference.

## Status

Ported so far: #204 (meta-shapes), `evaluate(validate=True)`, #201 (all 303 of `main`'s per-constraint annotation tests pass: `tests/shacl/integration/test_per_constraint_annotations.py`). #203 (the stored triples read by `sh:values` / `sh:defaultValue` are in the fragment: `shacl_engine/reads.py`; for `sh:select` the reads come from `starlayer.sparql.relevant`: the supports and the evidence of exclusion of the query), and `main`'s fuzzer and logic tests as standing engine tests. All five items are ported.

## Result

| `main` change | `shacl-engine` today | Port? | Size |
|---|---|---|---|
| **#201 per-constraint annotations** (`70a8e087`, `296a9713`, `8991a20d`): `sh:severity`, `sh:message`, `sh:deactivated` on the reifier of any constraint triple, for every component | **Partly.** 227 of `main`'s 303 tests pass: direct `sh:severity` and `sh:deactivated` work. 76 fail, in the groups below | **yes** | medium to large |
| **#202** conformance inside `extract_subgraph` uses the computed `sh:values` | works: 4 of 5 tests pass (the fifth is #203) | no | none |
| **#203** the stored triples read to compute `sh:values` / `sh:defaultValue` are in the fragment | **missing**: the fragment lacks them (about 25 failures, see below) | **yes** | medium |
| **#204** meta-shapes: `sh:values` / `sh:defaultValue` need a single IRI as `sh:path` | **missing**: 12 of 16 tests fail (a complex path is accepted) | **yes** | small: two shapes, 26 lines, in `scripts/assets/shacl12-validation-shapes.ttl` |
| `evaluate(validate=True)`: only the shapes a node conforms to contribute values | **missing**: `evaluate()` has no `validate` parameter (14 of 14 tests fail) | **yes** | small to medium |
| **#205** a violated `sh:closed` is evidence in a fragment, plus a randomized hunt for under-extraction | works: the 5 closed-evidence tests pass, and the fuzzer's properties P1 to P5 pass at 150 examples | port the **fuzzer** as a standing test | small |
| `bbd231e6` `extract_subgraph` and `sh:or` / `sh:xone` / `sh:not` / `sh:and`: order independence | works: 6 of 6 tests pass | the test only | none |
| generated API reference, `CLAUDE.md`, gap matrix | n/a | regenerate | none |

## #201 in detail: the 76 failures

The matrix test counts from `test_per_constraint_annotations.py`:

| Group | Failures | What is missing |
|---|---:|---|
| a reifier `sh:message` replaces the default and the shape's message, for each component (class, datatype, nodeKind, counts, lengths, pattern, languageIn, uniqueLang, in, hasValue, the property-pair ones, node, not/and/or/xone, qualified*, sparql, the SHACL 1.2 ones, closed, expression, node-level variants) | 46 | `sh:message` is not read from a reifier at all (the shape's message wins); severity and deactivated are |
| `sh:deactivated` whose value is a **node expression**, evaluated per focus node | 15 | only the literal `true` / `false` forms |
| annotations on the **other parameter triple** of one constraint, merged: `sh:flags` with `sh:pattern`, `sh:ignoredProperties` with `sh:closed`, `sh:qualifiedValueShapesDisjoint` with the count | 5 | only the main triple is read |
| a user-defined component with one parameter: each value with its own annotation runs alone; multi-parameter messages are united | 5 | no per-value attribution for custom components |
| conflicting severities in one constraint resolve to the most severe; two reifiers of one triple | 2 | no merge rule |
| language-tagged messages are all carried; an annotation changes only its own constraint | 3 | messages |

What the engine already does is in `shacl_engine/builder.py` (per-triple `sh:deactivated` and `sh:severity` read from the reifier). The port is
there and in how a violation takes its message, not a copy of `main`'s wrapper (`constraint_annotations.py` wraps the pyshacl-era component
classes). `main`'s tests are the specification to port. The W3C suite, which `shacl-engine` passes in full, has a reifier-message test
(`message-003`) that passes, so the gap is in how widely the engine looks, not in the idea.

## #203 in detail

For `sh:values` / `sh:defaultValue` whose expression reads the data (`shnex:pathValues`, multi-hop paths, nested in `sparql:concat`, `sh:select`,
custom functions), `main` records the triples read while computing the value and adds them to the fragment, never the computed triple itself,
so that `evaluate()` over the fragment recomputes the same values. `shacl-engine` returns a fragment without those triples unless another
constraint happens to read them (which is why the fuzzer's P4 passes: its shapes also constrain the path). The expression evaluator needs a
recording wrapper around the data it reads, used by `extract_subgraph` only.

## Where the tests differ for a reason, not a gap

- Four of `main`'s cases write the expression as `[ sh:path ex:first ]`, the SHACL-AF form. `shacl-engine` rejects it on purpose
  (`starlayer/shacl/CLAUDE.md`: use `shnex:pathValues`). Port those with the current form.
- `main`'s tests compare rdflib terms; ours are pyoxigraph terms. Porting them means writing them for the engine's term model.

## Adaptations made to run `main`'s tests here (so the numbers can be reproduced)

`str(term)` replaced by the term's value; `result.report_graph` by `result.report_graph.to_rdflib()`; the `pyshacl` imports removed
(`ReportableRuntimeError` is `MetaShaclError`); `from starlayer.graph.graph.starlayer_graph import StarLayerGraph` by `from starlayer import
StarLayerGraph`; in the fuzzer, `RDF.first` comparisons and `E.v` converted to pyoxigraph terms. After these, the fuzzer had 9 usable cases of 80
in a direct run (the generator works), and P1 to P5 pass at 150 examples.

## Suggested order

1. **#204**, the two shapes (small, and a stored meta-shape file that is otherwise already shared in spirit).
2. **`evaluate(validate=True)`**.
3. **#201**, message first (46 of the 76), then expression-valued `sh:deactivated`, then merging across parameter triples, then custom components.
4. **#203**, the recording wrapper.
5. Port `test_fragment_fuzz.py` as an engine test (hypothesis, `STARLAYER_FUZZ_EXAMPLES`).

## What this says about two lines

In nine days `main` gained these five issues, and each needs a re-implementation here, not a merge. That is the cost of two lines, measured; it
is input to `branch-decision-2026-11.md`. `main` also has none of the hunt fixes, so the work does not flow the other way either.

## After the port: SPARQL-based constraints and `sh:expression` in fragments

Checking the `sh:select` limit showed that `extract_subgraph` ignored `sh:sparql`, SPARQL-based components, `sh:expression` and `sh:nodeByExpression` altogether: a conforming node's fragment did not conform (2026-11-11). Fixed with the relevant-subgraph computation (`starlayer/sparql/relevant.py`) and `tests/shacl/integration/test_extract_subgraph_sparql.py`. `main` has the same gap (not checked there).
