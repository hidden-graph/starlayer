"""In-process transport for the native (``backend='rdf-1.2'``) backend, using
``oxrdflib``'s ordinary ``OxigraphStore`` as the store.

The native backend normally talks SPARQL text to a remote endpoint over HTTP
(``native.py``'s ``http_*`` functions). ``oxrdflib.OxigraphStore`` wraps a
``pyoxigraph.Store`` - the same Rust engine, run in-process - so the same
SPARQL text can be handed to it directly, with real RDF 1.2 triple terms and
SPARQL 1.2 evaluation, and no HTTP at all.

Opt-in and explicit: only a graph constructed with
``StarLayerGraph(store=<OxigraphStore>, backend='rdf-1.2')`` uses this path.
Every other graph is unaffected. ``oxrdflib`` and ``pyoxigraph`` are optional
dependencies, never imported at module level elsewhere.
"""
from __future__ import annotations

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.term import Variable

from starlayer.graph.backends.native import deskolemize_bnode
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.encoding import BN_NS
from starlayer.graph.model.triple import TripleTerm


def is_oxigraph_store(store) -> bool:
    """True for ``oxrdflib``'s ``OxigraphStore``. Duck-typed on class name and
    its lazily-created engine property, so no ``oxrdflib`` import is needed just to
    ask."""
    return type(store).__name__ == 'OxigraphStore' and hasattr(type(store), '_inner')


def _engine(store):
    """The wrapped ``pyoxigraph.Store`` of an ``OxigraphStore``."""
    return store._inner


def _parse_ox_term(term):
    """Convert a native pyoxigraph term to an rdflib node, DirLangString, or
    TripleTerm. Mirrors native.py's ``_parse_json_term()`` for the HTTP
    transport, minus the JSON dispatch - pyoxigraph hands back typed objects.
    """
    import pyoxigraph as ox

    if term is None:
        return None
    if isinstance(term, ox.NamedNode):
        value = term.value
        # Reverse skolemize_bnode() - see that function's docstring.
        if value.startswith(BN_NS):
            return BNode(value[len(BN_NS):])
        return URIRef(value)
    if isinstance(term, ox.BlankNode):
        return BNode(term.value)
    if isinstance(term, ox.Literal):
        if term.language and term.direction is not None:
            return DirLangString(term.value, term.language, str(term.direction))
        if term.language:
            return Literal(term.value, lang=term.language)
        dtype_iri = term.datatype.value
        # pyoxigraph always reports an explicit xsd:string datatype for a
        # plain literal; rdflib treats a simple literal and its
        # ^^xsd:string form as different terms, so collapse it back to a
        # plain Literal to match _parse_json_term()'s behavior.
        if dtype_iri == str(XSD.string):
            return Literal(term.value)
        literal = Literal(term.value, datatype=URIRef(dtype_iri))
        if dtype_iri == str(XSD.decimal):
            # Same engine-side whole-number xsd:decimal canonicalization
            # defect _parse_json_term() already works around for HTTP.
            from starlayer.graph.query.operator_patches import (
                _canonicalize_decimal_lexical_form,
            )

            literal = _canonicalize_decimal_lexical_form(literal)
        return literal
    if isinstance(term, ox.Triple):
        s = _parse_ox_term(term.subject)
        p = _parse_ox_term(term.predicate)
        o = _parse_ox_term(term.object)
        try:
            return TripleTerm(s, p, o)
        except ValueError as e:
            raise ValueError(
                f'oxigraph returned a triple term with an invalid RDF 1.2 subject or '
                f'predicate (subject={s!r}, predicate={p!r}, object={o!r}) - {e}. '
                f'This indicates a spec-conformance bug in the engine, not in this library.'
            ) from e
    raise ValueError(f'Unknown pyoxigraph term type: {type(term).__name__!r}')


def _query(store, sparql: str, default_union: bool):
    """Run a query; with ``default_union`` the default graph is the union of all graphs (pyoxigraph's flag), which is what
    ``StarLayerDataset(default_union=True)`` promises and a native query ignored (GitHub issue #98)."""
    if default_union:
        return _engine(store).query(sparql, use_default_graph_as_union=True)
    return _engine(store).query(sparql)


def ox_select(store, sparql: str, default_union: bool = False) -> tuple[list, list]:
    """SELECT -> (vars, bindings), the same shape ``http_select()`` returns."""
    solutions = _query(store, sparql, default_union)
    native_vars = solutions.variables
    vars_ = [Variable(v.value) for v in native_vars]
    bindings = []
    for sol in solutions:
        binding = {}
        for rdf_var, native_var in zip(vars_, native_vars, strict=True):
            raw = sol[native_var]
            if raw is not None:
                binding[rdf_var] = _parse_ox_term(raw)
        bindings.append(binding)
    return vars_, bindings


def ox_ask(store, sparql: str, default_union: bool = False) -> bool:
    return bool(_query(store, sparql, default_union))


def ox_update(store, sparql: str) -> None:
    _engine(store).update(sparql)


def ox_construct(store, sparql: str, default_union: bool = False):
    """CONSTRUCT/DESCRIBE -> already-deskolemized (s, p, o) triples, with no
    serialize/re-parse round trip."""
    for t in _query(store, sparql, default_union):
        yield (
            deskolemize_bnode(_parse_ox_term(t.subject)),
            _parse_ox_term(t.predicate),
            deskolemize_bnode(_parse_ox_term(t.object)),
        )
