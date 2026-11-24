"""Which nodes of a shapes graph a scoped meta check covers, and when a proposed edit must go through the full check.

An editor re-checks after every edit and a whole-graph check costs about 3 ms per node shape. The scoped check keeps the whole graph
visible (shape types are inferred from usage elsewhere, prefixes and component parameters are declared elsewhere) and restricts only
the focus nodes the meta-shapes are run on (``api.validate``'s ``focus_filter``). This module decides that set; ``meta.meta_validate``
runs it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.naming import short
from starlayer.shacl.engine.shapes_graphs import (
    _NODE_EXPRESSION_SHAPE_REFERENCES,
    _SHAPE_LIST_REFERENCES,
    _SHAPE_REFERENCES,
)
from starlayer.shacl.engine.terms import OWL, RDF, RDFS, SH, text, to_engine


@dataclass(frozen=True)
class MetaScope:
    """What a meta check covers. ``full``: the whole graph (``nodes`` is then empty); otherwise ``nodes`` are the focus nodes the
    check ran on. ``reasons`` say why, in a stable order (for a full check, the triples that forced it; for a scoped one, the count
    of nodes by origin; "new" are subjects the edit declares that the graph did not have, whose type triple is local)."""

    full: bool
    nodes: tuple = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _FullCheckTriggers:
    """What makes an edit too risky for a narrow check. Kept in one place so the list is easy to maintain."""

    predicates: frozenset
    subject_marks: frozenset  # a node that has one of these properties, or is the value of one, is a prefix holder, component or validator
    subject_types: frozenset


# Why these: the meta-shapes read the whole graph when they decide something about one node, so an edit to anything that other nodes
# inherit changes the result at nodes the edit does not name. Prefix declarations (sh:declare, sh:prefix, sh:namespace, sh:prefixes,
# owl:imports, owl:versionIRI) decide whether every query that uses them parses; component declarations (sh:parameter, the validators,
# rule templates) decide which parameters are known and what their values must be; sh:entailment and sh:shapesGraph change what the
# graph is read as. rdf:type and rdfs:subClassOf are in because a shape's type is partly inferred from them and from how it is used,
# so one such triple can change the checks of nodes that are not in it. The exception is a type or subclass triple on a subject the
# graph does not have yet: nothing else inherits from a node nobody refers to, so declaring a new shape or class is local unless it
# is typed as one of the risky classes (``subject_types``). A removed triple is judged by the triple itself, an added one
# by the triple and by the graph it is added to: a change of a component, of a parameter, of a node that holds prefix declarations or
# of a rule template counts however harmless the predicate.
FULL_CHECK_TRIGGERS = _FullCheckTriggers(
    predicates=frozenset({
        SH.declare, SH.prefix, SH.namespace, SH.prefixes, OWL.imports, OWL.versionIRI,
        SH.parameter, SH.validator, SH.nodeValidator, SH.propertyValidator,
        SH.entailment, SH.shapesGraph, RDF.type, RDFS.subClassOf,
    }),
    subject_marks=frozenset({SH.declare, SH.parameter}),
    subject_types=frozenset({SH.ConstraintComponent, SH.Parameter, SH.SPARQLRuleTemplate, SH.ShapesGraph}),
)

# a node that is the value of one of these is a validator, a parameter or a prefix declaration of somebody else
_INCOMING_MARKS = (SH.validator, SH.nodeValidator, SH.propertyValidator, SH.parameter, SH.declare)
_REFERENCE_PREDICATES = frozenset({SH[name] for name in _SHAPE_REFERENCES} | {SH[name] for name in _SHAPE_LIST_REFERENCES}
                                  | set(_NODE_EXPRESSION_SHAPE_REFERENCES))


def _is_node(term: Any) -> bool:
    return isinstance(term, (ox.NamedNode, ox.BlankNode))


def _subject_is_risky(graph: Any, subject: Any) -> bool:
    """Whether ``subject`` is, in ``graph``, a component, a parameter or validator of one, a prefix holder or a rule template."""
    t = FULL_CHECK_TRIGGERS
    if not _is_node(subject):
        return False
    if any(next(iter(graph.objects(subject, mark)), None) is not None for mark in t.subject_marks):
        return True
    if any(kind in t.subject_types for kind in graph.objects(subject, RDF.type)):
        return True
    return any(next(iter(graph.subjects(link, subject)), None) is not None for link in _INCOMING_MARKS)


def _is_fresh(graph: Any, subject: Any) -> bool:
    """Whether ``graph`` has no triple about ``subject`` as a subject, so an edit that types it cannot change another node's checks."""
    return _is_node(subject) and next(iter(graph.triples((subject, None, None))), None) is None


