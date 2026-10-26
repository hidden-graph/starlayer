"""``extract_subgraph()`` - given a focus node that conforms to a shape,
extract exactly the subgraph of *real, stored* triples that shape's
constraints covered for that node. A plain, standalone function (not a
``StarShaclSchema`` method) - conceptually "``StarLayerGraph.cbd()``, but
the reachability rule is a SHACL shape's own constraints instead of
blank-node adjacency."

``shape=``/``focus_node=`` are optional keyword-only filters, not required
inputs (redesigned 2026-10-14 - see this project's own memory under
"shacl-subgraph-extraction-design" for the full history): given neither,
``extract_subgraph()`` discovers every entry point the whole ``shacl_graph``
itself declares - every shape's own real SHACL targets (``sh:targetClass``/
``sh:targetNode``/``sh:targetSubjectsOf``/``sh:targetObjectsOf``/implicit
class targets/SPARQL-based ``sh:target``), via pySHACL's own
``Shape.focus_nodes()`` - checks each resulting ``(shape, focus_node)``
pair for conformance, and returns **one subgraph that's the union of every
conforming pair's own extraction** (not a per-pair breakdown - decided
directly with the user). Either filter narrows that search: ``shape=``
alone unions just that one shape's own real targets; ``focus_node=`` alone
unions every shape that actually declares this node as one of its own real
targets (not "any shape it happens to conform to" - anchored to what the
shapes graph itself declares, the same semantics `validate()` itself
would apply); both given reproduces the original single-pair behavior
exactly (same conformance check, same extraction - the only change is the
return contract below). A deactivated shape (``sh:deactivated true``) is
never treated as an entry point, matching `validate()`'s own behavior.

**Return contract, unified across every mode**: always a real graph
object; **empty when nothing conforms**, never ``None`` - a deliberate
behavioral change from the original single-pair-only version (which
returned ``None`` to signal non-conformance). One consistent contract
regardless of how many filters are supplied, rather than the fully-pinned
case behaving specially.

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

**Entailment**: ``shacl_graph``'s own declared ``sh:entailment`` regime(s),
plus an optional ``inference=`` keyword (a real ``ENTAILMENT.*`` IRI, or an
iterable of them - the same vocabulary ``sh:entailment`` itself uses, not
pySHACL's own strings - see ``starlayer.shacl.entailment``'s own module
docstring) and an optional ``ont_graph``, are applied once, up front, onto a
private, non-mutating copy of ``data_graph`` - both the conformance re-check
(``_shape_conforms``) and the extraction walk (``_extract``/``_walk_path``)
run against that entailed copy, so they agree with whatever entailment the
caller's own original ``validate()`` call used: re-checking conformance
without it could otherwise silently disagree with the validation that
supposedly already confirmed the node conforms. **Decision 5 above still
holds strictly for the *output* though**: an entailed triple may be *read*
to satisfy a constraint (same as any real one), but the final triple set is
intersected back against the real, pre-entailment ``data_graph`` before
returning, so an entailed-only triple never actually appears in
``extracted_graph`` - entailment only ever corrects *which*
triples/constraints are considered to hold, never contributes new ones to
what's extracted. This is the opposite choice from ``evaluate()``'s own
entailment handling (which does let entailed values appear in its own
returned subgraph) - the two functions have a genuinely different
relationship to "what counts as real" for their own stated purposes, not an
inconsistency to resolve uniformly.

**Shape Fragments (GitHub issue #11, 2026-10-23).** The result is the *shape
fragment* of Delva, Dimou, Jakubowski and Van den Bussche (arXiv 2112.11796),
and the paper's Conformance Theorem is the contract: if the data conforms to the
shapes, the extracted subgraph conforms to them too (``tests/shacl/integration/
test_shape_fragments_paper.py`` is the oracle, including a randomized check).
Three things follow from that:

- **Target triples are included** (``include_targets=True``, the default): the
  ``rdf:type``/``rdfs:subClassOf`` chain of a class target, the triples with the
  predicate of a ``sh:targetSubjectsOf``/``sh:targetObjectsOf``. Without them
  the fragment's nodes are no longer targets and validation passes vacuously.
  ``include_targets=False`` returns only what the constraints read.
- **Value-type evidence**: ``sh:class`` keeps the value's ``rdf:type`` path to
  the class, so a fragment still shows why the value qualifies.
- **``sh:not`` is supported** by returning a superset of the paper's neighborhood
  for the negated shape: its *full trace*, every triple it reads, rather than
  the minimal witness of non-conformance. The paper's Sufficiency Lemma allows
  returning more. A ``sh:qualifiedMaxCount`` keeps the non-qualifying values'
  full trace for the same reason, and ``sh:xone`` keeps the full trace of the
  disjuncts that do not hold.

Built on top of pySHACL's own ``Shape``/path-resolution machinery (the
project's existing `_shape_conforms` pattern in ``node_expressions.py``)
rather than reimplementing SHACL's constraint semantics from scratch - the
one piece pySHACL doesn't expose directly is the *intervening triples* of a
multi-hop path (``value_nodes_from_path`` returns only the final value
nodes), so ``_walk_path`` below implements SHACL's path algebra directly,
returning both the value nodes and every triple traversed to reach them.
"""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, RDFS
from rdflib.term import Node
from rdflib.namespace import Namespace as _Namespace

