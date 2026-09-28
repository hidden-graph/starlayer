"""starsparql.semantic_checks — cross-referential semantic checks over a
decoded algebra tree that SHACL's own per-node shapes structurally cannot
see on their own. A plain SHACL shape only ever inspects its own focus node
and its immediate property-path neighbors; "is every variable a `Project`
node's own `PV` names actually bound somewhere in its own pattern subtree"
needs to see the *whole* subtree underneath that one node - not expressible
as a local, per-node declarative shape without re-deriving SPARQL's own
variable-scoping rules inside SHACL itself.

The check itself is implemented here, in plain Python, reusing rdflib's own
real bookkeeping (``_addVars``/``analyse`` - the exact same computation
rdflib's own evaluator relies on) rather than reimplementing SPARQL's
variable-scoping rules as a hand-written SPARQL-over-SPARQL ``sh:sparql``
query - re-deriving those rules independently would risk this project's
own notion of "valid" silently drifting out of sync with what rdflib
actually does, previously recorded as the reason this was left an open,
deliberately-not-pursued gap in ``packages/sparql/CLAUDE.md``. It *is*,
however, wired into SHACL proper: ``ontology/native_components.py`` wraps
``_unbound_projected_variables_for_node`` below as a real pySHACL
``ConstraintComponent`` (``salg:noUnboundProjectedVariables``, activated on
``salg:ProjectShape`` in ``sparql_shapes.ttl``), so it participates in the
normal ``sh:ValidationReport`` `starsparql.validate()` already produces -
not a side-channel function a caller has to remember to also call.

Scope: the one concrete case the former gap named - a ``Project`` node's
own ``PV`` (its list of variables to project) naming a variable never
actually bound anywhere in its own pattern subtree. Not a general SPARQL
well-formedness validator - SPARQL's real well-formedness surface is much
bigger than this one check, and this module doesn't attempt the rest of
it (see ``sparql_shapes.py``'s own module docstring for what structural
coverage already exists elsewhere).

**Why ``Project.p._vars``, not ``Project._vars``.** rdflib's own
``_addVars`` computes a `Project` node's ``_vars`` as the union of *every*
child's ``_vars`` - and ``PV`` (a plain list of `Variable`s) is itself a
child in the generic traversal sense, so ``Project._vars`` unconditionally
includes every name in ``PV``, whether or not the underlying pattern ever
binds it - checking against it would make this check vacuously pass every
time. ``Project.p`` (the pattern *one level down*) has no such
contamination: its own ``_vars`` is the real, ground-truth set of
variables the pattern itself can bind - confirmed empirically, not
assumed, before this module was written.

**Why a Project node's own ``salg:p``/``salg:PV`` can be decoded and
checked in isolation, without needing the whole containing Query/Update.**
``_addVars`` is a purely bottom-up fold - each node's ``_vars`` depends
only on its own children, never on any ancestor context - confirmed
empirically (not assumed) by comparing a Project node's ``_vars`` computed
in isolation against the same node decoded as part of its full, original
query: identical either way. This is what lets both
``find_unbound_projected_variables`` (below) and the SHACL constraint
component check each ``salg:Project`` node independently, exactly matching
SHACL's own per-focus-node evaluation model.

**A real, confirmed gap in rdflib's own ``_addVars`` - not something this
project's decode pipeline introduced.** A ``VALUES`` clause's rows
(``values.res``) are ``List[Dict[Variable, term]]`` - one plain Python
``dict`` per solution row - and rdflib's own ``_traverseAgg`` (the generic
walker ``_addVars`` runs on) is only closed over
``CompValue``/``list``/``tuple``/``ParseResults``, never ``dict``, so a
``Variable`` living as a dict *key* is structurally invisible to it.
Confirmed directly against **plain, unmodified rdflib** (parsing
``SELECT ?a ?b WHERE { VALUES (?a ?b) { (1 2) } }`` with no round-trip
through this project's own code at all): the resulting ``values`` node's
own ``_vars`` is an empty set. Left unpatched, this would make every
VALUES-only-bound projected variable a false positive here.
``_effectively_bound_vars`` below closes exactly this one gap (walking for
``values``-named nodes and folding their rows' dict keys in) - not a
general reimplementation of ``_addVars``, just this one confirmed blind
spot, kept as narrow as the problem it fixes.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, Variable
from rdflib.namespace import RDF
from rdflib.plugins.sparql.algebra import _addVars, _traverseAgg, analyse

from rdflib.plugins.sparql.parserutils import CompValue

from . import from_rdf
from .vocab import SALG


@dataclass(frozen=True)
class UnboundProjectedVariable:
    """One `Project` node whose `PV` names a variable never bound anywhere
    in its own pattern subtree."""

    project_node: object
    variable: Variable
    projected_vars: tuple[Variable, ...]  # the node's full PV, for context


def _collect_values_bound_vars(node, found: set[Variable]) -> None:
    """Recursively collect every `Variable` used as a row-key inside any
    `values`-named CompValue under `node` - see this module's own docstring
    for why `_addVars` itself can never see these."""
    if isinstance(node, CompValue):
        if node.name == "values":
            for row in node.get("res") or []:
                if isinstance(row, dict):
                    found.update(k for k in row if isinstance(k, Variable))
        for value in node.values():
            _collect_values_bound_vars(value, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_values_bound_vars(item, found)


def _effectively_bound_vars(node) -> set[Variable]:
    """The real, ground-truth set of variables `node` can bind - rdflib's
    own `_addVars` result, supplemented with the one confirmed gap it has
    (VALUES-row variables) - see this module's own docstring."""
    bound = set(getattr(node, "_vars", None) or set())
    _collect_values_bound_vars(node, bound)
    return bound


