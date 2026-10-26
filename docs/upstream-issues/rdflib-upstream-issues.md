# rdflib Upstream Issues

Bugs in rdflib 7.6.0 found while building SPARQL 1.2 support here. Every example is plain `rdflib` (do not `import starlayer.graph`, which applies the fixes). **None are filed upstream yet**; they will be reported as a batch. Each has a fix applied in this repo, in `starlayer/graph/query/*_patches.py`.

| # | Bug | Effect | Fix |
|---|-----|--------|-----|
| 1 | `*` ignores numeric type promotion | wrong datatype | `operator_patches` |
| 2 | `translateAlgebra` emits invalid SPARQL | crash / bad text | `algebra_translator_patches` |
| 3 | `BIND` read through earlier `BIND` in `UNION` | wrong, duplicate rows | `evaluate_patches` |
| 4 | `BIND` needing a sibling branch's variable | silently missing value | `evaluate_patches` |
| 5 | `GROUP BY (expr)` without `AS` | crash | `evaluate_patches` |
| 6 | `SELECT *` row with no variables | row lost on iteration | `result_patches` |
| 7 | `xsd:integer()` of decimal/double/boolean | error | `operator_patches` |
| 8 | `FILTER` loses a variable bound outside it | filter always false | `evaluate_patches` |
| 9 | `INSERT DATA` into a `Dataset` default graph | crash | `evaluate_patches` |
| 10 | `REPLACE` ignores its flags argument | wrong result | `custom_functions` |
| 11 | `STRLANG` accepts an empty language tag | should be an error | `operator_patches` |
| 12 | `CEIL`/`FLOOR`/`ROUND` of a decimal | non-canonical `"2"` | `operator_patches` |
| 13 | Invalid queries the parser accepts (nested aggregate, repeated `VALUES` variable, `GROUP BY` scope clash) | no syntax error | `sparql/_syntax_checks` (nested aggregate, `VALUES`, `GROUP BY`) |
| 14 | Codepoint and surrogate escapes accepted anywhere | no syntax error | `sparql/_syntax_checks` (surrogates only) |
| 15 | Simple literal differs from its `^^xsd:string` form | unequal terms | `operator_patches` (`sameTerm()` only) |

## 1. `MultiplicativeExpression` doesn't apply numeric type promotion for `*`

`xsd:integer * xsd:integer` should stay `xsd:integer`, the same rule `+` already follows. Always comes back `xsd:decimal`.

```python
from rdflib import Graph
list(Graph().query("SELECT (6 * 7 AS ?r) WHERE {}"))[0][0]
# actual:   Literal('42', datatype=xsd:decimal)
# expected: Literal('42', datatype=xsd:integer)
```

Fix: `starlayer/graph/query/operator_patches.py::patch_multiplicative_expression_type_promotion`.

## 2. `translateAlgebra` regenerates invalid or crashing SPARQL text

`translateAlgebra` (`rdflib.plugins.sparql.algebra`) is not documented/user-facing rdflib API (unlike `prepareQuery`) - only reachable via the auto-generated API listing. Regeneration only: direct execution of every query below is correct; only `prepareQuery` → `translateAlgebra` round-tripping breaks.

**a. A blank node chaining two triples together glues them into one unparseable token:**

```python
from rdflib import Graph
from rdflib.plugins.sparql.processor import prepareQuery
from rdflib.plugins.sparql.algebra import translateAlgebra

src = "SELECT * WHERE { ?s <http://ex/p1> _:x . _:x <http://ex/p2> _:y . _:y <http://ex/p3> ?o . }"
list(Graph().query(src))  # direct execution - fine, no data needed to see the regenerated text is broken

q = prepareQuery(src)
translateAlgebra(q)
# -> 'SELECT ?o ?s{_:x <http://ex/p2> _:y._:y <http://ex/p3> ?o.?s <http://ex/p1> _:x.}'
# '_:y._:y' - no separator between the two triples; ParseException on re-parse
```

**b. Multi-value `IN`/`NOT IN` crashes outright** (inverted `isinstance` guard):

