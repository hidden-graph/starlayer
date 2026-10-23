# Shape fragments and `extract_subgraph()`

Written 2026-10-21 for GitHub issue #11 ("Shape Fragments"). Status: research (2026-10-21); the gaps it found were fixed 2026-10-23, see "Outcome" at the end.

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
| Target triples (`v a :Person`) | included (`phi AND tau`; spec 5.2) | included by default (`include_targets=True`) |
| `sh:minCount`, `sh:maxCount`, `sh:node`, `sh:property`, `sh:and` | path triples to the value nodes, recursing | same |
| `sh:or` | union of the neighborhoods of the disjuncts that hold | same (every passing disjunct) |
| `sh:qualifiedMinCount` | only values that satisfy the qualified shape | same, when it is the only constraint on the property |
| `sh:class`, `sh:datatype`, `sh:nodeKind` on a value | the triples that make the value satisfy it (spec 6.1), e.g. `(:Alice a :Student)` | included (the value's `rdf:type` path) |
| `sh:not`, negated cardinality, not-disjoint, not-equals | defined (spec 7, Table 2) | the negated shape's full trace (a superset of the paper's neighborhood, allowed by the Sufficiency Lemma) |
| `sh:equals` | the paths of both sides | same |
| `sh:disjoint`, `sh:lessThan`, `sh:closed`, `sh:uniqueLang` | empty (they cannot be broken by removing triples) | includes the second path (larger, harmless) |
| `sh:xone` | derived from `or` and `not`, so it carries the negated evidence | the passing disjunct, plus the full trace of the others |
| Stated guarantee | Conformance Theorem, Sufficiency Lemma | the Conformance Theorem, checked by `test_shape_fragments_paper.py` |

Larger-than-necessary output is allowed by the Sufficiency Lemma. Missing evidence is not.

## Measured

`tests/shacl/integration/test_shape_fragments_paper.py` runs the paper's own examples and one case per constructor, keeping the focus node as an explicit target and asking whether it still conforms inside the fragment. Before the fix, 4 of 11 failed (the workshop shape, a plain `sh:class`, `HappyAtWork` with `sh:not`/`sh:disjoint`, and `sh:not` around `sh:maxCount`) and the target triples were missing. A first version of this check passed everything: without the target triples, the fragment's nodes are no longer targets, so validation holds vacuously. That is why the focus node is kept as a target.

## Outcome (2026-10-23)

The research recommended five things; the first three were done, the last two stand.

1. The Conformance Theorem is the contract. The test file holds the paper's examples, one case per constructor, the combined Example 3.8 schema, target kinds, and a randomized check (Hypothesis) over generated shapes and graphs. Removing class evidence, or the `sh:not` branch, makes it fail.
2. Class evidence and negation are fixed. Negation returns the negated shape's full trace, a superset of the paper's minimal neighborhood, which the Sufficiency Lemma allows.
3. Target triples are on by default; `include_targets=False` switches them off.
4. Do not depend on `pySHACL-fragments`; Table 2 and the specification are the definition.
5. The whole-shapes-graph mode of `extract_subgraph()` is what the paper calls a *shape fragment*.
