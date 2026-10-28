"""Parser and serializer remainders of GitHub issues #73, #93, #99 and #128 (round 4), plus the TAB side finding.

Where plain rdflib can act as an oracle (Turtle 1.1 / N-Triples text), the test also checks that rdflib rejects the same input;
a case where rdflib is lenient is marked, and the grammar (Turtle 1.2 / N-Triples 1.2 / TriG 1.2) is the arbiter.
"""

import pytest
import rdflib
from rdflib import Literal, URIRef
from starlayer import StarLayerDataset, StarLayerGraph
from starlayer.graph import TripleTerm
from starlayer.graph.parsers.errors import Turtle12SyntaxError

REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


def _turtle(text):
    g = StarLayerGraph()
    g.parse(data=text, format='turtle12')
    return g


def _turtle_ds(text):
    d = StarLayerDataset()
    d.parse(data=text, format='turtle12')
    return d


# ---------------------------------------------------------------------------
# #93: a reifier with no identifier is a fresh blank node
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected', [
    ('<urn:s> <urn:p> <urn:o> ~ .', 2),
    ('<urn:s> <urn:p> <urn:o> ~ ; <urn:z> 1 .', 3),
    ('<urn:s> <urn:p> <urn:o> ~ , <urn:g> .', 3),
    ('<urn:s> <urn:p> <urn:o> ~ [] .', 2),
    ('<urn:s> <urn:p> <urn:o> ~ [ ] .', 2),
    ('<urn:s> <urn:p> <urn:o> ~ [] {| <urn:x> 1 |} .', 3),
    ('<urn:s> <urn:p> <urn:o> ~ {| <urn:x> 1 |} .', 3),
])
def test_reifier_without_identifier_adds_a_reifies_triple(text, expected):
    g = _turtle(text)
    assert len(g) == expected
    assert len(list(g.triples((None, REIFIES, None)))) == 1


def test_reifier_anon_is_a_fresh_blank_node_in_a_reified_triple():
    g = _turtle('<< <urn:s> <urn:p> <urn:o> ~ [] >> <urn:q> 1 .')
    (reifier, _, tt), = g.triples((None, REIFIES, None))
    assert tt == TripleTerm(URIRef('urn:s'), URIRef('urn:p'), URIRef('urn:o'))
    assert (reifier, URIRef('urn:q'), Literal(1)) in g


def test_a_reified_triple_alone_is_a_statement():
    g = _turtle('<< <urn:s> <urn:p> <urn:o> >> .')  # triples ::= reifiedTriple predicateObjectList?
    assert len(list(g.triples((None, REIFIES, None)))) == 1


# ---------------------------------------------------------------------------
# #128 and #73: Turtle syntax that the grammar rejects
# ---------------------------------------------------------------------------

# (text, does rdflib's Turtle parser reject it too? A False is rdflib being lenient; the grammar is the arbiter.)
BAD_TURTLE = [
    ('<urn:a> <urn:p> .', True),                                   # #128 predicate with no object
    ('<urn:a> <urn:p> ; <urn:q> <urn:o> .', True),                 # same, in the middle
    ('<urn:a> ; <urn:p> <urn:o> .', False),                         # ';' straight after the subject
    ('<urn:a> <urn:p> <urn:o> , .', True),                         # empty object
    ('<urn:a> <urn:p> , <urn:o> .', True),
    ('<urn:a> .', False),                                           # subject only
    ('~', True),                                                   # bare reifier
    ('<urn:a> <urn:p> <urn:o>', True),                             # missing final dot
    ('<urn:a> <urn:p> <urn:o> . .', True),                         # doubled dot
    ('<urn:a> <urn:p> "x"@en--ltr--rtl .', False),                 # rdflib has no direction support
    ('<urn:a> <urn:p> "x"@en--LTR .', False),
    ('<urn:a> <urn:p> "\\u00ZZ" .', False),                         # bad \u escape
    ('<urn:a> <urn:p> "\\q" .', True),                             # unknown escape
    ('<urn:a> <urn:p> "a\nb" .', True),                            # raw newline in a short string
    ('@prefix a: <urn:a:>', True),                                 # @prefix needs its dot
    ('@prefix a <urn:a:> .', True),
    ('<http://e/a b> <urn:p> <urn:o> .', False),                   # rdflib only warns about a space in an IRI
    ('<urn:a> _:b <urn:o> .', False),                               # blank node predicate
    ('"x" <urn:p> <urn:o> .', False),                               # literal subject
    ('@prefix e: <urn:e:> . <urn:a> <urn:p> e:b%zz .', False),     # bad percent escape
    ('<urn:a> <urn:p> "x"^^<http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString> .', False),
]