# rdflib's SH has no SHACL 1.2 terms (sh:ShapeClass, ...): AttributeError on any use (GitHub issue #82)
SH = _Namespace('http://www.w3.org/ns/shacl#')

_Triple = tuple[Any, Any, Any]

# a SHACL 1.2 term this rdflib's SH namespace does not define
_SH_TARGET_WHERE = URIRef(str(SH) + "targetWhere")

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


def _walk_inverse(data_graph: Any, focus: Any, path_val: Any, sg: Any) -> tuple[frozenset[Any], set[_Triple]]:
    """The value nodes v such that ``focus`` is reached from v by ``path_val`` (``^path``), with the data edges used.

    SHACL Core 2.3.1 allows any property path inside ``sh:inversePath``; only an IRI used to be handled, so an inverse of a
    sequence, alternative, repetition or another inverse followed nothing at all (GitHub issue #82).
    """
    if not isinstance(path_val, BNode):
        values = set(data_graph.subjects(path_val, focus))
        return frozenset(values), {(v, path_val, focus) for v in values}

    predicates = set(sg.graph.predicates(path_val))

    if SH.inversePath in predicates:  # ^(^X) = X
        inner = next(iter(sg.graph.objects(path_val, SH.inversePath)))
        return _walk_path(data_graph, focus, inner, sg)

    if SH.alternativePath in predicates:  # ^(a|b) = ^a|^b
        values: set[Any] = set()
        triples: set[_Triple] = set()
        for alt in _rdf_list(sg, next(iter(sg.graph.objects(path_val, SH.alternativePath)))):
            v, t = _walk_inverse(data_graph, focus, alt, sg)
            values |= v
            triples |= t
        return frozenset(values), triples

    if SH.zeroOrMorePath in predicates or SH.oneOrMorePath in predicates:  # ^(X*) = (^X)*
        zero_allowed = SH.zeroOrMorePath in predicates
        inner = next(iter(sg.graph.objects(path_val, SH.zeroOrMorePath if zero_allowed else SH.oneOrMorePath)))
        reachable: set[Any] = {focus} if zero_allowed else set()
        triples = set()
        frontier, seen = {focus}, {focus}
        while frontier:
            next_frontier: set[Any] = set()
            for node in frontier:
                step_values, step_triples = _walk_inverse(data_graph, node, inner, sg)
                triples |= step_triples
                for v in step_values:
                    reachable.add(v)
                    if v not in seen:
                        seen.add(v)
                        next_frontier.add(v)
            frontier = next_frontier
        return frozenset(reachable), triples

    if SH.zeroOrOnePath in predicates:  # ^(X?) = (^X)?
        inner = next(iter(sg.graph.objects(path_val, SH.zeroOrOnePath)))
        values, triples = _walk_inverse(data_graph, focus, inner, sg)
        return frozenset(values | {focus}), triples

    if RDF.first in predicates:  # ^(a/b) = ^b/^a
        current = {focus}
        triples = set()
        for element in reversed(_rdf_list(sg, path_val)):
            next_current: set[Any] = set()
            for node in current:
                v, t = _walk_inverse(data_graph, node, element, sg)
                next_current |= v
                triples |= t
            current = next_current
        return frozenset(current), triples

    raise NotImplementedError(f"Unrecognized sh:path expression: {path_val!r}")


