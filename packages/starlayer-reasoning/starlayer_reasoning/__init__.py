"""OWL reasoning for StarLayer.

``starlayer`` calls this package for the OWL regimes of ``infer()`` (``owl_rl_delta`` for OWL 2 RL with ``owlrl``, ``owl_direct_delta`` for OWL 2 DL with HermiT or rustdl). Each
takes and returns pyoxigraph triples.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

__all__ = ["owl_direct_delta", "owl_rl_delta"]

Triple = tuple[Any, Any, Any]


def owl_rl_delta(triples: Iterable[Triple], *, rdfs: bool, owl_rl: bool) -> set[Triple]:
    """The triples the OWL 2 RL closure adds to ``triples``; ``rdfs`` and ``owl_rl`` pick the regimes (RDFS, OWL-RL, or both)."""
    from starlayer_reasoning import owl_rl as _owl_rl

    return _owl_rl.delta(triples, rdfs=rdfs, owl_rl=owl_rl)


def owl_direct_delta(triples: Iterable[Triple], *, engine: str, timeout: Any) -> set[Triple]:
    """The triples an OWL 2 DL engine (``"hermit"`` or ``"rustdl"``) adds to ``triples``, within ``timeout`` seconds."""
    from starlayer_reasoning import owl_dl_delta

    return owl_dl_delta.delta(triples, engine=engine, timeout=timeout)
