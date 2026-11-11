"""SHACL UI property roles (https://www.w3.org/TR/shacl12-ui/, "Property Roles"): which property shapes of a node shape play a role, in order.

A property shape is annotated with ``shui:propertyRole`` in one of three forms:

* direct: ``ex:Label sh:path skos:prefLabel ; shui:propertyRole shui:LabelRole .``
* qualified: ``shui:propertyRole [ shui:propertyRole shui:LabelRole ; sh:order 0 ]``
* the RDF 1.2 triple annotation, the direct form with the order on the reifier: ``shui:propertyRole shui:LabelRole {| sh:order 0 |}``

"If multiple property shapes share the same role, they must be sorted in ascending order of their ``sh:order`` values, and any property
shape using a qualified role annotation comes before a shape using a direct, unqualified role annotation." For a role that shows one
value (``shui:LabelRole``) the order is the precedence: the first shape that yields a value wins. For a role that shows all values
(``shui:ClassificationRole``) it is the display order. This ``sh:order`` is unrelated to the presentation order of the form.

This module settles that order, and nothing else. Resolving a label from the data, language resolution and rendering are the
application's (the draft's Label Resolution reads the data graph and the user's language preferences).
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.shacl.ui_widget_selection import SHUI, _as_ox_graph, _term_in, _term_out
from starlayer.shacl_engine.terms import SH

_REIFIES = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

#: the built-in roles of the draft; a role from another namespace works the same way
LABEL_ROLE = SHUI.LabelRole
DEPICTION_ROLE = SHUI.DepictionRole
CLASSIFICATION_ROLE = SHUI.ClassificationRole
DESCRIPTION_ROLE = SHUI.DescriptionRole
ICON_ROLE = SHUI.IconRole


def _number(graph: Any, node: Any) -> float | None:
    """The ``sh:order`` of ``node``, or ``None``: the first value that is a number."""
    for value in graph.objects(node, SH.order):
        try:
            return float(value.value)
        except (AttributeError, ValueError):
            continue
    return None


def property_shapes_for_role(*, shape_node: Any, role: Any, shapes_graph: Any) -> list[Any]:
    """The property shapes of ``shape_node`` (its ``sh:property`` list) that play ``role``, in the order the draft gives: ascending
    ``sh:order``, the qualified annotations (a blank node, or a triple annotation that carries an ``sh:order``) before the direct ones
    that carry no order. Shapes with no order keep a stable order (by IRI or label). ``[]`` if none plays the role.

    ``role`` is the role's IRI (``shui:LabelRole`` or one of your own). ``shape_node`` and the returned shapes are in the term family
    of ``shape_node`` (pyoxigraph or rdflib)."""
    as_ox = isinstance(shape_node, (ox.NamedNode, ox.BlankNode))
    graph = _as_ox_graph(shapes_graph)
    shape = _term_in(shape_node)
    wanted = _term_in(role) if not isinstance(role, str) else ox.NamedNode(role)
    found: list[tuple[tuple, Any]] = []
    for prop in dict.fromkeys(graph.objects(shape, SH.property)):
        best: tuple | None = None
        for annotation in graph.objects(prop, SHUI.propertyRole):
            if annotation == wanted:  # direct; an order on a triple annotation makes it a qualified one
                order = None
                for reifier in graph.subjects(_REIFIES, ox.Triple(prop, SHUI.propertyRole, annotation)):
                    order = _number(graph, reifier)
                    if order is not None:
                        break
                key = (0, order, str(prop)) if order is not None else (1, 0.0, str(prop))
            elif isinstance(annotation, ox.BlankNode) and (annotation, SHUI.propertyRole, wanted) in graph:  # qualified
                order = _number(graph, annotation)
                key = (0, order if order is not None else float("inf"), str(prop))
            else:
                continue
            best = key if best is None or key < best else best
        if best is not None:
            found.append((best, prop))
    found.sort(key=lambda item: item[0])
    return [_term_out(prop, as_ox) for _key, prop in found]
