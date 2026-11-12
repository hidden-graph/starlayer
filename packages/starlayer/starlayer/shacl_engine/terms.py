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
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, unquote

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
        """Create a namespace rooted at the IRI prefix ``base``."""
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_cache", {})

    def __getitem__(self, name: str) -> ox.NamedNode:
        """The term for ``name`` in this namespace, built on first use and then reused; use it for names that are not identifiers."""
        node = self._cache.get(name)
        if node is None:
            node = self._cache[name] = ox.NamedNode(self._base + name)
        return node

    def __getattr__(self, name: str) -> ox.NamedNode:
        """Attribute access as ``__getitem__``; dunder names raise ``AttributeError`` so copy and pickle probes do not mint terms."""
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def __str__(self) -> str:
        """The base IRI text, so a namespace can be concatenated into IRI strings."""
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


_STAND_IN_IRI = re.compile(r"urn:starlayer:invalid-iri:((?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})*)")  # see ``_INVALID_IRI_PREFIX``


_STAND_IN_LANG = re.compile(r", datatype=<urn:starlayer:invalid-lang:((?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})*)>")  # see ``_INVALID_LANG_PREFIX``


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

# ---- foreign terms <-> engine (the rdflib code lives in graph/oxgraph/_rdflib_bridge.py) -------------------------------------------------------------------------------------

_VARIABLE_PREFIX = "urn:starlayer:variable:"  # an rdflib ``Variable`` crosses the boundary as this IRI

# Lenient mode: terms pyoxigraph rejects cross the boundary as opaque, reversible stand-ins (see ``TermError``).
_INVALID_IRI_PREFIX = "urn:starlayer:invalid-iri:"  # + percent-encoded text: an IRI term (also as a literal datatype)
_INVALID_LANG_PREFIX = "urn:starlayer:invalid-lang:"  # + percent-encoded tag: the datatype of a literal with a bad tag
_INVALID_BNODE_PREFIX = "starlayer-invalid-bnode-"  # + hex of the UTF-8 id
# + hex of the lexical form (UTF-8, surrogates kept), "-", then "d" + the percent-encoded datatype IRI, "l" + the language tag or
# nothing (a plain string): the datatype of a literal whose lexical form holds a lone surrogate (the direction of a tag is not kept)
_INVALID_LITERAL_PREFIX = "urn:starlayer:invalid-literal:"
_SURROGATE = re.compile("[\ud800-\udfff]")

TERM_POLICIES = ("error", "lenient")
_POLICY: contextvars.ContextVar[str] = contextvars.ContextVar("starlayer_shacl_term_policy", default="error")


class StarLayerFidelityWarning(UserWarning):
    """The data graph does not preserve literal lexical forms and the shapes use constraints that depend on them (see
    ``fidelity.py``). Filter it with ``warnings.simplefilter("ignore", StarLayerFidelityWarning)``. StarLayer issue #190."""


