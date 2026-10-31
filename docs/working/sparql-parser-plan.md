# A StarLayer-owned SPARQL 1.2 parser: study, prototype and estimate

Branch `sparql-parser` (a copy of `shacl-engine`). Prototype: `packages/starlayer/starlayer/sparql/parse_sparql.py`
(1,591 lines), tests `packages/starlayer/tests/sparql/test_parse_sparql.py` (+ `parse_sparql_support.py`).
All numbers below were measured on this branch unless marked "estimate".

## Part 1. The model

### A correction to the brief: SRL is not the model, Manchester (and Turtle) are

`srl.py` is **not** a hand-written parser. Its grammar is a pyparsing fragment (about 170 lines, `srl.py` 150-320)
spliced onto rdflib's SPARQL grammar: it imports `TriplesSameSubject`, `TriplesSameSubjectPath`, `Expression`,
`Constraint`, `iri`, `Var`, `String`, `BaseDecl`, `PrefixDecl` straight from `rdflib.plugins.sparql.parser`
(themselves extended in place by `_grammar12.install()`), adds the SRL-only productions (`RULE`, `DATA`, `NOT`, `SET`,
`IMPORTS`) and runs them through `parse_serialized`. Errors are pyparsing's `ParseException` text rewrapped in
`SRLParseError`. So SRL depends on exactly what we want to retire. Of the 153 SRL productions, the ones that are SPARQL's own
(expressions, builtins, terms, triple blocks, prologue) are rdflib's.

The hand-written model in the repo is `graph/parsers/manchester_parser.py`, so the prototype follows that.

| | Manchester (`manchester_parser.py`, 1,672 lines) | SRL (`srl.py` 1,073 + `_srl_ast.py` 477) | Turtle 1.2 (`turtle_parser.py` 1,307 + `syntax.py` 847 + `lexer.py` 313) |
|---|---|---|---|
| Grammar | hand-written recursive descent, one function per production (`_parse_description`, `_parse_restriction_tail`, ...) | pyparsing, spliced into rdflib's | hand-written, but string-splitting: `split_statements` cuts the document at `.`, `lexer.next_token` peels tokens off a statement string |
| Lexer | `_tokenize` (120 lines): one pass, token dicts `{kind, text, line}`, kinds IRI/LITERAL/WORD/PUNCT | pyparsing | `next_token(s)`: no positions, no token kinds |
| Parser state | `_Cursor` (token list, `peek`/`advance`/`expect_punct`, prefix map, bnode minting) | n/a | `_Expander`, per-statement |
| Output | RDF triples directly (`list[tuple]`); a `manch:` tree is built elsewhere (`starontology`) | `RuleSet` dataclasses (`_srl_ast.py`), then `srl:` RDF | rdflib triples |
| Errors | `ManchesterSyntaxError(why, text, pos, line)` from `cur.error()` / `err()` in the tokenizer; `run_guarded` turns `RecursionError` into a syntax error | `SRLParseError(str(pyparsing exception))`, no structured position | `Turtle12SyntaxError(why, text, pos, line)` |
| Conformance | `tests/starontology/manchester_conformance` (1,359 tests collected, opt-in): coverage matrix over the vendored `owl2-manchester-productions.json`, corpus, negative, differential against the OWL API, generated, tree, shape mutation; gap analysis doc | `tests/sparql/srl_conformance` (929 tests collected, opt-in; the brief says 991): coverage matrix over the vendored `sparql12-rl-productions.json` (**153** productions, section 7.6, with a checked SHA-256), 13 spec examples, builtin table, negative, an independent evaluator, shape mutation (`tools/mutation_scan.py`) | W3C `rdf-tests` Turtle suites |

How the SRL suite uses production numbers: `vendor/sparql12-rl-productions.json` holds every `[n] Name ::= body`
row; `test_sr_coverage_matrix.py` fails if any production is not exercised by `corpus.py`. That table-driven
"every production is hit by some case" gate is the part of SRL's method worth copying. Manchester's equivalent
is `grammar.py` + `test_mc_coverage_matrix.py`. No official SRL test suite exists, which is why SRL needs the evaluator
and the mutation scan; SPARQL has the W3C suite, so the gate is simpler (Part 3).

### What exists for SPARQL today

