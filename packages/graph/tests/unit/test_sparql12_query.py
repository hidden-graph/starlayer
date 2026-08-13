"""
Integration tests for StarLayerGraph.query() with SPARQL 1.2 triple-term syntax.

Each test class corresponds to one query example from sparql12_design.md.
The shared dataset matches the one defined at the top of that document.
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF

from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.model.triple import TripleTerm

EX = 'http://example.org/'

DATASET = """
@prefix :    <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

:alice :says <<( :bob :knows :carol )>> .

:stmt1 rdf:reifies <<( :bob :knows :carol )>> ;
       :confidence "0.9" ;
       :source :WikiData .

:bob :knows :carol {| :since "2020" ; :via :LinkedIn |} .

<< :bob :knows :carol >> :verifiedBy :ResearchTeam .
"""


@pytest.fixture
def g():
    sg = StarLayerGraph()
    sg.parse(data=DATASET, format='turtle12')
    return sg


def _uris(rows, var):
    return {row[var] for row in rows}


# ---------------------------------------------------------------------------
# Q1 — Triple term in object position (reification)
# ---------------------------------------------------------------------------

class TestQ1:
    def test_finds_named_reifier(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
            }
        """)
        stmts = _uris(r.bindings, r.vars[0])
        assert URIRef(EX + 'stmt1') in stmts

    def test_finds_anonymous_reifier(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
            }
        """)
        stmts = _uris(r.bindings, r.vars[0])
        assert len(stmts) == 3  # stmt1 (named) + anon from {| |} + anon from << >>

    def test_no_result_for_unknown_triple_term(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies <<( :x :y :z )>> .
            }
        """)
        assert r.bindings == []


# ---------------------------------------------------------------------------
# Q2 — Triple term as subject
# ---------------------------------------------------------------------------

class TestQ2:
    def test_triple_term_as_subject(self, g):
        # << >> (reification shorthand) in SPARQL subject position matches via reifier
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who WHERE {
              << :bob :knows :carol >> :verifiedBy ?who .
            }
        """)
        who = {row[r.vars[0]] for row in r.bindings}
        assert who == {URIRef(EX + 'ResearchTeam')}


# ---------------------------------------------------------------------------
# Q3 — Triple term in object position (non-reification)
# ---------------------------------------------------------------------------

class TestQ3:
    def test_triple_term_as_object(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who WHERE {
              ?who :says <<( :bob :knows :carol )>> .
            }
        """)
        who = {row[r.vars[0]] for row in r.bindings}
        assert who == {URIRef(EX + 'alice')}


# ---------------------------------------------------------------------------
# Q4 — Variable triple term components
# ---------------------------------------------------------------------------

class TestQ4:
    def test_variable_components_bind_correctly(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?s ?p ?o WHERE {
              ?stmt rdf:reifies <<( ?s ?p ?o )>> .
            }
        """)
        s_var, p_var, o_var = r.vars[1], r.vars[2], r.vars[3]
        for row in r.bindings:
            assert row[s_var] == URIRef(EX + 'bob')
            assert row[p_var] == URIRef(EX + 'knows')
            assert row[o_var] == URIRef(EX + 'carol')

    def test_two_reifiers_returned(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?s ?p ?o WHERE {
              ?stmt rdf:reifies <<( ?s ?p ?o )>> .
            }
        """)
        assert len(r.bindings) == 3  # stmt1 + anon from {| |} + anon from << >>


# ---------------------------------------------------------------------------
# Q5 — OPTIONAL annotations on a reifier
# ---------------------------------------------------------------------------

