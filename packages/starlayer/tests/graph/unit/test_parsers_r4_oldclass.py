"""Parser and serializer remainders of GitHub issues #73, #93, #99 and #128 (round 4), plus the TAB side finding.

Where plain rdflib can act as an oracle (Turtle 1.1 / N-Triples text), the test also checks that rdflib rejects the same input;
a case where rdflib is lenient is marked, and the grammar (Turtle 1.2 / N-Triples 1.2 / TriG 1.2) is the arbiter.
"""

import pytest
import rdflib
from rdflib import Literal, URIRef
from starlayer import StarLayerDataset, StarLayerGraph
from starlayer.graph import TripleTerm

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










# ---------------------------------------------------------------------------
# #73: stacked directives and directive-like names
# ---------------------------------------------------------------------------









# ---------------------------------------------------------------------------
# #73: language tags with direction
# ---------------------------------------------------------------------------







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


@pytest.mark.parametrize('fmt', ['trig12'])
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



