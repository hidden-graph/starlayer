"""``StarQuery`` - binds a SPARQL query (prepared once) plus every per-call
option ``StarLayerGraph.query()`` otherwise takes, so the same query can be
run against several different graphs without re-passing the same
``entailment=``/``initNs=``/etc. arguments every time.

Mirrors ``starlayer.shacl.StarShaclSchema``'s own "bind the thing to
interpret, plus cross-cutting config, once at construction" shape -
``StarShaclSchema`` binds a shapes graph; this binds a query instead.
Deliberately does not validate a ``CONSTRUCT`` query's own result graph
against a SHACL shape - considered and rejected as out of scope for this
class.

**A real, pre-existing ``StarLayerGraph.query()`` gap, found while building
this class, not assumed away**: ``entailment=ENTAILMENT.RDF``/``RDFS``
rewrites a query's algebra to express the entailment rule - but that
rewrite only ever runs when ``query_object`` is a plain string (inside
``query_cache.prepare_query_cached``, which ``StarLayerGraph.query()``
only calls on the ``isinstance(query_object, str)`` branch). Hand it an
*already-prepared* ``Query`` object instead (exactly what preparing once
via :func:`starlayer.sparql.parse12.prepare_query_12` and reusing it would
otherwise do) with ``entailment=ENTAILMENT.RDFS`` and the rewrite silently
never happens - confirmed live: the same query returns results against
raw text + ``entailment=ENTAILMENT.RDFS``, and an empty result against a
pre-prepared ``Query`` object + the identical ``entailment=``, no error
either way. Since this class's own purpose is exactly "prepare once, reuse
across calls with a bound entailment regime," silently shipping that bug
through it would make the entailment-binding feature actively wrong for
two of the four real regimes. Worked around here (see :meth:`run`) rather
than fixed at the ``StarLayerGraph.query()`` level - that method's own
algebra-rewrite step mutates a tree in place with no safe, cheap way to
copy an ``rdflib`` ``CompValue`` tree first (confirmed: a plain
``copy.deepcopy`` fails outright, ``CompValue.__init__()`` has no
zero-argument reconstruction path pickle/copy needs), so fixing it
properly there is a larger, riskier change to a heavily-shared method -
out of scope for building this class. Flagged in
``StarLayerGraph.query()``'s own docstring too.
"""

from __future__ import annotations

from typing import Any, Mapping

from rdflib.query import Result

from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.sparql.parse12 import prepare_query_12

# entailment=ENTAILMENT.RDF/.RDFS rewrite the query's own algebra - see this
# module's own docstring for why that rewrite is silently skipped when
# query_object isn't a plain string. run() falls back to the original text
# for exactly these two regimes so the rewrite actually happens.
_TEXT_REWRITE_ENTAILMENTS = (ENTAILMENT.RDF, ENTAILMENT.RDFS)

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
        self._prepared = prepare_query_12(text, base=base, initNs=initNs)
        self.initNs = initNs
        self.initBindings = initBindings
        self.entailment = entailment
        self.infer = infer
        self.engine = engine
        self.timeout = timeout

    def run(self, graph: Any, **overrides: Any) -> Result:
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

        if kwargs["entailment"] in _TEXT_REWRITE_ENTAILMENTS:
            # See this module's own docstring: only a plain string triggers
            # StarLayerGraph.query()'s own entailment-rewrite step for
            # these two regimes - the prepared Query object's algebra is
            # never rewritten. Falls back to the original text so the
            # rewrite actually happens; the target graph's own per-instance
            # prepared-query cache still avoids re-preparing on repeated
            # calls against the *same* graph.
            kwargs.setdefault("base", self._base)
            return graph.query(self._text, **kwargs)
        return graph.query(self._prepared, **kwargs)
