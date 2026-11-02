# SRL completeness suite

Answers: **how solid are the SRL (SPARQL Rules) parser, the `srl:` graph syntax and the text renderer?**
Mirrors `tests/starontology/manchester_conformance/`. Target: the W3C Working Draft *SPARQL 1.2 RL*, 14 October
2026 (https://www.w3.org/TR/sparql12-rl/), the draft `srl.py` is implemented against.

**Status: Part A (find the gaps) done; Part B largely done.** On 2026-10-19 `srl.py` (only) was wired onto `sqe:`/`spexpr:`,
which closed findings S1 to S6, T1 and the `salg:` dependency; the same day P1 to P4, L1, L2 and V1 were fixed (see "Closed" below). Every remaining gap is a strict
xfail in `known_failures.py` that flips to a failing XPASS the moment it is fixed.

## What it checks

| File | Property | Oracle |
|---|---|---|
| `test_sr_coverage_matrix.py` | all 153 grammar productions are exercised by the corpus | the draft's grammar table, `vendor/` |
| `test_sr_corpus.py` | each case parses; renders to text that re-parses to a fixpoint; **keeps its meaning** (every FILTER/SET expression evaluates the same before and after); the `srl:` tree validates and decodes to the same text | the draft; rdflib's expression evaluator |
| `test_sr_spec_examples.py` | the draft's 13 code examples parse, plan (stratify), round-trip and keep their meaning | the draft |
| `test_sr_builtins.py` | 70 SPARQL functions: those in SRL's `BuiltInCall` parse and encode; those that are not are rejected | the draft's `BuiltInCall` production |
| `test_sr_negative.py` | ill-formed SRL is refused: grammar errors, SPARQL-only constructs, section 4.2 well-formedness, non-stratifiable sets | the draft |
| `test_sr_evaluator.py` | `RuleSet.infer()` equals an independent evaluator written from the draft's section 6.4/6.5 pseudocode: hand-derived known answers, plus Hypothesis-generated rule sets and graphs | the draft's pseudocode |
| `test_sr_architecture.py` | SRL does not depend on `salg:`: published shapes, trees, validation graphs and `srl.py` are salg-free, and the published `.ttl` files validate SRL trees in a process that never imports starlayer | the architecture rule |
| `tools/mutation_scan.py` | (tool, not a test) damages `srl:` trees and checks whether the shapes reject them | mutation |

Marker: `srl_conformance`. **Opt-in**: left out of an ordinary run, including a bare `pytest`. Run it with
`pytest --srl-conformance`, `STARLAYER_SRL_CONFORMANCE=1 pytest`, or `pytest -m srl_conformance` (the same
mechanism as the Manchester suite; see `tests/conftest.py`). It takes about 10 minutes: each `parse_ruleset` runs
SHACL validation by default, about 140 ms, and parses are cached across tests.

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

## Shape mutation analysis: the `srl:` shapes are weak

`tools/mutation_scan.py` damages the `srl:` tree of every corpus case (remove a triple, swap a value for a
literal, add a second value, drop an `rdf:type`, break a list) once per distinct (node class, property,
operator): 153 mutants, about 3 minutes.

| Verdict | Mutants |
|---|---|
| rejected by `srl_validate` | **63 (41%)** |
| validates and still decodes | 63 |
| **validates yet crashes the decoder** | **27** |

For comparison the Manchester shapes rejected 95% and, after hardening, had no holes. The SRL shapes constrain
the rule, body and head structure; the **expression subtrees are barely constrained**:

- every one of the 27 holes is inside an expression (`ConditionalOrExpression`, `ConditionalAndExpression`,
  `RelationalExpression`, `AdditiveExpression`, `MultiplicativeExpression`, `UnaryNot`, `Builtin_*`): removing
  its `srl:expr`, an operand, an operator or its type passes validation, then the decoder raises
  `ExpressionNotCoveredException`, `TypeError` or `IndexError`;
- many survivors are semantically wrong, not merely optional: a function node whose IRI is replaced by a
  literal, a `RelationalExpression` whose operator is replaced by the string "MUTANT", an extra second operand;
- a tree with its `srl:RuleSet` type removed still validates (same RDFS-inference cause as Manchester);
- those expression shapes are the shared `salg:ExpressionShape` family, which is why this cannot be fixed inside
  SRL without either owning the expression shapes or waiting for `sqe:` to provide them.

## Independent evaluator: no disagreement found

`test_sr_evaluator.py` contains an evaluator that shares no code with the implementation (plain Python sets, its
own matcher and expression evaluator), following the draft's section 6.4 `evalRuleElements` / `evalRule` and
6.5 stratum-by-stratum evaluation line by line. Scope: positive and negated triple patterns, `FILTER` and `SET`
over integers, `DATA` blocks, `WHERE DATA` / `NOT DATA`, recursion and stratified negation. Out of scope:
blank nodes in heads (run-once rules), triple terms, aggregation (undecided in the draft), imports.

The oracle is grounded without the implementation: it reproduces the draft's worked example (section 6.6) and the
`G0`-only rule for `WHERE DATA`. Against `RuleSet.infer()`: **no disagreement in 3,000 unseeded generated cases**
(recursive chains, mutual recursion, negation, `NOT DATA`, `SET`, `DATA` blocks), nor in four hand-derived known
answers (transitive closure, `WHERE DATA`, `NOT` against `NOT DATA`, `DATA` blocks). So the stratifier and
evaluator are consistent with the draft's pseudocode on this subset.

**How much does a passing comparison prove?** I checked, by deliberately breaking the oracle five ways (`WHERE
DATA` matching the evaluation graph; `NOT DATA` ignored; no fixpoint within a stratum; errors keeping the
solution; `DATA` not added to the evaluation graph). The first version of the generated test caught only one:
random rule sets almost never contain a recursive join needing several passes, and 60 examples rarely hit
`WHERE DATA`. Fixes: a generator that builds recursive chains, and the deterministic known-answer tests. All
five mutations are now caught. Lesson recorded for the other suites: a generated comparison should be
mutation-tested before it is trusted.

## Architecture: SRL and `salg:`

The rule is that SRL may rely on `sqe:` but not on `salg:`. Measured (2026-10-19), and enforced by
`test_sr_architecture.py`:

| Where | Finding | Test |
|---|---|---|
| the `srl:` trees SRL produces | only four `salg:` terms: `TripleTerm`, `subject`, `predicate`, `object` (triple terms). Everything else is `srl:` or `spexpr:` | strict xfail |
| the graphs SRL validates against | `srl_validate` loads the **whole** `salg:` ontology (290 triples) and shapes (617), because the expression shapes it reuses live there; SRL's own `srl:` terms are 30 and 111 | strict xfail |
| source | `srl.py` loads `sparql_owl`/`sparql_shacl` by name; `ast_vocab.py`, `srl_shapes.ttl`, `srl-ontology.ttl` name `salg:` | strict xfail |
| the expression vocabulary `spexpr:` | **already free of `salg:` IRIs** (text mentions are comments and prefixes only). An earlier count of 39 was a text search and over-stated it. | passing guard |

So the dependency is narrower than it looked: SRL's data is almost entirely independent, and the real coupling
is the shared expression *shapes and renderer* (the same machinery behind findings S1 to S6, T1 and the
shape holes above). Moving SRL onto `sqe:` means `sqe:` supplying expression shapes, an encoder and a
renderer without `salg:`; the SQE work is the prerequisite, not a parallel task.

## Closed on 2026-10-19: SRL wired onto `sqe:`/`spexpr:`

Change confined to `srl.py`. Expressions are encoded with sqe's encoder (after `simplifyFilters`, so the AST holds the
canonical form), rendered with sqe's `expr_text`, triple terms use `sqe:TripleTerm`, and validation loads
`spexpr` + `srl` + `sqe` shapes only. Results: S1 to S6 and T1 fixed (spec Examples 9 and 10 now round-trip); no
`salg:` term in trees, validation graphs or `srl.py`; 145 of 145 trees validate with plain rdflib + pyshacl using only
the published `.ttl` files.

