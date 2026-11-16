"""``align_blank_nodes``: the blank nodes of one graph paired with those of another, so that ``diff`` and the operators can compare them."""

from __future__ import annotations

import pytest
from starlayer.graph import (
    StarLayerDataset,
    StarLayerGraph,
    align_blank_nodes,
    diff,
    isomorphic,
)

PREFIX = "@prefix ex: <http://example.org/> . "
BASE = "ex:a ex:p [ ex:q 1 ] . ex:b ex:p [ ex:q 2 ] . ex:c ex:p [ ex:q 3 ] ."
TWO = 'ex:alice ex:hasPet [ a ex:Cat ; ex:name "Tabby" ] . ex:bob ex:hasPet [ a ex:Cat ; ex:name "Tabby" ] .'
CHAIN = "ex:a ex:p [ ex:q [ ex:r [ ex:s 1 ] ] ] ."
TWINS = "ex:a ex:p [ ex:q 1 ] , [ ex:q 1 ] ."


def graph(text: str) -> StarLayerGraph:
    g = StarLayerGraph(prefixes={"ex": "http://example.org/"})
    g.parse(data=PREFIX + text, format="turtle")
    return g


def cat(owner: str, name: str, extra: str = "") -> str:
    return f'ex:{owner} ex:hasPet [ a ex:Cat ; ex:name "{name}" {extra} ] .'


# (what changed, old, new, triples the delta adds, triples it removes): the smallest change that turns old into new
CASES = [
    ("nothing", BASE, BASE, 0, 0),
    ("an extra triple on one node", BASE, "ex:a ex:p [ ex:q 1 ] . ex:b ex:p [ ex:q 2 ; ex:r 9 ] . ex:c ex:p [ ex:q 3 ] .", 1, 0),
    ("a group removed", BASE, "ex:b ex:p [ ex:q 2 ] . ex:c ex:p [ ex:q 3 ] .", 0, 2),
    ("a value changed", BASE, "ex:a ex:p [ ex:q 1 ] . ex:b ex:p [ ex:q 2 ] . ex:c ex:p [ ex:q 4 ] .", 1, 1),
    ("a group added", BASE, BASE + " ex:d ex:p [ ex:q 5 ] .", 2, 0),
    ("identical siblings, one more", TWINS, "ex:a ex:p [ ex:q 1 ] , [ ex:q 1 ] , [ ex:q 1 ] .", 2, 0),
    ("the deepest node of a chain changed", CHAIN, "ex:a ex:p [ ex:q [ ex:r [ ex:s 2 ] ] ] .", 1, 1),
    ("two cats with the same name, unchanged", TWO, TWO, 0, 0),
    ("one of the two cats renamed", TWO, cat("alice", "Tabby") + " " + cat("bob", "Felix"), 1, 1),
    ("a third owner with a cat of that name", TWO, TWO + " " + cat("carol", "Tabby"), 3, 0),
    ("one of the two cats removed", TWO, cat("alice", "Tabby"), 0, 3),
    ("one cat gets a colour", TWO, cat("alice", "Tabby") + " " + cat("bob", "Tabby", '; ex:colour "grey"'), 1, 0),
    ("a cat replaced by a dog", TWO, cat("alice", "Tabby") + ' ex:bob ex:hasPet [ a ex:Dog ; ex:name "Rex" ] .', 3, 3),
    ("a cat moved to another owner", TWO, cat("alice", "Tabby") + " " + cat("carol", "Tabby"), 3, 3),
]


@pytest.mark.parametrize("what, old_text, new_text, added, removed", CASES, ids=[c[0] for c in CASES])
def test_the_delta_between_aligned_graphs_is_the_smallest_change(what, old_text, new_text, added, removed):
    old, new = graph(old_text), graph(new_text)
    delta = diff(old, align_blank_nodes(new, to=old).graph)
    assert (len(delta.added), len(delta.removed)) == (added, removed)
    assert isomorphic(delta.apply(old.copy()), new)  # whatever the pairing, the delta turns old into something that is new


def test_an_empty_delta_means_the_graphs_are_isomorphic():
    for what, old_text, new_text, added, removed in CASES:
        old, new = graph(old_text), graph(new_text)
        empty = not diff(old, align_blank_nodes(new, to=old).graph)
        assert empty == isomorphic(old, new) == ((added, removed) == (0, 0)), what


def test_the_pairs_say_how_each_blank_node_was_paired():
    old, new = graph(TWO), graph(cat("alice", "Tabby") + " " + cat("bob", "Felix"))
    alignment = align_blank_nodes(new, to=old)
    kinds = sorted(p.kind for p in alignment.pairs)
    assert kinds == ["approximate", "exact"] and len(alignment.pairs) == 2
    (approximate,) = alignment.of_kind("approximate")
    assert 0.5 <= approximate.score < 1 and approximate.partner is not None
    # a paired node carries the reference's label, an unmatched one a label of its own
    assert {p.partner for p in alignment.pairs} <= {t[2] for t in old.triples((None, None, None))}
    gone = align_blank_nodes(graph(TWO + " " + cat("carol", "Tabby")), to=old)
    (unmatched,) = gone.of_kind("unmatched")
    assert unmatched.partner is None and unmatched.score is None


