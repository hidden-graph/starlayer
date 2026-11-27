"""The errors StarLayer raises on purpose. A leaf module: it imports only the standard library, so any part of the package can
import it without an import cycle.

``StarLayerError`` is the base of every error the library raises by design (``except StarLayerError`` means "the library said no").
It derives from ``Exception`` only, never from ``ValueError``, ``SyntaxError``, ``RuntimeError`` or ``OSError``: a plain
``ValueError`` (or ``TypeError``) is reserved for a bad argument at the entry of a public call, so a library error cannot be swallowed
by an ``except ValueError`` meant for that.

The tree::

    StarLayerError(Exception)
     |- ShapeError                  the shapes graph (a shape, a rule, a rules graph) or its setup is wrong; has ``kind`` (``"compile"``:
     |                              the engine cannot read or compile it; ``"meta"``: the meta check found it, with ``problems``,
     |                              ``report_text``, ``report_graph``, ``scope``) and ``context``
     |- ExecutionError              running failed (SHACL with a fine shapes graph, a query the engine could not evaluate, OWL-DL reasoning); has ``kind`` and ``context``
     |- FormatError                 text or data that is malformed; has ``kind``, ``context`` and the optional ``why``, ``line``, ``col``, ``pos``
     `- EndpointError(StarLayerError, OSError)   a SPARQL endpoint failed; has ``kind``, ``context`` and ``status`` (also importable from
                                    ``starlayer.graph``; it stays an ``OSError`` because a network failure is an I/O error)

``ExecutionError`` is one class; its ``kind`` (a key of ``ExecutionError.KINDS``, which maps each kind to a one-line meaning and is the
one list of the kinds) says what failed, and ``FormatError``, ``ShapeError`` and ``EndpointError`` are one class each too, their ``kind`` a key of
``FormatError.KINDS``, ``ShapeError.KINDS`` and ``EndpointError.KINDS``. Notes the
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
  and a ``ShapeError`` of kind ``"compile"`` for a shapes graph.
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
    """The shapes graph (a shape, a rule, a rules graph) or its setup is wrong or asks for something unsupported (the W3C suite's
    ``sht:Failure`` cases), found by anyone.

    One class; ``kind`` says who found it (a plain string, one of ``KINDS``: the mapping of every kind to its meaning) and never
    changes with the path the error travels. ``context`` (default ``None``) is a short string for where it was found, such as
    ``"sh:rule ex:R1"``; a handler that knows the place sets it and keeps the class and kind. The message carries the same text, so
    ``str(error)`` is enough for a person and ``context`` is there for a program.

    For kind ``"meta"`` (the meta check found the shapes graph invalid; the message says which shape and property each problem is
    about) ``problems`` has one line per result, ``report_text`` is the full validation report of the check and ``report_graph`` the
    same report as a graph, for a caller that shows each result next to its focus node. ``scope`` is the ``MetaScope`` the failed
    check used (``None`` for an error raised elsewhere), so a caller can tell a narrow check from a full one. For kind ``"compile"``
    these keep their defaults (``()``, ``""``, ``None``, ``None``).

    Catch ``ShapeError`` and test ``error.kind``; ``only_kind`` does the test inside a clause."""

    #: Every kind and what it means (iterate it or use ``in`` for the names); ``kind`` itself is always the plain string.
    KINDS = {
        "compile": "Malformed or unsupported shapes: a bad shape, path, constraint parameter, query or rule; an unsupported construct; an owl:imports object that is not an IRI",
        "meta": "Shapes graph that is invalid against the SHACL-SHACL meta shapes (meta_shacl=True); problems and the report say how",
    }

    def __init__(self, message: str = "", *, kind: str, context: str | None = None, problems: tuple[str, ...] = (),
                 report_text: str = "", report_graph: Any = None, scope: Any = None) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown ShapeError kind {kind!r}; one of {', '.join(self.KINDS)}")
        super().__init__(message)
        self.kind = kind
        self.context = context
        self.problems = tuple(problems)
        self.report_text = report_text
        self.report_graph = report_graph
        self.scope = scope

    def __reduce__(self) -> Any:  # the keyword-only fields must survive pickle and copy
        return (_rebuild_shape_error, (self.args[0] if self.args else "", self.kind, self.context, self.problems, self.report_text,
                                       self.report_graph, self.scope))


def _rebuild_shape_error(message: str, kind: str, context: str | None, problems: tuple[str, ...], report_text: str,
                         report_graph: Any, scope: Any) -> ShapeError:
    return ShapeError(message, kind=kind, context=context, problems=problems, report_text=report_text, report_graph=report_graph,
                      scope=scope)


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
        "rule": "Failed rule, or a rule set that fails as a whole (for example, one that cannot be ordered)",
        "expression": "Node expression that cannot be evaluated",
        "recursion": "Shape that reaches itself through sh:not (a cycle in the data)",
        "constraint-query": "sh:sparql constraint query that reported ?failure true",
        "internal": "Bug in StarLayer (it asked itself for something it cannot do); report it (report_url)",
        "timeout": "OWL-DL reasoning that exceeded its time budget",
        "inconsistent": "Data found logically inconsistent by the OWL-DL reasoner",
        "inference": "Reasoner that could not run or died (Java missing or broken, or the subprocess exited without a result)",
        "query": "SPARQL engine failure on a query or update whose text parsed",
        "import": "Unresolved owl:imports or SRL IMPORTS",
        "unsupported": "Valid input that the library or the target notation cannot handle",
        "limit": "Size or complexity cap reached (nesting depth, RDFC-1.0 symmetry, max_iterations, max_triples)",
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
        "sparql": "Malformed SPARQL text, sqe: tree or VERSION declaration",
        "srl": "Malformed SRL text, srl: tree, DATA block or rule body element, or a rule set that breaks the SRL rules",
        "rdf": "Malformed RDF document, term text (IRI, language tag, lexical form), list or prefixed name",
        "manchester": "Malformed Manchester Syntax text, manch: tree or SWRL Rule: frame",
        "owl": "Invalid OWL in RDF, or a malformed owl:imports declaration",
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


class EndpointError(StarLayerError, OSError):
    """A SPARQL endpoint failed: it could not be reached, answered with an error status or answered in a form StarLayer cannot read.
    Still an ``OSError`` (a network failure is an I/O error), so ``except OSError`` keeps working; one class, like the others.

    ``kind`` says what failed (a plain string, one of ``KINDS``: the mapping of every kind to its meaning). ``status`` (second
    positional argument, default ``None``) is the HTTP status, set for kind ``"http"``. ``context`` (default ``None``) is the URL
    involved, also in the message. Catch ``EndpointError`` and test ``error.kind``; ``only_kind`` does the test inside a clause."""

    #: Every kind and what it means (iterate it or use ``in`` for the names); ``kind`` itself is always the plain string.
    KINDS = {
        "http": "Error status answered by the endpoint (status holds it)",
        "unreachable": "Host that cannot be reached: the connection failed or timed out",
        "content-type": "Answer in a content type StarLayer cannot read",
    }

    def __init__(self, message: str = "", status: int | None = None, *, kind: str, context: str | None = None) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown EndpointError kind {kind!r}; one of {', '.join(self.KINDS)}")
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.context = context

    def __reduce__(self) -> Any:  # the keyword-only fields must survive pickle and copy
        return (_rebuild_endpoint_error, (self.args[0] if self.args else "", self.status, self.kind, self.context))


def _rebuild_endpoint_error(message: str, status: int | None, kind: str, context: str | None) -> EndpointError:
    return EndpointError(message, status, kind=kind, context=context)


def only_kind(error: ExecutionError | FormatError | ShapeError | EndpointError, *kinds: str) -> None:
    """For an ``except ExecutionError as error`` (or ``FormatError``, ``ShapeError``, ``EndpointError``) clause that handles only some kinds: returns when ``error.kind`` is one of ``kinds``
    and raises ``error`` again otherwise, so a clause that means "no value" cannot swallow a rule, limit or recursion failure."""
    if error.kind not in kinds:
        raise error
