"""
Unit tests for starlayergraph.serializers.turtle12.

Each test parses a TTL 1.2 snippet, serializes it back, then re-parses the
output and checks graph isomorphism — confirming a faithful round-trip.
"""

import pytest
from rdflib import Literal, URIRef
from rdflib.compare import isomorphic
from starlayergraph.graph.starlayer_graph import RDF_REIFIES, StarLayerGraph
from starlayergraph.model.triple import TripleTerm
from starlayergraph.serializers.turtle12 import serialize_turtle12

EX = 'http://example/'


def _roundtrip(ttl12_text):
    """Parse TTL 1.2 → StarLayerGraph → serialize → re-parse.

    Returns (raw1, raw2, output_text) where raw1/raw2 are plain rdflib.Graphs
    with the SL internal encoding, suitable for isomorphic() comparison.
    """
    from starlayergraph.parsers.turtle_parser import StarLayerTurtleParser
    raw1 = StarLayerTurtleParser().parse(ttl12_text)
    sg1 = StarLayerGraph.from_rdflib(raw1)
    out = serialize_turtle12(sg1)
    raw2 = StarLayerTurtleParser().parse(out)
    return raw1, raw2, out


# ---------------------------------------------------------------------------
# Output contains <<( )>> notation
# ---------------------------------------------------------------------------

class TestTtl12Notation:
    def test_tt_as_object_written_with_angle_brackets(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':s :p <<( :a :b :c )>> .\n'
        )
        out = serialize_turtle12(raw)
        assert '<<(' in out
        assert ':a' in out
        assert ':b' in out
        assert ':c' in out

    def test_tt_as_subject_written_with_angle_brackets(self, parser):
        # << >> (no parens) is the reification shorthand in subject position
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            '<< :a :b :c >> :p :o .\n'
        )
        out = serialize_turtle12(raw)
        assert '<< ' in out
        assert '<<(' not in out

    def test_tt_term_as_subject_rejected(self, parser):
        # <<( )>> in subject position is a syntax error per RDF 1.2
        with pytest.raises((SyntaxError, Exception)):
            parser.parse(
                '@prefix : <http://example/> .\n'
                '<<( :a :b :c )>> :p :o .\n'
            )

    def test_no_sl_tripleTerm_type_in_output(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':s rdf:reifies <<( :a :b :c )>> .\n'
        )
        out = serialize_turtle12(raw)
        assert 'TripleTerm' not in out

    def test_no_sl_reification_type_in_output(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':s :p :o {| :ann :val |} .\n'
        )
        out = serialize_turtle12(raw)
        assert 'Reification' not in out

    def test_encoding_predicates_absent(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':s rdf:reifies <<( :a :b :c )>> .\n'
        )
        out = serialize_turtle12(raw)
        assert 'rdf:subject'   not in out
        assert 'rdf:predicate' not in out
        assert 'rdf:object'    not in out


# ---------------------------------------------------------------------------
# Round-trip isomorphism
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_tt_as_object(self):
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            ':s :p <<( :a :b :c )>> .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_tt_as_subject(self):
        # << >> (no parens) is the reification shorthand; serializer round-trips it
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            '<< :a :b :c >> :p :o .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_annotation(self):
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            ':s :p :o {| :ann :val |} .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_annotation_multi(self):
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            ':s :p :o {| :ann1 :val1 ; :ann2 :val2 |} .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_explicit_reifier(self):
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            ':s :p :o ~ :i {| :ann :val |} .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_shared_tt(self):
        # Two anonymous reifiers on the same unasserted TT are merged into one
        # << >> subject block — the serializer emits reification shorthand (no parens).
        _, raw2, out = _roundtrip(
            '@prefix : <http://example/> .\n'
            '[] rdf:reifies <<( :a :b :c )>> ; :p :o .\n'
            '[] rdf:reifies <<( :a :b :c )>> ; :p1 :o1 .\n'
        )
        assert '<< ' in out
        assert 'rdf:reifies' not in out
        tt_triples = [(p, o) for s, p, o in raw2.triples((None, None, None))]
        preds = {str(p) for p, _ in tt_triples}
        assert 'http://example/p' in preds
        assert 'http://example/p1' in preds

    def test_tt_as_subject_with_property(self):
        # << >> (reification shorthand) in subject position round-trips
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            '<< :a :b :c >> :funny true .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_plain_turtle_unchanged(self):
        raw1, raw2, _ = _roundtrip(
            '@prefix : <http://example/> .\n'
            ':alice :knows :bob .\n'
            ':bob :name "Bob" .\n'
        )
        assert isomorphic(raw1, raw2)

    def test_ex1_full(self):
        # Two anonymous reifiers + direct TT property all merge into one << >> subject block.
        _, raw2, out = _roundtrip(
            '@prefix : <http://example/> .\n'
            '[] :p :o ; rdf:reifies <<( :a :b :c )>> .\n'
            '[] :p1 :o1 ; rdf:reifies <<( :a :b :c )>> .\n'
            '<< :a :b :c >> :funny true .\n'
        )
        assert '<< ' in out
        assert 'rdf:reifies' not in out
        preds = {str(p) for _, p, _ in raw2.triples((None, None, None))}
        assert 'http://example/p' in preds
        assert 'http://example/p1' in preds
        assert 'http://example/funny' in preds


