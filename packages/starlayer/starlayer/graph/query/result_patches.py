"""Targeted compatibility shim for a confirmed bug in plain rdflib's own
``rdflib.query.Result`` - result *materialization*, a different module and
phase from every other patch in this package (parsing/algebra translation:
``algebra_translator_patches.py``; SPARQL arithmetic: ``operator_patches.py``;
evaluation: ``evaluate_patches.py``). See ``docs/rdflib-upstream-issues.md``
issue 6 for the full write-up.

Same idempotent apply-once pattern as the other ``*_patches.py`` modules in
this package.
"""

from __future__ import annotations

from rdflib.query import Result, ResultRow

_result_patch_status: bool | None = None


def patch_result_iter_empty_binding_row() -> bool:
    """Fix a confirmed rdflib bug: ``Result.__iter__``'s ``SELECT`` handling
    guards on ``if b:`` before yielding each row's binding dict - meant to
    mean "skip past the end," but an empty dict (``{}``) is also falsy in
    Python, so a *real* solution row that happens to have zero variable
    bindings is silently dropped too, indistinguishable at this check from
    "no more rows."

    A zero-variable binding is a real, correct SPARQL solution - it's what
    ``SELECT *`` over a WHERE pattern with no variables anywhere produces
    when it matches (e.g. ``SELECT * WHERE { <a> <b> <c> . }`` - a "does
    this exact fact exist?" query). Confirmed via a plain, unmodified
    rdflib reproduction: ``Result.bindings`` (the property) and
    ``len(result)`` both correctly report one row for such a query, and
    ``ASK`` on the identical pattern correctly returns ``True`` - only
    iterating the ``Result`` object (``list(result)``, ``for row in
    result``) silently returns nothing. Confirmed to affect a genuinely
    remote SPARQLStore-backed result too (tested against a live Oxigraph
    instance, which itself sends the correct ``{"bindings": [{}]}`` over
    the wire) - this is purely rdflib's own client-side bug, unrelated to
    which backend produced the data.

    Fix: yield every row in ``self._bindings``/``self._genbindings``
    unconditionally - there is no sentinel value ever placed in either
    list to mean "not a real row," so the truthiness check was never
    actually distinguishing anything real to begin with.
    """
    global _result_patch_status
    if _result_patch_status is not None:
        return _result_patch_status

    try:
        original_iter = Result.__iter__
        if getattr(original_iter, "_starlayergraph_result_iter_patch", False):
            _result_patch_status = True
            return True

        def _patched_iter(self):
            if self.type in ("CONSTRUCT", "DESCRIBE"):
                yield from self.graph
            elif self.type == "ASK":
                yield self.askAnswer
            elif self.type == "SELECT":
                # this iterates over ResultRows of variable bindings
                if self._genbindings:
                    for b in self._genbindings:
                        self._bindings.append(b)
                        yield ResultRow(b, self.vars)
                    self._genbindings = None
                else:
                    for b in self._bindings:
                        yield ResultRow(b, self.vars)

        _patched_iter._starlayergraph_result_iter_patch = True  # type: ignore[attr-defined]
        Result.__iter__ = _patched_iter
        _result_patch_status = True
    except Exception:
        _result_patch_status = False

    return _result_patch_status
