"""The ordered children of ``sqe:`` and ``spexpr:`` trees are ``tree:ord`` ordinals, not ``rdf:List`` (graph/ordinals.py, starontology/tree).

Every ordered property is written as ordinals, read back in order, rendered to the same text, and the shapes reject a tie, a missing
ordinal, a non-integer ordinal and a blank node under two parents; the decoders raise ``FormatError`` kind ``"rdf"`` for the same faults.
"""

from __future__ import annotations

import warnings

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph
from starlayer.graph import ordinals as ord_
from starlayer.graph.rdfc import rdfc10_hash
from starlayer.sparql.parse_sparql import sparql_update_to_tree
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_tree_to_text, sqe_validate
from starlayer.sparql.sqe.shapes import _validate_shapes
from starlayer.sparql.sqe.vocab import ORDERED_PROPERTIES
from starlayer.sparql.vocab import SPEXPR, SQE

RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
RDF_FIRST = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#first")
RDF_REST = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#rest")
INTEGER = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

P = "PREFIX ex: <http://example.org/> "

QUERIES = {
    "select": P + """SELECT DISTINCT ?s (COUNT(?o) AS ?c) ?z FROM <http://g/a> FROM NAMED <http://g/b> WHERE {
        ?s ex:p ?o . ?s ex:q ?w . OPTIONAL { ?o ex:r ?z } { ?s a ex:A } UNION { ?s a ex:B } UNION { ?s a ex:C }
        MINUS { ?s ex:m ?m } GRAPH ?g { ?s ex:g ?o } VALUES (?a ?b) { (1 UNDEF) (2 3) }
        FILTER(?o IN (1, 2, 3) && STR(?o) != "x" || CONCAT(STR(?s), "a", "b") = "q")
        FILTER(?w + 1 - 2 * 3 / 4 > 0) FILTER(ex:f(?o, ?w) && COALESCE(?o, ?w, 1) && NOT EXISTS { ?s ex:n ?n . ?n ex:o ?s })
        ?s ex:a/ex:b|^ex:c ?o . ?s !(ex:d|^ex:e) ?w } GROUP BY ?s ?z (?w + 1 AS ?v) HAVING (COUNT(?o) > 1 && COUNT(?o) < 9) (?z)
        ORDER BY DESC(?c) ?s LIMIT 3""",
    "construct": P + "CONSTRUCT { ?s ex:out ?o . ?o ex:in ?s } WHERE { ?s ex:p ?o . ?o ex:q ?s }",
    "describe": P + "DESCRIBE ?s ex:thing <http://example.org/other> WHERE { ?s ex:p ?o . ?o ex:q ?s }",
    "ask": P + "ASK { ?s ex:p ?o . ?o ex:q ?s }",
    "values": P + "SELECT * WHERE { ?s ex:p ?o } VALUES ?o { 1 2 3 }",
}
UPDATES = {
    "insert data": P + "INSERT DATA { ex:a ex:p ex:b . ex:b ex:p ex:c GRAPH ex:g { ex:a ex:q ex:b . ex:c ex:q ex:d } }",
    "modify": P + "WITH ex:g DELETE { ?s ex:p ?o . ?o ex:q ?s } INSERT { ?s ex:r ?o . ?o ex:r ?s } USING ex:a USING NAMED ex:b WHERE { ?s ex:p ?o . ?o ex:q ?s }",
    "two operations": P + "CLEAR ALL ; DROP DEFAULT ; DELETE WHERE { ?s ex:p ?o . ?o ex:q ?s }",
}


def _tree(text: str, update: bool = False):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sparql_update_to_tree(text) if update else sqe_parse_to_tree(text)


def _all_trees():
    yield from ((name, *_tree(text)) for name, text in QUERIES.items())
    yield from ((name, *_tree(text, update=True)) for name, text in UPDATES.items())


def _is_sequence(graph, parent, prop) -> bool:
    """A relational expression holds one operator and one ``other``, not sequences; only IN / NOT IN hold a list (``spexpr:args``)."""
    if (parent, RDF_TYPE, SPEXPR.RelationalExpression) not in graph:
        return True
    return prop == SPEXPR.args


def _sequences(graph):
    """``(parent, property)`` for every ordered sequence the tree holds."""
    found = {(s, p) for s, p, _o in graph.triples((None, None, None)) if p in ORDERED_PROPERTIES}
    return sorted((pair for pair in found if _is_sequence(graph, *pair)), key=str)


