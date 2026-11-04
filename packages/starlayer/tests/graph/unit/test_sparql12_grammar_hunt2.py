"""SPARQL 1.2 pattern and data fixes from the third hunt (GitHub issue #93)."""

import warnings

import pytest
from starlayer.graph.oxgraph import OxGraph

warnings.simplefilter("ignore")
P = "PREFIX : <http://e/> "


def _graph():
    g = OxGraph()
    g.parse(
        data="@prefix : <http://e/> . :s :p <<( :x :q :y )>> . :s2 :p <<( :x2 :q :y2 )>> . :s3 :p :z .",
        format="turtle12",
    )
    return g


def _subjects(query):
    return sorted(r[0].value.rsplit("/", 1)[-1] for r in _graph().query(P + query))


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("<<( _:b :q :y )>>", ["s"]),
        ("<<( [] :q ?o )>>", ["s", "s2"]),
        ("<<( :x :q _:c )>>", ["s"]),
        ("<<( _:b :q _:b )>>", []),  # one blank node twice: subject and object must be the same term
        ("<<( ?a :q ?o )>>", ["s", "s2"]),
        ("<<( :x :q :y )>>", ["s"]),
    ],
)
def test_a_blank_node_inside_a_triple_term_in_a_pattern_is_an_anonymous_variable(pattern, expected):
    assert _subjects(f"SELECT ?s {{ ?s :p {pattern} }}") == expected


@pytest.mark.parametrize(
    "update",
    [
        "INSERT DATA { ?s :p :o }",
        "INSERT DATA { :s ?p :o }",
        "INSERT DATA { GRAPH :g { :s :p ?o } }",
        "INSERT DATA { :s :p <<( ?x :q :y )>> }",
        "DELETE DATA { :s :p ?o }",
        "DELETE DATA { :s :p <<( _:b :q :y )>> }",
    ],
)
def test_data_blocks_take_ground_data(update):
    with pytest.raises(SyntaxError):  # Oxigraph rejects it as a syntax error (O5); the old parser raised ValueError("not permitted")
        OxGraph().update(P + update)


@pytest.mark.parametrize(
    "update",
    ["INSERT DATA { :s :p :o }", "INSERT DATA { :s :p <<( :x :q :y )>> }", "INSERT { ?s :q :o } WHERE { ?s :p :o }"],
)
def test_ground_data_and_templates_with_variables_still_work(update):
    OxGraph().update(P + update)