class TestQ5:
    def test_named_reifier_has_confidence(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?conf ?source WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              OPTIONAL { ?stmt :confidence ?conf . }
              OPTIONAL { ?stmt :source ?source . }
            }
        """)
        stmt_var, conf_var, src_var = r.vars[0], r.vars[1], r.vars[2]
        by_stmt = {row[stmt_var]: row for row in r.bindings}
        stmt1 = by_stmt[URIRef(EX + 'stmt1')]
        assert stmt1[conf_var] == Literal('0.9')
        assert stmt1[src_var] == URIRef(EX + 'WikiData')

    def test_anonymous_reifier_has_no_confidence(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?conf WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              OPTIONAL { ?stmt :confidence ?conf . }
            }
        """)
        stmt_var, conf_var = r.vars[0], r.vars[1]
        stmt1_rows = [row for row in r.bindings if row[stmt_var] == URIRef(EX + 'stmt1')]
        anon_rows  = [row for row in r.bindings if row[stmt_var] != URIRef(EX + 'stmt1')]
        assert stmt1_rows[0][conf_var] == Literal('0.9')
        assert anon_rows[0][conf_var] is None


# ---------------------------------------------------------------------------
# Q6 — Triple term selected as a variable (post-processing)
# ---------------------------------------------------------------------------

class TestQ6:
    def test_tt_restored_to_triple_term_object(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who ?tt WHERE {
              ?who :says ?tt .
            }
        """)
        tt_var = r.vars[1]
        tt = r.bindings[0][tt_var]
        assert isinstance(tt, TripleTerm)

    def test_tt_str_uses_prefixed_names(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who ?tt WHERE {
              ?who :says ?tt .
            }
        """)
        tt = r.bindings[0][r.vars[1]]
        assert str(tt) == '<<( :bob :knows :carol )>>'

    def test_tt_components_correct(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who ?tt WHERE {
              ?who :says ?tt .
            }
        """)
        tt = r.bindings[0][r.vars[1]]
        assert tt.subject   == URIRef(EX + 'bob')
        assert tt.predicate == URIRef(EX + 'knows')
        assert tt.object    == URIRef(EX + 'carol')


# ---------------------------------------------------------------------------
# Q7 — SUBJECT / PREDICATE / OBJECT functions
# ---------------------------------------------------------------------------

class TestQ7:
    def test_subject_predicate_object_all_components(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who (SUBJECT(?tt) AS ?knower) (PREDICATE(?tt) AS ?rel) (OBJECT(?tt) AS ?known) WHERE {
              ?who :says ?tt .
            }
        """)
        assert len(r.bindings) == 1
        row = r.bindings[0]
        knower = row[r.vars[1]]
        rel    = row[r.vars[2]]
        known  = row[r.vars[3]]
        assert knower == URIRef(EX + 'bob')
        assert rel    == URIRef(EX + 'knows')
        assert known  == URIRef(EX + 'carol')

    def test_subject_only(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?who (SUBJECT(?tt) AS ?knower) WHERE {
              ?who :says ?tt .
            }
        """)
        assert r.bindings[0][r.vars[1]] == URIRef(EX + 'bob')


# ---------------------------------------------------------------------------
# Q8 — Annotation patterns
# ---------------------------------------------------------------------------

class TestQ8:
    def test_annotation_subject_all_annotations(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s ?p ?o ?pred ?val WHERE {
              << ?s ?p ?o >> ?pred ?val .
              FILTER(?pred != rdf:reifies)
            }
        """)
        pred_var, val_var = r.vars[3], r.vars[4]
        preds = {row[pred_var] for row in r.bindings}
        assert URIRef(EX + 'since')      in preds
        assert URIRef(EX + 'via')        in preds
        assert URIRef(EX + 'confidence') in preds
        assert URIRef(EX + 'source')     in preds

    def test_annotation_subject_base_triple_bound(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?s ?p ?o WHERE {
              << ?s ?p ?o >> ?pred ?val .
            }
        """)
        assert len(r.bindings) == 1
        row = r.bindings[0]
        assert row[r.vars[0]] == URIRef(EX + 'bob')
        assert row[r.vars[1]] == URIRef(EX + 'knows')
        assert row[r.vars[2]] == URIRef(EX + 'carol')

    def test_inline_annotation_block(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?since WHERE {
              :bob :knows :carol {| :since ?since |} .
            }
        """)
        assert len(r.bindings) == 1
        assert r.bindings[0][r.vars[0]] == Literal('2020')

    def test_tilde_reifier_binding(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?r ?pred ?val WHERE {
              :bob :knows :carol ~ ?r .
              ?r ?pred ?val .
              FILTER(?pred != rdf:reifies)
            }
        """)
        assert len(r.bindings) == 5  # 2 from stmt1 + 2 from {| |} + 1 from << >> reifier
        preds = {row[r.vars[1]] for row in r.bindings}
        assert URIRef(EX + 'since')       in preds
        assert URIRef(EX + 'via')         in preds
        assert URIRef(EX + 'confidence')  in preds
        assert URIRef(EX + 'source')      in preds
        assert URIRef(EX + 'verifiedBy')  in preds


# ---------------------------------------------------------------------------
# Q10 — Reifier and triple term as a unit
# ---------------------------------------------------------------------------

class TestQ10:
    def test_tt_in_object_position_restored(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?tt WHERE {
              ?stmt rdf:reifies ?tt .
            }
        """)
        tt_var = r.vars[1]
        tts = {row[tt_var] for row in r.bindings}
        assert len(tts) == 1
        tt = next(iter(tts))
        assert isinstance(tt, TripleTerm)
        assert tt == TripleTerm(URIRef(EX+'bob'), URIRef(EX+'knows'), URIRef(EX+'carol'))

    def test_two_reifiers_one_triple_term(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt ?tt WHERE {
              ?stmt rdf:reifies ?tt .
            }
        """)
        assert len(r.bindings) == 3  # stmt1 + anon from {| |} + anon from << >>


# ---------------------------------------------------------------------------
# Q11 — ASK with triple term
# ---------------------------------------------------------------------------

class TestQ11:
    def test_ask_true(self, g):
        # << >> (reification shorthand) in SPARQL matches via reifier of the triple
        r = g.query("""
            PREFIX :   <http://example.org/>
            ASK {
              << :bob :knows :carol >> :verifiedBy :ResearchTeam .
            }
        """)
        assert r.askAnswer is True

    def test_ask_false(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            ASK {
              << :bob :knows :carol >> :verifiedBy :nobody .
            }
        """)
        assert r.askAnswer is False


