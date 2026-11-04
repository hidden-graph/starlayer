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

from starlayer.graph.oxgraph.sparql_text import strip_version_directive  # noqa: F401  (moved; re-exported)


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
