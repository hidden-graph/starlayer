"""
Unit tests for starlayer.graph.parsers.trig12's own string-literal-aware
block/prefix splitting.

Covers a real bug found while running this project's own code-KG
extractor over this project's own graph/parsers/trig12.py: this module's
GRAPH-block detection and @prefix-declaration extraction used to run
blind text-wide regexes/single-char quote tracking with no awareness of
whether a given piece of text was really top-level syntax or just the
content of an open (triple- or single-quoted) string literal - e.g. a
docstring that quotes "@prefix : <http://example.org/> ." or shows a
literal "GRAPH <...> { ... }" example, exactly like this module's own
docstrings do.
"""

from rdflib import URIRef

from starlayer.graph.parsers.trig12 import (
    _consume_balanced,
    _extract_prefix_lines,
    _extract_prefix_map,
    _mask_string_literals,
    _split_trig_blocks_with_ids,
    parse_trig12_named,
)


class TestMaskStringLiterals:
    def test_masks_triple_quoted_content(self):
        text = 'a """hello "world" there""" b'
        masked = _mask_string_literals(text)
        assert masked.startswith('a ')
        assert masked.endswith(' b')
        assert '"' not in masked[2:-2].replace('#', '')  # only '#' filler inside
        assert len(masked) == len(text)

    def test_preserves_newlines_inside_masked_region(self):
        text = '"""line one\nline two"""'
        masked = _mask_string_literals(text)
        assert masked.count('\n') == text.count('\n')
        assert len(masked) == len(text)

    def test_leaves_non_string_content_untouched(self):
        text = '@prefix ex: <http://example.org/> .'
        assert _mask_string_literals(text) == text


class TestExtractPrefixLinesIgnoresStringContent:
    def test_real_prefix_line_still_found(self):
        text = '@prefix ex: <http://example.org/> .\nex:s ex:p ex:o .'
        result = _extract_prefix_lines(text)
        assert '@prefix ex: <http://example.org/> .' in result

    def test_prefix_lookalike_inside_long_string_ignored(self):
        text = (
            'ex:s ex:p """A directive like\n'
            '@prefix : <http://example.org/> . is just prose here."""  .'
        )
        result = _extract_prefix_lines(text)
        assert result == ''

    def test_prefix_lookalike_inside_long_string_ignored_in_map(self):
        text = (
            'ex:s ex:p """A directive like\n'
            '@prefix bogus: <http://bogus.example/> . is just prose."""  .'
        )
        result = _extract_prefix_map(text)
        assert 'bogus' not in result


class TestConsumeBalancedWithEmbeddedQuote:
    def test_embedded_single_quote_does_not_break_brace_depth(self):
        text = (
            '{\n'
            '    ex:s ex:p """A directive like\n'
            '"@prefix : <http://example.org/> ." is just prose, and this\n'
            'has a brace-looking } character too, still inside the string\n'
            'closing here""" .\n'
            '}'
        )
        block, end = _consume_balanced(text, 0)
        assert end == len(text)
        assert block == text


class TestSplitTrigBlocksWithEmbeddedDirectiveLookalikes:
    def test_graph_block_lookalike_inside_long_string_not_misdetected(self):
        text = (
            '@prefix ex: <http://example.org/> .\n'
            'ex:s ex:p """an example like\n'
            'GRAPH <http://example.org/g> { ex:a ex:b ex:c . } shown as prose\n'
            'real end""" .\n'
        )
        blocks = _split_trig_blocks_with_ids(text)
        # Only the default graph - the embedded "GRAPH <...> { }" text must
        # not be split out as a second, named graph block.
        assert len(blocks) == 1
        assert blocks[0][0] is None

    def test_end_to_end_parse_trig12_named_round_trips(self):
        text = (
            '@prefix ex: <http://example.org/> .\n'
            'ex:s ex:p """Example syntax:\n'
            '"@prefix : <http://example.org/> ." and\n'
            'GRAPH <http://example.org/g> { ... } shown as prose\n'
            'real end""" .\n'
            'GRAPH <http://example.org/real> {\n'
            '    ex:x ex:y ex:z .\n'
            '}\n'
        )
        result = parse_trig12_named(text)
        graph_ids = [gid for gid, _triples, _ns in result]
        assert None in graph_ids
        assert URIRef('http://example.org/real') in graph_ids
        default_triples = next(t for gid, t, _ns in result if gid is None)
        subjects_predicates = [(s, p) for s, p, o in default_triples]
        assert (URIRef('http://example.org/s'), URIRef('http://example.org/p')) in subjects_predicates
