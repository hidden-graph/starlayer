# 02e Working with a Graph's Contents: material removed from section 8 (Matching blank nodes)

Parked 2026-11-16. Section 8 of [02e](02e-graph-contents.ipynb) was cut to one introduction and one example. This is the rest: the first example (a document parsed twice, `isomorphic`, `rename_blank_nodes=False`), what "the same blank node" means, `min_overlap` and `max_changes`, and what the result guarantees. The details are also in the docstring of `starlayer.graph.bnode_align`. The cell ids are the ids the cells had in the notebook.

<!-- old cell a2e5000a, code -->

```python
from starlayer.graph import isomorphic

doc = "@prefix ex: <http://example.org/> . ex:a ex:p [ ex:q 1 ] ."
x, y = StarLayerGraph(), StarLayerGraph()
x.parse(data=doc, format="turtle")
y.parse(data=doc, format="turtle")
print("1. the same document parsed twice: the blank nodes get different labels")
print("   triples of x that are not in y:", len(x - y), "of", len(x))
print("   but the graphs are isomorphic:", isomorphic(x, y))

doc = "@prefix ex: <http://example.org/> . ex:a ex:p _:n . _:n ex:q 1 ."
x, y = StarLayerGraph(), StarLayerGraph()
x.parse(data=doc, format="turtle", rename_blank_nodes=False)
y.parse(data=doc, format="turtle", rename_blank_nodes=False)
print("\n2. rename_blank_nodes=False keeps the label _:n, so the blank nodes match")
print("   triples of x that are not in y:", len(x - y))
```

Output:

```
1. the same document parsed twice: the blank nodes get different labels
   triples of x that are not in y: 2 of 2
   but the graphs are isomorphic: True

2. rename_blank_nodes=False keeps the label _:n, so the blank nodes match
   triples of x that are not in y: 0
```

<!-- old cell a2e5000c, markdown -->

### Which blank node is which

Two blank nodes are the same when they have the same content and the same context. Content alone is not enough: if Alice and Bob each have a cat named Tabby, the two cats have the same content, but they are two cats, and what tells them apart is who they belong to.

`align_blank_nodes(graph, to=reference)` pairs the blank nodes of `graph` with those of `reference` and returns an `Alignment`:

- `alignment.graph` is a copy of `graph` in which the blank nodes that were paired carry the labels of their partners in `reference`. Use it in place of `graph`: `diff(reference, alignment.graph)`, `reference - alignment.graph` and so on. A delta made this way is written in the reference's labels, so it applies to the reference.
- `alignment.pairs` has one entry for each blank node of `graph`, with how it was paired: `exact` (the same content and context), `ambiguous` (several blank nodes that cannot be told apart, such as identical siblings, so any pairing gives the same result), `approximate` (not the same, but alike enough: see below) or `unmatched` (a new blank node). `alignment.of_kind("approximate")` lists the pairs of one kind.

In the example, Bob's cat is renamed.

<!-- old cell a2e5000e, markdown -->

### How alike is alike enough

A blank node that was edited does not have the same content, so it can't be an exact match. It is paired as `approximate` when it keeps enough of its edges (the triples it is in) and is reached from the same place as before, the same owner in the example. Two settings decide what enough is:

- `min_overlap` (0.5 by default) is the fraction of the larger node's edges that the two nodes share.
- `max_changes` (1 by default) is how many of the larger node's edges the other node may lack, whatever the fraction. A node with three edges that loses one keeps two thirds of them, which a `min_overlap` of 0.75 would refuse. `max_changes=1` still pairs it.

A node that is not paired is reported as removed, and the node it might have been in the other graph as added. In the example, Bob's cat loses its name.

<!-- old cell a2e5000f, code -->

```python
lost = StarLayerGraph(prefixes={"ex": "http://example.org/"})
lost.parse(data=prefix + 'ex:alice ex:hasPet [ a ex:Cat ; ex:name "Tabby" ] . ex:bob ex:hasPet [ a ex:Cat ] .', format="turtle")

for min_overlap, max_changes in ((0.75, 0), (0.75, 1)):
    alignment = align_blank_nodes(lost, to=old, min_overlap=min_overlap, max_changes=max_changes)
    delta = diff(old, alignment.graph)
    print(f"min_overlap={min_overlap}, max_changes={max_changes} -> removed: {len(delta.removed)}, added: {len(delta.added)} | pairs:", sorted(pair.kind for pair in alignment.pairs))
```

Output:

```
min_overlap=0.75, max_changes=0 -> removed: 3, added: 2 | pairs: ['exact', 'unmatched']
min_overlap=0.75, max_changes=1 -> removed: 1, added: 0 | pairs: ['approximate', 'exact']
```

<!-- old cell a2e50010, markdown -->

### What to rely on

- An empty delta from `diff(reference, alignment.graph)` means the two graphs are isomorphic, and a delta that is not empty means they are not. No pairing can hide a real difference.
- Applying the delta to `reference` gives a graph that is isomorphic to `graph`.
- A poor pairing does not make the delta wrong, only larger than it needs to be. Look at `alignment.pairs`: an `approximate` pair may be a wrong pairing, and an `unmatched` node may be one that was missed.
- The pairing is a heuristic, because finding the best match between the blank nodes of two graphs is a hard problem in general. It works on graphs, not on datasets.
