"""skolem_semantics.rewrite(): isBLANK / isIRI / ORDER BY must give the same
answers over skolem IRIs as the original query gives over real blank nodes.

Checked by running the ORIGINAL query on a graph holding real blank nodes and
the REWRITTEN query on an identical graph in which every blank node has been
replaced by its skolem IRI, then comparing the results with skolem IRIs mapped
back to blank nodes. No server involved - rdflib evaluates both."""

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from starlayer.graph.backends.skolem_semantics import rewrite
from starlayer.graph.model.encoding import BN_NS

EX = "http://example.org/"


def _graphs():
    """Same data twice: with real blank nodes, and with skolem IRIs."""
    b = {n: BNode(n) for n in ("b1", "b2", "b3")}
    sk = {n: URIRef(BN_NS + n) for n in b}
    def build(nodes):
        g = Graph()
        for i, n in enumerate(("b1", "b2", "b3")):
            g.add((URIRef(EX + f"s{i}"), URIRef(EX + "p"), nodes[n]))
        g.add((URIRef(EX + "s3"), URIRef(EX + "p"), URIRef(EX + "iri-a")))
        g.add((URIRef(EX + "s4"), URIRef(EX + "p"), URIRef(EX + "iri-b")))
        g.add((URIRef(EX + "s5"), URIRef(EX + "p"), Literal("lit-a")))
        g.add((URIRef(EX + "s6"), URIRef(EX + "p"), Literal("lit-b")))
        return g
    return build(b), build(sk)


def _norm(rows):
    """Map skolem IRIs back to a generic blank-node marker."""
    out = []
    for row in rows:
        out.append(tuple("_:bnode" if isinstance(v, BNode) or (isinstance(v, URIRef) and str(v).startswith(BN_NS)) else str(v) for v in row))
    return out


QUERIES = [
    ("isBLANK filter", "SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(isBLANK(?x)) }", False),
    ("not isBLANK", "SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(!isBLANK(?x)) } ORDER BY ?x", True),
    ("isIRI filter", "SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(isIRI(?x)) } ORDER BY ?x", True),
    ("isURI filter", "SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(isURI(?x)) } ORDER BY ?x", True),
    ("isLiteral untouched", "SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(isLiteral(?x)) } ORDER BY ?x", True),
    ("ORDER BY var", "SELECT ?x WHERE { ?s <http://example.org/p> ?x } ORDER BY ?x", True),
    ("ORDER BY DESC", "SELECT ?x WHERE { ?s <http://example.org/p> ?x } ORDER BY DESC(?x)", True),
    ("ORDER BY ASC()", "SELECT ?x WHERE { ?s <http://example.org/p> ?x } ORDER BY ASC(?x)", True),
    ("ORDER BY then LIMIT", "SELECT ?x WHERE { ?s <http://example.org/p> ?x } ORDER BY ?x LIMIT 4", True),
    ("two conditions", "SELECT ?s ?x WHERE { ?s <http://example.org/p> ?x } ORDER BY ?x ?s", True),
    ("isBLANK in BIND", "SELECT ?x ?k WHERE { ?s <http://example.org/p> ?x BIND(isBLANK(?x) AS ?k) } ORDER BY ?x", True),
    ("string that mentions the words", 'SELECT ?x WHERE { ?s <http://example.org/p> ?x FILTER(?x != "ORDER BY isBLANK(") } ORDER BY ?x', True),
]


@pytest.mark.parametrize("label,query,ordered", QUERIES, ids=[q[0] for q in QUERIES])
def test_skolem_iris_behave_like_blank_nodes(label, query, ordered):
    real, skolem = _graphs()
    expected = _norm(list(real.query(query)))
    actual = _norm(list(skolem.query(rewrite(query))))
    if ordered:
        # blank nodes have no relative order, so compare kinds in order and the rest exactly
        assert actual == expected, f"\nquery:    {query}\nrewritten: {rewrite(query)}"
    else:
        assert sorted(actual) == sorted(expected)


def test_text_without_those_constructs_is_unchanged():
    q = "SELECT ?s WHERE { ?s <http://example.org/p> ?o } LIMIT 3"
    assert rewrite(q) == q


def test_iri_containing_hash_or_angle_text_is_not_mangled():
    q = "SELECT ?s WHERE { ?s <http://example.org/a#isBLANK(> ?o }"
    assert rewrite(q) == q
