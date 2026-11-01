"""Tests for SPARQL 1.2 Update in the hand-written parser (``parse_sparql_update``), its ``sqe:`` trees and their text.

Gates, mirroring the query ones in ``test_parse_sparql.py``:

1. the W3C update fixtures (SPARQL 1.1 ``syntax-update-*`` and every update-evaluation request, SPARQL 1.2 update syntax
   and evaluation requests): every positive request parses, every negative one is rejected;
2. the sqe fixpoint: text -> tree -> ``sqe_tree_to_text`` -> tree is the same tree, and every positive tree conforms
   to the sqe shapes;
3. the static rules of the Update grammar, as a table of valid and invalid requests;
4. the shapes themselves: trees the grammar forbids (variables in data, blank nodes in DELETE) are rejected by SHACL.
"""

from __future__ import annotations

import pytest
from rdflib import RDF, Literal, URIRef
from rdflib.compare import isomorphic
from starlayer.sparql.parse_sparql import (
    Node,
    SparqlSyntaxError,
    parse_sparql_update,
    sparql_update_to_tree,
)
from starlayer.sparql.sqe import sqe_tree_to_text, sqe_validate
from starlayer.sparql.sqe.vocab import SQE
from tests.sparql.parse_sparql_support import (
    canonical_graph,
    w3c11_entries,
    w3c_entries,
)

POS_TYPES = ("PositiveSyntaxTest", "PositiveUpdateSyntaxTest", "UpdateEvaluationTest")
NEG_TYPES = ("NegativeSyntaxTest", "NegativeUpdateSyntaxTest")


def _file(e) -> str:
    return e.update_file or e.query_file


def _collect(types: tuple[str, ...]):
    out = [(e.key, e.read()) for e in w3c11_entries(*types, ext=".ru")]
    out += [
        ("12/" + e.category + "/" + e.test_iri.rsplit("#", 1)[-1], e.read(_file(e)))
        for e in w3c_entries(*types)
        if _file(e).endswith(".ru")
    ]
    return out


POSITIVE, NEGATIVE = _collect(POS_TYPES), _collect(NEG_TYPES)

# Update-evaluation requests whose text the grammar does not cover (none today); name -> why.
NOT_PARSED: dict[str, str] = {}


def test_w3c_update_suites_are_not_empty():
    assert len(POSITIVE) >= 150 and len(NEGATIVE) >= 14


@pytest.mark.parametrize("key,text", POSITIVE, ids=[k for k, _ in POSITIVE])
def test_w3c_positive_update_parses(key, text):
    parse_sparql_update(text)


@pytest.mark.parametrize("key,text", NEGATIVE, ids=[k for k, _ in NEGATIVE])
def test_w3c_negative_update_is_rejected(key, text):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql_update(text)


@pytest.mark.parametrize("key,text", POSITIVE, ids=[k for k, _ in POSITIVE])
def test_update_tree_text_fixpoint(key, text):
    tree = sparql_update_to_tree(text)
    rendered = sqe_tree_to_text(*tree)
    again = sparql_update_to_tree(rendered)
    assert len(tree[0]) == len(again[0])
    assert sqe_tree_to_text(*again) == rendered  # the text is a fixpoint
    if len(tree[0]) < 500:  # rdflib's isomorphism check is quadratic on the 5,000-triple W3C stress request
        assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0])), rendered


# SHACL costs 1-3 s per tree (more for the large ones), so validating every W3C tree is opt-in, as for queries:
# ``pytest --sqe-coverage``. The rule table below validates a representative set in the default run.
@pytest.mark.sqe_coverage
@pytest.mark.parametrize("key,text", POSITIVE, ids=[k for k, _ in POSITIVE])
def test_update_tree_conforms_to_the_shapes(key, text):
    ok, _, report = sqe_validate(sparql_update_to_tree(text)[0])
    assert ok, report


# ---------------------------------------------------------------------------
# The static rules of the Update grammar
# ---------------------------------------------------------------------------

P = "PREFIX : <http://e/>\n"