```python
q = prepareQuery("SELECT * WHERE { FILTER(1 IN (1, 2)) }")
translateAlgebra(q)
# -> ExpressionNotCoveredException
```

**c. `SELECT *` over a fully-ground pattern drops the `*`:**

```python
q = prepareQuery("SELECT * WHERE { <http://example/a> <http://example/b> <http://example/c> . }")
translateAlgebra(q)
# -> 'SELECT {...}' - missing *; ParseException on re-parse
```

Also affects: two `UNION` branches each `BIND`ing the same variable name regenerate as `(expr1 AS (expr2 AS ?var))` - nested, invalid.

Fix: `starlayer/graph/query/algebra_translator_patches.py::patch_algebra_translator_bugs`.

## 5. Un-aliased computed `GROUP BY` key crashes

SPARQL 1.1's grammar for `GroupCondition` makes the alias optional: `'(' Expression ( 'AS' Var )? ')'` ([§19.8 Grammar, production `GroupCondition`](https://www.w3.org/TR/sparql11-query/#rGroupCondition)) - `GROUP BY (?o+1)`, with no `AS ?var`, is legal syntax distinct from both `GROUP BY ?o` and the aliased `GROUP BY (?o+1 AS ?k)`. rdflib crashes on exactly this one form.

```python
from rdflib import Graph, Namespace, Literal
g = Graph(); ex = Namespace("http://ex/")
g.add((ex.s, ex.p, Literal(1))); g.add((ex.s, ex.p, Literal(2)))
list(g.query("SELECT (COUNT(?o) as ?c) WHERE { ?s <http://ex/p> ?o } GROUP BY (?o+1)"))
# actual:   Exception: Cannot eval thing: None
# expected: 2 grouped rows (GROUP BY ?o and GROUP BY (?o+1 AS ?k) both work fine)
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key`.

## 6. A `SELECT` row with no variable bindings gets silently dropped when iterated