def _walk_path(data_graph: Any, focus: Any, path_val: Any, sg: Any) -> tuple[frozenset[Any], set[_Triple]]:
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
        return _walk_inverse(data_graph, focus, inner, sg)

    if SH.alternativePath in predicates:
        alt_list = next(iter(sg.graph.objects(path_val, SH.alternativePath)))
        all_values: set[Any] = set()
        all_triples: set[_Triple] = set()
        for alt in _rdf_list(sg, alt_list):
            v, t = _walk_path(data_graph, focus, alt, sg)
            all_values |= v
            all_triples |= t
        return frozenset(all_values), all_triples

    if SH.zeroOrMorePath in predicates or SH.oneOrMorePath in predicates:
        zero_allowed = SH.zeroOrMorePath in predicates
        pred_key = SH.zeroOrMorePath if zero_allowed else SH.oneOrMorePath
        inner = next(iter(sg.graph.objects(path_val, pred_key)))
        reachable: set[Any] = {focus} if zero_allowed else set()
        triples: set[_Triple] = set()
        frontier = {focus}
        seen = {focus}
        while frontier:
            next_frontier: set[Any] = set()
            for node in frontier:
                # One step of the repeated path from `node`. `inner` is any path, not only a predicate: a step over an inverse,
                # alternative or sequence path is walked by this same function (GitHub issue #62: a repeated inverse path
                # followed nothing at all).
                values, step_triples = _walk_path(data_graph, node, inner, sg)
                triples |= step_triples
                for v in values:
                    reachable.add(v)
                    if v not in seen:
                        seen.add(v)
                        next_frontier.add(v)
            frontier = next_frontier
        # Every edge of every step taken, from the focus node too: for sh:oneOrMorePath the focus is not one of the nodes the
        # path reaches (unless a cycle returns to it), and the edges leaving it are the first ones the path walks (also #62).
        # The result does not depend on traversal order: all edges out of every node reached are included, not a spanning tree.
        return frozenset(reachable), triples

    if SH.zeroOrOnePath in predicates:
        inner = next(iter(sg.graph.objects(path_val, SH.zeroOrOnePath)))
        values, step_triples = _walk_path(data_graph, focus, inner, sg)
        return frozenset(values | {focus}), step_triples

    if RDF.first in predicates:
        # A sequence path: an RDF list of paths, applied in order.
        current = {focus}
        triples: set[_Triple] = set()
        for element in _rdf_list(sg, path_val):
            next_current: set[Any] = set()
            for node in current:
                v, t = _walk_path(data_graph, node, element, sg)
                next_current |= v
                triples |= t
            current = next_current
        return frozenset(current), triples

    raise NotImplementedError(f"Unrecognized sh:path expression: {path_val!r}")


def _type_paths(graph: Any, node: Any, cls: Any | None = None) -> set[_Triple]:
    """The triples on the ``rdf:type / rdfs:subClassOf*`` paths from ``node``. With ``cls``, only those on a path that
    ends at ``cls`` - the evidence that ``node`` is an instance of it (empty if it is not). Without, every triple of the
    closure of ``node``'s types, which is what must stay in a subgraph for a *negated* class test to keep failing."""
    typed: set[_Triple] = set()
    edges: set[_Triple] = set()
    stack = []
    for type_ in graph.objects(node, RDF.type):
        typed.add((node, RDF.type, type_))
        stack.append(type_)
    seen: set[Any] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for parent in graph.objects(current, RDFS.subClassOf):
            edges.add((current, RDFS.subClassOf, parent))
            stack.append(parent)
    if cls is None:
        return typed | edges
    reaches = {cls}
    changed = True
    while changed:
        changed = False
        for child, _, parent in edges:
            if parent in reaches and child not in reaches:
                reaches.add(child)
                changed = True
    return {t for t in typed if t[2] in reaches} | {t for t in edges if t[0] in reaches and t[2] in reaches}


def _class_values(sg: Any, shape_node: Any) -> list[Any]:
    """The classes named by ``sh:class`` on a shape: a single class or, in SHACL 1.2, a list of them."""
    classes: list[Any] = []
    for value in sg.graph.objects(shape_node, SH["class"]):
        if value == RDF.nil or next(iter(sg.graph.objects(value, RDF.first)), None) is not None:
            classes.extend(_rdf_list(sg, value))
        else:
            classes.append(value)
    return classes


