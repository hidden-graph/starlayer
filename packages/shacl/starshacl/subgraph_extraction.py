"""``StarShaclValidator.extract_subgraph()`` - given a focus node that
conforms to a shape, extract exactly the subgraph of *real, stored* triples
that shape's constraints covered for that node.

Design decisions (agreed with the user across several turns, recorded in
full in this project's memory under "shacl-subgraph-extraction-design" -
summarized here so the code and its rationale stay together):

1. Multi-hop paths keep every intervening triple, regardless of chain
   length, with cycle detection for unbounded paths (``zeroOrMorePath``/
   ``oneOrMorePath``) over data graphs that actually have cycles.
2. Nested/referenced shapes (``sh:node``, ``sh:property``,
   ``sh:qualifiedValueShape``) are included recursively.
3. For logical constraints where a shape can be satisfied more than one way
   (``sh:or``/``sh:xone``), only the branch that actually caused the pass is
   included - deterministic because ``sh:or``/``sh:xone``'s disjuncts are an
   RDF list (a real order), so "the first list member that conforms" is a
   fixed, reproducible rule, not an arbitrary one.
4. Where a requirement is satisfiable by more than one candidate and nothing
   in the shape imposes an order over them (``sh:qualifiedValueShape`` +
   ``sh:qualifiedMinCount`` where more values conform than the minimum
   requires), include *every* satisfying candidate, not just the minimum -
   trades minimality for determinism, since "the set of all qualifying
   values" is well-defined regardless of iteration order and this feature
   feeds a hash.
5. Only real, stored triples are ever included - never a synthesized triple
   for an ``sh:values``-computed or otherwise virtual value. A constraint
   satisfied via a node expression is resolved back to whichever real
   triples it actually read.

Known, deliberate simplification for this first implementation: ``sh:not``
contributes no additional triples (there is no well-defined "witness" of a
shape *not* matching, unlike the other logical constraints). Flagged as a
gap to revisit, not silently assumed correct - see the module memory note.

Built on top of pySHACL's own ``Shape``/path-resolution machinery (the
project's existing `_shape_conforms` pattern in ``node_expressions.py``)
rather than reimplementing SHACL's constraint semantics from scratch - the
one piece pySHACL doesn't expose directly is the *intervening triples* of a
multi-hop path (``value_nodes_from_path`` returns only the final value
nodes), so ``_walk_path`` below implements SHACL's path algebra directly,
returning both the value nodes and every triple traversed to reach them.
"""

from __future__ import annotations

from typing import Any, FrozenSet, Set, Tuple

from rdflib import BNode, Literal
from rdflib.namespace import RDF, SH

_Triple = Tuple[Any, Any, Any]

# Constraint components whose semantics require reading a *second* property
# path from the same focus node (not the constrained path's own value nodes)
# in order to determine conformance - those second-path triples are real
# data the shape's evaluation depended on, per decision 5.
_SECOND_PATH_PREDICATES = (SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals)

_QUALIFIED_FAMILY = frozenset(
    {SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedMaxCount, SH.qualifiedValueShapesDisjoint}
)
# Predicates that don't affect which of sh:path's value nodes are relevant -
# safe to ignore when deciding whether sh:qualifiedValueShape is the *only*
# thing constraining a property shape's raw value set.
_NON_CONSTRAINT_METADATA = frozenset(
    {SH.path, SH.name, SH.description, SH.order, SH.group, SH.message, SH.severity, SH.deactivated, RDF.type}
)


def _qualified_value_shape_is_sole_constraint(sg: Any, shape_node: Any) -> bool:
    """True if ``sh:qualifiedValueShape`` is present and nothing else on
    this property shape needs the *full*, unfiltered set of `sh:path`'s
    value nodes (e.g. a plain `sh:minCount` on the raw path, or `sh:node`,
    which - unlike `sh:qualifiedValueShape` - requires *every* value to
    conform, not just some minimum). Conservative by construction: any
    predicate this function doesn't specifically recognize as "safe" counts
    against narrowing, so an unrecognized constraint component falls back
    to the safe, over-inclusive behavior rather than risking an incorrect
    exclusion.
    """
    predicates = set(sg.graph.predicates(shape_node))
    if SH.qualifiedValueShape not in predicates:
        return False
    return len(predicates - _QUALIFIED_FAMILY - _NON_CONSTRAINT_METADATA) == 0


