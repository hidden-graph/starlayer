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
class targets), as the engine resolves them - checks each resulting ``(shape, focus_node)``
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
iterable of them - the same vocabulary ``sh:entailment`` itself uses) and an optional ``ont_graph``, are applied once, up front, onto a
private, non-mutating copy of ``data_graph`` - both the conformance re-check
and the extraction walk run against that entailed copy, so they agree with whatever entailment the
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

Built on the engine's own shape machinery (``starlayer.shacl_engine.subgraph``): conformance is the engine's, and the walk of a
shape's paths returns both the value nodes and every triple traversed to reach them.
"""

from __future__ import annotations

from typing import Any

from rdflib.term import Node

from starlayer.shacl import _adapter

__all__ = ["extract_subgraph"]


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

    ``shacl_graph`` and ``data_graph`` are never changed.

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
            every real target of each candidate shape (declared and implicit targets).
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
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    if any(_ox.is_oxigraph_input(g) for g in (data_graph, shacl_graph, ont_graph)):
        # an OxGraph / OxDataset / Store: extract from snapshot copies, return an OxGraph
        copies: dict[int, Any] = {}

        def _snapshot(g: Any) -> Any:
            return copies.setdefault(id(g), _ox.as_rdflib_graph(g)) if g is not None else None

        extracted = extract_subgraph(
            _snapshot(data_graph),
            _snapshot(shacl_graph),
            _snapshot(ont_graph),
            shape=_ox.from_engine_if_ox(shape),
            focus_node=_ox.from_engine_if_ox(focus_node),
            inference=inference,
            include_targets=include_targets,
        )
        return _ox.ox_result(extracted, data_graph, shacl_graph, ont_graph)
    shape, focus_node = _ox.from_engine_if_ox(shape), _ox.from_engine_if_ox(focus_node)
    for argument, value in (("shape", shape), ("focus_node", focus_node)):
        if value is not None and not isinstance(value, Node):
            # A str is not a term: a str shape was a bare KeyError and a str focus node silently matched nothing.
            raise TypeError(f"{argument} must be an rdflib term such as URIRef, not {type(value).__name__}: {value!r}")
    return _adapter.extract_subgraph(
        data_graph,
        shacl_graph,
        ont_graph,
        shape=shape,
        focus_node=focus_node,
        inference=inference,
        include_targets=include_targets,
    )
