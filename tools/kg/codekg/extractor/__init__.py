"""codekg.extractor - pure-logic pieces of the code-KG extractor.

Each sibling module here (``imports``, ``types``, ``docstrings``) is
self-contained and independently importable, with no dependency on each
other or on the not-yet-built AST visitor/build orchestration/CLI. This
``__init__.py`` deliberately re-exports nothing - callers import the
specific module they need (``from codekg.extractor import
imports`` etc.) rather than a flattened namespace, so each module's own
docstring stays the one place describing its contract.
"""
