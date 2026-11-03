"""The engine's term model: pyoxigraph ``NamedNode`` / ``BlankNode`` / ``Literal`` / ``Triple`` (one-to-one with Rust
``oxrdf``), plus the adapters at the boundary with rdflib / StarLayer terms.

Inside the engine every term is a pyoxigraph term. Literals keep exactly the lexical form and datatype they were built
with; value-space logic lives in ``xsd_values``. A language-tagged literal with a base direction is an ``ox.Literal`` with
``direction`` set; a triple term is an ``ox.Triple``. Outside the engine (callers' graphs, the report graph, query-layer
results) terms are rdflib ``URIRef`` / ``BNode`` / ``Literal`` and ``starlayer.graph.model`` ``TripleTerm`` /
``DirLangString``; ``to_engine`` / ``from_engine`` convert, preserving lexical forms (``str(literal)`` as the parser
stored it on the way in, ``Literal(..., normalize=False)`` on the way out).

Ill-formed terms. pyoxigraph validates on construction; rdflib does not. An rdflib ``URIRef`` that is not an absolute IRI
(``URIRef("a")``, ``URIRef("")``, an IRI with a space), a blank node id Oxigraph rejects, or a language tag that is not BCP47
is not an RDF 1.2 term, so a graph holding one is not an RDF graph and SHACL 1.2 (which defines validation over RDF graphs)
says nothing about it. The policy (``TermError``, ``term_policy``) is documented in
docs/working/shacl-engine-term-model-spike.md and in ``to_engine``.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pyoxigraph as ox

from starlayer.graph.backends._versions import require_supported_pyoxigraph

require_supported_pyoxigraph()

NamedNode, BlankNode, Literal, Triple = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple

_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}
_XSD = "http://www.w3.org/2001/XMLSchema#"


class NS:
    """A namespace of pyoxigraph ``NamedNode`` constants: ``SH.minCount``, ``SH["class"]``. Terms are created once."""

    __slots__ = ("_base", "_cache")

    def __init__(self, base: str) -> None:
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_cache", {})

    def __getitem__(self, name: str) -> ox.NamedNode:
        node = self._cache.get(name)
        if node is None:
            node = self._cache[name] = ox.NamedNode(self._base + name)
        return node

    def __getattr__(self, name: str) -> ox.NamedNode:
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def __str__(self) -> str:
        return self._base


RDF = NS("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = NS("http://www.w3.org/2000/01/rdf-schema#")
XSD = NS(_XSD)
OWL = NS("http://www.w3.org/2002/07/owl#")
SH = NS("http://www.w3.org/ns/shacl#")
DCTERMS = NS("http://purl.org/dc/terms/")

# ---- kind tests and text ----------------------------------------------------------------------------------------------

is_iri = lambda t: isinstance(t, ox.NamedNode)  # noqa: E731
is_bnode = lambda t: isinstance(t, ox.BlankNode)  # noqa: E731
is_literal = lambda t: isinstance(t, ox.Literal)  # noqa: E731
is_triple = lambda t: isinstance(t, ox.Triple)  # noqa: E731


def lexical(term: Any) -> str:
    """The lexical value of a term: a literal's lexical form, an IRI's text, a blank node's id. This is what ``str(term)``
    gave on an rdflib term; on a pyoxigraph term ``str()`` yields ``<iri>`` / the N-Triples form, so engine code never
    calls ``str()`` on a term (``tests/shacl_engine/test_no_str_of_terms.py``). A triple term has no lexical value: use
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


def local_name(iri: ox.NamedNode) -> str:
    v = iri.value
    return v.rsplit("#", 1)[-1] if "#" in v else v.rsplit("/", 1)[-1]


def datatype_iri(lit: ox.Literal) -> ox.NamedNode:
    """The RDF datatype of a literal (``rdf:langString`` / ``rdf:dirLangString`` for tagged strings): ``Literal.datatype``."""
    return lit.datatype


# ---- constructors -----------------------------------------------------------------------------------------------------


def literal(lexical: str, datatype: ox.NamedNode | None = None, lang: str | None = None) -> ox.Literal:
    if lang:
        return ox.Literal(lexical, language=lang)
    return ox.Literal(lexical, datatype=datatype) if datatype is not None else ox.Literal(lexical)


def boolean(value: bool) -> ox.Literal:
    return ox.Literal("true" if value else "false", datatype=XSD.boolean)


def integer(value: int) -> ox.Literal:
    return ox.Literal(str(value), datatype=XSD.integer)  # str-ok: value is a python int


TRUE = boolean(True)
FALSE = boolean(False)

