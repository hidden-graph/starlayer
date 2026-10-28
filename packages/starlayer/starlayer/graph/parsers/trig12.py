"""
starlayer.graph.parsers.trig12

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

from rdflib import BNode, URIRef

from starlayer.graph.parsers.turtle_parser import (
    StarLayerTurtleParser,
    _skolemize_encoding,
)

# ---------------------------------------------------------------------------
# TriG block extractor
# ---------------------------------------------------------------------------

# Matches start of a GRAPH block; group(1) captures the graph identifier token
_GRAPH_BLOCK_RE = _re.compile(
    r'\bGRAPH\s+(<[^>]*>|[A-Za-z_]\w*:[A-Za-z_]\w*|:[A-Za-z_]\w*)\s*\{',
    _re.IGNORECASE,
)

# A graph block, in every form the TriG grammar allows (GitHub issue #47): ``GRAPH <iri> {``, ``<iri> {``, ``ex:name {``,
# ``_:b {``, ``[] {`` and the bare ``{`` of the default graph. It is searched in a copy of the text with the strings and the
# directives (whose IRI would look like a label) blanked, and a label or a bare ``{`` only counts at the start of a
# statement. ``{|`` opens an annotation, not a graph.
_BLOCK_RE = _re.compile(
    r'(?P<kw>\bGRAPH\s+)?'
    r'(?P<label><[^>\s]*>|_:[^\s{}]+|(?:[A-Za-z_][\w.\-]*)?:[^\s{}<>]*|\[\s*\])?'
    r'\s*\{(?!\|)',
    _re.IGNORECASE,
)
_NON_SPACE_RE = _re.compile(r'\S')


def _search_block(scan: str, pos: int):
    """``_BLOCK_RE.search(scan, pos)``, starting at the first non-space character. A match that begins in white space can only
    be a bare ``{`` (a label or a ``GRAPH`` keyword starts with a visible character), and ``_BLOCK_RE`` re-reads the rest of
    the white space for every start, so a long blank run (the prefix lines that were blanked before this scan, 16 KB in the
    code graph) cost time proportional to its square: a second to find the first block. Starting at the first visible
    character finds the same blocks."""
    visible = _NON_SPACE_RE.search(scan, pos)
    if visible is None:
        return None
    return _BLOCK_RE.search(scan, visible.start())


_DIRECTIVE_RE = _re.compile(
    r'@prefix\s+[^\s<]*\s*<[^>]*>\s*\.|\bPREFIX\s+[^\s<]*\s*<[^>]*>'
    r'|@base\s*<[^>]*>\s*\.|\bBASE\s*<[^>]*>|@version\b[^.]*\.|\bVERSION\b\s*\S+',
    _re.IGNORECASE,
)

# A prefix or base declaration (what a graph block's chunk needs written in front of it, in document order)
_DECLARATION_RE = _re.compile(
    r'@prefix\s+[^\s<]*\s*<[^>]*>\s*\.|\bPREFIX\s+[^\s<]*\s*<[^>]*>'
    r'|@base\s*<[^>]*>\s*\.|\bBASE\s*<[^>]*>',
    _re.IGNORECASE,
)
_BASE_DECL_RE = _re.compile(r'(?:@base|BASE)\s*<([^>]*)>', _re.IGNORECASE)
_PREFIX_DECL_RE = _re.compile(r'(?:@prefix|PREFIX)\s+([^\s<]*?)\s*<([^>]*)>', _re.IGNORECASE)

# Regex to strip prefix declarations from a chunk (we'll re-add them ourselves)
_PREFIX_RE = _re.compile(
    r'(?:@prefix\s+[^\s<]*\s*<[^>]*>\s*\.|PREFIX\s+[^\s<]*\s*<[^>]*>)',
    _re.IGNORECASE,
)


# the characters _consume_balanced has to look at one by one; everything between them is skipped in one step
_BALANCE_SPECIALS = _re.compile(r"[{}<\"'#]")


def _consume_balanced(text: str, start: int) -> tuple[str, int]:
    """Consume from text[start] (must be '{') to the matching '}', return (block, end)."""
    assert text[start] == '{'
    depth = 1
    i = start + 1
    n = len(text)
    while i < n and depth > 0:
        m = _BALANCE_SPECIALS.search(text, i)
        if m is None:
            i = n
            break
        i = m.start()
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif c == '<' and not text.startswith('<<(', i):
            end = text.find('>', i + 1)
            if end == -1:  # an unterminated IRI: the rest of the text. (find() + 1 was 0 here, which sent the caller back to the start, forever)
                i = n
                break
            i = end + 1
            continue
        elif c == '<':
            # Triple term - skip to matching )>>
            d2 = 1
            i += 3
            while i < len(text) and d2 > 0:
                if text.startswith('<<(', i): d2 += 1; i += 3
                elif text.startswith(')>>', i): d2 -= 1; i += 3
                else: i += 1
            continue
        elif c in '"\'':
            # String literal - skip to its end. A long ('"""'/"\'\'\'"-delimited) string needs the real closing run of 3
            # matching quote chars, not just the next single matching one - otherwise a lone embedded quote character
            # (legal Turtle content, e.g. a docstring quoting a short phrase like this very module's own module-level
            # docstring, which quotes GRAPH-block syntax) closes the "string" after only 2 characters, scrambling this
            # function's own brace-depth tracking for everything that follows - confirmed via this project's own code-KG
            # extractor feeding this project's own trig12.py back through itself. Mirrors syntax._split_statements_impl's
            # matching fix.
            q = c
            if text.startswith(q * 3, i):
                i += 3
                while i < len(text) and not text.startswith(q * 3, i):
                    # Skip an escaped character as one atomic pair, same fix as the short-string branch just below and
                    # syntax._split_statements_impl's matching one - otherwise an escaped quote sitting directly against
                    # the real closing delimiter (e.g. a docstring ending "...the word \"profile.\"\"\"\"") is misread
                    # as itself starting the close, one character early.
                    i += 2 if text[i] == '\\' else 1
                i = min(i + 3, len(text))
            else:
                i += 1
                while i < len(text):
                    if text[i] == '\\': i += 2
                    elif text[i] == q: i += 1; break
                    else: i += 1
            continue
        elif c == '#':
            end = text.find('\n', i)
            if end == -1:  # a comment on the last line of an unterminated block: the rest of the text (i was 0 here, and the caller started over, forever)
                i = n
                break
            i = end + 1
            continue
        i += 1
    return text[start:i], i


def _mask_string_literals(text: str) -> str:
    """Return a same-length copy of text with the contents of every quoted
    string literal (long or short) replaced by '#' filler (newlines left
    untouched, so line-oriented matching elsewhere is unaffected).

    Used to protect the regex-based structural scans below
    (_GRAPH_BLOCK_RE, _PREFIX_RE, the prefix-map regex) from being fooled
    by literal text that merely *looks* like a GRAPH block or a @prefix/
    PREFIX declaration but is really just a string's own content - e.g. a
    docstring that quotes "@prefix : <http://example.org/> ." as part of
    its prose, or one that shows a literal "GRAPH <...> { ... }" example
    (this module's own docstrings do both). Positions/length are
    preserved so a match's span still slices correctly into the
    *original*, unmasked text.
    """
    out = list(text)
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'"):
            start = i
            if text.startswith(c * 3, i):
                i += 3
                while i < n and not text.startswith(c * 3, i):
                    # Same escaped-character-before-the-closing-delimiter
                    # fix as _consume_balanced()'s matching branch above.
                    i += 2 if text[i] == '\\' else 1
                i = min(i + 3, n)
            else:
                i += 1
                while i < n and text[i] != c:
                    i += 2 if text[i] == '\\' else 1
                i = min(i + 1, n)
            for k in range(start, i):
                if out[k] not in ('\n', '\r'):
                    out[k] = '#'
        else:
            i += 1
    return ''.join(out)


def _extract_prefix_lines(text: str) -> str:
    """Return a string of all @prefix / PREFIX declarations found in text.

    Matches against a string-literal-masked copy of text (see
    _mask_string_literals()), not text itself - a genuine declaration is
    never inside a string literal, so it's completely unaffected by
    masking, but text that merely *looks* like one inside a string's own
    content (e.g. a docstring quoting "@prefix : <http://example.org/> .")
    is masked away and correctly never matches.
    """
    masked = _mask_string_literals(text)
    lines = [m.group(0) for m in _PREFIX_RE.finditer(masked)]
    return '\n'.join(lines) + ('\n' if lines else '')


def _extract_prefix_map(text: str) -> dict[str, str]:
    """Return {prefix_str: namespace_uri} for all prefix declarations in
    text. See _extract_prefix_lines() for why this matches against a
    string-literal-masked copy rather than text itself."""
    masked = _mask_string_literals(text)
    prefixes: dict[str, str] = {}
    for m in _re.finditer(
        r'(?:@prefix\s+([^\s<]*?)\s*<([^>]*)>\s*\.|PREFIX\s+([^\s<]*?)\s*<([^>]*)>)',
        masked, _re.IGNORECASE,
    ):
        if m.group(1) is not None:
            prefixes[m.group(1).rstrip(':')] = m.group(2)
        else:
            prefixes[m.group(3).rstrip(':')] = m.group(4)
    return prefixes


def _resolution_state(declarations: list[str], base: str | None) -> tuple[str | None, dict[str, str]]:
    """The base IRI and the prefix map in effect after ``declarations`` (the text of each, in order), starting from ``base``.
    Relative IRIs resolve as in the Turtle parser, so a graph name and a relative ``@prefix p: <#>`` follow the document's
    ``@base`` / ``BASE`` (GitHub issue #132)."""
    from starlayer.graph.parsers.turtle_parser import _join

    prefixes: dict[str, str] = {}
    for decl in declarations:
        m = _BASE_DECL_RE.match(decl)
        if m:
            base = _join(base, m.group(1)) if base else m.group(1)
            continue
        m = _PREFIX_DECL_RE.match(decl)
        if m:
            ns = m.group(2)
            prefixes[m.group(1).rstrip(':')] = _join(base, ns) if base else ns
    return base, prefixes


def _resolve_graph_id(token: str, prefix_map: dict[str, str], base: str | None = None) -> URIRef | BNode:
    """Resolve a graph label token (<IRI>, prefix:local, _:label or []) to a URIRef or BNode."""
    if token.startswith('_:'):
        return BNode(token[2:])
    if token.startswith('['):
        return BNode()
    if token.startswith('<') and token.endswith('>'):
        from starlayer.graph.parsers.turtle_parser import _resolve_iri_reference

        return URIRef(_resolve_iri_reference(token[1:-1], base))
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
    base: str | None = None,
) -> list[tuple[URIRef | BNode | None, str]]:
    """Split a TriG document into (graph_id, turtle_chunk) pairs.

    graph_id is None for the default graph, a URIRef for each named graph.
    Each chunk has the document's prefix declarations prepended.
    """
    # The prefix declarations, in document order, with where each one starts: a declaration applies from there on, so a prefix
    # declared again changes the meaning of what FOLLOWS it and leaves what came before alone (GitHub issue #56).
    masked = _mask_string_literals(text)
    # (@base / BASE declarations are carried the same way, so a graph block resolves its relative IRIs against the base in
    # effect where it is written, and ``base`` - the publicID - is the base before any of them; GitHub issue #132.)
    declarations = [(m.start(), m.group(0)) for m in _DECLARATION_RE.finditer(masked)]

    def prefixes_before(pos: int) -> tuple[str, dict[str, str], str | None]:
        """The declarations written before ``pos``, as Turtle text to prepend, as a prefix map and as the base in effect."""
        before = [decl for start, decl in declarations if start < pos]
        in_scope_base, prefix_map = _resolution_state(before, base)
        return ''.join(d + '\n' for d in before), prefix_map, in_scope_base

    # Search for GRAPH blocks against a string-literal-masked copy, not
    # text itself - otherwise literal text that merely *looks* like a
    # GRAPH block inside a string's own content (e.g. a docstring showing
    # a literal "GRAPH <...> { ... }" example, as this module's own
    # module-level docstring does) is misdetected as a real one. A match
    # against masked text still has the correct start/end *position* to
    # slice the original, unmasked text with, since masking never changes
    # length. _consume_balanced() itself still runs against the original
    # text (never masked) - it already does its own, independent
    # triple-quote-aware string tracking to find the real matching '}'.
    default_parts: list[str] = []
    named_blocks:  list[tuple[URIRef | BNode, str]] = []
    # directives and strings blanked: what is left is statements, so a label before a '{' is a graph label
    scan = _DIRECTIVE_RE.sub(lambda m: ' ' * len(m.group(0)), masked)
    i = 0

    def block_start(m) -> int:
        """Where the block really starts: its GRAPH keyword or label, or the '{'. (``\\s*`` lets a match begin in the
        blanks left by a directive, which are not part of it.)"""
        if m.group('kw'):
            return m.start('kw')
        if m.group('label'):
            return m.start('label')
        return m.end() - 1

    while i < len(text):
        m = _search_block(scan, i)
        while m is not None:
            start = block_start(m)
            k = start - 1
            while k >= 0 and scan[k].isspace():
                k -= 1
            at_statement_start = k < 0 or scan[k] in '.}'
            # 'GRAPH' with no label is not a block; a label without GRAPH, or a bare '{', only counts at the start of a statement
            if (m.group('kw') and not m.group('label')) or not (m.group('kw') or at_statement_start):
                m = _search_block(scan, m.start() + 1)
                continue
            break
        if m is None:
            default_parts.append(text[i:])
            break

        start = block_start(m)
        default_parts.append(text[i:start])
        brace_pos = m.end() - 1
        block, j = _consume_balanced(text, brace_pos)
        inner = block[1:-1]
        label = m.group('label')
        if label is None:
            default_parts.append(inner)  # a bare { ... } is the default graph
        else:
            prefix_text, prefix_map, in_scope_base = prefixes_before(start)
            named_blocks.append((_resolve_graph_id(label, prefix_map, in_scope_base), prefix_text + inner))
        i = j

    # The default graph's content keeps its own declarations where they are written, in order: they are part of the
    # statements around them. (They used to be removed and ALL of the document's declarations put in front of every block.)
    default_content = ''.join(default_parts)
    result: list[tuple[URIRef | None, str]] = []
    if default_content.strip():
        result.append((None, default_content))
    result.extend(named_blocks)
    return result