A `SELECT *` query whose pattern has no variables at all - "does this exact fact exist?" - produces one real row when it matches (no columns, since there's nothing to bind, but a row: the fact was found). Reading that result the normal way, by iterating it, can't tell that apart from the fact not existing at all - both print as nothing.

```python
from rdflib import Graph
g = Graph()
g.parse(data="<http://example/a> <http://example/b> <http://example/c> .", format="nt")

# fact exists:
r = g.query("SELECT * WHERE { <http://example/a> <http://example/b> <http://example/c> . }")
r.bindings, len(r), list(r)
# actual:   ([{}], 1, [])
# expected: ([{}], 1, [()])  - one row (an empty ResultRow, prints as ()), same as ASK on this pattern (True)

# fact does not exist, for contrast:
r2 = g.query("SELECT * WHERE { <http://example/a> <http://example/b> <http://example/nope> . }")
r2.bindings, len(r2), list(r2)
# -> ([], 0, [])  - genuinely zero rows; before the fix, indistinguishable from the "exists" case via list()
```

Fix: `starlayer/graph/query/result_patches.py::patch_result_iter_empty_binding_row`.

## 7. `xsd:integer()` cannot cast a decimal, double, float or boolean

rdflib 7.6.0 (the latest release). The `xsd:integer` cast (`rdflib.plugins.sparql.operators.default_cast`) is `int(<lexical form>)`, so any source whose lexical form is not already an integer is an evaluation error. SPARQL 1.1 §17.5 casts through the XPath constructor functions, where a number casts to `xsd:integer` by truncation toward zero and a boolean casts to 1 or 0. A string such as `"16.0934"` correctly stays an error.

```python
from rdflib import Graph

q = 'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\nSELECT (COALESCE(xsd:integer({}), "ERROR") AS ?r) WHERE {{}}'
for arg in ("16.0934", "-2.7", "1.5e0", "true"):
    print(arg, list(Graph().query(q.format(arg)))[0][0])
# actual:   ERROR for all four
# expected: 16, -2, 1, 1
```

Found because the SRL spec's own Examples 9 and 10 compute `xsd:integer(?miles * 1.60934)` and infer nothing without it. (Without the `COALESCE`, the row is silently dropped; see item 6.)

Fix: `starlayer/graph/query/operator_patches.py::patch_integer_cast_from_numeric_and_boolean`, applied on `import starlayer.graph`. `NaN` and the infinities stay errors. **Not filed upstream.**



## 8. `FILTER` forgets a variable bound outside its group

```python
from rdflib import Graph
list(Graph().query("SELECT ?x WHERE { BIND(1 AS ?o) { BIND(2 AS ?x) FILTER(?x = ?o + 1) } }"))
# actual:   []
# expected: [(Literal(2),)]
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_evalfilter_forgotten_vars`. (Revised 2026-10-18: the first version of this patch kept every variable the filter mentions, which also made it see variables bound outside its group - see item 16. It now evaluates the filter over the variables its own group binds.)

## 9. `INSERT DATA` into a `Dataset`'s default graph crashes

```python
from rdflib import Dataset
Dataset().update("INSERT DATA { <http://ex/a> <http://ex/b> <http://ex/c> }")
# actual:   ValueError: not enough values to unpack (expected 4, got 3)
# expected: one triple added (a plain Graph works)
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_evalinsertdata_quad_unpacking`.

## 10. `REPLACE` ignores its flags argument

```python
from rdflib import Graph
list(Graph().query('SELECT (REPLACE("aBc", "b", "X", "i") AS ?r) WHERE {}'))[0][0]
# actual:   'aBc'   (flags "i" not applied)
# expected: 'aXc'
```

Cause: rdflib calls `re.sub(pattern, repl, text, flags)`, but the fourth positional parameter of `re.sub` is `count`, not `flags`. Worked around in `starlayer/graph/query/custom_functions.py` (`_replace`).

## 11. `STRLANG` accepts an empty language tag

```python
from rdflib import Graph
list(Graph().query('SELECT (STRLANG("a", "") AS ?r) WHERE {}'))[0][0]
# actual:   Literal('a')   (a plain string)
# expected: an error, so ?r is unbound
```

Fix: `starlayer/graph/query/operator_patches.py::patch_strlang_rejects_empty_language_tag`.

## 12. `CEIL`, `FLOOR` and `ROUND` of a decimal give a non-canonical lexical form

```python
from rdflib import Graph
list(Graph().query("SELECT (CEIL(1.5) AS ?r) WHERE {}"))[0][0]
# actual:   Literal('2', datatype=xsd:decimal)
# expected: Literal('2.0', datatype=xsd:decimal)
```

Fix: `starlayer/graph/query/operator_patches.py::patch_decimal_result_lexical_form`.


## 13. Queries that break the grammar are accepted

Each should be a syntax error. rdflib runs them.

```python
from rdflib import Graph
g = Graph()
list(g.query("SELECT (COUNT(COUNT(*)) AS ?c) WHERE { ?s ?p ?o }"))  # nested aggregate
list(g.query("SELECT * WHERE { VALUES (?a ?a) { (1 2) } }"))         # variable repeated in one VALUES row
list(g.query("SELECT (1 AS ?s) WHERE { ?s ?p ?o } GROUP BY ?s"))     # SELECT alias reuses a GROUP BY key's name
# actual:   all three return rows
# expected: a parse error for each
```

Fix: `starlayer/sparql/_syntax_checks.py::check_parse_tree`, run by `parse_query_12`/`parse_update_12`. The `GROUP BY` check covers a `SELECT` alias that reuses a `GROUP BY` key's name, not an alias that clashes with a variable in the `WHERE` pattern.

## 14. Codepoint and surrogate escapes are accepted anywhere

SPARQL allows `\uXXXX` escapes only in certain tokens, and only for valid Unicode scalar values.

```python
list(Graph().query("\\u0053ELECT * WHERE {}"))      # the keyword SELECT spelled with an escape
list(Graph().query('SELECT * WHERE { ?s ?p "\\uD800" }'))  # lone surrogate
# actual:   both run
# expected: a parse error for each
```

Surrogate escapes are now rejected by `starlayer/sparql/_syntax_checks.py::reject_surrogate_escapes`. Still accepted, and tracked as xfail: a keyword spelled with an escape (`codepoint-esc-01-bad`) and an escape inside a prefixed name (`codepoint-esc-03-bad`).

## 15. A simple literal and its `^^xsd:string` form are different terms

RDF 1.1 and 1.2 Concepts define a simple literal as shorthand for the `xsd:string` literal, so they are the same term.

```python
from rdflib import Literal, XSD
Literal("foo") == Literal("foo", datatype=XSD.string)
# actual:   False   (so sameTerm("foo", "foo"^^xsd:string) is false)
# expected: True
```

Fix: `starlayer/graph/query/operator_patches.py::patch_sameterm_simple_literal_is_xsd_string` makes `sameTerm()` treat them as one term. `Literal.__eq__` and triple-pattern matching are unchanged, so `?s ?p "a"^^xsd:string` still does not match a stored `"a"`; fixing that means changing `Literal` itself.

## 16. A `FILTER` in a nested group sees variables bound outside the group

SPARQL evaluates a group on its own and joins it with its siblings afterwards, so a `FILTER` can only see variables bound inside its own group. rdflib passes the outer bindings in, so `BOUND()` is true and comparisons use values the group should not have. Oxigraph follows the spec.

```python
from rdflib import Graph
q = "SELECT ?x WHERE { BIND(1 AS ?o) { BIND(2 AS ?x) FILTER(!BOUND(?o)) } }"
list(Graph().query(q))
# actual:   []
# expected: [(Literal(2),)]   (Oxigraph returns it)
```

Found 2026-10-18 by the Oxigraph differential tests (`tests/sparql/sqe_coverage/test_oxigraph_differential.py`); it shows up in `UNION`, `MINUS` and `GRAPH` blocks too.

Fix: `evaluate_patches.py::patch_evalfilter_forgotten_vars` now evaluates a filter over the variables its group binds (a structural walk of the group's pattern), not over the solution it was handed. Three cases keep the wider view on purpose: a filter in an `EXISTS`/`NOT EXISTS` pattern (the spec substitutes the outer solution into it, found by looking for `Builtin_EXISTS` on the call stack), a filter the triple-term lowering wrote (it leaves a pattern variable only in the filter), and `OPTIONAL` (its filter belongs to the join, so rdflib already gets it right). Tests: `tests/graph/unit/test_filter_group_scope.py`.

## 17. An explicit `GROUP BY` over no solutions returns one empty row

Grouping an empty solution sequence by a key gives no groups, so no rows (SPARQL 1.1 section 11.2). Only the implicit single group, for aggregates with no `GROUP BY`, exists when empty (`COUNT` is then 0). rdflib's `evalAggregateJoin` ends with `if len(res) == 0: yield FrozenBindings(ctx)`, which only ever runs for the explicit case and adds a row.

```python
from rdflib import Graph
q = "SELECT ?n (COUNT(?n) AS ?c) { ?s <http://x/p> ?n } GROUP BY ?n"
Graph().query(q).bindings
# actual:   [{}]
# expected: []
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_aggregate_join_no_row_for_empty_explicit_group`. Found by the Oxigraph differential tests.

## 18. `CONSTRUCT` keeps template triples that are not valid RDF

A template triple that instantiates to a literal subject or a non-IRI predicate is left out of the result (SPARQL 1.1 section 16.2.1). rdflib keeps it.

```python
from rdflib import Graph, Literal, URIRef
g = Graph()
g.add((URIRef("http://x/a"), URIRef("http://x/n"), Literal(1)))
list(g.query("CONSTRUCT { ?n <http://x/p> ?n } WHERE { ?s <http://x/n> ?n }").graph)
# actual:   [(Literal(1), <http://x/p>, Literal(1))]
# expected: []
```

Fix: `evaluate_patches.py::patch_construct_skips_encoding_solutions` (the CONSTRUCT patch) now filters them. Found by the Oxigraph differential tests.

## 19. Update graph management acts on the union, not the default graph; `CREATE`, `DELETE WHERE GRAPH ?g` and `USING` are broken

On a `Dataset` (rdflib's update code uses `ctx.graph`, which is the union of all graphs when `default_union` is set):

```python
from rdflib import Dataset
d = Dataset(default_union=True)
d.update("INSERT DATA { GRAPH <http://e/g> { <http://e/z> <http://e/p> <http://e/z> } }")
d.update("CLEAR DEFAULT")      # also empties <http://e/g>
d.update("CREATE GRAPH <http://e/n>")                       # Exception: Create not implemented!
d.update("DELETE WHERE { GRAPH ?g { ?s ?p ?o } }")           # deletes nothing
d.update("INSERT { ?s ?p ?o } USING <http://e/g> WHERE { ?s ?p ?o }")  # tries to fetch http://e/g
```

`ADD`/`COPY`/`MOVE` with `DEFAULT` raise `ValueError` or lose data. SPARQL 1.1 Update section 3.2 defines each on the true default graph; section 3.1.3 says `USING` names a graph of the dataset. Found by the second hunt (GitHub issue #78).

Fix: `starlayer/graph/query/update_patches.py::patch_update_graph_management`.

## 20. A negated property set matches the triple-term encoding; `isIRI` and `STR` accept a triple term

On the rdf-1.1 representation a triple term is a `tt:` IRI described by internal triples. rdflib knows nothing about that, so `?x !(:p) ?y` returns the internal `rdf:propositionFormSubject` / `Predicate` / `Object` triples as data, `isIRI(?t)` is true for a triple term and `STR(?t)` returns the internal IRI text. SPARQL 1.2 makes the term kinds disjoint (17.4.2.3): `isIRI` is false for a triple term and `STR` of one is a type error. Found by the second hunt (GitHub issue #74). Also fixed: a pattern holding a triple term and an IRI as objects of the same subject and predicate crashed in rdflib's `reorderTriples` (`TripleTermNode` had no ordering against a `URIRef`).

Fix: `evaluate_patches.py::patch_negated_path_skips_encoding_triples`, `operator_patches.py::patch_triple_terms_are_not_iris`, `TripleTermNode.__lt__`/`__gt__` in `sparql/triple_term.py`.

## 21. `SUBSTR` with a start below 1 returns the wrong string

`SUBSTR` is defined as `fn:substring` (SPARQL 1.1 section 17.4.3.3): it keeps the characters at 1-based positions `p` with `start <= p < start + length`. rdflib slices with the raw index, so a start below 1 gives `""` or a Python negative-index slice. A non-integer start is a type error (the signature takes `xsd:integer`).

```python
from rdflib import Graph
list(Graph().query('SELECT (SUBSTR("abc", 0, 2) AS ?x) (SUBSTR("abc", -1, 3) AS ?y) {}'))
# actual:   ("", "")
# expected: ("a", "a")
```

Found by the second hunt (GitHub issue #76). Fix: `starlayer/graph/query/builtin_error_patches.py::patch_substr_xpath_semantics` (also replaces `operators.Builtin_SUBSTR`, which the directional-literal `SUBSTR` reuses).

## 22. `TIMEZONE()` drops the minutes of a UTC offset

```python
from rdflib import Graph
list(Graph().query('SELECT (TIMEZONE("2020-01-02T03:04:05-05:30"^^<http://www.w3.org/2001/XMLSchema#dateTime>) AS ?x) {}'))
# actual:   "-PT5H"^^xsd:dayTimeDuration
# expected: "-PT5H30M"^^xsd:dayTimeDuration
```

rdflib computes the minutes with Python 3 true division, so the value is a float and the `%dM` branch is never right. A zero offset should be `PT0S` (fn:timezone-from-dateTime); rdflib normalises the lexical form of a `dayTimeDuration` literal to `P0D` on construction, which is the same value and is left alone. Fix: `builtin_error_patches.py::patch_timezone_keeps_minutes`.

## 23. `IN`, `NOT IN`, `&&`, ordering across types and directional-literal tag case

Four separate errors in `RelationalExpression` / `ConditionalAndExpression` and `sameTerm`:

* `IN` and `NOT IN` compare terms: `1 IN (1.0, 2)` is false and `FILTER(?o NOT IN (1, 2))` keeps `1.0`. SPARQL 1.1 section 17.4.1.9 defines `IN` as a chain of `=` tests (value equality).
* An error among the list members is swallowed: `2 IN (1/0, 1)` is false; with no match and one error it is an error.
* `1/0 && false` is an error; the section 17.2 truth table gives false (error AND false = false).
* `"x" > 1` is true (rdflib sorts across types). The operator mapping (section 17.3) has no `<`/`>` between a string and a number, so it is a type error: `BIND` leaves the target unbound, `FILTER` drops the row.
* `sameTerm("a"@en--rtl, "a"@EN--rtl)` and `=` on the same are false; RDF 1.2 Concepts compares language tags case-insensitively. The directional literal keeps its tag inside a synthetic datatype IRI, so rdflib compares the case.

```python
from rdflib import Graph
list(Graph().query('SELECT (1 IN (1.0, 2) AS ?a) (2 IN (1/0, 1) AS ?b) ("x" > 1 AS ?c) {}'))
# actual:   (false, false, true)
# expected: (true, error/unbound, error/unbound)
```

Found by the second hunt (GitHub issue #76). Fix: `builtin_error_patches.py::patch_relational_operators_follow_spec`; the `sameTerm` part is in `operator_patches.py::patch_sameterm_simple_literal_is_xsd_string`.

## 24. `SUM` and `AVG` over non-numeric values abort the whole query

An error while evaluating an aggregate leaves that one value unbound (SPARQL 1.1 sections 17.2 and 18.5); a `HAVING` condition over it then drops only that group. `SUM` and `AVG` are defined through `op:numeric-add`, which errors on a non-numeric operand. rdflib raises `SPARQLTypeError` / `TypeError` out of `query()` for `SUM`, so every row of the query is lost, and `AVG` silently skips the value.

```python
from rdflib import Graph
g = Graph(); g.parse(data='<http://x/s> <http://x/p> 1, "a" .', format="turtle")
list(g.query("SELECT (SUM(?o) AS ?s) (COUNT(*) AS ?n) { ?x <http://x/p> ?o }"))
# actual:   SPARQLTypeError
# expected: [(unbound, 2)]
```

Found by the second hunt (GitHub issue #76). Fix: `builtin_error_patches.py::patch_sum_avg_errors_are_unbound`. `MIN`/`MAX` order any mix of types (section 18.5 uses the `ORDER BY` ordering) and are unchanged.

## 25. An empty `VALUES` block crashes

`VALUES ?a { }` and `VALUES () { () }` are legal (grammar rules InlineDataOneVar and InlineDataFull): no rows give no solutions; `()` rows over no variables each give one empty solution. rdflib's `translateValues` returns a bare `[]` instead of a `Values` node, so evaluation fails with `AttributeError: 'list' object has no attribute 'name'`.

```python
from rdflib import Graph
list(Graph().query("SELECT * WHERE { VALUES ?a { } }"))
# actual:   AttributeError
# expected: []
```

Fix: `builtin_error_patches.py::patch_empty_values_clause`, plus `sparql/from_rdf.py` (a no-variable row is an empty RDF list in the algebra encoding and decoded to `rdf:nil`).

## 26. `STRDT` accepts a non-IRI datatype; `STRLANG` with an invalid tag raises `ValueError`

`STRDT("a", 1)` builds a literal with datatype `<1>`; `STRDT` takes a simple literal or `xsd:string` and an IRI (section 17.4.2.8). `STRLANG("a", "e n")` raises `ValueError: 'e n' is not a valid language tag!` out of the evaluator and aborts the query; a function error must make the value unbound. `STRLANGDIR("a"@en, ...)` (StarLayer's own function) also accepted a language-tagged lexical form.

```python
from rdflib import Graph
list(Graph().query('SELECT (STRDT("a", 1) AS ?x) (COALESCE(STRLANG("a", "!!"), "f") AS ?y) {}'))
# actual:   a literal with datatype <1>, then ValueError
# expected: (unbound, "f")
```

Fix: `builtin_error_patches.py::patch_strdt_requires_string_and_iri`; the `STRLANG` part extends `operator_patches.py::patch_strlang_rejects_empty_language_tag`.

## 27. Ill-typed literals: `RecursionError`, `isNumeric` true, and `AttributeError` in `DAY()`/`YEAR()`

rdflib's `numeric()` returns the `Literal` itself when its value cannot be parsed (`"abc"^^xsd:integer`), so `+` recurses until `RecursionError` and `isNumeric` answers true. `datetime()`/`date()` do the same, so `DAY("x"^^xsd:dateTime)` dies with `AttributeError: 'Literal' object has no attribute 'day'`. An ill-typed literal is a type error (section 17.3); the expression is unbound and `COALESCE` skips it.

```python
from rdflib import Graph
list(Graph().query('SELECT ("abc"^^<http://www.w3.org/2001/XMLSchema#integer> + 1 AS ?x) {}'))
# actual:   RecursionError
# expected: unbound
```

Fix: `builtin_error_patches.py::patch_ill_typed_literals_are_errors`.

## 28. `SELECT *` lists variables that occur only in a `FILTER`; `DESCRIBE *` crashes

The in-scope variables of a group pattern (section 18.2.1) come from its patterns. rdflib collects every variable in the `WHERE` tree, so `SELECT * { ?s :p ?o FILTER EXISTS { ?o :p ?zz } }` has an always-unbound `?zz` column. `DESCRIBE *` fails with `TypeError: 'NoneType' object is not iterable` because the parser leaves the variable list empty; it describes the resources bound to the in-scope variables.

Fix: `builtin_error_patches.py::patch_select_star_scope_and_describe_star`.

## 29. `xsd:double` division by zero is an error instead of INF

`op:numeric-divide` on `xsd:double`/`xsd:float` never raises: `1e0/0` is `INF`, `-1e0/0` is `-INF`, `0e0/0` is `NaN`. Only integer and decimal division by zero is an error. rdflib computes through `Decimal`, so it errors for all of them. The special values also need their XSD lexical forms (`INF`, `-INF`, `NaN`); rdflib writes `inf`, `nan`, and `canonicalize_query_result_value` had turned those into `inf.0` and `nan.0`.

```python
from rdflib import Graph
list(Graph().query("SELECT (1e0/0 AS ?x) {}"))
# actual:   unbound
# expected: "INF"^^xsd:double
```

Fix: `operator_patches.py::patch_multiplicative_expression_type_promotion` (the division branch), `graph/model/encoding.py::_canonicalize_numeric_literal`.

## Withdrawn entries

Items 3 and 4 of this list were withdrawn on 2026-10-25 (GitHub issue #54). Both claimed that a `BIND` should see a variable bound in a sibling or enclosing group, and StarLayer patched rdflib (`patch_evalextend_forgotten_bind_vars`, `patch_lazy_join_expr_dependency_order`) to make it so. SPARQL 1.1 section 18.2.2.6 evaluates each group on its own and joins the results, so a `BIND` cannot see such a variable and plain rdflib was right. For example `SELECT * { VALUES ?x {1 2} { BIND(?x+1 AS ?y) } }` returns `?x` only, and `{ BIND(:v1 AS ?t0) { { BIND(?t0 AS ?o) } UNION { BIND(:v2 AS ?o) } } ?s :p ?o }` returns every `?s :p ?o` row once per union branch (six rows, not two). Both patches were removed; `tests/graph/unit/test_bind_scoping.py` pins the spec behaviour. The numbers 3 and 4 are not reused. Items 8 and 16 (`FILTER`) are the same question for filters and have not been re-examined.
