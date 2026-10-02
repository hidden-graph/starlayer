# rdflib Upstream Issues

rdflib 7.6.0. Found while building SPARQL 1.2 support in this repo; every repro is plain `rdflib`, no starlayergraph code. **Not filed upstream** - deferred until rdflib itself starts RDF 1.2 work, then reported as a batch rather than piecemeal now. All have a real fix applied in this repo.

## 1. `MultiplicativeExpression` doesn't apply numeric type promotion for `*`

`xsd:integer * xsd:integer` should stay `xsd:integer`, the same rule `+` already follows. Always comes back `xsd:decimal`.

```python
from rdflib import Graph
list(Graph().query("SELECT (6 * 7 AS ?r) WHERE {}"))[0][0]
# actual:   Literal('42', datatype=xsd:decimal)
# expected: Literal('42', datatype=xsd:integer)
```

Fix: `starlayergraph/query/operator_patches.py::patch_multiplicative_expression_type_promotion`.

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

Fix: `starlayergraph/query/algebra_translator_patches.py::patch_algebra_translator_bugs`.

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

Fix: `starlayergraph/query/evaluate_patches.py::patch_evalextend_forgotten_bind_vars`.

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

Fix: `starlayergraph/query/evaluate_patches.py::patch_lazy_join_expr_dependency_order`.

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

Fix: `starlayergraph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key`.

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

Fix: `starlayergraph/query/result_patches.py::patch_result_iter_empty_binding_row`.
