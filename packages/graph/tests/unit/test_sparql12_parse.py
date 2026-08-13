"""
Tests for starlayergraph.query.parseQuery, prepareQuery, parseUpdate, prepareUpdate.

These wrappers accept SPARQL 1.2 syntax; the round-trip strategy is:
  1. Rewrite to SPARQL 1.1 (text level)
  2. Parse with rdflib's parser
  3. Post-process: remove encoding triples and replace ?__ttN with TripleTerm nodes
"""

import pytest
from rdflib import URIRef, Variable
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import Query

from starlayergraph.query import parseQuery, prepareQuery, parseUpdate, prepareUpdate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first_triples_block(result):
    """Return the first TriplesBlock CompValue inside a parsed SELECT query."""
    where = result[1]['where']
    for part in where['part']:
        if isinstance(part, CompValue) and part.name == 'TriplesBlock':
            return part
    return None


def _is_triple_term(node):
    return isinstance(node, CompValue) and node.name == 'TripleTerm'


# ---------------------------------------------------------------------------
# parseQuery — triple terms preserved in parse tree
# ---------------------------------------------------------------------------

class TestParseQueryTripleTermSubject:
    Q = """
        PREFIX : <http://example.org/>
        SELECT ?pred ?val WHERE {
          <<( :bob :knows :carol )>> ?pred ?val .
        }
    """

    def test_does_not_raise(self):
        parseQuery(self.Q)

    def test_encoding_triples_removed(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        assert tb is not None
        assert len(tb['triples']) == 1, "Encoding triples must be stripped"

    def test_subject_is_triple_term_node(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        s = tb['triples'][0][0]
        assert _is_triple_term(s)

    def test_triple_term_components_preserved(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        tt = tb['triples'][0][0]
        # Components are pname_ CompValues from the parser (not resolved IRIs)
        assert tt['subject']['localname']   == 'bob'
        assert tt['predicate']['localname'] == 'knows'
        assert tt['object']['localname']    == 'carol'


class TestParseQueryTripleTermObject:
    Q = """
        PREFIX : <http://example.org/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt WHERE {
          ?stmt rdf:reifies <<( :bob :knows :carol )>> .
        }
    """

    def test_does_not_raise(self):
        parseQuery(self.Q)

    def test_encoding_triples_removed(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        assert len(tb['triples']) == 1

    def test_object_is_triple_term_node(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        o = tb['triples'][0][2]
        assert _is_triple_term(o)

    def test_triple_term_components_preserved(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        tt = tb['triples'][0][2]
        assert tt['subject']['localname']   == 'bob'
        assert tt['predicate']['localname'] == 'knows'
        assert tt['object']['localname']    == 'carol'


class TestParseQueryNestedTripleTermInSubjectPosition:
    """A triple term nested in *subject* position - <<( <<(...)>> :p :o )>>
    - is syntactically parseable SPARQL (the W3C suite even labels this
    shape a PositiveSyntaxTest: compound-tripleterm-subject/
    nested-tripleterm-02) but not a legal RDF 1.2 term: per the grammar
    (https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm),
    nesting a triple term is legal only in *object* position. Confirmed via
    a live Oxigraph instance rejecting exactly this shape (HTTP 500) - see
    starsparql/triple_term.py's own InvalidTripleTermError docstring
    for the full investigation. Rejecting it here (construction time, not
    just at the grammar level) is the correct, spec-compliant behavior;
    this class previously asserted the opposite (silent acceptance), which
    was itself the bug.
    """

    Q = """
        PREFIX : <http://example.org/>
        SELECT ?x WHERE {
          <<( <<( :a :b :c )>> :p :o )>> :pred ?x .
        }
    """

    def test_raises_invalid_triple_term_error(self):
        from starsparql.triple_term import InvalidTripleTermError
        with pytest.raises(InvalidTripleTermError):
            parseQuery(self.Q)


class TestParseQueryNestedTripleTermInObjectPosition:
    """The legal nesting shape - a triple term inside another's *object*
    position - still parses and preserves structure correctly."""

    Q = """
        PREFIX : <http://example.org/>
        SELECT ?x WHERE {
          <<( :pred :p <<( :a :b :c )>> )>> ?x :val .
        }
    """

    def test_does_not_raise(self):
        parseQuery(self.Q)

    def test_outer_object_is_triple_term(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        outer = tb['triples'][0][0]
        assert _is_triple_term(outer)

    def test_inner_triple_term_preserved(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        outer = tb['triples'][0][0]
        inner = outer['object']
        assert _is_triple_term(inner)
        assert inner['subject']['localname']   == 'a'
        assert inner['predicate']['localname'] == 'b'
        assert inner['object']['localname']    == 'c'


class TestParseQueryOptionalBlock:
    Q = """
        PREFIX : <http://example.org/>
        SELECT ?pred ?val WHERE {
          OPTIONAL { <<( :bob :knows :carol )>> ?pred ?val . }
        }
    """

    def test_does_not_raise(self):
        parseQuery(self.Q)

    def test_triple_term_inside_optional(self):
        result = parseQuery(self.Q)
        where = result[1]['where']
        optional = where['part'][0]
        assert optional.name == 'OptionalGraphPattern'
        inner_where = optional['graph']
        inner_tb = inner_where['part'][0]
        assert inner_tb.name == 'TriplesBlock'
        assert len(inner_tb['triples']) == 1
        s = inner_tb['triples'][0][0]
        assert _is_triple_term(s)


class TestParseQueryPlainSparql11:
    """Plain SPARQL 1.1 queries must parse identically via the wrapper."""

    Q = "SELECT ?s ?p ?o WHERE { ?s ?p ?o . }"

    def test_does_not_raise(self):
        parseQuery(self.Q)

    def test_returns_parse_results(self):
        from pyparsing import ParseResults
        result = parseQuery(self.Q)
        assert isinstance(result, ParseResults)

    def test_triple_count_unchanged(self):
        result = parseQuery(self.Q)
        tb = _first_triples_block(result)
        assert len(tb['triples']) == 1


# ---------------------------------------------------------------------------
# prepareQuery — returns rdflib Query, accepts SPARQL 1.2 input
# ---------------------------------------------------------------------------

class TestPrepareQuery:
    def test_returns_query_object_for_plain_sparql(self):
        q = prepareQuery("SELECT ?s WHERE { ?s ?p ?o . }")
        assert isinstance(q, Query)

    def test_does_not_raise_on_sparql12_input(self):
        prepareQuery("""
            PREFIX : <http://example.org/>
            SELECT ?pred ?val WHERE {
              <<( :bob :knows :carol )>> ?pred ?val .
            }
        """)

    def test_returns_query_object_for_sparql12_input(self):
        q = prepareQuery("""
            PREFIX : <http://example.org/>
            SELECT ?stmt WHERE {
              ?stmt <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies>
                <<( :bob :knows :carol )>> .
            }
        """)
        assert isinstance(q, Query)

    def test_prepared_query_executes_on_graph(self):
        from rdflib import Graph, URIRef, Literal
        from rdflib.plugins.sparql.sparql import Query
        g = Graph()
        g.parse(data="""
            @prefix : <http://example.org/> .
            :a :b :c .
        """, format="turtle")
        q = prepareQuery("PREFIX : <http://example.org/> SELECT ?s WHERE { ?s :b :c . }")
        r = g.query(q)
        subjects = {row[r.vars[0]] for row in r.bindings}
        assert URIRef("http://example.org/a") in subjects


# ---------------------------------------------------------------------------
# parseUpdate — triple terms preserved in parse tree
# ---------------------------------------------------------------------------

class TestParseUpdate:
    def test_does_not_raise_on_sparql11(self):
        parseUpdate("INSERT DATA { <http://a> <http://b> <http://c> }")

    def test_does_not_raise_on_sparql12(self):
        parseUpdate("""
            DELETE WHERE {
              <<( ?s ?p ?o )>> <http://example.org/pred> ?val .
            }
        """)

    def test_returns_comp_value(self):
        result = parseUpdate("INSERT DATA { <http://a> <http://b> <http://c> }")
        assert isinstance(result, CompValue)

    def test_sparql12_returns_comp_value(self):
        result = parseUpdate("""
            DELETE WHERE {
              <<( ?s ?p ?o )>> <http://example.org/pred> ?val .
            }
        """)
        assert isinstance(result, CompValue)


# ---------------------------------------------------------------------------
# prepareUpdate — returns rdflib Update, accepts SPARQL 1.2 input
# ---------------------------------------------------------------------------

class TestPrepareUpdate:
    def test_does_not_raise_on_sparql11(self):
        from rdflib.plugins.sparql.sparql import Update
        u = prepareUpdate("INSERT DATA { <http://a> <http://b> <http://c> }")
        assert isinstance(u, Update)

    def test_does_not_raise_on_sparql12(self):
        prepareUpdate("""
            PREFIX : <http://example.org/>
            DELETE WHERE {
              <<( ?s ?p ?o )>> :pred ?val .
            }
        """)

    def test_prepared_update_executes_on_graph(self):
        from rdflib import Graph, URIRef
        g = Graph()
        g.parse(data="<http://a> <http://b> <http://c> .", format="nt")
        u = prepareUpdate("DELETE DATA { <http://a> <http://b> <http://c> }")
        g.update(u)
        assert len(g) == 0


# ---------------------------------------------------------------------------
# processUpdate — module-level wrapper, accepts SPARQL 1.2 input
# ---------------------------------------------------------------------------

class TestProcessUpdate:
    def test_does_not_raise_on_sparql11_plain_graph(self):
        from rdflib import Graph
        from starlayergraph.query import processUpdate
        g = Graph()
        processUpdate(g, "INSERT DATA { <http://a> <http://b> <http://c> }")
        assert len(g) == 1

    def test_does_not_raise_on_sparql12_starlayergraph_graph(self):
        from starlayergraph.query import processUpdate
        from starlayergraph.graph import StarLayerGraph
        g = StarLayerGraph()
        g.parse(data="<http://example.org/s> <http://example.org/p> <http://example.org/o> .", format="nt")
        # SPARQL 1.2 with triple-term should not raise
        processUpdate(g, """
            PREFIX : <http://example.org/>
            DELETE WHERE { :s :p :o . }
        """)
        assert len(g) == 0

    def test_routes_to_graph_update_for_starlayergraph_graph(self):
        """processUpdate on a StarLayerGraph must go through graph.update()
        so the TripleTerm registry is rebuilt after the update."""
        from starlayergraph.query import processUpdate
        from starlayergraph.graph import StarLayerGraph
        from rdflib import URIRef
        g = StarLayerGraph()
        g.parse(data="""
            @prefix : <http://example.org/> .
            :stmt rdf:reifies <<( :a :b :c )>> .
        """, format="turtle12")
        assert len(g) > 0
        processUpdate(g, "DELETE WHERE { ?s ?p ?o }")
        assert len(g) == 0