* `_grammar12.py` (932 lines): splices RDF 1.2 productions (triple terms, reifiers, annotations, `LANGDIR`,
  `STRLANGDIR`, `isTRIPLE` ...) into rdflib's pyparsing objects *in place*; `install()` is idempotent and
  import-order sensitive (`sparql/CLAUDE.md`, "Import order matters"). `parse12.py` (341) re-verifies and
  recovers when another import has un-patched the grammar; `_syntax_checks.py` (199) adds rules rdflib never
  enforces (surrogate escapes, scope, VALUES triple terms) by walking the parse tree.
* The rdflib tree is then encoded to `sqe:` by `sqe/to_rdf.py` (523) using rdflib's `translatePName`,
  `translatePath`, `triples()` (which calls `reorderTriples`, see Part 2) and the shared `to_rdf._encode`.
* Reusable from Turtle: very little. `lexer.py` works on a pre-split statement string without positions or token
  kinds, and cannot lex `?x`, operators, keywords or `<` as less-than. Reused in the prototype: `_join` (RFC 3986
  resolution that keeps an empty fragment). The Turtle *term* rules (what may be a triple-term subject, reifier
  forms) were reused as knowledge, not code.

### How much of SPARQL 1.2 Query does `srl.py` implement?

The SPARQL 1.2 Query grammar (section 19.7, fetched) has **194** numbered productions: [159]-[194] (36) are
lexical terminals, [3]-[54] include the Update family (about 25 productions, estimate), `Reifier` is [70],
`VersionDecl` [7], `AnnotationBlock` [112], `ReifiedTriple` [116], `TripleTerm` [119]. SRL's own grammar covers the
rule-specific productions plus, by reuse, `Prologue`/`BaseDecl`/`PrefixDecl`/`VersionDecl`, triple blocks
with `;` `,` `[ ]` `( )`, reifiers and annotations, `Expression` down to `BuiltInCall` (minus ten functions it
bans: `BOUND`, `COALESCE`, `RAND`, hashes, `EXISTS`), and `/` `^` paths only. It has none of: `SELECT`/`ASK`/
`CONSTRUCT`/`DESCRIBE`, `WhereClause`, `GroupGraphPattern` and its members (`OPTIONAL`, `UNION`, `MINUS`, `GRAPH`,
`SERVICE`, `BIND`, `VALUES`, sub-select), aggregates, solution modifiers, `*+?|!` paths, Update. Roughly 60 of the 158 non-terminal
productions are shared; about 100 are not. Because SRL borrows its pieces from rdflib, none of this is reusable
as code; the new parser is the first implementation it could share.

## Part 2. What the tree is

**Decision: an in-memory AST with a deterministic one-way encoder to `sqe:` RDF**, not RDF built directly by the parser.
The AST is a single generic class `Node(kind, **fields)`, because the vocabulary is generic: `spexpr:`/`sqe:`
encode a node as `[] a ns:<kind> ; ns:<field> value`, so `Node("Builtin_STR", arg=...)` encodes without a
per-kind table. Terms (IRI, literal, variable, blank node) are rdflib terms. Why not RDF directly: a parser that
emits triples cannot be checked, rewritten, scope-validated or unit-tested without a graph; Manchester does emit
triples, but it has no editing tree, whereas SPARQL needs the scope checks (`_check_query`) on a tree. The
encoder is 230 lines (`_Encoder`), the AST 40.

Measured: the encoded tree of the new parser equals `sqe_parse_to_tree`'s on 263 of 263 queries both can read
(Part 3), validates against the `sqe:` shapes, and renders through the unchanged `sqe_tree_to_text`.

### Node kinds and the vocabulary they map to

| Construct | AST kind (fields) | sqe / spexpr term |
|---|---|---|
| Query forms | `SelectQuery`, `AskQuery`, `ConstructQuery` (projection, modifier, template, where, group_by, having, order_by, limit, offset, values, datasets, prologue) | `sqe:SelectQuery` / `AskQuery` / `ConstructQuery`, `sqe:Query`, `sqe:projection`, `selectAll`, `distinct`, `reduced`, `template`, `where` |
| Prologue | `("base", iri)`, `("prefix", label, iri)`, `("version", s)` | `sqe:base`, `sqe:prologuePrefix`/`PrefixBinding`/`prefixLabel`/`namespace`; **VERSION: none** |
| Triple pattern | `TriplePattern(s, p, o)` | `sqe:TriplePattern` (`subject`, `predicate`, `object`) |
| Path | `InvPath`, `SequencePath`, `AlternativePath`, `MulPath(path, mod)`, `NegatedPath(args)` | `spexpr:InvPath` ... `spexpr:mod` |
| Group members | `Optional`, `Minus`, `Graph`, `Union(alts)`, `Filter`, `Bind`, `Values`, `SubSelect` | `sqe:Optional`, `Minus`, `Graph`, `Union`/`alternatives`, `Filter`, `Bind`, `Values`/`vars`/`rows`/`undef`, `SubSelect` |
| Triple term, reified triple, annotation, reifier | `TripleTerm(subject, predicate, object)`; the shorthands expand to `TriplePattern(r, rdf:reifies, TripleTerm)` | `sqe:TripleTerm`; expanded form only |
| Expressions | `Builtin_*`, `Function`, `Aggregate_*`, `Relational/Additive/Multiplicative/ConditionalAnd/Or/Unary*Expression`, `Builtin_EXISTS`/`NOTEXISTS` | `spexpr:<same names>`; EXISTS becomes `sqe:Exists` (`negated`) |
| Solution modifiers | `GroupAs`, `OrderCondition(expr, desc)`, limit/offset literals | `sqe:groupBy`, `Alias`, `having`, `orderBy`, `OrderCondition`/`descending`, `limit`, `offset`, `sqe:values` |