VALID = [
    "",
    "# only a comment",
    "PREFIX : <http://e/>",
    "INSERT DATA { }",
    "INSERT DATA { } ;",
    "INSERT DATA { } ; ; ".replace("; ;", ";") ,
    P + "INSERT DATA { _:a :p _:a . [] :q ( 1 2 ) }",
    P + "INSERT DATA { << :a :b :c >> :p :o }",
    P + "INSERT DATA { :s :p :o {| :a 1 |} }",
    P + "DELETE DATA { :s :p :o ~ :r }",
    P + "DELETE DATA { << :a :b :c ~ :r >> :p :o }",
    P + "DELETE DATA { :s :p <<( :a :b :c )>> }",
    P + "DELETE DATA { GRAPH :g { :s :p :o } }",
    P + "DELETE WHERE { ?s ?p ?o }",
    P + "DELETE WHERE { GRAPH ?g { ?s ?p ?o } }",
    P + "DELETE { ?s :p ?o } WHERE { ?s :p ?o }",
    P + "DELETE { ?s :p ?o ~ ?r } WHERE { ?s :p ?o }",
    P + "INSERT { _:b :p ?o } WHERE { ?s :p ?o }",
    P + "INSERT { ?s :p [ :q 1 ] } WHERE { ?s :p ?o }",
    P + "INSERT { ?s :p ?o } WHERE { }",
    P + "WITH :g INSERT { ?s :p ?o } USING :a USING NAMED :b WHERE { ?s :p ?o }",
    P + "INSERT { ?s :p ?o } WHERE { { SELECT ?s ?o { ?s :p ?o } LIMIT 1 } }",
    P + "INSERT { ?s :p ?x } WHERE { ?s :p ?o BIND(?o + 1 AS ?x) }",
    P + "INSERT { ?s :p ?x } WHERE { _:a :p ?s } ; INSERT DATA { _:b :p :o }",
    # templates and patterns are scoped to one operation (W3C basic-update/insert-where-same-bnode)
    P + "INSERT { _:a :p :o } WHERE { } ; INSERT { _:a :p :o } WHERE { } ; INSERT { _:a :p ?o } WHERE { _:a :p ?o }",
    P + "INSERT DATA { _:a :p :o } ; INSERT { _:a :p :o2 } WHERE { _:a :q ?x }",
    P + "INSERT DATA { GRAPH :g1 { _:b :p :o } GRAPH :g2 { _:b :p :o } }",
    P + "INSERT { _:a :p ?o } WHERE { _:a :q ?o } ; DELETE { ?s :p ?o } WHERE { _:a :q ?s } ",
    "CLEAR SILENT ALL ; DROP NAMED ; CREATE SILENT GRAPH <g> ; LOAD <x>",
    "ADD DEFAULT TO DEFAULT ; MOVE GRAPH <a> TO GRAPH <b> ; COPY <a> TO <b>",
    "PREFIX a: <http://a/> INSERT DATA { a:s a:p a:o } ; INSERT DATA { a:s a:p a:o2 }",  # prefixes stay in force
    "PREFIX a: <http://a/> INSERT DATA { a:s a:p a:o } ; PREFIX a: <http://a2/> INSERT DATA { a:s a:p a:o }",
    "BASE <http://b/> INSERT DATA { <s> <p> <o> } ; INSERT DATA { <s2> <p> <o> }",
    "INSERT DATA { } ; PREFIX x: <http://x/>",
    "VERSION '1.2' INSERT DATA { }",
    'INSERT DATA { <s> <p> "a\\u00e9" , 1.5e3 , true , "x"@en-US , "y"@en--ltr }',
]
INVALID = [
    ("LOAD", "expected an IRI"),
    ("LOAD <a> INTO <b>", "found '<b>'"),
    ("LOAD <a> INTO DEFAULT", "expected GRAPH"),
    ("CLEAR <g>", "expected GRAPH, DEFAULT, NAMED or ALL"),
    ("DROP", "expected GRAPH, DEFAULT, NAMED or ALL"),
    ("CREATE DEFAULT", "expected GRAPH"),
    ("CREATE <g>", "expected GRAPH"),
    ("ADD NAMED TO <b>", "expected an IRI"),
    ("ADD <a> <b>", "expected TO"),
    ("MOVE <a> TO ALL", "expected an IRI"),
    ("COPY <a>", "expected TO"),
    (";", "expected an update operation"),
    ("INSERT DATA { } INSERT DATA { }", "expected ';'"),
    ("INSERT DATA { } ; ; INSERT DATA { }", "expected an update operation"),
    ("INSERT DATA", "expected '{'"),
    ("INSERT { <s> <p> <o> }", "expected WHERE"),
    ("DELETE { <s> <p> <o> }", "expected WHERE"),
    ("INSERT WHERE { ?s ?p ?o }", "expected '{'"),
    ("DELETE WHERE { } WHERE { }", "expected ';'"),
    ("WITH <g> DELETE WHERE { ?s ?p ?o }", "expected '{'"),
    ("WITH DELETE { } WHERE { }", "expected an IRI"),
    ("DELETE { } USING WHERE { }", "expected an IRI"),
    ("DELETE { } WHERE", "expected '{'"),
    ("INSERT { } DELETE { } WHERE { }", "expected WHERE"),
    ("INSERT DATA { ?s <p> <o> }", "variables are not allowed in INSERT DATA"),
    ("INSERT DATA { <s> ?p <o> }", "variables are not allowed in INSERT DATA"),
    ("INSERT DATA { <s> <p> ?o }", "variables are not allowed in INSERT DATA"),
    ("INSERT DATA { GRAPH ?g { <s> <p> <o> } }", "variables are not allowed in INSERT DATA"),
    ("INSERT DATA { <s> <p> <<( <a> <b> ?c )>> }", "variables are not allowed in INSERT DATA"),
    ("INSERT DATA { <s> <p> <o> ~ ?r }", "variables are not allowed in INSERT DATA"),
    ("DELETE DATA { ?s <p> <o> }", "variables are not allowed in DELETE DATA"),
    ("DELETE DATA { _:a <p> <o> }", "blank nodes"),
    ("DELETE DATA { <s> <p> [] }", "blank nodes"),
    ("DELETE DATA { <s> <p> ( 1 ) }", "blank nodes"),
    ("DELETE DATA { << <a> <b> <c> >> <p> <o> }", "blank nodes"),
    ("DELETE DATA { <s> <p> <o> {| <a> 1 |} }", "blank nodes"),
    ("DELETE DATA { <s> <p> <o> ~ }", "blank nodes"),
    ("DELETE DATA { <s> <p> <<( _:b <b> <c> )>> }", "blank nodes"),
    ("DELETE WHERE { _:a <p> <o> }", "blank nodes"),
    ("DELETE WHERE { <s> <p> [ <q> 1 ] }", "blank nodes"),
    ("DELETE { <s> <p> [] } WHERE { ?x <p> <o> }", "blank nodes"),
    ("DELETE { ?s <p> ?o {| <a> 1 |} } WHERE { ?s <p> ?o }", "blank nodes"),
    ("DELETE { _:a <p> ?o } INSERT { _:b <p> ?o } WHERE { ?s <p> ?o }", "blank nodes"),
    ("INSERT DATA { GRAPH <a> { GRAPH <b> { <s> <p> <o> } } }", "expected"),
    ("INSERT DATA { <s> <p> <o> <s2> <p> <o> }", "expected '.'"),
    ("INSERT DATA { <s> <p> <o> . . }", "expected"),
    ("INSERT DATA { GRAPH <g> { <s> <p> <o> <s> <p> <o> } }", "expected '.'"),
    ("INSERT DATA { ?x ", "variables are not allowed|expected"),
    ("INSERT { ?s <p>/<q> ?o } WHERE { ?s <p> ?o }", "expected"),  # no property paths in a template
    ("INSERT { ?s <p> ?x } WHERE { ?s <p> ?x BIND(1 AS ?x) }", "already in scope"),
    ("INSERT { ?s <p> ?c } WHERE { ?s <p> ?o FILTER(COUNT(*) > 1) }", "aggregate"),
    ("INSERT { ?s <p> ?o } WHERE { _:a <p> ?s OPTIONAL { _:a <q> ?o } }", "two different basic graph patterns"),
    ("INSERT DATA { <s> <p> <o> } ; WHERE { }", "expected an update operation"),
    ("INSERT DATA { _:a <p> <o> } ; INSERT DATA { _:a <p> <o2> }", "INSERT DATA of another operation"),
    ("INSERT DATA { _:a <p> <o> } ; CLEAR ALL ; INSERT DATA { GRAPH <g> { <s> <p> _:a } }", "INSERT DATA of another operation"),
    ("INSERT DATA { ex:s <p> <o> }", "undeclared prefix"),
    ("PREFIX a: <http://a/> INSERT DATA { } ; INSERT DATA { b:s <p> <o> }", "undeclared prefix"),
    ("PREFIX a:b: <http://a/> INSERT DATA { }", "prefix label"),
    ("SELECT * { ?s ?p ?o }", "expected an update operation"),
    ("CREATE GRAPH <g> LOAD <x>", "expected ';'"),
]