def _is_new_declaration(graph: Any, triple: tuple) -> bool:
    """An added ``rdf:type`` / ``rdfs:subClassOf`` triple on a fresh subject whose object is not a component, parameter, rule template
    or shapes graph: the commonest edit (a new shape), kept off the full check."""
    s, p, o = triple
    return (p in (RDF.type, RDFS.subClassOf) and o not in FULL_CHECK_TRIGGERS.subject_types and _is_fresh(graph, s)
            and not _subject_is_risky(graph, s))


def _risk_reason(graph: Any, triple: tuple, prefixes: dict) -> str | None:
    s, p, _o = triple
    on = short(s, prefixes) if _is_node(s) else "a quoted triple"
    if p in FULL_CHECK_TRIGGERS.predicates:
        return "full check: " + short(p, prefixes) + " changed on " + on
    if _subject_is_risky(graph, s):
        return "full check: " + on + " is a component, a parameter, a prefix holder or a rule template, and " + short(p, prefixes) + " changed"
    return None


def _owners(graph: Any, node: Any, out: set) -> None:
    """The nodes that hold ``node`` in their description: a blank node belongs to whatever points at it (a property shape to its
    shape, a list cell to the head of its list and then the holder of the list), climbed through blank nodes to the first named one."""
    seen = {node}
    pending = [node]
    while pending:
        current = pending.pop()
        for holder in set(graph.subjects(None, current)):
            if holder in seen or not _is_node(holder):
                continue
            seen.add(holder)
            out.add(holder)
            if isinstance(holder, ox.BlankNode):
                pending.append(holder)


def _referrers(graph: Any, node: Any, out: set) -> None:
    """The shapes that refer to ``node`` through one of the reference predicates of ``referenced_shapes`` (the same set, read in
    reverse: ``referenced_shapes`` goes from a shape to what it refers to, this from a shape to what refers to it), a list member
    through the holder of its list."""
    for predicate in _REFERENCE_PREDICATES:
        for holder in graph.subjects(predicate, node):
            if _is_node(holder):
                out.add(holder)
    for cell in graph.subjects(RDF.first, node):
        _owners(graph, cell, out)  # the head's holder is the shape with the sh:and / sh:or / sh:xone; the cells in between are blank


def _node_terms(triples: Iterable[tuple]) -> list:
    """The subjects and the node-valued objects of ``triples``, in first-seen order, without duplicates."""
    seen: dict = {}
    for s, _p, o in triples:
        for term in (s, o):
            if _is_node(term):
                seen.setdefault(term, None)
    return list(seen)


def _normalise(triples: Iterable[Any]) -> list[tuple]:
    out = []
    for triple in triples:
        s, p, o = (to_engine(x) for x in triple)
        out.append((s, p, o))
    return out


def _count(n: int, noun: str) -> str:
    return str(n) + " " + noun + ("" if n == 1 else "s")


