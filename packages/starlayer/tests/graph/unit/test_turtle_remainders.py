"""Leftovers of issues #93 and #94 in the hand-written Turtle 1.2 parser."""

import pytest
from starlayer import StarLayerDataset


def _quads(text):
    ds = StarLayerDataset()
    ds.parse(data="PREFIX : <http://x/>\n" + text, format="turtle12")
    return ds


@pytest.mark.parametrize(
    "text",
    [
        ':t :val <<( :a :q "x"^^<http://e/d> )>> .',
        ':t :val <<( :a :q "01"^^<http://www.w3.org/2001/XMLSchema#integer> )>> .',
        ':t :val << :a :q "x"^^<http://e/d> ~ :r >> .',
        ':t :val << :a :q "x"^^<http://e/d> >> .',
    ],
)
def test_a_typed_literal_with_a_full_iri_datatype_inside_a_triple_term(text):
    assert len(_quads(text)) >= 1


def test_the_datatype_is_kept():
    ds = _quads(':t :val <<( :a :q "x"^^<http://e/d> )>> .')
    (term,) = [o for _s, _p, o, _g in ds.quads()]
    assert str(term.object.datatype) == "http://e/d"


@pytest.mark.parametrize(
    ("text", "count"),
    [
        (":t :val ([:a :b][:c :d]) .", 7),
        (":t :val ([:a :b] [:c :d]) .", 7),
        (":t :val ((1 2)(3)) .", 11),
        (":t :val ([][] :z) .", 7),
    ],
)
def test_adjacent_bracketed_items_in_a_collection(text, count):
    assert len(_quads(text)) == count
