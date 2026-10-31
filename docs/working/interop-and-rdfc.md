# Interoperability and canonicalisation over pyoxigraph (2026-10-31)

Branch `mig-interop`. New files only: `starlayer/graph/interop.py`, `starlayer/graph/rdfc_native.py`, tests
`tests/graph/unit/test_interop.py`, `test_rdfc_native.py` (helper `_interop_corpus.py`), vendored W3C suite
`tests/graph/vendor/rdfc10/`. pyoxigraph 0.5.13. Nothing existing was edited.

## API

`starlayer.graph.interop` (pyoxigraph terms; inputs may be a `Store`, `Dataset` or iterable of `Quad`/`Triple`):

| Function | Does |
|---|---|
| `to_basic(quads, *, bnode_prefix=None)` | Basic encoding; returns a list of quads with no triple term. No triple term in: returned unchanged. Refuses input that has triple terms and already uses the `rdf:PropositionForm` vocabulary. |
| `from_basic(quads, *, accept_iri_nodes=False)` | Inverse. Refuses ambiguous or incomplete structure (`BasicEncodingError`). `accept_iri_nodes` reads the old content-hash `tt:` IRIs. |
| `encode_directions(quads, policy)` / `decode_directions(quads)` | Base-direction policy (below). |
| `export_rdf11(store_or_quads, format, destination=None, prefixes=None, base_iri=None, *, bnode_prefix=None, direction_policy="datatype")` | `to_basic`, then the direction policy, assert no triple term or directional literal remains, serialise (Turtle, TriG, N-Triples, N-Quads, RDF/XML; names or `RdfFormat`). Triple-only formats refuse named graphs. Returns bytes when no destination. |

`starlayer.graph.rdfc_native`:

| Function | Does |
|---|---|
| `isomorphic(a, b, *, basic=False)` | Native `Dataset.canonicalize(RDFC_1_0)` on copies, compare. Graph names count. `basic=True` encodes first. |
| `canonical_quads(ds, *, algorithm="sha256", basic=True)` | Canonical quads (sorted); `algorithm` is `"sha256"`, `"sha384"` or the two `CanonicalizationAlgorithm.RDFC_1_0*` values. |
| `canonical_nquads(...)` | Canonical N-Quads text, sorted lines. |
| `canonical_hash(...)` | Hex SHA-256 (64 chars) or SHA-384 (96) of that text. |

Published canonical forms apply the basic encoding first (`basic=True`), so they rest on the draft's rewriting and then
RDFC-1.0. The form is defined by the draft and may change with it.

## The draft's rules, as implemented

From https://w3c.github.io/rdf-interop/spec/ (Editor's Draft, non-normative), read 2026-10-31:

- "consists of repeating the following steps until no triple term appears in the graph"; "minting a fresh blank node b
  (i.e., a blank node not yet in use in the graph)"; "replacing all occurrences of tt appearing in the graph with b";
  added triples `(b, rdf:type, rdf:PropositionForm)`, `(b, rdf:propositionFormSubject, s)`,
  `(b, rdf:propositionFormPredicate, p)`, `(b, rdf:propositionFormObject, o)`.
- Nested (algorithm `basic-encode-triple-term`, step 4.2.1): "Let b', M' and G' be the result of invoking
  basic-encode-triple-term passing o as t and M_i." The inner term is encoded first; its node is the outer's object.
- Repeated identical terms (same algorithm, step 3): "Let b be the blank node associated with t in M_i, if any." One node
  per distinct term, shared by every occurrence. Prose does not say this; only the algorithm does.
- Datasets: "Basic encoding an RDF dataset consists of basic encoding its default graph and each of its named graph. In this
  case, the fresh blank node assigned to each triple term must not be used in any graph of the dataset."
- Preservation: equivalent "only when the input graph either has no triple term appearing in it".
- Silent on: which graph holds the description triples, node naming, base direction.

Choices where the draft is silent: the description triples go in the graph where the term occurs; the map M is per graph (the
same term in two graphs gets two nodes, distinct from every input blank node); `bnode_prefix=None` mints random blank nodes,
a prefix mints `<prefix>0, 1, ...` in input order skipping labels in use. RDF 1.2 allows triple terms only as objects, so only
the object position is rewritten. `from_basic` output order differs from the input order, but the set of quads is the same.

## Base-direction literals

RDF 1.1 has no `"x"@en--ltr`; the draft does not mention it. Policy, `direction_policy` on `export_rdf11`:

- `"datatype"` (default): `"x"^^<https://github.com/hidden-graph/starlayergraph/ns/dirlang#en--ltr>`. Same namespace and
  `<lang>--<dir>` local name as `model/encoding.py` (`encode_dirlang_datatype`; a test asserts the equality). Lossless,
  reversed by `decode_directions`.
- `"error"`: raise `ValueError`.
- `"drop"`: keep `"x"@en`, discard direction (lossy).

## Differences from the old encoding

