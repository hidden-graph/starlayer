"""Recursive shapes are cut where the data actually cycles, not where the shapes repeat (GitHub issue #26).

SHACL leaves the meaning of a recursive shape undefined, so an engine must decide. pySHACL decides from the shapes alone:
``ConstraintComponent.recursion_triggers`` looks at the sequence of shapes and constraints it is evaluating and "backs out"
(with a ``ShapeRecursionWarning``) when the same shape has come round again, whatever the data looks like. For a shape such as
``ex:PersonShape sh:property [ sh:path ex:friend ; sh:node ex:PersonShape ]`` that means a chain of three or more friends, with
no cycle anywhere in the data, is cut short: a violation at the end of the chain is never found and the report says it conforms
(reproduced with plain pySHACL 0.40.1, see ``docs/upstream-issues/pyshacl-upstream-issues.md``).

This module replaces that heuristic with the exact rule: **a (shape, node) pair that is already being evaluated further up the
call chain is assumed to conform** (the usual greatest-fixpoint reading), and everything else is evaluated. Data without a cycle is evaluated in
full, exactly as if the recursive shape had been written out as many copies as the data is deep; data with a cycle stops, because
the same pair cannot be entered twice. ``recursion_triggers`` is switched off, so no ``ShapeRecursionWarning`` is raised.

Process-global, like the other pySHACL patches here. ``revisits()`` counts the pairs that were assumed conformant, for the
``recursion_revisits`` diagnostic.
"""

from __future__ import annotations

import threading
from typing import Any

# pySHACL's own guard against runaway recursion (its default is 15 levels). Cycles are caught exactly now, so this is only a safety net
# well beyond what Python's recursion limit allows anyway (about 120 hops of a self-referencing shape).
MAX_VALIDATION_DEPTH = 500

_installed = False
_counter = threading.local()


def revisits() -> int:
    """How many (shape, node) pairs were assumed conformant, on this thread, since ``reset_revisits()``."""
    return getattr(_counter, "n", 0)


def reset_revisits() -> None:
    _counter.n = 0


def _no_triggers(self: Any, _evaluation_path: Any, trigger_depth: int = 3) -> None:  # noqa: ARG001
    """Replaces ``ConstraintComponent.recursion_triggers``: never "potentially recursive". Cycles are caught exactly, in
    ``Shape.validate``."""
    return None


def install_recursion_patch() -> bool:
    """Install the exact cycle check. Idempotent. ``False`` (and nothing patched) if pySHACL's internals are not what this expects."""
    global _installed
    if _installed:
        return True
    try:
        from pyshacl.constraints.constraint_component import ConstraintComponent
        from pyshacl.pytypes import SHACLExecutor
        from pyshacl.shape import Shape
        from rdflib import Literal
        from rdflib.term import IdentifiedNode

        original_validate = Shape.validate
        if getattr(original_validate, "_starlayer_shacl_recursion_patch", False):
            _installed = True
            return True

        def _validate(self, executor_or_graph, target_graph_or_focus=None, focus=None, **kwargs):
            # Only a nested call (one with focus nodes given) is a step down a chain. The top-level call evaluates all of a shape's
            # targets together as a batch, and those are siblings, not ancestors of each other: registering them would make a node
            # reached through another target (alice -> bob, both targets) look like a cycle. A nested call is keyed by the whole
            # set of focus nodes, so an identical batch coming round again (a shape that refers to itself on the same nodes) is a
            # revisit too; the sets are finite, so any runaway recursion repeats one.
            if focus is None or not isinstance(executor_or_graph, SHACLExecutor) or self.deactivated:
                return original_validate(self, executor_or_graph, target_graph_or_focus, focus=focus, **kwargs)
            executor = executor_or_graph
            nodes = frozenset([focus] if isinstance(focus, (IdentifiedNode, Literal)) else focus)
            key = (self.node, nodes)
            active = executor.__dict__.setdefault("_starlayer_active_pairs", set())
            if key in active:
                _counter.n = getattr(_counter, "n", 0) + 1
                return True, []
            active.add(key)
            try:
                return original_validate(self, executor, target_graph_or_focus, focus=focus, **kwargs)
            finally:
                active.discard(key)

        _validate._starlayer_shacl_recursion_patch = True  # type: ignore[attr-defined]
        Shape.validate = _validate
        ConstraintComponent.recursion_triggers = _no_triggers
        _installed = True
    except Exception:
        return False
    return True
