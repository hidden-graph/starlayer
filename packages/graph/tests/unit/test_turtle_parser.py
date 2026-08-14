"""
Unit tests for starlayergraph.parsers.turtle_parser.

Tests cover plain Turtle 1.1 parsing (compared against rdflib) and
RDF 1.2 features (triple terms, reification, annotations).
"""

import pytest
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import RDF, XSD

from starlayergraph.parsers.turtle_parser import StarLayerTurtleParser, SL_NS
from starlayergraph.parsers.errors import TurtleSyntaxError

EX = 'http://example.org/'
SL_TRIPLE_TERM  = URIRef(SL_NS + 'TripleTerm')
SL_REIFICATION  = URIRef(SL_NS + 'Reification')
RDF_REIFIES     = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


# ---------------------------------------------------------------------------
# Plain Turtle 1.1 — must match rdflib's native parser
# ---------------------------------------------------------------------------

class TestPlainTurtle:
    def test_simple_iri_triple(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('simple.ttl'))
        assert (URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob')) in g

    def test_string_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('simple.ttl'))
        assert (URIRef(EX+'bob'), URIRef(EX+'name'), Literal('Bob')) in g

    def test_integer_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('simple.ttl'))
        assert (URIRef(EX+'alice'), URIRef(EX+'age'), Literal(30, datatype=XSD.integer)) in g

    def test_boolean_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('simple.ttl'))
        assert (URIRef(EX+'bob'), URIRef(EX+'active'), Literal(True, datatype=XSD.boolean)) in g

    def test_float_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('literals.ttl'))
        assert (URIRef(EX+'s'), URIRef(EX+'float'), Literal(3.14, datatype=XSD.decimal)) in g

    def test_typed_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('literals.ttl'))
        date_node = Literal('2024-01-01', datatype=URIRef('http://www.w3.org/2001/XMLSchema#date'))
        assert (URIRef(EX+'s'), URIRef(EX+'typed'), date_node) in g

    def test_lang_literal(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('literals.ttl'))
        assert (URIRef(EX+'s'), URIRef(EX+'lang'), Literal('bonjour', lang='fr')) in g

    def test_typed_literal_preserves_non_canonical_lexical_form(self, parser):
        """"04"^^xsd:integer must stay "04", not be silently rewritten to
        the canonical "4" - RDF 1.2's own literal term-equality definition
        (https://www.w3.org/TR/rdf12-concepts/#dfn-literal-term-equality)
        requires the lexical form to match, not just the value, so a parser
        that normalizes on construction makes two genuinely different terms
        indistinguishable."""
        g = parser.parse(
            '@prefix ex: <http://example.org/> .\n'
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n'
            'ex:s ex:p "04"^^xsd:integer .\n'
        )
        value = next(iter(g.objects(URIRef(EX + 's'), URIRef(EX + 'p'))))
        assert str(value) == '04'
        assert value != Literal('4', datatype=XSD.integer)

    def test_form_feed_and_backspace_escapes_decode(self, parser):
        """\\f (form feed, U+000C) and \\b (backspace, U+0008) are both valid
        Turtle ECHAR escapes (grammar: '\\' [tbnrf"'\\]) - _unescape() only
        handled t/n/r plus the quote/backslash escapes, silently leaving
        \\f/\\b as a literal backslash followed by the letter instead of the
        control character. Found via the W3C SHACL 1.2 test suite
        (core/property/singleLine-001.ttl, which uses \\f in a literal) -
        \\n/\\r/\\uXXXX all decoded correctly there, isolating the gap to
        exactly these two escapes."""
        g = parser.parse(
            '@prefix ex: <http://example.org/> .\n'
            'ex:s ex:p "a\\fb" .\n'
            'ex:s ex:q "a\\bb" .\n'
        )
        p_value = next(iter(g.objects(URIRef(EX + 's'), URIRef(EX + 'p'))))
        q_value = next(iter(g.objects(URIRef(EX + 's'), URIRef(EX + 'q'))))
        assert str(p_value) == 'a\fb'
        assert str(q_value) == 'a\bb'

    def test_rdf_type_abbreviation(self, parser):
        g = parser.parse('@prefix ex: <http://example.org/> .\nex:s a ex:Thing .\n')
        assert (URIRef(EX+'s'), RDF.type, URIRef(EX+'Thing')) in g

    def test_multiple_predicates_semicolon(self, parser):
        g = parser.parse('@prefix ex: <http://example.org/> .\nex:s ex:p ex:o ; ex:q ex:z .\n')
        assert len(list(g.triples((URIRef(EX+'s'), None, None)))) == 2

    def test_multiple_objects_comma(self, parser):
        g = parser.parse('@prefix ex: <http://example.org/> .\nex:s ex:p ex:o , ex:o2 .\n')
        assert len(list(g.triples((URIRef(EX+'s'), URIRef(EX+'p'), None)))) == 2

    def test_matches_rdflib_for_simple_file(self, parser, fixture_ttl):
        data = fixture_ttl('simple.ttl')
        g_ours = parser.parse(data)
        g_rdflib = Graph()
        g_rdflib.parse(data=data, format='turtle')
        for triple in g_rdflib:
            assert triple in g_ours, f"Triple missing from starlayergraph output: {triple}"


