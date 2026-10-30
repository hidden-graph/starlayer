"""
starlayer.graph.parsers.ntriples12

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

from rdflib import Literal, URIRef

from starlayer.graph.model.encoding import encode_dirlang_datatype
from starlayer.graph.model.triple import TripleTerm
from starlayer.graph.parsers.bnode_scope import labelled_bnode, per_document

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

    if text.startswith('<<', i):
        raise ValueError(f"<< >> reified-triple syntax is not N-Triples (a triple term is written <<( s p o )>>): {text[i:i+40]!r}")

    # Full IRI  <...>
    if text[i] == '<':
        j = text.find('>', i + 1)
        if j == -1:
            raise ValueError(f"Unterminated IRI at position {i}: {text[i:i+60]!r}")
        return text[i:j + 1], j + 1

    # Blank node  _:local
    if text.startswith('_:', i):
        j = i + 2
        while j < len(text) and not text[j].isspace() and text[j] not in ',;':
            # a '.' is part of the label only between two label characters ("_:a.b"); the last one ends the triple
            if text[j] == '.' and not (j + 1 < len(text) and (text[j + 1].isalnum() or text[j + 1] in '_-')):
                break
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

def _lines(text: str) -> list[str]:
    """The lines of an N-Triples/N-Quads document. Only CR and LF end a line (``EOL ::= [#xD#xA]+``);
    ``str.splitlines()`` also splits at VT, FF, FS, GS, RS, NEL, LS and PS, which are legal inside a literal
    (GitHub issue #133)."""
    return _re.split(r'\r\n|\r|\n', text)


_SIMPLE_ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', '\\': '\\', '"': '"', "'": "'"}
_HEX4 = _re.compile(r'[0-9A-Fa-f]{4}')
_HEX8 = _re.compile(r'[0-9A-Fa-f]{8}')
_LANG_DIR = _re.compile(r'[a-zA-Z]+(?:-[a-zA-Z0-9]+)*(?:--[a-zA-Z]+)?')
_ABSOLUTE_IRI = _re.compile(r'[a-zA-Z][a-zA-Z0-9+\-.]*:')
_IRI_FORBIDDEN = _re.compile(r'[\x00-\x20<>"{}|^`\\]')
_BNODE_LABEL = _re.compile(r'_:[A-Za-z0-9_\u00C0-\U000EFFFF](?:[A-Za-z0-9_\-.\u00B7\u00C0-\U000EFFFF]*[A-Za-z0-9_\-\u00B7\u00C0-\U000EFFFF])?')
_LANG_STRING_TYPES = ('http://www.w3.org/1999/02/22-rdf-syntax-ns#langString',
                      'http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString')


def _unescape_nt(s: str) -> str:
    """Decode N-Triples string escape sequences. Only ECHAR (``\\t \\b \\n \\r \\f \\" \\' \\\\``) and UCHAR
    (``\\uXXXX``, ``\\UXXXXXXXX``, never a surrogate) are legal; anything else is a ValueError (GitHub issue #73)."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] != '\\':
            out.append(s[i])
            i += 1
            continue
        esc = s[i + 1] if i + 1 < len(s) else ''
        if esc in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[esc]); i += 2
        elif esc in ('u', 'U'):
            width, pattern = (4, _HEX4) if esc == 'u' else (8, _HEX8)
            digits = s[i + 2:i + 2 + width]
            if not pattern.fullmatch(digits) or int(digits, 16) > 0x10FFFF:
                raise ValueError(f"bad \\{esc} escape {s[i:i + 2 + width]!r}")
            cp = int(digits, 16)
            if 0xD800 <= cp <= 0xDFFF:
                raise ValueError(f"\\{esc}{digits} is a UTF-16 surrogate, not a Unicode code point")
            out.append(chr(cp)); i += 2 + width
        else:
            raise ValueError(f"invalid escape \\{esc} in a string or IRI")
    return ''.join(out)


def _iri_node(body: str) -> URIRef:
    """The IRI of an ``<...>`` token (without the brackets): absolute, with none of the characters IRIREF excludes."""
    raw = _re.sub(r'\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8}', '', body)
    if _IRI_FORBIDDEN.search(raw):
        raise ValueError(f"character not allowed in an IRI: <{body}>")
    iri = _unescape_nt(body)
    if _IRI_FORBIDDEN.search(iri):
        raise ValueError(f"an escape in <{body}> names a character an IRI cannot hold")
    if not _ABSOLUTE_IRI.match(iri):
        raise ValueError(f"N-Triples IRIs must be absolute, got <{body}>")
    return URIRef(iri)


def _token_to_node(token: str):
    """Convert an N-Triples 1.2 token string to an rdflib node or TripleTerm."""
    token = token.strip()

    # Triple term
    if token.startswith('<<(') and token.endswith(')>>'):
        inner = token[3:-3].strip()
        tok_s, i = _consume_nt_term(inner, 0)
        tok_p, i = _consume_nt_term(inner, i)
        tok_o, i = _consume_nt_term(inner, i)
        if tok_s is None or tok_p is None or tok_o is None or inner[i:].strip():
            raise ValueError(f"Triple term must have exactly 3 components: {token!r}")
        t_s, t_p, t_o = _token_to_node(tok_s), _token_to_node(tok_p), _token_to_node(tok_o)
        if isinstance(t_s, Literal) or not isinstance(t_p, URIRef):
            raise ValueError(f"a triple term needs an IRI or blank node subject and an IRI predicate: {token!r}")
        return TripleTerm(t_s, t_p, t_o)

    # IRI
    if token.startswith('<') and token.endswith('>'):
        return _iri_node(token[1:-1])

    # Blank node
    if token.startswith('_:'):
        if not _BNODE_LABEL.fullmatch(token):
            raise ValueError(f"invalid blank node label: {token!r}")
        return labelled_bnode(token[2:])

    # Literal
    if token.startswith('"'):
        # Walk the literal, skipping each escape as a unit: a quote is the closing one unless an ODD number of backslashes
        # precede it, which looking only at the previous character gets wrong for an escaped backslash ("x\\\\"). GitHub issue #57.
        close = 1
        while close < len(token) and token[close] != '"':
            close += 2 if token[close] == '\\' else 1
        if close >= len(token):
            raise ValueError(f"Unterminated literal: {token!r}")
        value = _unescape_nt(token[1:close])
        suffix = token[close + 1:]
        if suffix.startswith('@'):
            lang_dir = suffix[1:]
            if not _LANG_DIR.fullmatch(lang_dir):
                raise ValueError(f"invalid language tag or base direction: @{lang_dir}")
            if '--' in lang_dir:
                # RDF 1.2 "text"@lang--dir (rdf:dirLangString) — see
                # starlayer.graph.parsers.turtle_parser._to_node for the same encoding.
                language, _, direction = lang_dir.rpartition('--')
                if direction not in ('ltr', 'rtl'):
                    raise ValueError(
                        f'RDF 1.2: base direction must be "ltr" or "rtl", got {direction!r} in @{lang_dir}'
                    )
                return Literal(value, datatype=encode_dirlang_datatype(language.lower(), direction))
            return Literal(value, lang=lang_dir)
        if suffix.startswith('^^<') and suffix.endswith('>'):
            datatype = _iri_node(suffix[3:-1])
            if str(datatype) in _LANG_STRING_TYPES:
                # rdf:langString / rdf:dirLangString literals carry a language tag (and direction); `"x"^^rdf:dirLangString` is
                # not one (RDF 1.2 Concepts sec 3.3) (GitHub issue #73)
                raise ValueError(f"a literal typed {datatype} needs a language tag, not ^^: {token!r}")
            return Literal(value, datatype=datatype)
        if suffix:
            raise ValueError(f"unexpected text after a literal: {suffix!r}")
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
        if isinstance(s, Literal):
            raise ValueError("a literal cannot be a subject")
        if not isinstance(p, URIRef):
            raise ValueError("a predicate must be an IRI")

        g = None
        if quads:
            # N-Quads: optional graph label before '.': an IRI or a blank node, never a literal
            tok_g, j = _consume_nt_term(stripped, i)
            if tok_g is not None:
                g = _token_to_node(tok_g)
                if isinstance(g, (Literal, TripleTerm)):
                    raise ValueError(f"a graph label must be an IRI or a blank node, got {tok_g!r}")
                i = j
        # exactly one '.', then nothing but whitespace or a comment
        tail = stripped[i:].lstrip()
        if not tail.startswith('.'):
            raise ValueError("expected '.' at the end of the statement" if not tail else f"unexpected text {tail[:30]!r} (one statement per line, ended by '.')")
        tail = tail[1:].strip()
        if tail and not tail.startswith('#'):
            raise ValueError(f"unexpected text after the final '.': {tail[:30]!r}")
        return (s, p, o, g) if quads else (s, p, o)

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
    starlayer.graph.model.conformance). Per the grammar, VERSION - if present -
    must be the first statement, so only the first non-blank/comment line is
    examined.

    Args:
        text: The N-Triples/N-Quads 1.2 document text to scan.

    Returns:
        The declared VERSION label (e.g. "1.2-basic"), or None if the
        document's first non-blank/comment line isn't a VERSION line.
    """
    for line in _lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        m = _VERSION_LINE_RE.match(stripped)
        return m.group(2) if m else None
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

@per_document
def parse_ntriples12(text: str) -> list[tuple]:
    """Parse N-Triples 1.2 text; return list of (s, p, o) triples.

    Subjects and objects may be TripleTerm instances.

    Args:
        text: The N-Triples 1.2 document text to parse.

    Returns:
        A list of (s, p, o) triples, one per non-blank/comment line.
    """
    triples = []
    for lineno, line in enumerate(_lines(text), 1):
        result = _parse_nt_line(line, lineno, quads=False)
        if result is not None:
            triples.append(result)
    return triples


@per_document
def parse_nquads12(text: str) -> list[tuple]:
    """Parse N-Quads 1.2 text; return list of (s, p, o, g) quads.

    Subjects and objects may be TripleTerm instances.

    Args:
        text: The N-Quads 1.2 document text to parse.

    Returns:
        A list of (s, p, o, g) quads, one per non-blank/comment line - g
        is a URIRef for a named graph, None for the default graph.
    """
    quads = []
    for lineno, line in enumerate(_lines(text), 1):
        result = _parse_nt_line(line, lineno, quads=True)
        if result is not None:
            quads.append(result)
    return quads