@pytest.mark.parametrize('text,rdflib_rejects', BAD_TURTLE)
def test_invalid_turtle_is_a_syntax_error(text, rdflib_rejects):
    with pytest.raises(Turtle12SyntaxError):
        _turtle(text)
    if rdflib_rejects:
        with pytest.raises(Exception):  # noqa: B017 - rdflib raises various types
            rdflib.Graph().parse(data=text, format='turtle')


@pytest.mark.parametrize('text', [t for t, _ in BAD_TURTLE if t not in ('<urn:a> <urn:p> <urn:o>',) and 'e:' not in t])
def test_invalid_turtle_is_a_syntax_error_through_a_dataset_too(text):
    with pytest.raises((Turtle12SyntaxError, ValueError)):
        _turtle_ds(text)


def test_a_missing_final_dot_is_an_error_in_a_dataset_turtle_document_but_not_in_a_trig_block():
    with pytest.raises(Turtle12SyntaxError):
        _turtle_ds('<urn:a> <urn:p> <urn:o>')
    d = StarLayerDataset()
    d.parse(data='<urn:g> { <urn:a> <urn:p> <urn:o> }', format='trig12')  # TriG: the last triple of a block may omit '.'
    assert len(list(d.quads())) == 1


@pytest.mark.parametrize('text,count', [
    ('<urn:a> <urn:p> <urn:o> ; .', 1),                            # a trailing ';' is allowed
    ('<urn:a> <urn:p> <urn:o> ; ; <urn:q> <urn:r> .', 2),
    ('@prefix e: <urn:e:> . <urn:a> <urn:p> e:o: .', 1),           # ':' may end a local name
    ('@prefix e: <urn:e:> . <urn:a> <urn:p> e:a\\%b .', 1),
    ('<urn:a> <urn:p> <urn:x,y> , <urn:z;w> .', 2),                # ',' and ';' inside an IRI are not separators
    ('<urn:a> <urn:p> "x"@en--ltr .', 1),
    ('<urn:a> <urn:p> """a\nb""" .', 1),
])
def test_valid_turtle_still_parses(text, count):
    assert len(_turtle(text)) == count


# ---------------------------------------------------------------------------
# #73: stacked directives and directive-like names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text', [
    'PREFIX a: <urn:a:> PREFIX b: <urn:b:> a:x b:p a:o .',
    'BASE <http://x/> PREFIX a: <urn:a:> BASE <http://y/> a:x a:p <o> .',
    '@prefix a: <urn:a:> . @prefix b: <urn:b:> . a:x b:p a:o .',
    'PREFIX a: <urn:a:> @prefix b: <urn:b:> . a:x b:p a:o .',
    '<urn:s> <urn:p> <urn:o> . PREFIX a: <urn:a:> a:x a:p a:o .',
])
def test_several_directives_on_one_line(text):
    g = _turtle(text)
    assert len(g) >= 1
    assert any(str(s) in ('urn:a:x', 'urn:s') for s, _, _ in g)
    assert len(rdflib.Graph().parse(data=text, format='turtle')) == len(g)  # rdflib agrees on the triples


def test_stacked_directives_resolve_in_order():
    g = _turtle('BASE <http://x/> BASE <http://y/> <a> <p> <o> .')
    assert (URIRef('http://y/a'), URIRef('http://y/p'), URIRef('http://y/o')) in g


