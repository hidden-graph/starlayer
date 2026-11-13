"""The engine's term model: pyoxigraph ``NamedNode`` / ``BlankNode`` / ``Literal`` / ``Triple`` (one-to-one with Rust
``oxrdf``), the same terms the callers' graphs and the report graph hold.

Literals keep exactly the lexical form and datatype they were built with; value-space logic lives in ``xsd_values``. A
language-tagged literal with a base direction is an ``ox.Literal`` with ``direction`` set; a triple term is an ``ox.Triple``.
``to_engine`` checks a caller's term (and says how to convert an rdflib one), ``engine_view`` a caller's graph."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

import pyoxigraph as ox

from starlayer.graph._versions import require_supported_pyoxigraph

require_supported_pyoxigraph()

NamedNode, BlankNode, Literal, Triple = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple

_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}
_XSD = "http://www.w3.org/2001/XMLSchema#"


from starlayer.graph.namespaces import DCTERMS, OWL, RDF, RDFS, SH, XSD  # noqa: E402,F401  (shared vocabularies)
from starlayer.graph.namespaces import Namespace as NS  # noqa: E402,F401  (the public namespace class)

# ---- kind tests and text ----------------------------------------------------------------------------------------------

is_iri = lambda t: isinstance(t, ox.NamedNode)  # noqa: E731
is_bnode = lambda t: isinstance(t, ox.BlankNode)  # noqa: E731
is_literal = lambda t: isinstance(t, ox.Literal)  # noqa: E731
is_triple = lambda t: isinstance(t, ox.Triple)  # noqa: E731


def lexical(term: Any) -> str:
    """The lexical value of a term: a literal's lexical form, an IRI's text, a blank node's id. This is what ``str(term)``
    gave on an rdflib term; on a pyoxigraph term ``str()`` yields ``<iri>`` / the N-Triples form, so engine code never
    calls ``str()`` on a term (``tests/shacl/engine/test_no_str_of_terms.py``). A triple term has no lexical value: use
    ``text`` or ``n3``."""
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal)):
        return term.value
    raise TypeError(f"a {type(term).__name__} has no lexical value")


def iri_text(term: ox.NamedNode) -> str:
    """The text of an IRI term (no angle brackets)."""
    if not isinstance(term, ox.NamedNode):
        raise TypeError(f"not an IRI: {type(term).__name__}")
    return term.value


def n3(term: Any) -> str:
    """The N-Triples / N3 form of a term (``<iri>``, ``_:b``, ``"lex"^^<dt>``): what ``str()`` of a pyoxigraph term gives,
    named so that using it is a decision. Used by sort keys and diagnostics that want an unambiguous rendering."""
    return str(term)  # str-ok: this helper is the one sanctioned place; the N-Triples form is wanted here


def text(term: Any) -> str:
    """Human text of a term, as ``str(rdflib term)`` gave it: IRI text, literal lexical form, blank node id."""
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal)):
        return term.value
    if isinstance(term, ox.Triple):
        return f"<<( {text(term.subject)} {text(term.predicate)} {text(term.object)} )>>"
    return str(term)  # str-ok: a plain value (str, int) that is not a term


_STAND_IN_IRI = re.compile(r"urn:starlayer:invalid-iri:((?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})*)")  # see ``INVALID_IRI_PREFIX``


_STAND_IN_LANG = re.compile(r", datatype=<urn:starlayer:invalid-lang:((?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})*)>")  # see ``INVALID_LANG_PREFIX``


def unmask(message: str) -> str:
    """``message`` with every lenient-mode stand-in replaced by the original term text, so a message or a report text shows the
    term the user wrote: an IRI stand-in (``urn:starlayer:invalid-iri:...``) by the IRI text, a rendered literal whose datatype is
    an invalid-lang stand-in by its language tag (``Literal("v", lang=e)``). Text, not terms: the report graph keeps the stand-ins."""
    if "urn:starlayer:invalid-" not in message:
        return message
    message = _STAND_IN_LANG.sub(lambda m: ", lang=" + unquote(m.group(1), errors="surrogatepass"), message)
    return _STAND_IN_IRI.sub(lambda m: unquote(m.group(1), errors="surrogatepass"), message)


def local_name(iri: ox.NamedNode) -> str:
    """The part of an IRI after the last ``#``, or after the last ``/`` when there is no ``#``."""
    v = iri.value
    return v.rsplit("#", 1)[-1] if "#" in v else v.rsplit("/", 1)[-1]


