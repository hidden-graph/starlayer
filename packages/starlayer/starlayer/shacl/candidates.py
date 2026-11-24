"""``Candidates``: the answer of ``candidate_values()``, what an editor can offer for one field of a property shape.

How the shape's constraints give the values (``sh:in``, ``sh:hasValue``, ``sh:class``, ``sh:rootClass``, ``sh:or``, ``sh:and``) and
which ones only filter is explained in ``starlayer.shacl.engine.candidates``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candidates:
    """What a field can be offered.

    ``kind`` is ``"list"`` (a closed list: ``sh:in`` or ``sh:hasValue``), ``"instances"`` (the nodes of ``sh:class`` or ``sh:rootClass``)
    or ``"open"`` (nothing to list: a datatype or node kind only). ``values`` are the terms in a stable order (IRIs by text, then
    blank nodes, then literals by lexical form and datatype), empty for ``"open"``. ``closed`` is True when only a member of ``values``
    is allowed. ``entry`` is what can be typed when it is not closed: the ``sh:datatype`` IRIs, else the ``sh:nodeKind`` IRIs."""

    kind: str
    values: tuple[Any, ...]
    closed: bool
    entry: tuple[Any, ...]
