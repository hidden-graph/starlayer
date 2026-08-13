"""
Unit tests for starlayergraph.parsers.syntax.

Covers coerce_object, classify_statement, split_statements,
extract_fields, and expand_triple_set.
"""

import pytest
from rdflib import Literal
from rdflib.namespace import XSD
from starlayergraph.parsers.syntax import (
    coerce_object,
    classify_statement,
    split_statements,
    split_statements_with_lines,
    extract_fields,
    expand_triple_set,
)
from starlayergraph.parsers.errors import TurtleSyntaxError


class TestCoerceObject:
    """Numeric literals come back as a correctly-typed, lexical-form-
    preserving Literal, not a Python int/float - see coerce_object's own
    docstring: a Python numeric type can't tell INTEGER/DECIMAL/DOUBLE
    apart from the lexical shape alone (e.g. "123e0" is xsd:double despite
    having no decimal point), and converting through one would also
    silently canonicalize the lexical form (e.g. "04" -> "4")."""
    def test_true(self):      assert coerce_object('true') is True
    def test_false(self):     assert coerce_object('false') is False

    def test_integer(self):
        result = coerce_object('42')
        assert result.datatype == XSD.integer
        assert str(result) == '42'

    def test_negative(self):
        result = coerce_object('-5')
        assert result.datatype == XSD.integer
        assert str(result) == '-5'

    def test_positive(self):
        # Lexical form preserved exactly, including the leading "+" - not
        # normalized away even though "+3" and "3" are the same value.
        result = coerce_object('+3')
        assert result.datatype == XSD.integer
        assert str(result) == '+3'

    def test_float(self):
        result = coerce_object('3.14')
        assert result.datatype == XSD.decimal
        assert str(result) == '3.14'

    def test_float_exp(self):
        # Lexical form preserved exactly - not collapsed to the value's
        # canonical "150.0" form.
        result = coerce_object('1.5e2')
        assert result.datatype == XSD.double
        assert str(result) == '1.5e2'

    def test_integer_with_exponent_is_double(self):
        """"123e0" has no decimal point but does have an exponent - Turtle
        grammar makes that xsd:double, not xsd:decimal or xsd:integer."""
        result = coerce_object('123e0')
        assert result.datatype == XSD.double
        assert str(result) == '123e0'

    def test_leading_zero_lexical_form_preserved(self):
        result = coerce_object('04')
        assert result.datatype == XSD.integer
        assert str(result) == '04'

    def test_string(self):    assert coerce_object(':foo') == ':foo'
    def test_whitespace(self):
        result = coerce_object('  42  ')
        assert result.datatype == XSD.integer
        assert str(result) == '42'


class TestClassifyStatement:
    def test_at_prefix_lower(self):
        assert classify_statement('@prefix ex: <http://x/>') == 'prefix'

    def test_bare_prefix_upper(self):
        assert classify_statement('PREFIX ex: <http://x/>') == 'prefix'

    def test_at_base(self):
        assert classify_statement('@base <http://x/>') == 'base'

    def test_bare_base_upper(self):
        assert classify_statement('BASE <http://x/>') == 'base'

    def test_triple(self):
        assert classify_statement(':s :p :o .') == 'triple'

    def test_triple_with_iri_subject(self):
        assert classify_statement('<http://x/s> :p :o .') == 'triple'


class TestSplitStatements:
    def test_single_prefix(self):
        stmts = split_statements('@prefix ex: <http://example.org/>')
        assert len(stmts) == 1
        assert classify_statement(stmts[0]) == 'prefix'

    def test_two_triples(self):
        data = ':s :p :o .\n:a :b :c .\n'
        stmts = split_statements(data)
        assert len(stmts) == 2

    def test_prefix_then_triple(self):
        data = '@prefix ex: <http://example.org/>\nex:s ex:p ex:o .\n'
        stmts = split_statements(data)
        assert len(stmts) == 2
        assert classify_statement(stmts[0]) == 'prefix'
        assert classify_statement(stmts[1]) == 'triple'

    def test_multiline_triple(self):
        data = ':s\n    :p\n    :o .\n'
        stmts = split_statements(data)
        assert len(stmts) == 1
        assert classify_statement(stmts[0]) == 'triple'

    def test_annotation_statement(self):
        data = 'PREFIX : <http://example/>\n:s :p :o {| :ann :val |} .\n'
        stmts = split_statements(data)
        assert len(stmts) == 2

    def test_period_inside_string_not_split(self):
        data = ':s :p "hello.world" .\n'
        stmts = split_statements(data)
        assert len(stmts) == 1