def _unbound_projected_variables_for_node(project_node, graph: Graph) -> list[UnboundProjectedVariable]:
    """Decode one ``salg:Project`` node's own ``salg:p``/``salg:PV`` in
    isolation and report any ``PV`` variable never bound in ``p``.

    Returns an empty list (not an error) for a node that doesn't decode
    cleanly - that's a structural problem ``sparql_shapes.py::validate()``
    already catches independently; this function's own job starts only
    once decoding succeeds.
    """
    p_node = graph.value(project_node, SALG.p)
    pv_node = graph.value(project_node, SALG.PV)
    if p_node is None or pv_node is None:
        return []

    try:
        pattern = from_rdf._decode(p_node, graph)
        pv = from_rdf._decode_list_field(pv_node, graph)
    except Exception:
        return []

    _traverseAgg(pattern, visitor=analyse)
    _traverseAgg(pattern, _addVars)
    bound = _effectively_bound_vars(pattern)

    return [
        UnboundProjectedVariable(project_node=project_node, variable=var, projected_vars=tuple(pv))
        for var in pv
        if var not in bound
    ]


def find_unbound_projected_variables(data_graph: Graph) -> list[UnboundProjectedVariable]:
    """Find every ``salg:Project`` node in ``data_graph`` (a ``salg:``
    algebra graph, as produced by ``to_rdf.query_to_rdf``/``update_to_rdf``
    - for a Query or an Update alike, ``Project`` nodes can appear in
    either) whose ``PV`` names a variable that's never actually bound
    anywhere in its own pattern subtree.

    A plain, standalone function for a caller who wants this one check
    directly - the same check also runs automatically as a real SHACL
    constraint whenever ``starsparql.validate()`` validates a graph whose
    ``salg:Project`` nodes activate it (see this module's own docstring).
    """
    found: list[UnboundProjectedVariable] = []
    for project_node in data_graph.subjects(RDF.type, SALG.Project):
        found.extend(_unbound_projected_variables_for_node(project_node, data_graph))
    return found
