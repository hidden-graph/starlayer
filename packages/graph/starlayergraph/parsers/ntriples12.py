"""
starlayergraph.parsers.ntriples12

Parse N-Triples 1.2 and N-Quads 1.2 text into lists of triples/quads.

Triple terms (<<( s p o )>>) are returned as TripleTerm objects.  The caller
(StarLayerGraph.parse) adds them via self.add(), which handles the internal
tt: encoding through _coerce_tt / _intern_tt.

Entry points:
    parse_ntriples12(text) -> list of (s, p, o)
    parse_nquads12(text)   -> list of (s, p, o, graph_uri_or_none)
"""

from __future__ import annotations

import re as _re
from rdflib import URIRef, BNode, Literal
from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.encoding import encode_dirlang_datatype


# ---------------------------------------------------------------------------
# Low-level term consumer
# ---------------------------------------------------------------------------

def _consume_nt_term(text: str, start: int) -> tuple[str | None, int]:
    """Consume one N-Triples 1.2 term starting at start; return (token, end)."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] in '.#':
        return None, i

    # Triple term  <<( ... )>>
    if text.startswith('<<(', i):
        depth, j = 1, i + 3
        while j < len(text):
            if text.startswith('<<(', j):
                depth += 1
                j += 3
            elif text.startswith(')>>', j):
                depth -= 1
                j += 3
                if depth == 0:
                    return text[i:j], j
            elif text[j] == '<':
                # IRI inside — skip to matching >
                k = text.find('>', j + 1)
                j = k + 1 if k != -1 else len(text)
            elif text[j] == '"':
                j += 1
                while j < len(text):
                    if text[j] == '\\':
                        j += 2
                    elif text[j] == '"':
                        j += 1
                        break
                    else:
                        j += 1
            else:
                j += 1
        raise ValueError(f"Unterminated triple term at position {start}: {text[start:start+60]!r}")

    # Full IRI  <...>
    if text[i] == '<':
        j = text.find('>', i + 1)
        if j == -1:
            raise ValueError(f"Unterminated IRI at position {i}: {text[i:i+60]!r}")
        return text[i:j + 1], j + 1

    # Blank node  _:local
    if text.startswith('_:', i):
        j = i + 2
        while j < len(text) and not text[j].isspace() and text[j] not in '.,;':
            j += 1
        return text[i:j], j

    # Literal  "value"[@lang | ^^<dtype>]
    if text[i] == '"':
        j = i + 1
        while j < len(text):
            if text[j] == '\\':
                j += 2
            elif text[j] == '"':
                j += 1
                break
            else:
                j += 1
        # Optional @lang
        if j < len(text) and text[j] == '@':
            k = j + 1
            while k < len(text) and (text[k].isalnum() or text[k] == '-'):
                k += 1
            return text[i:k], k
        # Optional ^^<dtype>
        if text.startswith('^^', j):
            k = j + 2
            if k < len(text) and text[k] == '<':
                m = text.find('>', k + 1)
                if m != -1:
                    return text[i:m + 1], m + 1
        return text[i:j], j

    raise ValueError(f"Unexpected character at position {i}: {text[i:i+30]!r}")


# ---------------------------------------------------------------------------
# Term token → rdflib node
# ---------------------------------------------------------------------------

def _unescape_nt(s: str) -> str:
    """Decode N-Triples string escape sequences."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] != '\\':
            out.append(s[i])
            i += 1
            continue
        esc = s[i + 1] if i + 1 < len(s) else ''
        if   esc == 'n':  out.append('\n'); i += 2
        elif esc == 'r':  out.append('\r'); i += 2
        elif esc == 't':  out.append('\t'); i += 2
        elif esc == 'b':  out.append('\b'); i += 2
        elif esc == 'f':  out.append('\f'); i += 2
        elif esc == '\\': out.append('\\'); i += 2
        elif esc == '"':  out.append('"');  i += 2
        elif esc == 'u' and i + 5 < len(s):
            out.append(chr(int(s[i+2:i+6], 16))); i += 6
        elif esc == 'U' and i + 9 < len(s):
            out.append(chr(int(s[i+2:i+10], 16))); i += 10
        else:
            out.append(s[i]); i += 1
    return ''.join(out)