class TestSameLineStatements:
    """Two or more statements crammed onto one physical line must still
    split correctly - previously a '.' only counted as a statement
    terminator when immediately followed by a newline, so anything after
    it on the same line got silently merged into the preceding statement
    and dropped (worst for a directive, whose regex-based field extractor
    only matches its own leading portion and ignores the rest)."""

    def test_two_triples_one_line(self):
        stmts = split_statements(':a :b :c . :d :e :f .')
        assert len(stmts) == 2
        assert classify_statement(stmts[0]) == 'triple'
        assert classify_statement(stmts[1]) == 'triple'

    def test_dotted_prefix_then_triple_one_line(self):
        stmts = split_statements('@prefix : <http://example.org/> . :a :knows :bob .')
        assert len(stmts) == 2
        assert classify_statement(stmts[0]) == 'prefix'
        assert classify_statement(stmts[1]) == 'triple'

    def test_multiple_dotted_prefixes_and_triples_one_line(self):
        data = ('@prefix : <http://example.org/> . '
                '@prefix ex: <http://example.com/> . '
                ':a :knows ex:bob . :a :likes ex:carol .')
        stmts = split_statements(data)
        assert len(stmts) == 4
        assert [classify_statement(s) for s in stmts] == ['prefix', 'prefix', 'triple', 'triple']

    def test_decimal_literal_not_split(self):
        """Guards the fix itself: a '.' terminates a statement unless
        immediately followed by a digit (the decimal point of a DECIMAL/
        DOUBLE literal like "3.14"), not "unless followed by a newline"."""
        stmts = split_statements(':a :b 3.14 .\n')
        assert len(stmts) == 1

    def test_decimal_literal_then_another_statement_same_line(self):
        stmts = split_statements(':a :b 3.14 . :c :d 5 .')
        assert len(stmts) == 2

    def test_dotless_prefix_still_works(self):
        """Regression guard: @prefix/@base/@version may omit the trailing
        '.' (existing, intentional leniency) - must still split correctly
        against the following statement on the next line."""
        data = '@prefix ex: <http://example.org/>\nex:s ex:p ex:o .\n'
        stmts = split_statements(data)
        assert len(stmts) == 2
        assert classify_statement(stmts[0]) == 'prefix'
        assert classify_statement(stmts[1]) == 'triple'

    def test_dot_inside_iri_with_dots_not_split(self):
        data = '@prefix ex: <http://example.com/path.with.dots#> . ex:a ex:b ex:c .'
        stmts = split_statements(data)
        assert len(stmts) == 2
        assert stmts[0] == '@prefix ex: <http://example.com/path.with.dots#> .'


class TestSplitStatementsWithLines:
    """split_statements_with_lines() - same split as split_statements(), plus
    each statement's approximate 1-based starting line number. Added for the
    2026-07-17 architectural review's "raise on malformed input" work; see
    TurtleSyntaxError and tests/unit/test_turtle_parser_errors.py."""

    def test_single_statement_line_one(self):
        stmts = split_statements_with_lines(':s :p :o .\n')
        assert stmts == [(':s :p :o .', 1)]

    def test_multiple_statements_line_numbers(self):
        data = ':s1 :p1 :o1 .\n:s2 :p2 :o2 .\n:s3 :p3 :o3 .\n'
        stmts = split_statements_with_lines(data)
        assert [line for _stmt, line in stmts] == [1, 2, 3]

    def test_prefix_then_triples_line_numbers(self):
        data = '@prefix : <http://example.org/>\n:s1 :p1 :o1 .\n:s2 :p2 :o2 .\n'
        stmts = split_statements_with_lines(data)
        assert [line for _stmt, line in stmts] == [1, 2, 3]

    def test_blank_lines_do_not_shift_line_numbers(self):
        # split_statements_with_lines() line numbers are relative to whatever
        # text it's given - StarLayerTurtleParser.parse() is responsible for
        # translating back to original-document line numbers when blank/
        # comment lines were stripped before calling this (see its line_map).
        data = ':s1 :p1 :o1 .\n\n:s2 :p2 :o2 .\n'
        stmts = split_statements_with_lines(data)
        assert [line for _stmt, line in stmts] == [1, 3]

    def test_multiline_triple_reports_start_line(self):
        data = ':s1 :p1 :o1 .\n:s2\n    :p2\n    :o2 .\n'
        stmts = split_statements_with_lines(data)
        assert stmts[1][1] == 2  # the multi-line triple starts on line 2

    def test_unclosed_bracket_at_end_of_document_raises(self):
        data = ':s1 :p1 :o1 .\n:s2 :p2 [ :a :b .\n'
        with pytest.raises(TurtleSyntaxError, match="unclosed '\\['"):
            split_statements_with_lines(data)

    def test_unterminated_string_at_end_of_document_raises(self):
        data = ':s1 :p1 :o1 .\n:s2 :p2 "unterminated .\n'
        with pytest.raises(TurtleSyntaxError, match='unterminated'):
            split_statements_with_lines(data)