# ---------------------------------------------------------------------------
# StarLayerGraph.serialize(format='turtle12') integration
# ---------------------------------------------------------------------------

class TestSerializeMethod:
    def test_sg_serialize_turtle12(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':s :p <<( :a :b :c )>> .\n'
        )
        sg = StarLayerGraph.from_rdflib(raw)
        out = sg.serialize(format='turtle12')
        assert '<<(' in out
        assert 'TripleTerm' not in out

    def test_sg_serialize_default_still_works(self, parser):
        raw = parser.parse(
            '@prefix : <http://example/> .\n'
            ':alice :knows :bob .\n'
        )
        sg = StarLayerGraph.from_rdflib(raw)
        out = sg.serialize(format='turtle')
        assert ':alice' in out

    def test_sg_serialize_turtle12_from_add(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'r'), RDF_REIFIES, (URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))))
        out = sg.serialize(format='turtle12')
        assert '<<(' in out
        assert 'TripleTerm' not in out


# ---------------------------------------------------------------------------
# RDF 1.2 version declaration
# ---------------------------------------------------------------------------

class TestVersionDeclaration:
    def test_version_emitted_when_triple_terms_present(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'stmt'), RDF_REIFIES,
                TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        out = sg.serialize(format='turtle12')
        assert '@version "1.2" .' in out

    def test_version_before_prefix_lines(self):
        sg = StarLayerGraph()
        sg.bind('ex', EX)
        sg.add((URIRef(EX+'stmt'), RDF_REIFIES,
                TripleTerm(URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o'))))
        out = sg.serialize(format='turtle12')
        lines = out.splitlines()
        version_idx = next(i for i, line in enumerate(lines) if '@version' in line)
        prefix_idx  = next(i for i, line in enumerate(lines) if '@prefix' in line)
        assert version_idx < prefix_idx

    def test_version_not_emitted_for_plain_graph(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        out = sg.serialize(format='turtle12')
        assert '@version' not in out

    def test_version_not_emitted_for_empty_graph(self):
        sg = StarLayerGraph()
        out = sg.serialize(format='turtle12')
        assert '@version' not in out

# ---------------------------------------------------------------------------
# longturtle12 serializer
# ---------------------------------------------------------------------------

class TestLongTurtle12:
    def test_one_triple_per_line(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o1')))
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o2')))
        out = sg.serialize(format='longturtle12')
        triple_lines = [line for line in out.splitlines() if line.strip() and not line.startswith('@')]
        assert len(triple_lines) == 2

    def test_no_semicolon_grouping(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.add((URIRef(EX+'s'), URIRef(EX+'q'), URIRef(EX+'z')))
        out = sg.serialize(format='longturtle12')
        assert ';' not in out

    def test_no_comma_grouping(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o1')))
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o2')))
        out = sg.serialize(format='longturtle12')
        assert ',' not in out

    def test_triple_term_serialized(self):
        sg = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIFIES, tt))
        out = sg.serialize(format='longturtle12')
        assert '<<(' in out

    def test_version_emitted_with_triple_terms(self):
        sg = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'a'), URIRef(EX+'b'), URIRef(EX+'c'))
        sg.add((URIRef(EX+'stmt'), RDF_REIFIES, tt))
        out = sg.serialize(format='longturtle12')
        assert '@version "1.2" .' in out

    def test_version_not_emitted_for_plain_graph(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        out = sg.serialize(format='longturtle12')
        assert '@version' not in out

    def test_round_trip_plain_triples(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')))
        sg.add((URIRef(EX+'s'), URIRef(EX+'q'), Literal('hello')))
        out = sg.serialize(format='longturtle12')
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='longturtle12')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg2
        assert (URIRef(EX+'s'), URIRef(EX+'q'), Literal('hello')) in sg2

    def test_round_trip_triple_term(self):
        sg = StarLayerGraph()
        tt = TripleTerm(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))
        sg.add((URIRef(EX+'stmt'), RDF_REIFIES, tt))
        out = sg.serialize(format='longturtle12')
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='longturtle12')
        assert sg2.has_triple_term(URIRef(EX+'alice'), URIRef(EX+'knows'), URIRef(EX+'bob'))

    def test_parse_via_longturtle12_alias(self):
        ttl = (
            f'@prefix ex: <{EX}> .\n'
            f'ex:s ex:p ex:o .\n'
        )
        sg = StarLayerGraph()
        sg.parse(data=ttl, format='longturtle12')
        assert (URIRef(EX+'s'), URIRef(EX+'p'), URIRef(EX+'o')) in sg


# ---------------------------------------------------------------------------
# Bare boolean/integer/decimal literal shorthand, and 'a' for rdf:type
# ---------------------------------------------------------------------------

class TestBareLiteralShorthandAndRdfTypeKeyword:
    """serialize_turtle12 emits Turtle's own bare BooleanLiteral/INTEGER/
    DECIMAL tokens (true/false, 42, 1.5) instead of "value"^^xsd:type, and
    the 'a' keyword for rdf:type - but only when the literal's own lexical
    form actually matches Turtle's bare-token grammar, which is narrower
    than XSD's own lexical space for each datatype. A value typed as one
    of these but whose lexical form doesn't match must fall back to the
    quoted+typed form - that's always syntactically valid Turtle
    regardless of how malformed the lexical form is; the bare form isn't."""

    def _roundtrip_and_serialized(self, sg):
        out = sg.serialize(format='turtle12')
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='turtle12')
        return out, sg2

    def test_boolean_true_false_emitted_bare(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p1'), Literal(True)))
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p2'), Literal(False)))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '^^' not in out
        assert (URIRef(EX + 's'), URIRef(EX + 'p1'), Literal(True)) in sg2
        assert (URIRef(EX + 's'), URIRef(EX + 'p2'), Literal(False)) in sg2

    def test_integer_emitted_bare_including_negative(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal(42)))
        sg.add((URIRef(EX + 's'), URIRef(EX + 'q'), Literal(-5)))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '^^' not in out
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal(42)) in sg2
        assert (URIRef(EX + 's'), URIRef(EX + 'q'), Literal(-5)) in sg2

    def test_decimal_emitted_bare(self):
        from rdflib import XSD
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('1.5', datatype=XSD.decimal)))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '^^' not in out
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('1.5', datatype=XSD.decimal)) in sg2

    def test_rdf_type_emitted_as_a_keyword(self):
        from rdflib import RDF
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), RDF.type, URIRef(EX + 'Thing')))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert ' a ' in out
        assert 'rdf:type' not in out
        assert (URIRef(EX + 's'), RDF.type, URIRef(EX + 'Thing')) in sg2

    def test_malformed_integer_lexical_form_falls_back_to_typed_form(self):
        # rdflib allows constructing this even though it warns - confirmed
        # live this previously serialized as a bare, unquoted, unparseable
        # token ("ex:s ex:p not-a-number .") and failed to re-parse at all.
        from rdflib import XSD
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('not-a-number', datatype=XSD.integer)))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '"not-a-number"^^xsd:integer' in out
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('not-a-number', datatype=XSD.integer)) in sg2

    def test_decimal_lexical_form_with_no_fractional_digits_falls_back(self):
        # Turtle's DECIMAL grammar requires >=1 digit after the '.' -
        # emitting a bare token with none (or none at all) would also be
        # ambiguous with INTEGER on re-parse.
        from rdflib import XSD
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('5', datatype=XSD.decimal)))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '"5"^^xsd:decimal' in out
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('5', datatype=XSD.decimal)) in sg2


