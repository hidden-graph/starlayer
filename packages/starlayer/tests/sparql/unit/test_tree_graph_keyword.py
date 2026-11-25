"""The syntax-tree graph parameter is ``tree_graph`` in all three tree families (sqe, srl, manchester).

The old names (``graph``, ``data_graph``) were renamed with no alias, so they are an unknown keyword.
"""

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text, sqe_validate
from starlayer.sparql.srl import srl_parse_to_tree, srl_tree_to_text, srl_validate
from starlayer.starontology.manchester import (
    manchester_parse_to_tree,
    manchester_tree_to_owl,
    manchester_tree_to_text,
    manchester_validate,
)

SQE = "SELECT * WHERE { ?s ?p ?o }"
SRL = "RULE { ?x <http://e/q> ?y } WHERE { ?x <http://e/p> ?y }"
MANCH = "Prefix: : <http://e/>\nClass: :A\n"


def test_sqe_tree_graph_keyword():
    target = StarLayerGraph()
    tree, root = sqe_parse_to_tree(SQE, tree_graph=target)
    assert tree is target
    assert "SELECT" in sqe_tree_to_text(tree_graph=tree, root=root)
    assert sqe_validate(tree_graph=tree)[0]
    for call in (
        lambda: sqe_parse_to_tree(SQE, graph=StarLayerGraph()),
        lambda: sqe_tree_to_text(graph=tree, root=root),
        lambda: sqe_validate(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()


def test_srl_tree_graph_keyword():
    target = StarLayerGraph()
    tree, root = srl_parse_to_tree(SRL, tree_graph=target)
    assert tree is target
    assert "RULE" in srl_tree_to_text(tree_graph=tree, root=root)
    assert srl_validate(tree_graph=tree)[0]
    for call in (
        lambda: srl_parse_to_tree(SRL, graph=StarLayerGraph()),
        lambda: srl_tree_to_text(graph=tree, root=root),
        lambda: srl_validate(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()


def test_manchester_tree_graph_keyword():
    target = StarLayerGraph()
    tree = manchester_parse_to_tree(MANCH, tree_graph=target)
    assert tree is target
    assert "Class" in manchester_tree_to_text(tree_graph=tree)
    assert manchester_tree_to_owl(tree_graph=tree) is not None
    assert manchester_validate(tree_graph=tree)[0]
    for call in (
        lambda: manchester_parse_to_tree(MANCH, graph=StarLayerGraph()),
        lambda: manchester_tree_to_text(graph=tree),
        lambda: manchester_tree_to_owl(graph=tree),
        lambda: manchester_validate(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()
