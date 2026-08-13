"""StarLayer-aware wrappers for rdflib SPARQL parse/prepare functions.

These wrappers accept SPARQL 1.2 syntax and return the same rdflib types
the originals do. All four go through ``starsparql``'s real
grammar/algebra pipeline (``parse12.py``/``lower_rdf11.py``) rather than
text-level rewriting:

  - ``parseQuery``/``parseUpdate`` return a raw parse tree (same shape
    ``rdflib.plugins.sparql.parser.parseQuery``/``parseUpdate`` return),
    via ``starsparql.parse12.parse_query_12``/``parse_update_12`` -
    genuine ``TripleTermNode`` nodes appear directly in triple-pattern
    position, constructed by the grammar itself, not detected and
    reassembled after the fact from an encoding pattern. ``TripleTermNode``
    is a ``CompValue`` subclass named ``'TripleTerm'`` with
    ``subject``/``predicate``/``object`` keys - the exact shape this
    module's own callers already expect.
  - ``prepareQuery``/``prepareUpdate`` return a compiled, directly
    executable ``Query``/``Update`` object whose algebra is already
    lowered to plain SPARQL 1.1 (``starsparql.lower_rdf11``'s
    ``query_to_rdf11``/``update_to_rdf11`` + ``rdf11_to_query``/
    ``rdf11_to_update``) - same contract as before ("the compiled algebra
    is SPARQL 1.1; the rewriting is transparent at execution time"), just
    produced by parsing+lowering the real algebra tree instead of
    rewriting text.

Use these instead of the rdflib originals when working with SPARQL 1.2 queries::

    from starlayergraph.query import parseQuery, prepareQuery, parseUpdate, prepareUpdate

    # All of these now accept SPARQL 1.2 triple-term syntax
    parseQuery("SELECT ?s WHERE { <<( ?s ?p ?o )>> ex:certainty ?c }")
    prepareQuery("SELECT ?s WHERE { <<( ?s ?p ?o )>> ex:certainty ?c }")
    parseUpdate("DELETE WHERE { <<( ?s ?p ?o )>> ?pred ?val }")
    prepareUpdate("DELETE WHERE { <<( ?s ?p ?o )>> ?pred ?val }")
"""

from __future__ import annotations


def parseQuery(q):
    """Parse a SPARQL 1.2 SELECT/ASK/CONSTRUCT/DESCRIBE query string.

    Returns a pyparsing ``ParseResults`` tree — same type as
    ``rdflib.plugins.sparql.parser.parseQuery`` — with genuine
    ``TripleTermNode`` nodes wherever ``<<( s p o )>>``/``TRIPLE(s, p, o)``
    appears, constructed directly by the grammar (see module docstring),
    not reassembled from a text-level encoding.
    """
    from starsparql.parse12 import parse_query_12
    return parse_query_12(q)


def prepareQuery(queryString: str, initNs=None, base=None):
    """Parse and translate a SPARQL 1.2 query string to an rdflib ``Query`` object.

    The compiled algebra is plain SPARQL 1.1 (triple terms lowered to
    starlayergraph's own ``tt:`` content-addressed encoding); the lowering is
    transparent at execution time.

    The returned ``Query`` object can be passed directly to
    ``StarLayerGraph.query()`` or ``rdflib.Graph.query()``.
    """
    from starsparql.parse12 import prepare_query_12
    from starsparql.lower_rdf11 import query_to_rdf11, rdf11_to_query
    prepared_12 = prepare_query_12(queryString, base=base, initNs=initNs)
    rdf_graph, root = query_to_rdf11(prepared_12)
    return rdf11_to_query(rdf_graph, root)


def parseUpdate(q):
    """Parse a SPARQL 1.2 Update request string.

    Returns an rdflib ``CompValue`` — same type as
    ``rdflib.plugins.sparql.parser.parseUpdate`` — with genuine
    ``TripleTermNode`` nodes preserved (same strategy as ``parseQuery``).
    """
    from starsparql.parse12 import parse_update_12
    return parse_update_12(q)


def prepareUpdate(updateString: str, initNs=None, base=None):
    """Parse and translate a SPARQL 1.2 Update request string to an rdflib ``Update`` object.

    The compiled form is plain SPARQL 1.1, same lowering as ``prepareQuery``.

    The returned ``Update`` object can be passed directly to
    ``StarLayerGraph.update()`` or ``rdflib.Graph.update()``.
    """
    from starsparql.parse12 import prepare_update_12
    from starsparql.lower_rdf11 import update_to_rdf11, rdf11_to_update
    prepared_12 = prepare_update_12(updateString, base=base, initNs=initNs)
    rdf_graph, root = update_to_rdf11(prepared_12)
    return rdf11_to_update(rdf_graph, root)


def processUpdate(graph, updateString: str, initBindings=None, initNs=None, base=None):
    """Execute a SPARQL 1.2 Update against a graph.

    This is the SPARQL 1.2-aware replacement for
    ``rdflib.plugins.sparql.processUpdate``. The rdflib original calls
    ``parseUpdate()`` directly, bypassing any ``graph.update()`` override.

    For ``StarLayerGraph``/``StarLayerDataset`` instances, this delegates
    the *original* SPARQL 1.2 text straight to ``graph.update()`` so that
    graph's own full update pipeline runs unmodified (registry rebuild,
    ``_invalidate_callback``, native-backend routing, INSERT/DELETE
    template-position triple-term handling — all of which is specific to
    those classes' own ``.update()``, not something to reimplement or
    bypass here). For a plain ``rdflib.Graph`` (which has no notion of
    SPARQL 1.2 syntax at all), ``updateString`` is first compiled via this
    module's own ``prepareUpdate`` into a directly executable, already-
    SPARQL-1.1 ``Update`` object, then handed to ``graph.update()`` — the
    same general entry point, not the more narrowly-typed
    ``rdflib.plugins.sparql.processUpdate`` function, since ``Graph.update()``
    already accepts a prepared object or text uniformly.

    Checks via attribute (``_tt_registry``/``_sg_cache``) rather than
    ``isinstance`` to avoid a circular import.
    """
    if hasattr(graph, '_tt_registry') or hasattr(graph, '_sg_cache'):
        # No base= here (matches this branch's pre-existing behavior): it
        # would flow through StarLayerGraph.update()'s own **kwargs all the
        # way to SPARQLUpdateProcessor.update(), which doesn't accept it -
        # confirmed via a real TypeError. StarLayerGraph.update() only
        # reads kwargs.get('base') for its own internal parsing when
        # updateString is a str; a caller needing base-relative IRI
        # resolution here should call graph.update(...) directly instead.
        graph.update(updateString, initBindings=initBindings, initNs=initNs)
        return
    update_object = (
        prepareUpdate(updateString, initNs=initNs, base=base)
        if isinstance(updateString, str) else updateString
    )
    graph.update(update_object, initBindings=initBindings)