# ---------------------------------------------------------------------------
# RDF list folding: turtle12 emits Turtle's '( a b c )' collection syntax
# instead of expanded rdf:first/rdf:rest/rdf:nil chains.
# ---------------------------------------------------------------------------

class TestListFolding:
    def _roundtrip_and_serialized(self, sg):
        out = sg.serialize(format='turtle12')
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='turtle12')
        return out, sg2

    def test_simple_list_folded(self):
        sg = StarLayerGraph()
        sg.parse(
            data=f'@prefix ex: <{EX}> .\nex:s ex:p ( ex:a ex:b ex:c ) .\n',
            format='turtle12',
        )
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert 'rdf:first' not in out
        assert 'rdf:rest' not in out
        assert '( ex:a ex:b ex:c )' in out
        assert isomorphic(sg, sg2)

    def test_list_of_blank_node_shapes_folded(self):
        # Each list item is itself a blank node with its own predicates -
        # matching real SHACL sh:or/sh:and usage, not just plain IRIs.
        sg = StarLayerGraph()
        sg.parse(
            data=(
                f'@prefix ex: <{EX}> .\n'
                'ex:S ex:or ( [ ex:path ex:email ] [ ex:path ex:orcid ] ) .\n'
            ),
            format='turtle12',
        )
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert 'rdf:first' not in out
        assert isomorphic(sg, sg2)

    def test_list_cell_with_extra_triple_not_folded(self):
        # A cell carrying some *other* triple besides rdf:first/rdf:rest
        # can't be folded away without losing that triple - must stay
        # expanded (same well-formedness rule rdflib's own serializer uses).
        sg = StarLayerGraph()
        sg.parse(
            data=(
                f'@prefix ex: <{EX}> .\n'
                'ex:s ex:p _:b0 .\n'
                '_:b0 rdf:first ex:a ; rdf:rest rdf:nil ; ex:extra "not part of the list" .\n'
            ),
            format='turtle12',
        )
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert 'rdf:first' in out  # not foldable - the extra triple would be lost otherwise
        assert isomorphic(sg, sg2)

    def test_shared_list_cell_not_folded(self):
        # A cell referenced from two different places can't be folded away -
        # doing so would hide the fact that something else points at it too.
        sg = StarLayerGraph()
        sg.parse(
            data=(
                f'@prefix ex: <{EX}> .\n'
                'ex:s1 ex:p _:b0 .\n'
                'ex:s2 ex:q _:b0 .\n'
                '_:b0 rdf:first ex:a ; rdf:rest rdf:nil .\n'
            ),
            format='turtle12',
        )
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert 'rdf:first' in out
        assert isomorphic(sg, sg2)

    def test_empty_graph_no_lists_unaffected(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), URIRef(EX + 'o')))
        out, sg2 = self._roundtrip_and_serialized(sg)
        assert '(' not in out
        assert isomorphic(sg, sg2)


