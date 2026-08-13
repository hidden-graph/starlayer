"""Per-graph/dataset SPARQL query preparation cache.

``StarLayerGraph.query()`` and ``StarLayerDataset.query()`` both parse
SPARQL 1.2 query text via ``starsparql``'s real grammar/algebra
pipeline (``prepare_query_12`` -> ``query_to_rdf11`` -> ``rdf11_to_query``)
on every call. Callers that evaluate the same query text repeatedly against
an unmutated graph with only ``initBindings`` differing - the exact shape of
pySHACL's own SHACL-AF rule/constraint evaluation, which calls ``.query()``
once per focus node per rule per iteration - redo that parse+lower work
every single time even though its result never changes between those calls.

``prepare_query_cached`` caches the parsed-and-lowered
``rdflib.plugins.sparql.sparql.Query`` object, keyed on the query text plus
the *effective* namespace mapping and base IRI - both of which are baked
into the parsed query at parse time (via ``prepare_query_12``'s own
``initNs``/``base`` passthrough to ``translateQuery``), so they're part of
what makes two calls equivalent, not just the query text. Passing an
already-prepared ``Query`` object instead of a string to ``Graph.query()``
is a first-class, documented rdflib capability (``Store.query()``'s own
type signature is ``Union[Query, str]``, and ``SPARQLProcessor.query()``
branches on exactly this) for the *default* code path - but not every
store honors that contract: confirmed via real Fuseki testing that
``rdflib.plugins.stores.sparqlstore.SPARQLStore``/``SPARQLUpdateStore``
(used for any remote HTTP SPARQL endpoint, not just Fuseki) hard-require a
plain string (``assert isinstance(query, str)`` in their own ``query()``),
raising ``AssertionError`` rather than falling back gracefully. Callers
must check ``store_accepts_prepared_query`` before deciding whether to use
the cached prepared object directly, or serialize it back to text first
(see ``StarLayerGraph.query()``'s own generalized remote-store handling).
"""

from __future__ import annotations

from typing import Any, Mapping

from rdflib.plugins.sparql.sparql import Query

from starsparql.parse12 import prepare_query_12
from starsparql.lower_rdf11 import query_to_rdf11, rdf11_to_query

# Store classes confirmed (via real Fuseki testing, not just code reading)
# to hard-require a plain query string - their own query() methods assert
# isinstance(query, str) rather than accepting a pre-parsed Query object.
# Both cover any remote HTTP SPARQL endpoint (SPARQLUpdateStore subclasses
# SPARQLStore), not just Fuseki specifically.
_STRING_ONLY_STORE_TYPES: tuple[type, ...] = ()


def _load_string_only_store_types() -> tuple[type, ...]:
    from rdflib.plugins.stores.sparqlstore import SPARQLStore, SPARQLUpdateStore

    return (SPARQLStore, SPARQLUpdateStore)


def store_accepts_prepared_query(store: Any) -> bool:
    """Whether ``store``'s own ``query()`` (if it implements one - see
    ``Graph.query()``'s ``hasattr(self.store, "query")`` dispatch) can
    safely be handed a pre-parsed ``rdflib.plugins.sparql.sparql.Query``
    object instead of a plain string. ``False`` for known string-only
    stores (confirmed via real Fuseki testing); ``True`` otherwise,
    including for the default in-memory ``Memory`` store, whose own
    ``query()`` just raises ``NotImplementedError`` and falls through to
    the generic ``SPARQLProcessor`` path, which does correctly accept a
    prepared ``Query`` object.
    """
    global _STRING_ONLY_STORE_TYPES
    if not _STRING_ONLY_STORE_TYPES:
        _STRING_ONLY_STORE_TYPES = _load_string_only_store_types()
    return not isinstance(store, _STRING_ONLY_STORE_TYPES)


def prepare_query_cached(
    cache: dict[tuple[str, tuple, str | None], Query],
    query_text: str,
    effective_ns: Mapping[str, Any] | None,
    base: str | None,
) -> Query:
    """Return a prepared SPARQL ``Query`` for ``query_text``, reusing a
    previous preparation from ``cache`` if the same
    (query text, effective namespaces, base) was seen before.

    ``effective_ns`` must already be the namespace mapping that will
    actually be used - the caller's explicit ``initNs``, or its own bound
    namespaces if none was given - not ``None`` standing in for "resolve
    it later"; a cache keyed before that resolution would miss real
    differences (or worse, reuse a stale mapping) if a graph's bound
    namespaces change between calls with the same query text.
    """
    ns_key = tuple(sorted((str(k), str(v)) for k, v in effective_ns.items())) if effective_ns else ()
    cache_key = (query_text, ns_key, base)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    from starlayergraph.query.version_directive import strip_version_directive, contains_triple_term
    stripped_text, declared_version = strip_version_directive(query_text)
    prepared_12 = prepare_query_12(
        stripped_text, base=base, initNs=dict(effective_ns) if effective_ns else None
    )
    if declared_version is not None:
        # A conformance warning fires at most once per distinct (query text,
        # namespaces, base) tuple, not on every call - a query that misses
        # the cache the first time and hits it on every repeat evaluation
        # (this cache's whole reason to exist) only needs to be flagged
        # once, not once per evaluation.
        from starlayergraph.model.conformance import check_version_conformance
        check_version_conformance(
            declared_version,
            uses_triple_term=contains_triple_term(prepared_12.algebra),
            uses_dirlangstring='--' in stripped_text,
            context='SPARQL query',
        )
    rdf_graph, root = query_to_rdf11(prepared_12)
    prepared = rdf11_to_query(rdf_graph, root)
    cache[cache_key] = prepared
    return prepared