@pytest.mark.parametrize("text", VALID, ids=[t[:70] for t in VALID])
def test_valid_requests_parse_and_round_trip(text):
    tree = sparql_update_to_tree(text, validate=True)
    again = sparql_update_to_tree(sqe_tree_to_text(*tree))
    assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0]))


@pytest.mark.parametrize("text,why", INVALID, ids=[t[:70] for t, _ in INVALID])
def test_invalid_requests_are_rejected_with_the_right_message(text, why):
    import re

    with pytest.raises(SparqlSyntaxError) as e:
        parse_sparql_update(text)
    assert re.search(why, str(e.value)), str(e.value)


def test_query_text_is_not_an_update_and_update_text_is_not_a_query():
    from starlayer.sparql.parse_sparql import parse_sparql

    with pytest.raises(SparqlSyntaxError):
        parse_sparql_update("ASK { }")
    with pytest.raises(SparqlSyntaxError):
        parse_sparql("INSERT DATA { }")


def test_error_carries_a_position():
    with pytest.raises(SparqlSyntaxError) as e:
        parse_sparql_update("CREATE GRAPH <g> ;\nDELETE DATA { ?s <p> <o> }")
    assert e.value.line == 2


# ---------------------------------------------------------------------------
# AST and tree shape
# ---------------------------------------------------------------------------