# ---------------------------------------------------------------------------
# Q12 — CONSTRUCT returns a StarLayerGraph
# ---------------------------------------------------------------------------

class TestQ12:
    def test_construct_returns_starlayergraph_graph(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT { ?stmt :hasConfidence ?conf . }
            WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              ?stmt :confidence ?conf .
            }
        """)
        assert isinstance(r.graph, StarLayerGraph)

    def test_construct_always_starlayergraph_graph_no_tt(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            CONSTRUCT { :a :b :c . }
            WHERE { :alice :says ?tt . }
        """)
        assert isinstance(r.graph, StarLayerGraph)

    def test_construct_plain_triple_content(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT { ?stmt :hasConfidence ?conf . }
            WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              ?stmt :confidence ?conf .
            }
        """)
        triples = list(r.graph.triples((None, URIRef(EX+'hasConfidence'), None)))
        assert len(triples) == 1
        s, _, o = triples[0]
        assert s == URIRef(EX + 'stmt1')
        assert o == Literal('0.9')


# ---------------------------------------------------------------------------
# Q13 — isTRIPLE and assertion check
# ---------------------------------------------------------------------------

class TestQ13:
    def test_is_triple_term_finds_tt(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT DISTINCT ?tt WHERE {
              { ?s ?p ?tt } UNION { ?tt ?p ?o }
              FILTER(isTRIPLE(?tt))
            }
        """)
        tts = [row[r.vars[0]] for row in r.bindings]
        assert len(tts) == 1
        assert isinstance(tts[0], TripleTerm)

    def test_bind_components_via_subject_predicate_object(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT DISTINCT ?tt ?s ?p ?o WHERE {
              { ?sub ?pred ?tt } UNION { ?tt ?pred ?obj }
              FILTER(isTRIPLE(?tt))
              BIND(SUBJECT(?tt) AS ?s)
              BIND(PREDICATE(?tt) AS ?p)
              BIND(OBJECT(?tt) AS ?o)
            }
        """)
        assert len(r.bindings) == 1
        row = r.bindings[0]
        assert isinstance(row[r.vars[0]], TripleTerm)
        assert row[r.vars[1]] == URIRef(EX + 'bob')
        assert row[r.vars[2]] == URIRef(EX + 'knows')
        assert row[r.vars[3]] == URIRef(EX + 'carol')

    def test_assertion_check_via_ask(self, g):
        # The base triple :bob :knows :carol is asserted (via {| |} annotation)
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT DISTINCT ?tt ?s ?p ?o WHERE {
              { ?sub ?pred ?tt } UNION { ?tt ?pred ?obj }
              FILTER(isTRIPLE(?tt))
              BIND(SUBJECT(?tt) AS ?s)
              BIND(PREDICATE(?tt) AS ?p)
              BIND(OBJECT(?tt) AS ?o)
              ?s ?p ?o .
            }
        """)
        assert len(r.bindings) == 1


