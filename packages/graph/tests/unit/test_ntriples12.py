"""Unit tests for starlayergraph.parsers.ntriples12.

Minimal coverage for the N-Triples 1.2 parser's own string-escape handling -
previously had no dedicated test file at all.
"""

from rdflib import URIRef

from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

EX = 'http://example.org/'


def test_form_feed_and_backspace_escapes_decode():
    # \f (form feed, U+000C) and \b (backspace, U+0008) are both valid
    # N-Triples ECHAR escapes (grammar: '\' [tbnrf"'\]) - _unescape_nt() only
    # handled n/r/t plus the quote/backslash escapes, silently leaving \f/\b
    # as a literal backslash followed by the letter instead of the control
    # character. Same bug class as starlayergraph.parsers.turtle_parser's
    # _unescape() (see test_turtle_parser.py's
    # test_form_feed_and_backspace_escapes_decode), fixed the same way.
    g = StarLayerGraph()
    g.parse(
        data=(
            f'<{EX}s> <{EX}p> "a\\fb" .\n'
            f'<{EX}s> <{EX}q> "a\\bb" .\n'
        ),
        format='nt12',
    )
    p_value = next(iter(g.objects(URIRef(EX + 's'), URIRef(EX + 'p'))))
    q_value = next(iter(g.objects(URIRef(EX + 's'), URIRef(EX + 'q'))))
    assert str(p_value) == 'a\fb'
    assert str(q_value) == 'a\bb'
