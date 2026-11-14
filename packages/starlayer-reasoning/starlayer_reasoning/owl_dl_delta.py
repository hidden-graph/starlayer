"""The triples an OWL 2 DL engine (HermiT through owlready2, or rustdl) adds to a graph, as pyoxigraph triples."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox
from starlayer.graph import interop


def delta(triples: Iterable[tuple[Any, Any, Any]], *, engine: str, timeout: Any) -> set[tuple[Any, Any, Any]]:
    """What ``engine`` adds to ``triples`` that they did not already hold."""
    triples = list(triples)
    if engine == "hermit":
        from starlayer_reasoning import owl_dl

        classify = owl_dl.classify_owl_dl
    elif engine == "rustdl":
        from starlayer_reasoning import owl_dl_rustdl

        classify = owl_dl_rustdl.classify_owl_dl_rustdl
    else:
        raise ValueError(f"Unsupported engine {engine!r}; expected one of ['hermit', 'rustdl']")
    _before, added = classify(triples, timeout=timeout)
    restored = interop.decode_directions(ox.Triple(s, p, o) for s, p, o in added)
    return {(q.subject, q.predicate, q.object) for q in restored} - set(triples)