@pytest.mark.parametrize('keyword', ['base', 'prefix', 'version', 'BASE', 'Version'])
def test_a_prefix_named_like_a_directive_is_not_a_directive(keyword):
    text = f'@prefix {keyword}: <urn:k:> .\n{keyword}:x {keyword}:p {keyword}:o .\n'
    assert (URIRef('urn:k:x'), URIRef('urn:k:p'), URIRef('urn:k:o')) in _turtle(text)
    assert len(_turtle_ds(text)) == 1


def test_a_multi_line_statement_whose_line_starts_with_a_directive_word_is_not_split():
    g = _turtle('@prefix base: <urn:k:> .\n<urn:a> <urn:p>\nbase:x ,\nbase:y .\n')
    assert len(g) == 2


# ---------------------------------------------------------------------------
# #73: language tags with direction
# ---------------------------------------------------------------------------

def test_two_direction_suffixes_are_rejected_in_turtle_and_ntriples():
    with pytest.raises(Turtle12SyntaxError):
        _turtle('<urn:a> <urn:p> "x"@en--ltr--rtl .')
    with pytest.raises(ValueError):
        StarLayerGraph().parse(data='<urn:a> <urn:p> "x"@en--ltr--rtl .\n', format='nt12')


def test_a_direction_must_be_lower_case_in_ntriples_as_in_turtle():
    with pytest.raises(ValueError):
        StarLayerGraph().parse(data='<urn:a> <urn:p> "x"@en--LTR .\n', format='nt12')


def test_a_bad_escape_is_the_parsers_own_error_not_a_bare_value_error():
    with pytest.raises(Turtle12SyntaxError):
        _turtle('<urn:a> <urn:p> "\\u00ZZ" .')
    with pytest.raises(Turtle12SyntaxError):
        _turtle('<urn:a> <urn:p> "x"@en--LTR .')


# ---------------------------------------------------------------------------
# #73 / #99: N-Triples and N-Quads
# ---------------------------------------------------------------------------

BAD_NT = [
    ('<urn:a> <urn:p> <urn:o> . junk', True),
    ('<urn:a> <urn:p> <urn:o> .<urn:a> <urn:p> <urn:d> .', True),
    ('<urn:a> <urn:p> <urn:o>', True),
    ('<a> <urn:p> <urn:o> .', False),                       # rdflib's nt parser resolves relative IRIs
    ('<urn:a> <urn:p> "a\\x" .', False),
    ('<urn:a> <urn:p> "x\\ud800" .', False),
    ('<urn:a> <urn:p> "x\\u00ZZ" .', False),
    ('<ur n:a> <urn:p> <urn:o> .', False),
    ('"x" <urn:p> <urn:o> .', False),
    ('<urn:a> _:b <urn:o> .', False),
    ('<< <urn:a> <urn:b> <urn:c> >> <urn:p> <urn:o> .', False),
    ('<urn:a> <urn:p> "x"^^<http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString> .', False),
    ('<urn:a> <urn:p> <<( <urn:s> <urn:p> <urn:o> <urn:x> )>> .', False),
]


@pytest.mark.parametrize('text,rdflib_rejects', BAD_NT)
def test_invalid_ntriples_is_an_error(text, rdflib_rejects):
    with pytest.raises(ValueError):
        StarLayerGraph().parse(data=text + '\n', format='nt12')
    if rdflib_rejects:
        with pytest.raises(Exception):  # noqa: B017 - rdflib raises various types
            rdflib.Graph().parse(data=text + '\n', format='nt')


@pytest.mark.parametrize('text', [
    '<urn:a> <urn:p> <urn:o> <urn:g> <urn:h> .',               # a fifth term used to be dropped silently
    '<urn:a> <urn:p> <urn:o> "g" .',                           # a literal is not a graph label
    '<urn:a> <urn:p> <<( ex:s <urn:p> <urn:o> )>> <urn:g> .',  # a prefixed name inside a triple term
    '<urn:a> <urn:p> <urn:o> <urn:g>',
])
def test_invalid_nquads_is_an_error(text):
    with pytest.raises(ValueError):
        StarLayerGraph().parse(data=text + '\n', format='nq12')
    with pytest.raises(ValueError):
        StarLayerDataset().parse(data=text + '\n', format='nq12')


