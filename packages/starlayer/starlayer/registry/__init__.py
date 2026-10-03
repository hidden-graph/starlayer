"""starlayer.registry - the cross-vocabulary ontology/SHACL-shapes registry.

Renamed from ``starlayer.ontology`` (2026-10-03) - the module is purely a
registry, nothing else, and contains no ontology content of its own
(``starontology`` already owns that); every vocabulary-specific loader
that used to live here moved out to wherever that vocabulary's own real
logic lives:

- ``manch:`` (parse/serialize/validate) -> ``starontology.manchester``
- ``skos:`` (validate) -> ``starontology.skos``
- ``salg:``/``srl:`` -> ``starlayer.sparql`` (``srl:`` eventually also
  moving to ``starontology.srl``, once it's separable from the sibling
  ``starlayer.sparql`` package's shared internals it currently depends on)

Each moved because validating (or, for ``manch:``, editing) a vocabulary
against/as its own structure is an ontology-management concern in its own
right, not something that belongs bundled into a generic cross-vocabulary
catalog. What's left here is exactly the one thing that has to sit *above*
all of them: ``list_ontologies()``/``get_ontology(name)``/``Ontology`` -
one name-based lookup so a caller doesn't need to know which of those
places actually implements a given vocabulary's ``.graph()``/``.validate()``.
"""

from __future__ import annotations

# Re-exported so `starlayer.registry.list_ontologies()`/
# `get_ontology()` work without a caller needing to know the registry
# lives in its own submodule - see registry.py's own docstring for the full
# design (why this lives here rather than in starlayer.shacl/starlayer.sparql, why
# every loader is lazy, and what's deliberately not yet registered).
from starlayer.registry.registry import (  # noqa: E402
    Ontology,
    get_ontology,
    list_ontologies,
)