class TestBlankNodes:
    def test_blank_node_object(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('blank_nodes.ttl'))
        addrs = list(g.objects(URIRef(EX+'alice'), URIRef(EX+'address')))
        assert len(addrs) == 1
        assert isinstance(addrs[0], BNode)

    def test_blank_node_inner_triple(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('blank_nodes.ttl'))
        addrs = list(g.objects(URIRef(EX+'alice'), URIRef(EX+'address')))
        bnode = addrs[0]
        cities = list(g.objects(bnode, URIRef(EX+'city')))
        assert cities == [Literal('Springfield')]

    def test_collection_head_is_bnode(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('blank_nodes.ttl'))
        items = list(g.objects(URIRef(EX+'doc'), URIRef(EX+'items')))
        assert len(items) == 1
        assert isinstance(items[0], BNode)

    def test_collection_has_rdf_first(self, parser, fixture_ttl):
        g = parser.parse(fixture_ttl('blank_nodes.ttl'))
        items_head = list(g.objects(URIRef(EX+'doc'), URIRef(EX+'items')))[0]
        firsts = list(g.objects(items_head, RDF.first))
        assert firsts == [URIRef(EX+'a')]


class TestBracketedSubject:
    """A non-empty bracketed property list (Turtle's blankNodePropertyList
    production) used as a statement's own subject - `[ :p :o ] .` or
    `[ :p :o ] :b :c .` - not just nested as an object (already covered by
    TestBlankNodes above). Previously silently produced zero triples with
    no error at all: extract_fields() (starlayergraph/parsers/syntax.py) only
    special-cased the empty-bracket case (`[]`) for a subject-position
    blank node, never a non-empty one - unlike object position, which
    expand_triple_set() already handled correctly. Found via a live Fuseki
    CONSTRUCT response using exactly this shape (Fuseki serializes its
    anonymous blank node with bracket syntax; Oxigraph uses a labeled
    `_:id`, which is why this only ever surfaced through Fuseki testing)."""

    def test_bare_bracket_single_predicate(self, parser):
        g = parser.parse('PREFIX : <http://example.org/>\n[ :q :z ] .\n')
        assert len(g) == 1
        s, p, o = next(iter(g))
        assert isinstance(s, BNode)
        assert (p, o) == (URIRef(EX+'q'), URIRef(EX+'z'))

    def test_bare_bracket_multiple_predicates(self, parser):
        g = parser.parse('PREFIX : <http://example.org/>\n[ :q :z ; :p :o ] .\n')
        assert len(g) == 2
        subjects = {s for s, _, _ in g}
        assert len(subjects) == 1
        bnode = next(iter(subjects))
        assert isinstance(bnode, BNode)
        assert set(g.predicate_objects(bnode)) == {
            (URIRef(EX+'q'), URIRef(EX+'z')),
            (URIRef(EX+'p'), URIRef(EX+'o')),
        }

    def test_bracket_with_trailing_outer_predicate(self, parser):
        # The exact W3C Turtle 1.2 fixture shape (turtle12-syntax-inside-01.ttl):
        # the bracketed blank node is itself also the subject of an outer
        # triple following the closing bracket.
        g = parser.parse('PREFIX : <http://example.org/>\n[ :q :z ] :b :c .\n')
        assert len(g) == 2
        bnode_subjects = {s for s, p, o in g if p == URIRef(EX+'q')}
        assert len(bnode_subjects) == 1
        bnode = next(iter(bnode_subjects))
        assert isinstance(bnode, BNode)
        assert (bnode, URIRef(EX+'b'), URIRef(EX+'c')) in g

    def test_bracket_with_triple_term_inside(self, parser):
        g = parser.parse(
            'PREFIX : <http://example.org/>\n'
            '[ rdf:reifies <<( :a :b :c )>> ; :q :z ] .\n'
        )
        bnode_subjects = {s for s, p, o in g if p == URIRef(EX+'q')}
        assert len(bnode_subjects) == 1
        bnode = next(iter(bnode_subjects))
        assert (bnode, URIRef(EX+'q'), URIRef(EX+'z')) in g
        reified = list(g.objects(bnode, RDF_REIFIES))
        assert len(reified) == 1