def datatype_iri(lit: ox.Literal) -> ox.NamedNode:
    """The RDF datatype of a literal (``rdf:langString`` / ``rdf:dirLangString`` for tagged strings): ``Literal.datatype``."""
    return lit.datatype


# ---- constructors -----------------------------------------------------------------------------------------------------


def literal(lexical: str, datatype: ox.NamedNode | None = None, lang: str | None = None) -> ox.Literal:
    """A literal from a lexical form; ``lang`` takes precedence over ``datatype`` when both are given."""
    if lang:
        return ox.Literal(lexical, language=lang)
    return ox.Literal(lexical, datatype=datatype) if datatype is not None else ox.Literal(lexical)


def boolean(value: bool) -> ox.Literal:
    """An ``xsd:boolean`` literal in its canonical form (``true`` / ``false``)."""
    return ox.Literal("true" if value else "false", datatype=XSD.boolean)


def integer(value: int) -> ox.Literal:
    """An ``xsd:integer`` literal in the decimal form of ``value``."""
    return ox.Literal(str(value), datatype=XSD.integer)  # str-ok: value is a python int


TRUE = boolean(True)
FALSE = boolean(False)

# ---- stand-ins -----------------------------------------------------------------------------------------------------------------

# The stand-ins ``sparql/_oxterms.py`` makes for query text pyoxigraph terms cannot hold (a relative IRI, a bad blank node label or language tag)
INVALID_IRI_PREFIX = "urn:starlayer:invalid-iri:"  # + percent-encoded text: an IRI term (also as a literal datatype)
INVALID_LANG_PREFIX = "urn:starlayer:invalid-lang:"  # + percent-encoded tag: the datatype of a literal with a bad tag
INVALID_BNODE_PREFIX = "starlayer-invalid-bnode-"  # + hex of the UTF-8 id


class StarLayerFidelityWarning(UserWarning):
    """The data graph does not preserve literal lexical forms and the shapes use constraints that depend on them (see
    ``fidelity.py``). Filter it with ``warnings.simplefilter("ignore", StarLayerFidelityWarning)``. StarLayer issue #190."""


def to_engine(term: Any) -> Any:
    """A term as a pyoxigraph term. ``None`` stays ``None``; a pyoxigraph term is returned as it is; a 3-tuple is a triple term.
    Anything else, an rdflib term above all, is a ``TypeError``: StarLayer takes pyoxigraph terms (``pyoxigraph.NamedNode``,
    ``Namespace`` from ``starlayer.graph``); a whole rdflib graph is converted explicitly with ``StarLayerGraph.from_rdflib()``."""
    if term is None or isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    if type(term) is tuple and len(term) == 3:
        return ox.Triple(*(to_engine(t) for t in term))
    module = type(term).__module__.split(".")[0]
    hint = (
        f"an rdflib term ({type(term).__name__}) is not accepted: use a pyoxigraph term (pyoxigraph.NamedNode(...), "
        "pyoxigraph.Literal(...)) or starlayer.graph.Namespace; convert a whole rdflib graph with StarLayerGraph.from_rdflib(graph)"
        if module == "rdflib"
        else f"expected a pyoxigraph term (NamedNode, BlankNode, Literal or Triple), not {type(term).__name__}: {term!r}"
    )
    raise TypeError(hint)


def to_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    """``to_engine`` applied to each position of a triple."""
    return to_engine(t[0]), to_engine(t[1]), to_engine(t[2])


def engine_view(graph: Any, where: str = "graph") -> Any:
    """The engine's term view of ``graph``: an Oxigraph-backed graph (``StarLayerGraph``, ``StarLayerDataset``, ``OxigraphGraph``) as it
    is; a bare ``pyoxigraph.Store`` as an ``StarLayerDataset``. An rdflib graph is a ``TypeError``: convert it first with
    ``StarLayerGraph.from_rdflib``. A dataset is its union (``_union_view``)."""
    if graph is None:
        return graph
    if getattr(graph, "engine_terms", False):
        return _union_view(graph)
    from starlayer.graph.inputs import as_oxigraph

    return as_oxigraph(graph, where)


def _union_view(graph: Any) -> Any:
    """SHACL validates one data graph, and a dataset is that graph's union of all its graphs (as pySHACL does, which sets
    ``default_union`` on a multi-graph data graph). A dataset whose own ``default_union`` is off is seen through a view of the same
    store with it on; every other graph is returned as it is."""
    from starlayer.graph import StarLayerDataset

    if isinstance(graph, StarLayerDataset) and not graph.default_union:
        return StarLayerDataset(store=graph.store, default_union=True, prefixes=dict(graph.prefixes))
    return graph
