"""Phase 2d: SPARQL property paths.

Unlike everything else covered so far, a property path
(rdflib.paths.Path: InvPath/SequencePath/AlternativePath/MulPath/
NegatedPath) is a plain Python object, not a CompValue — it needed
dedicated vocab classes and explicit encode/decode branches (see
to_rdf._encode_path / from_rdf._decode_path and vocab.py's "Property
paths" section), unlike every other Phase 2 feature which the generic
CompValue walker already covered for free.
"""

import pytest
from rdflib import Graph
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery

from starsparql import query_to_rdf, rdf_to_query

PREFIXES = "PREFIX : <http://example.org/>\n"

QUERIES = [
    PREFIXES + "SELECT ?x WHERE { :alice :knows+ ?x }",       # MulPath (OneOrMore)
    PREFIXES + "SELECT ?x WHERE { :alice :knows* ?x }",       # MulPath (ZeroOrMore)
    PREFIXES + "SELECT ?x WHERE { :alice :knows? ?x }",       # MulPath (ZeroOrOne)
    PREFIXES + "SELECT ?x WHERE { :bob ^:knows ?x }",         # InvPath
    PREFIXES + "SELECT ?x ?y WHERE { ?x (:knows|:likes) ?y }",  # AlternativePath
    PREFIXES + "SELECT ?x WHERE { :alice :knows/:knows ?x }",   # SequencePath
    PREFIXES + "SELECT ?x ?y WHERE { ?x !(:knows) ?y }",         # NegatedPath
    PREFIXES + "SELECT ?x WHERE { :alice (:knows|:likes)+ ?x }",  # MulPath wrapping AlternativePath
]


@pytest.fixture
def knows_graph():
    g = Graph()
    g.parse(
        data="""
        @prefix : <http://example.org/> .
        :alice :knows :bob .
        :bob :knows :carol .
        :carol :knows :dave .
        :alice :likes :cat .
        :bob :likes :dog .
        """,
        format="turtle",
    )
    return g


def _canon(res):
    rows = [
        frozenset((str(k), v.n3()) for k, v in b.items() if v is not None)
        for b in res["bindings"]
    ]
    return sorted(rows, key=lambda r: sorted(r))


@pytest.mark.parametrize("query_text", QUERIES)
def test_roundtrip_result_equivalence(knows_graph, query_text):
    prepared = prepareQuery(query_text)
    original = evalQuery(knows_graph, prepared)

    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    roundtripped = evalQuery(knows_graph, reconstructed)

    canon_original = _canon(original)
    canon_roundtripped = _canon(roundtripped)
    assert canon_original == canon_roundtripped
    assert len(canon_original) > 0
