"""
Unit tests for StarLayerDataset.query() and .update() with SPARQL-star.

Covers:
  - SELECT with ground triple-term pattern in a named graph
  - SELECT with variable triple-term pattern across multiple graphs
  - SELECT with SUBJECT/PREDICATE/OBJECT accessor functions inside GRAPH blocks
  - SELECT with isTRIPLE() filter
  - CONSTRUCT query
  - ASK query
  - UPDATE with WHERE clause containing triple-term pattern
  - UPDATE result visible through get_context() after registry rebuild
"""

import pytest
from rdflib import Literal, URIRef
from starlayergraph.graph import StarLayerDataset, StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'
G1 = URIRef(EX + 'graph1')
G2 = URIRef(EX + 'graph2')


def ex(local):
    return URIRef(EX + local)


TRIG = f"""\
@prefix ex: <{EX}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

GRAPH <{EX}graph1> {{
  ex:stmt1 rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
  ex:stmt1 ex:confidence "0.9" .
  ex:alice ex:knows ex:bob .
}}

GRAPH <{EX}graph2> {{
  ex:stmt2 rdf:reifies <<( ex:bob ex:likes ex:carol )>> .
  ex:stmt2 ex:source ex:newspaper .
}}
"""


@pytest.fixture
def ds():
    d = StarLayerDataset()
    d.parse(data=TRIG, format='trig12')
    return d


# ---------------------------------------------------------------------------
# SELECT — ground triple-term pattern
# ---------------------------------------------------------------------------

