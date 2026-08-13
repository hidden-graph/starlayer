"""
starlayergraph.model.triple

Core RDF 1.2 types: TripleTerm.
"""

from rdflib import BNode, URIRef


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
        # RDF 1.2 (17.4.6, TRIPLE()): a triple term's subject must be an IRI
        # or blank node, its predicate an IRI - never a Literal in either
        # position, and never itself a triple term (triple terms are only
        # ever legal in object position). Mirrors the identical validation
        # the in-memory backend's own TRIPLE() implementation already
        # enforces (starlayergraph/query/custom_functions.py::_tt_hash_fn) - this
        # constructor is the other place a TripleTerm comes into being, e.g.
        # decoding a native-backend query result back into a real Python
        # object, so it needs the same check independently. Confirmed via a
        # live Fuseki 5.5.0 bug (docs/fuseki-upstream-issues.md, Issue 1)
        # that a native backend can return an invalid triple term (a
        # Literal-valued subject) with no error of its own - this
        # constructor must not then silently accept it and construct an
        # equally-invalid TripleTerm object.
        if not isinstance(subject, (URIRef, BNode)):
            raise ValueError(
                "RDF 1.2: the subject of a triple term must be an IRI or blank node, "
                f"not {type(subject).__name__} ({subject!r})."
            )
        if not isinstance(predicate, URIRef):
            raise ValueError(
                "RDF 1.2: the predicate of a triple term must be an IRI, "
                f"not {type(predicate).__name__} ({predicate!r})."
            )
        self.subject = subject
        self.predicate = predicate
        self.object = obj
        self._namespace_manager = None

    def __setattr__(self, name, value):
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
        if isinstance(other, TripleTerm):
            return self._key() == other._key()
        if isinstance(other, tuple) and len(other) == 3:
            return self._key() == TripleTerm(*other)._key()
        return NotImplemented

    def __hash__(self):
        return hash(self._key())

    def __iter__(self):
        yield self.subject
        yield self.predicate
        yield self.object

    def n3(self, namespace_manager=None):
        nm = namespace_manager if namespace_manager is not None else self._namespace_manager
        return f'<<( {self.subject.n3(nm)} {self.predicate.n3(nm)} {self.object.n3(nm)} )>>'

    def __str__(self):
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
        fields = ', '.join(
            repr(getattr(self, name, '<unset>'))
            for name in ('subject', 'predicate', 'object')
        )
        return f'TripleTerm({fields})'


