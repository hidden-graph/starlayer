"""
End-to-end tests: StarLayerTurtleParser (via StarLayerGraph.parse(format='turtle12'))
must raise TurtleSyntaxError on malformed Turtle 1.2 input, in line with how
rdflib's own Turtle parser (rdflib.plugins.parsers.notation3.BadSyntax) reacts
to the same malformed input - confirmed directly against rdflib during the
2026-07-17 architectural review, which is what prompted this fix. Previously
this parser silently accepted malformed input and produced wrong data instead
of raising; see docs/future_enhancements.md for the write-up.
"""

import pytest

from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.parsers.errors import TurtleSyntaxError


def _parse(data: str):
    g = StarLayerGraph()
    g.parse(data=data, format='turtle12')
    return g


class TestWellFormedInputStillParses:
    """Sanity check: tightening error handling must not reject valid input."""

    def test_simple_triple(self):
        g = _parse('@prefix : <http://example.org/> .\n:s :p :o .\n')
        assert len(g) == 1

    def test_triple_term(self):
        g = _parse(
            '@prefix : <http://example.org/> .\n'
            ':stmt rdf:reifies <<( :bob :knows :carol )>> .\n'
        )
        assert len(g) > 0


class TestMalformedTokens:
    def test_garbage_object_token_raises(self):
        # The exact motivating case from the 2026-07-17 review: a stray,
        # unquoted, colonless token is not valid Turtle in any position -
        # rdflib's own parser rejects the same input with BadSyntax.
        data = '@prefix : <http://example.org/> .\n:s :p totally!bogus$$token .\n'
        with pytest.raises(TurtleSyntaxError, match='unrecognized term'):
            _parse(data)

    def test_garbage_token_reports_correct_line(self):
        data = (
            '@prefix : <http://example.org/> .\n'
            ':s1 :p1 :o1 .\n'
            ':s :p totally!bogus$$token .\n'
            ':s2 :p2 :o2 .\n'
        )
        with pytest.raises(TurtleSyntaxError) as excinfo:
            _parse(data)
        assert excinfo.value.line == 3


class TestUnterminatedForms:
    def test_unterminated_string_raises(self):
        data = '@prefix : <http://example.org/> .\n:s :p "unterminated .\n'
        with pytest.raises(TurtleSyntaxError, match='unterminated'):
            _parse(data)

    def test_unterminated_triple_quoted_string_raises(self):
        data = '@prefix : <http://example.org/> .\n:s :p """unterminated .\n'
        with pytest.raises(TurtleSyntaxError, match='unterminated'):
            _parse(data)

    def test_unclosed_triple_term_raises(self):
        # syntax.py's statement-splitter tracks '<' depth for its own
        # statement-boundary detection (so a '.' inside an unclosed <...>
        # doesn't prematurely end a statement) and catches this at
        # end-of-document before the lexer layer gets a chance to - still a
        # TurtleSyntaxError with a good line number, just phrased as
        # "unclosed '<'" rather than the lexer's own "unterminated <<( )>>".
        data = '@prefix : <http://example.org/> .\n:s :p <<( :a :b :c .\n'
        with pytest.raises(TurtleSyntaxError, match='unclosed'):
            _parse(data)

    def test_unclosed_blank_node_property_list_raises(self):
        data = '@prefix : <http://example.org/> .\n:s :p [ :a :b .\n'
        with pytest.raises(TurtleSyntaxError, match="unclosed '\\['"):
            _parse(data)

    def test_unclosed_collection_raises(self):
        data = '@prefix : <http://example.org/> .\n:s :p ( :a :b .\n'
        with pytest.raises(TurtleSyntaxError, match="unclosed '\\('"):
            _parse(data)

    def test_unclosed_iri_raises(self):
        # Same "caught by the statement-splitter's own '<' depth tracking
        # first" reasoning as test_unclosed_triple_term_raises above.
        data = '@prefix : <http://example.org/> .\n:s :p <http://example.org/unterminated\n'
        with pytest.raises(TurtleSyntaxError, match="unclosed '<'"):
            _parse(data)