def _target_triples(graph: Any, sg: Any, shape: Any, node: Any) -> set[_Triple]:
    """The triples that make ``node`` a target of ``shape`` (Shape Fragments paper: the shape is conjoined with its
    target; companion specification section 5.2). Empty for a node the shape does not target, and for
    ``sh:targetNode`` (no triple makes a node a target). SPARQL-based targets contribute nothing."""
    triples: set[_Triple] = set()
    classes = list(shape.target_classes()) + list(shape.implicit_class_targets())
    for cls in classes:
        triples |= _type_paths(graph, node, cls)
    for predicate in shape.target_subjects_of():
        triples |= {(node, predicate, obj) for obj in graph.objects(node, predicate)}
    for predicate in shape.target_objects_of():
        triples |= {(subj, predicate, node) for subj in graph.subjects(predicate, node)}
    for where_node in sg.graph.objects(shape.node, _SH_TARGET_WHERE):
        if _shape_conforms(sg, where_node, graph, node):
            triples |= _extract(graph, sg, sg.lookup_shape_from_node(where_node), node, frozenset())
    return triples


def _extract(
    data_graph: Any,
    sg: Any,
    shape: Any,
    focus_node: Any,
    visiting: frozenset[tuple[Any, Any, bool]],
    full_trace: bool = False,
) -> set[_Triple]:
    """The triples ``shape`` reads at ``focus_node``.

    By default only the triples that *show* the shape holds (the minimal neighborhood of the Shape Fragments paper,
    Table 2). ``full_trace=True`` returns every triple the evaluation reads, whether or not its branch holds. That is
    what a negated shape needs: ``sh:not`` stays true in a subgraph only if the triples that make the inner shape fail
    are still there, and removing evidence can flip a negation. It is a superset of the paper's negation
    neighborhoods, which the Sufficiency Lemma allows (a processor may return more)."""
    key = (shape.node, focus_node, full_trace)
    if key in visiting:
        return set()  # shape-level recursion guard (e.g. mutually-recursive shapes)
    visiting = visiting | {key}

    triples: set[_Triple] = set()

    if shape.is_property_shape:
        path_val = shape.path()
        value_nodes, path_triples = _walk_path(data_graph, focus_node, path_val, sg)

        qshape_nodes = list(sg.graph.objects(shape.node, SH.qualifiedValueShape))
        predicates = set(sg.graph.predicates(shape.node))
        has_min = SH.qualifiedMinCount in predicates
        has_max = SH.qualifiedMaxCount in predicates
        can_narrow = (
            bool(qshape_nodes)
            and has_min
            and not has_max
            and not full_trace
            and _qualified_value_shape_is_sole_constraint(sg, shape.node)
        )

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
                # problem this implementation doesn't attempt. Falls
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
                conforms = _shape_conforms(sg, qshape_node, data_graph, v)
                if conforms or full_trace:
                    triples |= _extract(data_graph, sg, qshape, v, visiting, full_trace)
                if has_max and not conforms and not full_trace:
                    # "at most n values satisfy the qualified shape" (the paper's <=n E.psi): a value that does not
                    # satisfy it must keep failing in any subgraph that holds its edge, which another shape's
                    # neighborhood may put there. So its evidence goes in too (paper Table 2, Example 3.8).
                    triples |= _extract(data_graph, sg, qshape, v, visiting, True)
    else:
        value_nodes = frozenset({focus_node})

    # sh:class: the triples that make each value an instance of the class (paper section 3.2, spec section 6.1).
    # In a full trace, the whole type closure: a negated class test must keep failing.
    for cls in _class_values(sg, shape.node):
        for v in value_nodes:
            triples |= _type_paths(data_graph, v, None if full_trace else cls)

    for nested_shape_node in sg.graph.objects(shape.node, SH.node):
        nested_shape = sg.lookup_shape_from_node(nested_shape_node)
        for v in value_nodes:
            triples |= _extract(data_graph, sg, nested_shape, v, visiting, full_trace)

    for prop_shape_node in sg.graph.objects(shape.node, SH.property):
        prop_shape = sg.lookup_shape_from_node(prop_shape_node)
        for v in value_nodes:
            triples |= _extract(data_graph, sg, prop_shape, v, visiting, full_trace)

    for and_list in sg.graph.objects(shape.node, SH["and"]):
        for member_node in _rdf_list(sg, and_list):
            member_shape = sg.lookup_shape_from_node(member_node)
            for v in value_nodes:
                triples |= _extract(data_graph, sg, member_shape, v, visiting, full_trace)

    for or_list in sg.graph.objects(shape.node, SH["or"]):
        for v in value_nodes:
            # sh:or only requires *at least one* disjunct to pass, so more than
            # one may legitimately conform at once - include every passing
            # disjunct's triples, not just the first in list order (list order
            # is an authoring artifact, not a semantic tie-break). A disjunct
            # that fails needs no evidence: it cannot make the shape fail.
            for member_node in _rdf_list(sg, or_list):
                if full_trace or _shape_conforms(sg, member_node, data_graph, v):
                    member_shape = sg.lookup_shape_from_node(member_node)
                    triples |= _extract(data_graph, sg, member_shape, v, visiting, full_trace)

    for xone_list in sg.graph.objects(shape.node, SH.xone):
        for v in value_nodes:
            # sh:xone is "this disjunct holds and every other one fails": the disjunct that holds contributes its
            # neighborhood, and each of the others its full trace, so that it keeps failing (paper section 3.2: xone is
            # a disjunction of phi_i AND not phi_j for the others).
            holding_seen = False
            for member_node in _rdf_list(sg, xone_list):
                member_shape = sg.lookup_shape_from_node(member_node)
                if full_trace:
                    triples |= _extract(data_graph, sg, member_shape, v, visiting, True)
                elif not holding_seen and _shape_conforms(sg, member_node, data_graph, v):
                    holding_seen = True
                    triples |= _extract(data_graph, sg, member_shape, v, visiting, False)
                else:
                    triples |= _extract(data_graph, sg, member_shape, v, visiting, True)

    for not_node in sg.graph.objects(shape.node, SH["not"]):
        # sh:not: the triples the inner shape reads, so that it keeps failing (paper section 3.2: negation).
        not_shape = sg.lookup_shape_from_node(not_node)
        for v in value_nodes:
            triples |= _extract(data_graph, sg, not_shape, v, visiting, True)

    return triples