def test_ast_of_a_request():
    u = parse_sparql_update(
        P + "WITH :g DELETE { ?s :p ?o } INSERT { ?s :q ?o } USING NAMED :n WHERE { ?s :p ?o } ; CLEAR SILENT NAMED"
    )
    assert u.kind == "UpdateRequest" and [o.kind for o in u["operations"]] == ["Modify", "Clear"]
    m, c = u["operations"]
    assert m["with_"] == URIRef("http://e/g") and m["using"] == [(True, URIRef("http://e/n"))]
    assert c["silent"] is True and c["target"].kind == "NamedGraphs"
    assert isinstance(m["delete"][0], Node) and m["prologue"] == [("prefix", "", "http://e/")] and c["prologue"] == []


def test_tree_of_a_request_is_typed_and_ordered():
    g, root = sparql_update_to_tree(P + "INSERT DATA { :s :p :o GRAPH :g { :a :b :c } } ; DROP ALL")
    assert (root, RDF.type, SQE.UpdateRequest) in g
    from rdflib.collection import Collection

    ops = list(Collection(g, g.value(root, SQE.operations)))
    assert [g.value(o, RDF.type) for o in ops] == [SQE.InsertData, SQE.Drop]
    quads = list(Collection(g, g.value(ops[0], SQE.quads)))
    assert (quads[0], RDF.type, SQE.TriplePattern) in g and (quads[1], RDF.type, SQE.QuadGraph) in g
    assert (g.value(ops[1], SQE.target), RDF.type, SQE.AllGraphs) in g


def test_query_trees_are_unchanged_by_the_update_vocabulary():
    from starlayer.sparql.parse_sparql import sparql_to_tree

    g, _ = sparql_to_tree("SELECT * { ?s ?p ?o }")
    assert not any(str(p).endswith(("#operations", "#quads", "#target")) for _, p, _ in g)


def test_text_of_a_request_is_valid_update_text():
    t = P + "INSERT DATA { :s :p :o } ;\nPREFIX x: <http://x/>\nLOAD SILENT x:a INTO GRAPH x:b ;\nDELETE WHERE { ?s ?p ?o }"
    text = sqe_tree_to_text(*sparql_update_to_tree(t))
    assert text.count(";") == 2 and "LOAD SILENT <http://x/a> INTO GRAPH <http://x/b>" not in text  # x: abbreviates
    assert "LOAD SILENT x:a INTO GRAPH x:b" in text


