# Moving the graph side to Oxigraph: staged plan

Branch `shacl-engine`, 2026-10-31. A draft for sign-off. Numbers come from the reports named in each section; line counts are
file-level. Nothing here has been done on `main`, and nothing is pushed.

Sources: `graph-rdflib-compat-inventory.md`, `oxigraph-capability-matrix.md`, `graph-functionality-comparison.md` (with the
decisions you recorded), `sparql-layers-exploration.md`, `salg-retirement-analysis.md`, and, on their own branches,
`sparql-parser-plan.md` (branch `sparql-parser`), `sparql-direct-execution-spike.md` (branch `sparql-direct`) and
`shacl-engine-term-model-spike.md` (branch `shacl-engine-terms`).

## 1. Decisions this plan rests on

- Oxigraph is the baseline store and query engine. `StarLayerGraph` stays, as a wrapper by composition over a `pyoxigraph.Store`
  (the pyoxigraph classes cannot be subclassed). Functions may take a store directly.
- SPARQL text goes straight to Oxigraph. The `salg:` export need not be preserved.
- sqe stays: it is the ontology that drives the SPARQL editor.
- rdflib does not stay as the SPARQL parser. A StarLayer-owned parser replaces it, modelled on the Manchester parser.
- The interchange form for triple terms is the "basic encoding" (already built in `graph/model/encoding.py`).
- Kept: pretty Turtle, HTTP engines, Manchester syntax, the OWL reasoning and shape derivation. Dropped: the SQLAlchemy and other
  rdflib stores, `Resource`, the prefix manager with its 29 default bindings.
- RDFC with triple terms is maintained.

## 2. What the investigations found that shapes the order

1. **Most of the "direct execution" work is already done.** `StarLayerGraph(backend='rdf-1.2')` already sends text straight to
   Oxigraph, with no parse and no lowering. The parse, lower and decode round trip (`prepare_query_12`, `query_to_rdf11`,
   `rdf11_to_query`) runs only on the default `rdf-1.1` backend over an rdflib store, and for the OWL entailment regimes
   (`sparql-direct-execution-spike.md`, trace table). So the move is mostly making the Oxigraph backend the default and retiring
   the rdflib-store backend with its `tt:` encoding.
2. **Direct execution is much faster.** On 20 queries at 20k and 100k triples, direct is 2 to 50 times faster on 17, and two
   queries (an OPTIONAL and a triple-term join) do not finish on rdflib in 120 s. Lowering costs 10 to 40 ms per distinct query
   text (median 16 ms) and is cached. Caveat: nested `FILTER EXISTS` was 6 to 20 times slower on Oxigraph (2.9 s and 55 s against
   0.5 s and 2.8 s at 20k and 100k triples).
3. **Identical test results with the opt-in flag.** `tests/graph` 2,526 and `tests/sparql` 1,078 passed both ways, and 745 tests in
   21 native, W3C and dataset files with the store matrix also passed both ways, with 230 queries and 66 updates routed direct. The
   full suites mostly use the rdf-1.1 backend, so the flag barely touches them; this is weaker evidence than it looks.
4. **A parsed tree is still needed in specific places:** query-time `entailment=RDF/RDFS` (done today by rewriting the rdflib
   algebra in `sparql/entailment_rdfs.py`; the native path raises `NotImplementedError`), the OWL query step, the prepared-query
   cache, `prepareQuery`/`parseQuery`, and consumers of `Query.algebra` (SHACL checks, SRL, sqe).
5. **A StarLayer-owned parser is feasible.** The prototype (1,594 lines, branch `sparql-parser`) parses all 167 W3C positive and
   rejects all 81 negative query syntax tests, round-trips 167 of 167 through text, and agrees with the current `sqe_parse_to_tree`
   on the 701 tests of the opt-in gate after one lexical-fidelity fix. Parse takes 0.9 ms against 18.7 ms. Remaining: about 1,000
   to 1,400 lines (Update, DESCRIBE, more semantic rules, a production coverage matrix, SRL onto it); 2 to 3 weeks for queries
   with gates, 4 to 5 with Update and the SPARQL 1.1 suite. Correction to an earlier assumption: SRL is not a hand-written parser; it
   is pyparsing spliced onto rdflib's grammar, so it depends on what is being retired.
6. **The engine runs on pyoxigraph terms** (branch `shacl-engine-terms`, all tests green, speed unchanged) with three conditions
   to settle. This aligns the engine's term model with `oxrdf` for a later Rust port.