# ---- foreign terms <-> engine (the rdflib code lives in graph/oxgraph/_rdflib_bridge.py) -------------------------------------------------------------------------------------

_VARIABLE_PREFIX = "urn:starlayer:variable:"  # an rdflib ``Variable`` crosses the boundary as this IRI

# Lenient mode: terms pyoxigraph rejects cross the boundary as opaque, reversible stand-ins (see ``TermError``).
_INVALID_IRI_PREFIX = "urn:starlayer:invalid-iri:"  # + percent-encoded text: an IRI term (also as a literal datatype)
_INVALID_LANG_PREFIX = "urn:starlayer:invalid-lang:"  # + percent-encoded tag: the datatype of a literal with a bad tag
_INVALID_BNODE_PREFIX = "starlayer-invalid-bnode-"  # + hex of the UTF-8 id

TERM_POLICIES = ("error", "lenient")
_POLICY: contextvars.ContextVar[str] = contextvars.ContextVar("starlayer_shacl_term_policy", default="error")


class StarLayerFidelityWarning(UserWarning):
    """The data graph does not preserve literal lexical forms and the shapes use constraints that depend on them (see
    ``fidelity.py``). Filter it with ``warnings.simplefilter("ignore", StarLayerFidelityWarning)``. StarLayer issue #190."""


class TermError(ValueError):
    """A term that is not an RDF 1.2 term (and so cannot be an engine term): a relative or invalid IRI, a blank node id
    Oxigraph rejects, a malformed language tag.

    Policy (one, for the whole engine): the engine validates RDF graphs, and SHACL 1.2 is defined over RDF graphs, in which an
    IRI is an absolute IRI. A graph holding such a term has no defined validation report (not a ``sh:nodeKind`` question,
    not a validation result: the input is outside the specification's domain). So the default is to fail, early and
    once: every entry point scans its data and shapes graphs before validating and raises ``TermError`` naming the
    offending terms and where they are. ``term_policy("lenient")`` (or ``invalid_terms="lenient"`` on an entry point) opts
    in to processing anyway: each such term becomes an opaque stand-in that is mapped back to the original rdflib term in
    every result and report, and the list of them is on ``Outcome.invalid_terms``. In lenient mode an ill-formed IRI is
    still an IRI (``sh:nodeKind sh:IRI`` holds, ``sh:IRI`` is what rdflib says too) but its text is the stand-in
    ``urn:starlayer:invalid-iri:<percent-encoded original>``, so text-based constraints (``sh:pattern``, ``sh:minLength``,
    ``sh:uniqueLang`` ...) see that text; a literal with a malformed language tag is a literal whose datatype is
    ``urn:starlayer:invalid-lang:<tag>`` (it is not ``rdf:langString``); a bad blank node id is a blank node.

    Attributes: ``term`` (the offending rdflib term), ``kind`` (``"iri"`` / ``"bnode"`` / ``"language"``), ``reason``,
    ``where`` (graph label such as ``"data graph"``), ``position`` (``"subject"`` / ``"predicate"`` / ``"object"`` /
    ``"datatype"``), ``triple`` (the first triple it was found in), ``errors`` (all offenders found, for an aggregate)."""

    def __init__(
        self,
        term: Any,
        kind: str,
        reason: str,
        *,
        where: str | None = None,
        position: str | None = None,
        triple: Any = None,
        errors: tuple[TermError, ...] = (),
    ) -> None:
        self.term, self.kind, self.reason = term, kind, reason
        self.where, self.position, self.triple, self.errors = where, position, triple, errors
        super().__init__(self._message())

    def _message(self) -> str:
        if self.errors:
            shown = "; ".join(e.describe() for e in self.errors[:5])
            more = f" (and {len(self.errors) - 5} more)" if len(self.errors) > 5 else ""
            return (
                f"{len(self.errors)} ill-formed RDF term(s): {shown}{more}. SHACL 1.2 validates RDF graphs, whose IRIs are "
                "absolute; fix the graph or pass invalid_terms='lenient' to process them as opaque terms"
            )
        return self.describe()

    def describe(self) -> str:
        where = ""
        if self.where:
            where = f" in the {self.where}"
        if self.position:
            where += f" as the {self.position}"
        if self.triple is not None:
            where += f" of the triple {_bridge().show(tuple(self.triple))}"  # str-ok: show() returns text
        return f"ill-formed {self.kind} {_bridge().show(self.term)}{where}: {self.reason}"  # str-ok: show() returns text

    def located(self, where: str | None, position: str | None, triple: Any) -> TermError:
        return TermError(self.term, self.kind, self.reason, where=where, position=position, triple=triple)


