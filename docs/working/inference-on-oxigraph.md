# Inference over an Oxigraph store: what is standard, what is best for starlayer

> **Decision (2026-11-05, owner):** keep `owlrl` on an rdflib copy (through `_rdflib_bridge.py`) for RDFS and OWL 2 RL reasoning. `reasonable` is **not**
> supported for now; revisit it later. The recommendations below that add it as an optional backend are deferred, not adopted.
> The native SRL evaluator on Oxigraph (no rdflib) is a separate piece of work and is not affected by this decision.

Branch `shacl-engine`, written 2026-11-04. Research only: no code was changed. Sources are cited inline with URLs;
anything from memory and not re-checked this session is marked **(memory, unverified)**. Page fetches this session
were made with a summarising fetch tool, so quotations are the tool's paraphrase of the page, not verbatim, unless
shown in quotes. Benchmarks are in section 6 and were run here; the script is not committed (it lives in the session
scratchpad) and is reproduced in outline there.

## 0. Summary

1. **Oxigraph ships no reasoner and no entailment regimes.** The upstream position (maintainer Tpt, issue
   [#130](https://github.com/oxigraph/oxigraph/issues/130), open, milestone "after 1.0") is that a reasoner should be a
   Datalog-like rule layer inside the SPARQL evaluator, built on a least-fixed-point operator, with truth maintenance.
   Nothing of the kind exists in pyoxigraph 0.5.13. A 2026 attempt to add an OWL 2 RL crate (`oxreason`,
   [PR #1692](https://github.com/oxigraph/oxigraph/pull/1692)) was closed, unmerged, at the maintainer's request that it
   live out of tree. Do not plan on an upstream reasoner.
2. **The standard approach on a SPARQL store is materialisation by a rule set** (RDFS and OWL 2 RL are both plain
   positive Datalog, apart from a handful of list and datatype rules), evaluated semi-naively, with DRed or
   counting for deletions. Done as naive SPARQL UPDATE rounds it works but is slow (section 6).
3. **The repo's SRL engine is not "native over Oxigraph".** `srl_eval.py` evaluates on an rdflib `Graph`
   (`evalBGP`, one call per incoming solution, naive re-evaluation of every rule each round); an Oxigraph input is
   snapshotted to rdflib terms first (`srl_eval.py:696`, `_srl_ast.py:484`). On the benchmark below it was
   slower than owlrl, not faster. The SHACL 1.2 rules engine (`shacl_engine/rules.py`) does run SPARQL CONSTRUCT through
   pyoxigraph on a materialised `OxGraph`, but its loop is also naive and the draft has no negation or
   stratification semantics. Expressing RDFS/OWL 2 RL as SRL is feasible on paper (section 5) but it needs a new,
   semi-naive, store-native evaluator first.
4. **Recommendation** (details in section 7): keep owlrl as the optional correctness oracle and the default for now;
   add [`reasonable`](https://github.com/gtfierro/reasonable) (BSD-3, Rust, pip wheels) as an optional fast
   OWL 2 RL / RDFS backend behind the same `infer()` contract, fed from the store's triples; build the RDFS rule set
   (and later OWL 2 RL) as an SRL/Datalog rule *file* run by a store-native semi-naive evaluator as the
   long-term, dependency-free path; keep HermiT/rustdl for OWL 2 Direct and add whelk (EL) only if a user needs fast
   classification. Prototype first: reasonable fed from pyoxigraph, and a semi-naive CONSTRUCT-delta evaluator.

## 1. What Oxigraph itself offers

| Item | Finding | Source |
|---|---|---|
| Reasoner / inference API | None in pyoxigraph 0.5.13 (`Store` has no `reason`/`infer`; checked in the venv). PyPI page does not mention reasoning. | <https://pypi.org/project/pyoxigraph/> (0.5.13, 2026-10-22) |
| SPARQL 1.1 entailment regimes | Not implemented. The W3C regimes document is itself still a Working Draft: [SPARQL 1.2 Entailment Regimes, 2026-04-09](https://www.w3.org/TR/sparql12-entailment/) (RDF, RDFS, D, OWL 2 RDF-Based, OWL 2 Direct, RIF Core; most obligations are MAY/SHOULD, inconsistent OWL Direct input MUST raise an error). No regime is required of an implementation. | W3C draft |
| Upstream plan | Issue #130 "Support OWL 2 RL reasoning?" open since 2021-08, milestone "after 1.0", label "help wanted". Tpt (2021): not a priority; truth maintenance, especially persistent, is the hard part; an external reasoner would need unstable internals. Tpt (2022-12): wants a "datalog-like" rule language, forward reasoning with truth maintenance on insert/delete and/or backward reasoning at query time. (2023) SHACL could sit on the SPARQL evaluator. | <https://github.com/oxigraph/oxigraph/issues/130> |
| Least fixed point | Tpt, in PR #1692: he would rather prioritise a least-fixed-point operator in the SPARQL evaluator (DataFusion has one; he has an old prototype in spareval; property paths are the missing piece) than carry a reasoner in tree. | <https://github.com/oxigraph/oxigraph/pull/1692> |
| 2026 community attempts | PR #1679 (GeoSPARQL plus `Store::reason`, ~18k lines, split on request, closed 2026-04-22). PR #1692 `lib/oxreason`: 39 OWL 2 RL rules, semi-naive, five inconsistency detectors, closed 2026-05-17, "prefer out of tree". Issue #1681 "Store::reason performance follow-ups" (open, no activity). The author says it was built with an AI assistant, and claims to lag [`reasonable`](https://github.com/gtfierro/reasonable) in profiling. Treat as unreviewed and unmerged. A commenter (July 2026) says he is folding the ideas into a fork called "Oxigraph Nova" (I could not find that project by search; unverified). | <https://github.com/oxigraph/oxigraph/pull/1679>, <https://github.com/oxigraph/oxigraph/issues/1681> |
| SHACL 1.2 Rules request | Issue #1737 (open, enhancement, 2026-05-28, no maintainer reply): asks for SHACL 1.2 Rules as a generic route to OWL 2 RL-style reasoning. | <https://github.com/oxigraph/oxigraph/issues/1737> |
| owlrl's own Oxigraph path | owlrl's README says its optional Oxigraph integration is "provided for compatibility ... rather than for speed", because term conversion removes the benefit. | <https://github.com/RDFLib/OWL-RL> |

Consequence: any inference we ship over Oxigraph is ours or a third party's, and must read the store's quads and write
triples back. There is no in-store integration to wait for.

## 2. Standard approaches on a SPARQL store

**Rules as SPARQL.** RDFS and OWL 2 RL are both defined as rule tables over triples. The RDFS rules are in the
[RDF 1.1 Semantics, section 9.2.1](https://www.w3.org/TR/rdf11-mt/#rdfs-entailment) (rdfs1 to rdfs13) and the OWL 2 RL
rules in the [OWL 2 Profiles, section 4.3](https://www.w3.org/TR/owl2-profiles/#Reasoning_in_OWL_2_RL_and_RDF_Graphs_using_Rules)
(roughly 78 rules in eight tables: eq-*, prp-*, cls-*, cax-*, scm-*, dt-*). Each rule is a conjunctive body
over triple patterns and a head of one or more triples, so each is an `INSERT { head } WHERE { body }` or a
`CONSTRUCT`. Run all rules until no new triples appear: the forward-chaining fixpoint. This is what Jena's rule
engine, Oracle's and RDFox's materialisation, and every OWL 2 RL reasoner do, differing in evaluation strategy
(RDFox, Jena: **memory** and the Datalog literature; no citation fetched here).

**Materialisation versus query-time rewriting.**

| | Materialise (forward chaining) | Rewrite at query time (backward chaining / UCQ rewriting) |
|---|---|---|
| Query cost | none extra | grows with ontology depth; property-path or UNION expansion |
| Update cost | closure maintenance, deletion is the hard part | none |
| Store size | grows (benchmark: x9 on a deliberately inference-heavy set) | unchanged |
| Fits OWL 2 RL | yes, it is designed for it | only RDFS-ish subsets cleanly (`rdfs:subClassOf*` paths) |
| Fits SHACL / validation | yes: validators read plain triples | needs the validator to know the rewrite |

For starlayer the consumers (SHACL `sh:entailment`, class targets, `sh:class`) read triples, so materialisation into
an overlay (the current `InferredView` design) is the right shape. A cheap RDFS-only alternative is query-time
`rdfs:subClassOf*` property paths, already used by SHACL class-target semantics; it avoids any closure but does not
cover domain/range or subproperty inference.

**Incremental maintenance.** Insertions are easy: seed the semi-naive delta with the new triples. Deletions are hard.
DRed (delete and rederive) over-deletes everything with a derivation through the removed fact, then rederives what
still has another derivation; its cost is dominated by over-deletion when facts have many derivations. The
Backward/Forward algorithm of Motik, Nenov, Piro and Horrocks (AAAI 2015, "Incremental Update of Datalog
Materialisation: the Backward/Forward Algorithm") is reported to beat DRed, more so on data with many derivations per
fact (a search-result snippet; I could not fetch the paper, so the numbers are unverified). Counting (keeping a
derivation count per triple) is simpler but breaks on recursive rules. `reasonable` offers `update_graph()` for
incremental re-materialisation after the first run (README, via the PyPI page), but how it handles deletions is not
documented in what I read. For starlayer, which computes a closure on demand as an overlay and discards it, the sound
choice is **recompute, do not maintain**; DRed only matters if the closure must live in the store across edits.
Oxigraph's own maintainer lists persistent truth maintenance as the hard unsolved part (#130 above).

**Naive versus semi-naive.** Naive evaluation re-joins everything each round. Semi-naive joins each rule body once
per body atom against the *delta* of the last round. The benchmark in section 6 is a naive SPARQL UPDATE loop;
semi-naive over SPARQL is possible by materialising the delta into a named graph and generating one query per body
atom, at the cost of generating rule text.

## 3. Reasoners that could run on a pyoxigraph store or its triples

All facts below are from the cited page unless marked. "Input" says what we would have to feed it.

| Tool | Licence | Maintenance | Input | Profile | RDF 1.2 / triple terms | Performance claim |
|---|---|---|---|---|---|---|
| [owlrl](https://github.com/RDFLib/OWL-RL) 7.6.2 | W3C Software Notice and License | alive (219 commits, 24 open issues, needs rdflib >= 7.6.0) | rdflib `Graph` in place; has an optional Oxigraph store path, documented as for compatibility, not speed | RDFS; OWL 2 RL (full, plus its own extras like generalised triples) | none (rdflib terms; the repo bridges `rdf:reifies` by decomposition) | none claimed; measured here, section 6 |
| [reasonable](https://github.com/gtfierro/reasonable) 0.4.4 (PyPI 2026-05-28; 0.5.0a1 pre-release 2026-09-17) | BSD-3-Clause | active (541 commits, 9 open issues) | rdflib `Graph` or iterable of 3-tuples via `from_graph`, or Turtle/N3 files; output as rdflib nodes. Python >= 3.8 wheels incl. macOS arm64/x86_64, Linux, Windows. Runtime dependency on rdflib | OWL 2 RL, partial: README table lists `eq-ref`, `eq-diff1-3`, `prp-ap`, `prp-adp`, `prp-key`, `prp-npa1/2`, `cls-maxc1/2`, `cls-maxqc1-4`, `cls-oo`, `cax-adc` as not implemented; RDFS entailment is a TODO; datatype semantics partial | none stated | "about 7x faster than Allegro and 38x faster than OWLRL" on Brick models (author's own; one workload) |
| [Growl](https://github.com/trivyn/growl) | Apache-2.0 | new, in development (111 commits, 18 stars, no releases, 2026) | Turtle files via CLI; Rust bindings; no Python | OWL 2 RL, 76 of 78 rules (datatype table gaps) | not mentioned | self-reported, one machine: Brick 24.0 s (OWL-RL) vs 314 ms (default), 150 ms (`--fast`) vs 190 ms (reasonable). Written in "SLOP", compiled to C. Too young to depend on |
| [whelk-rs](https://github.com/INCATools/whelk-rs) with [py-whelk](https://pypi.org/project/py-whelk/) 0.4.0 | not checked (**unverified**) | listed as active by a third-party comparison ([ontologos](https://ontologos.readthedocs.io/en/latest/comparison/)); marked experimental in another | OWL ontology through horned-owl / py-horned-owl (file or `PyIndexedOntology`), not triples | OWL 2 EL (classification only) | n/a | OBO-scale TBoxes (third-party description) |
| [horned-owl](https://github.com/phillord/horned-owl) / py-horned-owl | LGPL-3.0 (stated on the rustdl page) | active | OWL file formats, in-memory ontology | library, no reasoning itself | n/a | paper: [Horned-OWL, TGDK 2025](https://drops.dagstuhl.de/storage/08tgdk/tgdk-vol002/tgdk-vol002-issue002/html/TGDK.2.2.9/TGDK.2.2.9.html) |
| [rustdl](https://github.com/MaastrichtU-IDS/rustdl) 0.4.26 | Apache-2.0 or MIT (links horned-owl, LGPL-3.0) | active (2,164 commits); CLI crate yanked 2026-09-04 | OWL files (OFN, OWX, RDF/XML, Manchester), parsed by horned-owl; Python wheels (3.10+) | SROIQ(D), "sound"; complete by construction only on EL/Horn; HasKey and long chains refused (as the repo's `owl_dl_rustdl.py` documents) | none | none stated |
| HermiT via owlready2 | LGPL (HermiT), LGPL-3 (owlready2) **(memory, unverified)** | HermiT stagnant per [ontologos](https://ontologos.readthedocs.io/en/latest/comparison/); owlready2 alive | OWL file or owlready2 world; JVM subprocess | OWL 2 DL, sound and complete | none | slow on large EL ontologies |
| ELK | Apache-2.0 **(memory)** | active per ontologos | OWL API, JVM only | OWL 2 EL | none | very fast EL classification (memory) |
| Pellet / Openllet | AGPL/commercial (Pellet), AGPL-3 (Openllet) **(memory, unverified)** | Openllet sporadic | OWL API / Jena | OWL 2 DL | none | n/a |
| Konclude | LGPL-3 **(memory)** | active per ontologos | OWL file, C++ | OWL 2 DL | none | strong DL performance on benchmarks (memory) |
| [OntoLogos](https://ontologos.readthedocs.io/en/latest/comparison/) 1.1.4 | not checked | active per its own page | unified facade: EL (whelk), RL and RDFS (via reasonable), DL, DL-safe SWRL; `pip install ontologos` | all of the above with profile auto-detection | not stated | self-described comparison page; unverified third-party project |
| [Nemo](https://github.com/knowsys/nemo) (TU Dresden); v0.10 shown at ESWC 2026 ([paper](https://iccl.inf.tu-dresden.de/web/Inproceedings3466)) | Apache-2.0 or MIT | active research system | Datalog files; reads N-Triples, Turtle, RDF/XML, N-Quads, TriG, CSV and SPARQL endpoints; has a `nemo-python` directory (pip status not confirmed) | any Datalog with stratified negation, aggregates, existentials: RDFS and OWL 2 RL are expressible as rules, not shipped as a reasoner | data model "aimed at RDF 1.1 compatibility"; no RDF 1.2 mention | "fast in-memory rule engine", no figures on the page |
| Soufflé | UPL-1.0 **(memory)** | active | compiles Datalog to C++; facts as TSV; no RDF | Datalog | none | very fast compiled Datalog; heavy toolchain, not a fit for a pip library |
| RDFox (Oxford Semantic) | commercial | active | own store; reads RDF 1.1/RDF-star | OWL 2 RL, RDFS, Datalog with negation, incremental (BF) maintenance **(memory)** | RDF-star (memory) | the reference for materialisation speed; context only |
| Stardog | commercial | active | own store | OWL 2 QL/RL/EL, rules, query-time reasoning **(memory)** | RDF-star (memory) | context only |
| Apache Jena rules/OWL reasoners | Apache-2.0 | active | Jena model | RDFS, OWL Lite-ish rules, generic rule engine ([docs](https://jena.apache.org/documentation/inference/)) | RDF 1.2 in recent Jena **(memory)** | JVM; not a fit |
| oxirs-rule (Rust crate) | not checked | one search hit | Rust triple vectors | OWL 2 RL forward chaining incl. disjointWith conflict detection (search snippet) | unknown | unverified, very young |

Reading across: **reasonable is the only mature, permissively licensed, pip-installable OWL 2 RL engine**, and it takes
exactly the thing we have (an iterable of 3-tuples). It is incomplete on OWL 2 RL (equality-diff, keys, cardinality,
`cls-oo`, `cax-adc`, `prp-ap`) and thin on RDFS, so it cannot be the oracle; owlrl can. None of the Python options
speaks RDF 1.2 triple terms, so any route needs the existing decomposition step (triple term to reifier triples) the
repo already does in `_rdflib_bridge.py`, or must leave triple-term triples out of the reasoner input. I found no
2025-2026 reasoner that claims RDF 1.2 triple-term support; Growl and oxirs-rule are the newcomers worth watching.

## 4. What the repo does today

* `graph/oxgraph/helpers/entailment.py`: `infer()` computes RDF entailment natively (rdfD2 plus axiomatic triples),
  RDFS and OWL-RL by copying the store's triples into an rdflib `Graph`, running `owlrl.DeductiveClosure(...)` up to 8
  times to a fixpoint (GitHub issue #97: one pass is not a closure), dropping repeated `err:ErrorMessage` nodes and
  generalised triples, and converting the delta back. OWL-Direct goes to HermiT (owlready2) or rustdl through the
  existing `owl_dl*.py` bridges, again over an rdflib copy.
* `shacl_engine/entailment.py` calls that `infer(..., mode="delta")` on a combined data-plus-ontology graph and holds
  the delta as an overlay. This is the only consumer that matters for validation; it wants the delta, not a copy.
* Costs of this design: three copies of the data (store, rdflib, expanded rdflib), a repeat-to-fixpoint loop, owlrl's
  speed (section 6), and a hard dependency on rdflib for any inference even though the wrapper is meant to be
  rdflib-free.

## 5. Can RDFS and OWL 2 RL be SRL / SHACL rule sets over Oxigraph with no rdflib copy?

### 5.1 What SRL and the SHACL rules engine actually are here

* **SRL** (`sparql/srl.py`, `srl_eval.py`, `srl_semantic_checks.py`; spec
  [SPARQL 1.2 Rules](https://www.w3.org/TR/sparql12-rl/), the code cites the 2026-10-14 draft) is a positive Datalog
  with stratified negation (`NOT { }`), `FILTER`, assignment, `WHERE DATA`. Stratification, the dependency graph and the
  run-once versus general split are translated from the spec's pseudocode.
* The evaluator, however, is **rdflib-based**: `srl_eval.py` imports `evalBGP` and `QueryContext` from rdflib and calls
  one `evalBGP` per incoming solution per run of triple patterns; the base graph and the inferred graph are rdflib
  `Graph` objects; `_srl_ast.py:484-507` shows that an Oxigraph input is evaluated "on a snapshot of rdflib terms" and
  the result converted back. The loop in `_evaluate_ruleset_at_one_instant` is naive: every general rule is re-run in
  full until a whole pass adds nothing. There is no delta, no index choice, no join ordering beyond rdflib's.
  So the premise "SRL runs over Oxigraph" is only true at the API edge.
* **SHACL 1.2 Inference Rules** (`shacl_engine/rules.py`; draft [shacl12-inference-rules](https://www.w3.org/TR/shacl12-inference-rules/),
  2026-10-28 at fetch time) run `sh:SPARQLRule` CONSTRUCTs through pyoxigraph on a materialised `OxGraph` (its own
  docstring: SPARQL "runs on a materialised `OxGraph` (base copy plus inferred), built once per `InferredView` and kept
  in step incrementally"). That is store-native for matching, but: the iteration is naive (rerun all rules in a layer
  until nothing new), a rule is per focus node unless global, there is no negation semantics beyond what the author
  gets from `FILTER NOT EXISTS` and `sh:layer` ordering, and a rule set is SHACL-graph syntax (verbose; one
  `sh:SPARQLRule` plus prefixes per rule).

### 5.2 The rule sets

**RDFS** (RDF Semantics rules, only the non-trivial ones; rdfs1, rdfs4 and the axiomatic triples are bookkeeping):

```
# rdfs2 / rdfs3 / rdfs5 / rdfs7 / rdfs9 / rdfs11, as SRL
RULE { ?x rdf:type ?c }          WHERE { ?p rdfs:domain ?c . ?x ?p ?y . }
RULE { ?y rdf:type ?c }          WHERE { ?p rdfs:range  ?c . ?x ?p ?y . }
RULE { ?p rdfs:subPropertyOf ?r } WHERE { ?p rdfs:subPropertyOf ?q . ?q rdfs:subPropertyOf ?r . }
RULE { ?x ?q ?y }                WHERE { ?p rdfs:subPropertyOf ?q . ?x ?p ?y . }
RULE { ?x rdf:type ?d }          WHERE { ?c rdfs:subClassOf ?d . ?x rdf:type ?c . }
RULE { ?c rdfs:subClassOf ?e }   WHERE { ?c rdfs:subClassOf ?d . ?d rdfs:subClassOf ?e . }
```

Plus rdfs6/rdfs8/rdfs10/rdfs12/rdfs13 (reflexivity and class-of-X typing; one-line rules, e.g.
`{ ?c rdfs:subClassOf ?c } WHERE { ?c a rdfs:Class }`). SRL expresses all of these directly. rdfs1 (`?lit` of datatype
`D` has type `D`) and rdfs4a/b (every term is a `rdfs:Resource`) put a literal in the *object* position only, which is
fine, but the generalised-RDF case (literal subject) is dropped by SRL itself (`_eval_rule` skips literal subjects),
which also matches the library's own `legal_rdf_triples` filter. The `_NoHiddenSameAsRDFSSemantics` hack in the
current `entailment.py` (suppress owlrl's one-time RDFS rules that add `owl:sameAs`-ish noise) disappears because we
choose which rules to include.

**OWL 2 RL**: the [Profiles tables](https://www.w3.org/TR/owl2-profiles/#Reasoning_in_OWL_2_RL_and_RDF_Graphs_using_Rules)
split three ways.

| Group | Rules | SRL / SHACL rules? |
|---|---|---|
| Plain triple joins | `eq-sym`, `eq-trans`, `eq-rep-s/p/o`, `prp-dom`, `prp-rng`, `prp-fp`, `prp-ifp`, `prp-irp`, `prp-symp`, `prp-asyp`, `prp-trp`, `prp-spo1`, `prp-eqp1/2`, `prp-pdw`, `prp-inv1/2`, `cls-thing`, `cls-nothing1/2`, `cls-com`, `cls-svf1/2`, `cls-avf`, `cls-hv1/2`, `cls-maxc1/2`, `cls-maxqc1-4`, `cax-sco`, `cax-eqc1/2`, `cax-dw`, `scm-cls`, `scm-sco`, `scm-eqc1/2`, `scm-op`, `scm-dp`, `scm-spo`, `scm-eqp1/2`, `scm-dom1/2`, `scm-rng1/2`, `scm-hv`, `scm-svf1/2`, `scm-avf1/2`, `scm-int`, `scm-uni` (the last two partly list-based) | Yes, one rule each. Inconsistency rules (`eq-diff1`, `prp-irp`, `prp-asyp`, `prp-pdw`, `cls-nothing2`, `cls-com`, `cls-maxc1`, `cax-dw`) derive a marker triple such as `[] a rl:Inconsistent ; rl:rule "cax-dw" ; rl:subject ?x`. That is monotone and needs no new SRL feature, but SRL heads mint a fresh blank node per solution on every re-evaluation, so use a deterministic IRI built with `IRI(CONCAT(...))` in an assignment, or report with the offending triple instead of a node, to keep the fixpoint terminating |
| List-valued | `prp-spo2` (property chains), `prp-key`, `prp-adp`, `cls-int1/2`, `cls-uni`, `cls-oo`, `cax-adc`, `eq-diff2/3`, `scm-int`, `scm-uni`, `scm-eqc2` over lists | Expressible only by recursion over `rdf:first`/`rdf:rest`. Example, `cls-int1` (x has every class in the intersection list): derive `rl:allTypes(?x, ?list)` with a base rule on `rdf:nil` (needs a candidate `?x`, supplied by the head of the list via the first class) and a step rule `rl:allTypes(?x,?r) <- ?l rdf:first ?c ; rdf:rest ?r ; ?x a ?c ; rl:allTypes(?x,?r)` then `?x a ?I <- ?I owl:intersectionOf ?l . rl:allTypes(?x,?l)`. This is monotone Datalog so it fits SRL's stratified-negation language with only auxiliary predicates, no new features. Property chains of arbitrary length are the same pattern with a pair-valued helper. The alternative the other implementations use is to fix a maximum arity, which is not complete |
| Datatype | `dt-type1`, `dt-type2`, `dt-eq`, `dt-diff`, `dt-not-type` | Partly. `dt-type2` and `dt-not-type` need "this literal is in the lexical space of D". SPARQL can test only by casting (`xsd:integer(STR(?l))` errors become unbound); there is no general lexical-validity function. `dt-eq`/`dt-diff` need value-space equality across datatypes, which SPARQL `=` gives but only per pair of literals present in the graph. owlrl and Growl skip `dt-eq`/`dt-diff`, so nothing is lost relative to the status quo; and the starlayer-wide issue that Oxigraph normalises lexical forms on store (issue #190, cited in the Python warning) means lexical-space checks are unreliable over an Oxigraph store whatever engine runs |

What SRL cannot express that OWL 2 RL needs: (a) **checked existential quantification over lists** without recursion
helpers (workable as above); (b) **universal checks** such as `cls-avf` for "all values" are fine, but "not exists" in
a recursive stratum is refused by the stratifier, as it should be (OWL 2 RL has none, so no problem); (c) **lexical
validity of a literal** (above); (d) **inconsistency as a first-class outcome**: the OWL 2 Direct regime says an
inconsistent ontology MUST be reported, owlrl reports via `err:ErrorMessage` nodes. In SRL this is a marker triple the
caller must check after `infer()`; there is no abort-on-derive construct; (e) **disjunction in the head or negative
heads** do not occur in RL, so no problem; (f) **`owl:sameAs` blow-up**: `eq-rep-*` copies every triple of every
equivalent individual, which is the classic RL performance trap and an argument for not materialising it in the same
pass (RDFox and others use special handling **(memory, unverified)**). (g) **Triple terms**: SRL's AST has triple-term
patterns in rules, and `_srl_ast.py` already carries RDF 1.2 terms, so a rule may *match* `<<( s p o )>>`; OWL 2 RL
itself says nothing about them, so the only decision is to treat `rdf:reifies` triples as ordinary data (what
`_rdflib_bridge` does by decomposition).

### 5.3 What the library would need

1. **A store-native, semi-naive SRL evaluator** (the real gap). Compile each rule to a SPARQL query over the store
   (body to `WHERE`, head to `CONSTRUCT` template, `NOT { }` to `FILTER NOT EXISTS`, assignments to `BIND`), keep a
   delta named graph, and for each rule generate one variant per body triple pattern with that pattern restricted to
   the delta (`GRAPH <delta> { ... }`) and the others over the union. The loop is the standard semi-naive scheme and
   reuses the existing `_stratify` / dependency analysis, since only the per-rule evaluation changes. All matching
   then runs inside Oxigraph's engine, which `oxigraph-capability-matrix.md` measures at 10 to 1000x faster than
   rdflib on every operation timed. Constraints: pyoxigraph gives text in, results out, no algebra tree and no
   `initBindings` (matrix, section 0, item 2), so the compiler must emit query text; `FILTER NOT EXISTS` cost on
   large stores dominates (section 6 shows the filtered variant slower).
2. **The write path**: `Store.extend`/`bulk_extend` for the delta, or an overlay (the `InferredView` already used by
   the SHACL engine) so the base store is not touched. `update()` with `INSERT ... WHERE` is the simplest primitive.
3. **Rule sets as data files**: `docs`-visible `rdfs.srl` and `owl2rl.srl` under the package, parsed once (the repo
   already parses SRL text and validates it against SHACL shapes; for shipped rule sets validation can be skipped, as
   the 98 s measured for a six-rule set at 10k triples was evaluation (parsing was excluded from the timing)).
4. **A conformance harness**: the W3C [OWL 2 Test Cases](https://www.w3.org/TR/owl2-test/) include RL/RDF-based
   entailment and inconsistency tests (the repo already runs W3C syntax suites against Oxigraph, per recent commits;
   this would be the same pattern with owlrl as a cross-check). I did not enumerate the exact test count here.
5. **A deterministic inconsistency report** (marker IRIs, not blank nodes), and a rule-set option to exclude
   `eq-rep-*`.
6. **Triple-term handling**: keep the decomposition for the rdflib-free path or exclude `rdf:reifies` triples from the
   rule input; decide this once.

### 5.4 Expected performance relative to owlrl

Measured (section 6). A naive INSERT loop inside Oxigraph beat owlrl on RDFS at both sizes (8x at 10k, 1.5 to 2.7x at
100k) and beat the rdflib-based SRL by about 20x at 10k; `reasonable` beat everything (20x over owlrl RDFS at 100k). A
semi-naive store-native evaluator should close much of the gap to `reasonable` on this workload, but that is a
projection, not a measurement. Honest expectation: it will not reach a purpose-built Rust engine, and does not need to
if the goal is "no rdflib copy, no extra dependency" rather than "fastest".

## 6. Benchmark

Workload (generator in the session scratchpad, `bench.py`): a 364-class tree (branching 3, depth 5), 40 properties
(10 roots, 30 sub-properties), a domain and a range for each, and `N` individuals each with one `rdf:type` (leaf
class) and one random property edge. 10k total triples = 9,773 distinct; 100k = 99,773. The closure is large on
purpose (every individual gets 5 ancestor types, plus domain/range types, plus super-property edges):
84,263 new triples at 10k and 885,594 at 100k. Machine: macOS (Darwin 21.6, x86_64), Python 3.10.8, pyoxigraph 0.5.13,
rdflib 7.6.0, owlrl 7.6.2, reasonable 0.4.4. Times are wall clock of the inference call only (loading excluded;
the `reasonable` time includes its own conversion from rdflib), single run, no warm-up; treat them as order-of-magnitude. The rule set covers rdfs2, 3, 5, 7, 9, 11 only (no rdfs1,
4, 6, 8, 10, 12, 13 bookkeeping), so owlrl, which also derives `rdfs:Resource`/`rdf:type rdfs:Class`/container
and reflexive triples, adds more triples than the hand-written sets.

| Engine (input) | 10k triples (9,773) | 100k triples (99,773) | New triples |
|---|---|---|---|
| owlrl `RDFS_Semantics`, rdflib copy | 42.8 s | 367.6 s | 89,407 / 935,738 |
| owlrl `OWLRL_Semantics`, rdflib copy | 80.4 s | 677.9 s | 90,017 / 936,348 |
| SRL, six rules, `RuleSet.infer` on rdflib `Graph` (as shipped) | 98.4 s | not run at 100k; **499.3 s at 30k** (262,272 new). 3x the data cost 5x the time, so 100k would be well over an hour (projection, not measured) | 84,263 at 10k |
| pyoxigraph `Store.update`, six `INSERT ... WHERE` with `FILTER NOT EXISTS`, looped to fixpoint | 5.2 s | 237.8 s | 84,263 / 885,594 |
| pyoxigraph `Store.update`, same six without the `FILTER NOT EXISTS` (the store dedupes) | 6.2 s | 134.5 s | 84,263 / 885,594 |
| `reasonable` 0.4.4, `from_graph` on rdflib copy, `reason()` | 4.5 s | 18.1 s | returns the whole closure (99,093 / 1,035,424 triples) |

Reading it honestly: (1) the SRL engine as shipped is the slowest option by a wide margin, 2x slower than owlrl at 10k
and roughly 12x slower per triple at 30k than the Oxigraph loop at 10k; the premise that SRL is already a fast native
path is wrong today. (2) A naive SPARQL-UPDATE loop inside Oxigraph is 8x faster than owlrl at 10k but only 1.5 to
2.7x faster at 100k, because four full-join rounds re-derive 885k triples each time; it scales worse than owlrl
and needs semi-naive evaluation to be worth shipping. (3) `reasonable` is 20x faster than owlrl RDFS and 37x faster than
owlrl OWL-RL at 100k (the 38x on the project's README is in the same range, on a different workload), and it
timed only the engine on an rdflib copy, so the full cost through the wrapper would add the two conversions. Its
count is not comparable to the others because it returns base plus derived. (4) The OWL-RL regime costs owlrl
about 1.8x the RDFS-only regime here, but this data has none of the list, equality or cardinality constructs that make
OWL 2 RL expensive.

Notes. owlrl RDFS adds more triples than the six-rule sets (it also derives the bookkeeping rules); `reasonable`
returns the full triple set (base plus derived plus the RDF/OWL axioms it adds) so its count is not comparable to a
delta. The SRL result is the engine as shipped (`RuleSet.infer` on an rdflib `Graph`), timed after parsing. Neither
SPARQL-UPDATE variant is semi-naive; both re-run all six `INSERT ... WHERE` per round for four rounds (the last
round confirms nothing new), so most of their time is re-derivation of known triples. These numbers say nothing about
OWL 2 RL list rules, `owl:sameAs` or inconsistency detection, which none of the RDFS runs exercise.

## 7. Recommendation

### Decision matrix (1 = poor, 5 = good; my judgement, grounded in the sections above)

| Criterion | A. Keep owlrl on an rdflib copy | B. `reasonable` (optional backend) | C. OWL 2 RL / RDFS as SRL, native semi-naive evaluator | D. Nemo / Datalog engine | E. Contribute / wait for Oxigraph |
|---|---|---|---|---|---|
| Maintenance burden | 5 (nothing new) | 4 (thin adapter; upstream moves) | 2 (we own an engine and a rule library) | 3 (adapter; rules ours) | 1 (indefinite wait) |
| Correctness vs W3C OWL 2 RL | 4 (reference-quality, known to need repeat passes, issue #97) | 2 (documented rule gaps) | 4 if rules are the W3C table and tests run | 4 (rules ours) | n/a |
| Performance at 100k+ | 1 (section 6: 6 to 11 min for RDFS/OWL-RL) | 5 (18 s) | 3 to 4 (naive loop measured 134 to 238 s; semi-naive TBD) | 4 (claimed; not measured) | n/a |
| RDF 1.2 triple terms | 1 (decompose) | 1 (decompose) | 4 (SRL AST already has them; store-native) | 2 (no RDF 1.2) | 3 |
| Dependencies | rdflib + owlrl (optional) | rdflib + reasonable (optional) | none beyond pyoxigraph | new native dep, python packaging unconfirmed | none |
| Optional-dependency story | exists (`[reasoning]` extra) | same extra | no extra needed | new extra | none |
| Covers OWL 2 DL | no | no | no | no | no |

OWL 2 DL classification stays with HermiT/rustdl whichever row is chosen; none of the RL engines do it. Adding
whelk (EL) via py-horned-owl is a cheap extra for large biomedical-style TBoxes, but it classifies an ontology, not a
dataset, so it does not replace anything above.

### Staged path

1. **Now (no behaviour change):** document that `infer()` for RDFS/OWL-RL is a three-copy owlrl path, and that the
   SHACL engine only needs the delta. Add the benchmark above to `benchmarks-graph/` so regressions are visible.
2. **Prototype 1 (days):** a `engine="reasonable"` option on `infer()` for the OWL-RL regime: feed
   `g.triples()` as 3-tuples (decomposed as today), take `reason()`'s output, subtract the base. Gate by profile:
   if the data uses any rule `reasonable` does not implement (`owl:hasKey`, `maxCardinality`, `owl:oneOf` in
   `cls-oo`, `owl:AllDifferent`, `owl:NegativePropertyAssertion`, `owl:propertyDisjointWith` with assertions) fall back to
   owlrl. Differential-test against owlrl on the existing fixtures and on W3C RL tests.
3. **Prototype 2 (1 to 2 weeks):** the store-native semi-naive SRL evaluator on RDFS only. Success test: identical
   delta to owlrl's RDFS (modulo the bookkeeping rules we choose to omit) on the 100k set, at least 5x faster than owlrl,
   no rdflib import.
4. **Then:** the OWL 2 RL rule file, in groups (plain joins first, lists second, equality last), each group gated by
   the W3C test cases and the owlrl differential harness. Ship it as the default only when it passes everything
   owlrl passes. Keep owlrl as the oracle and the fallback, permanently, as an optional dependency used in CI.
5. **Defer:** incremental maintenance. Recompute on demand into an overlay; revisit only if users keep a closure in a
   persistent store across edits. Revisit Oxigraph upstream (a least-fixed-point operator in spareval would make C
   a thin layer) when issue #130 moves.

### Risks

* **Scope creep in C.** Owning a rule engine is a long-term cost. Mitigation: stage 3 is RDFS only and gated by a
  measured win; stop there if the win is not real.
* **SPARQL-text generation limits.** No algebra access or init bindings in pyoxigraph; `FILTER NOT EXISTS` cost on
  large stores (measured); `bulk_extend` versus transactional update semantics need checking. A prototype will show
  whether the semi-naive delta-graph approach really beats the naive loop; I have not built it.
* **`reasonable` incompleteness and young maintenance model.** One maintainer, alpha pre-release in progress, rule
  gaps, partial RDFS. Never make it the sole implementation.
* **Lexical-form normalisation.** Oxigraph rewrites literal lexical forms on store (upstream oxigraph#526, #1989);
  datatype-lexical-space rules therefore cannot be trusted over a store, for any engine.
* **owl:sameAs / eq-rep blow-up** and inconsistency reporting differ between engines; define the contract
  (marker triples, exclusion switch) before swapping engines.
* **Spec drift.** SRL (2026-10-14 WD in the code), SHACL 1.2 Rules (2026-10-28 WD) and SPARQL 1.2 Entailment Regimes
  (2026-04-09 WD) are all drafts. A rule set expressed in SRL tracks a moving language; keeping the rule files in
  SRL text (parsed by the repo's own parser) isolates that to the parser.
* **Unverified items.** Licences and status marked (memory) in section 3; whelk-rs licence; the Motik et al.
  numbers; the "Oxigraph Nova" fork; the exact OWL 2 RL rule count in the W3C tables (78 is the figure Growl's README
  uses; I did not recount).

### What needs prototyping before any decision is final

(a) `reasonable` fed from pyoxigraph triples, with the rule-gap fallback, differential-tested against owlrl;
(b) the semi-naive delta-graph SRL evaluator on pyoxigraph, RDFS first; (c) an owl:sameAs-heavy and a list-heavy
(intersection, property chain) benchmark, because the RDFS run here does not touch the expensive OWL 2 RL cases;
(d) the W3C OWL 2 RL conformance run for whichever engine becomes default.

## 8. Sources

* Oxigraph: <https://github.com/oxigraph/oxigraph/issues/130>, <https://github.com/oxigraph/oxigraph/pull/1692>,
  <https://github.com/oxigraph/oxigraph/pull/1679>, <https://github.com/oxigraph/oxigraph/issues/1681>,
  <https://github.com/oxigraph/oxigraph/issues/1737>, <https://pypi.org/project/pyoxigraph/>
* Reasoners: <https://github.com/RDFLib/OWL-RL>, <https://github.com/gtfierro/reasonable>,
  <https://pypi.org/project/reasonable/>, <https://github.com/trivyn/growl>, <https://github.com/MaastrichtU-IDS/rustdl>,
  <https://py-horned-owl.readthedocs.io/latest/reasoner.html>, <https://pypi.org/project/py-whelk/>,
  <https://ontologos.readthedocs.io/en/latest/comparison/>, <https://github.com/knowsys/nemo>,
  <https://iccl.inf.tu-dresden.de/web/Inproceedings3466>,
  <https://drops.dagstuhl.de/storage/08tgdk/tgdk-vol002/tgdk-vol002-issue002/html/TGDK.2.2.9/TGDK.2.2.9.html>
* Specs: <https://www.w3.org/TR/sparql12-entailment/>, <https://www.w3.org/TR/sparql12-rl/>,
  <https://www.w3.org/TR/shacl12-inference-rules/>, <https://www.w3.org/TR/owl2-profiles/>,
  <https://www.w3.org/TR/rdf11-mt/>, <https://www.w3.org/TR/owl2-test/>
* Repo files read: `starlayer/graph/oxgraph/helpers/entailment.py`, `starlayer/graph/oxgraph/_rdflib_bridge.py` (head),
  `starlayer/shacl_engine/entailment.py`, `starlayer/shacl_engine/rules.py`, `starlayer/sparql/srl.py`,
  `starlayer/sparql/srl_eval.py`, `starlayer/sparql/_srl_ast.py`, `starlayer/graph/graph/owl_dl_rustdl.py` (head),
  `docs/working/oxigraph-capability-matrix.md`, `docs/guides/03b-srl-sparql-rules.ipynb`.