### What sqe cannot express yet (the prototype raises or drops, never guesses)

1. **SPARQL Update** (all of it) and **DESCRIBE**: no vocabulary. `sqe` raises today.
2. **`FROM` / `FROM NAMED`** and **`SERVICE`**: parsed, but `sqe` has no terms, so the encoder raises `NotImplementedError`.
3. **`VERSION`**: parsed and kept in the AST; dropped by the encoder (the current path strips it before parsing).
4. **Lossy by design, same as today**: `;`/`,` lists, `[ ]`, `( )` collections, `a`, `{| |}`, `~`, `<< >>` and `CONSTRUCT WHERE` are stored expanded;
   `[]` and `_:x` are not told apart; prefixed names are resolved (the prologue is kept separately and its order is not);
   number lexical forms are typed literals; comments and layout are gone. A faithful editor would need a concrete
   layer (unexpanded shorthand, original order) the vocabulary does not have.
5. **The vocabulary carries rdflib's shape**: `op` as a plain string tagged `spexpr:PlainString`, `other` lists, an empty
   `distinct ()` list on aggregates, `Function` argument fields named `expr`. The new parser reproduces these to stay isomorphic; a cleaner
   vocabulary is a separate, breaking decision.
6. **Triple order inside a block is rdflib's, not the source's.** `algebra.triples` runs `reorderTriples`
   (a selectivity heuristic that breaks ties on random blank-node ids), so today's tree for `?s :p ?o {| :a :b |}`
   lists the annotation triples before the main triple. The new parser keeps source order. The comparison treats each
   run of adjacent patterns as a set. This is an improvement for an editor and a behaviour change for anything that
   read the old order.

## Part 3. Validation strategy

Local oracles (all found, counted):

| Suite | Where | Count | Use |
|---|---|---|---|
| W3C SPARQL 1.2 positive syntax + query-evaluation queries | `tests/sparql/w3c_sparql12/data` (index.tsv; a sibling copy in `tests/graph/w3c_sparql12`) | 167 `.rq` | must parse |
| W3C SPARQL 1.2 negative syntax | same | 81 `.rq` (63 triple-term, 9 codepoint, 5 syntax, 3 version, 1 langdir) | must be rejected |
| W3C update syntax / eval | same | 18 + 3 positive, 2 negative `.ru` | not covered by the prototype |
| sqe feature and modifier queries | `tests/sparql/sqe_coverage/test_sqe_features.py`, `test_sqe_modifiers.py` | 89 + 12 | agreement with the current path |
| sqe generated queries | `test_sqe_property_based.py` (`_QUERIES`) | hypothesis (60 per run by default) | agreement + Oxigraph differential |
| sqe through W3C | `test_w3c_through_sqe.py` | 167 entries, 6 known gaps in `sqe_known_gaps.txt` | round trip, executes evaluation fixtures |
| Oxigraph differential | `test_oxigraph_differential.py` (needs `pyoxigraph`, **not installed here**) | 3 properties | sqe text vs Oxigraph |

**There is no SPARQL 1.1 syntax suite locally** (`rdf-tests/sparql/sparql11/data-sparql11` is not vendored; the
downloader handles only `sparql12`). That is the largest hole in the gate: the 1.1 positive/negative syntax tests (several hundred) are
where rdflib's gaps live. Fetching them is the first task of the full build.