# ---------------------------------------------------------------------------
# Q14 — CONSTRUCT with <<( )>> in template and WHERE clause
# ---------------------------------------------------------------------------

class TestQ14:
    def test_construct_triple_term_same_variable(self, g):
        # <<( ?s ?p ?o )>> in the CONSTRUCT template must get the same variable
        # as the same pattern in WHERE. Before the content-based variable fix,
        # the rewriter assigned different sequential variables to each block,
        # so the CONSTRUCT template's encoding triples were never bound and the
        # result graph contained no reification triples.
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT {
              ?s ?p ?o .
              ?stmt rdf:reifies <<( ?s ?p ?o )>> .
              ?stmt ?attr ?val .
            } WHERE {
              ?stmt rdf:reifies <<( ?s ?p ?o )>> .
              ?stmt ?attr ?val .
              FILTER(?attr != rdf:reifies)
            }
        """)
        assert isinstance(r.graph, StarLayerGraph)
        RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
        reifies_triples = list(r.graph.triples((None, RDF_REIFIES, None)))
        assert len(reifies_triples) >= 1, "CONSTRUCT result must contain rdf:reifies triple"
        _, _, obj = reifies_triples[0]
        assert isinstance(obj, TripleTerm), f"Object of rdf:reifies must be TripleTerm, got {type(obj)}"
        assert obj == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))

    def test_construct_triple_term_serializable(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              ?stmt ?attr ?val .
            } WHERE {
              ?stmt rdf:reifies <<( :bob :knows :carol )>> .
              ?stmt ?attr ?val .
              FILTER(?attr != rdf:reifies)
            }
        """)
        ttl = r.graph.serialize(format='turtle12')
        assert '<<(' in ttl or 'reifies' in ttl


# ---------------------------------------------------------------------------
# Q15 — Encoding-triple isolation: open-pattern SELECT must not leak internals
# ---------------------------------------------------------------------------

