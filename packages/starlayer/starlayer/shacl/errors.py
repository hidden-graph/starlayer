"""The errors SHACL processing raises, importable from ``starlayer.shacl``.

``ShapeError``: the shapes graph is ill-formed or asks for something unsupported (a shape the engine cannot read).
``RuleError``: a rule failed, or the rules are ill-formed (the rule set fails as a whole).
``EvaluationFailure``: a node expression has an evaluation failure (SHACL 1.2 Node Expressions 3.2).
``MetaShaclError``: the shapes graph fails the shapes-about-shapes check (``meta_shacl=True``). ``ShapeError``, ``RuleError`` and
``MetaShaclError`` are ``ValueError`` subclasses; ``EvaluationFailure`` is a plain ``Exception`` (callers that treat it as "no value" catch it).
"""

from __future__ import annotations

from starlayer.shacl_engine.expressions import EvaluationFailure
from starlayer.shacl_engine.meta import MetaShaclError
from starlayer.shacl_engine.plan import ShapeError
from starlayer.shacl_engine.rules import RuleError

__all__ = ["EvaluationFailure", "MetaShaclError", "RuleError", "ShapeError"]
