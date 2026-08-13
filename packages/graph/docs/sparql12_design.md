# SPARQL 1.2 Query Design — Examples and Expected Behaviour

*Last reviewed: 2026-07-17*

This document defines how `StarLayerGraph.query()` should behave with SPARQL 1.2
triple-term syntax. It is a design agreement, not an implementation spec.

---

## Dataset Used in All Examples

```turtle
@prefix :    <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

# Unasserted Triple term in object position. No reification.
:alice :says <<( :bob :knows :carol )>> .

# Named reifier using tilde syntax — triple is asserted.
:bob :knows :carol ~ :stmt1 .
:stmt1 :confidence "0.9" ;
       :source :WikiData .

# Inline annotation — anonymous reifier of asserted triple.  
:bob :knows :carol {| :since "2020" ; :via :LinkedIn |} .

# Reification shorthand — anonymous reifier, underlying triple NOT asserted.
<< :bob :knows :carol >> :verifiedBy :ResearchTeam .

# Reification of a different, unasserted triple.
<< :carol :knows :dave >> :certainty "low" .
```

---

## Formal RDF 1.2 Representation

The above dataset expressed in formal RDF 1.2 (no annotation syntax) — using `rdf:reifies` and `<<( )>>` triple terms. This is the canonical form that all annotation syntaxes desugar to. Anonymous reifiers are written here as `_:rr0`/`_:rr1`/`_:rr2` for readability (an unnamed reifier is conceptually a blank node); internally, and in raw query results (e.g. `?stmt` in QF4/QF5 below), starlayergraph actually returns a stable skolemized `rr:N` URIRef rather than a true rdflib `BNode` — this has no bearing on any of the query results below, since none of them assume BNode identity.

```turtle
@prefix :    <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

# Triple term in object position — base triple not asserted.
:alice :says <<( :bob :knows :carol )>> .

# Base triple is asserted (from both the tilde and inline-annotation examples above).
:bob :knows :carol .

# Named reifier (:stmt1) with its properties.
:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" ;
       :source :WikiData .

# Anonymous reifier (_:rr0) with its properties — from the {| |} annotation.
_:rr0 rdf:reifies <<( :bob :knows :carol )>> ;
      :since "2020" ;
      :via :LinkedIn .

# Anonymous reifier (_:rr1) from the << >> shorthand — base triple is asserted above.
_:rr1 rdf:reifies <<( :bob :knows :carol )>> ;
      :verifiedBy :ResearchTeam .

# Anonymous reifier (_:rr2) for a different triple that is NOT asserted.
_:rr2 rdf:reifies <<( :carol :knows :dave )>> ;
      :certainty "low" .
```

---

## SPARQL 1.2 Query Examples

QF1 pairs the formal pattern with its syntactically equivalent `<< >>` turtle annotation form. QF2 introduces `{| |}`, which differs semantically — it requires the base triple to be asserted — and shows what that constraint excludes.

---

### QF1 — All properties of reifiers of a specific triple

**Formal**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?p ?o WHERE {
  ?r rdf:reifies <<( :bob :knows :carol )>> .
  ?r ?p ?o .
}
```

**Equivalent — `<< >>` annotation form**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?p ?o WHERE {
  << :bob :knows :carol >> ?p ?o .
}
```

**Expected results**

?p              | ?o
rdf:reifies     | <<( :bob :knows :carol )>>
rdf:reifies     | <<( :bob :knows :carol )>>
rdf:reifies     | <<( :bob :knows :carol )>>
:confidence     | "0.9"
:source         | :WikiData
:since          | "2020"
:via            | :LinkedIn
:verifiedBy     | :ResearchTeam

The `rdf:reifies` row appears once per reifier (three times) since it is a
property of each reifier node. Add `FILTER(?p != rdf:reifies)` to see only
annotation properties.

---

### QF2 — Annotation syntax: asserted triples only

The formal pattern below includes `?s ?p ?o .` to assert the base triple, then finds its reifiers' properties. The `{| |}` form is the annotation equivalent.