class TestQ15:
    """An unbound ?s ?p ?o scan must return exactly the visible triples.

    Encoding triples (tt:HASH rdf:subject/predicate/object ...) are an internal
    implementation detail of starlayergraph's triple-term storage.  They must never
    appear in SPARQL SELECT results, even when the query has no triple-term
    patterns of its own and would otherwise match every triple in the store.
    """

    def test_open_scan_row_count_matches_triples(self, g):
        visible = sum(1 for _ in g.triples((None, None, None)))
        r = g.query('SELECT * WHERE { ?s ?p ?o }')
        assert len(r.bindings) == visible, (
            f'SELECT * returned {len(r.bindings)} rows but triples() yields '
            f'{visible} — encoding triples are leaking into SPARQL results'
        )

    def test_open_scan_no_encoding_predicates(self, g):
        from rdflib.namespace import RDF as _RDF
        encoding_preds = {_RDF.subject, _RDF.predicate, _RDF.object}
        r = g.query('SELECT * WHERE { ?s ?p ?o }')
        p_var = r.vars[1]
        leaked = [row for row in r.bindings if row[p_var] in encoding_preds]
        assert leaked == [], (
            f'{len(leaked)} encoding triple(s) leaked into SPARQL results: {leaked}'
        )


# ---------------------------------------------------------------------------
# Q16 — initBindings with a TripleTerm value
# ---------------------------------------------------------------------------

class TestQ16:
    """A TripleTerm passed in ``initBindings`` must resolve against the store
    the same way every other read path (triples(), __contains__, ...) does —
    by first encoding it to its internal tt:HASH URIRef.
    """

    def test_registered_triple_term_binding_matches(self, g):
        tt = TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))
        r = g.query(
            'SELECT ?s WHERE { ?s :says ?tt }',
            initNs={'': EX},
            initBindings={'tt': tt},
        )
        assert _uris(r.bindings, r.vars[0]) == {URIRef(EX + 'alice')}

    def test_unregistered_triple_term_binding_yields_no_rows(self, g):
        tt = TripleTerm(URIRef(EX + 'nobody'), URIRef(EX + 'knows'), URIRef(EX + 'noone'))
        r = g.query(
            'SELECT ?s WHERE { ?s :says ?tt }',
            initNs={'': EX},
            initBindings={'tt': tt},
        )
        assert list(r.bindings) == []


# ---------------------------------------------------------------------------
# Q17 — CONSTRUCT minting a triple term from variables bound by WHERE patterns
# ---------------------------------------------------------------------------

class TestQ17:
    def test_construct_mints_triple_term_from_where_bound_variables(self):
        # The triple term minted in the template (<<( ?this :reach ?z )>>) uses
        # ?z, which is bound only by ordinary WHERE matching (transitive reach),
        # not a constant and not otherwise matched as a triple-term pattern. The
        # injected BIND must come after those WHERE patterns so ?z is already
        # bound when it evaluates - this is the same rule-construction shape a
        # SHACL-AF sh:construct rule uses to reify a freshly-derived fact.
        g = StarLayerGraph()
        g.parse(data="""
            @prefix : <http://example.org/> .
            :a :reach :b .
            :b :reach :c .
        """, format='turtle')

        r = g.query("""
            PREFIX : <http://example.org/>
            CONSTRUCT {
              ?this :reach ?z .
              ?this :witness <<( ?this :reach ?z )>> .
            }
            WHERE {
              ?this :reach ?y .
              ?y :reach ?z .
            }
        """)

        witnesses = list(r.graph.triples((None, URIRef(EX + 'witness'), None)))
        assert len(witnesses) == 1
        _, _, obj = witnesses[0]
        assert isinstance(obj, TripleTerm)
        assert obj == TripleTerm(URIRef(EX + 'a'), URIRef(EX + 'reach'), URIRef(EX + 'c'))


# ---------------------------------------------------------------------------
# Q18 — TRIPLE(s, p, o) constructor, end to end
# ---------------------------------------------------------------------------

