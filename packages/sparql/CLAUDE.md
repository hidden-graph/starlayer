# CLAUDE.md

Project-specific instructions for Claude Code sessions working in this repo.

## Purpose

Translate SPARQL 1.2 queries into and out of an RDF representation of their algebra, so a query can be stored, versioned, annotated, and queried about at the same granularity as any other RDF data — and eventually, so a query can be *produced* as structured RDF (e.g. by an LLM) rather than as an opaque string.

Sibling package: `../graph` (`starlayergraph`), this project's own RDF 1.2 triplestore/execution engine. The two packages have an intentional two-way dependency — `starsparql` is treated as part of `starlayergraph`'s own SPARQL engine layer, not an independent generic library, and `starlayergraph` depends back on `starsparql` to consume `parse12`/`to_rdf`/`from_rdf`/`lower_rdf11` directly. Don't try to "fix" this into a one-way dependency — it's a deliberate design decision, not an oversight.

## Design

rdflib's own SPARQL algebra (`rdflib.plugins.sparql.algebra`) is already a tree of `CompValue`/`Expr` nodes — each just a named dict (`name` + typed keys, e.g. `BGP(triples=...)`, `Filter(expr=..., p=...)`). That maps onto RDF almost mechanically: `node.name` → `rdf:type salg:<name>`, each `key: value` → `salg:<key>` predicate, recursively encoded. **One generic recursive encoder/decoder** (`to_rdf.py`/`from_rdf.py`) handles every operator and expression builtin uniformly — including introspecting rdflib's live parser grammar at import time to rebuild the expression-name → eval-function table (`from_rdf._discover_expr_evalfns`), rather than hand-transcribing rdflib's ~60 builtins. See `starsparql/vocab.py`'s module docstring for the full encoding rules and the handful of shapes needing their own convention (triple patterns, variables, property paths, VALUES rows, bare-Python-string bookkeeping values, Update's quads-by-graph maps).

## Current capabilities

- Full algebra-level round-trip (encode → decode → re-execute, compared by actual query result, not regenerated text) for `SELECT`/`ASK`/`CONSTRUCT`/`DESCRIBE`, `BGP`/`FILTER`/`OPTIONAL`/`UNION`/`MINUS`/`SERVICE` (structural only), property paths, aggregates/`GROUP BY`/`HAVING`, `ORDER BY`/`LIMIT`/`OFFSET`, subqueries, `VALUES`, and full SPARQL Update (all ten operations).
- `BASE`/`PREFIX` prologue round-trip (`query.prologue`/`update.prologue`, not part of the algebra tree itself).
- A genuine, native SPARQL 1.2 algebra representation — real `TripleTermNode`s (`<<( s p o )>>`/`TRIPLE(s, p, o)`) as first-class nodes, plus annotation/reification-shorthand syntax (`<<s p o>>`, `<<s p o ~ r>>`, `s p o ~ r`, `s p o {| ... |}`). Ingestion goes through this project's own `parse12.py`, which extends rdflib's real grammar in place (`grammar12.py`) — no dependency on any text-rewrite pipeline.
- Direct in-process execution with **no SPARQL text round-trip at all**: `lower_rdf11.py` lowers the decoded 1.2 algebra tree straight to a directly-runnable 1.1 `Query`/`Update` object (`rdf11_to_query`/`rdf11_to_update`). Text serialization (`rdf11_to_sparql11_text`/`rdf11_update_to_sparql11_text`) still exists for callers that need real text (a remote store requiring a plain string).
- `salg:QueryCollection` — serializing a *set* of independent queries as one RDF graph/Turtle file.
- SHACL shapes (`shapes.py`, backed by a real RDFS ontology in `salg-ontology.ttl`) validating the structure of an algebra RDF graph before decoding — covers every operator/expression builtin/Update operation above.
- A W3C SPARQL 1.2 conformance test suite harness (`tests/test_w3c_sparql12.py`) run end-to-end against this pipeline's own translation (not just self-consistency). Four known, deliberately-unfixed failures are documented divergences, not bugs in this project — two (`compound-tripleterm-subject`/`nested-tripleterm-02`) correctly reject text the suite labels `PositiveSyntaxTest` because it's invalid RDF 1.2 regardless of parsing as SPARQL text; two (`list-anonreifier-01`/`list-tripleterm-01`) are left open because the fixtures' own text flags genuine spec ambiguity (see "Known gaps" below).
- `starlayergraph`'s old ~2,164-line regex-based `sparql12_to_11.py` text rewriter has been fully removed and replaced by this pipeline everywhere.

Not implemented: `ASK`/`DESCRIBE` text serialization (no `_AlgebraTranslator` branch exists for either — same class of gap `CONSTRUCT` had before it was added), a real Oxigraph backend as a second execution leg, and syntax-layer round-trip beyond the prologue (original `PName` spelling, formatting, comments — algebra-layer round-trip is semantically canonical but not textually faithful).

## Known non-obvious facts (confirmed by running real code — trust these, but re-verify if rdflib's version changes)

- **A bare Python `str` in the algebra tree is not safe to encode as `rdflib.Literal`.** `Literal("=") == "="` is `False` in rdflib, and the two hash differently. `RelationalExpression.op`, `OrderCondition.order`, VALUES' `UNDEF` sentinel, and Update's `GraphRefAll` keywords are all genuine bare `str` in the live algebra (from a bare `pyparsing.Keyword` match, not a real-term grammar production). Fix in place: any bare `str` gets tagged with the reserved datatype `SALG.PyStr` on encode, decoded back to a bare `str` — by value shape, not by an allowlist.
- **`rdflib.plugins.sparql.algebra.translateAlgebra` never reads `query.prologue` at all.** Its text output is byte-identical whether the prologue is populated or empty — don't expect regenerated query text to use prefixed names; that would require patching rdflib itself.
- **RDF 1.2 (`starlayergraph`) queries need no special handling at the plain algebra layer.** `starlayergraph` rewrites `<<( )>>`/`isTRIPLE`/`LANGDIR`/etc. to plain SPARQL 1.1 text *before* calling rdflib's `translateQuery` — so `query.algebra` never contains a `TripleTermNode` via that path. (The native `parse12.py` path, used for Phase 6+ features, is different — see above.)
- **`_vars`/`lazy` bookkeeping must be recomputed after decoding a Query's algebra, but NOT after decoding an Update's.** `translateQuery` runs `_addVars`/`analyse` on the finished tree; `translateUpdate` never does, even for a `Modify`'s WHERE clause. `from_rdf.rdf_to_query` recomputes these; `from_rdf.rdf_to_update` correctly does not.
- **A triple term can never be legal as another triple term's own subject or predicate — enforced at construction, not just in the grammar.** The RDF 1.2 Turtle grammar's `ttSubject ::= iri | BlankNode` has no `tripleTerm` alternative, unconditionally (not just in "expression position" — an earlier version of this rule was wrong about that, see `triple_term.py`'s `InvalidTripleTermError`). The grammar itself stays permissive (matches what the W3C suite's `PositiveSyntaxTest` labels expect it to parse as text); `TripleTermNode.validate()` is the real semantic backstop, called from both `grammar12.py`'s `_promote` and `from_rdf.py`'s decode branch, so nothing can construct an invalid one and have it survive downstream.
- **Import order matters: `starsparql/__init__.py` imports `parse12` first, before anything else in the package.** `from_rdf.py` snapshots rdflib's live parser grammar at import time (`_discover_expr_evalfns`); `parse12.py` mutates that same shared grammar in place (`grammar12.install()`). If anything imports the bare package before `parse12` runs, later query evaluation silently corrupts (queries that should match return 0 rows). This is why the import order in `__init__.py` is load-bearing, not stylistic — don't reorder it.
- **A ground triple term at ordinary BGP pattern position must not be lowered via a fresh `BIND` variable** — rdflib's `evalExtend` does not enforce "BIND target must be previously unbound" (`c.merge(...)` unconditionally overwrites), so a `BIND`-based lowering can silently produce a false match if that variable is also bound by the BGP's own triple match. `lower_rdf11.py` computes the value eagerly in Python instead and substitutes a literal term.
- **Two Turtle-authoring gotchas in `shapes.py`'s `SHAPES_TURTLE` Python string:** don't embed a literal `"` inside an `sh:message` via Python-level escaping (`\"`) — the resulting Turtle text has a genuinely unescaped quote that breaks Turtle's own parser; avoid literal quote characters in message text instead. And `SALG.term` (attribute access) silently resolves to `rdflib.Namespace`'s own `.term(name)` **method**, not the `salg:term` URIRef — use bracket access (`SALG["term"]`) in hand-written Python; `to_rdf.py`'s own generic encoder already does.

## File map

- `starsparql/vocab.py` — the `salg:` namespace and every encoding convention, with a long module docstring explaining each one and why. Check here first for "how is X encoded?" before re-deriving it.
- `starsparql/to_rdf.py` / `from_rdf.py` — the generic encoder/decoder (`query_to_rdf`/`rdf_to_query`, `update_to_rdf`/`rdf_to_update`, `queries_to_collection`/`rdf_to_collection`) plus the special-cased shapes (triple patterns, paths, binding rows, quads maps, prologue) and `_discover_expr_evalfns` (the live-grammar introspection).
- `starsparql/shapes.py` — hand-authored SHACL shapes over the full vocabulary; `validate()` wraps `pyshacl.validate` with `ont_graph=ontology_graph()`, `inference="rdfs"`.
- `starsparql/salg-ontology.ttl` / `ontology.py` — a real RDFS ontology for the `salg:` vocabulary, actually consulted by `shapes.py::validate()` for RDFS reasoning, not just documentation.
- `starsparql/expr_families.py` — `_EXPR_NODE_FAMILY`, the `{builtin name: argument-signature family}` table both `shapes.py` and `ontology.py` generate their per-builtin declarations from. Its own module so `ontology.py` never needs `pyshacl`.
- `starsparql/grammar12.py` — new pyparsing productions for `<<( s p o )>>`/`TRIPLE(s, p, o)` and the annotation/reification-shorthand forms, spliced into rdflib's own real grammar objects in place via `.append()`/`.insert()` (`install()`).
- `starsparql/triple_term.py` — `TripleTermNode` (the `CompValue` subclass a real triple term needs to survive rdflib's unmodified `translateQuery`/`translateUpdate`) and `InvalidTripleTermError`.
- `starsparql/parse12.py` — `parse_query_12`/`parse_update_12`/`prepare_query_12`/`prepare_update_12`, this project's own SPARQL 1.2 ingestion entry points.
- `starsparql/serialize12.py` — SPARQL 1.2 text serialization for `SELECT`/`CONSTRUCT`, extending rdflib's own `algebra.translateAlgebra`/`_AlgebraTranslator`.
- `starsparql/lower_rdf11.py` — tree-level SPARQL 1.2 algebra → 1.1 algebra lowering, both Query and Update sides; the preferred execution path (`rdf11_to_query`/`rdf11_to_update`, no text involved).
- `tests/w3c_sparql12/` (harness, downloader, and both W3C-suite test files) — the W3C SPARQL 1.2 conformance suite harness (`download_w3c_sparql12_tests.py` fetches it from `w3c/rdf-tests`; a hand-written SPARQL JSON Results parser, `harness.py::parse_srj`, exists because rdflib's own built-in one doesn't understand the RDF 1.2 `"type": "triple"` result-term shape). `test_w3c_sparql12_oxigraph_roundtrip.py` additionally requires a live Oxigraph/Fuseki instance and self-skips otherwise.
- `tests/unit/test_shacl_shapes.py` — valid queries/updates conform; deliberately malformed graphs fail with the expected violation.
- `tests/integration/test_adversarial_roundtrip.py` — hand-authored adversarial cases (not W3C fixtures) proving translation round-trip against a live Oxigraph/Fuseki instance; self-skips if neither is reachable.
- `tests/unit/` — everything else: one file per feature area, no live infra needed.

## Known gaps (deliberately not chased, not oversights)

- **Cross-referential semantic checks SHACL's per-node shapes structurally cannot see** — e.g. a `Project.PV` referencing a variable never bound anywhere in `.p` currently conforms (each shape only checks its own node/immediate neighbors); would need a query spanning the whole subtree. Not pursued: SPARQL's real well-formedness rules are a much bigger surface than this project's own scope needs, and risks the SHACL notion of "valid" drifting from rdflib's own `_addVars`/`analyse`/`evalQuery` ground truth.
- A `<<...>>` reifier-shorthand term's subject/object can't yet themselves be another reifier term or a nested ground triple term.
- `starlayergraph`'s own Turtle parser rejects the `~ reifier` shorthand in Turtle/TriG *data* (as opposed to SPARQL query text, a separate codebase) — out of this project's control without patching that repo.
- The W3C harness's `StarLayerGraph()` construction isn't dataset-capable, so named-graph fixtures (`.trig`/`.nq`) using `GRAPH ?g { }` patterns can't work regardless of query-text correctness.
- `list-anonreifier-01`/`list-tripleterm-01` (`NegativeSyntaxTest`s) — an empty collection `()` as a triple/reifier term's object still parses when the fixture expects rejection. Deliberately left open: the fixture's own text carries a `# TODO: See if this should be throwing an error` comment — genuine spec ambiguity, not a clear gap.
- Whether `TripleTermNode` is actually aligned with the SPARQL 1.2 spec's own formal algebra, or only with rdflib+starlayergraph's pragmatic representation of one, is an open question — not yet resolved against the spec text directly (section 18 of the editor's draft wasn't fully readable at the time this was checked). Low-risk everywhere except `TripleTermNode` itself, since the rest of the operator vocabulary demonstrably matches rdflib's internal naming.
- Actual LLM integration/prompting is explicitly out of scope for this project — a separate downstream effort once the IR + validator + translator exist.

## Setup / running tests

Not published to PyPI. Part of the `starlayer` monorepo — install all three packages from the repo root, in dependency order:

```bash
pip install -e packages/graph -e packages/sparql -e packages/shacl
pip install -e packages/sparql[test]   # includes pyshacl, for shapes.py
cd packages/sparql && pytest
```
