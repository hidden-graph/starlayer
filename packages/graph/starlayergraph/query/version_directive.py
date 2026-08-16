"""SPARQL 1.2 Query prologue's optional leading ``VERSION "label"``
directive (SPARQL 1.2 Query sec 4.3), e.g. the spec's own example::

    VERSION "1.2"
    PREFIX : <http://example/>
    SELECT ...

Not real SPARQL 1.1 syntax at all — rdflib's parser (and
``starsparql``'s own grammar, which extends it) has no notion of this
directive and raises a ``ParseException`` on it unconditionally, so it must
always be stripped before ordinary parsing, regardless of pipeline or
backend.

Kept as its own small, self-contained module (not part of the retired
``sparql12_to_11.py`` text rewriter it used to live in): a leading,
unambiguously-anchored prefix strip has none of the nested/ambiguous-
structure fragility (ordering-sensitive splicing, join-order bugs) that
motivated replacing the rest of that module with a real grammar/algebra
pipeline — there's no structure here to get wrong, just a fixed prologue
token to recognize and remove.

See ``starlayergraph.model.conformance`` for what happens with the extracted
label (a warning, never a hard error, if it doesn't match what the query
actually uses), and ``starlayergraph.backends.native.check_native_version_conformance``
for the equivalent used by the native rdf-1.2 backend, which sends VERSION
straight through to the endpoint unmodified instead of stripping it.
"""

from __future__ import annotations

import re

_VERSION_DIRECTIVE_RE = re.compile(r'^\s*VERSION\s+([\'"])((?:(?!\1).)*)\1\s*', re.IGNORECASE)


def strip_version_directive(query: str) -> tuple[str, str | None]:
    """Strip a leading ``VERSION "label"`` prologue directive.

    Returns ``(query_with_directive_removed, label_or_None)``.
    """
    m = _VERSION_DIRECTIVE_RE.match(query)
    if not m:
        return query, None
    return query[m.end():], m.group(2)


def contains_triple_term(node) -> bool:
    """Recursively check whether a parsed SPARQL 1.2 parse tree/algebra
    contains a ``TripleTermNode`` anywhere — used for VERSION-directive
    conformance checking (see ``starlayergraph.model.conformance``). More
    reliable than a text-presence heuristic: this walks the real parsed
    structure, so it can't be fooled by e.g. ``<<(`` appearing inside a
    string literal or comment.
    """
    from rdflib.plugins.sparql.parserutils import CompValue
    from starsparql.triple_term import TripleTermNode

    if isinstance(node, TripleTermNode):
        return True
    if isinstance(node, CompValue):
        return any(contains_triple_term(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(contains_triple_term(item) for item in node)
    return False