@contextlib.contextmanager
def term_policy(mode: str) -> Iterator[None]:
    """Set the ill-formed-term policy (``"error"`` the default, or ``"lenient"``) for the enclosed block (a context
    variable, so thread and task local)."""
    if mode not in TERM_POLICIES:
        raise ValueError(f"invalid_terms must be one of {TERM_POLICIES}, not {mode!r}")
    token = _POLICY.set(mode)
    try:
        yield
    finally:
        _POLICY.reset(token)


def _iri_or_stand_in(text_: str, original: Any) -> ox.NamedNode:
    try:
        return ox.NamedNode(text_)
    except ValueError as exc:
        err = TermError(original, "iri", str(exc))
        if _POLICY.get() != "lenient":
            raise err from None
        return ox.NamedNode(_INVALID_IRI_PREFIX + quote(text_, safe=""))


def _bnode_or_stand_in(text_: str, original: Any) -> ox.BlankNode:
    try:
        return ox.BlankNode(text_)
    except ValueError as exc:
        err = TermError(original, "bnode", str(exc))
        if _POLICY.get() != "lenient":
            raise err from None
        return ox.BlankNode(_INVALID_BNODE_PREFIX + text_.encode("utf-8", "surrogatepass").hex())


def _lang_literal_or_stand_in(lexical_: str, lang: str, original: Any, direction: Any = None) -> ox.Literal:
    try:
        return ox.Literal(lexical_, language=lang, direction=direction)
    except ValueError as exc:
        err = TermError(original, "language", str(exc))
        if _POLICY.get() != "lenient":
            raise err from None
        return ox.Literal(lexical_, datatype=ox.NamedNode(_INVALID_LANG_PREFIX + quote(lang, safe="")))


def _bridge() -> Any:
    from starlayer.graph.oxgraph import _rdflib_bridge

    return _rdflib_bridge


def to_engine(term: Any) -> Any:
    """A term as a pyoxigraph term. ``None`` stays ``None``; a pyoxigraph term is returned as it is. An rdflib / StarLayer term
    (or a 3-tuple, a triple term) is converted by the rdflib bridge (``graph/oxgraph/_rdflib_bridge.py``): a term pyoxigraph rejects
    raises ``TermError`` (a ``ValueError``), or under ``term_policy("lenient")`` becomes an opaque stand-in (see ``TermError``)."""
    if term is None or isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    return _bridge().foreign_to_engine(term)


def from_engine(term: Any) -> Any:
    """A pyoxigraph term as an rdflib / StarLayer term (the rdflib bridge); anything that is not a pyoxigraph term is returned
    unchanged. Only for callers outside the engine that still speak rdflib terms."""
    if not isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    return _bridge().engine_to_foreign(term)


def from_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return from_engine(t[0]), from_engine(t[1]), from_engine(t[2])


def to_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return to_engine(t[0]), to_engine(t[1]), to_engine(t[2])


def with_term_policy(fn: Any) -> Any:
    """Decorator for engine entry points: adds the keyword ``invalid_terms`` (``"error"`` / ``"lenient"``; omitted keeps the
    ambient policy) which sets ``term_policy`` for the call. See ``TermError``."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, invalid_terms: str | None = None, **kwargs: Any) -> Any:
        if invalid_terms is None:
            return fn(*args, **kwargs)
        with term_policy(invalid_terms):
            return fn(*args, **kwargs)

    return wrapper


def check_graphs(*labelled: tuple[Any, str]) -> tuple[TermError, ...]:
    """The up-front check of a run: every ``(graph, label)`` that is not an Oxigraph-backed graph (an rdflib / StarLayer graph)
    is scanned for terms that are not RDF terms, and, under the strict policy, one aggregate ``TermError`` names every offender.
    Under ``term_policy("lenient")`` the offenders are returned instead. Engine-term graphs and ``None`` hold only
    well-formed terms."""
    return _bridge().check_graphs(*labelled)


def engine_view(graph: Any, where: str = "graph") -> Any:
    """The engine's term view of ``graph``: an Oxigraph-backed graph (``OxGraph``, ``OxDataset``, ``OxigraphGraph``) as it
    is; a bare ``pyoxigraph.Store`` as an ``OxDataset``; an rdflib / StarLayer graph as an ``OxGraph`` copy made by the rdflib
    bridge, which raises ``TermError`` for a term that is not an RDF term (see there)."""
    if graph is None or getattr(graph, "engine_terms", False):
        return graph
    return _bridge().to_oxgraph(graph, where)


def __getattr__(name: str) -> Any:
    # ``LegacyTermView`` (an rdflib-term view of an engine graph, for the salg component owners) lives in the bridge
    if name == "LegacyTermView":
        return _bridge().LegacyTermView
    raise AttributeError(name)
