# starsparql

Translate SPARQL 1.2 queries into and out of an RDF representation of their
algebra, so a query can be stored, versioned, annotated, and queried about at
the same granularity as any other RDF data — and eventually, so a query can
be *produced* as structured RDF (e.g. by an LLM) rather than as an opaque
string.

Depends on [`starlayergraph`](../graph) for RDF 1.2 (triple-term/reification)
execution — see the root [README](../../README.md#dependency-shape) for why
the dependency runs both directions.

## Design

rdflib's own SPARQL algebra (`rdflib.plugins.sparql.algebra`) is already a
tree of `CompValue`/`Expr` nodes — each just a named dict (`name` +
typed keys, e.g. `BGP(triples=...)`, `Filter(expr=..., p=...)`,
`LeftJoin(p1=..., p2=..., expr=...)`). That shape maps onto RDF almost
mechanically:

- `node.name` -> `rdf:type salg:<name>`
- each `key: value` -> `salg:<key>` predicate, value encoded recursively
  (nested node -> nested resource, list -> `rdf:List`, RDF term -> itself)

See `starsparql/vocab.py` for the full encoding rules, including the
handful of shapes that need their own convention beyond the generic rule:
triple patterns, SPARQL variables, property paths (`rdflib.paths.Path` —
not a CompValue), `VALUES`-row bindings, bare-Python-string bookkeeping
values (grammar keyword tokens like `UNDEF`/`DEFAULT`/`SILENT` that rdflib
represents as plain `str`, never as a real RDF term), and Update's
quads-by-graph maps.

This is deliberately **one generic recursive encoder/decoder**
(`to_rdf.py` / `from_rdf.py`), not one function per algebra operator — it
mirrors whatever operator/expression names rdflib's own grammar and algebra
module actually define, including by *introspecting* rdflib's live parser
grammar at import time to rebuild the expression-name -> eval-function table
(see `from_rdf._discover_expr_evalfns`), rather than hand-transcribing it.
That means it doesn't need to be extended by hand when rdflib adds a new
algebra operator or expression builtin.

## What it does

- **Full algebra round-trip** — `SELECT`/`ASK`/`CONSTRUCT`/`DESCRIBE`, `BGP`,
  `FILTER`, `OPTIONAL`, `UNION`, `MINUS`, `SERVICE` (structural only — never
  executed, since that needs a live network call), all five property-path
  forms, aggregates/`GROUP BY`/`HAVING`, `ORDER BY`/`LIMIT`/`OFFSET`,
  subqueries, `VALUES` (including `UNDEF`), and full SPARQL Update. Verified
  by *executing* both the original and round-tripped query/update and
  comparing results, not by comparing regenerated query text (text form
  isn't stable — see "Non-obvious facts" below).
- **`BASE`/`PREFIX` prologue round-trip** — `query.prologue`/
  `update.prologue` aren't part of the algebra tree at all, but are needed
  for correct `BASE`-relative `IRI()`/`URI()` resolution at evaluation time.
- **Native SPARQL 1.2 algebra** — real `TripleTermNode`s (`<<( s p o )>>`/
  `TRIPLE(s, p, o)`) as first-class nodes in the tree this project encodes,
  plus the annotation/reification-shorthand forms (`<<s p o>>`,
  `<<s p o ~ reifier>>`, `s p o ~ r`, `s p o {| ap av ; ... |}`). Ingestion
  goes through this project's own `starsparql.parse12`, which extends
  rdflib's real grammar in place (`grammar12.py`) — not a text-rewrite
  pipeline.
- **Direct execution, no text round-trip** — `lower_rdf11.py` lowers a
  decoded SPARQL 1.2 algebra tree straight into a directly-runnable SPARQL
  1.1 `Query`/`Update` object (`rdf11_to_query`/`rdf11_to_update`), executed
  against a real `StarLayerGraph`/`StarLayerDataset` with no SPARQL text
  involved anywhere after the initial parse. Text serialization
  (`rdf11_to_sparql11_text`/`rdf11_update_to_sparql11_text`) still exists for
  callers that need real text, e.g. a remote store requiring a plain string.
- **`salg:QueryCollection`** — serializing a *set* of independent queries as
  one RDF graph/Turtle file.
- **SHACL shapes over the vocabulary** (`starsparql/ontology/sparql_shapes.py`, backed by a
  real RDFS ontology in `starsparql/ontology/salg-ontology.ttl`) — structural validation for an
  algebra RDF graph, LLM-authored or hand-authored, before attempting
  `rdf_to_query`/`rdf_to_update`. Covers every operator/expression
  builtin/Update operation above.
- **A real W3C SPARQL 1.2 conformance test suite harness**
  (`tests/test_w3c_sparql12.py`), run end to end against this project's own
  pipeline — parse → encode → decode → re-execute — compared against the
  suite's own official expected results, not just self-consistency.

Not implemented: `ASK`/`DESCRIBE` text serialization, a real Oxigraph
backend as a second execution leg, and syntax-layer round-trip beyond the
prologue (original `PName` spelling, formatting, comments — round-trip is
semantically canonical, not textually faithful).

## Non-obvious facts worth knowing before you dig in

- **A bare Python `str` in the algebra tree isn't safe to encode as
  `rdflib.Literal`** — `Literal("=") == "="` is `False` in rdflib. Any bare
  `str` (grammar keyword tokens like `UNDEF`/`DEFAULT`/`SILENT`) gets tagged
  with the reserved datatype `SALG.PyStr` on encode instead.
- **`rdflib.plugins.sparql.algebra.translateAlgebra` never reads
  `query.prologue` at all** — regenerated query text is never prefixed,
  regardless of the source prologue; that's a real rdflib limitation, not a
  gap in this project.
- **A triple term can never be legal as another triple term's own subject
  or predicate**, enforced at construction (`TripleTermNode.validate()`),
  not just in the grammar — the grammar itself stays permissive to match
  what SPARQL's own text-level parsing accepts.

See `CLAUDE.md` for the full list, the file map, and current known gaps.

## Setup

Not published to PyPI. Part of the `starlayer` monorepo — install all three
packages from the repo root, in dependency order:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/graph -e packages/sparql -e packages/shacl
pip install -e packages/sparql[test]   # includes pyshacl, for shapes.py
cd packages/sparql && pytest
```