# ---------------------------------------------------------------------------
# RDF 1.2 features
# ---------------------------------------------------------------------------

class TestTripleTerms:
    def test_triple_term_creates_sl_node(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        tt_nodes = list(g.subjects(RDF.type, SL_TRIPLE_TERM))
        assert len(tt_nodes) == 1

    def test_triple_term_has_subject(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        tt = list(g.subjects(RDF.type, SL_TRIPLE_TERM))[0]
        assert list(g.objects(tt, RDF.subject)) == [URIRef(EX+'s')]

    def test_triple_term_deduplication(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r1 rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
            'ex:r2 rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
        )
        tt_nodes = list(g.subjects(RDF.type, SL_TRIPLE_TERM))
        assert len(tt_nodes) == 1

    def test_two_distinct_triple_terms(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:r1 rdf:reifies <<( ex:s ex:p ex:o )>> .\n'
            'ex:r2 rdf:reifies <<( ex:a ex:b ex:c )>> .\n'
        )
        tt_nodes = list(g.subjects(RDF.type, SL_TRIPLE_TERM))
        assert len(tt_nodes) == 2


class TestBnodeListInTripleTerm:
    """RDF 1.2 grammar: ttSubject/rtSubject/ttObject/rtObject all admit
    `BlankNode`, which is BLANK_NODE_LABEL or ANON (a bare `_:label` or an
    *empty* `[]`) - never a blankNodePropertyList carrying its own
    properties. Confirmed directly against the W3C RDF 1.2 Turtle syntax
    test suite (turtle12-bad-7, "compound blank node expression", a
    TestTurtleNegativeSyntax case - see tests/w3c_turtle12/).

    An earlier version of this parser instead silently *expanded* a
    non-empty `[ ... ]` here (a bug fix for a different problem: it used to
    produce a garbage URIRef from the raw bracket text) - that was more
    lenient than the grammar actually allows. Both the acceptance below
    (empty `[]`) and the rejection (non-empty) are asserted here."""

    def test_empty_bnode_in_object_position_accepted(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:a ex:says <<( ex:bob ex:knows [] )>> .\n'
        )
        tt = list(g.subjects(RDF.type, SL_TRIPLE_TERM))[0]
        obj = list(g.objects(tt, RDF.object))[0]
        assert isinstance(obj, BNode)

    def test_empty_bnode_in_subject_position_accepted(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:a ex:says <<( [] ex:knows ex:carol )>> .\n'
        )
        tt = list(g.subjects(RDF.type, SL_TRIPLE_TERM))[0]
        subj = list(g.objects(tt, RDF.subject))[0]
        assert isinstance(subj, BNode)

    def test_bnode_with_properties_in_object_position_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:a ex:says <<( ex:bob ex:knows [ ex:name "Bob" ] )>> .\n'
            )

    def test_bnode_with_properties_in_subject_position_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:a ex:says <<( [ ex:name "Bob" ] ex:knows ex:carol )>> .\n'
            )

    def test_bnode_with_properties_in_reification_shorthand_rejected(self, parser):
        """Same restriction applies to << >> (rtObject), not just <<( )>>."""
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                '<< ex:s ex:p [ ex:a 1 ] >> ex:q 123 .\n'
            )