class TestSelectGround:
    def test_select_in_specific_graph(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert rows[0][0] == ex('stmt1')

    def test_select_across_graphs(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt ?g WHERE {{
            GRAPH ?g {{
                ?stmt rdf:reifies <<( ?s ?p ?o )>> .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 2
        stmts = {row[0] for row in rows}
        assert ex('stmt1') in stmts
        assert ex('stmt2') in stmts

    def test_select_result_is_uri_not_triple_term(self, ds):
        """?stmt is bound to a URI (the reifier), not a TripleTerm."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert isinstance(rows[0][0], URIRef)

    def test_no_match_returns_empty(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:nobody ex:knows ex:nobody )>> .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert rows == []


# ---------------------------------------------------------------------------
# SELECT — triple-term object restoration
# ---------------------------------------------------------------------------

class TestSelectRestore:
    def test_variable_bound_to_triple_term_restored(self, ds):
        """When ?tt is bound to a tt:HASH encoding, it should be restored to TripleTerm."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        tt = rows[0][0]
        assert isinstance(tt, TripleTerm)
        assert tt == TripleTerm(ex('alice'), ex('knows'), ex('bob'))

    def test_triple_term_from_graph2_restored(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {{
            GRAPH <{EX}graph2> {{
                ex:stmt2 rdf:reifies ?tt .
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        tt = rows[0][0]
        assert isinstance(tt, TripleTerm)
        assert tt == TripleTerm(ex('bob'), ex('likes'), ex('carol'))

    def test_triple_terms_from_both_graphs_restored(self, ds):
        q = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {
            GRAPH ?g {
                ?stmt rdf:reifies ?tt .
            }
        }
        """
        rows = list(ds.query(q))
        tts = {row[0] for row in rows}
        assert TripleTerm(ex('alice'), ex('knows'), ex('bob')) in tts
        assert TripleTerm(ex('bob'), ex('likes'), ex('carol')) in tts


# ---------------------------------------------------------------------------
# SELECT — SPARQL-star accessor functions inside GRAPH blocks
# ---------------------------------------------------------------------------

class TestSelectFunctions:
    def test_subject_via_bind(self, ds):
        """BIND(SUBJECT(?tt) AS ?s) inside a GRAPH block extracts the subject."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?s WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
                BIND(SUBJECT(?tt) AS ?s)
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert rows[0][0] == ex('alice')

    def test_predicate_via_bind(self, ds):
        """BIND(PREDICATE(?tt) AS ?p) inside a GRAPH block extracts the predicate."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?p WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
                BIND(PREDICATE(?tt) AS ?p)
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert rows[0][0] == ex('knows')

    def test_object_via_bind(self, ds):
        """BIND(OBJECT(?tt) AS ?o) inside a GRAPH block extracts the object."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?o WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
                BIND(OBJECT(?tt) AS ?o)
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert rows[0][0] == ex('bob')

    def test_all_components_via_bind(self, ds):
        """All three BIND accessors work together inside a GRAPH block."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
                BIND(SUBJECT(?tt) AS ?s)
                BIND(PREDICATE(?tt) AS ?p)
                BIND(OBJECT(?tt) AS ?o)
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert rows[0][0] == ex('alice')
        assert rows[0][1] == ex('knows')
        assert rows[0][2] == ex('bob')

    def test_istriple_filter(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 rdf:reifies ?tt .
                FILTER(isTRIPLE(?tt))
            }}
        }}
        """
        rows = list(ds.query(q))
        assert len(rows) == 1
        assert isinstance(rows[0][0], TripleTerm)


# ---------------------------------------------------------------------------
# ASK
# ---------------------------------------------------------------------------

class TestAsk:
    def test_ask_true_when_pattern_matches(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        ASK {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
            }}
        }}
        """
        assert bool(ds.query(q))

    def test_ask_false_when_no_match(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        ASK {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:nobody ex:knows ex:nobody )>> .
            }}
        }}
        """
        assert not bool(ds.query(q))


# ---------------------------------------------------------------------------
# CONSTRUCT
# ---------------------------------------------------------------------------

class TestConstruct:
    def test_construct_returns_starlayer_graph(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        CONSTRUCT {{ ?stmt ex:about ?tt }}
        WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies ?tt .
            }}
        }}
        """
        r = ds.query(q)
        assert isinstance(r.graph, StarLayerGraph)

    def test_construct_result_has_triple(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        CONSTRUCT {{ ?stmt ex:confidence ?c }}
        WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt ex:confidence ?c .
            }}
        }}
        """
        r = ds.query(q)
        triples = list(r.graph.triples((None, None, None)))
        assert len(triples) == 1
        assert triples[0][0] == ex('stmt1')


# ---------------------------------------------------------------------------
# UPDATE — plain triple, no <<( )>> in WHERE
# ---------------------------------------------------------------------------

class TestUpdatePlain:
    def test_insert_plain_triple_visible_in_context(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{
            GRAPH <{EX}graph1> {{
                ex:alice ex:age "30" .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        assert (ex('alice'), ex('age'), Literal('30')) in g1

    def test_delete_plain_triple(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        DELETE DATA {{
            GRAPH <{EX}graph1> {{
                ex:stmt1 ex:confidence "0.9" .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        assert (ex('stmt1'), ex('confidence'), Literal('0.9')) not in g1


# ---------------------------------------------------------------------------
# UPDATE — triple-term pattern in WHERE clause
# ---------------------------------------------------------------------------

class TestUpdateWithTripleTerm:
    def test_insert_using_triple_term_where(self, ds):
        """Mark all statements about alice-knows-bob as verified."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        INSERT {{
            GRAPH <{EX}graph1> {{ ?stmt ex:verified "true" . }}
        }}
        WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        assert (ex('stmt1'), ex('verified'), Literal('true')) in g1

    def test_delete_using_triple_term_where(self, ds):
        """Remove confidence annotation for any alice-knows-bob reification."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        DELETE {{
            GRAPH <{EX}graph1> {{ ?stmt ex:confidence ?c . }}
        }}
        WHERE {{
            GRAPH <{EX}graph1> {{
                ?stmt rdf:reifies <<( ex:alice ex:knows ?o )>> .
                ?stmt ex:confidence ?c .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        triples = list(g1.triples((ex('stmt1'), ex('confidence'), None)))
        assert triples == []

    def test_cross_graph_update(self, ds):
        """Copy a metadata property from graph2 to graph1 when graphs share a subject predicate."""
        q = f"""
        PREFIX ex: <{EX}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        INSERT {{
            GRAPH <{EX}graph1> {{ ?stmt2 ex:copied "yes" . }}
        }}
        WHERE {{
            GRAPH <{EX}graph2> {{
                ?stmt2 rdf:reifies <<( ?s ?p ?o )>> .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        assert (ex('stmt2'), ex('copied'), Literal('yes')) in g1

    def test_registry_intact_after_update(self, ds):
        """Triple-term registry in graph1 must survive an UPDATE that touches graph1."""
        q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{
            GRAPH <{EX}graph1> {{ ex:extra ex:p ex:o . }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        assert g1.has_triple_term(ex('alice'), ex('knows'), ex('bob'))


# ---------------------------------------------------------------------------
# UPDATE — ground triple term directly inside INSERT DATA / DELETE DATA
#
# QuadData (the { ... } block in INSERT DATA/DELETE DATA) forbids all
# expressions, permitting only ground terms - so a ground <<( s p o )>>
# triple term here can't be handled the way one inside an ordinary WHERE
# clause is (hoisting to a BIND). See
# starlayergraph.query.sparql12_to_11._rewrite_insert_delete_data_blocks.
# ---------------------------------------------------------------------------

class TestUpdateDataWithGroundTripleTerm:
    def test_insert_data_with_ground_triple_term(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{
            ex:who ex:verifiedBy <<( ex:alice ex:knows ex:bob )>> .
        }}
        """
        ds.update(q)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        matches = list(ds.triples((ex('who'), ex('verifiedBy'), None)))
        assert matches == [(ex('who'), ex('verifiedBy'), tt)]

    def test_delete_data_with_ground_triple_term(self, ds):
        insert_q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{
            ex:who ex:verifiedBy <<( ex:alice ex:knows ex:bob )>> .
        }}
        """
        ds.update(insert_q)
        delete_q = f"""
        PREFIX ex: <{EX}>
        DELETE DATA {{
            ex:who ex:verifiedBy <<( ex:alice ex:knows ex:bob )>> .
        }}
        """
        ds.update(delete_q)
        matches = list(ds.triples((ex('who'), ex('verifiedBy'), None)))
        assert matches == []

    def test_insert_data_with_ground_triple_term_in_named_graph(self, ds):
        q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{
            GRAPH <{EX}graph1> {{
                ex:who ex:verifiedBy <<( ex:alice ex:knows ex:bob )>> .
            }}
        }}
        """
        ds.update(q)
        g1 = ds.get_context(G1)
        tt = TripleTerm(ex('alice'), ex('knows'), ex('bob'))
        assert (ex('who'), ex('verifiedBy'), tt) in g1

    def test_insert_data_without_triple_term_still_works(self, ds):
        """Plain INSERT DATA (no triple term at all) must be unaffected by
        this rewrite pass - it should never even fire."""
        q = f"""
        PREFIX ex: <{EX}>
        INSERT DATA {{ ex:dave ex:age "40" . }}
        """
        ds.update(q)
        matches = list(ds.triples((ex('dave'), ex('age'), None)))
        assert matches == [(ex('dave'), ex('age'), Literal('40'))]