# ---------------------------------------------------------------------------
# Multi-line string literals: turtle12 (compact) preserves them via Turtle's
# triple-quoted '"""..."""' form; longturtle12 (canonical) escapes newlines
# instead, to keep its one-triple-per-line guarantee.
# ---------------------------------------------------------------------------

class TestMultilineStringLiterals:
    def test_turtle12_uses_triple_quote_and_preserves_newlines(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('line one\nline two')))
        out = sg.serialize(format='turtle12')
        assert '"""' in out
        assert 'line one\nline two' in out
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='turtle12')
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('line one\nline two')) in sg2

    def test_turtle12_single_quote_for_single_line(self):
        # Regression guard: the triple-quote branch must not fire for
        # ordinary single-line literals.
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('no newlines here')))
        out = sg.serialize(format='turtle12')
        assert '"""' not in out

    def test_longturtle12_escapes_newline_keeps_one_line_per_triple(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('line one\nline two')))
        out = sg.serialize(format='longturtle12')
        assert '"""' not in out
        assert '\\n' in out
        triple_lines = [line for line in out.splitlines() if line.strip() and not line.startswith('@')]
        assert len(triple_lines) == 1
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='longturtle12')
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal('line one\nline two')) in sg2

    def test_embedded_quotes_in_multiline_literal_round_trip(self):
        # Realistic case: an embedded SPARQL query containing string
        # literals of its own (e.g. FILTER(?x = "foo")) inside a
        # multi-line sh:select/sh:construct value.
        text = 'PREFIX ex: <http://example.org/>\nSELECT $this WHERE {\n  $this ex:p "foo" .\n}'
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal(text)))
        out = sg.serialize(format='turtle12')
        sg2 = StarLayerGraph()
        sg2.parse(data=out, format='turtle12')
        assert (URIRef(EX + 's'), URIRef(EX + 'p'), Literal(text)) in sg2


# ---------------------------------------------------------------------------
# longturtle12 is fully canonical - unlike turtle12, it must never use the
# bare boolean/integer/decimal shorthand, even though the same underlying
# _node_to_ttl function implements both.
# ---------------------------------------------------------------------------

class TestLongTurtle12Canonical:
    def test_boolean_not_bare_in_longturtle12(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal(True)))
        out = sg.serialize(format='longturtle12')
        assert '^^xsd:boolean' in out

    def test_integer_not_bare_in_longturtle12(self):
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal(42)))
        out = sg.serialize(format='longturtle12')
        assert '^^xsd:integer' in out

    def test_decimal_not_bare_in_longturtle12(self):
        from rdflib import XSD
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal('1.5', datatype=XSD.decimal)))
        out = sg.serialize(format='longturtle12')
        assert '^^xsd:decimal' in out

    def test_turtle12_still_uses_bare_forms(self):
        # Confirms the two formats genuinely diverge, not just that
        # longturtle12 avoids the shorthand.
        sg = StarLayerGraph()
        sg.add((URIRef(EX + 's'), URIRef(EX + 'p'), Literal(True)))
        out = sg.serialize(format='turtle12')
        assert '^^xsd:boolean' not in out
        assert ' true' in out
