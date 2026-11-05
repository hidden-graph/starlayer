"""Optional dependencies: rdflib is an extra (``pip install starlayer[rdflib]``), not a core dependency.

Code that needs it either imports it inside the function that uses it, or (a whole module that is rdflib-based) calls
``require_rdflib(...)`` before its own ``import rdflib``, so a user without rdflib gets one clear ``ImportError`` that
names the extra instead of a bare ``ModuleNotFoundError``.
"""

from __future__ import annotations

RDFLIB_EXTRA_HINT = "pip install starlayer[rdflib]"


def have_rdflib() -> bool:
    """True when rdflib can be imported."""
    try:
        import rdflib  # noqa: F401
    except ImportError:
        return False
    return True


def require_rdflib(feature: str) -> None:
    """Raise a clear ``ImportError`` naming the extra when rdflib is missing; ``feature`` says what needed it."""
    try:
        import rdflib  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"{feature} needs rdflib, which is an optional dependency of starlayer. Install it with `{RDFLIB_EXTRA_HINT}`."
        ) from exc