def _token_to_node(token: str):
    """Convert an N-Triples 1.2 token string to an rdflib node or TripleTerm."""
    token = token.strip()

    # Triple term
    if token.startswith('<<(') and token.endswith(')>>'):
        inner = token[3:-3].strip()
        tok_s, i = _consume_nt_term(inner, 0)
        tok_p, i = _consume_nt_term(inner, i)
        tok_o, _ = _consume_nt_term(inner, i)
        if tok_s is None or tok_p is None or tok_o is None:
            raise ValueError(f"Triple term must have exactly 3 components: {token!r}")
        return TripleTerm(_token_to_node(tok_s), _token_to_node(tok_p), _token_to_node(tok_o))

    # IRI
    if token.startswith('<') and token.endswith('>'):
        return URIRef(_unescape_nt(token[1:-1]))

    # Blank node
    if token.startswith('_:'):
        return BNode(token[2:])

    # Literal
    if token.startswith('"'):
        close = token.index('"', 1)
        while close > 0 and token[close - 1] == '\\':
            close = token.index('"', close + 1)
        value = _unescape_nt(token[1:close])
        suffix = token[close + 1:]
        if suffix.startswith('@'):
            lang_dir = suffix[1:]
            if '--' in lang_dir:
                # RDF 1.2 "text"@lang--dir (rdf:dirLangString) — see
                # starlayergraph.parsers.turtle_parser._to_node for the same encoding.
                language, _, direction = lang_dir.rpartition('--')
                direction = direction.lower()
                if direction not in ('ltr', 'rtl'):
                    raise ValueError(
                        f'RDF 1.2: base direction must be "ltr" or "rtl", got {direction!r} in @{lang_dir}'
                    )
                return Literal(value, datatype=encode_dirlang_datatype(language.lower(), direction))
            return Literal(value, lang=lang_dir)
        if suffix.startswith('^^<') and suffix.endswith('>'):
            return Literal(value, datatype=URIRef(_unescape_nt(suffix[3:-1])))
        return Literal(value)

    raise ValueError(f"Unknown N-Triples 1.2 term: {token!r}")


# ---------------------------------------------------------------------------
# Line parser
# ---------------------------------------------------------------------------

def _parse_nt_line(line: str, lineno: int, quads: bool = False) -> tuple | None:
    """Parse one N-Triples (or N-Quads) line.

    Returns:
        (s, p, o)        for N-Triples
        (s, p, o, g)     for N-Quads  (g is None for default graph)
        None             for blank / comment lines
    """
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or stripped.upper().startswith('VERSION'):
        return None

    try:
        tok_s, i = _consume_nt_term(stripped, 0)
        tok_p, i = _consume_nt_term(stripped, i)
        tok_o, i = _consume_nt_term(stripped, i)

        if tok_s is None or tok_p is None or tok_o is None:
            raise ValueError("Incomplete triple")

        s = _token_to_node(tok_s)
        p = _token_to_node(tok_p)
        o = _token_to_node(tok_o)

        if not quads:
            return s, p, o

        # N-Quads: optional graph name before '.'
        tok_g, _ = _consume_nt_term(stripped, i)
        g = _token_to_node(tok_g) if tok_g is not None else None
        return s, p, o, g

    except Exception as exc:
        raise ValueError(f"Line {lineno}: {exc}\n  {line!r}") from exc


# ---------------------------------------------------------------------------
# VERSION directive (RDF 1.2 N-Triples grammar: 'VERSION' STRING_LITERAL_QUOTE,
# first non-blank/comment line only)
# ---------------------------------------------------------------------------

_VERSION_LINE_RE = _re.compile(r'VERSION\s*([\'"])((?:(?!\1).)*)\1\s*$', _re.IGNORECASE)


def extract_version_directive(text: str) -> str | None:
    """Return the declared VERSION label (e.g. "1.2-basic"), or None.

    _parse_nt_line() already recognizes a VERSION line but only to discard it
    like a comment - it never surfaces the label. This is a separate,
    lightweight scan so parse_ntriples12()/parse_nquads12() keep their
    existing list[tuple] return signature; StarLayerGraph.parse() calls this
    alongside them for the RDF12ConformanceWarning check (see
    starlayergraph.model.conformance). Per the grammar, VERSION - if present -
    must be the first statement, so only the first non-blank/comment line is
    examined.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        m = _VERSION_LINE_RE.match(stripped)
        return m.group(2) if m else None
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def parse_ntriples12(text: str) -> list[tuple]:
    """Parse N-Triples 1.2 text; return list of (s, p, o) triples.

    Subjects and objects may be TripleTerm instances.
    """
    triples = []
    for lineno, line in enumerate(text.splitlines(), 1):
        result = _parse_nt_line(line, lineno, quads=False)
        if result is not None:
            triples.append(result)
    return triples


def parse_nquads12(text: str) -> list[tuple]:
    """Parse N-Quads 1.2 text; return list of (s, p, o, g) quads.

    g is a URIRef for named graphs, None for the default graph.
    Subjects and objects may be TripleTerm instances.
    """
    quads = []
    for lineno, line in enumerate(text.splitlines(), 1):
        result = _parse_nt_line(line, lineno, quads=True)
        if result is not None:
            quads.append(result)
    return quads
