"""
Integration tests for StarLayerGraph.update() with SPARQL 1.2 triple-term syntax.

Covers:
  U1 — DELETE WHERE with triple term in WHERE clause
  U2 — INSERT WHERE with triple term in WHERE clause
  U3 — INSERT DATA with ground triple term
  U4 — DELETE DATA with ground triple term
  U5 — Combined DELETE/INSERT WHERE with triple term
"""

import pytest
from rdflib import URIRef
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'
RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')

DATASET = """
@prefix :    <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" ;
       :source :WikiData .

:stmt2 rdf:reifies <<( :alice :knows :bob )>> ;
       :confidence "0.7" .
"""


@pytest.fixture
def g():
    sg = StarLayerGraph()
    sg.parse(data=DATASET, format='turtle12')
    return sg


# ---------------------------------------------------------------------------
# U1 — DELETE WHERE: remove a property of a reifier found via triple term
# ---------------------------------------------------------------------------

class TestU1:
    def test_delete_confidence_of_known_triple(self, g):
        # Confirm it exists before
        assert any(True for _ in g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'confidence'), None)))

        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r :confidence ?c }
            WHERE  { ?r rdf:reifies <<( :bob :knows :carol )>> ;
                        :confidence ?c }
        """)

        triples = list(g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'confidence'), None)))
        assert triples == []

    def test_other_properties_unaffected(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r :confidence ?c }
            WHERE  { ?r rdf:reifies <<( :bob :knows :carol )>> ;
                        :confidence ?c }
        """)
        # :source should still be there
        source_triples = list(g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'source'), None)))
        assert source_triples != []

    def test_delete_where_wrong_triple_term_is_noop(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r :confidence ?c }
            WHERE  { ?r rdf:reifies <<( :nobody :knows :anyone )>> ;
                        :confidence ?c }
        """)
        # Nothing should be deleted
        triples = list(g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'confidence'), None)))
        assert triples != []


# ---------------------------------------------------------------------------
# U2 — INSERT WHERE: add a property to a reifier found via triple term
# ---------------------------------------------------------------------------

class TestU2:
    def test_insert_new_property_via_triple_term(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT { ?r :verified :true }
            WHERE  { ?r rdf:reifies <<( :bob :knows :carol )>> }
        """)
        verified = list(g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'verified'), None)))
        assert len(verified) == 1
        assert verified[0][2] == URIRef(EX + 'true')

    def test_insert_where_only_affects_matching_reifier(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT { ?r :verified :true }
            WHERE  { ?r rdf:reifies <<( :bob :knows :carol )>> }
        """)
        # stmt2 reifies a different triple — should NOT be tagged
        verified2 = list(g.triples((URIRef(EX + 'stmt2'), URIRef(EX + 'verified'), None)))
        assert verified2 == []


# ---------------------------------------------------------------------------
# U3 — INSERT DATA with ground triple term
# ---------------------------------------------------------------------------

class TestU3:
    def test_insert_data_adds_reification(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {
                :stmt3 rdf:reifies <<( :carol :knows :dave )>> .
                :stmt3 :confidence "0.5" .
            }
        """)
        stmt3 = URIRef(EX + 'stmt3')
        # rdf:reifies triple exists
        reifies = list(g.triples((stmt3, RDF_REIFIES, None)))
        assert len(reifies) == 1
        tt = reifies[0][2]
        assert isinstance(tt, TripleTerm)
        assert tt.subject   == URIRef(EX + 'carol')
        assert tt.predicate == URIRef(EX + 'knows')
        assert tt.object    == URIRef(EX + 'dave')

    def test_insert_data_triple_term_registered(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {
                :stmt3 rdf:reifies <<( :carol :knows :dave )>> .
            }
        """)
        assert g.has_triple_term(
            URIRef(EX + 'carol'), URIRef(EX + 'knows'), URIRef(EX + 'dave')
        )

    def test_insert_data_queryable_after_insert(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT DATA {
                :stmt3 rdf:reifies <<( :carol :knows :dave )>> .
            }
        """)
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?r WHERE { ?r rdf:reifies <<( :carol :knows :dave )>> }
        """)
        stmts = {row[r.vars[0]] for row in r.bindings}
        assert URIRef(EX + 'stmt3') in stmts


# ---------------------------------------------------------------------------
# U4 — DELETE DATA with ground triple term
# ---------------------------------------------------------------------------

class TestU4:
    def test_delete_data_removes_reification_triple(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE DATA {
                :stmt2 rdf:reifies <<( :alice :knows :bob )>> .
            }
        """)
        stmt2 = URIRef(EX + 'stmt2')
        reifies = list(g.triples((stmt2, RDF_REIFIES, None)))
        assert reifies == []

    def test_delete_data_preserves_encoding_triples(self, g):
        """Encoding triples (rdf:subject/predicate/object) must not be removed."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE DATA {
                :stmt2 rdf:reifies <<( :alice :knows :bob )>> .
            }
        """)
        # The TT should still be registered and queryable
        tt = next(g.triple_terms(
            URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob')
        ), None)
        assert tt is not None

    def test_delete_data_other_reifier_unaffected(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE DATA {
                :stmt2 rdf:reifies <<( :alice :knows :bob )>> .
            }
        """)
        # stmt1 reifies a different TT, should be untouched
        reifies1 = list(g.triples((URIRef(EX + 'stmt1'), RDF_REIFIES, None)))
        assert len(reifies1) == 1


# ---------------------------------------------------------------------------
# U5 — Combined DELETE/INSERT WHERE
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# U6 — INSERT template with <<( )>> in subject position (post-processing path)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# U7 — INSERT/DELETE template with <<( )>> in object position
# ---------------------------------------------------------------------------

class TestU7:
    def test_insert_template_tt_object_creates_reification(self, g):
        """Ground subject + TT object: :newStmt rdf:reifies <<( ?s ?p ?o )>>."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT { :newStmt rdf:reifies <<( ?s ?p ?o )>> }
            WHERE  { :stmt1 rdf:reifies <<( ?s ?p ?o )>> }
        """)
        new_stmt = URIRef(EX + 'newStmt')
        reifies = list(g.triples((new_stmt, RDF_REIFIES, None)))
        assert len(reifies) == 1
        tt = reifies[0][2]
        assert isinstance(tt, TripleTerm)
        assert tt.subject   == URIRef(EX + 'bob')
        assert tt.predicate == URIRef(EX + 'knows')
        assert tt.object    == URIRef(EX + 'carol')

    def test_insert_template_tt_object_registered(self, g):
        """TT created via object-position template INSERT is registered."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT { :newStmt rdf:reifies <<( ?s ?p ?o )>> }
            WHERE  { :stmt1 rdf:reifies <<( ?s ?p ?o )>> }
        """)
        assert g.has_triple_term(
            URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')
        )

    def test_insert_template_variable_subject_and_tt_object(self, g):
        """Variable reifier subject bound from WHERE + TT in object position."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            INSERT { ?r2 rdf:reifies <<( ?s ?p ?o )>> . ?r2 :clone :true }
            WHERE  { :stmt2 rdf:reifies <<( ?s ?p ?o )>> .
                     BIND(:cloneOfStmt2 AS ?r2) }
        """)
        clone = URIRef(EX + 'cloneOfStmt2')
        reifies = list(g.triples((clone, RDF_REIFIES, None)))
        assert len(reifies) == 1
        tt = reifies[0][2]
        assert tt.subject   == URIRef(EX + 'alice')
        assert tt.predicate == URIRef(EX + 'knows')
        assert tt.object    == URIRef(EX + 'bob')

    def test_delete_template_tt_object_removes_reification(self, g):
        """DELETE template with TT in object position removes the reification triple."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r rdf:reifies <<( ?s ?p ?o )>> }
            WHERE  { ?r rdf:reifies <<( ?s ?p ?o )>> . ?r :confidence "0.9" }
        """)
        stmt1 = URIRef(EX + 'stmt1')
        reifies = list(g.triples((stmt1, RDF_REIFIES, None)))
        assert reifies == []

    def test_delete_template_tt_object_preserves_other_reifier(self, g):
        """DELETE with TT object only removes the matching reifier, not others."""
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r rdf:reifies <<( ?s ?p ?o )>> }
            WHERE  { ?r rdf:reifies <<( ?s ?p ?o )>> . ?r :confidence "0.9" }
        """)
        # stmt2 has confidence "0.7" — should be untouched
        stmt2 = URIRef(EX + 'stmt2')
        reifies = list(g.triples((stmt2, RDF_REIFIES, None)))
        assert len(reifies) == 1