**Formal** *(base triple assertion explicit)*
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?s ?p ?o ?pred ?val WHERE {
  ?s ?p ?o .
  ?r rdf:reifies <<( ?s ?p ?o )>> .
  ?r ?pred ?val .
  FILTER(?pred != rdf:reifies)
}
```

**Equivalent — `{| |}` annotation form**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?s ?p ?o ?pred ?val WHERE {
  ?s ?p ?o {| ?pred ?val |} .
  FILTER(?pred != rdf:reifies)
}
```

**Expected results**

?s     | ?p       | ?o       | ?pred        | ?val
:bob   | :knows   | :carol   | :confidence  | "0.9"
:bob   | :knows   | :carol   | :source      | :WikiData
:bob   | :knows   | :carol   | :since       | "2020"
:bob   | :knows   | :carol   | :via         | :LinkedIn
:bob   | :knows   | :carol   | :verifiedBy  | :ResearchTeam

`:carol :knows :dave` does not appear — its base triple is not asserted, so `?s ?p ?o .` finds no match.

---

### QF3 — Triple term in object position

This pattern matches a triple term used as a value, not a reification relationship.

```sparql
PREFIX : <http://example.org/>

SELECT ?who WHERE {
  ?who :says <<( :bob :knows :carol )>> .
}
```

**Expected results**

?who
:alice

---

### QF4 — Enumerate reifiers and their triple term components

`?stmt` is needed to correlate the reifier with its predicate and object — `<< >>` does not expose the reifier variable, so only the formal pattern is used here.

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?s ?p ?o WHERE {
  ?stmt rdf:reifies <<( ?s ?p ?o )>> .
}
```

**Expected results**

?stmt    ?s      ?p       ?o
:stmt1   :bob    :knows   :carol
_:rr0    :bob    :knows   :carol
_:rr1    :bob    :knows   :carol
_:rr2    :carol  :knows   :dave

All four reifiers are returned. `:rr2` reifies a different triple term
`<<( :carol :knows :dave )>>` whose base triple is not asserted.

---

### QF5 — Triple term bound as a variable

When `?t` is selected directly, `query()` post-processes the result to return a
`TripleTerm` object rather than the internal `tt:HASH` URIRef.

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?t WHERE {
  ?stmt rdf:reifies ?t .
}
```

**Expected results**

?stmt    | ?t
:stmt1   | <<( :bob :knows :carol )>>
_:rr0    | <<( :bob :knows :carol )>>
_:rr1    | <<( :bob :knows :carol )>>
_:rr2    | <<( :carol :knows :dave )>>

All four reifiers are returned. `:stmt1`, `_:rr0`, and `_:rr1` all reify the same
triple term; `_:rr2` reifies a different one.

---

### QF6 — Triple term in object position, returned as a variable

```sparql
PREFIX : <http://example.org/>

SELECT ?who ?t WHERE {
  ?who :says ?t .
}
```

**Expected results**

?who     | ?t
:alice   | <<( :bob :knows :carol )>>

`?t` binds to the triple term value. `query()` restores it to a `TripleTerm` object
in the result; callers never see the internal `tt:HASH` encoding.

---

### QF7 — `SUBJECT`, `PREDICATE`, `OBJECT` functions

These functions extract the components of a bound triple term variable. They rewrite to `rdf:subject`/`rdf:predicate`/`rdf:object` triple patterns in the underlying query.

**Using SELECT expressions**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?t
       (SUBJECT(?t)   AS ?s)
       (PREDICATE(?t) AS ?p)
       (OBJECT(?t)    AS ?o)
WHERE {
  ?stmt rdf:reifies ?t .
}
```

**Using BIND**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?s ?p ?o WHERE {
  ?stmt rdf:reifies ?t .
  BIND(SUBJECT(?t)   AS ?s)
  BIND(PREDICATE(?t) AS ?p)
  BIND(OBJECT(?t)    AS ?o)
}
```

**Expected results**

