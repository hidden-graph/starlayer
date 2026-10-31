"""Lexical-form-faithful parsing helpers shared by the StarLayer parse paths.

rdflib normalises a datatyped literal's lexical form on construction (``"04"^^xsd:integer``
becomes ``"4"``, ``"1"^^xsd:boolean`` becomes ``"true"``) unless ``normalize=False`` is given. StarLayer's
own parsers (Turtle/TriG/N-Triples/N-Quads 1.2) pass ``normalize=False``. rdflib's RDF/XML parser has
no such option, so :func:`faithful_rdfxml_literals` gives it one for the duration of a
``with`` block, on the current thread only. rdflib's global ``NORMALIZE_LITERALS`` is never changed, so
plain rdflib use in the same process is unaffected.
"""

from __future__ import annotations

import contextlib
import threading

from rdflib import Literal

_state = threading.local()
_installed = False
_install_lock = threading.Lock()


def _faithful_literal(*args, **kwargs):
    if getattr(_state, 'depth', 0) > 0 and 'normalize' not in kwargs:
        kwargs['normalize'] = False
    return Literal(*args, **kwargs)


def _install() -> None:
    global _installed
    with _install_lock:
        if not _installed:
            from rdflib.plugins.parsers import rdfxml
            rdfxml.Literal = _faithful_literal  # behaves exactly like Literal unless a faithful block is active on this thread
            _installed = True


@contextlib.contextmanager
def faithful_rdfxml_literals():
    """While active (on this thread), rdflib's RDF/XML parser keeps each datatyped literal's lexical form as written."""
    _install()
    _state.depth = getattr(_state, 'depth', 0) + 1
    try:
        yield
    finally:
        _state.depth -= 1