# ---------------------------------------------------------------------------
# Shapes: trees that the grammar forbids are not valid trees
# ---------------------------------------------------------------------------


def _mutate(text: str, edit):
    g, root = sparql_update_to_tree(text)
    edit(g, root)
    return sqe_validate(g)[0]


def _first_op(g, root):
    from rdflib.collection import Collection

    return next(iter(Collection(g, g.value(root, SQE.operations))))


def test_shapes_accept_the_untouched_trees():
    assert _mutate(P + "DELETE DATA { :s :p :o }", lambda g, r: None)


def test_shapes_reject_a_variable_in_insert_data():
    def edit(g, root):
        from rdflib.collection import Collection
        from starlayer.sparql.vocab import VARIABLE_DATATYPE

        pat = next(iter(Collection(g, g.value(_first_op(g, root), SQE.quads))))
        g.set((pat, SQE.object, Literal("o", datatype=VARIABLE_DATATYPE)))

    assert not _mutate(P + "INSERT DATA { :s :p :o }", edit)


def test_shapes_reject_a_blank_node_in_delete_data_and_in_delete_template():
    from rdflib import BNode
    from rdflib.collection import Collection

    def edit_data(g, root):
        pat = next(iter(Collection(g, g.value(_first_op(g, root), SQE.quads))))
        g.set((pat, SQE.subject, BNode()))

    def edit_template(g, root):
        pat = next(iter(Collection(g, g.value(_first_op(g, root), SQE.delete))))
        g.set((pat, SQE.object, BNode()))

    assert not _mutate(P + "DELETE DATA { :s :p :o }", edit_data)
    assert not _mutate(P + "DELETE { ?s :p ?o } WHERE { ?s :p ?o }", edit_template)
    # the same edit is fine in an INSERT template
    assert _mutate(P + "INSERT { ?s :p ?o } WHERE { ?s :p ?o }", lambda g, r: g.set(
        (next(iter(Collection(g, g.value(_first_op(g, r), SQE.insert)))), SQE.object, BNode())))


def _target(g, r, p=None):
    return g.value(_first_op(g, r), p or SQE.target)


def _retype(g, node, old, new):
    g.remove((node, RDF.type, old))
    g.remove((node, SQE.graphIri, None))  # its domain is GraphRef: RDFS inference would type the node as one again
    g.add((node, RDF.type, new))


def _drop_quad_graph_name(g, r):
    from rdflib.collection import Collection

    qg = next(iter(Collection(g, g.value(_first_op(g, r), SQE.quads))))
    g.remove((qg, SQE.graphName, None))


MALFORMED = {
    "missing operations list": (P + "CLEAR ALL", lambda g, r: g.remove((r, SQE.operations, None))),
    "a clear without a target": (P + "CLEAR ALL", lambda g, r: g.remove((_first_op(g, r), SQE.target, None))),
    "create of ALL": (
        P + "CREATE GRAPH <g>", lambda g, r: _retype(g, _target(g, r), SQE.GraphRef, SQE.AllGraphs)
    ),
    "add from NAMED": (
        P + "ADD <a> TO <b>", lambda g, r: _retype(g, _target(g, r, SQE["from"]), SQE.GraphRef, SQE.NamedGraphs)
    ),
    "a graph reference without an IRI": (
        P + "CREATE GRAPH <g>", lambda g, r: g.remove((_target(g, r), SQE.graphIri, None))
    ),
    "a modify with no template": (
        P + "DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }", lambda g, r: g.remove((_first_op(g, r), SQE.delete, None))
    ),
    "a modify without where": (
        P + "DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }", lambda g, r: g.remove((_first_op(g, r), SQE.where, None))
    ),
    "a load without a source": (P + "LOAD <a>", lambda g, r: g.remove((_first_op(g, r), SQE.loadFrom, None))),
    "a non-boolean silent": (P + "LOAD <a>", lambda g, r: g.set((_first_op(g, r), SQE.silent, Literal("yes")))),
    "a quad graph without a name": (P + "INSERT DATA { GRAPH :g { :a :b :c } }", _drop_quad_graph_name),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_shapes_reject_malformed_operations(name):
    text, edit = MALFORMED[name]
    assert not _mutate(text, edit)
