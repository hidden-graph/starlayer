"""
Unit tests for rdf:dirLangString (RDF 1.2 base-direction-tagged literals).

Covers the DirLangString value type, StarLayerGraph read/write interception,
Turtle/N-Triples/N-Quads/TriG/RDF-XML/TriX/JSON-LD 1.2 parser and serializer
round-trips, and the SPARQL 1.2 base-direction functions.
"""

import pytest
from rdflib import URIRef, Literal

from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.dirlangstring import DirLangString, encode_dirlangstring, decode_dirlangstring
from starlayergraph.model.encoding import DIRLANG_NS, encode_dirlang_datatype, decode_dirlang_datatype

EX = 'http://example.org/'


def ex(local):
    return URIRef(EX + local)


def round_trip(g, fmt):
    text = g.serialize(format=fmt)
    g2 = StarLayerGraph()
    g2.parse(data=text, format=fmt)
    return text, g2


# ---------------------------------------------------------------------------
# Model type
# ---------------------------------------------------------------------------

class TestDirLangStringType:
    def test_equality_and_hash(self):
        a = DirLangString('hello', 'en', 'ltr')
        b = DirLangString('hello', 'EN', 'ltr')  # case-insensitive language tag
        c = DirLangString('hello', 'en', 'rtl')
        assert a == b
        assert hash(a) == hash(b)
        assert a != c

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValueError, match="direction"):
            DirLangString('hello', 'en', 'sideways')

    def test_empty_language_rejected(self):
        with pytest.raises(ValueError, match="language"):
            DirLangString('hello', '', 'ltr')

    def test_immutable(self):
        d = DirLangString('hello', 'en', 'ltr')
        with pytest.raises(AttributeError):
            d.value = 'other'

    def test_n3(self):
        d = DirLangString('hello', 'en', 'ltr')
        assert d.n3() == '"hello"@en--ltr'

    def test_str(self):
        assert str(DirLangString('hello', 'en', 'ltr')) == 'hello'


class TestEncodeDecode:
    def test_round_trip_through_literal(self):
        d = DirLangString('hello', 'en', 'rtl')
        lit = encode_dirlangstring(d)
        assert isinstance(lit, Literal)
        assert str(lit) == 'hello'
        assert str(lit.datatype) == f'{DIRLANG_NS}en--rtl'
        assert decode_dirlangstring(lit) == d

    def test_decode_non_dirlang_literal_returns_none(self):
        assert decode_dirlangstring(Literal('hello', lang='en')) is None
        assert decode_dirlangstring(Literal('hello')) is None

    def test_datatype_helpers_round_trip(self):
        dt = encode_dirlang_datatype('en', 'ltr')
        assert decode_dirlang_datatype(dt) == ('en', 'ltr')

    def test_datatype_helper_rejects_foreign_namespace(self):
        assert decode_dirlang_datatype(URIRef('http://example.org/en--ltr')) is None


# ---------------------------------------------------------------------------
# StarLayerGraph read/write
# ---------------------------------------------------------------------------

class TestStarLayerGraphIntegration:
    def test_add_and_read_back(self):
        g = StarLayerGraph()
        d = DirLangString('Hello', 'en', 'ltr')
        g.add((ex('a'), ex('greets'), d))
        results = list(g.triples((ex('a'), ex('greets'), None)))
        assert results == [(ex('a'), ex('greets'), d)]

    def test_contains(self):
        g = StarLayerGraph()
        d = DirLangString('Hello', 'en', 'ltr')
        g.add((ex('a'), ex('greets'), d))
        assert (ex('a'), ex('greets'), d) in g
        assert (ex('a'), ex('greets'), DirLangString('Hello', 'en', 'rtl')) not in g

    def test_len_counts_it_once(self):
        g = StarLayerGraph()
        g.add((ex('a'), ex('greets'), DirLangString('Hello', 'en', 'ltr')))
        assert len(g) == 1

    def test_remove(self):
        g = StarLayerGraph()
        d = DirLangString('Hello', 'en', 'ltr')
        g.add((ex('a'), ex('greets'), d))
        g.remove((ex('a'), ex('greets'), d))
        assert len(g) == 0

    def test_subject_position_rejected(self):
        g = StarLayerGraph()
        d = DirLangString('Hello', 'en', 'ltr')
        with pytest.raises(ValueError, match="subject position"):
            g.add((d, ex('p'), ex('o')))

    def test_triples_choices(self):
        g = StarLayerGraph()
        d1 = DirLangString('Hello', 'en', 'ltr')
        d2 = DirLangString('Bonjour', 'fr', 'ltr')
        g.add((ex('a'), ex('greets'), d1))
        g.add((ex('b'), ex('greets'), d2))
        results = list(g.triples_choices((None, ex('greets'), [d1, d2])))
        assert {r[2] for r in results} == {d1, d2}

    def test_nested_in_triple_term_object(self):
        d = DirLangString('Hello', 'en', 'ltr')
        g = StarLayerGraph()
        g.add((ex('alice'), ex('says'), (ex('bob'), ex('greets'), d)))
        results = list(g.triples((ex('alice'), ex('says'), None)))
        assert len(results) == 1
        outer = results[0][2]
        assert outer.object == d

    def test_init_bindings_matches_registered_value(self):
        g = StarLayerGraph()
        d = DirLangString('Hello', 'en', 'ltr')
        g.add((ex('a'), ex('greets'), d))
        r = g.query(
            'SELECT ?s WHERE { ?s <http://example.org/greets> ?t }',
            initBindings={'t': d},
        )
        assert {row[r.vars[0]] for row in r.bindings} == {ex('a')}