def extract_subgraph(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    shape: Any | None = None,
    focus_node: Any | None = None,
    inference: Any | None = None,
    include_targets: bool = True,
) -> Any:
    """Returns the subgraph covered by one shape+focus_node pair, or by
    every real entry point a whole shapes graph declares.

    Like ``StarLayerGraph.cbd()``, but the reachability rule is a SHACL
    shape's own constraints instead of blank-node adjacency. See the
    module docstring for the full design this follows, including the
    four filter combinations and the unified return contract.

    ``shacl_graph`` is a raw shapes graph (already normalized by the caller,
    matching ``evaluate()``'s own calling convention) - wrapped here into a
    ``pyshacl.ShapesGraph`` so ``lookup_shape_from_node``/shape harvesting
    work the same way they do for ``_shape_conforms`` elsewhere in this
    codebase. Wrapped over a *copy*, never the caller's own object:
    ``pyshacl.ShapesGraph.__init__``/``.shapes`` mutates whatever graph it's
    given in place (injecting a couple of RDFS/OWL class-hierarchy axiom
    triples for its own implicit-class-target support), which would
    otherwise silently pollute the caller's ``shacl_graph`` as an unrelated
    side effect of calling this function.

    ``shacl_graph=None`` falls back to ``data_graph`` itself - matching
    ``validate()``'s own "data graph doubles as shapes graph" allowance,
    for a data file carrying its own embedded shapes.

    ``ont_graph``/``inference=``: entailment feeds the conformance re-check
    and the extraction walk, but the returned triples are intersected back
    against the real, pre-entailment ``data_graph`` before returning, so an
    entailed-only triple never appears in the output - see the module
    docstring's entailment section for the full design.

    Args:
        data_graph: The full data graph - not a pre-narrowed candidate,
            since multi-hop paths/nested shapes mean the traversal's real
            reach can't be known in advance.
        shacl_graph: The shapes graph. Defaults to ``data_graph``.
        ont_graph: Optional ontology graph feeding entailment.
        shape: Restrict to this one shape's own entry point(s). Omit to
            consider every (non-deactivated) shape in ``shacl_graph``.
        focus_node: Restrict to this one focus node. Omit to discover
            every real target ``pySHACL``'s own ``Shape.focus_nodes()``
            resolves for each candidate shape (declared/implicit targets,
            including SPARQL-based ``sh:target``).
        inference: An ``ENTAILMENT.*`` regime IRI, or an iterable of them.
        include_targets: Also return the triples that make each focus node a target of its shape
            (``sh:targetClass``: its ``rdf:type`` and ``rdfs:subClassOf`` triples; ``sh:targetSubjectsOf`` /
            ``sh:targetObjectsOf``: the triples with that predicate). The Shape Fragments paper includes them
            (the shape is conjoined with its target), and without them the fragment no longer says why its
            nodes were chosen: validating it against the same shapes treats those nodes as no longer targeted
            and passes vacuously. ``sh:targetNode`` has no such triple. Default ``True``.

    Returns:
        A new graph - the union of every conforming ``(shape, focus_node)``
        pair's own extraction. Empty (never ``None``) if nothing conforms.
    """
    for argument, value in (("shape", shape), ("focus_node", focus_node)):
        if value is not None and not isinstance(value, Node):
            # A str is not a term: a str shape was a bare KeyError and a str focus node silently matched nothing.
            raise TypeError(f"{argument} must be an rdflib term such as URIRef, not {type(value).__name__}: {value!r}")
    if shacl_graph is None:
        shacl_graph = data_graph

    from pyshacl.shapes_graph import ShapesGraph

    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    shacl_graph_copy = StarLayerGraph()
    for prefix, ns in shacl_graph.namespaces():
        shacl_graph_copy.bind(prefix, ns)
    for t in shacl_graph:
        shacl_graph_copy.add(t)

    sg = ShapesGraph(shacl_graph_copy)
    sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

    base_triples = frozenset(data_graph)

    from starlayer.shacl.entailment import apply_entailment

    entailed_data_graph = apply_entailment(data_graph, shacl_graph, ont_graph, inplace=False, inference=inference)

    if shape is not None:
        candidate_shape_objs = [sg.lookup_shape_from_node(shape)]
    else:
        candidate_shape_objs = [s for s in sg.shapes if not s.deactivated]

    all_triples: set[_Triple] = set()
    for shape_obj in candidate_shape_objs:
        if focus_node is not None:
            candidate_focus_nodes: Any = [focus_node]
        else:
            shape_obj.set_advanced(True)
            candidate_focus_nodes = shape_obj.focus_nodes(entailed_data_graph)
        for node in candidate_focus_nodes:
            if not _shape_conforms(sg, shape_obj.node, entailed_data_graph, node):
                continue
            all_triples |= _extract(entailed_data_graph, sg, shape_obj, node, frozenset())
            if include_targets:
                all_triples |= _target_triples(entailed_data_graph, sg, shape_obj, node)

    all_triples &= base_triples

    result_graph = StarLayerGraph()
    for t in all_triples:
        result_graph.add(t)
    return result_graph