class TestTripleTermPositionValidation:
    """RDF 1.2 grammar restricts what can appear in each slot of
    <<( s p o )>>/<< s p o >>: the verb is always an IRI, ttSubject/
    rtSubject is iri|BlankNode (no literal), and a tripleTerm/reifiedTriple
    itself can never appear as an outer triple's predicate. Confirmed
    against the W3C RDF 1.2 Turtle syntax test suite (tests/w3c_turtle12/)."""

    def test_reified_triple_as_predicate_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:x << ex:s ex:p ex:o >> 123 .\n'
            )

    def test_triple_term_as_predicate_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:a <<( ex:s ex:p ex:o )>> ex:z .\n'
            )

    def test_literal_as_triple_term_subject_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:q ex:r <<( "XYZ" ex:p ex:o )>> .\n'
            )

    def test_literal_as_verb_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:q ex:r <<( ex:s "XYZ" ex:o )>> .\n'
            )

    def test_bnode_as_verb_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:q ex:r << ex:s _:label ex:o >> .\n'
            )

    def test_over_long_reified_triple_rejected(self, parser):
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.org/>\n'
                'ex:s ex:p << ex:g ex:s ex:p ex:o >> .\n'
            )


class TestReification:
    def test_reification_shorthand_as_subject(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            '<< ex:s ex:p ex:o >> ex:q ex:z .\n'
        )
        reif_nodes = list(g.subjects(RDF.type, SL_REIFICATION))
        assert len(reif_nodes) == 1

    def test_reification_node_tagged(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            '<< ex:s ex:p ex:o >> ex:q ex:z .\n'
        )
        reif = list(g.subjects(RDF.type, SL_REIFICATION))[0]
        tt_nodes = list(g.objects(reif, RDF_REIFIES))
        assert len(tt_nodes) == 1
        assert list(g.objects(tt_nodes[0], RDF.type)) == [SL_TRIPLE_TERM]