def compute_scope(
    graph: Any,
    *,
    add: Iterable[Any] = (),
    remove: Iterable[Any] = (),
    nodes: Iterable[Any] | None = None,
    with_dependents: bool = True,
    prefixes: dict | None = None,
) -> tuple[MetaScope, list, list]:
    """The ``MetaScope`` of a check of ``graph`` with the edit ``add`` / ``remove`` applied, the normalised ``add`` and ``remove``.
    ``graph`` is the graph before the edit; nothing is validated or copied here. A type or subclass triple is risky on a subject
    the graph already has and local on one it does not (a new shape or class), unless the type is one of the risky classes."""
    adds, removes = _normalise(add), _normalise(remove)
    given = None if nodes is None else [to_engine(n) for n in nodes]
    if given is None and not adds and not removes:
        return MetaScope(True, (), ("full check: no nodes or edit given",)), adds, removes
    prefixes = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "owl": "http://www.w3.org/2002/07/owl#", **(prefixes or {})}
    reasons = []
    new: dict = {}  # subjects the edit declares: their type triples are local
    for triple in adds:
        if _is_new_declaration(graph, triple):
            new[triple[0]] = None
    for triple in [*removes, *adds]:
        if triple in adds and triple not in removes and triple[0] in new and _is_new_declaration(graph, triple):
            continue
        reason = _risk_reason(graph, triple, prefixes)
        if reason is not None and reason not in reasons:
            reasons.append(reason)
    if reasons:
        if len(reasons) > 5:
            reasons = [*reasons[:5], "full check: and " + _count(len(reasons) - 5, "more risky change")]
        return MetaScope(True, (), tuple(reasons)), adds, removes
    changed = [n for n in _node_terms([*removes, *adds]) if n not in new]
    for triple in [*removes, *adds]:  # a reifier is part of the triple it reifies: the shape holding the link is covered too
        for term in _reified(graph, triple[0]):
            if _is_node(term) and term not in changed:
                changed.append(term)
    changed_and_new = [*new, *changed]
    covered = dict.fromkeys(changed_and_new)
    given_only = [n for n in (given or []) if n not in covered]
    covered.update(dict.fromkeys(given_only))
    inline = [n for n in _inline_parts(graph, list(covered)) if n not in covered]  # a shape's property shapes are reported as its own
    covered.update(dict.fromkeys(inline))
    dependents: list = []
    if with_dependents:
        found: set = set()
        for node in [*changed_and_new, *given_only]:
            if _is_node(node):
                _referrers(graph, node, found)
                if isinstance(node, ox.BlankNode):
                    _owners(graph, node, found)
        dependents = sorted((n for n in found if n not in covered and not _is_list_cell(graph, n)), key=text)
        covered.update(dict.fromkeys(dependents))
    parts = []
    if changed:
        parts.append(str(len(changed)) + " changed")
    if new:
        parts.append(str(len(new)) + " new")
    if given_only:
        parts.append(str(len(given_only)) + " given")
    if inline:
        parts.append(str(len(inline)) + " inline")
    if dependents:
        parts.append(_count(len(dependents), "dependent"))
    reason = "checked " + _count(len(covered), "node") + (": " + ", ".join(parts) if parts else "")
    return MetaScope(False, tuple(covered), (reason,)), adds, removes


def _is_list_cell(graph: Any, node: Any) -> bool:
    return isinstance(node, ox.BlankNode) and next(iter(graph.objects(node, RDF.first)), None) is not None


def _inline_parts(graph: Any, nodes: list) -> list:
    """The blank nodes ``nodes`` are described through (property shapes, SPARQL constraints, node expressions), transitively: the
    meta-shapes report a defect in one of them on the blank node itself, so checking a shape means checking those too. List cells are
    not included, a list is part of the value that holds it."""
    out: dict = {}
    pending = list(nodes)
    seen = set(pending)
    while pending:
        current = pending.pop()
        if not _is_node(current):
            continue
        for _p, obj in graph.predicate_objects(current):
            if isinstance(obj, ox.BlankNode) and obj not in seen:
                seen.add(obj)
                pending.append(obj)
                if not _is_list_cell(graph, obj):
                    out[obj] = None
    return sorted(out, key=text)


def _reified(graph: Any, subject: Any) -> list:
    """The subjects of the triples ``subject`` reifies (``subject`` is a reifier, e.g. an annotation on a ``sh:property`` link)."""
    return [t.subject for t in graph.objects(subject, RDF.reifies) if isinstance(t, ox.Triple)] if _is_node(subject) else []


def after_edit(graph: Any, add: list, remove: list) -> Any:
    """A copy of ``graph`` with ``remove`` taken out and then ``add`` put in (an edit in both ends up added); ``graph`` is not changed.
    No edit: ``graph`` itself."""
    if not add and not remove:
        return graph
    from starlayer.graph.core import StarLayerGraph
    from starlayer.shacl.engine.graphs import new_graph

    if isinstance(graph, StarLayerGraph):
        view = graph.copy()
    else:  # a union view of a dataset: its triples as one graph
        view = new_graph(graph)
        view.extend(list(graph.triples((None, None, None))))
        view.prefixes.update(getattr(graph, "prefixes", None) or {})
    for s, p, o in remove:
        view.remove((s, p, o))
    view.extend(add)
    return view