def _remove_rdf_list(graph: Any, list_node: Any) -> None:
    while list_node is not None and list_node != RDF.nil:
        next_node = next(graph.objects(list_node, RDF.rest), None)
        for p, o in list(graph.predicate_objects(list_node)):
            graph.remove((list_node, p, o))
        list_node = next_node


def _close_shape(shacl_graph: Any, shape: Any) -> Any:
    """Return a *copy* of ``shacl_graph`` (the original is never mutated) in
    which ``shape`` - and every shape it recursively references in a way
    that describes a value node's *complete* property set (``sh:node``,
    ``sh:qualifiedValueShape``, and every ``sh:and``/``sh:or``/``sh:xone``
    member) - is closed (``sh:closed true``) with any ``sh:ignoredProperties``
    removed, except that ``rdf:type`` (class targets, ``sh:class``) and the
    predicates of ``sh:targetSubjectsOf`` stay allowed: ``extract_subgraph()``
    includes those triples, so the strict form must accept them (and nothing else).

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

    Private - reach this through :meth:`StarShaclSchema.close_shape` instead,
    which binds ``self.shacl_graph`` rather than taking it as a parameter,
    matching every other processing mode on that class.
    """
    result = type(shacl_graph)()
    for prefix, ns in shacl_graph.namespaces():
        result.bind(prefix, ns)
    for t in shacl_graph:
        result.add(t)

    to_close: set[Any] = set()
    visited: set[Any] = set()

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

    # extract_subgraph() adds the triples that make a node a target (rdf:type for a class target, the predicate of
    # sh:targetSubjectsOf) and the rdf:type evidence for sh:class, so the strict form must let exactly those through and
    # nothing else.
    allowed: set[Any] = set()
    for shape_node in visited:
        if (
            list(result.objects(shape_node, SH.targetClass))
            or list(result.objects(shape_node, SH["class"]))
            or any(t in (RDFS.Class, SH.ShapeClass) for t in result.objects(shape_node, RDF.type))
        ):
            allowed.add(RDF.type)
        allowed |= set(result.objects(shape_node, SH.targetSubjectsOf))

    for shape_node in to_close:
        result.remove((shape_node, SH.closed, None))
        result.add((shape_node, SH.closed, Literal(True)))
        if allowed:
            from rdflib.collection import Collection

            ignored = BNode()
            Collection(result, ignored, sorted(allowed, key=str))
            result.add((shape_node, SH.ignoredProperties, ignored))

    return result
