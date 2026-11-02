"""The SPARQL 1.2 RL grammar as data: the spine of the coverage matrix."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
_DOC = json.loads((HERE / "vendor" / "sparql12-rl-productions.json").read_text(encoding="utf-8"))

PRODUCTIONS: dict[str, str] = {p["name"]: p["rhs"] for p in _DOC["productions"]}
ALL_ROWS: tuple[str, ...] = tuple(sorted(PRODUCTIONS))
SPEC_EXAMPLES: list[dict] = json.loads((HERE / "vendor" / "spec-examples.json").read_text(encoding="utf-8"))
