"""The errors SHACL processing raises, importable from ``starlayer.shacl``. They are defined in ``starlayer.errors``,
the library's leaf error module; this module and ``starlayer.shacl`` re-export the same class objects. They are classified by cause.

Each derives from ``StarLayerError`` and from nothing else, so none is a ``ValueError``: a plain ``ValueError`` or ``TypeError`` is
only a bad argument at the entry of a public call, and ``except ValueError`` never catches one of these.

``ShapeError``: the shapes graph (a shape, a rule, a rules graph) or its setup (an ``owl:imports`` declaration that is not an IRI; an
import that is merely not resolved is ``ExecutionError`` kind ``"import"``) is wrong or asks for something unsupported, found by anyone.
One class; its ``kind`` (a key of ``ShapeError.KINDS``) says who found it:

* ``"compile"``: the engine itself cannot read or compile the shapes graph, its rules or its setup, whenever it finds out (when a
  processor is built, or later in a run).
* ``"meta"``: the meta check (the shapes-about-shapes, ``meta_shacl=True``) found it. Carries ``problems``, ``report_text``,
  ``report_graph`` and ``scope``.

``ExecutionError``: the shapes graph is fine and running it failed. Not a ``ShapeError``, so that an ``except ShapeError`` for a wrong
shapes graph does not catch it. One class; its ``kind`` attribute says what failed:

* ``"rule"``: a rule failed while running, or the rule set failed as a whole.
* ``"expression"``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
* ``"recursion"``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
* ``"constraint-query"``: a ``sh:sparql`` constraint query reported ``?failure true``.
* ``"internal"``: the engine failed an assertion about its own result, a bug in StarLayer to be reported.  The message starts "internal error (a bug in StarLayer, please report it at ...)" and ``report_url`` is the issues URL.
* ``"limit"``: ``max_iterations`` or ``max_triples`` of the rules was exceeded (a size cap of the library, as the RDFC-1.0 cap).

The kinds ``"timeout"``, ``"inconsistent"`` and ``"inference"`` belong to OWL-DL reasoning (``starlayer-reasoning``, see
``starlayer/errors.py``). They are never raised by the engine's own rules and validation, but an entailment regime run before
validation (``inference=ENTAILMENT["OWL-Direct"]``) lets them propagate out of ``validate()``.

The class and the ``kind`` name the cause and never change with the path an error travels: an expression that cannot be evaluated is an
``ExecutionError`` of kind ``"expression"`` from ``validate()``, from a rule and from fragment extraction alike, and a malformed shape
is a ``ShapeError`` wherever it is read. Where it happened (which rule, shape, focus node or call) is ``context`` on every
``ExecutionError`` and ``ShapeError``, a short string such as ``"sh:rule ex:R1"`` (``None`` when nothing narrows it), repeated in the
message; a handler that knows the place sets it and re-raises the same class and kind.

A bad argument to a public call (a role that is not ``"editor"`` or ``"viewer"``, a shape name the shapes graph does not have) is a plain
``ValueError`` or ``TypeError``, raised before any shape is read.
"""

from __future__ import annotations

from starlayer.errors import (
    ExecutionError,
    FormatError,
    ShapeError,
)

__all__ = [
    "ExecutionError",
    "FormatError",
    "ShapeError",
]
