"""The errors StarLayer raises on purpose. A leaf module: it imports only the standard library, so any part of the package can
import it without an import cycle.

``StarLayerError`` is the base of every error the library raises by design (``except StarLayerError`` means "the library said no").
It derives from ``Exception`` only, never from ``ValueError``, ``SyntaxError``, ``RuntimeError`` or ``OSError``: a plain
``ValueError`` (or ``TypeError``) is reserved for a bad argument at the entry of a public call, so a library error cannot be swallowed
by an ``except ValueError`` meant for that.

The tree::

    StarLayerError(Exception)
     |- ShapeError                  the shapes graph (a shape, a rule, a rules graph) or its setup is wrong; has ``context``
     |   |- ShapeCompileError       the engine cannot read or compile it
     |   `- MetaShaclError          the meta check (shapes-about-shapes) found it: ``problems``, ``report_text``, ``report_graph``, ``scope``
     `- ExecutionError              running failed (SHACL with a fine shapes graph, or OWL-DL reasoning); has ``kind`` and ``context``

``ExecutionError`` is one class; its ``kind`` (one of ``ExecutionError.KINDS``) says what failed:

* ``"rule"``: a rule failed while running, ``max_iterations`` or ``max_triples`` was exceeded, or the rule set failed as a whole.
* ``"expression"``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
* ``"nesting"``: the validation path or node expressions nest deeper than the limit (a cyclic expression, a recursive function).
* ``"recursion"``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
* ``"constraint-query"``: a ``sh:sparql`` constraint query reported ``?failure true``.
* ``"internal"``: the engine failed an assertion about its own result, a bug in StarLayer to be reported.
* ``"timeout"``: an OWL-DL reasoning call (either engine) did not finish within its wall-clock budget and was killed.
* ``"inconsistent"``: the OWL-DL reasoner found the data logically inconsistent under OWL 2 DL semantics.
* ``"inference"``: the reasoner could not run or died: a Java runtime that is missing or broken, an owlready2 Java error, or a
  reasoning subprocess that exited without a result (a crash, not a timeout).

The class and the ``kind`` name the cause and never change with the path an error travels. Where it happened is ``context`` (a short
string such as ``"sh:rule ex:R1"``, ``None`` when nothing narrows it), repeated in the message; a handler that knows the place sets it
and re-raises the same class and kind.

The SHACL errors are importable from ``starlayer.shacl`` and ``starlayer.shacl.errors`` too (the same class objects). The other error
classes of the library are not yet derived from ``StarLayerError``.
"""

from __future__ import annotations

from typing import Any


class StarLayerError(Exception):
    """The base of the errors StarLayer raises on purpose. Never raised bare, and not a ``ValueError``, ``SyntaxError``,
    ``RuntimeError`` or ``OSError``."""


class ShapeError(StarLayerError):
    """The base of the shapes-graph errors: the shapes graph, its rules or its setup is wrong or asks for something unsupported (the
    W3C suite's ``sht:Failure`` cases), found by anyone. Raised as ``ShapeCompileError`` (the engine cannot read or compile it) or
    ``MetaShaclError`` (the meta check found it); catch ``ShapeError`` for either.

    The class names the cause and never changes with the path the error travels. ``context`` (default ``None``) is a short string
    for where it was found, such as ``"sh:rule ex:R1"``; a handler that knows the place sets it and keeps the class. The message
    carries the same text, so ``str(error)`` is enough for a person and ``context`` is there for a program."""

    def __init__(self, *args: Any, context: str | None = None) -> None:
        super().__init__(*args)
        self.context = context


class ShapeCompileError(ShapeError):
    """The engine itself cannot read or compile the shapes graph, its rules or its setup: a malformed shape, path, constraint
    parameter, query or rule, an unsupported construct, or an ``owl:imports`` it cannot resolve. Not a ``MetaShaclError``, which the
    meta check (shacl_shacl) raises."""


class MetaShaclError(ShapeError):
    """The shapes graph does not validate against the meta-shapes (the meta check found it, as against ``ShapeCompileError``, where the engine cannot compile it); the message says which shape and property each problem is about.

    ``problems`` has one line per result, ``report_text`` is the full validation report of the check and ``report_graph`` the same
    report as a graph, for a caller that shows each result next to its focus node. ``scope`` is the ``MetaScope`` the failed check
    used (``None`` for an error raised elsewhere), so a caller can tell a narrow check from a full one."""

    def __init__(self, message: str, problems: tuple[str, ...] = (), report_text: str = "", report_graph: Any = None,
                 scope: Any = None, *, context: str | None = None) -> None:
        super().__init__(message, context=context)
        self.scope = scope
        self.problems = problems
        self.report_text = report_text
        self.report_graph = report_graph


class ExecutionError(StarLayerError):
    """Running failed: for SHACL the shapes graph is fine, for OWL-DL reasoning the input is fine and the reasoner timed out, found
    the data inconsistent or could not run. Not a ``ShapeError`` and not a ``ValueError``: a handler for a wrong shapes graph (or a
    bad argument) must not swallow it.

    One class; ``kind`` says what failed (a plain string, one of ``KINDS``, listed in the module docstring). ``kind`` names the cause
    and never changes with the path the error travels: an expression that cannot be evaluated is ``"expression"`` whether
    ``validate()`` or a rule met it, and ``"rule"`` is only for a failure that is about the rule itself. Where it happened (which
    rule, shape, focus node or call) is ``context`` (a short string, default ``None``) and is also in the message, so ``str(error)``
    stays the whole text and a program reads ``context`` alone.

    Catch ``ExecutionError`` and test ``error.kind``; ``only_kind`` does the test inside a clause."""

    KINDS = ("rule", "expression", "nesting", "recursion", "constraint-query", "internal", "timeout", "inconsistent", "inference")

    def __init__(self, message: str, *, kind: str, context: str | None = None) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown ExecutionError kind {kind!r}; one of {', '.join(self.KINDS)}")
        super().__init__(message)
        self.kind = kind
        self.context = context

    def __reduce__(self) -> Any:  # the keyword-only ``kind`` and ``context`` must survive pickle and copy
        return (_rebuild_execution_error, (self.args[0] if self.args else "", self.kind, self.context))


def _rebuild_execution_error(message: str, kind: str, context: str | None = None) -> ExecutionError:
    return ExecutionError(message, kind=kind, context=context)


def only_kind(error: ExecutionError, *kinds: str) -> None:
    """For an ``except ExecutionError as error`` clause that handles only some kinds: returns when ``error.kind`` is one of ``kinds``
    and raises ``error`` again otherwise, so a clause that means "no value" cannot swallow a rule, nesting or recursion failure."""
    if error.kind not in kinds:
        raise error