New findings from the wiring:

| Code | Finding |
|---|---|
| V2 | A zero-argument function call (`FILTER :f()`) fails `spexpr:_FunctionExprBodyShape` (requires an argument list and `distinct`). Shared spexpr defect: sqe rejects it too. |
| V3 | An aggregate inside `SET` is no longer rejected by the shapes (the shared spexpr shapes accept aggregates); `parse_ruleset` still rejects it in Python. Needs a constraint in `srl_shapes.ttl` (strict xfail in `tests/sparql/unit/test_srl_shapes.py`). |

Later the same day: L1 (a `.` is now required between triple groups), L2 (the ten non-SRL functions are rejected),
V1 (`SRLParseError` for an undeclared prefix), P2b (unicode escapes: `parse_ruleset` now runs rdflib's
`expandUnicodeEscapes` like `parseQuery` does), tabs inside string literals (pyparsing expanded them) and P1 (bare
`~`, in `_grammar12.py`). P2 (`\'`), P3 (negative decimals) and P4 (`PN_LOCAL_ESC`) are **rdflib defects** that fail
in plain `prepareQuery` too; they are patched in `_grammar12._fix_rdflib_lexical_gaps`, which changes parsing for all
of starlayer's SPARQL, and are items 19 to 21 in `docs/upstream-issues/rdflib-upstream-issues.md`. Regressions:
`tests/sparql/unit/test_lexical_gaps.py`. Only V2 and V3 remain.

The shape mutation scan predates the wiring and should be re-run against the new validation configuration.

## Next

Part B, in dependency order. (a) Fixes that live in SRL alone: the parser/lexer findings P1 to P4, V1 and the
leaks L1/L2 (reject the ten SPARQL-only functions, require the `.` between triples). (b) Fixes that live in the
shared expression machinery (S1 to S6, T1, the shape holes): a working copy under this suite, as with
Manchester, merged only after the SQE work is done. (c) An opt-in pre-flight on asserted types, and stronger
expression shapes, once (b) exists.