def test_a_literal_graph_label_is_rejected_by_rdflib_too():
    with pytest.raises(Exception):  # noqa: B017 - rdflib raises various types
        rdflib.Dataset().parse(data='<urn:a> <urn:p> <urn:o> "g" .\n', format='nquads')


@pytest.mark.parametrize('text', [
    '<urn:a> <urn:p> <urn:o> . # a comment',
    '<urn:a> <urn:p> "it\\\'s" .',
    '_:a.b <urn:p> _:c .',
    '<urn:a> <urn:p> "x"@en-GB--rtl .',
    '<urn:a> <urn:p> <<( <urn:s> <urn:p> "o"@en )>> .',
])
def test_valid_ntriples_still_parses(text):
    assert len(StarLayerGraph().parse(data=text + '\n', format='nt12')) == 1


# ---------------------------------------------------------------------------
# #99: empty named graphs and JSON-LD
# ---------------------------------------------------------------------------

def _graph_names(ds):
    return sorted(str(g.identifier) for g in ds.graphs() if str(g.identifier) != 'urn:x-rdflib:default')


@pytest.mark.parametrize('text', ['GRAPH <urn:g> { }', '<urn:g> { }', '@prefix : <urn:> . GRAPH :g { }'])
def test_an_empty_named_graph_block_is_a_graph_of_the_dataset(text):
    d = StarLayerDataset()
    d.parse(data=text, format='trig12')
    assert _graph_names(d) == ['urn:g']


@pytest.mark.parametrize('fmt', ['trig12', 'trix12'])
def test_an_empty_named_graph_survives_a_round_trip(fmt):
    d = StarLayerDataset()
    d.graph(URIRef('urn:empty'))
    d.graph(URIRef('urn:full')).add((URIRef('urn:a'), URIRef('urn:p'), URIRef('urn:o')))
    text = d.serialize(format=fmt)
    back = StarLayerDataset()
    back.parse(data=text, format=fmt)
    assert _graph_names(back) == ['urn:empty', 'urn:full']
    assert len(list(back.quads())) == 1


def test_json_ld_of_a_dataset_writes_triple_terms_not_null():
    tt = TripleTerm(URIRef('urn:a'), URIRef('urn:b'), URIRef('urn:c'))
    d = StarLayerDataset()
    d.graph(URIRef('urn:g1')).add((URIRef('urn:s'), URIRef('urn:p'), tt))
    out = d.serialize(format='json-ld')
    assert 'null' not in out
    assert 'propositionFormSubject' in out  # RDF 1.2 Interoperability basic encoding, as StarLayerGraph writes
    plain = rdflib.Dataset()
    plain.parse(data=out, format='json-ld')
    assert len(plain) == 5  # s p _:b ; _:b a PropositionForm ; its subject, predicate and object


def test_json_ld_of_a_graph_with_a_triple_term_round_trips():
    tt = TripleTerm(URIRef('urn:a'), URIRef('urn:b'), URIRef('urn:c'))
    g = StarLayerGraph()
    g.add((URIRef('urn:s'), URIRef('urn:p'), tt))
    back = StarLayerGraph()
    back.parse(data=g.serialize(format='json-ld'), format='json-ld')
    assert g.isomorphic(back)


# ---------------------------------------------------------------------------
# side finding: a raw TAB in a SPARQL string literal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('query', [
    'SELECT ("a\tb" AS ?x) WHERE {}',
    'SELECT ("""a\tb""" AS ?x) WHERE {}',
    "SELECT ('a\tb' AS ?x) WHERE {}",
    'SELECT\t("a\tb"\tAS\t?x)\tWHERE\t{}',
])
def test_a_raw_tab_in_a_query_string_literal_is_kept(query):
    (row,) = list(StarLayerGraph().query(query))
    assert str(row[0]) == 'a\tb'


def test_a_raw_tab_in_an_update_string_literal_is_kept():
    g = StarLayerGraph()
    g.update('INSERT DATA { <urn:a> <urn:p> "a\tb" }')
    assert str(next(iter(g.objects()))) == 'a\tb'