`model/encoding.py` has **no `to_basic()`/`from_basic()` functions** (the docs refer to them, the code does not): the old
encoding is the graph classes' internal representation, readable as raw triples (`rdflib.Graph.triples(g, ...)`).
Same vocabulary, same sharing of identical terms, same direction datatype. Differences: node naming (content-hash IRI under
`tt:` versus fresh blank node), and the old scheme shares a term across a whole dataset's graphs by name while the draft encodes
per graph. Checked on three ground and nested corpora: old raw triples with `tt:` read as blank nodes are isomorphic to
`encode_directions(to_basic(x))`, and `from_basic(old, accept_iri_nodes=True)` recovers the original.

## Results

Tests: 128 passed, 1 skipped (the W3C poison negative test) across the two new files; ruff clean on the new files (the 85
repository errors are elsewhere).

- **W3C RDFC-1.0 suite** (https://github.com/w3c/rdf-canon/tree/main/tests, commit 15619df, vendored with its licence):
  64 `RDFC10EvalTest` cases, **64/64 pass** natively (including the SHA-384 test075, test060 escaping, named graphs, and
  the blank-node-graph-name cases). Not run: 22 `RDFC10MapTest` (need the issued-identifier map, which pyoxigraph does not
  expose), and 1 negative test.
- **Poison test074** (10-node clique, must raise): pyoxigraph **does not finish** (killed after 20 s). It has no
  denial-of-service defence, which RDFC-1.0 section 7.1 requires. Do not canonicalise untrusted input without an outer limit;
  `rdfc.py` raises `CanonicalizationComplexityError` here.
- **Isomorphism verdicts**, three methods plus a brute-force oracle (all blank-node bijections), 2,500 random datasets
  (default and named graphs, blank-node graph names, triple terms nested two deep, directional literals, 35 percent relabelled,
  45 percent one-quad mutations, 20 percent unrelated; 932 truly isomorphic): native, native-after-basic-encoding and
  old `compare.isomorphic`: **0 disagreements with the oracle, none among themselves.** Symmetric cases (4-cycle versus two
  2-cycles, with and without triple-term wrapping): all three correct. Hypothesis reruns this in the test suite.
- **Properties** (150 Hypothesis examples each): `from_basic(to_basic(x)) == x`; canonical form invariant under relabelling
  and quad order; two datasets differing only in the identity of a triple term's blank node (or the encoding's fresh node)
  are isomorphic and hash the same; `export_rdf11` output has no `<<`.
- **rdf-canon issue #233** (blank-node graph name): **not reproduced.** 2,456 random datasets with a blank-node graph name plus
  hand-built symmetric ones, each relabelled: canonical form identical in all (native 0 differences; old rdfc.py also 0).
  The issue's own example was not located, so this is evidence, not proof.

## Disagreements and verdicts

One class, found by comparing canonical **strings** (not verdicts): old `rdfc.py` and native agree exactly on 3,953 of 3,953
random tt-free datasets where no quad repeats a blank node, and differ on 701 of 2,047 where one does (a blank node as both
subject and graph name, or a self-loop `_:a p _:a` alongside other blank nodes). Minimal case `_:b0 <p> _:b2 _:b0 .`: native
`_:c14n0 <p> _:c14n1 _:c14n0`, old `_:c14n1 <p> _:c14n0 _:c14n1`. Cause: old step 2 appends a quad once per blank-node
*component*, so a quad with the same node twice is counted twice in its first-degree hash. The spec text is ambiguous ("For each
blank node that is a component of Q, add a reference to Q"; its gloss says "the set of quads of which it is a component").
Native counts once. Hand check: SHA-256 of b0's first-degree line sorts before b2's, giving b0 = c14n0, the native answer, under
the set reading. **Verdict: native is right under the set reading, which the spec's own gloss supports; old is right only
under a reading with duplicates.** The W3C suite cannot decide it (its self-link tests 018 and 019 pass under both). Not
verified against a third implementation: an attempt to run `rdf-canonize` (JavaScript) was blocked by the sandbox. Worth an
upstream rdf-canon issue; until settled, canonical hashes of datasets with such quads may not match other implementations.
The old code's verdicts are unaffected (isomorphism does not depend on the labels), only its labels.

## What the existing code can retire and what must stay

- **`model/encoding.py` `tt:` family** (hash, memo, `encoding_triples`, `ENCODING_*`): retires with the graph classes once
  storage is Oxigraph; `interop.py` replaces the interchange role. **Keep** the DIRLANG helpers while any code reads old data;
  `interop.DIRLANG_NS` mirrors them.
- **`rdfc.py` (410 lines)**: its isomorphism and canonical-form role is covered by `rdfc_native` (64/64 W3C, no disagreement on
  verdicts). Retire after the label disagreement above is settled and **only if a denial-of-service limit is supplied
  elsewhere**: `rdfc.py`'s permutation budget is the only protection against poison input. Keep (or port the budget as a
  guard in front of `canonical_*`) for untrusted data. It also exposes issued identifiers (map tests), which pyoxigraph does not.
- **`compare.py` (282 lines)**: `isomorphic`, `to_canonical_hash` are replaced by `rdfc_native`. `graph_diff`, `to_isomorphic`
  return rdflib graphs and rely on rdflib's algorithm; they have no native equivalent and stay until their callers are gone
  (or are rebuilt as a quad-set difference after canonicalisation).
