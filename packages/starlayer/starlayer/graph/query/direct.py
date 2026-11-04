"""Direct execution of SPARQL 1.2 text on an in-process Oxigraph (spike, opt-in).

No rdflib parse, no algebra-to-RDF encoding, no 1.2-to-1.1 lowering and no rdflib evaluator: the text goes to
``pyoxigraph.Store.query`` / ``.update`` as it is. See ``docs/working/sparql-direct-execution-spike.md``.

What this module does around the engine call:

- ``init_ns`` -> the engine's ``prefixes=`` argument (Oxigraph resolves the prefixes while parsing; a ``PREFIX`` in the
  text wins over it), ``base`` -> ``base_iri=``.
- ``init_bindings`` -> the engine's ``substitutions=`` (SEP-0007). The engine raises ``RuntimeError`` when the variable
  is not in the SELECT projection (or for an aggregate-only projection); then the documented fallback applies: the
  same ``VALUES`` injection the existing native path uses (``native.inject_init_bindings``).
- results -> ``rdflib.query.Result`` with the same term conversion as ``native_oxigraph`` (TripleTerm, DirLangString,
  whole-number decimal canonicalization, skolem-IRI blank nodes back to ``BNode``).

Not here, because they need a parsed tree: ``entailment=`` rewriting, the prepared-query cache, ``Query.algebra``.
"""
from __future__ import annotations

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.query import Result

from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm


def direct_enabled(explicit: bool | None = None) -> bool:
    """The opt-in switch: an explicit constructor argument wins, else ``STARLAYER_QUERY_DIRECT=1``."""
    if explicit is not None:
        return explicit
    import os
    return os.environ.get('STARLAYER_QUERY_DIRECT', '') not in ('', '0', 'false', 'False')


def _engine(store):
    """The ``pyoxigraph.Store`` behind an ``oxrdflib.OxigraphStore`` (or the store itself)."""
    from starlayer.graph.backends._versions import require_supported_pyoxigraph
    require_supported_pyoxigraph()
    return getattr(store, '_inner', store)


def _to_ox(term):
    """An rdflib/StarLayer term as a pyoxigraph term (for ``substitutions``)."""
    import pyoxigraph as ox

    from starlayer.graph.backends.native import skolemize_bnode

    if isinstance(term, TripleTerm):
        return ox.Triple(_to_ox(term.subject), _to_ox(term.predicate), _to_ox(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return ox.Triple(*(_to_ox(t) for t in term))
    if isinstance(term, BNode):
        # an in-process store holds blank nodes written one at a time as skolem IRIs (GitHub issue #98)
        return ox.NamedNode(str(skolemize_bnode(term)))
    if isinstance(term, URIRef):
        return ox.NamedNode(str(term))
    if isinstance(term, DirLangString):
        return ox.Literal(str(term), language=term.language, direction=ox.BaseDirection(term.direction.upper()))
    if isinstance(term, Literal):
        if term.language:
            return ox.Literal(str(term), language=term.language)
        if term.datatype:
            return ox.Literal(str(term), datatype=ox.NamedNode(str(term.datatype)))
        return ox.Literal(str(term))
    raise TypeError(f'cannot bind {term!r} (type {type(term).__name__}) as an initial binding')


def _prefix_dict(init_ns) -> dict[str, str] | None:
    if not init_ns:
        return None
    items = init_ns.items() if hasattr(init_ns, 'items') else init_ns
    return {str(k): str(v) for k, v in items}


def _call_query(engine, text, *, prefixes, base, default_union, substitutions):
    kwargs: dict = {}
    if prefixes:
        kwargs['prefixes'] = prefixes
    if base:
        kwargs['base_iri'] = base
    if default_union:
        kwargs['use_default_graph_as_union'] = True
    if substitutions:
        kwargs['substitutions'] = substitutions
    return engine.query(text, **kwargs)


def run_direct(store, text: str, *, init_ns=None, init_bindings=None, base=None, default_union=True) -> Result:
    """Run SPARQL query ``text`` on ``store`` (``pyoxigraph.Store`` or ``OxigraphStore``) and return a ``Result``.

    ``default_union=True`` makes the default graph the union of all graphs (what ``StarLayerGraph.query`` on the
    existing native path does NOT do - it passes False; pass ``default_union=False`` for parity with that path).
    """
    import pyoxigraph as ox

    from starlayer.graph.backends.native import check_native_version_conformance
    from starlayer.graph.backends.native_oxigraph import _parse_ox_term

    if not isinstance(text, str):
        raise NotImplementedError('direct execution needs the query as text, not a prepared Query object')
    check_native_version_conformance(text)
    engine = _engine(store)
    prefixes = _prefix_dict(init_ns)

    substitutions = None
    if init_bindings:
        substitutions = {
            ox.Variable(str(k).lstrip('?$')): _to_ox(v) for k, v in init_bindings.items()
        }
    if not substitutions:  # a correlated FILTER [NOT] EXISTS is much faster as a join (sparql/sqe/rewrite.py); same rows
        from starlayer.sparql.sqe.rewrite import rewrite_exists_text

        text = rewrite_exists_text(text, prefixes=prefixes, base=base)
    try:
        res = _call_query(engine, text, prefixes=prefixes, base=base, default_union=default_union,
                          substitutions=substitutions)
    except RuntimeError as e:
        if not substitutions or 'projection' not in str(e):
            raise
        # documented fallback: the variable is not projected -> VALUES injection (needs the prefixes in the text)
        from starlayer.graph.backends.native import inject_init_bindings
        res = _call_query(engine, inject_init_bindings(text, dict(init_bindings)), prefixes=prefixes, base=base,
                          default_union=default_union, substitutions=None)

    if isinstance(res, ox.QueryBoolean):
        r = Result('ASK')
        r.askAnswer = bool(res)
        return r
    if isinstance(res, ox.QueryTriples):
        from starlayer.graph.backends.native import deskolemize_bnode, new_graph_like
        g = new_graph_like(store if hasattr(store, '_inner') else _wrap(store), 'rdf-1.2')
        triples = [
            (deskolemize_bnode(_parse_ox_term(t.subject)), _parse_ox_term(t.predicate),
             deskolemize_bnode(_parse_ox_term(t.object)))
            for t in res
        ]
        g._native_add_many(triples)
        r = Result('CONSTRUCT')
        r.graph = g
        return r
    vars_ = [Variable(v.value) for v in res.variables]
    bindings = []
    for sol in res:
        row = {}
        for rv, nv in zip(vars_, res.variables, strict=True):
            raw = sol[nv]
            if raw is not None:
                row[rv] = _parse_ox_term(raw)
        bindings.append(row)
    r = Result('SELECT')
    r.vars = vars_
    r.bindings = bindings
    return r


def _wrap(raw_store):
    from oxrdflib import OxigraphStore
    return OxigraphStore(store=raw_store)


def run_direct_update(store, text: str, *, init_ns=None, base=None) -> None:
    """Run SPARQL Update ``text`` on ``store`` as it is. ``init_bindings`` has no meaning for an update (rdflib's
    own ``update`` takes it, but the engine has no pre-binding for updates), so it is not accepted here."""
    from starlayer.graph.backends.native import check_native_version_conformance

    if not isinstance(text, str):
        raise NotImplementedError('direct execution needs the update as text, not a prepared Update object')
    check_native_version_conformance(text)
    kwargs: dict = {}
    prefixes = _prefix_dict(init_ns)
    if prefixes:
        kwargs['prefixes'] = prefixes
    if base:
        kwargs['base_iri'] = base
    _engine(store).update(text, **kwargs)

