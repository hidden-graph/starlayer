"""
starlayergraph.parsers.trig12

Parse TriG 1.2 text into triples, preserving or merging named-graph structure.

TriG 1.2 is Turtle 1.2 with optional ``GRAPH <name> { ... }`` blocks.  Each
block's content is Turtle 1.2, so this parser:

  1. Extracts PREFIX / @prefix declarations.
  2. Splits the document into graph blocks (default graph + each GRAPH block).
  3. Prepends the prefix declarations to each block's content.
  4. Parses each chunk as Turtle 1.2 via StarLayerTurtleParser.

Entry points:
    parse_trig12(text)        -> list of (s, p, o)            (merges all graphs)
    parse_trig12_named(text)  -> list of (graph_id, triples, namespaces)
"""

from __future__ import annotations

import re as _re
from rdflib import URIRef

from starlayergraph.parsers.turtle_parser import StarLayerTurtleParser, _skolemize_encoding


# ---------------------------------------------------------------------------
# TriG block extractor
# ---------------------------------------------------------------------------

# Matches start of a GRAPH block; group(1) captures the graph identifier token
_GRAPH_BLOCK_RE = _re.compile(
    r'\bGRAPH\s+(<[^>]+>|[A-Za-z_]\w*:[A-Za-z_]\w*|:[A-Za-z_]\w*)\s*\{',
    _re.IGNORECASE,
)

# Regex to strip prefix declarations from a chunk (we'll re-add them ourselves)
_PREFIX_RE = _re.compile(
    r'(?:@prefix\s+\S*\s+<[^>]+>\s*\.|PREFIX\s+\S*\s+<[^>]+>)',
    _re.IGNORECASE,
)


def _consume_balanced(text: str, start: int) -> tuple[str, int]:
    """Consume from text[start] (must be '{') to the matching '}', return (block, end)."""
    assert text[start] == '{'
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        elif text[i] == '<' and not text.startswith('<<(', i):
            i = text.find('>', i + 1) + 1
            continue
        elif text.startswith('<<(', i):
            # Triple term — skip to matching )>>
            d2 = 1
            i += 3
            while i < len(text) and d2 > 0:
                if text.startswith('<<(', i): d2 += 1; i += 3
                elif text.startswith(')>>', i): d2 -= 1; i += 3
                else: i += 1
            continue
        elif text[i] in '"\'':
            # String literal — skip to end
            q = text[i]
            i += 1
            while i < len(text):
                if text[i] == '\\': i += 2
                elif text[i] == q: i += 1; break
                else: i += 1
            continue
        elif text[i] == '#':
            i = text.find('\n', i) + 1
            if i == 0:
                break
            continue
        i += 1
    return text[start:i], i


def _extract_prefix_lines(text: str) -> str:
    """Return a string of all @prefix / PREFIX declarations found in text."""
    lines = []
    for m in _PREFIX_RE.finditer(text):
        lines.append(m.group(0))
    return '\n'.join(lines) + ('\n' if lines else '')


def _extract_prefix_map(text: str) -> dict[str, str]:
    """Return {prefix_str: namespace_uri} for all prefix declarations in text."""
    prefixes: dict[str, str] = {}
    for m in _re.finditer(
        r'(?:@prefix\s+(\S*?)\s+<([^>]+)>\s*\.|PREFIX\s+(\S*?)\s+<([^>]+)>)',
        text, _re.IGNORECASE,
    ):
        if m.group(1) is not None:
            prefixes[m.group(1).rstrip(':')] = m.group(2)
        else:
            prefixes[m.group(3).rstrip(':')] = m.group(4)
    return prefixes


def _resolve_graph_id(token: str, prefix_map: dict[str, str]) -> URIRef:
    """Resolve a GRAPH identifier token (<IRI> or prefix:local) to a URIRef."""
    if token.startswith('<') and token.endswith('>'):
        return URIRef(token[1:-1])
    if ':' in token:
        colon = token.index(':')
        prefix, local = token[:colon], token[colon + 1:]
        if prefix in prefix_map:
            return URIRef(prefix_map[prefix] + local)
        if prefix == '' and '' in prefix_map:
            return URIRef(prefix_map[''] + local)
    return URIRef(token)