class TestU6:
    def test_insert_template_tt_registered_after_insert(self, g):
        """New TT created via INSERT template must be registered in the graph.

        Uses reifier shorthand (no parens), not a raw triple term, as the
        template's subject - a raw `<<( s p o )>>` triple term is never
        legal RDF 1.2 in subject position (see
        starsparql.triple_term.InvalidTripleTermError's rule 2,
        2026-08-15). The shorthand still constructs and registers the same
        underlying (alice, knows, bob) triple term - it just does so as the
        object of an auto-generated `rdf:reifies` triple rather than
        directly as `:note`'s subject - so this still correctly exercises
        the thing this test is named for."""
        g.update("""
            PREFIX :   <http://example.org/>
            INSERT { <<:alice :knows :bob ~ :myReifier>> :note :x }
            WHERE  { :alice :knows :bob }
        """)
        from rdflib import URIRef
        assert g.has_triple_term(
            URIRef(EX + 'alice'), URIRef(EX + 'knows'), URIRef(EX + 'bob')
        )


# ---------------------------------------------------------------------------
# U5 — Combined DELETE/INSERT WHERE
# ---------------------------------------------------------------------------

class TestU5:
    def test_replace_source_for_known_triple(self, g):
        g.update("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            DELETE { ?r :source ?old }
            INSERT { ?r :source :NewSource }
            WHERE  { ?r rdf:reifies <<( :bob :knows :carol )>> ;
                        :source ?old }
        """)
        sources = list(g.triples((URIRef(EX + 'stmt1'), URIRef(EX + 'source'), None)))
        assert len(sources) == 1
        assert sources[0][2] == URIRef(EX + 'NewSource')