def _shape_conforms(sg: Any, shape_node: Any, data_graph: Any, node: Any) -> bool:
    """Mirrors ``node_expressions._shape_conforms`` - kept as a separate,
    private copy rather than a shared import to avoid coupling this module's
    (already large) surface to node_expressions.py's own evolution."""
    from pyshacl.pytypes import SHACLExecutor

    shape = sg.lookup_shape_from_node(shape_node)
    conforms, _reports = shape.validate(SHACLExecutor(), data_graph, focus=node)
    return conforms


def _rdf_list(sg: Any, list_node: Any) -> list:
    return list(sg.graph.items(list_node))


def _walk_path(data_graph: Any, focus: Any, path_val: Any, sg: Any) -> Tuple[FrozenSet[Any], Set[_Triple]]:
    """SHACL property-path algebra, returning both the value nodes reached
    and every triple traversed to reach them (decision 1) - the one thing
    pySHACL's own ``value_nodes_from_path`` doesn't expose."""
    # Simple predicate path: a bare IRI.
    if not isinstance(path_val, BNode):
        values = set(data_graph.objects(focus, path_val))
        return frozenset(values), {(focus, path_val, v) for v in values}

    predicates = set(sg.graph.predicates(path_val))

    if SH.inversePath in predicates:
        inner = next(iter(sg.graph.objects(path_val, SH.inversePath)))
        values = set(data_graph.subjects(inner, focus))
        return frozenset(values), {(v, inner, focus) for v in values}

    if SH.alternativePath in predicates:
        alt_list = next(iter(sg.graph.objects(path_val, SH.alternativePath)))
        all_values: Set[Any] = set()
        all_triples: Set[_Triple] = set()
        for alt in _rdf_list(sg, alt_list):
            v, t = _walk_path(data_graph, focus, alt, sg)
            all_values |= v
            all_triples |= t
        return frozenset(all_values), all_triples

    if SH.zeroOrMorePath in predicates or SH.oneOrMorePath in predicates:
        zero_allowed = SH.zeroOrMorePath in predicates
        pred_key = SH.zeroOrMorePath if zero_allowed else SH.oneOrMorePath
        inner = next(iter(sg.graph.objects(path_val, pred_key)))
        reachable: Set[Any] = {focus} if zero_allowed else set()
        frontier = {focus}
        seen = {focus}
        while frontier:
            next_frontier: Set[Any] = set()
            for node in frontier:
                for v in data_graph.objects(node, inner):
                    reachable.add(v)
                    if v not in seen:
                        seen.add(v)
                        next_frontier.add(v)
            frontier = next_frontier
        # Every real edge of `inner` between two nodes already known
        # reachable (focus included) - not just a spanning tree - so the
        # result is deterministic regardless of traversal order (decision 4's
        # same "don't pick an arbitrary witness" spirit) and stays within
        # the predicate the path itself already sanctions.
        triples = {
            (u, inner, v) for u in reachable for v in data_graph.objects(u, inner) if v in reachable
        }
        return frozenset(reachable), triples

    if SH.zeroOrOnePath in predicates:
        inner = next(iter(sg.graph.objects(path_val, SH.zeroOrOnePath)))
        values = set(data_graph.objects(focus, inner))
        return frozenset(values | {focus}), {(focus, inner, v) for v in values}

    if RDF.first in predicates:
        # A sequence path: an RDF list of paths, applied in order.
        current = {focus}
        triples: Set[_Triple] = set()
        for element in _rdf_list(sg, path_val):
            next_current: Set[Any] = set()
            for node in current:
                v, t = _walk_path(data_graph, node, element, sg)
                next_current |= v
                triples |= t
            current = next_current
        return frozenset(current), triples

    raise NotImplementedError(f"Unrecognized sh:path expression: {path_val!r}")


