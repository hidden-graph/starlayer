"""Importing this module raises the clear ``ImportError`` when rdflib is not installed.

A module that is rdflib-based throughout (the Manchester syntax, the SRL and salg machinery, the ``sqe:`` trees, ...) starts with
``import starlayer._needs_rdflib`` before its own ``import rdflib``. Without rdflib the user then reads "starlayer.sparql.srl needs
rdflib ... pip install starlayer[rdflib]" instead of a bare ``ModuleNotFoundError``. With rdflib it costs one cached import.
"""

import sys

from starlayer._optional import require_rdflib


def _importer() -> str:
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name.startswith("starlayer.") and name not in (__name__, "starlayer._optional"):
            return name
        frame = frame.f_back
    return "this part of starlayer"


require_rdflib(_importer())
