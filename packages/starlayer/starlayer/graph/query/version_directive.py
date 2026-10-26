"""SPARQL 1.2 Query prologue's optional ``VERSION "label"`` directive
(SPARQL 1.2 Query sec 4.3), e.g. the spec's own example::

    VERSION "1.2"
    PREFIX : <http://example/>
    SELECT ...

Not real SPARQL 1.1 syntax at all — rdflib's parser (and
``starlayer.sparql``'s own grammar, which extends it) has no notion of this
directive and raises a ``ParseException`` on it unconditionally, so it must
always be stripped before ordinary parsing, regardless of pipeline or
backend.

**``VERSION`` is not always the first token.** Per the real grammar
(``tests/graph/vendor/spec_snapshots/sparql12-query.txt``):
``Prologue ::= ( BaseDecl | PrefixDecl | VersionDecl )*`` - the three
prologue declaration kinds may appear in *any* order and ``VersionDecl`` may
appear more than once. That's why this module scans the whole leading
prologue token-by-token (recognizing ``BaseDecl``/``PrefixDecl`` well enough
to skip over them unmodified, removing only ``VersionDecl`` tokens wherever
they appear) rather than anchor-matching ``VERSION`` as the very first
token of the document, which the grammar does not guarantee.

Kept as its own small, self-contained module (not part of the retired
``sparql12_to_11.py`` text rewriter it used to live in): a prologue-only
token scan has none of the nested/ambiguous-structure fragility (ordering-
sensitive splicing, join-order bugs) that motivated replacing the rest of
that module with a real grammar/algebra pipeline — there's no *query body*
structure to get wrong here, only the three known prologue declaration
shapes to recognize and either pass through (``BaseDecl``/``PrefixDecl``) or
remove (``VersionDecl``).

See ``starlayer.graph.model.conformance`` for what happens with the extracted
label (a warning, never a hard error, if it doesn't match what the query
actually uses), and ``starlayer.graph.backends.native.check_native_version_conformance``
for the equivalent used by the native rdf-1.2 backend, which sends VERSION
straight through to the endpoint unmodified instead of stripping it.
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


def contains_triple_term(node) -> bool:
    """Recursively check whether a parsed SPARQL 1.2 parse tree/algebra
    contains a ``TripleTermNode`` anywhere — used for VERSION-directive
    conformance checking (see ``starlayer.graph.model.conformance``). More
    reliable than a text-presence heuristic: this walks the real parsed
    structure, so it can't be fooled by e.g. ``<<(`` appearing inside a
    string literal or comment.

    Args:
        node: A parse tree/algebra node, list, tuple, or leaf value to
            search.

    Returns:
        True if a ``TripleTermNode`` appears anywhere in ``node``.
    """
    from rdflib.plugins.sparql.parserutils import CompValue

    from starlayer.sparql.triple_term import TripleTermNode

    if isinstance(node, TripleTermNode):
        return True
    if isinstance(node, CompValue):
        return any(contains_triple_term(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(contains_triple_term(item) for item in node)
    return False
