"""SPARQL text helpers for ``run.py`` and ``shacl_engine.oxigraph_view``: the ``VERSION`` prologue directive (SPARQL 1.2 Query
sec 4.3: ``Prologue ::= ( BaseDecl | PrefixDecl | VersionDecl )*``, in any order, repeatable) and pre-binding a variable by a
``VALUES`` clause when the engine's ``substitutions`` cannot.

Oxigraph reads ``VERSION`` natively, so the text is sent unmodified; the check only surfaces the conformance warning the engine
never raises.
"""

from __future__ import annotations

import re

# Whitespace and ``#`` comments (a comment runs to the end of the line; SPARQL
# treats both as whitespace between tokens, so a header comment may precede
# or sit between prologue declarations).
_LEADING_WS_RE = re.compile(r'(?:\s|#[^\n\r]*)*')
# VersionSpecifier ::= STRING_LITERAL1 | STRING_LITERAL2: one quote character
# on each side, no raw newline, backslash escapes allowed inside. A
# triple-quoted form is not a VersionSpecifier, so it is excluded here and left
# for the parser to reject with its own error.
_VERSION_DECL_RE = re.compile(
    r"""VERSION\s+(?!\"\"\"|\'\'\')(?:"((?:[^"\\\n\r]|\\.)*)"|'((?:[^'\\\n\r]|\\.)*)')""",
    re.IGNORECASE,
)
# BaseDecl/PrefixDecl recognized just well enough to skip over them intact -
# not a full IRIREF/PN_PREFIX grammar (this module's own design note above:
# a deliberately simple scanner). "BASE <iri>" and "PREFIX name: <iri>",
# the overwhelming real-world shape of both (a bare, unescaped IRIREF - no
# SPARQL grammar permits a literal ">" inside one at all, so the naive
# "up to the next '>'" delimiter is exactly as safe as a real IRIREF scan).
_BASE_DECL_RE = re.compile(r'BASE\s*<[^>]*>', re.IGNORECASE)
_PREFIX_DECL_RE = re.compile(r'PREFIX\s+[^\s:]*:\s*<[^>]*>', re.IGNORECASE)


def strip_version_directive(query: str) -> tuple[str, str | None]:
    """Strip every ``VERSION "label"`` directive out of the leading
    prologue, leaving any ``BASE``/``PREFIX`` declarations - and their
    original relative order - untouched.

    If more than one ``VersionDecl`` is present (legal per the grammar's own
    ``( ... )*``, though the spec gives no precedence rule for it), the
    *last* one scanned is returned - an arbitrary but documented choice for
    a case real queries are not expected to actually use.

    Args:
        query: The raw SPARQL 1.2 query/update text, possibly carrying one
            or more leading ``VERSION`` directives.

    Returns:
        A ``(stripped_query, label)`` tuple: the query text with every
        ``VersionDecl`` removed, and the declared version label, or
        ``None`` if no ``VERSION`` directive was present.
    """
    out_parts: list[str] = []
    pos = 0
    label: str | None = None
    while True:
        pos = _LEADING_WS_RE.match(query, pos).end()
        m = _VERSION_DECL_RE.match(query, pos)
        if m:
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            label = re.sub(r'\\(.)', r'\1', raw)
            pos = m.end()
            continue
        m = _BASE_DECL_RE.match(query, pos) or _PREFIX_DECL_RE.match(query, pos)
        if m:
            out_parts.append(query[pos:m.end()])
            pos = m.end()
            continue
        break
    if label is None:
        return query, None
    out_parts.append(query[pos:])
    return ' '.join(out_parts), label


def check_native_version_conformance(text: str) -> None:
    """Warn (``SPARQL12ConformanceWarning``) when a ``VERSION`` directive in raw SPARQL text does not match what the text uses.

    Oxigraph reads ``VERSION`` natively, so the text is sent unmodified, but the engine returns no signal for a mismatch; this
    is the only place the warning comes from. The directive is not stripped.

    Args:
        text: The raw SPARQL query or update text to check.
    """
    from starlayer.graph.model.conformance import (
        SPARQL12ConformanceWarning,
        check_version_conformance,
    )

    _, declared_version = strip_version_directive(text)
    if declared_version is None:
        return
    # a ``--`` or ``~`` inside a string, IRI or comment is not RDF 1.2 syntax
    text = re.sub(
        r"(?s)<[^<>\s\"{}|^`\\]*>|\"\"\"(?:[^\"\\]|\\.|\"(?!\"\"))*\"\"\"|'''(?:[^'\\]|\\.|'(?!''))*'''"
        r"|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|#[^\n]*",
        " ",
        text,
    )
    check_version_conformance(
        declared_version,
        uses_triple_term=bool(
            "<<(" in text or re.search(r'<<[^(]|\{\|', text) or '~' in text
        ),
        uses_dirlangstring='--' in text,
        context='SPARQL query',
        warning_class=SPARQL12ConformanceWarning,
    )


def inject_init_bindings(sparql: str, init_bindings: dict[str, str]) -> str:
    """The query with ``init_bindings`` (variable name -> the term as SPARQL writes it) applied as ``VALUES (?a ?b) { (x y) }``
    at the start of the outermost ``WHERE`` group.

    A native store has no engine-level way to pre-bind a variable, and silently ignoring ``initBindings`` gave answers that
    disagree with the bindings; SHACL's SPARQL constraints (``sh:sparql``, ``$this``) pass the focus node this way
    (GitHub issue #98). ``VALUES`` at the head of the group joins to everything that follows, which is what a pre-binding
    means. Strings, IRIs and comments are skipped when looking for the group.
    """
    names = ['?' + str(key).lstrip('?$') for key in init_bindings]
    terms = list(init_bindings.values())
    values = f" VALUES ({' '.join(names)}) {{ ({' '.join(terms)}) }} "

    iri = re.compile(r'<[^<>"{}|^`\\\s]*>')
    n, i, depth = len(sparql), 0, 0
    template_pending = False  # CONSTRUCT { template } WHERE { group }: the first brace is the template, not the group

    def keyword_at(pos: int, word: str) -> bool:
        return (
            sparql[pos:pos + len(word)].upper() == word
            and not (pos > 0 and (sparql[pos - 1].isalnum() or sparql[pos - 1] in '_?$:'))
            and not sparql[pos + len(word):pos + len(word) + 1].isalnum()
        )

    while i < n:
        c = sparql[i]
        if c == '#':
            while i < n and sparql[i] not in '\r\n':
                i += 1
            continue
        if c in '"\'':
            q = c * 3 if sparql.startswith(c * 3, i) else c
            i += len(q)
            while i < n and not sparql.startswith(q, i):
                i += 2 if sparql[i] == '\\' else 1
            i += len(q)
            continue
        if c == '<':
            m = iri.match(sparql, i)
            if m:
                i = m.end()
                continue
        if depth == 0 and keyword_at(i, 'CONSTRUCT'):
            rest = sparql[i + 9:].lstrip()
            template_pending = not rest[:5].upper() == 'WHERE'
            i += 9
            continue
        if c == '{':
            if depth == 0 and not template_pending:
                return sparql[:i + 1] + values + sparql[i + 1:]
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                template_pending = False
        i += 1
    raise ValueError("initBindings: could not find the query's WHERE group")
