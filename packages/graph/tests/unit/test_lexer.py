"""
Unit tests for starlayergraph.parsers.lexer.

Tests cover every token form that next_token must handle, plus the
annotation-block and object-annotation helpers.
"""

import pytest
from starlayergraph.parsers.errors import TurtleSyntaxError
from starlayergraph.parsers.lexer import (
    consume_annotation_block,
    next_token,
    split_obj_and_annotations,
)


class TestNextTokenEmpty:
    def test_empty_string_returns_none(self):
        assert next_token('') == (None, '')


class TestNextTokenIri:
    def test_simple_iri(self):
        tok, rest = next_token('<http://example.org/foo> bar')
        assert tok == '<http://example.org/foo>'
        assert rest == 'bar'

    def test_iri_with_no_trailing(self):
        tok, rest = next_token('<http://example.org/>')
        assert tok == '<http://example.org/>'
        assert rest == ''


class TestNextTokenPlainToken:
    def test_prefixed_name(self):
        tok, rest = next_token('ex:alice :p')
        assert tok == 'ex:alice'
        assert rest == ':p'

    def test_bare_prefix(self):
        tok, rest = next_token(':p :o')
        assert tok == ':p'
        assert rest == ':o'

    def test_blank_node(self):
        tok, rest = next_token('_:b0 rest')
        assert tok == '_:b0'
        assert rest == 'rest'

    def test_rdf_type_a(self):
        tok, rest = next_token('a ex:Thing')
        assert tok == 'a'
        assert rest == 'ex:Thing'


class TestNextTokenQuotedTripleTerm:
    def test_basic_triple_term(self):
        tok, rest = next_token('<<( :s :p :o )>> :q')
        assert tok == '<<( :s :p :o )>>'
        assert rest == ':q'

    def test_triple_term_with_iri(self):
        tok, rest = next_token('<<( <http://example/s> <http://example/p> <http://example/o> )>>')
        assert tok.startswith('<<(')
        assert tok.endswith(')>>')
        assert rest == ''

    def test_nested_triple_term(self):
        tok, rest = next_token('<<( <<( :a :b :c )>> :p :o )>> rest')
        assert tok == '<<( <<( :a :b :c )>> :p :o )>>'
        assert rest == 'rest'

    def test_triple_term_with_space_before_paren(self):
        tok, rest = next_token('<< ( :s :p :o ) >> :q')
        assert tok == '<< ( :s :p :o ) >>'
        assert rest == ':q'


class TestNextTokenBareStopCharAtStart:
    """A stop char with no dedicated branch (bare '{'/'}'/')'/']'/','/';' at
    the very start of the scan) previously fell through to the bare-token
    loop, whose while-condition is false on the first character - returning
    an *empty* token ('', s) silently instead of raising. That's
    indistinguishable, to every caller, from "there was nothing here" -
    concretely, an N3-style "{ :s :p :o } :q :r ." formula-as-subject
    statement parsed with zero errors and produced zero triples. See
    test_turtle_parser_errors.py for the end-to-end reproduction of that bug."""

    @pytest.mark.parametrize('s', ['{ :s :p :o } rest', '}', ')', ']', ',', ';'])
    def test_bare_stop_char_raises(self, s):
        with pytest.raises(TurtleSyntaxError, match='unexpected'):
            next_token(s)

    def test_error_message_names_the_character(self):
        with pytest.raises(TurtleSyntaxError) as excinfo:
            next_token('{ :s :p :o }')
        assert repr('{') in str(excinfo.value.why)

    def test_annotation_block_opener_unaffected(self):
        # '{|' is a real, valid token form, but it's consumed by
        # consume_annotation_block - every real caller (e.g.
        # split_obj_and_annotations) checks rest.startswith('{|') and routes
        # there *before* ever calling next_token, so next_token itself is
        # never supposed to receive '{|...' directly. Confirm the real,
        # caller-level entry point still parses annotation blocks correctly
        # after this fix (next_token raising on a bare '{' it's never
        # actually asked to handle doesn't regress the real path).
        obj, anns = split_obj_and_annotations(':o {| :a :b |}')
        assert obj == ':o'
        assert len(anns) == 1


class TestNextTokenReificationShorthand:
    def test_basic_reification(self):
        tok, rest = next_token('<< :s :p :o >> :q')
        assert tok == '<< :s :p :o >>'
        assert rest == ':q'

    def test_reification_with_iri_subject(self):
        tok, rest = next_token('<< <http://example/s> :p :o >> rest')
        assert tok.startswith('<<')
        assert tok.endswith('>>')


class TestNextTokenStrings:
    def test_double_quoted(self):
        tok, rest = next_token('"hello" :p')
        assert tok == '"hello"'
        assert rest == ':p'

    def test_single_quoted(self):
        tok, rest = next_token("'hello' :p")
        assert tok == "'hello'"
        assert rest == ':p'

    def test_triple_double_quoted(self):
        tok, rest = next_token('"""hello world""" :p')
        assert tok == '"""hello world"""'
        assert rest == ':p'

    def test_triple_single_quoted(self):
        tok, rest = next_token("'''hello world''' :p")
        assert tok == "'''hello world'''"
        assert rest == ':p'

    def test_string_with_escape(self):
        tok, rest = next_token(r'"say \"hi\"" :p')
        assert tok == r'"say \"hi\""'
        assert rest == ':p'

    def test_string_with_internal_angle_bracket(self):
        tok, rest = next_token('"a < b" :p')
        assert tok == '"a < b"'
        assert rest == ':p'


