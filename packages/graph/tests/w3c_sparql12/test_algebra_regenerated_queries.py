"""Isolated regression cases for a specific, narrow class of bug: the
*original* W3C SPARQL 1.2 query text for these 6 fixtures already passes
cleanly against StarLayerGraph's in-memory backend (see
test_w3c_sparql12_eval.py's own test_eval_select_original_query/
test_eval_construct_original_query for those same 6 IDs) - but the
*algebra-regenerated* text the downstream starsparql project's own
SPARQL-1.2 -> RDF-algebra -> SPARQL-1.2 round-trip pipeline produces for
the identical query does not, when run against this same in-memory
backend.

This isn't an algebra-correctness bug: the regenerated text has already
been confirmed semantically equivalent to the original against two
independent, real RDF 1.2 engines (Oxigraph and Fuseki) - see the
downstream project's own tests/test_w3c_sparql12_oxigraph_roundtrip.py,
which passes cleanly for all 6 of these IDs against both backends. The
regenerated text is valid, correct SPARQL 1.2 - something specific to
*this* in-memory backend's own SPARQL 1.2 -> 1.1 text-rewriting pipeline
(starlayergraph/query/sparql12_to_11.py) trips on the regenerated phrasing
specifically, even though it handles the original phrasing of the exact
same query correctly.

The (original, regenerated) pairs below were captured once, directly from
the downstream project's own pipeline
(starsparql.parse12.prepare_query_12 -> query_to_rdf -> rdf_to_query
-> starsparql.serialize12.translate_algebra_12), and hardcoded here
rather than re-run live: this file's whole point is to isolate the bug
inside *this* repo's own test suite, with zero dependency on the sibling
project or a live Oxigraph/Fuseki instance, so it can be debugged and
fixed here directly.
"""

from __future__ import annotations

import pytest

from starlayergraph.graph.starlayer_dataset import StarLayerDataset
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from .harness import bindings_match

pytestmark = pytest.mark.w3c_sparql12

# ---------------------------------------------------------------------------
# Shared data fixtures - copied verbatim from tests/w3c_sparql12/data/, see
# each case's own data_file comment for which fixture it came from.
# ---------------------------------------------------------------------------

_DATA_2_TTL = """
PREFIX :       <http://example/>

:s :p1 :o .
<<:s :p1 :o>> :q :z .

# pattern-3
:a1 :b <<:s :p1 :o ~ :reifier >>  .
<<:s :p1 :o  ~ :reifier >> :b :a2 .

# pattern-3-nomatch
:a1 :b2 <<:s :p1 :o >>  .
<<:s :p1 :o >> :b2 :a2 .

# pattern-5
:s :p2 :o .
<<:s :p2 :o>> :sym <<:s :p2 :o>> .

# pattern-6
<<:s :p2 :o>> :p3 :z .
<< <<:s :p2 :o>> :p3 :z >> :q :o .

# pattern-8
<<:s :p2 :o ~ :reifier2 >> :p4 :z .
<< <<:s :p2 :o  ~ :reifier2 >> :p4 :z >> :q :o .
"""

_DATA_4_TRIG = """
PREFIX : <http://example/>

:s :p :o1 .

GRAPH :g {
     <<:s :p :o1 >> :q1 :z1 .
     <<:s :p :o2 >> :q2 :z2 .
}

GRAPH :g1 { _:b :r :o3 . _:b :r :o4 . }

GRAPH :g2 { << _:b :r :o3 >> :pb "abc" . }
"""

# ---------------------------------------------------------------------------
# Cases: (name, data, data_format, original_query, regenerated_query)
# data_format is None for the data-less expr-2/triple-on-undefs cases -
# both use only VALUES-supplied ground terms, no backing graph data needed.
# ---------------------------------------------------------------------------

