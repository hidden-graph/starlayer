"""The W3C Manchester Syntax grammar as data: the spine of the coverage matrix.

``PRODUCTIONS`` is loaded from ``vendor/owl2-manchester-productions.json`` (see
``vendor/VENDORED_FROM.md`` for provenance). ``LABELLED_ALTERNATIVES`` are the note's named
alternatives inside ``restriction``, which the note marks up as anchors but not as productions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent

PRODUCTIONS: dict[str, str] = json.loads(
    (HERE / "vendor" / "owl2-manchester-productions.json").read_text(encoding="utf-8")
)

LABELLED_ALTERNATIVES: tuple[str, ...] = (
    "objectsome", "objectonly", "objectvalue", "objectSelf",
    "objectmin", "objectmax", "objectexactly",
    "datasome", "dataonly", "datavalue",
    "datamin", "datamax", "dataexactly",
)

# Generic list templates (``<NT>List`` etc.) are patterns instantiated by many productions, not
# productions of their own; they are covered implicitly wherever an instantiation is.
TEMPLATE_PRODUCTIONS = frozenset({"<NT>List", "<NT>2List", "<NT>AnnotatedList"})


def _list_instantiations() -> frozenset[str]:
    """Names like ``descriptionAnnotatedList`` / ``individual2List`` / ``literalList``: the note defines
    three list templates once (``<NT>List``, ``<NT>2List``, ``<NT>AnnotatedList``) and the other
    productions use their instantiations without defining them. Each instantiation is its own row, so a
    list form that no case exercises is visible rather than waved through."""
    pattern = re.compile(r"\b([A-Za-z]+(?:2List|AnnotatedList|List))\b")
    found: set[str] = set()
    for rhs in PRODUCTIONS.values():
        found.update(pattern.findall(rhs))
    return frozenset(found)


LIST_INSTANTIATIONS: frozenset[str] = _list_instantiations()

# Lexical productions are covered by the literal/IRI cases, tracked individually so a lexical gap (say,
# no exponent form) still shows up as an uncovered row rather than being waved through.
ALL_ROWS: tuple[str, ...] = tuple(
    sorted(
        (set(PRODUCTIONS) - TEMPLATE_PRODUCTIONS)
        | set(LABELLED_ALTERNATIVES)
        | set(LIST_INSTANTIATIONS)
    )
)