def test_every_ordered_property_is_exercised_by_these_trees():
    seen = {p for _name, graph, _root in _all_trees() for _s, p in _sequences(graph)}
    assert seen == ORDERED_PROPERTIES, sorted(str(p) for p in ORDERED_PROPERTIES - seen)


@pytest.mark.parametrize("name,graph,root", list(_all_trees()), ids=lambda v: v if isinstance(v, str) else "")
def test_no_tree_holds_an_rdf_list(name, graph, root):
    assert not list(graph.triples((None, RDF_FIRST, None))) and not list(graph.triples((None, RDF_REST, None)))
    assert not list(graph.triples((None, None, ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-nil"))))


@pytest.mark.parametrize("name,graph,root", list(_all_trees()), ids=lambda v: v if isinstance(v, str) else "")
def test_the_ordinals_are_dense_and_every_child_is_a_blank_node_or_an_item(name, graph, root):
    for parent, prop in _sequences(graph):
        rows = ord_.ordered_children(graph, parent, prop)
        numbers = [int(next(graph.objects(child, ord_.ORD)).value) for child, _m in rows]
        assert numbers == list(range(len(rows))), (parent, prop)
        for child, member in rows:
            if (child, RDF_TYPE, ord_.ITEM) in graph:
                assert isinstance(member, (ox.NamedNode, ox.Literal)) or member != child
            else:
                assert isinstance(child, ox.BlankNode) and member == child


@pytest.mark.parametrize("name,graph,root", list(_all_trees()), ids=lambda v: v if isinstance(v, str) else "")
def test_the_trees_conform_and_render_to_text_that_parses_again(name, graph, root):
    assert _validate_shapes(graph).conforms
    text = sqe_tree_to_text(graph, root)
    again, again_root = _tree(text, update=name in UPDATES)
    assert sqe_tree_to_text(again, again_root) == text


@pytest.mark.parametrize("name,graph,root", list(_all_trees()), ids=lambda v: v if isinstance(v, str) else "")
def test_an_unordered_sequence_is_noticed_everywhere(name, graph, root):
    """For each sequence: a tie, a missing ordinal and a non-integer ordinal fail the shapes and make the renderer raise."""
    text = sqe_tree_to_text(graph, root)
    for parent, prop in _sequences(graph):
        rows = ord_.ordered_children(graph, parent, prop)
        faults = []
        child = rows[0][0]
        faults.append(("missing", child, None))
        faults.append(("text", child, ox.Literal("first")))
        faults.append(("negative", child, ox.Literal("-1", datatype=INTEGER)))
        if len(rows) > 1:
            faults.append(("tie", rows[1][0], next(graph.objects(rows[0][0], ord_.ORD))))
        for kind, node, bad in faults:
            damaged = graph.copy()
            old = next(damaged.objects(node, ord_.ORD))
            damaged.remove((node, ord_.ORD, old))
            if bad is not None:
                damaged.add((node, ord_.ORD, bad))
            assert not _validate_shapes(damaged).conforms, (kind, prop)
            with pytest.raises(FormatError) as raised:
                sqe_tree_to_text(damaged, root)
            assert raised.value.kind == "rdf", (kind, prop)
    assert sqe_tree_to_text(graph, root) == text


def test_sqe_validate_reports_a_tie_and_does_not_raise():
    graph, root = _tree(P + "SELECT * WHERE { ?s ex:a ?o . ?s ex:b ?o }")
    first, second = (child for child, _m in ord_.ordered_children(graph, root, SQE.where))
    graph.remove((second, ord_.ORD, None))
    graph.add((second, ord_.ORD, next(graph.objects(first, ord_.ORD))))
    report = sqe_validate(graph)
    assert not report.conforms and "same tree:ord" in report.report_text


def test_the_order_is_the_ordinal_not_the_blank_node_label():
    graph, root = _tree(P + "SELECT * WHERE { ?s ex:a ?o . ?s ex:b ?o . ?s ex:c ?o }")
    patterns = ord_.ordered_items(graph, root, SQE.where)
    ord_.append(graph, root, SQE.where, ord_.remove_at(graph, root, SQE.where, 0))  # the first moves to the end
    text = sqe_tree_to_text(graph, root)
    assert text.index("ex:b") < text.index("ex:c") < text.index("ex:a")
    assert len(patterns) == 3
    # a gap left by a removal is allowed and does not change the order
    ord_.remove_at(graph, root, SQE.where, 0)
    assert "ex:b" not in sqe_tree_to_text(graph, root)
    assert _validate_shapes(graph).conforms


def test_an_empty_sequence_is_no_triple_and_an_empty_group_still_renders():
    graph, root = _tree("SELECT * WHERE { }")
    assert not list(graph.objects(root, SQE.where))
    text = sqe_tree_to_text(graph, root)
    assert text.startswith("SELECT *\nWHERE {") and text.endswith("}") and "?s" not in text
    assert _validate_shapes(graph).conforms
    graph, root = _tree(P + "DESCRIBE ex:a")
    assert "WHERE" not in sqe_tree_to_text(graph, root)


def test_a_modify_with_both_templates_empty_is_written_with_an_empty_delete():
    graph, root = _tree(P + "DELETE { } INSERT { } WHERE { ?s ?p ?o }", update=True)
    text = sqe_tree_to_text(graph, root)
    assert "DELETE { }" in text
    assert _validate_shapes(graph).conforms


def test_a_blank_node_under_two_parents_is_rejected_and_a_named_one_is_accepted():
    graph, _root = _tree(P + "SELECT ?s WHERE { ?s ex:p ?o . FILTER(?o > 1) }")
    other, other_root = _tree(P + "SELECT ?s WHERE { ?s ex:q ?o }")
    # the triple pattern of the first query is also put into the second one: one blank node, two parents
    first_root = next(graph.subjects(RDF_TYPE, SQE.Query))
    pattern = ord_.ordered_items(graph, first_root, SQE.where)[0]
    both = StarLayerGraph(prefixes={})
    both.extend(list(graph))
    both.extend(list(other))
    second_root = next(s for s in other.subjects(RDF_TYPE, SQE.Query))
    both.add((second_root, SQE.where, pattern))
    both.add((pattern, ord_.ORD, ox.Literal("5", datatype=INTEGER)))
    report = _validate_shapes(both)
    assert not report.conforms
    assert "more than one parent" in report.report_text or "tree:ord" in report.report_text
    # held through an Item instead, the same pattern as a named node is shared: accepted
    assert other_root is not None


def test_a_node_without_a_tree_item_wrapper_is_not_accepted_for_a_named_node():
    graph, root = _tree(P + "SELECT ?s WHERE { ?s ex:p ?o }")
    graph.add((root, SQE.where, ox.NamedNode("http://example.org/queries#named")))
    assert not _validate_shapes(graph).conforms
    with pytest.raises(FormatError) as raised:
        sqe_tree_to_text(graph, root)
    assert raised.value.kind == "rdf"


# ---- the guide's appendix B1: two queries share one named filter, held through a tree:Item -------------------------------------------

B1_SHARED = """
@prefix ex: <http://example.org/> .
@prefix q: <http://example.org/queries#> .
@prefix sqe: <https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#> .
@prefix spexpr: <https://github.com/hidden-graph/starlayer/ns/sparql/expr#> .
@prefix tree: <https://github.com/hidden-graph/starlayer/ns/tree#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

q:shippedSinceCutoff a sqe:Query, sqe:SelectQuery ;
    sqe:projection [ a tree:Item ; tree:ord 0 ; tree:value "s"^^spexpr:Variable ] ;
    sqe:prefixDecl [ a sqe:PrefixDecl ; sqe:namespace ex: ; sqe:prefixLabel "ex"^^spexpr:PlainString ] ;
    sqe:where [
        a sqe:TriplePattern ; tree:ord 0 ;
        sqe:subject "s"^^spexpr:Variable ;
        sqe:predicate ex:shipDate ;
        sqe:object "d"^^spexpr:Variable
    ], [ a tree:Item ; tree:ord 1 ; tree:value q:sinceCutoffFilter ] .

q:receivedSinceCutoff a sqe:Query, sqe:SelectQuery ;
    sqe:projection [ a tree:Item ; tree:ord 0 ; tree:value "s"^^spexpr:Variable ] ;
    sqe:prefixDecl [ a sqe:PrefixDecl ; sqe:namespace ex: ; sqe:prefixLabel "ex"^^spexpr:PlainString ] ;
    sqe:where [
        a sqe:TriplePattern ; tree:ord 0 ;
        sqe:subject "s"^^spexpr:Variable ;
        sqe:predicate ex:receivedDate ;
        sqe:object "d"^^spexpr:Variable
    ], [ a tree:Item ; tree:ord 1 ; tree:value q:sinceCutoffFilter ] .

q:sinceCutoffFilter a sqe:Filter ;
    sqe:expr [
        a spexpr:RelationalExpression ;
        spexpr:expr "d"^^spexpr:Variable ;
        spexpr:op ">="^^spexpr:PlainString ;
        spexpr:other "2026-02-01"^^xsd:date
    ] .
"""

SHIPMENTS = """
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:ship1 ex:shipDate "2026-01-05"^^xsd:date ; ex:receivedDate "2026-01-12"^^xsd:date .
ex:ship2 ex:shipDate "2026-02-10"^^xsd:date ; ex:receivedDate "2026-02-15"^^xsd:date .
ex:ship3 ex:shipDate "2026-03-01"^^xsd:date ; ex:receivedDate "2026-03-04"^^xsd:date .
"""


def _b1():
    graph = StarLayerGraph()
    graph.parse(data=B1_SHARED, format="turtle")
    return graph


def test_b1_two_queries_share_one_named_filter_through_a_tree_item():
    graph = _b1()
    assert sqe_validate(graph).conforms
    shipments = StarLayerGraph()
    shipments.parse(data=SHIPMENTS, format="turtle")
    names = {}
    for key in ("shippedSinceCutoff", "receivedSinceCutoff"):
        text = sqe_tree_to_text(graph, ox.NamedNode(f"http://example.org/queries#{key}"))
        assert 'FILTER(?d >= "2026-02-01"^^<http://www.w3.org/2001/XMLSchema#date>)' in text
        names[key] = sorted(str(r.s.value).rsplit("/", 1)[-1] for r in shipments.query(text))
    assert names == {"shippedSinceCutoff": ["ship2", "ship3"], "receivedSinceCutoff": ["ship2", "ship3"]}


def test_b1_the_shared_filter_is_edited_once_and_both_queries_follow():
    graph = _b1()
    filter_node = ox.NamedNode("http://example.org/queries#sinceCutoffFilter")
    cbd = graph.cbd(filter_node)
    assert len(cbd) == 6  # the filter has no ordinal of its own: the Items that hold it carry them
    graph = graph - cbd
    graph.parse(data=B1_SHARED.split("q:sinceCutoffFilter a sqe:Filter")[0].split("q:shippedSinceCutoff")[0] + """
q:sinceCutoffFilter a sqe:Filter ;
    sqe:expr [ a spexpr:RelationalExpression ; spexpr:expr "d"^^spexpr:Variable ; spexpr:op ">="^^spexpr:PlainString ; spexpr:other "2026-03-01"^^xsd:date ] .
""", format="turtle")
    assert sqe_validate(graph).conforms
    text = sqe_tree_to_text(graph, ox.NamedNode("http://example.org/queries#receivedSinceCutoff"))
    assert "2026-03-01" in text


def test_b1_a_node_that_two_queries_share_must_be_named():
    graph = _b1()
    first = ox.NamedNode("http://example.org/queries#shippedSinceCutoff")
    second = ox.NamedNode("http://example.org/queries#receivedSinceCutoff")
    pattern = ord_.ordered_items(graph, first, SQE.where)[0]
    graph.add((second, SQE.where, pattern))  # the blank pattern now has two parents, and an ordinal that cannot tell them apart
    assert not sqe_validate(graph).conforms


# ---- editing, renumbering and hashing -------------------------------------------------------------------------------------------

def test_a_tree_that_lost_a_child_hashes_as_the_same_tree_after_renumber_dense():
    full, full_root = _tree(P + "SELECT * WHERE { ?s ex:a ?o . ?s ex:b ?o . ?s ex:c ?o }")
    fresh, _ = _tree(P + "SELECT * WHERE { ?s ex:a ?o . ?s ex:c ?o }")
    removed = ord_.remove_at(full, full_root, SQE.where, 1)
    for triple in list(full.cbd(removed)):  # the member stays in the graph until its own triples are removed
        full.remove(triple)
    assert rdfc10_hash(full) != rdfc10_hash(fresh)  # a gap is data
    ord_.renumber_dense(full)
    assert rdfc10_hash(full) == rdfc10_hash(fresh)
    assert "ex:b" not in sqe_tree_to_text(full, full_root)


def test_inserting_a_pattern_between_two_others_renders_in_that_place():
    graph, root = _tree(P + "SELECT * WHERE { ?s ex:a ?o . ?s ex:c ?o }")
    donor, _ = _tree(P + "SELECT * WHERE { ?s ex:b ?o }")
    donor_root = next(donor.subjects(RDF_TYPE, SQE.Query))
    new = ord_.ordered_items(donor, donor_root, SQE.where)[0]
    ord_.remove_at(donor, donor_root, SQE.where, 0)
    graph.extend(list(donor.triples((new, None, None))))
    ord_.insert_at(graph, root, SQE.where, 1, new)
    text = sqe_tree_to_text(graph, root)
    assert text.index("ex:a") < text.index("ex:b") < text.index("ex:c")
    assert _validate_shapes(graph).conforms


def test_expression_operands_are_ordered_too():
    graph, root = _tree(P + "SELECT * WHERE { ?s ex:p ?o FILTER(?o + 1 - 2 > 0) FILTER(CONCAT(?o, 'a', 'b') = 'x') FILTER(?o IN (1, 2, 3)) }")
    for prop in (SPEXPR.other, SPEXPR.op, SPEXPR.args):
        found = [(s, p) for s, p in _sequences(graph) if p == prop]
        assert found, prop
    additive = next(graph.subjects(RDF_TYPE, SPEXPR.AdditiveExpression))
    assert [m.value for m in ord_.ordered_items(graph, additive, SPEXPR.op)] == ["+", "-"]
    concat = next(graph.subjects(RDF_TYPE, SPEXPR.CONCAT))
    assert [getattr(m, "value", None) for m in ord_.ordered_items(graph, concat, SPEXPR.args)][1:] == ["a", "b"]
    assert not list(graph.triples((concat, SPEXPR.arg, None)))


def _relational(tree_text: str):
    graph, root = _tree(P + "SELECT * WHERE { ?s ex:p ?o FILTER(" + tree_text + ") }")
    return graph, next(graph.subjects(RDF_TYPE, SPEXPR.RelationalExpression))


@pytest.mark.parametrize("operator", ["IN", "NOT IN"])
@pytest.mark.parametrize("values,count", [("1", 1), ("1, 2, 3", 3), ("", 0)])
def test_in_and_not_in_keep_their_values_in_spexpr_args_and_have_no_other(operator, values, count):
    graph, rel = _relational(f"?o {operator} ({values})")
    assert not list(graph.objects(rel, SPEXPR.other))
    assert len(ord_.ordered_items(graph, rel, SPEXPR.args)) == count
    assert [m.value for m in ord_.ordered_items(graph, rel, SPEXPR.args)] == values.replace(" ", "").split(",")[:count]
    assert f"?o {operator} (" + ", ".join(v for v in values.split(", ") if v) + ")" in _text_of(graph)
    assert _validate_shapes(graph).conforms


def _text_of(graph) -> str:
    root = next(graph.subjects(RDF_TYPE, SQE.SelectQuery))
    return sqe_tree_to_text(graph, root)


def test_a_comparison_has_exactly_one_other_and_no_args():
    graph, rel = _relational("?o > 1")
    assert len(list(graph.objects(rel, SPEXPR.other))) == 1 and not list(graph.objects(rel, SPEXPR.args))
    assert _validate_shapes(graph).conforms


def test_an_operator_other_than_in_with_args_is_rejected_and_in_with_other_is_rejected():
    graph, rel = _relational("?o > 1")
    item = ox.BlankNode()
    graph.extend([(rel, SPEXPR.args, item), (item, RDF_TYPE, ord_.ITEM), (item, ord_.ORD, ox.Literal("0", datatype=INTEGER)),
                  (item, ord_.VALUE, ox.Literal("2", datatype=INTEGER))])
    assert not _validate_shapes(graph).conforms
    graph, rel = _relational("?o IN (1, 2)")
    graph.add((rel, SPEXPR.other, ox.Literal("3", datatype=INTEGER)))
    assert not _validate_shapes(graph).conforms


def test_a_comparison_without_its_other_is_rejected():
    graph, rel = _relational("?o > 1")
    graph.remove((rel, SPEXPR.other, None))
    assert not _validate_shapes(graph).conforms



def test_describe_with_an_empty_where_and_without_one_are_the_same_tree_and_an_empty_delete_is_no_delete():
    a, root_a = _tree(P + "DESCRIBE ex:x WHERE { }")
    b, root_b = _tree(P + "DESCRIBE ex:x")
    assert sqe_tree_to_text(a, root_a) == sqe_tree_to_text(b, root_b)
    assert rdfc10_hash(a) == rdfc10_hash(b)
    c, root_c = _tree(P + "DELETE { } INSERT { ex:s ex:p ex:o } WHERE { ?s ex:q ?o }", update=True)
    d, root_d = _tree(P + "INSERT { ex:s ex:p ex:o } WHERE { ?s ex:q ?o }", update=True)
    assert rdfc10_hash(c) == rdfc10_hash(d)
    assert sqe_tree_to_text(c, root_c) == sqe_tree_to_text(d, root_d)
