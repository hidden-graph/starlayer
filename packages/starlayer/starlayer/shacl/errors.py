"""The errors SHACL processing raises, importable from ``starlayer.shacl``. They are classified by cause.

``ShapeError``: the shapes graph (a shape, a rule, a rules graph) or its setup (an ``owl:imports`` that cannot be resolved) is wrong or asks
for something unsupported, whenever the engine finds it (when a processor is built, or later in a run). A ``ValueError`` subclass.
``MetaShaclError``: the shapes graph fails the shapes-about-shapes check (``meta_shacl=True``), also a ``ValueError`` subclass.
``ExecutionError``: the shapes graph is fine and running it failed. A plain ``Exception`` on purpose, not a ``ValueError``, so that an
``except ValueError`` cannot swallow it. Its subclasses:

* ``RuleError``: a rule failed while running, or the rules did not reach a fixpoint within ``max_iterations``.
* ``EvaluationFailure``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
* ``NestingTooDeep``: shapes or node expressions nest deeper than the limit (a cyclic expression, a recursive function).
* ``RecursionThroughNot``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
* ``ConstraintQueryFailure``: a ``sh:sparql`` constraint query reported ``?failure true``.
"""

from __future__ import annotations

from starlayer.shacl.engine.expressions import EvaluationFailure
from starlayer.shacl.engine.meta import MetaShaclError
from starlayer.shacl.engine.plan import (
    ConstraintQueryFailure,
    ExecutionError,
    NestingTooDeep,
    RecursionThroughNot,
    ShapeError,
)
from starlayer.shacl.engine.rules import RuleError

__all__ = [
    "ConstraintQueryFailure",
    "EvaluationFailure",
    "ExecutionError",
    "MetaShaclError",
    "NestingTooDeep",
    "RecursionThroughNot",
    "RuleError",
    "ShapeError",
]
