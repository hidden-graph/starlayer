"""The lexical-fidelity diagnostic: a warning when a validation run could give a different answer because the data graph
does not return literals exactly as they were written.

Oxigraph normalises a literal's lexical form on storage ("04"^^xsd:integer becomes "4", "1"^^xsd:boolean becomes "true",
"none"^^xsd:boolean becomes "false"), so an ``OxigraphGraph`` has ``preserves_lexical_forms = False``. Constraints that look at
the lexical form or the exact datatype of a value (sh:pattern, sh:minLength, sh:maxLength, sh:datatype of a numeric or boolean
type, sh:in / sh:hasValue with numeric or boolean values, sh:equals, sh:disjoint, the boolean parameters) can then conform
or fail differently from validating the same data held in a lexical-form-preserving graph.

``check_lexical_fidelity`` decides whether that applies to a run; ``validate`` emits one ``StarLayerFidelityWarning`` per call
and records the message on ``Outcome.warnings``. References: StarLayer issue #190; upstream oxigraph#526, oxigraph#1989 and
PR #2010.
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine.terms import RDF, SH

_XSD_NS = "http://www.w3.org/2001/XMLSchema#"
#: The datatypes whose lexical form Oxigraph rewrites (integer family, decimal, float, double, boolean).
AFFECTED_DATATYPES: frozenset[str] = frozenset(
    _XSD_NS + n
    for n in (
        "integer", "int", "long", "short", "byte", "nonNegativeInteger", "positiveInteger", "nonPositiveInteger",
        "negativeInteger", "unsignedLong", "unsignedInt", "unsignedShort", "unsignedByte", "decimal", "float", "double",
        "boolean",
    )
)

#: Constraints that read the lexical form (or the exact datatype) of every value node.
_ALWAYS = ("pattern", "minLength", "maxLength", "equals", "disjoint")
# sh:in and sh:hasValue matter only when their own parameter values include an affected literal (checked in code).
#: Boolean parameters: their meaning depends on how the literal "true"/"1" is written.
_BOOLEAN_PARAMS = ("uniqueLang", "closed", "qualifiedValueShapesDisjoint")

MESSAGE = (
    "The data graph does not preserve literal lexical forms (Oxigraph normalises them on storage: \"04\"^^xsd:integer "
    "becomes \"4\", \"1\"^^xsd:boolean becomes \"true\"), and the shapes use constraints whose result depends on the "
    "original lexical form or datatype: {kinds}. Results may differ from validating the same data in a graph that keeps "
    "lexical forms (an rdflib-backed StarLayerGraph). See StarLayer issue #190; upstream oxigraph#526, oxigraph#1989, PR #2010."
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


def sensitive_constraints(plan: Any) -> list[str]:
    """The sorted ``sh:`` names of the constraint kinds in ``plan`` whose result depends on lexical form or datatype."""
    found: set[str] = set()
    for shape in _plan_shapes(plan):
        params = shape.params
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


def check_lexical_fidelity(plan: Any, data: Any) -> str | None:
    """The warning text when ``data`` does not preserve lexical forms, ``plan`` has sensitive constraints and ``data`` holds
    a literal of an affected datatype; otherwise ``None``."""
    if getattr(data, "preserves_lexical_forms", True):
        return None
    kinds = sensitive_constraints(plan)
    if not kinds or not data_has_affected_literal(data):
        return None
    return MESSAGE.format(kinds=", ".join(kinds))


__all__ = ["AFFECTED_DATATYPES", "MESSAGE", "check_lexical_fidelity", "data_has_affected_literal", "sensitive_constraints"]