7. **Retiring salg is mostly unblocked.** Steps 1 to 3 (move the generic codec into an sqe-owned module, add parity tests and the
   pre-bound-variable exemption to sqe, repoint `meta_shapes` at sqe and drop the engine's SalG component) depend on nothing else.
   About 2,300 lines can go, plus the lowering layer once execution no longer needs it. It touches `starontology/` (see section 5).
8. **Lexical fidelity is a project-wide property, not an Oxigraph one.** The default `turtle` parser and the `Literal`
   constructor normalise; `turtle12` and `normalize=False` do not; Oxigraph's store normalises with no switch (issue #190,
   upstream PR #2010 pending).

## 3. The stages

Each stage has a gate that must pass before the next starts. Work stays on branches until you decide otherwise.

**Stage 0: independent groundwork (no ordering constraints).**
- 0.1 **(done)** Adopt the term-model work into `shacl-engine`, after the three conditions: define what `to_engine` does with invalid IRIs,
  blank-node ids and language tags; ban `str(term)` inside the engine; cross-check `xsd_values` against a second implementation.
- 0.2 *(moved to the final stage by the owner's decision: salg is retired at the end.)* Salg retirement steps 1 to 3. Gate: sqe parity
  tests cover the checks the salg shapes performed; the 12 salg-using test files pass or are rewritten.
- 0.3 Retire the SPARQL `=` guard for dirLangString (`backends/dirlang_equality.py`, 296 lines): the abort is fixed in pyoxigraph
  0.5.13. Gate: the 16 guarded shapes pass with the guard off. **DONE on branch `mig-stage0` (2026-10-31):** the guard now applies only below pyoxigraph 0.5.13 or to a remote Oxigraph of unknown version; the file retires with the version pin.
- 0.4 Decide the default for lexical fidelity in parsing (see section 5, item 6), and add the `preserves_lexical_forms` warning. **DONE on branch `mig-stage0` (2026-10-31):** see `docs/working/lexical-fidelity-default.md` and `StarLayerFidelityWarning` (`shacl_engine/fidelity.py`).
- 0.5 Fetch the SPARQL 1.1 syntax suite (only 1.2 is vendored).

**Stage 1: the parser.** Finish the query parser with its gates (W3C 1.1 and 1.2 syntax, sqe agreement, a production coverage
matrix in the style of the SRL suite), then Update and DESCRIBE, then port SRL onto it. Decide how `FROM`, `SERVICE`, `DESCRIBE`
and Update are modelled in sqe (they have no terms today). Gate: every query the repo's tests parse is accepted by the new parser
and agrees; no W3C negative test passes. Behaviour change to record: triple order follows the source, not rdflib's
`reorderTriples`.

**Stage 2: the wrapper and the default.** Build `StarLayerGraph` as a composition wrapper over `pyoxigraph.Store` with the common
methods delegated explicitly and the rest forwarded; add `as_store()`. Make the Oxigraph backend the default; keep the rdflib
backend behind a flag for one release. Port query-time RDFS/RDF entailment onto the sqe tree. Add the prefix handling decided in
section 5 (per-call prefixes, a shared read-only library or none). Gate: `tests/graph`, `tests/sparql`, `tests/shacl` and the
engine suites pass on the new default; the nested `FILTER EXISTS` slowdown is understood (a rewrite in the sqe tree may avoid it).

**Stage 3: retire the old machinery.**
- the evaluator-side rdflib patches (about 2,440 lines) and the triple-term patching inside them (about 617);
- the `tt:` encoding family in the graph classes (about 1,300 lines), keeping `to_basic()`/`from_basic()` as interchange;
- the 1.2-to-1.1 lowering and its cache (about 1,180 lines), then `lower_rdf11.py` and `serialize12.py` where nothing else uses
  them (`serialize12.py` is also used by `sqe/to_text` and `expr_text`);
- the hand-written parsers and serializers that Oxigraph replaces (about 5,600 lines, not Manchester, pretty Turtle or TriX),
  gated on the W3C RDF 1.2 syntax suites passing against Oxigraph's parsers (not yet run);
- the salg encoder and the salg files (about 2,300 lines), TriX (324 lines), the rdflib stores, `Resource`, the prefix manager;
- `compare.py` and `rdfc.py` once the Oxigraph canonicalisation plus the basic encoding match them on their corpus.

**Stage 4: the facade.** `StarLayerGraph(Graph)` survives for a transition period as a compatibility class, then goes. Only then
can rdflib leave the dependency list entirely; that is optional and depends on who still passes rdflib graphs in. 252 test files
import rdflib, mostly for term classes, so the tests move with the term-model decision.

## 4. What is given up, in one place

From `graph-functionality-comparison.md`, plus what the spikes added.
- **Control of literal lexical forms in the store** until issue #190 is fixed upstream (bridges: the reifier sidecar, the warning).
- **Language-tag case** (Oxigraph lowercases) and `sameTerm("1","01")`: the SPARQL parser normalises numeric constants.
- **Error types and messages** (`SyntaxError` with a position instead of rdflib's `ParseException`), and `SELECT *` column order
  (alphabetical against order of appearance).
- **Speed on nested `FILTER EXISTS`** (6 to 20 times slower), unless rewritten.
- **Browser or Pyodide deployment**, and a pure-Python install (native wheels only).
- **`LOAD <file://…>`** in UPDATE; **per-process custom function registration** (functions are passed per call).
- **rdflib stores** (SQLAlchemy and others), **`Resource`**, the **prefix manager and 29 default bindings**, graph set operators
  (unless kept).
- **Third-party code that expects an rdflib `Graph`**, once the facade is retired.
- **TriX**: dropped (decided).
- Gains: 10 to 1,000 times faster loads and queries, parallel queries, RocksDB persistence, `CREATE GRAPH`, custom aggregates, native
  RDFC-1.0, and no lowering or `tt:` encoding to maintain.

## 5. Sign-offs and open questions

Answers recorded 2026-10-31.

1. **Adopt the term-model port into `shacl-engine`, with its three conditions: yes. DONE (merge d0a7699, 2026-10-31).** The conditions: ill-formed
   terms raise a `TermError` up front (lenient opt-in with reversible stand-ins); `str(term)` is banned in the engine by an AST test;
   `xsd_values` was cross-checked against Oxigraph's engine (five bugs in `xsd_values` fixed; Oxigraph's own differences documented and
   asserted). Engine suites 1,792 passed, 4 expected failures, 1 known fixture defect; default SHACL tier 1,738 passed; native-mode tier unchanged.
2. **The three give-ups: all accepted (2026-10-31).** `LOAD <file://…>` in UPDATE (use `Store.load(path=…)`); browser/Pyodide
   deployment ("ok for now": revisit if a serverless in-browser workbench is wanted); language-tag case (Oxigraph lowercases `EN-us`).
3. **`starontology/`: changes on this branch are fine** (nothing reaches `main` until the end). **Salg is retired at the end**, not
   in Stage 0: Stage 0.2 moves to the final stage. Memory updated accordingly.
4. **The `rdf-1.1` backend does not survive.** The owner's direction: handle RDF 1.1 *output* with the RDF 1.2 Interoperability
   approach (the basic encoding) at export time, instead of keeping a separate storage backend. So Stage 2 makes the Oxigraph
   backend the only backend and adds an export mode (`serialize(..., rdf_version="1.1")` or similar) that rewrites triple terms
   with `to_basic()`. **Agreed by the owner (2026-10-31).** The basic-encoding document is valid RDF 1.1 syntax but, as the draft says,
   not semantically equivalent to the input.
5. **Wrapper and rdflib `Graph`:** "whatever works"; nothing will be used until the final form, so build it standalone and add
   compatibility only where a test or user needs it.
6. **Parsing and the name `turtle`:** the owner assumes Oxigraph's `turtle` is Turtle 1.2. Confirmed: pyoxigraph's `RdfFormat.TURTLE`
   parses RDF 1.2 Turtle (triple terms, annotations, reifiers, `VERSION`, base direction), and keeps lexical forms on parse.
   Decision (agreed): `turtle` means Turtle 1.2 and is the faithful parser; `turtle12` stays as an alias, and both are accepted for now
   (the alias can be dropped later). RDF 1.1 output goes through the approach in item 4.
7. **Prefixes:** a global setting (default empty, like Oxigraph) that populates each graph's prefix map when the graph is built;
   the graph's map is a plain dictionary used at serialize and query time (Oxigraph has no store-level prefixes). Whether a graph
   copies the global at build time (isolated from later changes) or references it is a detail to settle; copying is cheap.
8. **TriX: dropped** (decided 2026-10-31; `parsers/trix12.py` 161 and `serializers/trix12.py` 163 lines retire in Stage 3).
   **Set operations: built.** `graph/setops.py` provides `union`, `intersection`, `difference` and `symmetric_difference` for the rdflib
   family and for pyoxigraph `Store`/`Dataset` with one set of semantics (blank nodes by label, quads with their graph name, inputs
   never modified, streaming membership tests); 24 tests. To wire to `+ - & ^` on the Oxigraph-backed `StarLayerGraph` wrapper in Stage 2.
9. **`ssyn`/`sast`: dropped (done, branch `shacl-engine`).** Six modules (946 lines) and two test files removed; 808 SPARQL unit tests pass.

## 6. Risks

- The parser's static semantic rules are where a hand-written parser silently accepts too much; the negative-test gate and the
  coverage matrix are the control.
- Dropping the rdflib parse path changes triple ordering in trees (source order), which can change blank-node ordering in outputs
  and golden files.
- The direct-execution evidence is thinner than the headline: most of the existing suites run on the rdf-1.1 backend. Stage 2's gate
  must run them on the new default.
- Remote engines (Fuseki and `oxigraph serve`) were not exercised in the spikes.
- pyoxigraph's version policy: the plan assumes 0.5.13 or newer; pin the minimum.
- Schedule: roughly 4 to 5 weeks of parser work is the long pole; stages 2 and 3 can overlap it only where they do not depend on a
  tree.