class TestAnnotations:
    def test_annotation_emits_main_triple(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o {| ex:certainty "0.9" |} .\n'
        )
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in g

    def test_annotation_creates_reification(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o {| ex:certainty "0.9" |} .\n'
        )
        reif_nodes = list(g.subjects(RDF.type, SL_REIFICATION))
        assert len(reif_nodes) == 1

    def test_annotation_triple_attached_to_reifier(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o {| ex:certainty "0.9" |} .\n'
        )
        reif = list(g.subjects(RDF.type, SL_REIFICATION))[0]
        vals = list(g.objects(reif, URIRef(EX+'certainty')))
        assert vals == [Literal('0.9')]

    def test_explicit_reifier(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o ~ ex:stmt {| ex:certainty "0.9" |} .\n'
        )
        assert (URIRef(EX+'stmt'), RDF_REIFIES, None) in [(s, p, None) for s, p, o in g]
        vals = list(g.objects(URIRef(EX+'stmt'), URIRef(EX+'certainty')))
        assert vals == [Literal('0.9')]

    def test_multiple_annotations(self, parser):
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o {| ex:a "1" ; ex:b "2" |} .\n'
        )
        reif = list(g.subjects(RDF.type, SL_REIFICATION))[0]
        ann_a = list(g.objects(reif, URIRef(EX+'a')))
        ann_b = list(g.objects(reif, URIRef(EX+'b')))
        assert ann_a == [Literal('1')]
        assert ann_b == [Literal('2')]

    def test_bare_tilde_with_annotation_block(self, parser):
        """'~ {| |}' - a bare, anonymous reifier immediately followed by an
        annotation block (reifier ::= '~' (iri|BlankNode)? - the name is
        optional) must parse, with the block's properties attached to a
        fresh anonymous reifier (W3C turtle12-ann-8, "empty reifier with
        annotation block" - see tests/w3c_turtle12/)."""
        g = parser.parse(
            'PREFIX ex: <http://example.org/>\n'
            'ex:s ex:p ex:o ~ {| ex:q ex:r |} .\n'
        )
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in g
        reif = list(g.subjects(RDF.type, SL_REIFICATION))[0]
        assert list(g.objects(reif, URIRef(EX+'q'))) == [URIRef(EX+'r')]

    def test_triple_as_annotation_body_rejected(self, parser):
        """{| :s :p :o |} (3 terms - a full triple, not a predicateObjectList)
        must be rejected, not silently truncated to just the first pred/obj
        pair with the rest dropped (W3C turtle12-bad-ann-2, "triple as
        annotation" - see tests/w3c_turtle12/)."""
        with pytest.raises(TurtleSyntaxError):
            parser.parse(
                'PREFIX ex: <http://example.com/ns#>\n'
                'ex:a ex:b ex:c {| ex:s ex:p ex:o |} .\n'
            )


class TestDirLangStringCaseSensitivity:
    """RDF 1.2 Concepts sec 3.4: base direction MUST be exactly "ltr" or
    "rtl" (lowercase only - not case-folded the way the language tag
    itself is, per sec 3.4.1). Confirmed against the W3C RDF 1.2 Turtle
    syntax test suite (nt-ttl12-langdir-bad-2 - see tests/w3c_turtle12/)."""

    def test_lowercase_direction_accepted(self, parser):
        g = parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "hi"@en--rtl .\n')
        assert len(g) == 1

    def test_uppercase_direction_rejected(self, parser):
        with pytest.raises(Exception):
            parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "hi"@en--LTR .\n')


class TestSurrogateEscapes:
    """Turtle's UCHAR (\\uXXXX/\\UXXXXXXXX) grammar directly encodes a
    Unicode codepoint - the UTF-16 surrogate range (U+D800-U+DFFF) is
    excluded, since surrogates are a UTF-16 encoding artifact, not a valid
    standalone codepoint (a supplementary-plane character is written with
    a single \\U escape of its real codepoint, not a \\u\\u surrogate pair
    the way JSON/JavaScript encode it). Confirmed against the W3C RDF 1.2
    Turtle syntax test suite (turtle12-surrogate*/turtle12-surrogates-bad-*
    - see tests/w3c_turtle12/)."""

    def test_non_surrogate_uchar_accepted(self, parser):
        g = parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "\\u0041" .\n')
        assert len(g) == 1

    def test_lone_high_surrogate_rejected(self, parser):
        with pytest.raises(Exception):
            parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "\\uD83C" .\n')

    def test_lone_low_surrogate_rejected(self, parser):
        with pytest.raises(Exception):
            parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "\\uDCA1" .\n')

    def test_surrogate_pair_rejected(self, parser):
        """Even a well-formed high+low pair (which JSON/JS would combine
        into a supplementary-plane character) is invalid - Turtle has no
        such combining rule for \\u escapes."""
        with pytest.raises(Exception):
            parser.parse('PREFIX ex: <http://example.org/>\nex:a ex:b "\\uD83C\\uDCA1" .\n')


