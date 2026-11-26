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

``ExecutionError`` is one class; its ``kind`` (a key of ``ExecutionError.KINDS``, which maps each kind to a one-line meaning and is the
one list of the kinds) says what failed, and ``FormatError`` is one class too, its ``kind`` a key of ``FormatError.KINDS``. Notes the
one-liners cannot carry:

* ``"internal"``: the message always starts "internal error (a bug in StarLayer, please report it at <ISSUES_URL>): " (added once, in
  ``ExecutionError``, never at a raise site) and ``report_url`` is that URL (``None`` for every other kind).
* ``"unsupported"`` and ``"internal"`` differ in who asked: ``"unsupported"`` is the user asking for something StarLayer cannot do
  (the user can see the limit and choose differently: a name that is not a registered entailment regime, in a call or in a shapes
  graph's ``sh:entailment``; a format that cannot hold what was given, such as a named graph for Turtle; a term Manchester syntax has
  no form for; ``relevant_subgraph`` given a ``DESCRIBE`` or ``SERVICE`` query; a blank node that came from an endpoint being written
  back; a base-direction literal under the ``"error"`` policy of the RDF 1.1 export); ``"internal"`` is StarLayer asking itself for something it cannot do (an OWL regime reaching the query rewrite), a
  bug the user cannot fix.