def _extract(
    data_graph: Any,
    sg: Any,
    shape: Any,
    focus_node: Any,
    visiting: FrozenSet[Tuple[Any, Any]],
) -> Set[_Triple]:
    key = (shape.node, focus_node)
    if key in visiting:
        return set()  # shape-level recursion guard (e.g. mutually-recursive shapes)
    visiting = visiting | {key}

    triples: Set[_Triple] = set()

    if shape.is_property_shape:
        path_val = shape.path()
        value_nodes, path_triples = _walk_path(data_graph, focus_node, path_val, sg)

        qshape_nodes = list(sg.graph.objects(shape.node, SH.qualifiedValueShape))
        can_narrow = bool(qshape_nodes) and _qualified_value_shape_is_sole_constraint(sg, shape.node)

        if can_narrow:
            qualifying_values = {
                v for v in value_nodes if any(_shape_conforms(sg, q, data_graph, v) for q in qshape_nodes)
            }
            path_predicates = set(sg.graph.predicates(path_val)) if isinstance(path_val, BNode) else set()
            if not isinstance(path_val, BNode):
                # Simple predicate path (the overwhelming majority of real
                # sh:qualifiedValueShape usage) - narrow precisely: drop the
                # membership edge for any value that didn't qualify, since
                # nothing else on this property shape needs it (decision 4's
                # "no arbitrary witnesses" spirit, extended to non-qualifying
                # candidates too - they're not just an unresolved tie,
                # they're simply irrelevant to this constraint).
                triples |= {t for t in path_triples if t[2] in qualifying_values}
                value_nodes = qualifying_values
            elif SH.inversePath in path_predicates:
                triples |= {t for t in path_triples if t[0] in qualifying_values}
                value_nodes = qualifying_values
            else:
                # A complex path (sequence/alternative/zeroOrMore) combined
                # with sh:qualifiedValueShape - precisely pruning
                # intermediate hops down to "only those leading to a
                # qualifying final value" is a real graph-reachability
                # problem this first implementation doesn't attempt. Falls
                # back to the safe, over-inclusive behavior rather than risk
                # an incorrect exclusion. Known scoping boundary, not an
                # oversight.
                triples |= path_triples
        else:
            triples |= path_triples

        for pred in _SECOND_PATH_PREDICATES:
            for other_path_val in sg.graph.objects(shape.node, pred):
                _other_values, other_triples = _walk_path(data_graph, focus_node, other_path_val, sg)
                triples |= other_triples

        for qshape_node in qshape_nodes:
            qshape = sg.lookup_shape_from_node(qshape_node)
            for v in value_nodes:
                if _shape_conforms(sg, qshape_node, data_graph, v):
                    triples |= _extract(data_graph, sg, qshape, v, visiting)
    else:
        value_nodes = frozenset({focus_node})

    for nested_shape_node in sg.graph.objects(shape.node, SH.node):
        nested_shape = sg.lookup_shape_from_node(nested_shape_node)
        for v in value_nodes:
            triples |= _extract(data_graph, sg, nested_shape, v, visiting)

    for prop_shape_node in sg.graph.objects(shape.node, SH.property):
        prop_shape = sg.lookup_shape_from_node(prop_shape_node)
        for v in value_nodes:
            triples |= _extract(data_graph, sg, prop_shape, v, visiting)

    for and_list in sg.graph.objects(shape.node, SH["and"]):
        for member_node in _rdf_list(sg, and_list):
            member_shape = sg.lookup_shape_from_node(member_node)
            for v in value_nodes:
                triples |= _extract(data_graph, sg, member_shape, v, visiting)

    for or_list in sg.graph.objects(shape.node, SH["or"]):
        for v in value_nodes:
            # sh:or only requires *at least one* disjunct to pass, so more than
            # one may legitimately conform at once - include every passing
            # disjunct's triples, not just the first in list order (list order
            # is an authoring artifact, not a semantic tie-break).
            for member_node in _rdf_list(sg, or_list):
                if _shape_conforms(sg, member_node, data_graph, v):
                    member_shape = sg.lookup_shape_from_node(member_node)
                    triples |= _extract(data_graph, sg, member_shape, v, visiting)

    for xone_list in sg.graph.objects(shape.node, SH.xone):
        for v in value_nodes:
            # sh:xone requires *exactly one* disjunct to pass, so at most one
            # can ever legitimately conform - include that one. This is not an
            # arbitrary determinism choice: if data later changes so a second
            # disjunct also starts passing, sh:xone itself is no longer
            # satisfied, so _shape_conforms() for this shape+node turns False
            # and extract_subgraph() reports conforms=False outright, rather
            # than silently extracting a different subgraph.
            for member_node in _rdf_list(sg, xone_list):
                if _shape_conforms(sg, member_node, data_graph, v):
                    member_shape = sg.lookup_shape_from_node(member_node)
                    triples |= _extract(data_graph, sg, member_shape, v, visiting)
                    break

    # sh:not: deliberately no additional triples - see module docstring.

    return triples


