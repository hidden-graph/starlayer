"""The lexical-fidelity diagnostic: a warning when a validation run could give a different answer because the data graph
does not return literals exactly as they were written.

Oxigraph normalises a literal's lexical form on storage ("04"^^xsd:integer becomes "4", "1"^^xsd:boolean becomes "true",
"none"^^xsd:boolean becomes "false"), so an ``OxigraphGraph`` has ``preserves_lexical_forms = False``. Constraints that look at
the lexical form or the exact datatype of a value (sh:pattern, sh:minLength, sh:maxLength, sh:datatype of a numeric or boolean
type, sh:in / sh:hasValue with numeric or boolean values, sh:equals, sh:disjoint, the boolean parameters) can then conform
or fail differently from validating the same data held in a lexical-form-preserving graph.

The load warns first (``graph/lexical.py``: it names the literals the store kept in another form and counts them on the store).
``check_lexical_fidelity`` decides whether the validation run is affected: the data had such a literal and the shapes use a
form-dependent constraint. ``validate`` emits one ``StarLayerFidelityWarning`` per call and records the message on ``Outcome.warnings``. References: StarLayer issue #190; upstream oxigraph#526, oxigraph#1989 and
PR #2010.
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.graph.lexical import AFFECTED_DATATYPES, rewritten_count
from starlayer.shacl.engine.terms import RDF, SH

#: Constraints that read the lexical form (or the exact datatype) of every value node.
_ALWAYS = ("pattern", "minLength", "maxLength", "equals", "disjoint")
# sh:in and sh:hasValue matter only when their own parameter values include an affected literal (checked in code).
#: Boolean parameters: their meaning depends on how the literal "true"/"1" is written.
_BOOLEAN_PARAMS = ("uniqueLang", "closed", "qualifiedValueShapesDisjoint")

MESSAGE = (
    "{count} literal{s} in the data graph {were} stored in a different form than written (Oxigraph keeps some literals in a canonical "
    "form: \"04\"^^xsd:integer as \"4\", \"1\"^^xsd:boolean as \"true\"), and the shapes use constraints whose result depends on "
    "the original lexical form or datatype: {kinds}. Results may differ from validating the same data with its lexical forms "
    "as written. See StarLayer issue #190; upstream oxigraph#526, oxigraph#1989, PR #2010."
)


def _is_affected_literal(term: Any) -> bool:
    return isinstance(term, ox.Literal) and term.datatype.value in AFFECTED_DATATYPES


def _list_members(graph: Any, head: Any) -> list:
    """The members of the RDF list at ``head`` (cycle-safe; a malformed list yields what could be read)."""
    members, seen = [], set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        members.extend(graph.objects(head, RDF.first))
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return members


def _plan_shapes(plan: Any) -> list:
    shapes = {}
    try:
        nodes = plan.all_shape_nodes()
    except Exception:
        nodes = []
    for node in nodes:
        try:
            shapes[node] = plan.shape(node)
        except Exception:
            pass  # a malformed shape is reported by the run itself
    for node, shape in getattr(plan, "_cache", {}).items():
        shapes.setdefault(node, shape)
    return list(shapes.values())


def _sparql_component_predicates(plan: Any) -> set:
    """The parameter predicates of the SPARQL-based constraint components declared in the shapes graph."""
    try:
        from starlayer.shacl.engine.components.registry import static_specs
        from starlayer.shacl.engine.components.sparql_components import (
            declared_components,
        )

        return {p for spec in declared_components(plan) for p in spec.predicates} - {
            p for spec in static_specs() for p in spec.predicates
        }
    except Exception:
        return set()


def sensitive_constraints(plan: Any) -> list[str]:
    """The sorted ``sh:`` names of the constraint kinds in ``plan`` whose result depends on lexical form or datatype."""
    found: set[str] = set()
    sparql_preds = _sparql_component_predicates(plan)
    for shape in _plan_shapes(plan):
        params = shape.params
        if SH.sparql in params or any(p in params for p in sparql_preds):
            found.add("sparql")  # a SPARQL query can read STR(?v) or DATATYPE(?v)
        for name in _ALWAYS + _BOOLEAN_PARAMS:
            if SH[name] in params:
                found.add(name)
        for v in params.get(SH.hasValue, ()):
            if _is_affected_literal(v):
                found.add("hasValue")
        for head in params.get(SH["in"], ()):
            if any(_is_affected_literal(v) for v in _list_members(plan.shapes_graph, head)):
                found.add("in")
        for dt in params.get(SH.datatype, ()):
            if isinstance(dt, ox.NamedNode) and dt.value in AFFECTED_DATATYPES:
                found.add("datatype")
    return sorted("sh:" + n for n in found)


def data_has_affected_literal(data: Any) -> bool:
    """Whether ``data`` holds a literal of an affected datatype (stops at the first)."""
    for _s, _p, o in data.triples((None, None, None)):
        if _is_affected_literal(o):
            return True
    return False


def rewritten_literals(data: Any) -> int | None:
    """How many literals loaded into ``data`` were stored in a different form than written (``graph/lexical.py``); ``None`` when
    ``data`` is not a view over a store, so it cannot be said."""
    for _ in range(4):
        store = getattr(data, "store", None)
        if isinstance(store, ox.Store):
            return rewritten_count(store)
        data = getattr(data, "base", None)
        if data is None:
            return None
    return None


def check_lexical_fidelity(plan: Any, data: Any) -> str | None:
    """The warning text when ``data`` does not preserve lexical forms, ``plan`` has sensitive constraints and literals were
    stored in a different form than written (a ``data`` that cannot say holds a literal of an affected datatype); otherwise
    ``None``."""
    if getattr(data, "preserves_lexical_forms", True):
        return None
    kinds = sensitive_constraints(plan)
    if not kinds:
        return None
    count = rewritten_literals(data)
    if count is None:
        if not data_has_affected_literal(data):
            return None
        count = 0
    elif not count:
        return None
    return MESSAGE.format(count=count or "Some", s="" if count == 1 else "s", were="was" if count == 1 else "were", kinds=", ".join(kinds))


__all__ = ["AFFECTED_DATATYPES", "MESSAGE", "check_lexical_fidelity", "data_has_affected_literal", "rewritten_literals", "sensitive_constraints"]
