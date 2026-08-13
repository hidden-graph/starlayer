import pytest
from rdflib import Graph


@pytest.fixture
def fixture_graph() -> Graph:
    g = Graph()
    g.parse(
        data="""
        @prefix : <http://example.org/> .
        @prefix foaf: <http://xmlns.com/foaf/0.1/> .

        :alice a foaf:Person ; foaf:name "Alice" ; foaf:age 30 ;
            foaf:knows :bob, :carol .
        :bob a foaf:Person ; foaf:name "Bob" ; foaf:age 25 .
        :carol a foaf:Person ; foaf:name "Carol" .
        """,
        format="turtle",
    )
    return g
