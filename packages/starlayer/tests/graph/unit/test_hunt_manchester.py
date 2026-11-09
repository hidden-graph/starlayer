"""Regression tests for the Manchester parser / serializer bug hunt.

The oracle for the serializer is its own documented bar: ``parse_manchester`` output written by
``serialize_manchester`` and parsed again is isomorphic, or the writer raises ``ValueError``.
"""

import pyoxigraph as ox
import pytest
from starlayer.graph.compare import isomorphic
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.parsers._ox_terms import OWL
from starlayer.graph.parsers.errors import ManchesterSyntaxError
from starlayer.graph.parsers.manchester_parser import parse_manchester
from starlayer.graph.serializers.manchester import serialize_manchester

P = 'Prefix: : <http://e/o#>\nPrefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n'


def _graph(triples):
    g = StarLayerGraph()
    g.extend(triples)
    return g


def _round_trip(text, prefix=P):
    g = _graph(parse_manchester(prefix + text))
    out = serialize_manchester(g)
    return g, _graph(parse_manchester(out)), out


def _assert_round_trip(text, prefix=P):
    g, g2, out = _round_trip(text, prefix)
    assert isomorphic(g, g2), f'{len(g)} triples in, {len(g2)} after:\n{out}'


# --- parser ------------------------------------------------------------------------------------

@pytest.mark.parametrize('body', ['p value ' + '9' * 5000, 'p min ' + '9' * 5000 + ' B'])
def test_huge_integer_is_a_literal_or_a_syntax_error(body):
    try:
        parse_manchester('Prefix: : <http://e/>\nClass: A\n SubClassOf: ' + body)
    except ManchesterSyntaxError:
        pass


def test_huge_integer_value_keeps_all_digits():
    ts = parse_manchester('Prefix: : <http://e/>\nClass: A\n SubClassOf: p value ' + '9' * 5000)
    assert any(isinstance(o, ox.Literal) and o.value == '9' * 5000 for _, _, o in ts)


@pytest.mark.parametrize('word, lexical', [('+007', '7'), ('-0', '0'), ('-012', '-12'), ('0', '0')])
def test_integer_lexical_form_is_canonical(word, lexical):
    ts = parse_manchester('Prefix: : <http://e/>\nClass: A\n SubClassOf: p value ' + word)
    assert any(isinstance(o, ox.Literal) and o.value == lexical for _, _, o in ts)


@pytest.mark.parametrize('digit', ['²', '³', '٣'])
def test_non_ascii_digit_cardinality_is_a_syntax_error(digit):
    with pytest.raises(ManchesterSyntaxError):
        parse_manchester(f'Prefix: : <http://e/>\nClass: :A SubClassOf: :p min {digit} :B\n')


def test_error_line_after_multiline_string():
    with pytest.raises(ManchesterSyntaxError) as exc:
        parse_manchester('Prefix: : <http://e/>\nClass: A\n SubClassOf: p value "a\nb\nc"\n Foo: C')
    assert exc.value.line == 6


def test_name_resolution_error_reports_the_offending_line():
    src = 'Prefix: : <http://ex.org/>\nClass: A\n    SubClassOf: nope:B\nClass: C\n'
    with pytest.raises(ManchesterSyntaxError) as exc:
        parse_manchester(src)
    assert exc.value.line == 3
    assert 'nope:B' in str(exc.value)


def test_negative_fact_keeps_annotation_of_annotation():
    src = P + 'Individual: :a Facts: Annotations: Annotations: :x "n" :y "v" %s :p :b\n'
    pos = parse_manchester(src % '')
    neg = parse_manchester(src % 'not')

    def has(ts):
        return (any(p == OWL.annotatedProperty and str(o).endswith('/y>') or str(o).endswith('#y>')
                    for _, p, o in ts) and any(str(o) == '"n"' for _, _, o in ts))
    assert has(pos)
    assert has(neg)