class TestNextTokenBrackets:
    def test_empty_blank_node(self):
        tok, rest = next_token('[] :p')
        assert tok == '[]'
        assert rest == ':p'

    def test_blank_node_with_content(self):
        tok, rest = next_token('[ :p :o ] :q')
        assert tok == '[ :p :o ]'
        assert rest == ':q'

    def test_nested_blank_node(self):
        tok, rest = next_token('[ :p [ :q :z ] ] rest')
        assert tok == '[ :p [ :q :z ] ]'
        assert rest == 'rest'

    def test_empty_collection(self):
        tok, rest = next_token('() :p')
        assert tok == '()'
        assert rest == ':p'

    def test_collection_with_elements(self):
        tok, rest = next_token('( :a :b :c ) :q')
        assert tok == '( :a :b :c )'
        assert rest == ':q'


class TestNextTokenUnterminated:
    """next_token() must raise TurtleSyntaxError, not silently return the
    rest of the text as one token, when a closing delimiter is never found -
    see docs/future_enhancements.md and the 2026-07-17 architectural review."""

    def test_unterminated_triple_term(self):
        with pytest.raises(TurtleSyntaxError, match='unterminated <<\\( \\)>> triple term'):
            next_token('<<( :s :p :o rest')

    def test_unterminated_reification(self):
        with pytest.raises(TurtleSyntaxError, match='unterminated << >> reification'):
            next_token('<< :s :p :o rest')

    def test_unterminated_iri(self):
        with pytest.raises(TurtleSyntaxError, match="unterminated IRI"):
            next_token('<http://example.org/unterminated')

    def test_unterminated_triple_quoted_string(self):
        with pytest.raises(TurtleSyntaxError, match='unterminated'):
            next_token('"""unterminated triple quote')

    def test_unterminated_single_quoted_string(self):
        with pytest.raises(TurtleSyntaxError, match='unterminated'):
            next_token('"unterminated single quote')

    def test_unclosed_blank_node_property_list(self):
        with pytest.raises(TurtleSyntaxError, match="unclosed '\\['"):
            next_token('[ :p :o rest')

    def test_unclosed_collection(self):
        with pytest.raises(TurtleSyntaxError, match="unclosed '\\('"):
            next_token('( :a :b rest')


class TestConsumeAnnotationBlock:
    def test_simple(self):
        body, rest = consume_annotation_block('{| :ann :val |}')
        assert body == ':ann :val'
        assert rest == ''

    def test_with_trailing_period(self):
        body, rest = consume_annotation_block('{| :ann :val |} .')
        assert body == ':ann :val'
        assert rest.strip() == '.'

    def test_multiple_predicates(self):
        body, rest = consume_annotation_block('{| :a :b ; :c :d |}')
        assert ':a :b' in body
        assert ':c :d' in body
        assert rest == ''

    def test_nested_block(self):
        body, rest = consume_annotation_block('{| :a [ :b :c ] |}')
        assert ':a' in body
        assert rest == ''


class TestSplitObjAndAnnotations:
    def test_plain_object(self):
        obj, anns = split_obj_and_annotations(':o')
        assert obj == ':o'
        assert anns == []

    def test_iri_object(self):
        obj, anns = split_obj_and_annotations('<http://example.org/x>')
        assert obj == '<http://example.org/x>'
        assert anns == []

    def test_typed_literal(self):
        obj, anns = split_obj_and_annotations('"2024"^^xsd:date')
        assert obj == '"2024"^^xsd:date'
        assert anns == []

    def test_typed_literal_bracketed_iri_datatype(self):
        # '^^<full-iri>' (as opposed to '^^prefixed:name') - ordinary,
        # common Turtle syntax (e.g. canonical/no-prefixes documents), but
        # previously broken: next_token()'s bare-token scanner treats '<'
        # as a stop char, so calling it on the whole '^^<...>' string
        # stopped right after '^^', leaving the IRI as unconsumed trailing
        # content. Confirmed live via a real TurtleSyntaxError before this
        # fix, for input as ordinary as
        # '"hi"^^<http://www.w3.org/2001/XMLSchema#string>'.
        obj, anns = split_obj_and_annotations('"2024"^^<http://www.w3.org/2001/XMLSchema#date>')
        assert obj == '"2024"^^<http://www.w3.org/2001/XMLSchema#date>'
        assert anns == []

    def test_lang_literal(self):
        obj, anns = split_obj_and_annotations('"hello"@en')
        assert obj == '"hello"@en'
        assert anns == []

    def test_anonymous_annotation(self):
        obj, anns = split_obj_and_annotations(':o {| :ann :val |}')
        assert obj == ':o'
        assert len(anns) == 1
        reifier, body = anns[0]
        assert reifier is None
        assert ':ann :val' in body

    def test_explicit_reifier_with_body(self):
        obj, anns = split_obj_and_annotations(':o ~ :r {| :ann :val |}')
        assert obj == ':o'
        assert len(anns) == 1
        reifier, body = anns[0]
        assert reifier == ':r'
        assert ':ann :val' in body

    def test_explicit_reifier_no_body(self):
        obj, anns = split_obj_and_annotations(':o ~ :r')
        assert obj == ':o'
        assert len(anns) == 1
        reifier, body = anns[0]
        assert reifier == ':r'
        assert body is None

    def test_multiple_annotations(self):
        obj, anns = split_obj_and_annotations(':o {| :a :b |} {| :c :d |}')
        assert obj == ':o'
        assert len(anns) == 2