?stmt    | ?t                          | ?s      | ?p       | ?o
:stmt1   | <<( :bob :knows :carol )>>  | :bob    | :knows   | :carol
_:rr0    | <<( :bob :knows :carol )>>  | :bob    | :knows   | :carol
_:rr1    | <<( :bob :knows :carol )>>  | :bob    | :knows   | :carol
_:rr2    | <<( :carol :knows :dave )>> | :carol  | :knows   | :dave

---

### QF8 — `isTripleTerm` filter

`isTripleTerm(?x)` returns `true` when `?x` is a triple term value. Use it to find
triple terms anywhere in the graph without knowing which predicate carries them.
`isTRIPLE(?x)` — the SPARQL 1.2 spec's own name for this function (§17.4.6) — is
accepted as an exact alias; the two spellings rewrite identically.

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?t ?s ?p ?o ?asserted WHERE {
  ?sub ?pred ?t .
  FILTER(isTripleTerm(?t))
  BIND(SUBJECT(?t)   AS ?s)
  BIND(PREDICATE(?t) AS ?p)
  BIND(OBJECT(?t)    AS ?o)
  BIND(EXISTS { ?s ?p ?o } AS ?asserted)
}
```

**Expected results**

?t                           | ?s      | ?p       | ?o      | ?asserted
<<( :bob :knows :carol )>>   | :bob    | :knows   | :carol  | true
<<( :carol :knows :dave )>>  | :carol  | :knows   | :dave   | false

`DISTINCT` collapses duplicates from multiple reifiers of the same triple term.
`BIND` extracts the components before `EXISTS` tests them as a plain triple pattern.
`?asserted` is `true` for `:bob :knows :carol` (explicitly asserted); `false` for
`:carol :knows :dave` (only reified, never asserted).

Note the `EXISTS` is bound in its own `BIND(... AS ?asserted)` line rather than
inline as a `(EXISTS {...} AS ?asserted)` SELECT-projection expression — the
latter hits a real rdflib limitation (`EXISTS` fails in a SELECT-projection
`(expr AS ?var)` position; a separate `BIND` in the WHERE clause works fine).

---

### QF9 — OPTIONAL: per-reifier annotation properties

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt ?conf ?source ?since ?via ?verified ?certainty WHERE {
  ?stmt rdf:reifies <<( ?s ?p ?o )>> .
  OPTIONAL { ?stmt :confidence ?conf }
  OPTIONAL { ?stmt :source     ?source }
  OPTIONAL { ?stmt :since      ?since }
  OPTIONAL { ?stmt :via        ?via }
  OPTIONAL { ?stmt :verifiedBy ?verified }
  OPTIONAL { ?stmt :certainty  ?certainty }
}
```

**Expected results**

?stmt    ?conf   ?source    ?since   ?via        ?verified        ?certainty
:stmt1   "0.9"   :WikiData  —        —           —                —
_:rr0    —       —          "2020"   :LinkedIn   —                —
_:rr1    —       —          —        —           :ResearchTeam    —
_:rr2    —       —          —        —           —                "low"

---

### QF10 — ASK: does any reifier of a specific triple carry a given property?

**Formal**
```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

ASK {
  ?r rdf:reifies <<( :bob :knows :carol )>> .
  ?r :confidence ?c .
}
```

**Equivalent — `<< >>` annotation form**
```sparql
PREFIX : <http://example.org/>

ASK {
  << :bob :knows :carol >> :confidence ?c .
}
```

**Expected result:** `true`

---

### QF11 — CONSTRUCT: rebuild a reifier subgraph

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

CONSTRUCT {
  ?stmt rdf:reifies <<( :bob :knows :carol )>> .
  ?stmt ?p ?o .
} WHERE {
  ?stmt rdf:reifies <<( :bob :knows :carol )>> .
  ?stmt :confidence ?c .
  ?stmt ?p ?o .
  FILTER(?p != rdf:reifies)
}
```

**Expected result graph**

```turtle
:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" ;
       :source :WikiData .
