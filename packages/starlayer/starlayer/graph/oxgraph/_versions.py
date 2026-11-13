"""The minimum pyoxigraph StarLayer supports.

Older pyoxigraph aborts the whole process on SPARQL ``=`` over an ``rdf:dirLangString``
(oxigraph/oxigraph#1982, fixed in 0.5.13), and StarLayer no longer guards against it, so
an older engine is refused at import time rather than left to crash at query time.
"""
from __future__ import annotations

import re
from functools import cache

MIN_PYOXIGRAPH = (0, 5, 13)


def _version_tuple(text) -> tuple[int, ...] | None:
    """``'0.5.13'`` or ``'0.5.13-rc1'`` as ``(0, 5, 13)``; ``None`` if unparseable."""
    m = re.match(r'\s*v?(\d+)\.(\d+)\.(\d+)', str(text))
    return tuple(int(x) for x in m.groups()) if m else None


def check_pyoxigraph_version(version_text) -> None:
    """Raise ``ImportError`` unless ``version_text`` names a version >= 0.5.13."""
    version = _version_tuple(version_text)
    if version is None or version < MIN_PYOXIGRAPH:
        raise ImportError(
            'StarLayer needs pyoxigraph >= 0.5.13: older versions abort the process on '
            f'SPARQL = over rdf:dirLangString (oxigraph#1982); found {version_text!r}'
        )


@cache
def require_supported_pyoxigraph() -> None:
    """Check the installed pyoxigraph once (cached); raise ``ImportError`` if too old or unreadable."""
    import pyoxigraph
    check_pyoxigraph_version(getattr(pyoxigraph, '__version__', None))