SELECT_CASES = [
    (
        "pattern-6",
        _DATA_2_TTL,
        "turtle12",
        """
        PREFIX :       <http://example/>
        SELECT * {
          << <<:s :p2 :o>> :p3 :z>> :q  ?q .
        }
        """,
        """
        SELECT ?q{_:Naf55cb9e703a4fc9b4ba3dee0bf2a75a <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( _:Nd380b099c2514399a16fce4b15897ebb <http://example/p3> <http://example/z> )>>. _:Nd380b099c2514399a16fce4b15897ebb <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( <http://example/s> <http://example/p2> <http://example/o> )>>. _:Naf55cb9e703a4fc9b4ba3dee0bf2a75a <http://example/q> ?q. }
        """,
    ),
    (
        "graphs-1",
        _DATA_4_TRIG,
        "trig12",
        """
        PREFIX :       <http://example/>
        SELECT * {
           :s :p ?o .
           GRAPH ?g { <<:s :p ?o>> ?q ?z }
        }
        """,
        """
        SELECT ?o ?g ?q ?z{<http://example/s> <http://example/p> ?o. GRAPH ?g {_:N16420f64a20341ffbed782a2a851e608 <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( <http://example/s> <http://example/p> ?o )>>. _:N16420f64a20341ffbed782a2a851e608 ?q ?z. }}
        """,
    ),
    (
        "graphs-2",
        _DATA_4_TRIG,
        "trig12",
        """
        PREFIX :       <http://example/>
        SELECT * {
           GRAPH ?g1 { ?s ?p ?o }
           GRAPH ?g2 { << ?s ?p ?o >> ?q ?z }
        }
        """,
        """
        SELECT ?s ?o ?g1 ?p ?z ?g2 ?q{GRAPH ?g1 {?s ?p ?o. }GRAPH ?g2 {_:Nde52f34b3fc543509341543c6d335ce1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ?s ?p ?o )>>. _:Nde52f34b3fc543509341543c6d335ce1 ?q ?z. }}
        """,
    ),
    (
        "expr-2",
        None,
        None,
        """
        PREFIX :       <http://example/>
        SELECT * {
          VALUES ?t {
                 <<(:s :p :o )>>
                 :x
                  <<(:s :p :o1 )>>
                  }
          FILTER(isTriple(?t))
          FILTER(SUBJECT(?t) = :s)
          FILTER(PREDICATE(?t) = :p)
          FILTER(OBJECT(?t) = :o)
        }
        """,
        """
        SELECT ?t{FILTER(isTRIPLE(?t) && SUBJECT(?t) = <http://example/s> && PREDICATE(?t) = <http://example/p> && OBJECT(?t) = <http://example/o>) {{VALUES (?t){(<<( <http://example/s> <http://example/p> <http://example/o> )>>)(<http://example/x>)(<<( <http://example/s> <http://example/p> <http://example/o1> )>>)}}}}
        """,
    ),
    (
        "triple-on-undefs",
        None,
        None,
        """
        PREFIX : <http://example/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?subject ?predicate ?object ?triple {
          VALUES (?subject ?predicate ?object) {
            (:a :b :c)
            (UNDEF :b :c)
            (:a UNDEF :c)
            (:a :b UNDEF)
          }
          BIND(TRIPLE(?subject, ?predicate, ?object) AS ?triple)
        }
        """,
        """
        SELECT ?subject ?predicate ?object ?triple{{{VALUES (?subject ?predicate ?object){(<http://example/a> <http://example/b> <http://example/c>)(UNDEF <http://example/b> <http://example/c>)(<http://example/a> UNDEF <http://example/c>)(<http://example/a> <http://example/b> UNDEF)}}}BIND(<<( ?subject ?predicate ?object )>> AS ?triple)}
        """,
    ),
]

CONSTRUCT_CASES = [
    (
        "expr-1",
        _DATA_4_TRIG,
        "trig12",
        """
        PREFIX : <http://example/>
        CONSTRUCT {
          ?g :graphContains ?t .
        } WHERE {
          GRAPH ?g {
            ?s ?p ?o .
            BIND(<<(?s ?p  ?o)>> AS ?t)
          }
        }
        """,
        """
        CONSTRUCT {?g <http://example/graphContains> ?t. } WHERE {GRAPH ?g {?s ?p ?o. BIND(<<( ?s ?p ?o )>> AS ?t)}}
        """,
    ),
]


def _new_graph(data_format: str | None) -> StarLayerGraph | StarLayerDataset:
    if data_format in ("trig12", "nq12"):
        return StarLayerDataset()
    return StarLayerGraph()


@pytest.mark.parametrize("name,data,fmt,original,regenerated", SELECT_CASES, ids=[c[0] for c in SELECT_CASES])
def test_regenerated_select_matches_original(name, data, fmt, original, regenerated):
    g = _new_graph(fmt)
    if data:
        g.parse(data=data, format=fmt)

    original_bindings = [dict(row) for row in g.query(original).bindings]
    regenerated_bindings = [dict(row) for row in g.query(regenerated).bindings]

    assert bindings_match(original_bindings, regenerated_bindings), (
        f"[{name}] original and regenerated disagree against starlayergraph's in-memory backend.\n"
        f"original Q:\n{original}\nregenerated Q':\n{regenerated}\n"
        f"original results: {original_bindings}\nregenerated results: {regenerated_bindings}"
    )


@pytest.mark.parametrize("name,data,fmt,original,regenerated", CONSTRUCT_CASES, ids=[c[0] for c in CONSTRUCT_CASES])
def test_regenerated_construct_matches_original(name, data, fmt, original, regenerated):
    g = _new_graph(fmt)
    if data:
        g.parse(data=data, format=fmt)

    original_graph = g.query(original).graph
    regenerated_graph = g.query(regenerated).graph

    original_triples = set(original_graph)
    regenerated_triples = set(regenerated_graph)

    assert original_triples == regenerated_triples, (
        f"[{name}] original and regenerated disagree against starlayergraph's in-memory backend.\n"
        f"original Q:\n{original}\nregenerated Q':\n{regenerated}\n"
        f"original triples: {original_triples}\nregenerated triples: {regenerated_triples}"
    )
