# SRL completeness suite

Answers: **how solid are the SRL (SPARQL Rules) parser, the `srl:` graph syntax and the text renderer?**
Mirrors `tests/starontology/manchester_conformance/`. Target: the W3C Working Draft *SPARQL 1.2 RL*, 14 October
2026 (https://www.w3.org/TR/sparql12-rl/), the draft `srl.py` is implemented against.

**Status: Part A (find the gaps) is in progress. No library code has been changed.** Every gap is a strict xfail
in `known_failures.py` that flips to a failing XPASS the moment it is fixed.

## What it checks

| File | Property | Oracle |
|---|---|---|
| `test_sr_coverage_matrix.py` | all 153 grammar productions are exercised by the corpus | the draft's grammar table, `vendor/` |
| `test_sr_corpus.py` | each case parses; renders to text that re-parses to a fixpoint; **keeps its meaning** (every FILTER/SET expression evaluates the same before and after); the `srl:` tree validates and decodes to the same text | the draft; rdflib's expression evaluator |
| `test_sr_spec_examples.py` | the draft's 13 code examples parse, plan (stratify), round-trip and keep their meaning | the draft |
| `test_sr_builtins.py` | 70 SPARQL functions: those in SRL's `BuiltInCall` parse and encode; those that are not are rejected | the draft's `BuiltInCall` production |
| `test_sr_negative.py` | ill-formed SRL is refused: grammar errors, SPARQL-only constructs, section 4.2 well-formedness, non-stratifiable sets | the draft |

Marker: `srl_conformance`. The corpus tests take about 10 minutes (each `parse_ruleset` runs SHACL validation
by default, about 140 ms); parses are cached across tests.

## Where there is no oracle

Manchester had the OWL API. For SRL there is no official test suite (w3c/rdf-tests has no rules category) and no
second implementation we can run. The oracles are therefore: the draft itself (grammar, examples, the spec's
own BuiltInCall list), rdflib's evaluator for expressions, and round-trip *meaning preservation* (evaluate
before and after). An independent naive evaluator for rule semantics is the next step (see below).

## Findings so far

The parser is tighter than the Manchester one was: trailing garbage is rejected, and `OPTIONAL`, `UNION`,
`GRAPH`, `VALUES`, `BIND`, subselects, `MINUS`, `SERVICE`, `*`/`+`/`?`/`|`/`!` paths and head filters are all
refused. The weaknesses are in the **text renderer**, in a few lexical corners, and in what leaks through from
rdflib's SPARQL grammar.

| Code | Finding | Severity |
|---|---|---|
| S3 | **Parentheses are dropped when rendering to text**: `(?y + 1) * 2` comes back as `?y + 1 * 2`, which parses and means something else | **High: silent change of meaning** |
| S1 | Function calls render as the placeholder `{Function}` (`xsd:integer(...)`, `:f(...)`): **the draft's own Examples 9 and 10 cannot round-trip** | High |
| S2 | Unary `+`/`-` render as `{UnaryPlus}`/`{UnaryMinus}` | Medium |
| S6 | A triple term inside an expression renders as `{TripleTerm}` | Medium |
| S4 | `IN ()` renders as `IN <rdf:nil>` (the tree path gets it right) | Low |
| S5 | `BNODE()` cannot be rendered or encoded (`ExpressionNotCoveredException`) | Medium |
| P1 | A bare reifier `<< ?x :q ?y ~ >>` is rejected, though the grammar allows it | Medium |
| P2 | String escape `\'` rejected; **unicode escapes `\uXXXX` / `\UXXXXXXXX` in strings rejected** | Medium |
| P3 | **Negative decimals unusable**: `-1.5`, `-0.5` raise "Not a number" | High |
| P4 | `PN_LOCAL_ESC` not decoded: `:a\-b` becomes an invalid IRI with a backslash | Medium |
| L1 | A missing `.` between triples is accepted (`?x :a ?y ?y :b ?z` read as two triples) | Low |
| L2 | **Ten SPARQL functions the grammar excludes are accepted**: `BOUND`, `COALESCE`, `RAND`, `MD5`, `SHA1`, `SHA256`, `SHA384`, `SHA512`, `EXISTS`, `NOT EXISTS` (`RAND` is non-deterministic, which a fixpoint evaluation cannot allow; `EXISTS` has no defined meaning in a rule) | Medium |
| T1 | `TRIPLE(s, p, o)` is in the spec's `BuiltInCall` but the resulting tree does not conform to the shapes | Medium |
| V1 | An undeclared prefix is rejected with a bare `Exception`, not an `SRLParseError` | Low |

All of S1 to S6 and T1 are in **machinery shared with `salg:`**: the expression renderer
(`ssyn_to_text._render_expr_text`) and the expression encoder. That bears on the architecture rule that SRL
should rely on `sqe:` and not on `salg:`: SRL cannot fix these without owning its expression rendering and
encoding, or waiting for `sqe:` to provide them.

### Not defects (corpus mistakes I made and corrected)

A triple term in subject position is rejected by section 4.2, correctly; several cases had unbound variables.
Spec Examples 19 and 39 differ between the tree and text paths only in parser-minted blank-node labels, which
the tests now canonicalise.

## Next

1. **Shape mutation analysis** of `srl_shapes.ttl` (reuse the Manchester `mutation_scan.py`). A 48-mutant probe
   already found 5 mutants that validate but crash the decoder (`ExpressionNotCoveredException`).
2. **Independent evaluator oracle**: a small naive stratified-Datalog evaluator in the test code, and a
   Hypothesis generator of rule sets and graphs, compared with `RuleSet.infer()`.
3. **Architecture test**: SRL must not reference `salg:`; the inventory is the strict-xfail list of today's
   references.
4. Part B: fix the findings above, starting with S3 (silent change of meaning) and P3.
