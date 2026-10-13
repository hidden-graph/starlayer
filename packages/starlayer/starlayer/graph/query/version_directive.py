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

**``VERSION`` is not always the first token** - confirmed directly against
the real grammar (``tests/graph/vendor/spec_snapshots/sparql12-query.txt``):
``Prologue ::= ( BaseDecl | PrefixDecl | VersionDecl )*`` - the three
prologue declaration kinds may appear in *any* order and ``VersionDecl`` may
appear more than once. Found 2026-10-13, via the W3C suite's own `version`
category (``version-02`` through ``version-06``: ``VERSION`` after a
``PREFIX``, a single-quoted form, and one fixture with three separate
``VERSION`` declarations interleaved with a ``PREFIX``) - this module's
original implementation only ever matched ``VERSION`` as the very first
token, which every one of those fixtures violates. Fixed by scanning the
whole leading prologue token-by-token (recognizing ``BaseDecl``/
``PrefixDecl`` well enough to skip over them unmodified, removing only
``VersionDecl`` tokens wherever they appear) rather than a single anchored
match - still a deliberately simple scanner, not a full grammar parser (see
the module's own prior design note below), but one that actually matches
the real ``Prologue`` production instead of a stricter-than-spec guess at
it.

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

_LEADING_WS_RE = re.compile(r'\s*', re.DOTALL)
_VERSION_DECL_RE = re.compile(r'VERSION\s+([\'"])((?:(?!\1).)*)\1', re.IGNORECASE)
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

    Returns ``(query_with_version_directives_removed, label_or_None)``. If
    more than one ``VersionDecl`` is present (legal per the grammar's own
    ``( ... )*``, though the spec gives no precedence rule for it), the
    *last* one scanned is returned - an arbitrary but documented choice for
    a case real queries are not expected to actually use.
    """
    out_parts: list[str] = []
    pos = 0
    label: str | None = None
    while True:
        pos = _LEADING_WS_RE.match(query, pos).end()
        m = _VERSION_DECL_RE.match(query, pos)
        if m:
            label = m.group(2)
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