# ---------------------------------------------------------------------------
# RDF 1.2 version declaration parsing
# ---------------------------------------------------------------------------

class TestVersionDirective:
    def test_turtle_version_directive_ignored(self, parser):
        """@version "1.2" . is silently consumed; triples parse normally."""
        ttl = f'@version "1.2" .\n@prefix ex: <{EX}> .\nex:s ex:p ex:o .\n'
        g = parser.parse(ttl)
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in g

    def test_sparql_version_directive_ignored(self, parser):
        """VERSION "1.2" (no period) is silently consumed; triples parse normally."""
        ttl = f'VERSION "1.2"\n@prefix ex: <{EX}> .\nex:s ex:p ex:o .\n'
        g = parser.parse(ttl)
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in g

    def test_version_directive_with_triple_terms(self, parser):
        """@version directive does not interfere with triple-term parsing."""
        RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
        ttl = (
            '@version "1.2" .\n'
            f'@prefix ex: <{EX}> .\n'
            '@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n'
            'ex:stmt rdf:reifies <<( ex:alice ex:knows ex:bob )>> .\n'
        )
        g = parser.parse(ttl)
        from starlayergraph.graph import StarLayerGraph
        sg = StarLayerGraph.from_rdflib(g)
        assert len(list(sg.triple_terms())) == 1

    def test_round_trip_preserves_version(self, parser):
        """Serialize with @version, re-parse, verify data intact."""
        from starlayergraph.graph import StarLayerGraph
        from starlayergraph.model.triple import TripleTerm
        RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
        sg = StarLayerGraph()
        sg.bind('ex', EX)
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg.add((URIRef(EX+'stmt1'), RDF_REIFIES, tt))
        out = sg.serialize(format='turtle12')
        assert '@version "1.2" .' in out
        g2 = parser.parse(out)
        sg2 = StarLayerGraph.from_rdflib(g2)
        assert sg2.has_triple_term(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))


# ---------------------------------------------------------------------------
# Base URI resolution (RFC 3986)
# ---------------------------------------------------------------------------

