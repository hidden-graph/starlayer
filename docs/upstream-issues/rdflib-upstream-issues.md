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
| 11 | `STRLANG` accepts an empty language tag | should be an error | not yet patched |
| 12 | `CEIL`/`FLOOR`/`ROUND` of a decimal | non-canonical `"2"` | `operator_patches` |

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

Fix: `starlayer/graph/query/evaluate_patches.py::patch_evalfilter_forgotten_vars`.

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

Not yet patched here.

## 12. `CEIL`, `FLOOR` and `ROUND` of a decimal give a non-canonical lexical form

```python
from rdflib import Graph
list(Graph().query("SELECT (CEIL(1.5) AS ?r) WHERE {}"))[0][0]
# actual:   Literal('2', datatype=xsd:decimal)
# expected: Literal('2.0', datatype=xsd:decimal)
```

Fix: `starlayer/graph/query/operator_patches.py::patch_decimal_result_lexical_form`.
