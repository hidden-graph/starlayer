"""Two rule-loading fixes on pySHACL's ``SHACLRule`` (GitHub issue #137).

* ``sh:condition`` naming a shape that is both ``sh:NodeShape`` and ``rdfs:Class``: SHACL 1.2 Inference Rules ("Conditions on
  Shape Rules") say a focus node must also conform to every non-deactivated superclass of the condition shape that is itself
  both a node shape and a class. pySHACL only checks the named shape, so ``get_conditions`` adds the superclass shapes.
* A non-numeric ``sh:order`` crashed with a raw ``decimal.InvalidOperation``; ``order`` now raises ``RuleLoadError`` like the
  other malformed-rule cases, and returns the numeric value of an ``xsd:decimal``/``xsd:integer``/float literal.

Process-global and idempotent, like the other pySHACL patches.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rdflib import RDF, RDFS, Literal
from rdflib.namespace import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
_SENTINEL = "_starlayer_shacl_rule_conditions_patch"


def order_value(order_node: Any) -> Decimal:
    """The numeric value of an ``sh:order`` object, or ``RuleLoadError`` if it is not a numeric literal."""
    from pyshacl.errors import RuleLoadError

    value = order_node.value if isinstance(order_node, Literal) else None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise RuleLoadError(
            f"A SHACL Rule's sh:order must be an xsd:decimal or xsd:integer literal, got {order_node!r}.",
            "https://www.w3.org/TR/shacl-af/#rules-order",
        )
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:  # NaN, infinity
        raise RuleLoadError(
            f"A SHACL Rule's sh:order must be a finite number, got {order_node!r}.",
            "https://www.w3.org/TR/shacl-af/#rules-order",
        ) from exc


def _is_true(graph: Any, node: Any, predicate: Any) -> bool:
    return any(isinstance(v, Literal) and bool(v.value) for v in graph.objects(node, predicate))


def class_condition_superclasses(graph: Any, shape_node: Any) -> list[Any]:
    """Transitive ``rdfs:subClassOf`` superclasses of ``shape_node`` that are node shapes and classes and not deactivated.

    Only applies when ``shape_node`` itself is both ``sh:NodeShape`` and ``rdfs:Class``; otherwise empty."""

    def is_class_shape(node: Any) -> bool:
        types = set(graph.objects(node, RDF.type))
        return SH.NodeShape in types and RDFS.Class in types

    if not is_class_shape(shape_node):
        return []
    found: list[Any] = []
    seen = {shape_node}
    frontier = [shape_node]
    while frontier:
        current = frontier.pop()
        for sup in graph.objects(current, RDFS.subClassOf):
            if sup in seen:
                continue
            seen.add(sup)
            frontier.append(sup)  # a non-qualifying superclass is still walked through
            if is_class_shape(sup) and not _is_true(graph, sup, SH.deactivated):
                found.append(sup)
    return found


def install_rule_condition_patch() -> bool:
    """Replace ``SHACLRule.get_conditions`` and ``SHACLRule.order``. True if installed or already installed."""
    try:
        from pyshacl.errors import RuleLoadError
        from pyshacl.rules.shacl_rule import SHACLRule, SHACLRuleCondition

        if getattr(SHACLRule.get_conditions, _SENTINEL, False):
            return True
        original_get_conditions = SHACLRule.get_conditions

        def get_conditions(self):
            conditions = original_get_conditions(self)
            graph = self.shape.sg.graph
            have = {c.cond_shape.node for c in conditions}
            for condition in list(conditions):
                for sup in class_condition_superclasses(graph, condition.cond_shape.node):
                    if sup in have:
                        continue
                    have.add(sup)
                    try:
                        sup_shape = self.shape.sg.lookup_shape_from_node(sup)
                    except (AttributeError, KeyError):
                        raise RuleLoadError(
                            "A SHACL Rule Condition must be an existing well-formed SHACL Shape.",
                            "https://www.w3.org/TR/shacl-af/#condition",
                        ) from None
                    conditions.append(SHACLRuleCondition(self, sup_shape))
            return conditions

        def order(self) -> Decimal:
            order_nodes = list(self.shape.sg.objects(self.node, SH.order))
            if not order_nodes:
                return Decimal("0.0")
            if len(order_nodes) > 1:
                raise RuleLoadError(
                    "A SHACL Rule can have only one sh:order property.", "https://www.w3.org/TR/shacl-af/#rules-order"
                )
            return order_value(order_nodes[0])

        setattr(get_conditions, _SENTINEL, True)
        SHACLRule.get_conditions = get_conditions
        SHACLRule.order = property(order)
        return True
    except Exception:
        return False
