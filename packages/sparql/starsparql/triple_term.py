"""``TripleTermNode`` — the algebra-tree representation of a SPARQL 1.2
``<<( s p o )>>``/``TRIPLE(s, p, o)`` triple term.

A plain ``CompValue('TripleTerm', subject=, predicate=, object=)`` node
cannot survive rdflib's own ``algebra.translateQuery``/``translateUpdate``
unmodified: ``reorderTriples``/``_knownTerms`` (BGP join-order optimization)
require every triple-pattern term to be hashable, and a bare ``CompValue``
(an ``OrderedDict`` subclass) is not. A further, less obvious requirement
found empirically: when two triples tie on ``_knownTerms``' sort key (common
for fully-ground triples), rdflib's own sort falls back to comparing the raw
triples with ``<``, so the term must be *orderable* too, not merely hashable.

Subclassing ``CompValue`` (rather than substituting some other, unrelated
hashable object) is what makes this safe on both fronts: rdflib's
``_addVars``/``analyse`` bookkeeping pass walks the tree via a generic
recursive traversal (``_traverseAgg``) that is closed over
``CompValue``/``list``/``tuple``/``ParseResults`` — nothing else. A
non-``CompValue`` proxy would make any ``Variable`` nested inside a
pattern-with-variables triple term invisible to that traversal, silently
under-computing ``_vars`` on every ancestor node. A ``CompValue`` subclass
does not have this problem: the existing generic recursion already finds
nested variables correctly, for free.
"""

from __future__ import annotations

from rdflib.plugins.sparql.parserutils import CompValue


class InvalidTripleTermError(ValueError):
    """A triple term's own subject or predicate would themselves be a triple
    term — illegal per RDF 1.2's grammar
    (https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm):

        tripleTerm ::= '<<(' ttSubject verb ttObject ')>>'
        ttSubject  ::= iri | BlankNode
        ttObject   ::= iri | BlankNode | literal | tripleTerm

    Neither ``ttSubject`` nor ``verb`` (the predicate production) has a
    ``tripleTerm`` alternative — unconditionally, not just when the triple
    term is used as an expression value. Nesting a triple term is legal
    only in *object* position, where ``ttObject`` explicitly allows it.

    Confirmed empirically (2026-08-08) that a query pattern using the
    illegal shape still *parses* as SPARQL syntax (the W3C SPARQL 1.2 test
    suite even labels two such fixtures, `compound-tripleterm-subject`/
    `nested-tripleterm-02`, as ``PositiveSyntaxTest``) — but "SPARQL's
    grammar parses this text" and "this represents a valid RDF 1.2 term"
    are different claims, and only the first is true here. A pattern using
    this shape can never match any real, valid RDF 1.2 data, since no such
    data could ever exist. This project previously (mis)read those
    `PositiveSyntaxTest` fixtures as evidence the shape should be *accepted*
    (see git history / CLAUDE.md's now-superseded finding #20) and widened
    the pattern-position subject grammar accordingly — confirmed as a real
    bug via a live Oxigraph instance rejecting exactly this shape
    (`HTTP 500`) while this project's own construction path did not reject
    it at all; see the sibling `starlayergraph` repo's
    `docs/oxigraph-upstream-issues.md` Issue 1 for the full investigation
    (retracted as an Oxigraph bug, redirected here instead).

    Deliberately raised here — at ``TripleTermNode`` construction — rather
    than only in the SPARQL grammar (`grammar12.py`), so this is a hard
    backstop regardless of construction path: parsed from SPARQL 1.2 text,
    decoded from RDF (`from_rdf.py`), or built programmatically. The
    grammar's own parse-time acceptance of the two `PositiveSyntaxTest`
    fixtures above is left unchanged (matching what SPARQL's own grammar
    apparently permits syntactically) — this is the semantic-level check
    that catches what parsing alone can't.
    """


def _reject_nested_triple_term(value, position: str, node: "TripleTermNode") -> None:
    if isinstance(value, TripleTermNode):
        raise InvalidTripleTermError(
            f"RDF 1.2: a triple term's {position} may never itself be a triple term "
            f"(nesting a triple term is legal only in object position) — "
            f"got {value!r} as the {position} of {node!r}"
        )


def _sort_key(value):
    """A stable, total-ordering key for one subject/predicate/object slot.

    Always a plain ``str`` — never the raw nested tuple ``TripleTermNode
    ._sort_key()`` produces — which matters more than it looks: two
    *sibling* triples in the same BGP can tie on rdflib's outer sort key
    (`_knownTerms`) and fall back to comparing raw triples slot-by-slot
    with ``<``. If triple A's subject is a ground triple term with a
    *nested* triple-term subject (recursing into another 3-tuple) while
    triple B's subject in that same slot is an ordinary, non-nested term
    (a plain ``repr()`` string), Python ends up comparing a ``tuple``
    against a ``str`` at that slot — a real, reproducible ``TypeError``
    confirmed via the W3C test `compound-tripleterm-subject`, not a
    hypothetical. Wrapping the nested case in `repr(...)` keeps every
    slot's key a `str` unconditionally, so two sort keys are always
    comparable regardless of how deeply either side nests — the actual
    order chosen still doesn't matter semantically, only that comparisons
    never raise.
    """
    if isinstance(value, TripleTermNode):
        return repr(value._sort_key())
    return repr(value)


class TripleTermNode(CompValue):
    """A ``CompValue`` subclass for SPARQL 1.2 triple terms — see module
    docstring for why plain ``CompValue`` isn't sufficient here specifically
    (every other operator/expression name in this project's vocabulary is
    fine as a bare ``CompValue``)."""

    def _sort_key(self):
        return (
            _sort_key(self.get("subject")),
            _sort_key(self.get("predicate")),
            _sort_key(self.get("object")),
        )

    def __hash__(self):
        return hash(self._sort_key())

    def __eq__(self, other):
        if isinstance(other, TripleTermNode):
            return self._sort_key() == other._sort_key()
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, TripleTermNode):
            return self._sort_key() < other._sort_key()
        return NotImplemented

    def validate(self) -> "TripleTermNode":
        """Raise ``InvalidTripleTermError`` if this node's own subject or
        predicate is itself a triple term — see that exception's docstring
        for why. Not enforced automatically on every dict mutation (kept
        explicit rather than hooking ``update()``/``__setitem__``, to avoid
        surprising ``CompValue``'s existing, delicately-hash/order-balanced
        behavior) — call this at every construction site instead:
        ``grammar12.py``'s ``_promote`` and ``from_rdf.py``'s ``TripleTerm``
        decode branch both do. Returns ``self`` so it can be chained
        directly onto a construction call.
        """
        _reject_nested_triple_term(self.get("subject"), "subject", self)
        _reject_nested_triple_term(self.get("predicate"), "predicate", self)
        return self
