"""The SPARQL 1.2 Query grammar as data: the spine of the production coverage matrix."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
_DOC = json.loads((HERE / "vendor" / "sparql12-query-productions.json").read_text(encoding="utf-8"))

PRODUCTIONS: dict[str, str] = {p["name"]: p["rhs"] for p in _DOC["productions"]}
NUMBER: dict[str, int] = {p["name"]: p["n"] for p in _DOC["productions"]}
ALL_ROWS: tuple[str, ...] = tuple(sorted(PRODUCTIONS, key=NUMBER.get))

# Productions [3] and [31]-[53] are the SPARQL Update rows (UpdateUnit .. QuadsNotTriples). Their cases in ``corpus.py`` are
# marked ``update=True`` and go through ``parse_sparql_update``. TriplesTemplate [54] is shared with CONSTRUCT.
UPDATE_ONLY: frozenset[str] = frozenset(name for name, n in NUMBER.items() if n == 3 or 31 <= n <= 53)