# ---------------------------------------------------------------------------
# Turtle 1.2
# ---------------------------------------------------------------------------

class TestTurtle12:
    def test_parse_ltr(self):
        g = StarLayerGraph()
        g.parse(data=f'<{EX}s> <{EX}p> "hello"@en--ltr .', format='turtle12')
        results = list(g.triples((None, None, None)))
        assert results == [(ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr'))]

    def test_parse_rtl_non_ascii(self):
        g = StarLayerGraph()
        g.parse(data=f'<{EX}s> <{EX}p> "HTML היא שפת סימון"@he--rtl .', format='turtle12')
        obj = next(g.objects(ex('s'), ex('p')))
        assert obj == DirLangString('HTML היא שפת סימון', 'he', 'rtl')

    def test_invalid_direction_raises(self):
        g = StarLayerGraph()
        with pytest.raises(ValueError, match="ltr.*rtl"):
            g.parse(data=f'<{EX}s> <{EX}p> "hello"@en--sideways .', format='turtle12')

    def test_round_trip_turtle12(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, 'turtle12')
        assert '"hello"@en--ltr' in text
        assert '@version "1.2" .' in text
        assert list(g2.triples((None, None, None))) == list(g.triples((None, None, None)))

    def test_round_trip_longturtle12(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, 'longturtle12')
        assert '"hello"@en--ltr' in text
        assert list(g2.triples((None, None, None))) == list(g.triples((None, None, None)))

    def test_version_directive_emitted_even_without_triple_terms(self):
        # A graph with only a DirLangString (no TripleTerm at all) must still
        # get the @version "1.2" directive - it's new RDF 1.2 syntax too.
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text = g.serialize(format='turtle12')
        assert '@version "1.2" .' in text


# ---------------------------------------------------------------------------
# N-Triples 1.2 / N-Quads 1.2
# ---------------------------------------------------------------------------

class TestNTriples12:
    def test_parse(self):
        nt = f'<{EX}s> <{EX}p> "hello"@en--ltr .\n'
        g = StarLayerGraph()
        g.parse(data=nt, format='nt12')
        assert list(g.triples((None, None, None))) == [(ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr'))]

    def test_round_trip_nt12(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, 'nt12')
        assert '"hello"@en--ltr' in text
        assert 'VERSION "1.2"' in text
        assert list(g2.triples((None, None, None))) == list(g.triples((None, None, None)))

    def test_round_trip_nq12(self):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, 'nq12')
        assert '"hello"@en--ltr' in text
        assert list(g2.triples((None, None, None))) == list(g.triples((None, None, None)))


# ---------------------------------------------------------------------------
# TriG 1.2 (via StarLayerDataset)
# ---------------------------------------------------------------------------

class TestTrig12:
    def test_round_trip(self):
        from starlayergraph.graph.starlayer_dataset import StarLayerDataset

        ds = StarLayerDataset()
        ds.parse(data=f'''
            @prefix : <{EX}> .
            GRAPH :g1 {{ :s :p "hello"@en--ltr . }}
        ''', format='trig12')
        text = ds.serialize(format='trig12')
        assert '"hello"@en--ltr' in text

        ds2 = StarLayerDataset()
        ds2.parse(data=text, format='trig12')
        quads = list(ds2.quads((None, None, None)))
        assert any(o == DirLangString('hello', 'en', 'ltr') for _, _, o, _ in quads)


# ---------------------------------------------------------------------------
# RDF/XML 1.2, TriX 1.2, JSON-LD 1.2
# ---------------------------------------------------------------------------

class TestOtherFormats:
    @pytest.mark.parametrize('fmt', ['rdfxml12', 'trix12', 'jsonld12'])
    def test_round_trip(self, fmt):
        g = StarLayerGraph()
        g.add((ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr')))
        text, g2 = round_trip(g, fmt)
        assert list(g2.triples((None, None, None))) == [(ex('s'), ex('p'), DirLangString('hello', 'en', 'ltr'))]


# ---------------------------------------------------------------------------
# SPARQL 1.2 base-direction functions
# ---------------------------------------------------------------------------

class TestSparqlFunctions:
    @pytest.fixture
    def g(self):
        g = StarLayerGraph()
        g.add((ex('dir'),   ex('title'), DirLangString('HTML page', 'en', 'ltr')))
        g.add((ex('lang'),  ex('title'), Literal('plain lang', lang='en')))
        g.add((ex('plain'), ex('title'), Literal('no lang at all')))
        return g

    def _query(self, g, expr):
        r = g.query(f'SELECT ?s ({expr} AS ?v) WHERE {{ ?s <{EX}title> ?t }}')
        return {row[r.vars[0]]: row[r.vars[1]] for row in r.bindings}

    def test_langdir(self, g):
        result = self._query(g, 'LANGDIR(?t)')
        assert result[ex('dir')] == Literal('ltr')
        assert result[ex('lang')] == Literal('')
        assert result[ex('plain')] == Literal('')

    def test_has_langdir(self, g):
        result = self._query(g, 'hasLANGDIR(?t)')
        assert result[ex('dir')] == Literal(True)
        assert result[ex('lang')] == Literal(False)
        assert result[ex('plain')] == Literal(False)

    def test_lang_upgraded_for_dirlangstring(self, g):
        result = self._query(g, 'LANG(?t)')
        assert result[ex('dir')] == Literal('en')
        assert result[ex('lang')] == Literal('en')
        assert result[ex('plain')] == Literal('')

    def test_has_lang(self, g):
        result = self._query(g, 'hasLANG(?t)')
        assert result[ex('dir')] == Literal(True)
        assert result[ex('lang')] == Literal(True)
        assert result[ex('plain')] == Literal(False)

    def test_strlangdir_constructs_matching_value(self, g):
        r = g.query(f'''
            SELECT ?s WHERE {{
              ?s <{EX}title> ?t .
              FILTER(?t = STRLANGDIR("HTML page", "en", "ltr"))
            }}
        ''')
        assert {row[r.vars[0]] for row in r.bindings} == {ex('dir')}

    def test_strlangdir_result_restored_to_dirlangstring(self, g):
        r = g.query('SELECT (STRLANGDIR("hi", "EN", "LTR") AS ?x) WHERE {}')
        assert r.bindings[0][r.vars[0]] == DirLangString('hi', 'en', 'ltr')

    def test_strlangdir_wrong_arity_raises(self, g):
        # starsparql's grammar production for STRLANGDIR requires
        # exactly 3 comma-separated arguments structurally (grammar12.py's
        # _StrLangDirArgs) - a 2-arg call is simply not valid SPARQL 1.2
        # syntax by this grammar's own rules, so it's rejected at parse
        # time (pyparsing.ParseException), not accepted and validated
        # afterward with a custom error message the way the legacy
        # text-based rewriter used to.
        from pyparsing.exceptions import ParseException
        with pytest.raises(ParseException):
            g.query('SELECT (STRLANGDIR("hi", "en") AS ?x) WHERE {}')

    def test_is_triple_alias_unaffected_by_lang_rewrite(self, g):
        # Sanity check that the LANG-family rewrite doesn't interfere with
        # unrelated existing rewrite passes sharing this module.
        r = g.query(f'''
            SELECT ?s WHERE {{
              ?s <{EX}title> ?t .
              FILTER(!isTRIPLE(?t) && LANG(?t) != "fr")
            }}
        ''')
        assert {row[r.vars[0]] for row in r.bindings} == {ex('dir'), ex('lang'), ex('plain')}

    # -- nested/arbitrary-expression arguments (previously a known limitation) --

    def test_langdir_of_strlangdir_nested(self, g):
        r = g.query('SELECT (LANGDIR(STRLANGDIR("x", "en", "rtl")) AS ?d) WHERE {}')
        assert r.bindings[0][r.vars[0]] == Literal('rtl')

    def test_has_langdir_of_arbitrary_expression(self, g):
        r = g.query('''
            SELECT (hasLANGDIR(IF(true, STRLANGDIR("x", "en", "ltr"), "y")) AS ?h) WHERE {}
        ''')
        assert r.bindings[0][r.vars[0]] == Literal(True)

    def test_lang_of_strlangdir_nested(self, g):
        r = g.query('SELECT (LANG(STRLANGDIR("x", "en", "ltr")) AS ?l) WHERE {}')
        assert r.bindings[0][r.vars[0]] == Literal('en')

    def test_has_lang_of_strlangdir_nested(self, g):
        r = g.query('SELECT (hasLANG(STRLANGDIR("x", "en", "ltr")) AS ?h) WHERE {}')
        assert r.bindings[0][r.vars[0]] == Literal(True)

    def test_strlangdir_with_nested_strlangdir_argument(self, g):
        # Pathological but exercises full recursion: the "lex" argument is
        # itself an expression that must be rewritten before being spliced
        # into the outer STRLANGDIR's constructor-function call.
        r = g.query('''
            SELECT (STRLANGDIR(STR(STRLANGDIR("x", "en", "ltr")), "fr", "rtl") AS ?v) WHERE {}
        ''')
        assert r.bindings[0][r.vars[0]] == DirLangString('x', 'fr', 'rtl')

    # -- invalid STRLANGDIR direction: soft-failure semantics matching native
    # engines (confirmed against live Fuseki 5.5.0 and Oxigraph 0.5.9
    # 2026-07-16: an invalid direction leaves that one variable unbound
    # rather than aborting the query or dropping the row) --

    def test_strlangdir_invalid_direction_leaves_variable_unbound(self, g):
        r = g.query('SELECT (STRLANGDIR("x", "en", "sideways") AS ?v) WHERE {}')
        assert len(r.bindings) == 1
        assert r.bindings[0][r.vars[0]] is None

    def test_strlangdir_invalid_direction_does_not_abort_other_rows(self, g):
        # The defining case for soft-failure semantics: one bad row must not
        # take down the rows around it.
        r = g.query('''
            SELECT ?label (STRLANGDIR("x", "en", ?dir) AS ?v) WHERE {
              VALUES (?label ?dir) {
                ("good-ltr" "ltr")
                ("bad-direction" "sideways")
                ("good-rtl" "rtl")
              }
            }
        ''')
        by_label = {row[r.vars[0]]: row[r.vars[1]] for row in r.bindings}
        assert len(by_label) == 3
        assert by_label[Literal('good-ltr')] == DirLangString('x', 'en', 'ltr')
        assert by_label[Literal('bad-direction')] is None
        assert by_label[Literal('good-rtl')] == DirLangString('x', 'en', 'rtl')

    # -- literal "text"@lang--dir written directly in a query (not a bound
    # variable from stored data) - found broken via a live three-way
    # comparison against Fuseki/Oxigraph 2026-07-16, fixed same day --

    def test_langdir_of_literal_written_directly_in_query(self, g):
        r = g.query('SELECT (LANGDIR("hi"@en--rtl) AS ?dir) WHERE {}')
        assert r.bindings[0][r.vars[0]] == Literal('rtl')

    def test_all_dirlang_functions_accept_literal_directly_in_query(self, g):
        r = g.query("""
            SELECT (LANGDIR("hi"@en--rtl) AS ?dir)
                   (hasLANGDIR("hi"@en--rtl) AS ?hd)
                   (LANG("hi"@en--rtl) AS ?l)
                   (hasLANG("hi"@en--rtl) AS ?hl)
            WHERE {}
        """)
        row = r.bindings[0]
        assert row[r.vars[0]] == Literal('rtl')
        assert row[r.vars[1]] == Literal(True)
        assert row[r.vars[2]] == Literal('en')
        assert row[r.vars[3]] == Literal(True)


# ---------------------------------------------------------------------------
# Native backend (rdf-1.2) term serialization + JSON parsing
# ---------------------------------------------------------------------------

class TestNativeBackend:
    def test_sparql_term_emits_real_lexical_form(self):
        from starlayergraph.backends.native import sparql_term
        d = DirLangString('hello', 'en', 'rtl')
        assert sparql_term(d) == '"hello"@en--rtl'

    def test_sparql_term_escapes_quotes(self):
        from starlayergraph.backends.native import sparql_term
        d = DirLangString('say "hi"', 'en', 'ltr')
        assert sparql_term(d) == '"say \\"hi\\""@en--ltr'

    def test_parse_json_term_with_its_dir_key(self):
        # "its:dir" confirmed 2026-07-16 against live Fuseki 5.5.0 and
        # Oxigraph 0.5.9 (both agree independently).
        from starlayergraph.backends.native import _parse_json_term
        term = _parse_json_term({'type': 'literal', 'value': 'hello', 'xml:lang': 'en', 'its:dir': 'rtl'})
        assert term == DirLangString('hello', 'en', 'rtl')

    def test_parse_json_term_without_direction_key_is_plain_lang_literal(self):
        from starlayergraph.backends.native import _parse_json_term
        term = _parse_json_term({'type': 'literal', 'value': 'hello', 'xml:lang': 'en'})
        assert term == Literal('hello', lang='en')
        assert not isinstance(term, DirLangString)
