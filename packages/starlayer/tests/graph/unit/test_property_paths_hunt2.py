"""Property path fixes from the third hunt (GitHub issue #77); expected rows computed by hand from SPARQL 1.1 section 18.4."""

import warnings

import pytest
from starlayer.graph import StarLayerGraph

warnings.simplefilter("ignore")
P = "PREFIX : <http://e/> "
DATA = "@prefix : <http://e/> . :a :p :b . :b :q :c . :c :p :d . :d :p :a . :x :p :b . :a :r :b ."
CYCLE = "@prefix : <http://e/> . :a :p :b . :b :p :c . :c :p :a . :a :p :a . :x :q :y ."


def _rows(turtle, path, select="?s ?o", pattern="?s {path} ?o"):
    g = StarLayerGraph()
    g.parse(data=turtle, format="turtle12")
    query = f"{P}SELECT {select} {{ {pattern.format(path=path)} }}"
    return sorted(tuple(str(v).rsplit("/", 1)[-1] for v in row) for row in g.query(query))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("!(:p)", [("a", "b"), ("b", "c")]),
        ("!(^:p)", [("b", "a"), ("c", "b")]),  # inverse of the non-p triples b q c and a r b
        ("!^:p", [("b", "a"), ("c", "b")]),
        ("!(^:p|^:q)", [("b", "a")]),  # only a r b is neither
        # forward non-p: (a,b) (b,c); inverse non-q: (b,a) (d,c) (a,d) (b,x) and a r b twice-reversed (b,a): a bag
        ("!(:p|^:q)", [("a", "b"), ("a", "d"), ("b", "a"), ("b", "a"), ("b", "c"), ("b", "x"), ("d", "c")]),
        ("!(^:p|:r)", [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b"), ("c", "d"), ("d", "a"), ("x", "b")]),
    ],
)
def test_negated_property_set_with_inverse_members(path, expected):
    assert _rows(DATA, path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (":p*", ["a", "b", "c"]),
        (":p+", ["a", "b", "c"]),
        (":p?", ["a", "b"]),
        ("(:p|:q)*", ["a", "b", "c"]),
    ],
)
def test_repetition_paths_give_each_node_once(path, expected):
    rows = _rows(CYCLE, path, "?y", ":a {path} ?y")
    assert [r[0] for r in rows] == expected


def test_zero_length_match_for_a_node_not_in_the_graph():
    assert _rows(CYCLE, ":p*", "?y", ":zzz {path} ?y") == [("zzz",)]


def test_unbound_subject_repetition_is_unchanged():
    pairs = _rows(CYCLE, ":p*")
    assert len(pairs) == 11 and len(set(pairs)) == 11


@pytest.mark.parametrize("path", ["!(^<http://e/p>)", "!(<http://e/p>|^<http://e/q>)", "!(^<http://e/p>|^<http://e/q>)"])
def test_sqe_renders_a_negated_set_with_an_inverse_member(path):
    from rdflib import Graph
    from starlayer.sparql import sqe

    tree, root = sqe.sqe_parse_to_tree(f"SELECT * WHERE {{ ?s {path} ?o }}")
    text = sqe.sqe_tree_to_text(tree, root)
    assert path in text
    Graph().query(text)  # and the text parses again