How to use them as a gate: (1) positive must parse, negative must raise `SparqlSyntaxError`, as strict lists with a
known-gaps file in the style of `sqe_known_gaps.txt`; (2) tree -> `sqe_tree_to_text` -> parse again gives the same tree
(fixpoint); (3) **agreement with the current path**: `sqe_parse_to_tree(text)` and the new `sparql_to_tree(text)` compared with
`rdflib.compare.isomorphic` after turning each run of triple patterns into an unordered set (`canonical_graph`
in `parse_sparql_support.py`); (4) once `pyoxigraph` is available, run the rendered text on Oxigraph and the original
text on the current path and compare as sets (`test_sqe_text_agrees_with_oxigraph` already does this per query),
and run the W3C evaluation fixtures through the new text. Note that (3) costs about 1 s per query on the old
side because `sqe_parse_to_tree` validates with SHACL, so it is opt-in (`--sqe-coverage`).

## Part 4. The prototype

`parse_sparql.py`, 1,591 lines: tokenizer (about 80 lines, one master regex with named groups, tokens carry `pos`;
`SparqlSyntaxError` carries `pos`, `line`, `col`), `Node`, `_Parser` (one method per production), static checks
(`_check_query`, about 140 lines: duplicate projection, BIND/alias scope, nested aggregates, ungrouped projection, `SELECT *` with
GROUP BY), `_Encoder` to `sqe:` RDF. Entry points `parse_sparql(text, base) -> Node`, `sparql_to_tree(text, base)`.
Covered: BASE/PREFIX/VERSION; SELECT (DISTINCT/REDUCED, `*`, `(expr AS ?v)`), ASK, CONSTRUCT (and `CONSTRUCT WHERE`),
FROM (parsed); BGPs with `;` `,` `[ ]` `( )`, `<<( )>>`, `<< >>`, `~`, `{| |}`; property paths;
OPTIONAL, UNION, MINUS, GRAPH, SERVICE (parsed), FILTER, BIND, VALUES (inline and trailing, including triple-term
data), sub-select; all builtins of the 1.2 list incl. `TRIPLE`, `SUBJECT`, `LANGDIR`, `STRLANGDIR`, `EXISTS`; aggregates;
GROUP BY / HAVING / ORDER BY / LIMIT / OFFSET. Not covered: DESCRIBE, Update.

Results (W3C data as vendored; `pytest tests/sparql/test_parse_sparql.py`: 438 tests pass in 21 s, plus the 268-case
opt-in agreement gate):

| Gate | Result |
|---|---|
| W3C positive syntax (query) | **167 / 167** parse |
| W3C negative syntax (query) | **81 / 81** rejected |
| Text fixpoint | **167 / 167** |
| Agreement with `sqe_parse_to_tree` (isomorphic, triple runs as sets), sqe features | **89 / 89** |
| ... sqe modifiers | **12 / 12** |
| ... W3C queries both can read | **162 / 162** |
| W3C queries the *current* parser rejects and the new one accepts | 5 (`not-not` `!!`; codepoint-esc-08, 09; `compound-tripleterm-subject`, `nested-tripleterm-02`) |
| Generated (hypothesis) queries | HYPOTHESIS_PLACEHOLDER |
| Speed (162 W3C queries) | parse only 0.9 ms/query against 18.7 ms for `parse_query_12`; parse + encode 3.4 ms against 28.0 ms |

Findings while building it:

* The W3C 1.2 tests disagree with the old suite notes: a triple term *is* allowed as a pattern subject
  (`basic-tripleterm-01`) and as the subject of a nested triple term in a pattern, but not in `VALUES` or an expression.
  `known_gaps` called three of these "suite errors"; they are grammar facts the new parser follows.
* SPARQL 1.2 does not pre-process `\u` escapes over the whole query (`codepoint-esc-01-bad`, `-03-bad` are negative;
  `-08`, `-09` positive): escapes are decoded inside strings and IRIs only. The pre-pass rdflib does is wrong for 1.2, and a good reason to own the lexer.
* `!!x` is valid 1.2 (`UnaryExpression ::= '!' UnaryExpression`).
* Group scope: `SELECT (123 AS ?z) ... GROUP BY ?s` is legal when `?z` is in the pattern but not grouped.
* Not done: blank-node-label reuse across BGPs, `BIND` scope inside `OPTIONAL`/`UNION` arms, aggregate use in non-aggregate queries, IRI/number
  validity edge cases; these have no fixture among the 248 above.

## Part 5. Estimate and feasibility

**A StarLayer-owned parser is feasible**, and for the query half it is mostly done: 1,591 lines buys full agreement
with the current tree on every query both can read, plus 5 it cannot, at about 20 times the speed. What remains:

| Item | Estimate |
|---|---|
| Update grammar (about 25 productions: LOAD/CLEAR/DROP/CREATE/ADD/MOVE/COPY, INSERT/DELETE DATA, DELETE WHERE, Modify with USING/WITH, Quads) | 350 lines parser, plus the `sqe:` update vocabulary (about 20 terms), shapes and encoder (200-300 lines); W3C: 18+3+2 local `.ru` |
| DESCRIBE, SERVICE/FROM vocabulary | 30 lines parser, 5 vocabulary terms |
| Remaining semantic rules (bnode-label scope, BIND scope in nested groups, aggregate placement, update-specific rules: no bnodes in DELETE, no variables in DATA) | 150-250 lines |
| Fetch and wire the SPARQL 1.1 syntax suite (positive/negative query and update) as a gate | download script (fork of `download_w3c_sparql12_tests.py`, about 270 lines) + test glue 100 lines; the real work is triaging the failures |
| Production coverage matrix (vendor the 194 productions as JSON, SRL style) | about 100 lines + a corpus |
| SRL on the new parser (`srl.py` 150-320 becomes a subclass of `_Parser`) | net deletion of about 170 lines of pyparsing; the 929-test SRL suite is the gate |
| Total new code | roughly 1,000-1,400 lines, so about 2,600-3,000 lines of parser, against the 1,472 lines of grammar + checks + sqe encoder it replaces |

Calendar: about 2-3 working weeks for query-complete with gates, 4-5 with Update, 1.1 suite triage and the SRL port (estimate).

### What it could retire (lines measured; "users" = importers found by grep)

| File | Lines | Fate |
|---|---|---|
| `sparql/_grammar12.py` | 932 | retire after SRL moves; users: `parse12`, `lower_rdf11`, `serialize12`, `srl.py` |
| `sparql/parse12.py` | 341 | retire; users: `srl.py`, `star_query.py`, `serialize12`, `from_ast_rdf`, `ssyn_to_text`, `lower_rdf11`, `sparql/__init__` (import-order hack goes with it) |
| `sparql/_syntax_checks.py` | 199 | retire (replaced by `_check_query`); user: `parse12` only |
| `sparql/sqe/to_rdf.py` | 523 | shrinks to the error classes + shared encode glue; it calls `parse_query_12` |
| `sparql/lower_rdf11.py` | 1,971 | **only if execution moves to Oxigraph text**; users: `starlayer_graph`, `starlayer_dataset`, `native.py`, `query_cache`, `srl_eval` |
| `sparql/serialize12.py` | 542 | same condition; also used by `sqe/to_text.py`, `sqe/expr_text.py`, `algebra_translator_patches.py` (so not free) |
| `graph/query/query_cache.py` | 172 | same condition (caches lowered queries) |
| `graph/query/*_patches.py` (about 4,800 lines) | | rdflib evaluation patches: retire only with the evaluator, not with the parser |
| `to_rdf.py` / `from_rdf.py` / `salg/` | 508 / 599 | the salg export; per the decision not kept, but `sqe` and `srl` still import `_encode`/`_decode`; port first |

So the parser alone retires about 1,470 lines now (grammar, parse12, syntax checks) plus the rdflib import-order hazard; the
2,700-plus lines of lowering/serialising only go if Oxigraph executes.

### Risks

1. **The gate is thin without the SPARQL 1.1 suite.** 248 query fixtures agree, but the 1.1 syntax corners (`PN_LOCAL` escapes, numeric edge cases, `GROUP BY` forms, comments in odd places, nested sub-select scope) are untested. Do not delete anything before that suite passes.
2. **sqe is shaped by rdflib** (items 4-6 above). Matching it keeps both paths isomorphic but cements rdflib's quirks, and the order of triples changes for anyone who relied on it.
3. **The static semantic rules are where rdflib was weakest** and where hand-written parsers are usually wrong (scope, aggregates). The prototype has a subset; each missed rule is a silent false accept. Negative fixtures exist for few of them.
4. **Dependents are not isolated.** `srl.py` imports the grammar, `sqe_tree_to_query` and `lower_rdf11` need rdflib algebra shapes, and `serialize12` is used by `sqe/to_text`. Retirement is a sequence, not a deletion.
5. **Update and Oxigraph are separate decisions**: the update half has no sqe vocabulary; if Oxigraph runs updates as text, the parser may only need to *validate* them.
6. **Recursion and pathological input**: guarded by catching `RecursionError`; no fuzz run beyond the hypothesis queries.
