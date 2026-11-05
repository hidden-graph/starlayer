"""``TripleTermNode``: the SRL syntax tree's form of an RDF 1.2 triple term ``<<( s p o )>>`` / ``TRIPLE(s, p, o)``.

A pattern or template may hold variables inside a triple term, so it cannot be a ``pyoxigraph.Triple`` (which holds only
terms). ``TripleTermNode`` is the parser's own ``Node`` of kind ``TripleTerm`` (the form ``parse_sparql`` gives and the
``sqe:`` / ``srl:`` encoder writes as ``sqe:TripleTerm``) made comparable and hashable, so rules can be compared, deduplicated
and matched against each other. Its three slots hold pyoxigraph terms (and variables) or further triple terms.
"""

from __future__ import annotations

from .parse_sparql import Node

_SLOTS = ("subject", "predicate", "object")


class InvalidTripleTermError(ValueError):
    """A triple term is being used somewhere RDF 1.2 never permits one.

    **1. A triple term's own subject or predicate is itself a triple term.** RDF 1.2's grammar
    (https://www.w3.org/TR/rdf12-turtle/#grammar-production-tripleTerm) has ``ttSubject ::= iri | BlankNode`` and
    ``ttObject ::= iri | BlankNode | literal | tripleTerm``: nesting is legal only in object position. Checked by
    ``TripleTermNode.validate()``.

    **2. A whole triple term is the subject of an ordinary triple.** RDF 1.2 Concepts only forms a triple ``(s, p, o)`` with
    ``s`` an IRI or blank node and ``p`` an IRI; a triple term is legal only as ``o``. For SRL rule sets this is the
    ``triple_term_in_subject`` / ``triple_term_in_predicate`` well-formedness issue (``srl_semantic_checks``).
    """


def _value_key(value):
    """A comparable, hashable key for a term, a node or a list of them."""
    if isinstance(value, ExprNode):
        return value._key()
    if isinstance(value, (list, tuple)):
        return tuple(_value_key(v) for v in value)
    return (type(value).__name__, repr(value))


class ExprNode(Node):
    """A parser ``Node`` of an SRL expression, comparable and hashable by what it holds (the source offset is ignored), so
    rules and rule sets can be compared and a rule set read back from its ``srl:`` tree equals the one it was written from."""

    __slots__ = ()

    def _key(self) -> tuple:
        return (self.kind, tuple((k, _value_key(v)) for k, v in self.f.items()))

    def __hash__(self) -> int:
        return hash(self._key())

    def __eq__(self, other) -> bool:
        if isinstance(other, ExprNode):
            return self._key() == other._key()
        return NotImplemented


class TripleTermNode(ExprNode):
    """A triple term with ``subject``, ``predicate`` and ``object`` slots (``.get(name)`` reads one)."""

    __slots__ = ()

    def __init__(self, kind: str = "TripleTerm", **f):
        super().__init__(kind, **f)

    def get(self, name: str, default=None):
        return self.f.get(name, default)

    def validate(self) -> TripleTermNode:
        """Raise ``InvalidTripleTermError`` if this node's own subject or predicate is itself a triple term.

        Returns:
            self, so it can be chained onto a construction call.
        """
        for slot in ("subject", "predicate"):
            if isinstance(self.f.get(slot), TripleTermNode):
                raise InvalidTripleTermError(
                    f"RDF 1.2: a triple term's {slot} may never itself be a triple term "
                    f"(nesting a triple term is legal only in object position), got {self.f.get(slot)!r} as the {slot} of {self!r}"
                )
        return self