def test_identical_siblings_are_ambiguous_and_either_pairing_gives_the_same_result():
    old, new = graph(TWINS), graph(TWINS)
    alignment = align_blank_nodes(new, to=old)
    assert [p.kind for p in alignment.pairs] == ["ambiguous", "ambiguous"]
    assert not diff(old, alignment.graph)


def test_min_overlap_decides_how_much_an_edited_node_must_keep():
    old, new = graph(TWO), graph(cat("alice", "Tabby") + " " + cat("bob", "Felix"))
    assert len(diff(old, align_blank_nodes(new, to=old, min_overlap=0.5).graph)) == 2  # one name changed
    strict = align_blank_nodes(new, to=old, min_overlap=0.9, max_changes=0)
    delta = diff(old, strict.graph)
    assert (len(delta.added), len(delta.removed)) == (3, 3)  # a different cat: removed, and another added
    assert [p.kind for p in strict.pairs].count("unmatched") == 1


def test_max_changes_pairs_a_small_node_that_lost_one_edge_whatever_the_fraction():
    # the cat has three edges (its owner, its type, its name); with the name removed it keeps two of them, 0.67 of itself
    old, new = graph(TWO), graph(cat("alice", "Tabby") + " ex:bob ex:hasPet [ a ex:Cat ] .")
    by_fraction = align_blank_nodes(new, to=old, min_overlap=0.75, max_changes=0)
    delta_by_fraction = diff(old, by_fraction.graph)  # a different cat: its three triples removed, its two added
    assert [p.kind for p in by_fraction.pairs].count("unmatched") == 1
    assert (len(delta_by_fraction.added), len(delta_by_fraction.removed)) == (2, 3)
    by_count = align_blank_nodes(new, to=old, min_overlap=0.75, max_changes=1)
    delta = diff(old, by_count.graph)
    assert (len(delta.added), len(delta.removed)) == (0, 1)
    (pair,) = by_count.of_kind("approximate")
    assert pair.changes == 1 and 0.6 < pair.score < 0.7
    # two missing edges are more than the count allows
    two_lost = align_blank_nodes(graph(cat("alice", "Tabby") + " ex:bob ex:hasPet [ ex:age 3 ] ."), to=old, min_overlap=0.75, max_changes=1)
    assert [p.kind for p in two_lost.pairs].count("unmatched") == 1


def test_the_graph_is_a_copy_with_its_prefixes_and_the_inputs_are_not_changed():
    old, new = graph(BASE), graph(BASE)
    before = set(new.triples((None, None, None)))
    result = align_blank_nodes(new, to=old).graph
    assert isinstance(result, StarLayerGraph) and dict(result.prefixes) == {"ex": "http://example.org/"}
    assert set(new.triples((None, None, None))) == before and result is not new


def test_a_blank_node_inside_a_triple_term_is_paired_too():
    text = "ex:a ex:says <<( ex:b ex:p _:z )>> . _:z ex:q 1 ."
    old, new = graph(text), graph(text)
    aligned = align_blank_nodes(new, to=old).graph
    assert not diff(old, aligned) and any(type(t[2]).__name__ == "Triple" for t in aligned.triples((None, None, None)))


def test_the_inputs_must_be_graphs_and_min_overlap_a_fraction():
    g = graph(BASE)
    with pytest.raises(TypeError):
        align_blank_nodes(StarLayerDataset(), to=g)
    with pytest.raises(TypeError):
        align_blank_nodes(g, to=StarLayerDataset())
    with pytest.raises(ValueError):
        align_blank_nodes(g, to=g, min_overlap=1.5)
    with pytest.raises(ValueError):
        align_blank_nodes(g, to=g, max_changes=-1)


# ---- a shapes graph: many blank nodes with much the same shape ---------------------------------------------------------------
def _shacl_shacl() -> StarLayerGraph:
    from pathlib import Path

    import starlayer

    g = StarLayerGraph()
    g.parse(str(Path(starlayer.__file__).parent / "starontology" / "_sources" / "vendor" / "w3c-shacl-shacl.ttl"), format="turtle")
    return g


def test_a_shapes_graph_parsed_again_has_no_difference():
    old, new = _shacl_shacl(), _shacl_shacl()
    assert len(diff(old, new)) > 100  # every triple with a blank node differs: the labels
    alignment = align_blank_nodes(new, to=old)
    assert not diff(old, alignment.graph) and all(p.kind == "exact" for p in alignment.pairs)


def test_removing_any_one_triple_of_a_shapes_graph_is_one_change():
    import random

    import pyoxigraph as ox

    old = _shacl_shacl()
    candidates = sorted((t for t in old.triples((None, None, None)) if isinstance(t[0], ox.BlankNode)), key=str)
    for triple in random.Random(5).sample(candidates, 25):
        new = old.copy()
        new.remove(triple)
        delta = diff(old, align_blank_nodes(new, to=old).graph)
        assert (len(delta.added), len(delta.removed)) == (0, 1)