```

The WHERE clause restricts to reifiers that carry `:confidence` (only `:stmt1`).
All remaining properties of that reifier are projected via `?p`/`?o`.

---

### QF12 — `TRIPLE()` constructor function

`TRIPLE(s, p, o)` is the SPARQL 1.2 spec's function-call form of a triple term
(§17.4.6) — an alternative spelling of `<<( s p o )>>`, useful when the subject,
predicate, or object come from expressions rather than being written literally.
It is rewritten to `<<( s p o )>>` before any other processing, so it works
anywhere that syntax does: graph-pattern position, `BIND`, and CONSTRUCT
templates (including minting a triple term that has no existing match, the
same way QF11 combined with the CONSTRUCT-template case in the test suite does).

```sparql
PREFIX :   <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?stmt WHERE {
  ?stmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
}
```

is exactly equivalent to writing `?stmt rdf:reifies <<( :bob :knows :carol )>> .`
(QF1's formal form) — same expected result: `:stmt1` plus both anonymous reifiers.

---

## How the Rewriter Works

`StarLayerGraph.query()` routes each query based on the configured backend.

**rdf-1.1 backend (default, including in-memory):** the query is translated into SPARQL 1.1, executed against the underlying rdflib store, then any triple term values in the results are restored. Queries with no RDF 1.2 constructs and no triple term results pass through unchanged. This translation has three phases.

**Native rdf-1.2 backend:** the query is forwarded directly to the
SPARQL endpoint via HTTP. No phase 1–3 processing applies — the backend handles
triple terms natively.

---

### Phase 1 — Annotation form expansion

The three annotation shorthand forms are expanded directly to RDF 1.1 triple
patterns in optimized join order. There is no intermediate step through canonical
RDF 1.2 — Phase 1 produces the final encoding-layer patterns in one pass.

Join order rationale: component patterns (`rdf:subject`/`rdf:predicate`/`rdf:object`)
come first because the `rdf:subject` index is very selective when the subject is a
ground term, binding `?__tt` before the engine searches for reifiers. The base triple
assertion (`s p o .`) comes last so the engine starts from the smaller set of triple
term nodes rather than scanning every triple when s/p/o are variables.

**`s p o ~ ?r`** — named reifier, base triple asserted

```sparql
# Input
s p o ~ ?r .

# Expanded
?__tt0 rdf:subject   s .
?__tt0 rdf:predicate p .
?__tt0 rdf:object    o .
?r rdf:reifies ?__tt0 .
s p o .
```

**`s p o {| ?pred ?val |}`** — anonymous reifier, base triple asserted

```sparql
# Input
s p o {| ?pred ?val |} .

# Expanded
?__tt1 rdf:subject   s .
?__tt1 rdf:predicate p .
?__tt1 rdf:object    o .
?__r0 rdf:reifies ?__tt1 .
?__r0 ?pred ?val .
s p o .
```

**`<< s p o >> ?pred ?val`** — anonymous reifier, no assertion check

```sparql
# Input
<< s p o >> ?pred ?val .

# Expanded
?__tt1 rdf:subject   s .
?__tt1 rdf:predicate p .
?__tt1 rdf:object    o .
?__r0 rdf:reifies ?__tt1 .
?__r0 ?pred ?val .
```

The `~` and `{| |}` forms append `s p o .` to enforce that the base triple is
asserted; `<< >>` does not. The anonymous reifier `?__r0` is never exposed in
SELECT results — use `~ ?r` to name it.

---

### Phase 2 — Triple term rewrite (RDF 1.2 → RDF 1.1)

Each explicit `<<( s p o )>>` triple term in a WHERE clause is replaced by an
auto-generated variable `?__ttN`, and three encoding triples are injected into
the same graph pattern block. Annotation forms are already fully expanded by
Phase 1 and do not pass through here.

**Fixed triple term**

```sparql
# Input
?stmt rdf:reifies <<( :bob :knows :carol )>> .