class TestExtractFields:
    def test_prefix_at(self):
        fields = extract_fields('@prefix ex: <http://example.org/>', 'prefix')
        assert fields['prefix'] == 'ex'
        assert fields['iri'] == 'http://example.org/'

    def test_prefix_bare(self):
        fields = extract_fields('PREFIX ex: <http://example.org/>', 'prefix')
        assert fields['prefix'] == 'ex'

    def test_prefix_empty_local(self):
        fields = extract_fields('@prefix : <http://example.org/>', 'prefix')
        assert fields['prefix'] == ''

    def test_base(self):
        fields = extract_fields('@base <http://example.org/>', 'base')
        assert fields['iri'] == 'http://example.org/'

    def test_version_dotted_form(self):
        fields = extract_fields('@version "1.2" .', 'version')
        assert fields['version'] == '1.2'

    def test_version_bare_form(self):
        fields = extract_fields('VERSION "1.2"', 'version')
        assert fields['version'] == '1.2'

    def test_version_single_quoted(self):
        fields = extract_fields("@version '1.2-basic' .", 'version')
        assert fields['version'] == '1.2-basic'

    def test_version_basic_label(self):
        fields = extract_fields('VERSION "1.2-basic"', 'version')
        assert fields['version'] == '1.2-basic'

    def test_version_unquoted_rejected(self):
        """VersionSpecifier ::= STRING_LITERAL_QUOTE | STRING_LITERAL_SINGLE_QUOTE
        - a bare, unquoted value is not valid (W3C turtle12-version-bad-01/04)."""
        with pytest.raises(TurtleSyntaxError):
            extract_fields('VERSION 1.2', 'version')
        with pytest.raises(TurtleSyntaxError):
            extract_fields('@version 1.2 .', 'version')

    def test_version_triple_quoted_rejected(self):
        """The long/triple-quoted string forms are a different grammar
        production, not valid here (W3C turtle12-version-bad-02/03/05/06)."""
        with pytest.raises(TurtleSyntaxError):
            extract_fields('VERSION """1.2"""', 'version')
        with pytest.raises(TurtleSyntaxError):
            extract_fields("VERSION '''1.2'''", 'version')
        with pytest.raises(TurtleSyntaxError):
            extract_fields('@version """1.2""" .', 'version')

    def test_simple_triple(self):
        fields = extract_fields(':s :p :o .', 'triple', [0])
        ts = fields['triple_set']
        assert len(ts) == 1
        assert ts[0]['subject'] == ':s'
        assert ts[0]['predicate'] == ':p'
        assert ts[0]['object'] == ':o'

    def test_multiple_predicates(self):
        fields = extract_fields(':s :p :o ; :q :z .', 'triple', [0])
        ts = fields['triple_set']
        assert len(ts) == 2
        predicates = {t['predicate'] for t in ts}
        assert ':p' in predicates
        assert ':q' in predicates

    def test_multiple_objects(self):
        fields = extract_fields(':s :p :o , :o2 .', 'triple', [0])
        ts = fields['triple_set']
        assert len(ts) == 2
        objects = {t['object'] for t in ts}
        assert ':o' in objects
        assert ':o2' in objects

    def test_rdf_type_abbreviation(self):
        fields = extract_fields(':s a :Thing .', 'triple', [0])
        ts = fields['triple_set']
        assert ts[0]['predicate'] == 'a'

    def test_annotation_recorded(self):
        fields = extract_fields(':s :p :o {| :ann :val |} .', 'triple', [0])
        ts = fields['triple_set']
        assert ts[0].get('annotations') is not None

    def test_blank_node_subject_expanded(self):
        counter = [0]
        fields = extract_fields('[] :p :o .', 'triple', counter)
        ts = fields['triple_set']
        assert ts[0]['subject'].startswith('_:sl_')


class TestExpandTripleSet:
    def test_plain_triple_unchanged(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': ':o'}]
        result = expand_triple_set(ts, [0])
        assert result == ts

    def test_blank_node_object_expands(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '[ :q :z ]'}]
        result = expand_triple_set(ts, [0])
        assert len(result) > 1
        assert result[0]['object'].startswith('_:sl_')

    def test_blank_node_inner_triple_present(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '[ :q :z ]'}]
        result = expand_triple_set(ts, [0])
        bnode = result[0]['object']
        inner = [t for t in result if t['subject'] == bnode]
        assert len(inner) == 1
        assert inner[0]['predicate'] == ':q'

    def test_empty_collection_becomes_nil(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '()'}]
        result = expand_triple_set(ts, [0])
        assert len(result) == 1
        assert result[0]['object'] == 'rdf:nil'

    def test_single_element_collection(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '( :a )'}]
        result = expand_triple_set(ts, [0])
        predicates = {t['predicate'] for t in result}
        assert 'rdf:first' in predicates
        assert 'rdf:rest' in predicates
        rest_triples = [t for t in result if t['predicate'] == 'rdf:rest']
        assert rest_triples[-1]['object'] == 'rdf:nil'

    def test_two_element_collection(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '( :a :b )'}]
        result = expand_triple_set(ts, [0])
        first_triples = [t for t in result if t['predicate'] == 'rdf:first']
        assert len(first_triples) == 2

    def test_nested_blank_in_collection(self):
        ts = [{'subject': ':s', 'predicate': ':p', 'object': '( [ :q :z ] )'}]
        result = expand_triple_set(ts, [0])
        predicates = {t['predicate'] for t in result}
        assert 'rdf:first' in predicates
        assert ':q' in predicates
