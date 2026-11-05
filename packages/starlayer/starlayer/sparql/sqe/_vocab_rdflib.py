"""``sqe/vocab.py`` as rdflib terms, for the code that still builds or reads ``sqe:`` trees with rdflib (``from_rdf.py``,
which decodes a tree to an rdflib ``Query``, and the SRL encoder in ``..srl``). Every name of ``sqe/vocab.py`` is available here
with the same IRI as an rdflib ``URIRef``; ``SQE`` is an rdflib ``Namespace``. Delete with the rdflib users."""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
from typing import Any

import pyoxigraph as ox
from rdflib import Namespace, URIRef

from . import vocab as _native

SQE = Namespace(_native.SQE["x"].value[:-1])
_cache: dict[str, Any] = {"SQE": SQE}


def __getattr__(name: str) -> Any:
    if name.startswith("__"):
        raise AttributeError(name)
    if name not in _cache:
        value = getattr(_native, name)
        if not isinstance(value, ox.NamedNode):
            raise AttributeError(name)
        _cache[name] = URIRef(value.value)
    return _cache[name]