# Rewritten
?stmt rdf:reifies ?__tt0 .
?__tt0 rdf:subject   :bob .
?__tt0 rdf:predicate :knows .
?__tt0 rdf:object    :carol .
```

**Variable triple term components**

```sparql
# Input
?stmt rdf:reifies <<( ?s ?p ?o )>> .

# Rewritten
?stmt rdf:reifies ?__tt0 .
?__tt0 rdf:subject   ?s .
?__tt0 rdf:predicate ?p .
?__tt0 rdf:object    ?o .
```

**Triple term in object position**

```sparql
# Input
?who :says <<( :bob :knows :carol )>> .

# Rewritten
?who :says ?__tt0 .
?__tt0 rdf:subject   :bob .
?__tt0 rdf:predicate :knows .
?__tt0 rdf:object    :carol .
```

**Nested triple term**

```sparql
# Input
?r rdf:reifies <<( :alice :believes <<( :bob :knows :dave )>> )>> .

# Rewritten
?r rdf:reifies ?__tt1 .
?__tt1 rdf:subject   :alice .
?__tt1 rdf:predicate :believes .
?__tt1 rdf:object    ?__tt0 .
?__tt0 rdf:subject   :bob .
?__tt0 rdf:predicate :knows .
?__tt0 rdf:object    :dave .
```

**Function rewrites**

**`SUBJECT(?t)` / `PREDICATE(?t)` / `OBJECT(?t)`** — inject component triple patterns
```sparql
# Input
(SUBJECT(?t) AS ?s)  (PREDICATE(?t) AS ?p)  (OBJECT(?t) AS ?o)

# Rewritten — inject into WHERE, substitute variable in SELECT
?t rdf:subject   ?s .
?t rdf:predicate ?p .
?t rdf:object    ?o .
```

**`isTripleTerm(?x)`** — rewritten to a URI prefix check
```sparql
# Input
FILTER(isTripleTerm(?x))

# Rewritten
FILTER(STRSTARTS(STR(?x), "https://github.com/hidden-graph/starlayergraph/ns/tt#"))
```

`STRSTARTS` alone is sufficient: every `tt:`-prefixed URIRef is created exclusively
by the triple-term interning path, which always writes its `rdf:subject`/`predicate`/`object`
encoding triples in the same call — there's no state where the prefix matches without
them. An earlier version also wrapped this in `EXISTS { ?x rdf:subject [] } &&`, which
was both unnecessary and actively wrong to keep: it hit a real rdflib limitation where
`EXISTS {...} && ...` fails inside a `(expr AS ?var)` position (SELECT projection or
`BIND`) even though the identical expression works fine inside a plain `FILTER(...)`.

---

### Phase 3 — Result restoration

After execution, `query()` scans the result bindings for any `tt:HASH` URIRef
values (the internal encoding of triple terms) and replaces them with `TripleTerm`
objects. This applies only to variables the caller explicitly selected — internal
variables like `?__tt0` are never exposed.

Variables that appear **inside** a triple term pattern (e.g. `?s`, `?p`, `?o` in
`<<( ?s ?p ?o )>>`) bind to plain RDF terms — URIRefs, literals, or blank nodes —
and require no restoration.

```sparql
# Input — no <<( )>> patterns, so Phase 2 is unchanged
SELECT ?stmt ?t WHERE {
  ?stmt rdf:reifies ?t .
}

# rdflib executes and returns (internal representation):
#   ?stmt = :stmt1          ← plain URIRef, unchanged
#   ?t    = tt:a1b2c3d4     ← tt:HASH URIRef (internal encoding)

# After Phase 3 restoration:
#   ?stmt = :stmt1          ← unchanged
#   ?t    = <<( :bob :knows :carol )>>   ← restored to TripleTerm
```

`?t` is restored because it was selected by the caller and holds a `tt:HASH`
URIRef. Variables that bind to triple term *components* (e.g. `?s`, `?p`, `?o`
from `<<( ?s ?p ?o )>>`) are plain RDF terms and are never restored.

Phase 3 applies only to the rdf-1.1 backend. Native backends return triple
terms directly — no `tt:HASH` encoding, no restoration step.
