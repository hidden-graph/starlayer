"""A query session over a graph and the triples an OWL regime entails from it.

``query(entailment=ENTAILMENT["OWL-RDF-Based"])`` and ``["OWL-Direct"]`` copy the store and add the entailed triples to the copy
for every call. A session makes that copy once and queries it as often as asked, until it is closed: a repeated query then costs
the query only, however large the store (a million triples take about a second to copy). The copy holds the data as it was when the
session was opened or last refreshed; the session's graph is never modified.
"""

from __future__ import annotations

from typing import Any

from starlayer.graph.oxgraph import union

__all__ = ["EntailmentSession"]

_OWL_REGIMES = "ENTAILMENT['OWL-RDF-Based'] and ENTAILMENT['OWL-Direct']"


class EntailmentSession:
    """Open with ``graph.entailment_session(regime)``. Use it as a context manager, or call :meth:`close`.

    The entailed triples come from the graph's kept ones (``infer=`` as on ``query()``: ``"changed"`` computes them again only
    after a write, ``"cached"`` reuses any, ``"always"`` computes them). :meth:`query` never computes them: the session answers
    from its copy. :attr:`stale` says whether the graph was written to since the copy was made; :meth:`refresh` makes a new copy.
    """

    def __init__(self, graph: Any, regime: str, *, infer: str, engine: str, timeout: Any) -> None:
        from starlayer.graph.oxgraph.helpers import entailment as ent

        if regime not in (ent.OWL_RL_REGIME, ent.OWL_DIRECT_REGIME):
            raise ValueError(
                f"a session holds the entailed triples of {_OWL_REGIMES}, not {regime!r}: RDF and RDFS entailment rewrite "
                "the query and keep nothing, so use query(entailment=...) for them."
            )
        if infer not in ("always", "cached", "changed"):
            raise ValueError(f"infer must be one of ['always', 'cached', 'changed'], got {infer!r}")
        if regime != ent.OWL_DIRECT_REGIME and (engine != "hermit" or timeout is not None):
            raise ValueError("engine= and timeout= are only meaningful for entailment=ENTAILMENT['OWL-Direct'].")
        self._graph = graph
        self._regime = regime
        self._engine = engine
        self._timeout = ent.DEFAULT_TIMEOUT if timeout is None else timeout
        self._copy: Any = None
        self._stamp = 0
        self._build(infer)

    def _build(self, infer: str) -> None:
        stamp = union.current()  # taken first: a write that lands while the reasoner runs makes the copy stale
        copy = self._graph._entailed_copy(self._regime, infer, engine=self._engine, timeout=self._timeout)
        self._release()
        self._copy, self._stamp = copy, stamp

    def _release(self) -> None:
        if self._copy is not None:
            self._copy.store.clear()
            self._copy = None

    # ---- use ---------------------------------------------------------------------------------------------------
    def query(self, text: str, initNs: Any = None, initBindings: Any = None, base: str | None = None) -> Any:  # noqa: N803
        """Run SPARQL ``text`` on the copy (the data as of the last open or refresh, plus the entailed triples). Read the result
        before the session is closed or refreshed: closing empties the copy."""
        return self._open().query(text, initNs=initNs, initBindings=initBindings, base=base)

    @property
    def stale(self) -> bool:
        """True if a write was made through StarLayer since the copy was made (any graph counts, as for ``infer="changed"``)."""
        self._open()
        return union.current() != self._stamp

    @property
    def closed(self) -> bool:
        return self._copy is None

    def refresh(self, infer: str = "changed") -> EntailmentSession:
        """Make a new copy of the graph's current data; the entailed triples are computed again as ``infer`` says
        (``"changed"``: only if the graph was written to since they were computed)."""
        self._open()
        if infer not in ("always", "cached", "changed"):
            raise ValueError(f"infer must be one of ['always', 'cached', 'changed'], got {infer!r}")
        self._build(infer)
        return self

    def close(self) -> None:
        """End the session: empty and drop the copy. The graph and the entailed triples it keeps are not affected. Calling it
        again does nothing."""
        self._release()

    def _open(self) -> Any:
        if self._copy is None:
            raise RuntimeError("this entailment session is closed; open another with graph.entailment_session(...)")
        return self._copy

    def __enter__(self) -> EntailmentSession:
        self._open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<EntailmentSession {'closed' if self.closed else 'stale' if self.stale else 'open'}>"