class TestQ18:
    def test_triple_constructor_matches_literal_syntax_in_pattern_position(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
            }
        """)
        stmts = _uris(r.bindings, r.vars[0])
        assert URIRef(EX + 'stmt1') in stmts

    def test_triple_constructor_in_bind_matches_registered_term(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              BIND(TRIPLE(:bob, :knows, :carol) AS ?tt)
              ?stmt rdf:reifies ?tt .
            }
        """)
        stmts = _uris(r.bindings, r.vars[0])
        assert URIRef(EX + 'stmt1') in stmts

    def test_triple_constructor_mints_new_term_in_construct(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT {
              :newstmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
            }
            WHERE { }
        """)
        RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
        result = list(r.graph.triples((URIRef(EX + 'newstmt'), RDF_REIFIES, None)))
        assert len(result) == 1
        assert result[0][2] == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))


# ---------------------------------------------------------------------------
# Q19 — isTRIPLE()
#
# Previously also tested equivalence with isTripleTerm(), a starlayergraph-only,
# pre-spec-stabilization alias for the same function. That alias is not
# SPARQL syntax at all - only a name the legacy text-based rewriter special-
# cased before rdflib's real parser ever saw the query - and is gone now
# that queries go through starsparql's real, spec-based grammar
# instead. isTRIPLE() (the actual spec name, RDF 1.2 17.4.6) is unaffected
# and already covered by every other isTRIPLE test in this file.
# ---------------------------------------------------------------------------

class TestQ19:
    def test_is_triple(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT DISTINCT ?t WHERE {
              ?sub ?pred ?t .
              FILTER(isTRIPLE(?t))
            }
        """)
        got = {row[r.vars[0]] for row in r.bindings}
        assert got == {TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))}


# ---------------------------------------------------------------------------
# Q20 — TRIPLE()/isTRIPLE() used directly in a SELECT projection, no BIND
#
# Found broken via a live three-way comparison against Fuseki/Oxigraph
# 2026-07-16 (a ParseException, not a wrong answer - the component-matching
# patterns landed after the query's closing brace). Fixed same day.
# ---------------------------------------------------------------------------