def _split_trig_blocks_with_ids(
    text: str,
) -> list[tuple[URIRef | None, str]]:
    """Split a TriG document into (graph_id, turtle_chunk) pairs.

    graph_id is None for the default graph, a URIRef for each named graph.
    Each chunk has the document's prefix declarations prepended.
    """
    prefix_text = _extract_prefix_lines(text)
    prefix_map  = _extract_prefix_map(text)

    default_parts: list[str] = []
    named_blocks:  list[tuple[URIRef, str]] = []
    i = 0

    while i < len(text):
        m = _GRAPH_BLOCK_RE.search(text, i)
        if m is None:
            default_parts.append(text[i:])
            break

        default_parts.append(text[i:m.start()])
        graph_id = _resolve_graph_id(m.group(1), prefix_map)
        brace_pos = m.end() - 1
        block, j = _consume_balanced(text, brace_pos)
        inner = block[1:-1]
        named_blocks.append((graph_id, prefix_text + inner))
        i = j

    default_content = _PREFIX_RE.sub('', ''.join(default_parts))
    result: list[tuple[URIRef | None, str]] = []
    if default_content.strip():
        result.append((None, prefix_text + default_content))
    result.extend(named_blocks)
    return result


def _split_trig_blocks(text: str) -> list[str]:
    """Split a TriG document into Turtle 1.2 chunks (merges all graphs).

    Each chunk has the document's prefix declarations prepended so it can be
    parsed independently by StarLayerTurtleParser.
    """
    return [chunk for _, chunk in _split_trig_blocks_with_ids(text)]


def extract_version_directive(text: str) -> str | None:
    """Return the document-level declared VERSION label, or None.

    TriG's VERSION directive (if present) applies to the whole document, not
    per-GRAPH-block - it must be the very first statement, before any
    @prefix/PREFIX declaration or GRAPH block. Each per-block chunk handed to
    StarLayerTurtleParser by _split_trig_blocks*() never includes this
    leading directive as such (it either lands, stripped of significance,
    in the default-graph chunk, or is absent from every GRAPH-block chunk
    entirely), so callers need this dedicated top-level scan instead - see
    StarLayerGraph.parse()/StarLayerDataset.parse()'s 'trig12' branches,
    which use it for the RDF12ConformanceWarning check
    (starlayergraph.model.conformance). Reuses starlayergraph.parsers.syntax's
    existing statement splitter/classifier rather than duplicating that
    grammar.
    """
    from starlayergraph.parsers.syntax import split_statements, classify_statement, extract_fields
    stmts = split_statements(text)
    if not stmts or classify_statement(stmts[0]) != 'version':
        return None
    return extract_fields(stmts[0], 'version').get('version')


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def parse_trig12(text: str) -> list[tuple]:
    """Parse TriG 1.2 text; return list of (s, p, o) triples.

    All named graphs are merged.  Returns tt:-encoded triples ready for
    super().add() + _build_registry_from_store() (same pattern as turtle12).

    One shared rr_counter box is passed to every block's own
    _skolemize_encoding() call so anonymous-reifier numbering (rr:N) stays
    unique across the *whole* document, not just within each block - see
    _skolemize_encoding()'s own docstring for why a per-block-only scan
    isn't enough (two different blocks' own "rr:0" would otherwise collide
    once merged into this one graph, which is exactly what merging does).
    """
    rr_counter = [0]
    triples = []
    for chunk in _split_trig_blocks(text):
        if not chunk.strip():
            continue
        raw = StarLayerTurtleParser().parse(chunk)
        processed = _skolemize_encoding(raw, rr_counter)
        for triple in processed:
            triples.append(triple)
    return triples


def parse_trig12_named(
    text: str,
) -> list[tuple[URIRef | None, list[tuple], list[tuple]]]:
    """Parse TriG 1.2 text; return per-graph data preserving named-graph structure.

    Returns a list of ``(graph_id, triples, namespaces)`` entries where:
    - *graph_id* is ``None`` for the default graph or a ``URIRef`` for named graphs.
    - *triples* is a list of tt:-encoded ``(s, p, o)`` triples ready for
      ``Graph.add()`` + ``_build_registry_from_store()``.
    - *namespaces* is a list of ``(prefix, namespace)`` pairs from that chunk.

    One shared rr_counter box is passed to every block's own
    _skolemize_encoding() call so anonymous-reifier numbering (rr:N) stays
    unique across the *whole* document, not just within each block - see
    _skolemize_encoding()'s own docstring for why a per-block-only scan
    isn't enough. Each graph block here stays its own separate Graph
    (unlike parse_trig12(), which merges them), but two different blocks'
    "rr:0" would otherwise still collide the moment a query result (e.g. a
    CONSTRUCT crossing GRAPH boundaries) puts content from both in one place.
    """
    rr_counter = [0]
    result = []
    for graph_id, chunk in _split_trig_blocks_with_ids(text):
        if not chunk.strip():
            continue
        raw = StarLayerTurtleParser().parse(chunk)
        processed = _skolemize_encoding(raw, rr_counter)
        triples = list(processed)
        namespaces = list(processed.namespaces())
        result.append((graph_id, triples, namespaces))
    return result
