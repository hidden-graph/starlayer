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
     |- ExecutionError              running failed (SHACL with a fine shapes graph, a query the engine could not evaluate, OWL-DL reasoning); has ``kind`` and ``context``
     |- FormatError                 text or data that is malformed; has ``kind``, ``context`` and the optional ``why``, ``line``, ``col``, ``pos``
     `- EndpointError(StarLayerError, OSError)   a SPARQL endpoint could not be reached or answered with an error status; has ``status``
                                    (``starlayer.graph.endpoint``; it stays an ``OSError`` because a network failure is an I/O error)

``ExecutionError`` is one class; its ``kind`` (one of ``ExecutionError.KINDS``) says what failed:

* ``"rule"``: a rule failed while running, or the rule set failed as a whole (an SRL
  rule set whose rules cannot be ordered, §4.4.1).
* ``"expression"``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
* ``"recursion"``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
* ``"constraint-query"``: a ``sh:sparql`` constraint query reported ``?failure true``.
* ``"internal"``: the engine failed an assertion about its own result, a bug in StarLayer to be reported. The message of this kind
  always starts "internal error (a bug in StarLayer, please report it at <ISSUES_URL>): " (added once, in ``ExecutionError``, never
  at a raise site) and ``report_url`` is that URL (``None`` for every other kind).
* ``"timeout"``: an OWL-DL reasoning call (either engine) did not finish within its wall-clock budget and was killed.
* ``"inconsistent"``: the OWL-DL reasoner found the data logically inconsistent under OWL 2 DL semantics.
* ``"query"``: the SPARQL engine (Oxigraph) failed while evaluating a query or update (its ``RuntimeError``), for text that parsed.
* ``"inference"``: the reasoner could not run or died: a Java runtime that is missing or broken, an owlready2 Java error, or a
  reasoning subprocess that exited without a result (a crash, not a timeout).
* ``"import"``: an SRL ``IMPORTS`` document cannot be loaded (the loader failed) or an imported rule set was never resolved, so the
  rule set cannot be run (§4.5). An imported text that is not a valid rule set is a ``FormatError`` of kind ``"srl"`` instead.
* ``"unsupported"``: valid input the library or the target notation cannot handle, nobody's mistake, as against malformed input (a
  ``FormatError``) and a bad argument (a ``ValueError``): the Manchester serializer meeting a term, literal or axiom that Manchester
  syntax has no form for, a query-time entailment rewrite that has no exact form for the query, a name that is not a registered
  entailment regime, ``relevant_subgraph`` given a ``DESCRIBE`` or ``SERVICE`` query, a blank node that came from an endpoint being
  written back, and a base-direction literal under the ``"error"`` policy of the RDF 1.1 export.
* ``"limit"``: a size or complexity cap of the library was reached, as against a bug (``"internal"``): a depth limit (a query, tree or
  class expression nested past the stack, the validation path or node expressions nested past ``max_validation_depth`` or the expression
  depth; ``context`` says what was too deep), RDFC-1.0's defence against a highly symmetric blank-node structure (§7.1), and the SHACL rule caps ``max_iterations``
  and ``max_triples``.

``FormatError`` is one class too; its ``kind`` (one of ``FormatError.KINDS``) says what is malformed: ``"sparql"`` (SPARQL query or
update text, an ``sqe:`` tree, a ``VERSION`` declaration), ``"srl"``, ``"rdf"``, ``"term"``, ``"manchester"``, ``"owl"``. ``"srl"`` covers SRL text, an ``srl:`` tree, a rule set built or edited by hand that holds something
that is not a rule body element, and a goal pattern whose predicate SRL does not allow. A position
(``line`` and ``col`` 1-based, ``pos`` a 0-based offset) is set only by code that knows it, never parsed out of an engine message.

The class and the ``kind`` name the cause and never change with the path an error travels. Where it happened is ``context`` (a short
string such as ``"sh:rule ex:R1"``, ``None`` when nothing narrows it), repeated in the message; a handler that knows the place sets it
and re-raises the same class and kind.

The SHACL errors are importable from ``starlayer.shacl`` and ``starlayer.shacl.errors`` too (the same class objects). Every error the
library raises on purpose derives from ``StarLayerError``, ``EndpointError`` included; a plain ``ValueError`` or ``TypeError`` is a bad
argument at the entry of a public call, ``ImportError`` a missing optional package, and ``NotImplementedError`` a wrapper method the
object does not have.
"""

from __future__ import annotations

from typing import Any

#: Where a bug in StarLayer is reported; ``ExecutionError.report_url`` is this for kind ``"internal"``, so an application built on StarLayer can show it.
ISSUES_URL = "https://github.com/hidden-graph/starlayer/issues"
_INTERNAL_MARK = f"internal error (a bug in StarLayer, please report it at {ISSUES_URL}): "


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

    KINDS = ("rule", "expression", "recursion", "constraint-query", "internal", "timeout", "inconsistent", "inference", "query", "import", "unsupported", "limit")

    def __init__(self, message: str, *, kind: str, context: str | None = None) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown ExecutionError kind {kind!r}; one of {', '.join(self.KINDS)}")
        if kind == "internal" and _INTERNAL_MARK not in message:  # once: a re-raised or rebuilt error already has it somewhere in its text
            message = _INTERNAL_MARK + message
        super().__init__(message)
        self.kind = kind
        self.context = context

    @property
    def report_url(self) -> str | None:
        """``ISSUES_URL`` for kind ``"internal"`` (a bug in StarLayer: the message says so and an application can show the link), else ``None``."""
        return ISSUES_URL if self.kind == "internal" else None

    def __reduce__(self) -> Any:  # the keyword-only ``kind`` and ``context`` must survive pickle and copy
        return (_rebuild_execution_error, (self.args[0] if self.args else "", self.kind, self.context))


def _rebuild_execution_error(message: str, kind: str, context: str | None = None) -> ExecutionError:
    return ExecutionError(message, kind=kind, context=context)


class FormatError(StarLayerError):
    """Text or data is malformed: SPARQL text, an ``sqe:`` tree, a ``VERSION`` declaration, and in later stages SRL, RDF documents,
    terms, Manchester syntax and OWL-in-RDF. Not a ``ValueError``, ``SyntaxError`` or ``SyntaxError`` subclass.

    One class; ``kind`` says what is malformed (one of ``KINDS``) and never changes with the path the error travels. ``context`` is where
    it was found (a short string, default ``None``). ``why`` is the reason without the position (default: the message); ``line`` and
    ``col`` (1-based) and ``pos`` (a 0-based offset) are ``None`` unless the code that raised it knew them: they are never read out of
    an engine's message. ``message`` defaults to ``why``."""

    KINDS = ("sparql", "srl", "rdf", "term", "manchester", "owl")

    def __init__(self, message: str | None = None, *, kind: str, context: str | None = None, why: str | None = None,
                 line: int | None = None, col: int | None = None, pos: int | None = None) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown FormatError kind {kind!r}; one of {', '.join(self.KINDS)}")
        if message is None:
            message = why if why is not None else ""
        super().__init__(message)
        self.kind = kind
        self.context = context
        self.why = why if why is not None else message
        self.line = line
        self.col = col
        self.pos = pos

    def __reduce__(self) -> Any:  # the keyword-only fields must survive pickle and copy
        return (_rebuild_format_error, (self.args[0] if self.args else "", self.kind, self.context, self.why, self.line, self.col, self.pos))


def _rebuild_format_error(message: str, kind: str, context: str | None, why: str | None, line: int | None, col: int | None,
                          pos: int | None) -> FormatError:
    return FormatError(message, kind=kind, context=context, why=why, line=line, col=col, pos=pos)


def only_kind(error: ExecutionError, *kinds: str) -> None:
    """For an ``except ExecutionError as error`` clause that handles only some kinds: returns when ``error.kind`` is one of ``kinds``
    and raises ``error`` again otherwise, so a clause that means "no value" cannot swallow a rule, limit or recursion failure."""
    if error.kind not in kinds:
        raise error