class TestQ20:
    def test_triple_bare_in_select_projection(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT (TRIPLE(:bob, :knows, :carol) AS ?t) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(
            URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')
        )

    def test_is_triple_of_nested_triple_in_select_projection(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT (isTRIPLE(TRIPLE(:bob, :knows, :carol)) AS ?v) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == Literal(True)


# ---------------------------------------------------------------------------
# Q21 — A ground TRIPLE()/<<( )>> used as a value must behave like a literal
# IRI: always constructible, restorable to a proper TripleTerm, but with no
# side effect of writing/registering the triple term into the graph. Asking
# about a triple that doesn't exist must not cause it to exist - the same way
# asking about an IRI that isn't in the graph doesn't add it. Graph-pattern
# *matching* on a ground triple term (e.g. a reverse rdf:reifies lookup) must
# still require the term to actually be registered.
#
# Added 2026-07-16 per explicit design direction; see docs/future_enhancements.md.
# ---------------------------------------------------------------------------

class TestQ21:
    def test_ground_triple_constructed_on_empty_graph_has_no_side_effects(self):
        empty = StarLayerGraph()
        assert len(empty) == 0
        r = empty.query("""
            PREFIX :   <http://example.org/>
            SELECT (TRIPLE(:bob, :knows, :carol) AS ?t) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(
            URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')
        )
        # Constructing the value must not have written or registered anything.
        assert len(empty) == 0
        assert list(empty.triple_terms()) == []

    def test_ground_triple_pattern_matching_still_requires_registration(self):
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
            }
        """)
        assert r.bindings == []

        empty.add((URIRef(EX + 'stmt1'), URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies'),
                   TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))))
        r2 = empty.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
              ?stmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
            }
        """)
        assert _uris(r2.bindings, r2.vars[0]) == {URIRef(EX + 'stmt1')}

    def test_nested_ground_triple_restores_correctly_without_registration(self):
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            SELECT (TRIPLE(:alice, :believes, TRIPLE(:bob, :knows, :carol)) AS ?t) WHERE {}
        """)
        assert len(empty) == 0
        assert r.bindings[0][r.vars[0]] == TripleTerm(
            URIRef(EX + 'alice'), URIRef(EX + 'believes'),
            TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')),
        )

    def test_mixed_ground_and_variable_triple_term_is_unaffected(self, g):
        # A triple term with at least one variable component is a reverse
        # lookup/enumeration, not a value construction - it must keep the old
        # matching semantics (no match on an empty graph) rather than the new
        # ground-value BIND path. Uses the dataset's own << >> (no-parens,
        # reification-shorthand) encoding of :verifiedBy - see TestQ2.
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            SELECT ?s WHERE {
              << ?s :knows :carol >> :verifiedBy :ResearchTeam .
            }
        """)
        assert r.bindings == []

        r2 = g.query("""
            PREFIX :   <http://example.org/>
            SELECT ?s WHERE {
              << ?s :knows :carol >> :verifiedBy :ResearchTeam .
            }
        """)
        assert _uris(r2.bindings, r2.vars[0]) == {URIRef(EX + 'bob')}

    def test_is_triple_of_unregistered_ground_value(self):
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            SELECT (isTRIPLE(TRIPLE(:bob, :knows, :carol)) AS ?v) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == Literal(True)
        assert len(empty) == 0

    def test_construct_template_minting_unaffected_by_ground_value_path(self):
        # CONSTRUCT-template minting (a *new* triple term written by the
        # query) is a distinct code path from ground-value construction in a
        # SELECT/ASK/BIND context, and must keep working unchanged.
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            CONSTRUCT {
              :newstmt rdf:reifies TRIPLE(:bob, :knows, :carol) .
            }
            WHERE { }
        """)
        RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
        result = list(r.graph.triples((URIRef(EX + 'newstmt'), RDF_REIFIES, None)))
        assert len(result) == 1
        assert result[0][2] == TripleTerm(URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol'))


# ---------------------------------------------------------------------------
# Q22 — SUBJECT()/PREDICATE()/OBJECT() applied directly to a <<( )>>/TRIPLE()
# literal, not just a bound variable.
#
# Found missing via property-based fuzz testing 2026-07-17 - only the bare-
# variable form (SUBJECT(?tt)) was handled; SUBJECT(<<( :a :b :c )>>) raised
# a ParseException. Fixed same day.
# ---------------------------------------------------------------------------

class TestQ22:
    def test_subject_of_triple_term_literal(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT (SUBJECT(<<( :bob :knows :carol )>>) AS ?s) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == URIRef(EX + 'bob')

    def test_predicate_and_object_of_triple_constructor_literal(self, g):
        r = g.query("""
            PREFIX :   <http://example.org/>
            SELECT (PREDICATE(TRIPLE(:bob, :knows, :carol)) AS ?p)
                   (OBJECT(TRIPLE(:bob, :knows, :carol)) AS ?o) WHERE {}
        """)
        row = r.bindings[0]
        assert row[r.vars[0]] == URIRef(EX + 'knows')
        assert row[r.vars[1]] == URIRef(EX + 'carol')

    def test_object_of_nested_triple_term_literal_restores_correctly(self):
        # Nesting a triple term is legal only in *object* position (RDF 1.2
        # grammar: https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm) -
        # previously this used <<( <<(...)>> :p :o )>> (nested in *subject*
        # position), a shape that's syntactically parseable SPARQL but not
        # a legal RDF 1.2 term (see starsparql/triple_term.py's
        # InvalidTripleTermError docstring for the full investigation,
        # confirmed via a live Oxigraph rejecting exactly this shape).
        empty = StarLayerGraph()
        r = empty.query("""
            PREFIX :   <http://example.org/>
            SELECT (OBJECT(<<( :p :q <<( :bob :knows :carol )>> )>>) AS ?o) WHERE {}
        """)
        assert r.bindings[0][r.vars[0]] == TripleTerm(
            URIRef(EX + 'bob'), URIRef(EX + 'knows'), URIRef(EX + 'carol')
        )
        assert len(empty) == 0