def extract_subgraph(data_graph: Any, shacl_graph: Any, shape: Any, focus_node: Any):
    """Implements ``StarShaclValidator.extract_subgraph()`` - see module
    docstring for the design this follows. Returns a
    ``starshacl.results.SubgraphExtractionResult``.

    ``shacl_graph`` is a raw shapes graph (already normalized by the caller,
    matching ``evaluate()``'s own calling convention) - wrapped here into a
    pySHACL ``ShapesGraph`` so ``lookup_shape_from_node``/shape harvesting
    work the same way they do for ``_shape_conforms`` elsewhere in this
    codebase. Wrapped over a *copy*, never the caller's own object -
    confirmed live that ``ShapesGraph.__init__``/``.shapes`` mutates
    whatever graph it's given in place (injecting a couple of RDFS/OWL
    class-hierarchy axiom triples for its own implicit-class-target
    support), which would otherwise silently pollute the caller's
    ``shacl_graph`` as an unrelated side effect of calling this function.
    """
    from pyshacl.shapes_graph import ShapesGraph

    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    from starshacl.results import SubgraphExtractionResult

    shacl_graph_copy = StarLayerGraph()
    for prefix, ns in shacl_graph.namespaces():
        shacl_graph_copy.bind(prefix, ns)
    for t in shacl_graph:
        shacl_graph_copy.add(t)

    sg = ShapesGraph(shacl_graph_copy)
    sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

    if not _shape_conforms(sg, shape, data_graph, focus_node):
        return SubgraphExtractionResult(conforms=False, data_graph=None)

    shape_obj = sg.lookup_shape_from_node(shape)
    triples = _extract(data_graph, sg, shape_obj, focus_node, frozenset())

    result_graph = StarLayerGraph()
    for t in triples:
        result_graph.add(t)
    return SubgraphExtractionResult(conforms=True, data_graph=result_graph)


def _remove_rdf_list(graph: Any, list_node: Any) -> None:
    while list_node is not None and list_node != RDF.nil:
        next_node = next(graph.objects(list_node, RDF.rest), None)
        for p, o in list(graph.predicate_objects(list_node)):
            graph.remove((list_node, p, o))
        list_node = next_node


def close_shape(shacl_graph: Any, shape: Any) -> Any:
    """Return a *copy* of ``shacl_graph`` (the original is never mutated) in
    which ``shape`` - and every shape it recursively references in a way
    that describes a value node's *complete* property set (``sh:node``,
    ``sh:qualifiedValueShape``, and every ``sh:and``/``sh:or``/``sh:xone``
    member) - is closed (``sh:closed true``) with any ``sh:ignoredProperties``
    removed.

    Built for exactly one purpose: turning a shape's normal, everyday
    production form (which very often *does* need ``sh:ignoredProperties`` -
    e.g. exempting ``rdf:type``, since almost every real instance has one)
    into the strict verification form ``extract_subgraph()``'s acceptance
    test needs, without hand-maintaining a second, drift-prone copy of the
    shape alongside the real one.

    Plain property shapes referenced only via ``sh:property`` (e.g.
    ``sh:property [ sh:path ex:amount ; sh:minCount 1 ]``) are walked
    (to find any *further* nested ``sh:node``/etc. reference inside them)
    but never themselves closed - unlike ``sh:node``, a bare ``sh:property``
    entry doesn't claim to describe its value nodes' *complete* property
    set, so closing it would incorrectly require those values to have zero
    other properties.
    """
    result = type(shacl_graph)()
    for prefix, ns in shacl_graph.namespaces():
        result.bind(prefix, ns)
    for t in shacl_graph:
        result.add(t)

    to_close: Set[Any] = set()
    visited: Set[Any] = set()

    def _walk(shape_node: Any, should_close: bool) -> None:
        if shape_node in visited:
            return
        visited.add(shape_node)
        if should_close:
            to_close.add(shape_node)

        for nested in result.objects(shape_node, SH.node):
            _walk(nested, True)
        for prop in result.objects(shape_node, SH.property):
            _walk(prop, False)
        for qshape in result.objects(shape_node, SH.qualifiedValueShape):
            _walk(qshape, True)
        for and_list in result.objects(shape_node, SH["and"]):
            for member in result.items(and_list):
                _walk(member, True)
        for pred in (SH["or"], SH.xone):
            for member_list in result.objects(shape_node, pred):
                for member in result.items(member_list):
                    _walk(member, True)

    _walk(shape, True)

    for shape_node in visited:
        for ip_list in list(result.objects(shape_node, SH.ignoredProperties)):
            result.remove((shape_node, SH.ignoredProperties, ip_list))
            _remove_rdf_list(result, ip_list)

    for shape_node in to_close:
        result.remove((shape_node, SH.closed, None))
        result.add((shape_node, SH.closed, Literal(True)))

    return result
