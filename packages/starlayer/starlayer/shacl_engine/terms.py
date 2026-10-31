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
import weakref
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, unquote

import pyoxigraph as ox

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
    return ox.Literal(str(value), datatype=XSD.integer)


TRUE = boolean(True)
FALSE = boolean(False)

# ---- rdflib / StarLayer <-> engine -------------------------------------------------------------------------------------

_CACHE_MAX = 200_000
_TO_ENGINE: dict = {}
_FROM_ENGINE: dict = {}
_VARIABLE_PREFIX = "urn:starlayer:variable:"  # an rdflib ``Variable`` crosses the boundary as this IRI

# Lenient mode: terms pyoxigraph rejects cross the boundary as opaque, reversible stand-ins (see ``TermError``).
_INVALID_IRI_PREFIX = "urn:starlayer:invalid-iri:"  # + percent-encoded text: an IRI term (also as a literal datatype)
_INVALID_LANG_PREFIX = "urn:starlayer:invalid-lang:"  # + percent-encoded tag: the datatype of a literal with a bad tag
_INVALID_BNODE_PREFIX = "starlayer-invalid-bnode-"  # + hex of the UTF-8 id

TERM_POLICIES = ("error", "lenient")
_POLICY: contextvars.ContextVar[str] = contextvars.ContextVar("starlayer_shacl_term_policy", default="error")


def _show(term: Any) -> str:
    """A short, never-raising rendering of an rdflib term for messages (``URIRef.n3()`` refuses an invalid IRI)."""
    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    if isinstance(term, URIRef):
        return f"<{term}>"
    if isinstance(term, BNode):
        return f"_:{term}"
    if isinstance(term, RLiteral):
        suffix = f"@{term.language}" if term.language else (f"^^<{term.datatype}>" if term.datatype else "")
        return f"{str(term)!r}{suffix}"  # str-ok: rdflib literal, its lexical form
    if isinstance(term, tuple):
        return "(" + " ".join(_show(t) for t in term) + ")"
    return repr(term)


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
            where += f" of the triple {_show(tuple(self.triple))}"
        return f"ill-formed {self.kind} {_show(self.term)}{where}: {self.reason}"

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


def to_engine(term: Any) -> Any:
    """rdflib / StarLayer term -> pyoxigraph term. ``None`` stays ``None``; a 3-tuple becomes a triple term; a term that
    already is a pyoxigraph term is returned as it is. A term pyoxigraph rejects raises ``TermError`` (a ``ValueError``),
    or under ``term_policy("lenient")`` becomes an opaque stand-in that ``from_engine`` maps back (see ``TermError``)."""
    if term is None:
        return None
    from rdflib import BNode, URIRef, Variable
    from rdflib import Literal as RLiteral

    from starlayer.graph.model.dirlangstring import DirLangString
    from starlayer.graph.model.triple import TripleTerm

    cls = type(term)
    if cls is URIRef or cls is BNode:
        out = _TO_ENGINE.get(term)
        if out is None:
            out = _iri_or_stand_in(str(term), term) if cls is URIRef else _bnode_or_stand_in(str(term), term)
            if out.value.startswith((_INVALID_IRI_PREFIX, _INVALID_BNODE_PREFIX)) and _POLICY.get() == "lenient":
                return out  # a stand-in is not cached: the strict policy must still reject the original
            if len(_TO_ENGINE) >= _CACHE_MAX:
                _TO_ENGINE.clear()
            _TO_ENGINE[term] = out
        return out
    if isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)):
        return term
    if isinstance(term, URIRef):
        return _iri_or_stand_in(str(term), term)
    if isinstance(term, BNode):
        return _bnode_or_stand_in(str(term), term)
    if isinstance(term, DirLangString):
        return _lang_literal_or_stand_in(term.value, term.language, term, _DIRECTIONS[term.direction])
    if isinstance(term, RLiteral):
        if term.language:
            return _lang_literal_or_stand_in(str(term), term.language, term)
        if term.datatype is not None:
            return ox.Literal(str(term), datatype=_iri_or_stand_in(str(term.datatype), term.datatype))
        return ox.Literal(str(term))
    if isinstance(term, Variable):  # SPARQL-algebra graphs (salg) store query variables as terms: no oxrdf equivalent
        return ox.NamedNode(_VARIABLE_PREFIX + str(term))
    if isinstance(term, TripleTerm):
        return ox.Triple(to_engine(term.subject), to_engine(term.predicate), to_engine(term.object))
    if isinstance(term, tuple) and len(term) == 3:
        return ox.Triple(*(to_engine(t) for t in term))
    raise TypeError(f"cannot convert {term!r} ({type(term).__name__}) to an engine term")


