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

## 3. A `BIND` read through an earlier `BIND`, inside `UNION`, gives wrong/duplicate rows

```python
from rdflib import Graph
g = Graph()
g.parse(data="@prefix : <http://ex/> . :s0 :p :vX . :s1 :p :v1 . :s2 :p :v2 .", format="turtle")

list(g.query("""PREFIX : <http://ex/>
SELECT ?s WHERE {
  BIND(:v1 AS ?t0) . BIND(:v2 AS ?t1) .
  { { BIND(?t0 AS ?o) } UNION { BIND(?t1 AS ?o) } }
  ?s :p ?o .
}"""))
# actual:   [(:s2,), (:s0,), (:s1,), (:s2,), (:s0,), (:s1,)]   - 6 rows, :s0 shouldn't match, duplicates
# expected: [(:s1,), (:s2,)]

# same query with :v1/:v2 written directly inside the UNION (no hoisted BIND):
list(g.query("""PREFIX : <http://ex/>
SELECT ?s WHERE {
  { { BIND(:v1 AS ?o) } UNION { BIND(:v2 AS ?o) } }
  ?s :p ?o .
}"""))
# -> [(:s1,), (:s2,)]  - correct
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_evalextend_forgotten_bind_vars`.

## 4. A `BIND` inside one branch of a join can silently lose its value

A `BIND` whose expression needs a variable from *another* branch of the same (implicit or explicit) join is evaluated before that other branch runs, so the variable it needs is unbound. rdflib treats an unbound-variable error inside a `BIND` the same way it treats any failed `BIND` (leave the target unbound, don't abort) - so this doesn't raise anywhere. It just silently produces a row missing that binding, which then fails any `FILTER` that depends on it, and the query returns nothing instead of a real match.

```python
from rdflib import Graph
list(Graph().query("
SELECT ?t {
  FILTER(?a0 = 1)
  {
    BIND(?t + 0 AS ?a0)
    {
      BIND(1 AS ?t)
    }
  }
}"))
# actual:   []
# expected: [(Literal(1, datatype=xsd:integer),)]
```

Fix: `starlayer/graph/query/evaluate_patches.py::patch_lazy_join_expr_dependency_order`.

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


## 19. A negative decimal literal is a parse error

`-1.5` (`DECIMAL_NEGATIVE`, SPARQL 1.1 grammar [153]) raises "Not a number"; `-1` and `-1e3` work. The parse action negates with `Literal(-literal, datatype=...)`.

```python
from rdflib.plugins.sparql import prepareQuery
prepareQuery("SELECT * WHERE { ?s ?p -1.5 }")
# actual:   Exception: Not a number; Literal('1.5', datatype=xsd:decimal)
# expected: parses, the object is "-1.5"^^xsd:decimal
```

Fix: `starlayer/sparql/_grammar12.py::_fix_rdflib_lexical_gaps` replaces the parse action. Found by the SRL conformance suite (rdflib 7.6.0).

## 20. `\'` is rejected in a double-quoted string, and `\"` in a single-quoted one

ECHAR (grammar [160]) is `\` followed by one of `t b n r f " ' \`, in every string form. rdflib's `STRING_LITERAL1`/`STRING_LITERAL2` regexes allow only `\'` in the first and `\"` in the second.

```python
prepareQuery("""SELECT * WHERE { ?s ?p "a\\'b" }""")
# actual:   ParseException: Expected SelectQuery
# expected: parses, the object is "a'b"
```

Fix: same function, widens both regexes. Found by the SRL conformance suite.

## 21. `PN_LOCAL_ESC` keeps its backslash

In a prefixed name, `\-`, `\.` and the other `PN_LOCAL_ESC` escapes (grammar [173]) stand for the escaped character. rdflib leaves the backslash in the local name, giving the IRI `http://e/a\-b`, which it then warns "does not look like a valid URI".

```python
prepareQuery("PREFIX : <http://e/> SELECT * WHERE { :a\\-b ?p ?o }")
# actual:   subject <http://e/a\-b>
# expected: <http://e/a-b>
```

Fix: same function, strips the backslash in a parse action on `PN_LOCAL`. Found by the SRL conformance suite.
