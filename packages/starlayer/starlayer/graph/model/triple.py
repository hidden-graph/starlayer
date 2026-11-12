"""
starlayer.graph.model.triple

Core RDF 1.2 types: TripleTerm.
"""

import sys

import pyoxigraph as ox


def _iri_and_bnode_types() -> tuple[tuple[type, ...], tuple[type, ...]]:
    """The classes that count as an IRI and as a blank node: pyoxigraph's always, rdflib's when rdflib has been imported (rdflib is an
    optional extra, so it is never imported here; a user holding an rdflib term has imported it)."""
    iri: tuple[type, ...] = (ox.NamedNode,)
    bnode: tuple[type, ...] = (ox.BlankNode,)
    rdflib = sys.modules.get("rdflib")
    if rdflib is not None:
        iri += (rdflib.URIRef,)
        bnode += (rdflib.BNode,)
    return iri, bnode


def _n3(term, namespace_manager):
    """N3 text of a component: rdflib terms have ``n3``; a pyoxigraph term's ``str`` is its N-Triples form."""
    n3 = getattr(term, "n3", None)
    return n3(namespace_manager) if callable(n3) else str(term)


class TripleTerm:
    """An RDF 1.2 triple term — a triple used as a resource.

    Value-typed: two instances with the same (s, p, o) are equal and have the
    same hash. A plain Python 3-tuple is coerced to TripleTerm wherever the
    StarLayerGraph API expects a node.

    _namespace_manager is set by StarLayerGraph._restore() when returning a
    TripleTerm from a query result so that __str__ can emit prefixed names.
    It is excluded from equality and hashing.
    """
    __slots__ = ('subject', 'predicate', 'object', '_namespace_manager')

    # Slots that may only be written once (during __init__)
    _IMMUTABLE = frozenset({'subject', 'predicate', 'object'})

    def __init__(self, subject, predicate, obj):
        """Build a triple term; a subject or predicate that RDF 1.2 does not allow raises ValueError."""
        # RDF 1.2 (17.4.6, TRIPLE()): a triple term's subject must be an IRI
        # or blank node, its predicate an IRI - never a Literal in either
        # position, and never itself a triple term (triple terms are only
        # ever legal in object position). Mirrors the identical validation
        # the in-memory backend's own TRIPLE() implementation already
        # enforces (starlayer.graph/query/custom_functions.py::_tt_hash_fn) - this
        # constructor is the other place a TripleTerm comes into being, e.g.
        # decoding a native-backend query result back into a real Python
        # object, so it needs the same check independently. Confirmed via a
        # live Fuseki 5.5.0 bug (docs/upstream-issues/fuseki-upstream-issues.md, Issue 1)
        # that a native backend can return an invalid triple term (a
        # Literal-valued subject) with no error of its own - this
        # constructor must not then silently accept it and construct an
        # equally-invalid TripleTerm object.
        iri_types, bnode_types = _iri_and_bnode_types()
        if not isinstance(subject, iri_types + bnode_types):
            raise ValueError(
                "RDF 1.2: the subject of a triple term must be an IRI or blank node, "
                f"not {type(subject).__name__} ({subject!r})."
            )
        if not isinstance(predicate, iri_types):
            raise ValueError(
                "RDF 1.2: the predicate of a triple term must be an IRI, "
                f"not {type(predicate).__name__} ({predicate!r})."
            )
        self.subject = subject
        self.predicate = predicate
        self.object = obj
        self._namespace_manager = None

    def __setattr__(self, name, value):
        """Keep subject, predicate and object fixed after construction, as a value-typed triple term needs."""
        if name in TripleTerm._IMMUTABLE:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                object.__setattr__(self, name, value)
                return
            raise AttributeError(f"TripleTerm is immutable; cannot reassign '{name}'")
        object.__setattr__(self, name, value)

    def _key(self):
        s = self.subject._key() if isinstance(self.subject, TripleTerm) else self.subject
        o = self.object._key()  if isinstance(self.object,  TripleTerm) else self.object
        return (s, self.predicate, o)

    def __eq__(self, other):
        """Equal to a TripleTerm with the same (s, p, o), or to a 3-tuple that makes the same triple term."""
        if isinstance(other, TripleTerm):
            return self._key() == other._key()
        if isinstance(other, tuple) and len(other) == 3:
            try:
                return self._key() == TripleTerm(*other)._key()
            except ValueError:  # a 3-tuple that cannot be a triple is simply not equal
                return False
        return NotImplemented

    def __hash__(self):
        """Hash of the (s, p, o) key, so equal triple terms hash alike."""
        return hash(self._key())

    def __iter__(self):
        """Yield subject, predicate, object, so a triple term unpacks like a 3-tuple."""
        yield self.subject
        yield self.predicate
        yield self.object

    def n3(self, namespace_manager=None):
        """Returns the N3/Turtle-1.2 (``<<( s p o )>>``) text form."""
        nm = namespace_manager if namespace_manager is not None else self._namespace_manager
        return f'<<( {_n3(self.subject, nm)} {_n3(self.predicate, nm)} {_n3(self.object, nm)} )>>'

    def __str__(self):
        """The N3 text form from n3(); a half-constructed instance falls back to repr()."""
        try:
            return self.n3()
        except AttributeError:
            # __init__ rejects an invalid subject (see above) before ever
            # assigning any of __slots__ - so an instance can reach here
            # half-constructed (e.g. a traceback formatter repr()'ing the
            # failed __init__ call's own `self` argument). Falls back to
            # __repr__'s own equally-defensive formatting rather than
            # raising a second, unrelated AttributeError on top of
            # whatever real error is already being reported.
            return repr(self)

    def __repr__(self):
        """Constructor-style text; a field not yet assigned shows as '<unset>' instead of raising."""
        fields = ', '.join(
            repr(getattr(self, name, '<unset>'))
            for name in ('subject', 'predicate', 'object')
        )
        return f'TripleTerm({fields})'


