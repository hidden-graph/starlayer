"""The RDFS closure ``infer(ENTAILMENT.RDFS)`` materializes, computed on pyoxigraph terms so it needs no rdflib.

It reproduces what ``owlrl``'s ``RDFS_Semantics`` derives with its once-only literal rule off, no axiomatic triples and
no datatype axioms (rdf1, rdfs2 to rdfs11 and rdfs13, rdfs4 only for terms that occur in a triple), because that is the
closure StarLayer shipped and the SHACL engine depends on; ``tests/graph/unit/test_rdfs_closure.py`` compares the two.
Generalized triples (a literal subject, a blank-node predicate) take part in the rules, as in owlrl, and are dropped from the
result, as are triples that mention a triple term (owlrl saw those through a decomposition and the bridge drops them).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_TYPE = ox.NamedNode(_RDF + "type")
_PROPERTY = ox.NamedNode(_RDF + "Property")
_RESOURCE = ox.NamedNode(_RDFS + "Resource")
_CLASS = ox.NamedNode(_RDFS + "Class")
_LITERAL = ox.NamedNode(_RDFS + "Literal")
_DATATYPE = ox.NamedNode(_RDFS + "Datatype")
_CONTAINER_MEMBERSHIP = ox.NamedNode(_RDFS + "ContainerMembershipProperty")
_MEMBER = ox.NamedNode(_RDFS + "member")
_DOMAIN = ox.NamedNode(_RDFS + "domain")
_RANGE = ox.NamedNode(_RDFS + "range")
_SUB_PROPERTY = ox.NamedNode(_RDFS + "subPropertyOf")
_SUB_CLASS = ox.NamedNode(_RDFS + "subClassOf")


def _inner_terms(term: Any) -> Iterable[Any]:
    """The terms inside a triple term, at any depth."""
    if isinstance(term, ox.Triple):
        for part in (term.subject, term.predicate, term.object):
            yield part
            yield from _inner_terms(part)


class _Closure:
    def __init__(self, triples: Iterable[tuple]) -> None:
        self.all: set = set()
        self.by_predicate: dict = defaultdict(set)  # p -> {(s, o)}
        self.instances: dict = defaultdict(set)  # class -> {x : x rdf:type class}
        self.out: dict = {_SUB_CLASS: defaultdict(set), _SUB_PROPERTY: defaultdict(set), _DOMAIN: defaultdict(set), _RANGE: defaultdict(set)}
        self.into: dict = {_SUB_CLASS: defaultdict(set), _SUB_PROPERTY: defaultdict(set)}
        self.queue: list = []
        for t in triples:
            self.add(t)

    def add(self, t: tuple) -> None:
        s, p, o = t
        if t in self.all or isinstance(p, ox.Literal):
            return
        self.all.add(t)
        self.by_predicate[p].add((s, o))
        if p == _TYPE:
            self.instances[o].add(s)
        if p in self.out:
            self.out[p][s].add(o)
        if p in self.into:
            self.into[p][o].add(s)
        self.queue.append(t)

    def run(self) -> None:
        queue = self.queue
        while queue:
            self.apply(queue.pop())

    def apply(self, t: tuple) -> None:
        s, p, o = t
        add = self.add
        add((p, _TYPE, _PROPERTY))
        for node in (s, o):
            add((node, _TYPE, _RESOURCE))
            for inner in _inner_terms(node):
                add((inner, _TYPE, _RESOURCE))
        for cls in tuple(self.out[_DOMAIN].get(p, ())):
            add((s, _TYPE, cls))
        for cls in tuple(self.out[_RANGE].get(p, ())):
            add((o, _TYPE, cls))
        for q in tuple(self.out[_SUB_PROPERTY].get(p, ())):
            add((s, q, o))
        if p == _TYPE:
            for sup in tuple(self.out[_SUB_CLASS].get(o, ())):
                add((s, _TYPE, sup))
            if o == _PROPERTY:
                add((s, _SUB_PROPERTY, s))
            elif o == _CLASS:
                add((s, _SUB_CLASS, _RESOURCE))
                add((s, _SUB_CLASS, s))
            elif o == _CONTAINER_MEMBERSHIP:
                add((s, _SUB_PROPERTY, _MEMBER))
            elif o == _DATATYPE:
                add((s, _SUB_CLASS, _LITERAL))
        elif p == _DOMAIN:
            for user, _ in tuple(self.by_predicate.get(s, ())):
                add((user, _TYPE, o))
        elif p == _RANGE:
            for _, value in tuple(self.by_predicate.get(s, ())):
                add((value, _TYPE, o))
        elif p == _SUB_PROPERTY:
            for sup in tuple(self.out[_SUB_PROPERTY].get(o, ())):
                add((s, _SUB_PROPERTY, sup))
            for sub in tuple(self.into[_SUB_PROPERTY].get(s, ())):
                add((sub, _SUB_PROPERTY, o))
            for subject, value in tuple(self.by_predicate.get(s, ())):
                add((subject, o, value))
        elif p == _SUB_CLASS:
            for instance in tuple(self.instances.get(s, ())):
                add((instance, _TYPE, o))
            for sup in tuple(self.out[_SUB_CLASS].get(o, ())):
                add((s, _SUB_CLASS, sup))
            for sub in tuple(self.into[_SUB_CLASS].get(s, ())):
                add((sub, _SUB_CLASS, o))


def _mentions_triple_term(t: tuple) -> bool:
    return any(isinstance(x, ox.Triple) for x in t)


def rdfs_delta(triples: Iterable[tuple]) -> set[tuple]:
    """The triples the RDFS closure of ``triples`` adds (not the ones already there)."""
    original = set(triples)
    closure = _Closure(original)
    closure.run()
    return {
        t
        for t in closure.all - original
        if not isinstance(t[0], ox.Literal) and isinstance(t[1], ox.NamedNode) and not _mentions_triple_term(t)
    }