def _split_trig_blocks(text: str, base: str | None = None) -> list[str]:
    """Split a TriG document into Turtle 1.2 chunks (merges all graphs).

    Each chunk has the document's prefix declarations prepended so it can be
    parsed independently by StarLayerTurtleParser.
    """
    return [chunk for _, chunk in _split_trig_blocks_with_ids(text, base)]


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
    (starlayer.graph.model.conformance). Reuses starlayer.graph.parsers.syntax's
    existing statement splitter/classifier rather than duplicating that
    grammar.

    Args:
        text: The full TriG 1.2 document text.

    Returns:
        The declared VERSION label (e.g. "1.2"), or None if the
        document's first statement isn't a VERSION directive.
    """
    from starlayer.graph.parsers.syntax import (
        classify_statement,
        extract_fields,
        split_statements,
    )
    # Only the first statement matters, and a VERSION directive precedes every graph block, so the text before the first
    # '{' is enough. (Splitting the whole document buffered each GRAPH block as one statement, which was quadratic.)
    brace = text.find('{')
    head = text if brace < 0 else text[:brace]
    stmts = split_statements(head)
    if not stmts or classify_statement(stmts[0]) != 'version':
        return None
    return extract_fields(stmts[0], 'version').get('version')


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def parse_trig12(text: str, base: str | None = None) -> list[tuple]:
    """Parse TriG 1.2 text; return list of (s, p, o) triples.

    All named graphs are merged.  Returns tt:-encoded triples ready for
    super().add() + _build_registry_from_store() (same pattern as turtle12).

    Each block is parsed via its own, independent call to
    _skolemize_encoding() - no cross-block coordination needed for anonymous
    reifiers, since they're left as ordinary BNodes (globally unique per
    instantiation, not numbered), unlike the old rr:N scheme this replaced.

    Args:
        text: The TriG 1.2 document text to parse.

    Returns:
        A list of tt:-encoded (s, p, o) triples, all named graphs merged
        together with the default graph.
    """
    triples = []
    for chunk in _split_trig_blocks(text, base):
        if not chunk.strip():
            continue
        raw = StarLayerTurtleParser().parse(chunk, base=base, require_final_dot=False)
        processed = _skolemize_encoding(raw)
        for triple in processed:
            triples.append(triple)
    return triples


def parse_trig12_named(
    text: str,
    base: str | None = None,
    require_final_dot: bool = False,
) -> list[tuple[URIRef | None, list[tuple], list[tuple]]]:
    """Parse TriG 1.2 text; return per-graph data preserving named-graph structure.

    Each graph block stays its own separate Graph (unlike parse_trig12(),
    which merges them). No cross-block reifier-numbering coordination is
    needed - see parse_trig12()'s docstring.

    Args:
        text: The TriG 1.2 document text to parse.
        base: The base IRI.
        require_final_dot: A last triple without its '.' is an error (right for a
            Turtle document read through this path; a TriG graph block may omit it).

    Returns:
        A list of (graph_id, triples, namespaces) entries, one per graph
        block: graph_id is None for the default graph or a URIRef for a
        named graph; triples is a list of tt:-encoded (s, p, o) triples
        ready for Graph.add() + _build_registry_from_store(); namespaces
        is a list of (prefix, namespace) pairs declared in that block.
    """
    result = []
    for graph_id, chunk in _split_trig_blocks_with_ids(text, base):
        if not chunk.strip() and graph_id is None:
            continue
        # an empty named block (`GRAPH <g> { }`) is still a graph of the dataset (GitHub issue #99)
        raw = StarLayerTurtleParser().parse(chunk, base=base, require_final_dot=require_final_dot)
        processed = _skolemize_encoding(raw)
        triples = list(processed)
        namespaces = list(processed.namespaces())
        result.append((graph_id, triples, namespaces))
    return result