* ``"import"``: a declared import is not resolved, on every path that resolves imports (an RDF or OWL graph's ``owl:imports``, a shapes
  graph's, an ontology graph's, an SRL rule set's ``IMPORTS``). An import is satisfied when its IRI is a subject in the graph after
  resolution (or is a built-in ontology of the ``starontology`` registry; for SRL, when the loader produced a rule set for it); one that
  is not, because there was no loader or it returned nothing or a graph without that IRI, is this error, with the IRIs in ``unresolved``
  and ``context`` ``"owl:imports <iri>"``. A loader that raises is wrapped (this kind, the loader's exception as ``__cause__``).
  ``ignore_imports=True`` skips the whole step. An imported SRL text that is not a valid rule set is a ``FormatError`` of kind ``"srl"``
  instead, and a malformed declaration (an ``owl:imports`` object that is not an IRI) is a ``FormatError`` of kind ``"owl"`` for a graph
  and a ``ShapeCompileError`` for a shapes graph.
* ``"limit"``: a depth limit's ``context`` says what was too deep (a query, tree or class expression nested past the stack, the
  validation path or node expressions nested past ``max_validation_depth`` or the expression depth).
* ``FormatError`` kind ``"rdf"`` covers an RDF document, a list, an encoding and a term (the smallest piece of RDF text; ``context``
  says which), ``"srl"`` SRL text, an ``srl:`` tree, a rule set built or edited by hand that holds something that is not a rule body
  element, and a goal pattern whose predicate SRL does not allow. A position (``line`` and ``col`` 1-based, ``pos`` a 0-based offset)
  is set only by code that knows it, never parsed out of an engine message.

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
    parameter, query or rule, an unsupported construct, or an ``owl:imports`` declaration that is malformed (an object that is not an IRI; an import that is merely not resolved is ``ExecutionError`` kind ``"import"``). Not a ``MetaShaclError``, which the
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

    One class; ``kind`` says what failed (a plain string, one of ``KINDS``: the mapping of every kind to its meaning). ``kind`` names the cause
    and never changes with the path the error travels: an expression that cannot be evaluated is ``"expression"`` whether
    ``validate()`` or a rule met it, and ``"rule"`` is only for a failure that is about the rule itself. Where it happened (which
    rule, shape, focus node or call) is ``context`` (a short string, default ``None``) and is also in the message, so ``str(error)``
    stays the whole text and a program reads ``context`` alone.

    ``unresolved`` (default ``()``, keyword-only) is the tuple of import IRIs (``NamedNode``) that were not resolved: set for kind ``"import"``
    only, so an application can load them and call again (``starlayer.graph.unresolved_imports`` asks the same of a graph).

    Catch ``ExecutionError`` and test ``error.kind``; ``only_kind`` does the test inside a clause."""

    #: Every kind and what it means (iterate it or use ``in`` for the names); ``kind`` itself is always the plain string.
    KINDS = {
        "rule": "a rule failed while running, or the rule set failed as a whole (an SRL rule set that cannot be ordered)",
        "expression": "a node expression cannot be evaluated, an error and not an empty result",
        "recursion": "a shape reaches itself on a focus node through sh:not (a cycle in the data)",
        "constraint-query": "a sh:sparql constraint query reported ?failure true",
        "internal": "StarLayer asked itself for something it cannot do: a bug in StarLayer, to be reported (report_url)",
        "timeout": "an OWL-DL reasoning call did not finish within its time budget and was killed",
        "inconsistent": "the OWL-DL reasoner found the data logically inconsistent",
        "inference": "the reasoner could not run or died: Java missing or broken, or a reasoning subprocess that exited without a result",
        "query": "the SPARQL engine failed while evaluating a query or update whose text parsed",
        "import": "a declared import (owl:imports, an SRL IMPORTS) is not resolved",
        "unsupported": "valid input that the library or the target notation cannot handle: the user asked for something StarLayer cannot do and can choose differently",
        "limit": "a size or complexity cap of the library was reached (a depth limit, RDFC-1.0's symmetry defence, max_iterations, max_triples)",
    }

    def __init__(self, message: str, *, kind: str, context: str | None = None, unresolved: tuple[Any, ...] = ()) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown ExecutionError kind {kind!r}; one of {', '.join(self.KINDS)}")
        if kind == "internal" and _INTERNAL_MARK not in message:  # once: a re-raised or rebuilt error already has it somewhere in its text
            message = _INTERNAL_MARK + message
        super().__init__(message)
        self.kind = kind
        self.context = context
        self.unresolved = tuple(unresolved)

    @property
    def report_url(self) -> str | None:
        """``ISSUES_URL`` for kind ``"internal"`` (a bug in StarLayer: the message says so and an application can show the link), else ``None``."""
        return ISSUES_URL if self.kind == "internal" else None

    def __reduce__(self) -> Any:  # the keyword-only ``kind`` and ``context`` must survive pickle and copy
        return (_rebuild_execution_error, (self.args[0] if self.args else "", self.kind, self.context, self.unresolved))


def _rebuild_execution_error(message: str, kind: str, context: str | None = None, unresolved: tuple[Any, ...] = ()) -> ExecutionError:
    return ExecutionError(message, kind=kind, context=context, unresolved=unresolved)


class FormatError(StarLayerError):
    """Text or data is malformed: SPARQL text, an ``sqe:`` tree, a ``VERSION`` declaration, and in later stages SRL, RDF documents,
    terms, Manchester syntax and OWL-in-RDF. Not a ``ValueError``, ``SyntaxError`` or ``SyntaxError`` subclass.

    One class; ``kind`` says what is malformed (one of ``KINDS``) and never changes with the path the error travels. ``context`` is where
    it was found (a short string, default ``None``). ``why`` is the reason without the position (default: the message); ``line`` and
    ``col`` (1-based) and ``pos`` (a 0-based offset) are ``None`` unless the code that raised it knew them: they are never read out of
    an engine's message. ``message`` defaults to ``why``."""

    #: Every kind and what is malformed (iterate it or use ``in`` for the names); ``kind`` itself is always the plain string.
    KINDS = {
        "sparql": "SPARQL query or update text, an sqe: tree, a VERSION declaration",
        "srl": "SRL text, an srl: tree, a rule set built with something that is not a rule body element, a bad DATA block, a rule set that breaks the SRL rules",
        "rdf": "an RDF document that cannot be parsed, the text of a term (an IRI, a language tag, a lexical form), a list that is not well formed, a name that has no prefixed form",
        "manchester": "Manchester Syntax text, a manch: tree, a SWRL Rule: frame",
        "owl": "RDF that is not valid OWL when it is written as Manchester Syntax, or a malformed owl:imports declaration",
    }

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
