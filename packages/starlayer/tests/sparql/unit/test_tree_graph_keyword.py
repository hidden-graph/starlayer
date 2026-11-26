"""The syntax-tree graph parameter is ``tree_graph`` in all three tree families (sqe, srl, manchester).

The old names (``graph``, ``data_graph``) were renamed with no alias, so they are an unknown keyword.
"""

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.sparql import sparql_to_tree, tree_to_sparql, validate_sparql_tree
from starlayer.starontology.manchester import (
    manchester_to_tree,
    tree_to_manchester,
    tree_to_owl,
    validate_manchester_tree,
)

SQE = "SELECT * WHERE { ?s ?p ?o }"
SRL = "RULE { ?x <http://e/q> ?y } WHERE { ?x <http://e/p> ?y }"
MANCH = "Prefix: : <http://e/>\nClass: :A\n"


def test_sqe_tree_graph_keyword():
    target = StarLayerGraph()
    tree, root = sparql_to_tree(SQE, tree_graph=target)
    assert tree is target
    assert "SELECT" in tree_to_sparql(tree_graph=tree, root=root)
    assert validate_sparql_tree(tree_graph=tree).conforms
    for call in (
        lambda: sparql_to_tree(SQE, graph=StarLayerGraph()),
        lambda: tree_to_sparql(graph=tree, root=root),
        lambda: validate_sparql_tree(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()


def test_srl_tree_graph_keyword():
    target = StarLayerGraph()
    tree, root = sparql_to_tree(SRL, tree_graph=target)
    assert tree is target
    assert "RULE" in tree_to_sparql(tree_graph=tree, root=root)
    assert validate_sparql_tree(tree_graph=tree).conforms
    for call in (
        lambda: sparql_to_tree(SRL, graph=StarLayerGraph()),
        lambda: tree_to_sparql(graph=tree, root=root),
        lambda: validate_sparql_tree(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()


def test_manchester_tree_graph_keyword():
    target = StarLayerGraph()
    tree = manchester_to_tree(MANCH, tree_graph=target)
    assert tree is target
    assert "Class" in tree_to_manchester(tree_graph=tree)
    assert tree_to_owl(tree_graph=tree) is not None
    assert validate_manchester_tree(tree_graph=tree).conforms
    for call in (
        lambda: manchester_to_tree(MANCH, graph=StarLayerGraph()),
        lambda: tree_to_manchester(graph=tree),
        lambda: tree_to_owl(graph=tree),
        lambda: validate_manchester_tree(data_graph=tree),
    ):
        with pytest.raises(TypeError):
            call()