class TermError(ValueError):
    """A term that is not an RDF 1.2 term (and so cannot be an engine term): a relative or invalid IRI, a blank node id
    Oxigraph rejects, a malformed language tag, a literal subject or a predicate that is not an IRI.

    Policy (one, for the whole engine): the engine validates RDF graphs, and SHACL 1.2 is defined over RDF graphs, in which an
    IRI is an absolute IRI. A graph holding such a term has no defined validation report (not a ``sh:nodeKind`` question,
    not a validation result: the input is outside the specification's domain). So the default is to fail, early and
    once: every entry point scans its data and shapes graphs before validating and raises ``TermError`` naming the
    offending terms and where they are. ``term_policy("lenient")`` (or ``invalid_terms="lenient"`` on an entry point) opts
    in to processing anyway: each such term becomes an opaque stand-in that is mapped back to the original rdflib term in
    every result and report (the report graph and ``Result`` terms hold the stand-in IRIs; ``Outcome.report_text`` and the result
    messages show the original text, see ``unmask``), and the list of them is on ``Outcome.invalid_terms``. In lenient mode an ill-formed IRI is
    still an IRI (``sh:nodeKind sh:IRI`` holds, ``sh:IRI`` is what rdflib says too) but its text is the stand-in
    ``urn:starlayer:invalid-iri:<percent-encoded original>``, so text-based constraints (``sh:pattern``, ``sh:minLength``,
    ``sh:uniqueLang`` ...) see that text; a literal with a malformed language tag is a literal whose datatype is
    ``urn:starlayer:invalid-lang:<tag>`` (it is not ``rdf:langString``); a bad blank node id is a blank node; a literal whose
    lexical form holds a lone UTF-16 surrogate (not a Unicode scalar value) is a literal of datatype
    ``urn:starlayer:invalid-literal:...`` whose lexical form shows U+FFFD in place of the surrogate.

    Attributes: ``term`` (the offending rdflib term), ``kind`` (``"iri"`` / ``"bnode"`` / ``"language"`` / ``"literal"`` / ``"term"``: a literal subject or a predicate that is not an IRI, which under the lenient policy is left out of the copy), ``reason``,
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
        """Build the error; when ``errors`` is given the message summarises those offenders instead of describing this one.

        Args:
            errors: every offender found in one scan, for the aggregate error raised by the up-front check.
        """
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
        """One-line text naming the term, where it was found and why it is ill-formed, with no aggregate summary."""
        where = ""
        if self.where:
            where = f" in the {self.where}"
        if self.position:
            where += f" as the {self.position}"
        if self.triple is not None:
            where += f" of the triple {_bridge().show(tuple(self.triple))}"  # str-ok: show() returns text
        return f"ill-formed {self.kind} {_bridge().show(self.term)}{where}: {self.reason}"  # str-ok: show() returns text

    def located(self, where: str | None, position: str | None, triple: Any) -> TermError:
        """A copy of this error with the graph label, position and triple filled in by the scan that found it."""
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
        return ox.NamedNode(_INVALID_IRI_PREFIX + quote(text_, safe="", errors="surrogatepass"))


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
        return ox.Literal(lexical_, datatype=ox.NamedNode(_INVALID_LANG_PREFIX + quote(lang, safe="", errors="surrogatepass")))


def has_lone_surrogate(text_: str) -> bool:
    """Whether ``text_`` holds a lone UTF-16 surrogate, which is not a Unicode scalar value and so cannot be an Oxigraph literal."""
    return _SURROGATE.search(text_) is not None


def _surrogate_literal_stand_in(lexical_: str, original: Any, datatype: Any = None, lang: str | None = None) -> ox.Literal:
    """A literal whose lexical form holds a lone surrogate: ``TermError``, or under the lenient policy an opaque stand-in."""
    err = TermError(original, "literal", "the lexical form holds a lone surrogate, which is not a Unicode scalar value")
    if _POLICY.get() != "lenient":
        raise err from None
    spec = "l" + quote(lang, safe="", errors="surrogatepass") if lang else "d" + quote(datatype.value, safe="") if datatype is not None else ""
    payload = lexical_.encode("utf-8", "surrogatepass").hex()
    shown = _SURROGATE.sub("\ufffd", lexical_)
    return ox.Literal(shown, datatype=ox.NamedNode(_INVALID_LITERAL_PREFIX + payload + "-" + spec))


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
    """``from_engine`` applied to each position of a triple."""
    return from_engine(t[0]), from_engine(t[1]), from_engine(t[2])


def to_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    """``to_engine`` applied to each position of a triple."""
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
    """The engine's term view of ``graph``: an Oxigraph-backed graph (``StarLayerGraph``, ``StarLayerDataset``, ``OxigraphGraph``) as it
    is; a bare ``pyoxigraph.Store`` as an ``StarLayerDataset``; an rdflib / StarLayer graph as an ``StarLayerGraph`` copy made by the rdflib
    bridge, which raises ``TermError`` for a term that is not an RDF term (see there). A dataset is its union (``_union_view``)."""
    if graph is None:
        return graph
    if getattr(graph, "engine_terms", False):
        return _union_view(graph)
    return _bridge().to_oxgraph(graph, where)


def _union_view(graph: Any) -> Any:
    """SHACL validates one data graph, and a dataset is that graph's union of all its graphs (as pySHACL does, which sets
    ``default_union`` on a multi-graph data graph). A dataset whose own ``default_union`` is off is seen through a view of the same
    store with it on; every other graph is returned as it is."""
    from starlayer.graph.oxgraph import StarLayerDataset

    if isinstance(graph, StarLayerDataset) and not graph.default_union:
        return StarLayerDataset(store=graph.store, default_union=True, prefixes=dict(graph.prefixes))
    return graph


def __getattr__(name: str) -> Any:
    """Module-level lazy lookup of ``LegacyTermView``, which lives in the bridge and is imported only on first use."""
    # ``LegacyTermView`` (an rdflib-term view of an engine graph) lives in the bridge
    if name == "LegacyTermView":
        return _bridge().LegacyTermView
    raise AttributeError(name)