class TestBaseURI:
    def test_fragment_relative(self, parser):
        """<#name> resolved against @base gives base + fragment."""
        ttl = (
            '@base <http://example.org/> .\n'
            '@prefix ex: <http://example.org/> .\n'
            '<#alice> ex:knows <#bob> .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef('http://example.org/#alice'), URIRef(EX+'knows'), URIRef('http://example.org/#bob')) in g

    def test_path_relative(self, parser):
        """A path-relative IRI is resolved against the base."""
        ttl = (
            '@base <http://example.org/data/> .\n'
            '@prefix ex: <http://example.org/> .\n'
            '<alice> ex:knows <bob> .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef('http://example.org/data/alice'), URIRef(EX+'knows'), URIRef('http://example.org/data/bob')) in g

    def test_dot_dot_navigation(self, parser):
        """<../other> navigates up from the base path."""
        ttl = (
            '@base <http://example.org/a/b/> .\n'
            '@prefix ex: <http://example.org/> .\n'
            '<../../alice> ex:knows ex:bob .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef('http://example.org/alice'), URIRef(EX+'knows'), URIRef(EX+'bob')) in g

    def test_multiple_base_declarations(self, parser):
        """Each @base affects only the triples that follow it."""
        ttl = (
            '@base <http://example.org/a/> .\n'
            '@prefix ex: <http://example.org/> .\n'
            '<x> ex:type ex:A .\n'
            '@base <http://example.org/b/> .\n'
            '<y> ex:type ex:B .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef('http://example.org/a/x'), URIRef(EX+'type'), URIRef(EX+'A')) in g
        assert (URIRef('http://example.org/b/y'), URIRef(EX+'type'), URIRef(EX+'B')) in g

    def test_second_base_relative_to_first(self, parser):
        """A relative @base is resolved against the active base."""
        ttl = (
            '@base <http://example.org/> .\n'
            '@prefix ex: <http://example.org/> .\n'
            '@base <sub/> .\n'
            '<item> ex:type ex:Thing .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef('http://example.org/sub/item'), URIRef(EX+'type'), URIRef(EX+'Thing')) in g

    def test_absolute_iri_unaffected_by_base(self, parser):
        """Absolute IRIs are never modified by @base."""
        ttl = (
            '@base <http://example.org/> .\n'
            '<http://other.org/alice> <http://other.org/knows> <http://other.org/bob> .\n'
        )
        g = parser.parse(ttl)
        assert (
            URIRef('http://other.org/alice'),
            URIRef('http://other.org/knows'),
            URIRef('http://other.org/bob'),
        ) in g

    def test_g_base_set_to_last_base(self, parser):
        """g.base is set to the last active @base declaration."""
        ttl = (
            '@base <http://example.org/a/> .\n'
            '@base <http://example.org/b/> .\n'
            '<x> <http://example.org/p> <http://example.org/o> .\n'
        )
        g = parser.parse(ttl)
        assert str(g.base) == 'http://example.org/b/'

    def test_base_seeded_via_parse_argument(self, parser):
        """parse(..., base=...) resolves "<>" and relative IRIs without
        needing an in-document @base directive - the caller-supplied base
        plays the same role StarLayerGraph.parse()'s publicID does.
        Previously there was no way to seed this at all; a document with no
        @base of its own had no working relative-IRI resolution regardless
        of what the caller passed in."""
        ttl = '@prefix ex: <http://example.org/> .\n<> ex:knows <bob> .\n'
        g = parser.parse(ttl, base='http://example.org/data/alice.ttl')
        assert (
            URIRef('http://example.org/data/alice.ttl'),
            URIRef(EX + 'knows'),
            URIRef('http://example.org/data/bob'),
        ) in g

    def test_in_document_base_overrides_seeded_base(self, parser):
        """An in-document @base still takes over from the seeded base for
        every triple after it, exactly as if the seeded base were itself a
        preceding @base declaration."""
        ttl = (
            '@base <http://example.org/other/> .\n'
            '<x> <http://example.org/p> <http://example.org/o> .\n'
        )
        g = parser.parse(ttl, base='http://example.org/seeded/')
        assert (
            URIRef('http://example.org/other/x'),
            URIRef('http://example.org/p'),
            URIRef('http://example.org/o'),
        ) in g

    def test_no_base_seeded_behaves_as_before(self, parser):
        """base=None (the default) - a document with no @base and no seeded
        base still resolves a relative IRI as a bare relative string, same
        as prior behavior (regression guard for the new parameter's default)."""
        ttl = '@prefix ex: <http://example.org/> .\n<x> ex:p <y> .\n'
        g = parser.parse(ttl)
        assert (URIRef('x'), URIRef(EX + 'p'), URIRef('y')) in g


# ---------------------------------------------------------------------------
# Lexical edge cases found via the W3C SHACL 1.2 test suite (a downstream
# consumer's real-world fixtures, not part of this package).
# ---------------------------------------------------------------------------

class TestNoSpaceBeforeDelimiter:
    """A predicate/subject/object token followed immediately by '(', '[',
    '"', etc. with no separating whitespace is valid Turtle (none of these
    characters can appear inside a PrefixedName/IRI/literal token, so no
    space is needed to disambiguate) - previously the plain-token fallback
    scanner only stopped at whitespace or '<', gluing the delimiter onto the
    preceding token instead of starting a new one."""

    def test_predicate_immediately_followed_by_collection(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p( ex:a ex:b ) .\n'
        g = parser.parse(ttl)
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), RDF.first) not in g  # sanity: no garbage predicate
        first = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        assert list(g.items(first)) == [URIRef(EX + 'a'), URIRef(EX + 'b')]

    def test_predicate_immediately_followed_by_blank_node(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p[ ex:q ex:o ] .\n'
        g = parser.parse(ttl)
        bnode = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        assert (bnode, URIRef(EX + 'q'), URIRef(EX + 'o')) in g

    def test_predicate_immediately_followed_by_quoted_literal(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p"hello" .\n'
        g = parser.parse(ttl)
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('hello')) in g


class TestCollectionElementLiteralCoercion:
    """A bare numeric/boolean Turtle literal used as an RDF collection member
    (e.g. "( 42 )") needs the same string->Python-value coercion an ordinary
    (non-list) object already gets - previously only non-list objects were
    coerced, so a bare literal *inside* a collection reached final term
    conversion as a raw string and was rejected as an unrecognized term."""

    def test_bare_integer_in_collection(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p ( 42 ) .\n'
        g = parser.parse(ttl)
        head = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        assert list(g.items(head)) == [Literal(42, datatype=XSD.integer)]

    def test_bare_boolean_in_collection(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p ( true false ) .\n'
        g = parser.parse(ttl)
        head = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        assert list(g.items(head)) == [
            Literal(True, datatype=XSD.boolean),
            Literal(False, datatype=XSD.boolean),
        ]

    def test_bare_float_in_collection(self, parser):
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p ( 3.5 ) .\n'
        g = parser.parse(ttl)
        head = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        assert list(g.items(head)) == [Literal(3.5, datatype=XSD.decimal)]

    def test_blank_node_member_still_expands_normally(self, parser):
        """Regression guard: fixing literal coercion for collection members
        must not disturb the existing (already-correct) expansion of a
        '[ ... ]' blank-node member into its own triples."""
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p ( [ ex:q ex:o ] 42 ) .\n'
        g = parser.parse(ttl)
        head = next(g.objects(URIRef(EX + 's'), URIRef(EX + 'p')))
        members = list(g.items(head))
        assert len(members) == 2
        assert isinstance(members[0], BNode)
        assert (members[0], URIRef(EX + 'q'), URIRef(EX + 'o')) in g
        assert members[1] == Literal(42, datatype=XSD.integer)


class TestMidLineComments:
    """A '#' comment starting after other content on the same line must be
    stripped, the same as a comment occupying a whole line by itself -
    previously only a whole comment-only line was recognized."""

    def test_comment_after_semicolon(self, parser):
        ttl = (
            '@prefix ex: <http://example.org/> .\n'
            'ex:s ex:p ex:o ;  # trailing note\n'
            '  ex:q ex:r .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), URIRef(EX + 'o')) in g
        assert (URIRef(EX + 's'), URIRef(EX + 'q'), URIRef(EX + 'r')) in g

    def test_comment_after_statement_end(self, parser):
        ttl = (
            '@prefix ex: <http://example.org/> .\n'
            'ex:s ex:p ex:o .  # done\n'
            'ex:s2 ex:p2 ex:o2 .\n'
        )
        g = parser.parse(ttl)
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), URIRef(EX + 'o')) in g
        assert (URIRef(EX + 's2'), URIRef(EX + 'p2'), URIRef(EX + 'o2')) in g

    def test_hash_inside_iri_fragment_not_treated_as_comment(self, parser):
        """A '#' inside an <IRI> (a fragment identifier) is real IRI content,
        not a comment start - must not be stripped."""
        ttl = '<http://example.org/page#frag> <http://example.org/p> <http://example.org/o> .\n'
        g = parser.parse(ttl)
        assert (
            URIRef('http://example.org/page#frag'),
            URIRef('http://example.org/p'),
            URIRef('http://example.org/o'),
        ) in g

    def test_hash_inside_string_not_treated_as_comment(self, parser):
        """A '#' inside a quoted string literal is real content, not a
        comment start - must not be stripped."""
        ttl = '@prefix ex: <http://example.org/> .\nex:s ex:p "a # not a comment" .\n'
        g = parser.parse(ttl)
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('a # not a comment')) in g