def from_engine(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (``URIRef``, ``BNode``, ``Literal(..., normalize=False)``,
    ``DirLangString``, ``TripleTerm``). Anything that is not a pyoxigraph term is returned unchanged."""
    if isinstance(term, ox.Triple):
        from starlayer.graph.model.triple import TripleTerm

        return TripleTerm(from_engine(term.subject), from_engine(term.predicate), from_engine(term.object))
    if not isinstance(term, (ox.NamedNode, ox.BlankNode, ox.Literal)):
        return term
    out = _FROM_ENGINE.get(term)
    if out is None:
        out = _from_engine(term)
        if len(_FROM_ENGINE) >= _CACHE_MAX:
            _FROM_ENGINE.clear()
        _FROM_ENGINE[term] = out
    return out


def _from_engine(term: Any) -> Any:
    from rdflib import BNode, URIRef
    from rdflib import Literal as RLiteral

    if isinstance(term, ox.NamedNode):
        if term.value.startswith(_VARIABLE_PREFIX):
            from rdflib import Variable

            return Variable(term.value[len(_VARIABLE_PREFIX) :])
        if term.value.startswith(_INVALID_IRI_PREFIX):
            return URIRef(unquote(term.value[len(_INVALID_IRI_PREFIX) :]))
        return URIRef(term.value)
    if isinstance(term, ox.BlankNode):
        if term.value.startswith(_INVALID_BNODE_PREFIX):
            return BNode(bytes.fromhex(term.value[len(_INVALID_BNODE_PREFIX) :]).decode("utf-8", "surrogatepass"))
        return BNode(term.value)
    if term.language:
        if term.direction is not None:
            from starlayer.graph.model.dirlangstring import DirLangString

            return DirLangString(term.value, term.language, str(term.direction))
        return RLiteral(term.value, lang=term.language)
    dt = term.datatype.value
    if dt.startswith(_INVALID_LANG_PREFIX):
        return RLiteral(term.value, lang=unquote(dt[len(_INVALID_LANG_PREFIX) :]))
    if dt.startswith(_INVALID_IRI_PREFIX):
        return RLiteral(term.value, datatype=URIRef(unquote(dt[len(_INVALID_IRI_PREFIX) :])), normalize=False)
    return RLiteral(term.value) if dt == _XSD + "string" else RLiteral(term.value, datatype=URIRef(dt), normalize=False)


def from_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return from_engine(t[0]), from_engine(t[1]), from_engine(t[2])


def to_engine_triple(t: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
    return to_engine(t[0]), to_engine(t[1]), to_engine(t[2])


# ---- graph views -------------------------------------------------------------------------------------------------------


def _ill_formed(term: Any) -> TermError | None:
    """The ``TermError`` ``to_engine`` raises for ``term`` under the strict policy, or None if it converts."""
    with term_policy("error"):
        try:
            to_engine(term)
        except TermError as exc:
            return exc
    return None


_SCANNED: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()  # graph -> (len, errors): a graph is scanned once per size
_MAX_ERRORS = 100


def scan_graph(graph: Any, where: str = "graph") -> tuple[TermError, ...]:
    """Every ill-formed term of an rdflib / StarLayer graph (first ``_MAX_ERRORS``), each located by ``where``, position and
    the first triple it occurs in. Distinct terms are checked once. A graph already scanned at the same size is not
    scanned again."""
    try:
        size = len(graph)
        cached = _SCANNED.get(graph)
        if cached is not None and cached[0] == size:
            return tuple(e.located(where, e.position, e.triple) for e in cached[1])
    except TypeError:
        size = None
    seen: set = set()
    errors: list[TermError] = []
    for triple in graph.triples((None, None, None)):
        for position, term in zip(("subject", "predicate", "object"), triple, strict=True):
            if term in seen:
                continue
            seen.add(term)
            err = _ill_formed(term)
            if err is None:
                continue
            if err.kind == "iri" and err.term != term and getattr(term, "datatype", None) == err.term:
                position = "datatype of the object"  # noqa: PLW2901
            errors.append(err.located(where, position, triple))
            if len(errors) >= _MAX_ERRORS:
                break
        if len(errors) >= _MAX_ERRORS:
            break
    if size is not None:
        with contextlib.suppress(TypeError):
            _SCANNED[graph] = (size, tuple(errors))
    return tuple(errors)


def check_graphs(*labelled: tuple[Any, str]) -> tuple[TermError, ...]:
    """The single up-front check of a run: scan each ``(graph, label)`` (rdflib / StarLayer graphs; engine-term graphs and
    ``None`` hold only well-formed terms) and, under the strict policy, raise one aggregate ``TermError`` naming every
    offender with its graph label. Under ``term_policy("lenient")`` return the offenders instead."""
    errors: list[TermError] = []
    done: set[int] = set()
    for graph, where in labelled:
        if graph is None or getattr(graph, "engine_terms", False) or id(graph) in done:
            continue
        done.add(id(graph))
        errors.extend(scan_graph(graph, where))
    if errors and _POLICY.get() != "lenient":
        raise TermError(errors[0].term, errors[0].kind, errors[0].reason, errors=tuple(errors))
    return tuple(errors)


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


class RdflibTermView:
    """A ``GraphView`` that yields engine (pyoxigraph) terms from an rdflib ``Graph`` / ``StarLayerGraph``: patterns are
    converted to rdflib terms on the way in, results to engine terms on the way out. ``graph`` is the wrapped graph;
    ``namespaces`` / ``namespace_manager`` pass through so report prefixes still work.

    Construction scans the graph once for ill-formed terms (``TermError``): under the default strict policy it raises
    ``TermError`` (aggregate: all offenders, ``where`` names the graph); under ``term_policy("lenient")`` the offenders are
    kept on ``invalid_terms`` and processed as opaque stand-ins. ``where`` labels the graph in messages; ``check=False``
    skips the scan (conversion then still raises ``TermError`` lazily on first contact in strict mode)."""

    engine_terms = True
    preserves_lexical_forms = True

    def __init__(self, graph: Any, where: str = "graph", check: bool = True) -> None:
        self.graph = graph
        self.where = where
        self.policy = _POLICY.get()  # a lenient view stays lenient when it is read after the ``term_policy`` block ended
        self.invalid_terms: tuple[TermError, ...] = ()
        if check:
            errors = scan_graph(graph, where)
            if errors:
                if _POLICY.get() != "lenient":
                    raise TermError(errors[0].term, errors[0].kind, errors[0].reason, errors=errors)
                self.invalid_terms = errors

    def _in(self, t: Any) -> Any:
        return None if t is None else from_engine(t)

    def _out(self, t: Any) -> Any:
        if self.policy == _POLICY.get():
            return to_engine(t)
        token = _POLICY.set(self.policy)
        try:
            return to_engine(t)
        finally:
            _POLICY.reset(token)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        try:
            it = self.graph.triples((self._in(s), self._in(p), self._in(o)))
            first = next(it, None)  # a pattern the graph rejects (a literal subject ...) simply has no match
        except (TypeError, ValueError):
            return
        if first is not None:
            yield self._out(first[0]), self._out(first[1]), self._out(first[2])
            for ts, tp, to in it:
                yield self._out(ts), self._out(tp), self._out(to)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        for _s, _p, o in self.triples((subject, predicate, None)):
            yield o

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        for s, _p, _o in self.triples((None, predicate, object)):
            yield s

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        s, p, o = triple
        return next(iter(self.triples((s, p, o))), None) is not None

    def __len__(self) -> int:
        return len(self.graph)

    def __getattr__(self, name: str) -> Any:
        if name in ("namespaces", "namespace_manager", "identifier"):
            return getattr(self.graph, name)
        if name == "sparql_query" and hasattr(self.graph, "sparql_query"):
            return self._sparql_query  # a graph with its own SPARQL (``SparqlCapable``) keeps precedence
        raise AttributeError(name)

    def _sparql_query(self, text: str, init_bindings: Any = None) -> Any:
        from dataclasses import replace

        out = self.graph.sparql_query(text, {k: from_engine(v) for k, v in (init_bindings or {}).items()} or None)
        return replace(out, rows=tuple({k: to_engine(v) for k, v in row.items()} for row in out.rows))


def engine_view(graph: Any, where: str = "graph") -> Any:
    """The engine's term view of ``graph``: an Oxigraph-backed view or an already-engine view as it is; anything else
    (rdflib, StarLayerGraph) through ``RdflibTermView`` (which raises ``TermError`` for ill-formed terms: see there)."""
    if graph is None or getattr(graph, "engine_terms", False):
        return graph
    return RdflibTermView(graph, where)


class LegacyTermView:
    """The inverse adapter: a view over an engine-term graph that speaks rdflib terms (for code that still is rdflib)."""

    def __init__(self, view: Any) -> None:
        self.view = view

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        for t in self.view.triples((to_engine(s), to_engine(p), to_engine(o))):
            yield from_engine_triple(t)

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        for o in self.view.objects(to_engine(subject), to_engine(predicate)):
            yield from_engine(o)

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        for s in self.view.subjects(to_engine(predicate), to_engine(object)):
            yield from_engine(s)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for p, o in self.view.predicate_objects(to_engine(subject)):
            yield from_engine(p), from_engine(o)

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        return tuple(to_engine(t) for t in triple) in self.view

    def __len__(self) -> int:
        return len(self.view)

    def predicates(self, subject: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        seen: set = set()
        for _s, p, _o in self.triples((subject, None, object)):
            if p not in seen:
                seen.add(p)
                yield p

    def items(self, head: Any) -> Iterator[Any]:
        """Members of the rdf:list at ``head`` (as ``rdflib.Graph.items``)."""
        rdf_nil, rdf_first, rdf_rest = from_engine(RDF.nil), from_engine(RDF.first), from_engine(RDF.rest)
        seen: set = set()
        while head is not None and head != rdf_nil and head not in seen:
            seen.add(head)
            first = next(self.objects(head, rdf_first), None)
            if first is None:
                return
            yield first
            head = next(self.objects(head, rdf_rest), None)

    def query(self, text: str, init_bindings: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """``OxigraphGraph.query`` with rdflib terms in and out (SELECT rows, ASK bool, CONSTRUCT triples)."""
        out = self.view.query(text, {k: to_engine(v) for k, v in (init_bindings or {}).items()} or None, **kwargs)
        if isinstance(out, list):
            return [
                {k: from_engine(v) for k, v in row.items()} if isinstance(row, dict) else from_engine_triple(row)
                for row in out
            ]
        return out

    @property
    def inferred(self) -> frozenset:
        return frozenset(from_engine_triple(t) for t in self.view.inferred)

    def __getattr__(self, name: str) -> Any:
        if name in ("namespaces", "namespace_manager", "identifier", "store"):
            return getattr(self.view, name)
        raise AttributeError(name)
