# Shape fragments and `extract_subgraph()`

Written 2026-10-21 for GitHub issue #11 ("Shape Fragments"). Status: research and a test; no library change.

## Sources

- **Paper:** Delva, Dimou, Jakubowski, Van den Bussche, *Shape Fragments*, arXiv 2112.11796 (read in full, 26 pages).
- **Companion specification:** github.com/Shape-Fragments/shape-fragments-spec, a W3C-style document that follows the SHACL recommendation (read).
- **Reference implementations by the authors** (not read, not used): `pySHACL-fragments` (a 2021 fork of the engine we wrap; 482 of 4501 lines changed; no complex paths), `SHACL2SPARQL` (translation to SPARQL).

## What a shape fragment is

For a set of shapes S, the fragment of a graph G is the union, over every node `v` and every shape `phi` in S (a shape together with its target), of the **neighborhood** `B(v, G, phi)`: the triples that show `v` conforms to `phi`. It is empty if `v` does not conform. The neighborhood is defined constructor by constructor (the paper's Table 2, the specification's sections 5 to 7), is deterministic, and is deliberately minimal. Negation is pushed down to atomic shapes first.

Two results make it more than a convention:

- **Sufficiency Lemma:** any graph between the neighborhood and G still satisfies `phi` at `v`. A processor may therefore return *more* than the neighborhood (the "relaxation property").
- **Conformance Theorem:** if G conforms to the shapes graph, so does its fragment.

## How `extract_subgraph()` compares

| Construct | Paper / specification | `extract_subgraph()` |
|---|---|---|
| Target triples (`v a :Person`) | included (`phi AND tau`; spec 5.2) | **left out** |
| `sh:minCount`, `sh:maxCount`, `sh:node`, `sh:property`, `sh:and` | path triples to the value nodes, recursing | same |
| `sh:or` | union of the neighborhoods of the disjuncts that hold | same (every passing disjunct) |
| `sh:qualifiedMinCount` | only values that satisfy the qualified shape | same, when it is the only constraint on the property |
| `sh:class`, `sh:datatype`, `sh:nodeKind` on a value | the triples that make the value satisfy it (spec 6.1), e.g. `(:Alice a :Student)` | **class evidence left out** |
| `sh:not`, negated cardinality, not-disjoint, not-equals | defined (spec 7, Table 2) | **contributes nothing** (a documented gap) |
| `sh:equals` | the paths of both sides | same |
| `sh:disjoint`, `sh:lessThan`, `sh:closed`, `sh:uniqueLang` | empty (they cannot be broken by removing triples) | includes the second path (larger, harmless) |
| `sh:xone` | derived from `or` and `not`, so it carries the negated evidence | only the passing disjunct |
| Stated guarantee | Conformance Theorem, Sufficiency Lemma | none |

Larger-than-necessary output is allowed by the Sufficiency Lemma. Missing evidence is not.

## Measured

`tests/shacl/integration/test_shape_fragments_paper.py` runs the paper's own examples and one case per constructor, keeping the focus node as an explicit target and asking whether it still conforms inside the fragment. **4 of 11 fail** (the workshop shape, a plain `sh:class`, `HappyAtWork` with `sh:not`/`sh:disjoint`, and `sh:not` around `sh:maxCount`); the other seven, including the person/address shape and Example 3.8, pass. Each failure is a strict xfail naming the paper section. A fifth xfail records the target-triple difference. A first version of this check passed everything: without the target triples, the fragment's nodes are no longer targets, so validation holds vacuously. That is why the focus node is kept as a target.

## Recommendation (not done)

1. **Make the paper's Conformance Theorem the contract** and keep this test as its oracle; extend it to generated shapes.
2. **Fix the two real gaps:** evidence for value-type constraints (`sh:class` at least), and negation (push `sh:not` down as the paper does).
3. **Decide about the target triples** (an option, probably default on, since the paper and the specification include them).
4. **Do not depend on `pySHACL-fragments`** (stale, covers less than we do on paths); use the paper's Table 2 and the specification as the definition instead.
5. Naming: the whole-shapes-graph mode of `extract_subgraph()` is what the paper calls a *shape fragment*.
