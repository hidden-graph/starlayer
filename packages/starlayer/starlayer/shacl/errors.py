"""The errors SHACL processing raises, importable from ``starlayer.shacl``. They are classified by cause.

``ShapeError``: the base of the shapes-graph errors. The shapes graph (a shape, a rule, a rules graph) or its setup (an ``owl:imports``
that cannot be resolved) is wrong or asks for something unsupported, found by anyone. A ``ValueError`` subclass, never raised bare, so
``except ShapeError`` catches either kind below:

* ``ShapeCompileError``: the engine itself cannot read or compile the shapes graph, its rules or its setup, whenever it finds out (when a
  processor is built, or later in a run).
* ``MetaShaclError``: the meta check (the shapes-about-shapes, ``meta_shacl=True``) found it. Carries ``problems``, ``report_text``,
  ``report_graph`` and ``scope``.

``ExecutionError``: the shapes graph is fine and running it failed. A plain ``Exception`` on purpose, not a ``ValueError`` and not a
``ShapeError``, so that an ``except ValueError`` cannot swallow it. One class; its ``kind`` attribute says what failed:

* ``"rule"``: a rule failed while running, ``max_iterations`` or ``max_triples`` was exceeded, or the rule set failed as a whole.
* ``"expression"``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
* ``"nesting"``: the validation path or node expressions nest deeper than the limit (a cyclic expression, a recursive function).
* ``"recursion"``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
* ``"constraint-query"``: a ``sh:sparql`` constraint query reported ``?failure true``.

A bad argument to a public call (a role that is not ``"editor"`` or ``"viewer"``, a shape name the shapes graph does not have) is a plain
``ValueError`` or ``TypeError``, raised before any shape is read.
"""

from __future__ import annotations

from starlayer.shacl.engine.meta import MetaShaclError
from starlayer.shacl.engine.plan import (
    ExecutionError,
    ShapeCompileError,
    ShapeError,
)

__all__ = [
    "ExecutionError",
    "MetaShaclError",
    "ShapeCompileError",
    "ShapeError",
]
