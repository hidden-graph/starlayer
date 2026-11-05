"""``StarQuery`` - binds a SPARQL query (syntax-checked once) plus every per-call
option ``StarLayerGraph.query()`` otherwise takes, so the same query can be
run against several different graphs without re-passing the same
``entailment=``/``initNs=``/etc. arguments every time.

Mirrors ``starlayer.shacl.StarShaclSchema``'s own "bind the thing to
interpret, plus cross-cutting config, once at construction" shape -
``StarShaclSchema`` binds a shapes graph; this binds a query instead.
Deliberately does not validate a ``CONSTRUCT`` query's own result graph
against a SHACL shape - considered and rejected as out of scope for this
class.

Oxigraph runs the query text, so construction only checks the syntax (with StarLayer's own parser); the RDF / RDFS
entailment regimes rewrite the text on each run, inside ``StarLayerGraph.query()``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Sentinel for "no timeout= override bound" - lets run() omit the kwarg
# entirely and fall through to StarLayerGraph.query()'s own real default,
# rather than this module hardcoding (and risking drifting out of sync
# with) that default's actual numeric value.
_TIMEOUT_NOT_BOUND = object()


class StarQuery:
    """A SPARQL query, prepared once, bound with the options
    ``StarLayerGraph.query()`` otherwise takes per call - run it against as
    many graphs as you like via :meth:`run`.
    """

    def __init__(
        self,
        text: str,
        *,
        base: str | None = None,
        initNs: Mapping[str, Any] | None = None,
        initBindings: Mapping[str, Any] | None = None,
        entailment: Any | None = None,
        infer: str = "changed",
        engine: str = "hermit",
        timeout: Any = _TIMEOUT_NOT_BOUND,
    ) -> None:
        """Parse and prepare ``text`` once; bind every other
        ``StarLayerGraph.query()`` option alongside it.

        Args:
            text: The SPARQL query text (SPARQL 1.2, including RDF 1.2
                triple-term/annotation syntax).
            base: Optional base IRI, passed through to query preparation.
            initNs: Namespace bindings for the query - bound once here
                rather than repeated on every :meth:`run` call.
            initBindings: Initial variable bindings, bound once.
            entailment: The entailment regime to use on every :meth:`run`
                call, unless overridden per call - see
                ``StarLayerGraph.query()``'s own ``entailment=`` for the
                full set of accepted values.
            infer: Passed through to ``StarLayerGraph.query()`` - only
                consulted for the two entailment regimes that cache a
                delta (``OWL-RDF-Based``/``OWL-Direct``).
            engine: Passed through to ``StarLayerGraph.query()`` - only
                consulted for ``entailment=ENTAILMENT["OWL-Direct"]``.
            timeout: Passed through to ``StarLayerGraph.query()``. Left
                unset by default (the sentinel below), in which case
                ``StarLayerGraph.query()``'s own default is used instead of
                this module duplicating that default's actual value.
        """
        self._text = text
        self._base = base
        from .parse_sparql import parse_sparql

        # StarLayer's own parser checks the syntax, so a bad query raises here
        parse_sparql(text, base, {k: str(getattr(v, "value", v)) for k, v in (initNs or {}).items()})
        self.initNs = initNs
        self.initBindings = initBindings
        self.entailment = entailment
        self.infer = infer
        self.engine = engine
        self.timeout = timeout

    def run(self, graph: Any, **overrides: Any) -> Any:
        """Run the bound query against ``graph``.

        Any option bound at construction can be overridden for just this
        one call via ``**overrides`` - the bound value itself is never
        changed.

        Args:
            graph: The graph to query (a ``StarLayerGraph``, or anything
                else ``StarLayerGraph.query()``'s own ``query_object``
                parameter already accepts a prepared ``Query`` against).
            **overrides: Any of ``initNs``/``initBindings``/``entailment``/
                ``infer``/``engine``/``timeout``/``processor``/``result``/
                ``use_store_provided``, overriding the bound value (or
                ``StarLayerGraph.query()``'s own default) for this call
                only.

        Returns:
            Whatever ``graph.query()`` itself returns for this query.
        """
        kwargs: dict[str, Any] = dict(
            initNs=self.initNs,
            initBindings=self.initBindings,
            entailment=self.entailment,
            infer=self.infer,
            engine=self.engine,
        )
        if self.timeout is not _TIMEOUT_NOT_BOUND:
            kwargs["timeout"] = self.timeout
        kwargs.update(overrides)

        from starlayer.graph.oxgraph import _rdflib_bridge as _ox

        if not _ox.is_oxigraph_input(graph):
            graph = _ox.to_oxgraph(graph)  # an rdflib graph is copied in by the rdflib bridge (rdflib is then needed)
        # The wrapper runs the query text on Oxigraph. RDF / RDFS entailment rewrites the text; the OWL regimes run on a temporary
        # closure copy (see StarLayerGraph.query). timeout is only meaningful for OWL-Direct, as on StarLayerGraph.query(), which is
        # where a misuse raises.
        return graph.query(
            self._text,
            initNs=kwargs["initNs"],
            initBindings=kwargs["initBindings"],
            base=kwargs.get("base", self._base),
            entailment=kwargs["entailment"],
            infer=kwargs["infer"],
            engine=kwargs["engine"],
            timeout=kwargs.get("timeout"),
        )
