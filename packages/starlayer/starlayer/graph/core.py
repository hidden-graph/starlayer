"""``StarLayerGraph`` (one graph of a store) and ``StarLayerDataset`` (the whole store): composition wrappers over a ``pyoxigraph.Store``.

Terms are pyoxigraph terms. rdflib is not imported here; a caller may still pass rdflib / StarLayer terms, which are converted
on the way in (see ``terms.term``). These are the library's graph classes (``starlayer.graph.StarLayerGraph`` / ``StarLayerDataset``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pyoxigraph as ox

from starlayer.errors import FormatError
from starlayer.graph import config, formats, lexical, ntversion, terms
from starlayer.graph._detached import detached
from starlayer.graph._versions import require_supported_pyoxigraph
from starlayer.graph.execution import run, union
from starlayer.graph.execution.result import Result
from starlayer.graph.ox_store import OxStore

require_supported_pyoxigraph()

_ABSOLUTE_IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")
_TURTLE_LIKE = (ox.RdfFormat.TURTLE, ox.RdfFormat.TRIG)
# The syntaxes that define a version declaration (RDF 1.2 Turtle, TriG, N-Triples, N-Quads): the line written for "1.2".
_VERSION_LINE = {
    ox.RdfFormat.TURTLE: b'@version "1.2" .\n',
    ox.RdfFormat.TRIG: b'@version "1.2" .\n',
    ox.RdfFormat.N_TRIPLES: b'VERSION "1.2"\n',
    ox.RdfFormat.N_QUADS: b'VERSION "1.2"\n',
}


def _uses_rdf12(items: Iterable[Any]) -> bool:
    """True when a triple or quad has a triple term as its object or a base-direction literal: what RDF 1.1 cannot say."""
    for i in items:
        o = i.object
        if isinstance(o, ox.Triple) or (isinstance(o, ox.Literal) and o.direction is not None):
            return True
    return False


def as_store(x: Any) -> ox.Store:
    """The ``pyoxigraph.Store`` behind a wrapper, an ``OxigraphGraph`` view, or a bare store."""
    from starlayer.graph.endpoint import BackedStore

    if isinstance(x, (ox.Store, BackedStore)):
        return x
    s = getattr(x, "store", None)
    if isinstance(s, (ox.Store, BackedStore)):
        return s
    raise TypeError(f"expected an StarLayerGraph, StarLayerDataset or pyoxigraph.Store, not {type(x).__name__}")


_IRI_OR_STRING = re.compile(
    r"\\."  # an escaped character of a prefixed name's local part (``b:it\'s``): its quote does not open a string
    r'|"""(?:[^"\\]|\\.|"(?!""))*"""'  # long strings first
    r"|'''(?:[^'\\]|\\.|'(?!''))*'''"
    r'|"(?:[^"\\\n]|\\.)*"'
    r"|'(?:[^'\\\n]|\\.)*'"
    r'|<[^<>\s"{}|^`\\]*>',  # an IRI reference
    re.S,
)


def _strip_unused_prefixes(text: str) -> str:
    """Drop the ``@prefix`` header lines Oxigraph wrote for prefixes the body does not use (it declares every prefix it is given)."""
    lines = text.split("\n")
    n = 0
    decl = re.compile(r"@prefix ([^\s:]*): <[^>]*> \.$")
    while n < len(lines) and (lines[n].startswith("@base ") or decl.match(lines[n])):
        n += 1
    head, body = lines[:n], "\n".join(lines[n:])
    # Look for prefixed names only outside IRIs and strings, but everywhere else: after ``^^`` (a datatype), inside ``<<( )>>``,
    # ``<< >>``, ``{| |}`` and after ``~``. (A lookbehind on ``^^`` here used to hide a prefix used only as a datatype.)
    names = _IRI_OR_STRING.sub(" ", body)
    keep = []
    for line in head:
        m = decl.match(line)
        if m is None:
            keep.append(line)
            continue
        p = m.group(1)
        used = re.search(r"(?<![\w.\-:%])" + re.escape(p) + r":", names)
        if used:
            keep.append(line)
    return "\n".join([*keep, body])


_NCNAME = re.compile(r"[^\W\d][\w.\-]*")


def _xml_safe_blank_nodes(items: Iterable[Any]) -> Iterable[Any]:
    """The triples or quads with every blank node whose label is not an XML NCName (``1``, ``0a:b``) relabelled: RDF/XML
    writes the label as ``rdf:nodeID``, which must be an NCName. A graph with only valid labels is returned as it was."""
    items = list(items)
    labels: set[str] = set()

    def scan(t: Any) -> None:
        if isinstance(t, ox.BlankNode):
            labels.add(t.value)
        elif isinstance(t, ox.Triple):
            for x in (t.subject, t.predicate, t.object):
                scan(x)

    for i in items:
        for x in (i.subject, i.predicate, i.object, *([i.graph_name] if isinstance(i, ox.Quad) else [])):
            scan(x)
    bad = sorted(x for x in labels if not _NCNAME.fullmatch(x))
    if not bad:
        return items
    taken, new, n = set(labels), {}, 0
    for old in bad:
        while f"b{n}" in taken:
            n += 1
        new[old] = f"b{n}"
        taken.add(f"b{n}")

    def fix(t: Any) -> Any:
        if isinstance(t, ox.BlankNode):
            return ox.BlankNode(new[t.value]) if t.value in new else t
        if isinstance(t, ox.Triple):
            return ox.Triple(fix(t.subject), t.predicate, fix(t.object))
        return t

    if items and isinstance(items[0], ox.Quad):
        return [ox.Quad(fix(q.subject), q.predicate, fix(q.object), fix(q.graph_name)) for q in items]
    return [ox.Triple(fix(t.subject), t.predicate, fix(t.object)) for t in items]


def _no_backend(backend: Any) -> None:
    if backend is not None:
        raise TypeError(
            f"backend={backend!r} is not an option of the Oxigraph wrapper: it is always an Oxigraph store speaking RDF 1.2. "
            "Choose the storage with store= (a pyoxigraph.Store) or path= (an on-disk store), or hold a graph of a remote SPARQL "
            "endpoint with endpoint= (an Endpoint); a query can also read one with SERVICE"
        )


def _read_input(data: Any, source: Any, file: Any) -> tuple[dict[str, Any], str | None]:
    """The ``ox.parse`` keyword for the input, and a path hint for format guessing."""
    given = [x for x in (data, source, file) if x is not None]
    if len(given) != 1:
        raise ValueError("parse() needs exactly one of data=, source= or file=")
    obj = given[0]
    if data is not None:
        if not isinstance(obj, (str, bytes, bytearray)) and not hasattr(obj, "read"):
            raise TypeError(f"data= must be str or bytes, not {type(obj).__name__}")
        return {"input": obj}, None
    if hasattr(obj, "read"):
        return {"input": obj}, getattr(obj, "name", None)
    if isinstance(obj, (str, os.PathLike)):
        text = os.fspath(obj)
        if text.startswith(("http://", "https://")):
            import urllib.request

            req = urllib.request.Request(text, headers={"Accept": "text/turtle, application/rdf+xml;q=0.9, */*;q=0.1"})
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                return {"input": resp.read()}, text
        if text[:5].lower() == "file:":  # a file: URL names a local path
            import urllib.parse
            import urllib.request

            text = urllib.request.url2pathname(urllib.parse.urlparse(text).path)
        return {"path": text}, text
    raise TypeError(f"cannot read RDF from {type(obj).__name__}")


class _Base:
    """What a single graph (``StarLayerGraph``) and the dataset share. Subclasses define ``_pattern_graph`` and ``_union``."""

    #: the engine's term model is pyoxigraph's (the SHACL engine reads these)
    engine_terms = True
    preserves_lexical_forms = False
    native_sparql = True

    store: ox.Store
    prefixes: dict[str, str]
    _path: str | None = None

    # ---- construction ------------------------------------------------------------------------------------------
    def _init_store(self, store: Any, path: Any, prefixes: dict[str, str] | None) -> None:
        if store is not None and path is not None:
            raise ValueError("give a store or a path, not both")
        self.store = as_store(store) if store is not None else ox.Store(os.fspath(path) if path is not None else None)
        self._path = os.fspath(path) if path is not None else None
        self.prefixes = dict(prefixes) if prefixes is not None else config.new_prefix_dict()
        self._hold_version()

    def _hold_version(self) -> None:
        """Keep the write count (and the entailed copies on it) of this store alive as long as this wrapper is (``union._versions`` holds it weakly)."""
        self._version = union.version_of(self.store)

    # ---- a graph held by an endpoint (``StarLayerGraph(endpoint=...)``) ---------------------------------------------
    def sync(self) -> Any:
        """Pull the graph from the endpoint again, replacing the local copy (a graph that has no endpoint is already in sync)."""
        if hasattr(self.store, "sync"):
            self.store.sync()
        return self

    def as_store(self) -> ox.Store:
        union.touch(self.store)  # the caller may write to it: a deduplicated copy of the union is stale from now on
        return self.store

    # ---- StarLayer helpers (thin delegates; the code lives in graph/) -------------------------------------
    def infer(self, entailment: Any = None, **kw: Any) -> Any:
        from starlayer.graph.entailment import infer as m
        return m.infer(self, m.ENTAILMENT.RDFS if entailment is None else entailment, **kw)

    def owl_imports(self) -> tuple[Any, ...]:
        from starlayer.graph import imports
        return imports.owl_imports(self)

    def has_import_locally(self, iri: Any) -> bool:
        from starlayer.graph import imports
        return imports.has_import_locally(self, iri)

    def resolve_imports(self, **kw: Any) -> Any:
        from starlayer.graph import imports
        return imports.resolve_imports(self, **kw)

    def skolemize(self, *a: Any, **kw: Any) -> Any:
        from starlayer.graph import rewrite
        return rewrite.skolemize(self, *a, **kw)

    def de_skolemize(self, *a: Any, **kw: Any) -> Any:
        from starlayer.graph import rewrite
        return rewrite.de_skolemize(self, *a, **kw)

    def cbd(self, resource: Any, **kw: Any) -> Any:
        from starlayer.graph import rewrite
        return rewrite.cbd(self, resource, **kw)

    def empty_like(self) -> Any:
        from starlayer.graph import rewrite
        return rewrite.empty_like(self)

    def qname(self, uri: Any) -> str:
        from starlayer.graph import qnames
        return qnames.qname(self.prefixes, uri)

    def compute_qname(self, uri: Any, generate: bool = True) -> tuple[str, str, str]:
        from starlayer.graph import qnames
        return qnames.compute_qname(self.prefixes, uri, generate)

    def expand_curie(self, curie: str) -> Any:
        from starlayer.graph import qnames
        return qnames.expand_curie(self.prefixes, curie)

    def qname_term(self, term: Any) -> str:
        """The prefixed N3 form of any term (IRI, blank node, literal, triple term) using this graph's prefixes; an IRI with no
        fitting prefix is ``<iri>``. pyoxigraph terms have no ``n3()``: this replaces ``term.n3(namespace_manager)``, and
        ``str(term)`` replaces ``term.n3()``."""
        from starlayer.graph import qnames
        return qnames.n3(self.prefixes, term)

    def namespaces(self) -> Iterator[tuple[str, str]]:
        """``(prefix, namespace)`` pairs of the bound prefixes; the namespace is a plain ``str`` (the ``prefixes`` dict's value)."""
        return iter(list(self.prefixes.items()))

    # ---- subclass hooks ----------------------------------------------------------------------------------------
    def _pattern_graph(self) -> Any: ...
    def _add_graph(self) -> Any: ...
    _union = False

    # ---- reading ------------------------------------------------------------------------------------------------
    def _quads(self, s: Any, p: Any, o: Any, g: Any = ...) -> Iterator[ox.Quad]:
        """The matching quads, safe to abandon or finish on another thread (see ``_detached``); ``_has_quad`` for an existence test."""
        pat = terms.in_pattern(s, p, o)
        if pat is None:
            return iter(())
        return detached(self.store.quads_for_pattern(*pat, self._pattern_graph() if g is ... else g))

    def _has_quad(self, s: Any, p: Any, o: Any, g: Any = ...) -> bool:
        pat = terms.in_pattern(s, p, o)
        if pat is None:
            return False
        return next(self.store.quads_for_pattern(*pat, self._pattern_graph() if g is ... else g), None) is not None  # (dropped here, on this thread)

    def triples(self, pattern: tuple[Any, Any, Any] = (None, None, None)) -> Iterator[tuple[Any, Any, Any]]:
        s, p, o = pattern
        seen: set | None = set() if self._union else None
        for q in self._quads(s, p, o):
            key = (q.subject, q.predicate, q.object)
            if seen is not None:
                if key in seen:
                    continue
                seen.add(key)
            yield key

    def quads(self, pattern: tuple = (None, None, None, None)) -> Iterator[ox.Quad]:
        """Quads matching ``(s, p, o)`` or ``(s, p, o, graph)``; ``None`` is a wildcard. On a ``StarLayerGraph`` the graph is fixed."""
        s, p, o = pattern[:3]
        g = terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else ...
        return self._quads_in(s, p, o, g)

    def _quads_in(self, s: Any, p: Any, o: Any, g: Any) -> Iterator[ox.Quad]:
        return self._quads(s, p, o, ... if g is ... else g)

    def __iter__(self) -> Iterator[tuple[Any, Any, Any]]:
        return self.triples()

    def __len__(self) -> int:
        if self._union:
            return sum(1 for _ in self.triples())
        if isinstance(self.store, ox.Store) and self._pattern_graph() == ox.DefaultGraph() and next(iter(self.store.named_graphs()), None) is None:
            return len(self.store)  # the default graph is all the store has: the store counts them, without a Python object per quad
        return sum(1 for _ in self._quads(None, None, None))

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, (ox.Triple, ox.Quad)):
            item = tuple(item)
        if len(item) == 4:  # a single graph contains nothing of another graph (``_quads_in`` is empty for a foreign graph)
            return next(self._quads_in(*item[:3], terms.graph_name(item[3])), None) is not None
        return self._has_quad(*item)

    def _terms(self, s: Any, p: Any, o: Any, pick: Any, unique: bool) -> Iterator[Any]:
        """The ``pick`` term of each matching triple. On a union a triple held by several graphs counts once (as ``triples()``
        does); ``unique`` also drops a repeated term."""
        seen_terms: set | None = set() if unique else None
        seen_triples: set | None = set() if self._union else None
        for q in self._quads(s, p, o):
            if seen_triples is not None:
                key = (q.subject, q.predicate, q.object)
                if key in seen_triples:
                    continue
                seen_triples.add(key)
            t = pick(q)
            if seen_terms is not None:
                if t in seen_terms:
                    continue
                seen_terms.add(t)
            yield t

    def objects(self, subject: Any = None, predicate: Any = None, unique: bool = False) -> Iterator[Any]:
        return self._terms(subject, predicate, None, lambda q: q.object, unique)

    def subjects(self, predicate: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:
        return self._terms(None, predicate, object, lambda q: q.subject, unique)

    def predicates(self, subject: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:
        return self._terms(subject, None, object, lambda q: q.predicate, unique)

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def subject_objects(self, predicate: Any = None) -> Iterator[tuple[Any, Any]]:
        for s, _p, o in self.triples((None, predicate, None)):
            yield s, o

    def subject_predicates(self, object: Any = None) -> Iterator[tuple[Any, Any]]:
        for s, p, _o in self.triples((None, None, object)):
            yield s, p

    def value(self, subject: Any = None, predicate: Any = terms.RDF_VALUE, object: Any = None, default: Any = None,
              any: bool = True) -> Any:  # noqa: A002
        """The one term completing ``(subject, predicate, object)`` (exactly one of the three is None; ``predicate`` defaults to
        ``rdf:value`` as in rdflib). ``default`` when nothing matches; with ``any=False`` more than one match raises ``ValueError``."""
        if (subject is None) + (predicate is None) + (object is None) != 1:
            raise ValueError("value() needs exactly one of subject, predicate, object to be None")
        slot = 0 if subject is None else 1 if predicate is None else 2
        it = (t[slot] for t in self.triples((subject, predicate, object)))
        first = next(it, None)
        if first is None:
            return default
        if not any and next(it, None) is not None:
            raise ValueError("more than one value")
        return first

    def items(self, head: Any) -> Iterator[Any]:
        """The members of the RDF list starting at ``head`` (read-only). ``rdf:nil`` is the empty list. A cycle, a node with no
        ``rdf:first`` or with several ``rdf:first`` / ``rdf:rest`` raises a ``FormatError`` (kind ``"rdf"``)."""
        head = terms.term(head)
        seen: set = set()
        while head != terms.RDF_NIL:
            if head in seen:
                raise FormatError(f"cycle in the RDF list at {head}", kind="rdf", context=f"rdf:List at {head}")
            seen.add(head)
            firsts = list(self.objects(head, terms.RDF_FIRST, unique=True))
            rests = list(self.objects(head, terms.RDF_REST, unique=True))
            if len(firsts) != 1 or len(rests) != 1:
                raise FormatError(f"{head} is not a well-formed list node ({len(firsts)} rdf:first, {len(rests)} rdf:rest)", kind="rdf", context=f"rdf:List at {head}")
            yield firsts[0]
            head = rests[0]

    def profile(self) -> Any:
        """A snapshot of what the data says about itself (classes with counts, the properties their instances use); see ``profile.profile``."""
        from starlayer.graph.profile import profile

        return profile(self)

    def add_list(self, items: Iterable[Any], head: Any = None) -> Any:
        """Write ``items`` as an RDF list and return its head (``rdf:nil`` for none); see ``rdflist.add_list``."""
        from starlayer.graph import rdflist

        return rdflist.add_list(self, items, head)

    def remove_list(self, head: Any) -> Any:
        """Remove the list nodes of the list starting at ``head``; see ``rdflist.remove_list``."""
        from starlayer.graph import rdflist

        return rdflist.remove_list(self, head)

    def set_list(self, subject: Any, predicate: Any, items: Iterable[Any]) -> Any:
        """Make ``items`` the one list ``subject`` has for ``predicate`` and return its head; see ``rdflist.set_list``."""
        from starlayer.graph import rdflist

        return rdflist.set_list(self, subject, predicate, items)

    def set(self, triple: Any) -> Any:  # noqa: A003
        """Make ``triple`` the only one with its subject and predicate: remove the others, then add it (``rdflib.Graph.set``)."""
        subject, predicate, _object = triple
        self.remove((subject, predicate, None))
        return self.add(triple)

    def transitive_objects(self, subject: Any, predicate: Any) -> Iterator[Any]:
        """``subject`` and the nodes reached from it by repeating ``predicate``, each once; see ``rdflist.transitive_objects``."""
        from starlayer.graph import rdflist

        return rdflist.transitive_objects(self, subject, predicate)

    def transitive_subjects(self, predicate: Any, object: Any) -> Iterator[Any]:  # noqa: A002
        """``object`` and the nodes that reach it by repeating ``predicate``, each once; see ``rdflist.transitive_subjects``."""
        from starlayer.graph import rdflist

        return rdflist.transitive_subjects(self, predicate, object)

    # ---- writing ------------------------------------------------------------------------------------------------
    def _quad(self, triple: Any, g: Any, strict: bool = True) -> ox.Quad:
        """The quad for a triple (into graph ``g``) or a quad. With ``strict`` a quad that is not in this graph (a quad of
        another graph) raises ``ValueError``: a ``StarLayerGraph`` never writes outside its own graph."""
        if isinstance(triple, ox.Quad):
            q = triple
        elif len(triple) == 4:
            q = ox.Quad(*(terms.term(t) for t in triple[:3]), terms.graph_name(triple[3]))
        else:
            s, p, o = triple
            return ox.Quad(terms.term(s), terms.term(p), terms.term(o), g)
        if strict and not self._accepts(q):
            raise ValueError(f"this StarLayerGraph writes only to graph {self._add_graph()}; it cannot add a quad of graph {q.graph_name}")
        return q

    def add(self, triple: Any) -> Any:
        rewrites = lexical.Rewrites()
        quad = self._quad(triple, self._add_graph())
        self.store.add(next(iter(lexical.watch((quad,), rewrites))))
        union.touch(self.store)
        rewrites.emit(self.store)
        return self

    def extend(self, triples: Iterable[Any]) -> Any:
        """Add many triples (or quads on a dataset) in one transaction."""
        g = self._add_graph()
        rewrites = lexical.Rewrites()
        try:
            self.store.extend(lexical.watch((self._quad(t, g) for t in triples), rewrites))
        finally:
            union.touch(self.store)
            rewrites.emit(self.store)
        return self

    def addN(self, quads: Iterable[Any]) -> Any:  # noqa: N802
        """rdflib's name: add ``(s, p, o, graph)`` quads. On a ``StarLayerGraph`` only quads for its graph are added."""
        rewrites = lexical.Rewrites()
        try:
            self.store.extend(lexical.watch((q for q in (self._quad(q, self._add_graph(), False) for q in quads) if self._accepts(q)), rewrites))
        finally:
            union.touch(self.store)
            rewrites.emit(self.store)
        return self

    def _accepts(self, quad: ox.Quad) -> bool:
        return True

    def remove(self, pattern: tuple[Any, Any, Any]) -> Any:
        """Remove every statement matching the pattern (``None`` is a wildcard), as rdflib's ``remove`` does. On a ``StarLayerGraph`` a
        pattern naming another graph matches nothing and removes nothing (it never reaches into the other graph)."""
        doomed = list(self._quads_in(*pattern[:3], terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else ...))
        for q in doomed:
            self.store.remove(q)
        union.touch(self.store)
        return self

    # ---- Oxigraph's own store methods: ``g.ox.<method>(...)`` (``ox_store.py``); ``read_only`` makes a store ------------------------
    def _scope(self) -> Any:
        """The one graph this object may touch through ``.ox`` (a ``StarLayerGraph``), or ``None`` (a dataset: any graph)."""
        return None

    @classmethod
    def read_only(cls, path: Any, **kw: Any) -> Any:
        """Oxigraph's ``Store.read_only``: open an existing on-disk store for reading (a write raises ``RuntimeError``). Close any writer of the path first.
        ``kw`` is what the class takes besides the store (``identifier=`` or ``prefixes=``; ``default_union=`` or ``prefixes=``)."""
        return cls(store=ox.Store.read_only(os.fspath(path)), **kw)

    # ---- parse / serialize --------------------------------------------------------------------------------------
    def parse(self, source: Any = None, format: str | None = None, *, data: Any = None, file: Any = None,  # noqa: A002
              base: str | None = None, publicID: str | None = None, rename_blank_nodes: bool = True) -> Any:  # noqa: N803
        """Parse a document into this graph. ``source`` is a path, URL or file object; or give ``data=`` (str / bytes) or
        ``file=``. ``format`` is a name (``formats.py``) or an ``RdfFormat``; omitted it is guessed from the file name, else
        Turtle. Blank nodes are scoped to the document (renamed per parse unless ``rename_blank_nodes=False``). The prefixes the
        document declares are copied into ``self.prefixes``. A triple format loads into the default graph of a dataset or into
        this graph; a quad format loads each quad into its graph, and into a single ``StarLayerGraph`` only if it has no named graphs
        (otherwise ``ValueError``: parse into a ``StarLayerDataset``). A malformed document is a ``FormatError`` (kind ``"rdf"``) with
        ``line`` and ``col`` when the parser reports them; a file that cannot be read stays an ``OSError``; an unknown ``format`` name is a ``ValueError``."""
        kw, hint = _read_input(data, source, file)
        if formats.is_manchester(format) or (format is None and hint and str(hint).lower().endswith((".omn", ".manchester"))):
            return self._parse_manchester(kw, hint, base or publicID)
        guessed = formats.format_from_path(hint) if hint else None
        fmt = formats.to_format(format, default=guessed or ox.RdfFormat.TURTLE)
        direct = isinstance(self._add_graph(), ox.DefaultGraph)  # quads can go to the store untouched (the fast path)
        extra = {"without_named_graphs": True} if (direct and not isinstance(self, StarLayerDataset)) else {}
        if base is None and publicID is None:  # the retrieval location is the base IRI (RFC 3986 5.1.3)
            if "path" in kw:
                base = Path(kw["path"]).resolve().as_uri()
            elif hint and str(hint).lower().startswith(("http://", "https://")):
                base = str(hint)
        parser = ox.parse(format=fmt, base_iri=base or publicID, rename_blank_nodes=rename_blank_nodes, **extra,
                          **ntversion.accept_version_directive(kw, fmt))
        rewrites = lexical.Rewrites()
        try:
            try:
                if direct:
                    self.store.extend(lexical.watch(parser, rewrites))
                else:
                    move = self._retarget(self._add_graph())
                    self.store.extend(move(q) for q in lexical.watch(parser, rewrites))
            finally:
                union.touch(self.store)
                rewrites.emit(self.store)
        except SyntaxError as e:
            if type(e) is not SyntaxError:
                raise
            if "named graph" in str(e).lower():  # the wrong target for this document (an argument), not a malformed document
                raise ValueError("the document has named graphs; parse it into an StarLayerDataset") from e
            raise FormatError(str(e), kind="rdf", context=str(hint) if hint else f"{fmt} document", line=e.lineno, col=e.offset) from e
        self.prefixes.update(parser.prefixes or {})
        return self

    _default_format = "turtle"

    def _parse_manchester(self, kw: dict[str, Any], hint: str | None, base: str | None) -> Any:
        """OWL 2 Manchester Syntax: the parser (``parsers/manchester_parser.py``) is independent of the store and builds the
        triples, which are added here. It has no named graphs, so a dataset gets them in its default graph."""
        from starlayer.graph.manchester.parser import parse_manchester

        if "path" in kw:
            with open(kw["path"], encoding="utf-8") as fh:
                text = fh.read()
            base = base or Path(kw["path"]).resolve().as_uri()
        else:
            raw = kw["input"].read() if hasattr(kw["input"], "read") else kw["input"]
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        self.extend(list(parse_manchester(text, base=base)))
        return self

    def serialize(self, destination: Any = None, format: str | ox.RdfFormat | None = None, base: str | None = None,  # noqa: A002
                  prefixes: Mapping[str, str] | None = None, *, only_used: bool = False, rdf_version: str | None = None,
                  encoding: str = "utf-8", pretty: bool | str = False, bnode_labels: str | None = None) -> str | None:
        """Write the graph. ``destination`` None returns a ``str``; a path or file object is written and ``None`` returned.
        Prefixes are the graph's dict plus ``prefixes`` (the per-call override); ``only_used=True`` declares only those the
        output uses (Turtle, TriG). ``rdf_version="1.1"`` exports through ``starlayer.graph.interop`` (the basic encoding of
        triple terms), so the output contains no triple term. ``pretty=True`` lays Turtle / TriG out with
        ``pretty`` (nested blank nodes, lists, annotations; see that module).

        A Turtle, TriG, N-Triples or N-Quads document that uses an RDF 1.2 feature (a triple term, a base-direction literal)
        starts with the version declaration (``@version "1.2" .`` / ``VERSION "1.2"``), as does any such document written with
        ``rdf_version="1.2"``; plain RDF 1.1 data gets none unless asked. ``rdf_version="1.1"`` never writes one. Oxigraph's
        writers do not write it, so the wrapper adds it.

        ``bnode_labels="short"`` writes the blank nodes as ``_:b0``, ``_:b1``, ... instead of their long ids (see ``bnodes.py``; the graph
        keeps its ids, and the labels and the order of the statements are the same every time for the same graph). The default
        ``None`` writes the ids as they are."""
        if bnode_labels not in (None, "short"):
            raise ValueError(f"bnode_labels must be None or 'short', not {bnode_labels!r}")
        if formats.is_manchester(format):
            from starlayer.graph.manchester.serializer import serialize_manchester

            return self._write(serialize_manchester(self).encode("utf-8"), destination, encoding)
        fmt = formats.to_format(format or self._default_format)
        if rdf_version not in (None, "1.1", "rdf-1.1", "1.2", "rdf-1.2"):
            raise ValueError(f"unknown rdf_version {rdf_version!r}")
        pfx = {**self.prefixes, **{str(k): str(v) for k, v in (prefixes or {}).items()}}
        if not pretty and fmt in _TURTLE_LIKE:  # the pretty writer renames such a prefix; Oxigraph's would write Turtle that does not parse (N-Triples, N-Quads and JSON-LD write no prefixes)
            from starlayer.graph.pretty import _PN_PREFIX

            for name in pfx:
                if not _PN_PREFIX.fullmatch(name):
                    raise ValueError(f"{name!r} is not a valid prefix name")
        items = self._serial_items(fmt)
        if bnode_labels == "short":
            from starlayer.graph.bnodes import short_bnode_labels

            items = short_bnode_labels(items)
        if fmt == ox.RdfFormat.RDF_XML:
            items = _xml_safe_blank_nodes(items)
        if pretty:  # pretty Turtle / TriG (RDF 1.2): pretty.py
            from starlayer.graph.pretty import serialize_pretty

            source = self._pretty_source(fmt)
            if rdf_version in ("1.1", "rdf-1.1"):  # pretty-print the basic encoding, so the output has no triple term either
                from starlayer.graph import interop

                source = interop.encode_directions(interop.to_basic(self._serial_items(fmt)))
            if bnode_labels == "short":
                source = short_bnode_labels(list(source))
            raw = serialize_pretty(source, fmt, pfx or None, base, only_used, pretty).encode("utf-8")
        elif rdf_version in ("1.1", "rdf-1.1"):
            # Triple terms by the Interoperability draft's basic encoding, base-direction literals by the interop
            # policy (a datatype IRI form by default); the result contains neither.
            from starlayer.graph import interop

            raw = interop.export_rdf11(items, fmt, None, pfx or None, base, bnode_labels=bnode_labels)
        else:
            raw = ox.serialize(items, None, fmt, prefixes=pfx or None, base_iri=base)
        if only_used and fmt in _TURTLE_LIKE and pfx:
            raw = _strip_unused_prefixes(raw.decode("utf-8")).encode("utf-8")
        line = _VERSION_LINE.get(fmt)
        if line is not None and rdf_version not in ("1.1", "rdf-1.1") and not raw.startswith(line):
            # a quick byte test rules out most data; the exact test then reads the terms (a literal may contain "<<(")
            marked = rdf_version in ("1.2", "rdf-1.2") or (
                (b"<<(" in raw or b"--ltr" in raw or b"--rtl" in raw) and _uses_rdf12(self._serial_items(fmt))
            )
            if marked:
                raw = line + raw
        return self._write(raw, destination, encoding, fmt)

    @staticmethod
    def _write(raw: bytes, destination: Any, encoding: str, fmt: ox.RdfFormat | None = None) -> str | None:
        if destination is None:
            return raw.decode("utf-8")
        # ``raw`` is UTF-8. A path or a binary stream gets the bytes in ``encoding``; a text stream encodes for itself.
        if encoding.lower().replace("_", "-") in ("utf-8", "utf8"):
            data = raw
        elif fmt == ox.RdfFormat.RDF_XML:  # the XML declaration must name the encoding the bytes are in
            import codecs

            name = codecs.lookup(encoding).name
            name = "ISO-8859-" + name[len("iso8859-"):] if name.startswith("iso8859-") else name
            text = raw.decode("utf-8").replace('encoding="UTF-8"', f'encoding="{name}"', 1)
            data = text.encode(encoding, errors="xmlcharrefreplace")
        else:
            data = raw.decode("utf-8").encode(encoding)
        if isinstance(destination, (str, os.PathLike)):
            with open(destination, "wb") as fh:
                fh.write(data)
        else:
            try:
                destination.write(data)
            except TypeError:
                destination.write(raw.decode("utf-8"))
        return None

    def _pretty_source(self, fmt: ox.RdfFormat) -> Any:
        return self

    def _serial_items(self, fmt: ox.RdfFormat) -> Iterable[Any]:
        raise NotImplementedError

    # ---- prefixes -----------------------------------------------------------------------------------------------
    def bind(self, prefix: str, namespace: Any, override: bool = True) -> None:
        """Bind ``prefix`` to ``namespace``. The prefix must be a valid Turtle PN_PREFIX (``''`` is the empty prefix) and the
        namespace an absolute IRI (a ``str`` or a ``NamedNode``); anything else raises ``ValueError`` here, so a bad binding
        cannot make later ``query()`` / ``update()`` / ``serialize()`` calls fail."""
        from starlayer.graph.pretty import _IRI_BAD, _PN_PREFIX

        if not isinstance(prefix, str) or not _PN_PREFIX.fullmatch(prefix):
            raise ValueError(f"{prefix!r} is not a valid prefix name")
        # rdflib's namespace classes (``OWL``, ``Namespace(...)``) are not all ``str`` but print as their IRI
        ns = namespace.value if isinstance(namespace, ox.NamedNode) else (None if namespace is None else str(namespace))
        if not isinstance(ns, str) or not _ABSOLUTE_IRI.match(ns) or _IRI_BAD.search(ns):
            raise ValueError(f"{namespace!r} is not an absolute IRI, so it cannot be a namespace")
        if not override and prefix in self.prefixes:
            return
        self.prefixes[prefix] = str(ns)

    def unbind(self, prefix: str) -> bool:
        return self.prefixes.pop(prefix, None) is not None

    def used_prefixes(self) -> list[tuple[str, str]]:
        """``(prefix, namespace)`` pairs, sorted by prefix, of the graph's prefixes that its Turtle (TriG for a dataset)
        output actually uses: Oxigraph's own choice, read back from what its writer declares."""
        if not self.prefixes:
            return []
        fmt = ox.RdfFormat.TRIG if isinstance(self, StarLayerDataset) else ox.RdfFormat.TURTLE
        text = _strip_unused_prefixes(ox.serialize(self._serial_items(fmt), None, fmt, prefixes=self.prefixes).decode("utf-8"))
        import re

        out = {m.group(1): m.group(2) for m in re.finditer(r"(?m)^@prefix ([^\s:]*): <([^>]*)> \.$", text)}
        return sorted(out.items())

    # ---- SPARQL -------------------------------------------------------------------------------------------------
    def query(self, text: str, initNs: Mapping[str, str] | None = None, initBindings: Mapping[Any, Any] | None = None,  # noqa: N803
              base: str | None = None, *, entailment: Any = None, recompute: str = "onChange", engine: str = "hermit",
              timeout: Any = None, custom_functions: Mapping[Any, Any] | None = None,
              custom_aggregate_functions: Mapping[Any, Any] | None = None) -> Result:
        """Run SPARQL ``text`` on Oxigraph as it is. ``initNs`` overrides the graph's prefixes for this call; ``initBindings``
        pre-binds variables (``substitutions``, with the ``VALUES`` fallback). A ``StarLayerGraph`` queries its own graph as the default
        graph; a dataset the default graph, or the union of all graphs when ``default_union``.

        ``entailment`` is a regime IRI. ``ENTAILMENT.RDF`` / ``ENTAILMENT.RDFS``: the query is rewritten (see
        ``sparql/sqe/entailment.py``), the data is not touched or copied. ``ENTAILMENT["OWL-RDF-Based"]`` / ``["OWL-Direct"]``:
        the store is copied, the entailed triples are added to the copy and the query runs on the copy (this graph is never
        modified). The copy is kept on the store (``graph/entailment/cache.py``: shared by every wrapper of it, and by SHACL
        validation, whose ``inference=`` / ``sh:entailment`` OWL regimes and also RDF and RDFS use the same copy; here RDF and
        RDFS are the rewrite and never make or read one), one per regime (and per engine for ``OWL-Direct``), and ``recompute``
        says when it is made again: ``"onChange"`` (default) after a write made through this package since it was made
        (``as_store()`` counts; a write on a raw store reference kept from before is not seen, call ``union.touch()`` after it),
        ``"always"`` on every call (and then keeps none, dropping what was kept), ``"never"`` only when none is kept (it
        may then be out of date, data included). A write to another store does not count.
        ``clear_entailment_cache()`` drops the copies. ``engine`` /
        ``timeout`` (``"hermit"`` / ``"rustdl"``, seconds) apply to ``OWL-Direct`` only and raise ``ValueError`` otherwise.
        Anything else raises ``NotImplementedError``.

        ``custom_functions`` maps a function IRI (a ``NamedNode`` or its text) to a Python callable that takes pyoxigraph terms and
        returns a term or ``None``; the query can then call ``<iri>(?x)``. ``custom_aggregate_functions`` maps an IRI to a factory of
        objects with ``accumulate(term)`` and ``finish()``. Both are Oxigraph's, passed through for this call only."""
        regime = None if entailment is None else str(getattr(entailment, "value", entailment))
        from starlayer.graph.entailment import infer as ent

        if regime is not None and regime not in (ent.RDF_REGIME, ent.RDFS_REGIME, ent.OWL_RL_REGIME, ent.OWL_DIRECT_REGIME):
            raise NotImplementedError(
                f"entailment must be one of ENTAILMENT.RDF, RDFS, ['OWL-RDF-Based'], ['OWL-Direct'], got {entailment!r}."
            )
        if regime != ent.OWL_DIRECT_REGIME:
            if engine != "hermit":
                raise ValueError(f"engine={engine!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] (got entailment={entailment!r}) - omit engine= otherwise.")
            if timeout is not None:
                raise ValueError(f"timeout={timeout!r} is only meaningful for entailment=ENTAILMENT['OWL-Direct'] (got entailment={entailment!r}) - omit timeout= otherwise.")
        if regime in (ent.OWL_RL_REGIME, ent.OWL_DIRECT_REGIME):
            if recompute not in ("always", "never", "onChange"):
                raise ValueError(f"recompute must be one of ['always', 'never', 'onChange'], got {recompute!r}")
            from starlayer.graph.entailment import cache

            copy = cache.entailed_store_view(self, [regime], engine=engine, timeout=timeout, recompute=recompute)
            return copy.query(text, initNs=initNs, initBindings=initBindings, base=base,
                              custom_functions=custom_functions, custom_aggregate_functions=custom_aggregate_functions)
        return run.query(self._query_store(), text, prefixes=self.prefixes, init_ns=initNs, init_bindings=initBindings, base=base,
                         default_graph=self._query_default_graph(), union=self._union and not self._merged(), entailment=regime,
                         custom_functions=custom_functions, custom_aggregate_functions=custom_aggregate_functions)

    def clear_entailment_cache(self) -> Any:
        """Drop the entailed copies kept for this graph's store (``graph/entailment/cache.py``), which hold the whole store in memory: the
        ones query-time OWL entailment made and the ones SHACL validation with ``inference=`` made, for every wrapper of the store (one
        cache serves both). The next query or validation that needs one makes it again. Returns this object."""
        from starlayer.graph.entailment import cache

        cache.clear(self)
        return self

    def _query_store(self) -> ox.Store:
        return self.store

    def _merged(self) -> bool:
        return False

    def _query_default_graph(self) -> Any:
        return None

    def relevant_subgraph(
        self, query: str, init_bindings: Mapping[Any, Any] | None = None, init_ns: Mapping[str, str] | None = None
    ) -> Any:
        """The triples of this graph that the answer of ``query`` depends on, as a new graph (for a dataset the quads, as a new
        dataset); the query may use the prefixes, and ``init_ns`` overrides them (see ``starlayer.sparql.relevant``)."""
        from starlayer.sparql.relevant import relevant_subgraph

        return relevant_subgraph(self, query, init_bindings, {**self.prefixes, **(init_ns or {})})

    def check_query(
        self,
        text: str,
        *,
        custom_functions: Mapping[Any, Any] | None = None,
        custom_aggregate_functions: Mapping[Any, Any] | None = None,
    ) -> Any:
        """``starlayer.sparql.check_query`` for text that will run against this graph or dataset, so its prefixes count as declared."""
        from starlayer.sparql.check import check_query

        return check_query(
            text,
            prefixes=self.prefixes,
            custom_functions=custom_functions,
            custom_aggregate_functions=custom_aggregate_functions,
        )

    def update(self, text: str, initNs: Mapping[str, str] | None = None, base: str | None = None, *,  # noqa: N803
               custom_functions: Mapping[Any, Any] | None = None, custom_aggregate_functions: Mapping[Any, Any] | None = None) -> None:
        """Run SPARQL Update ``text`` (``custom_functions`` and ``custom_aggregate_functions`` as for ``query()``). On a ``StarLayerGraph`` the update stays within
        its graph: what it leaves unqualified is aimed at the graph (``INSERT DATA`` triples, ``WITH`` / ``USING``, ``CLEAR ALL``) and an update that names another graph
        raises ``ValueError`` (``execution/update_scope.py``). On a dataset it acts on the whole store. On a ``default_union`` dataset the ``WHERE`` of an ``INSERT`` /
        ``DELETE`` operation reads the union of all graphs, as ``query()`` does (done by adding ``USING`` clauses; see ``run.union_update_text`` for how, and its limits)."""
        try:
            run.update(self.store, text, prefixes=self.prefixes, init_ns=initNs, base=base, union=self._union,
                       overlap=self._overlap if self._union else None, custom_functions=custom_functions,
                       custom_aggregate_functions=custom_aggregate_functions, scope=self._scope())
        finally:
            union.touch(self.store)

    # ---- RDF 1.2 reifiers (thin functions in reification.py) -----------------------------------------------------
    def add_reification(self, reifier: Any, triple_term: Any) -> Any:
        from starlayer.graph import reification

        return reification.add_reification(self, reifier, triple_term)

    def reifiers(self, tt: Any = None, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: A002
        from starlayer.graph import reification

        return reification.reifiers(self, tt, predicate, object)

    def reified_triples(self, reifier: Any = None) -> Iterator[ox.Triple]:
        from starlayer.graph import reification

        return reification.reified_triples(self, reifier)

    def annotations(self, tt: Any = None) -> Iterator[tuple[Any, Any, Any]]:
        from starlayer.graph import reification

        return reification.annotations(self, tt)

    def remove_reification(self, reifier: Any, triple_term: Any = None) -> Any:
        from starlayer.graph import reification

        return reification.remove_reification(self, reifier, triple_term)

    def triple_terms(self, subject: Any = None, predicate: Any = None, object: Any = None) -> Iterator[ox.Triple]:  # noqa: A002
        from starlayer.graph import reification

        return reification.triple_terms(self, subject, predicate, object)

    # ---- the SHACL engine's graph view -------------------------------------------------------------------------
    def engine_view(self) -> Any:
        from starlayer.shacl.engine.oxigraph_view import DEFAULT, UNION, OxigraphGraph

        return OxigraphGraph(self.store, self._engine_graph_name(UNION, DEFAULT))

    def sparql_query(self, text: str, init_bindings: Mapping[str, Any] | None = None, custom_functions: Any = None) -> Any:
        """The engine's ``SparqlCapable`` hook (``custom_functions``: function IRI -> Python callable, as pyoxigraph takes them)."""
        return self._sparql_view().sparql_query(text, init_bindings, custom_functions)

    def _sparql_view(self) -> Any:
        return self.engine_view()

    def _engine_graph_name(self, union: Any, default: Any) -> Any:
        raise NotImplementedError

    # ---- set operators ------------------------------------------------------------------------------------------
    def _op(self, name: str, other: Any) -> Any:
        if type(other) is not type(self):
            return NotImplemented
        from starlayer.graph import setops

        res = self._combine(getattr(setops, name), other)
        res.prefixes.update({**other.prefixes, **self.prefixes})
        return res

    def __add__(self, other: Any) -> Any:
        return self._op("union", other)

    def __sub__(self, other: Any) -> Any:
        return self._op("difference", other)

    def __and__(self, other: Any) -> Any:
        return self._op("intersection", other)

    def __xor__(self, other: Any) -> Any:
        return self._op("symmetric_difference", other)

    def __iadd__(self, other: Any) -> Any:
        if type(other) is not type(self):
            return NotImplemented
        self.extend(other.quads() if isinstance(self, StarLayerDataset) else other.triples())
        return self

    def _items(self) -> list[Any]:
        return list(self.quads() if isinstance(self, StarLayerDataset) else self.triples())

    def _discard(self, items: Iterable[Any]) -> None:
        g = self._add_graph()
        try:
            for item in list(items):  # a list: ``items`` may come from this very graph
                self.store.remove(self._quad(item, g))
        finally:
            union.touch(self.store)

    # The in-place forms change this graph itself, as ``+=`` does and as rdflib's ``-=`` and a Python set's ``-=``, ``&=``, ``^=`` do. Without
    # them Python would run ``a = a - b``, which makes a new in-memory graph and leaves every other reference to ``a`` (and a graph on disk) unchanged.
    def __isub__(self, other: Any) -> Any:
        if type(other) is not type(self):
            return NotImplemented
        self._discard(other._items())
        return self

    def __iand__(self, other: Any) -> Any:
        if type(other) is not type(self):
            return NotImplemented
        self._discard((self - other)._items())
        return self

    def __ixor__(self, other: Any) -> Any:
        if type(other) is not type(self):
            return NotImplemented
        common, only_other = self & other, other - self
        self._discard(common._items())
        self.extend(only_other._items())
        return self

    def _combine(self, fn: Any, other: Any) -> Any:
        raise NotImplementedError

    def copy(self) -> Any:
        """An in-memory copy (new store) with a copy of the prefixes."""
        raise NotImplementedError

    def __copy__(self) -> Any:
        return self.copy()

    def __deepcopy__(self, memo: dict) -> Any:
        return self.copy()

    def to_rdflib(self, *, bnode_prefix: str | None = None, direction_policy: str = "datatype") -> Any:
        """A snapshot as plain rdflib (``rdflib.Graph`` for an ``StarLayerGraph``, ``rdflib.Dataset`` for an ``StarLayerDataset``), with
        RDF 1.2 presented as RDF 1.1 (``interop.to_rdf11``): each triple term becomes a blank node described by the
        ``rdf:PropositionForm`` basic encoding, each base-direction literal its datatype-IRI form (``direction_policy`` as in
        ``interop.encode_directions``). rdflib terms keep their lexical form as stored. Writes to the result do not reach
        this graph."""
        return _rdflib_bridge("to_rdflib()").to_rdflib_rdf11(self, bnode_prefix=bnode_prefix, direction_policy=direction_policy)

    def _refuse_path_pickle(self) -> None:
        if self._path is not None:
            raise TypeError(
                f"cannot pickle an {type(self).__name__} opened with path={self._path!r}: its data lives in an on-disk store. "
                "The unpickled object cannot reopen that path (a second opener of one RocksDB path is unsafe while this one is "
                "open, and the path may not exist where the pickle is read), and silently pickling the whole store would copy it "
                "into the pickle. Use .copy() for an in-memory copy, or serialize(format='nq') / parse() to move the data."
            )

    __hash__ = object.__hash__

    def __eq__(self, other: Any) -> bool:
        return self is other

    @property
    def ox(self) -> OxStore:
        """Oxigraph's own store methods, as Oxigraph defines them: ``g.ox.add(quad)``, ``g.ox.load(...)``, ``g.ox.flush()``. A method that
        writes keeps the write counter; on a ``StarLayerGraph`` a call that would reach another graph raises ``ValueError``. See ``ox_store.py``."""
        return OxStore(self)


def _sharing(graph: Any, prefixes: dict[str, str]) -> Any:
    """``graph`` with the prefix dict of the dataset it is a view of: a view and its dataset keep one set of prefixes. (A graph made with
    ``prefixes=`` copies the dict it is given.)"""
    graph.prefixes = prefixes
    return graph


def _rdflib_bridge(what: str) -> Any:
    """The ``rdflib_bridge`` module, or an ``ImportError`` that says how to install rdflib (the core itself never imports it)."""
    from starlayer.graph import rdflib_bridge

    rdflib_bridge.require_rdflib(what)
    return rdflib_bridge


class StarLayerGraph(_Base):
    """One graph of a store: the default graph (``identifier=None``) or the named graph ``identifier`` (a ``NamedNode``,
    ``BlankNode``, or an IRI string)."""

    def __init__(self, store: Any = None, path: Any = None, identifier: Any = None, *, prefixes: dict[str, str] | None = None,
                 backend: str | None = None, endpoint: Any = None, max_age: float | None = None, pull: bool = True) -> None:
        """``endpoint`` (an ``Endpoint``) holds this graph (the default graph, or the named graph ``identifier``) in a SPARQL endpoint;
        the graph keeps a full local copy, in memory or, with ``path``, on disk, in sync with the writes made through this object
        (``max_age`` seconds old at most, when given; ``pull=False`` opens an existing on-disk copy without asking the endpoint). See
        ``endpoint.py``."""
        _no_backend(backend)
        self._g = terms.graph_name(identifier)
        if endpoint is not None:
            if store is not None:
                raise ValueError("give an endpoint, or a store")
            from starlayer.graph.endpoint import BackedStore

            self.store = BackedStore(endpoint, self._g, max_age=max_age, path=path, pull=pull)
            self._path = os.fspath(path) if path is not None else None
            self.prefixes = dict(prefixes) if prefixes is not None else config.new_prefix_dict()
            self._hold_version()
        else:
            self._init_store(store, path, prefixes)

    @classmethod
    def from_rdflib(cls, graph: Any) -> StarLayerGraph:
        """A new in-memory ``StarLayerGraph`` with the triples, the prefixes its data uses and (when it is an IRI) identifier of an rdflib ``Graph`` or an
        old-style ``StarLayerGraph``; a ``TripleTerm`` becomes a triple term, a directional literal in its datatype-IRI form
        (what ``to_rdflib`` writes) is restored, and the basic encoding is left as triples (``interop.from_basic`` decodes it).
        A term RDF does not allow raises ``ValueError``. An ``StarLayerGraph`` is copied.
        For an rdflib dataset's named graphs use ``StarLayerDataset.from_rdflib``."""
        if isinstance(graph, StarLayerGraph):
            return graph.copy()
        if isinstance(graph, (StarLayerDataset, ox.Store)):
            raise TypeError(f"StarLayerGraph.from_rdflib takes an rdflib graph, not {type(graph).__name__}")
        return _rdflib_bridge("from_rdflib()").graph_from_rdflib(graph, restore_directions=True)

    @property
    def identifier(self) -> Any:
        """The name of the graph this ``StarLayerGraph`` holds."""
        return self._g

    def _pattern_graph(self) -> Any:
        return self._g

    def _add_graph(self) -> Any:
        return self._g

    def _accepts(self, quad: ox.Quad) -> bool:
        return quad.graph_name == self._g

    def _quads_in(self, s: Any, p: Any, o: Any, g: Any) -> Iterator[ox.Quad]:
        if g is not ... and g != self._g:
            return iter(())
        return self._quads(s, p, o)

    def _retarget(self, target: Any) -> Any:
        def move(q: ox.Quad) -> ox.Quad:
            if not isinstance(q.graph_name, ox.DefaultGraph):
                raise ValueError("the document has named graphs; parse it into an StarLayerDataset")
            return ox.Quad(q.subject, q.predicate, q.object, target)

        return move

    def _serial_items(self, fmt: ox.RdfFormat) -> Iterable[Any]:
        if fmt in formats.QUAD_FORMATS:
            return self._quads(None, None, None)
        if isinstance(self._g, ox.DefaultGraph) and isinstance(self.store, ox.Store):
            # a triple format writes a default-graph quad as the triple it holds, so the quads go to the writer as they are (it is
            # about eight times faster than making a Triple of each one first); the writer reads them all within the call, on this thread
            return self.store.quads_for_pattern(None, None, None, self._g)
        return (ox.Triple(q.subject, q.predicate, q.object) for q in self._quads(None, None, None))

    def _pretty_source(self, fmt: ox.RdfFormat) -> Any:
        # a quad format keeps the graph name of a named graph (the pretty writer flattens one passed as such)
        return list(self._quads(None, None, None)) if fmt in formats.QUAD_FORMATS else self

    def _query_default_graph(self) -> Any:
        return self._g

    def _engine_graph_name(self, union: Any, default: Any) -> Any:
        return default if isinstance(self._g, ox.DefaultGraph) else self._g

    def _scope(self) -> Any:
        return self._g

    def remove_graph(self) -> StarLayerGraph:
        """Drop this graph from its store with its triples (the default graph is emptied). Oxigraph's own form: ``ox.remove_graph(name)``."""
        if isinstance(self._g, ox.DefaultGraph):
            self.store.clear_graph(self._g)
        else:
            self.store.remove_graph(self._g)
        union.touch(self.store)
        return self

    def named_graphs(self) -> Iterator[Any]:
        """The names of the named graphs of the whole store, this one and the others, empty ones included. Oxigraph's own form: ``ox.named_graphs()``."""
        return iter(self.store.named_graphs())

    def clear(self) -> StarLayerGraph:
        """Remove every triple of this graph only; other graphs of the store are untouched."""
        self.store.clear_graph(self._g)
        union.touch(self.store)
        return self

    def _combine(self, fn: Any, other: StarLayerGraph) -> StarLayerGraph:
        a, b = ox.Store(), ox.Store()
        a.extend(ox.Quad(*t, ox.DefaultGraph()) for t in self.triples())
        b.extend(ox.Quad(*t, ox.DefaultGraph()) for t in other.triples())
        return StarLayerGraph(store=fn(a, b))

    def copy(self) -> StarLayerGraph:
        """An independent in-memory copy of this graph (same identifier, own copy of the prefixes). ``copy.copy`` and
        ``copy.deepcopy`` do the same, also for a graph opened with ``path=``."""
        g = StarLayerGraph(identifier=self._g)
        g.store.extend(self._quads(None, None, None))
        g.prefixes.clear()
        g.prefixes.update(self.prefixes)
        return g

    def __reduce__(self) -> Any:
        """Pickle: the quads of this graph, its identifier and prefixes (``pyoxigraph.Store`` is not picklable). A graph opened
        with ``path=`` is refused (``TypeError``), see ``_refuse_path_pickle``."""
        self._refuse_path_pickle()
        return (_rebuild_graph, (self._g, dict(self.prefixes), list(self._quads(None, None, None))))

    def __repr__(self) -> str:
        """A short form with the graph name and the triple count."""
        return f"<StarLayerGraph {self._g} ({len(self)} triples)>"


class StarLayerDataset(_Base):
    """The whole store. ``default_union`` (default True) makes ``triples`` / ``len`` / ``iter`` / SPARQL's default graph the
    union of all graphs, as the engine's graph view does; False restricts them to the default graph (rdflib's ``Dataset``)."""

    _default_format = "trig"  # a dataset writes its graphs unless asked for a triple format

    def __init__(self, store: Any = None, path: Any = None, default_union: bool = True, *, prefixes: dict[str, str] | None = None,
                 backend: str | None = None, endpoint: Any = None, max_age: float | None = None, pull: bool = True) -> None:
        """``endpoint`` (an ``Endpoint``) holds the whole dataset in a SPARQL endpoint; ``path``, ``max_age`` and ``pull`` are as for
        ``StarLayerGraph`` (see ``endpoint.py``)."""
        _no_backend(backend)
        if endpoint is not None:
            if store is not None:
                raise ValueError("give an endpoint, or a store")
            from starlayer.graph.endpoint import BackedStore

            self.store = BackedStore(endpoint, dataset=True, max_age=max_age, path=path, pull=pull)
            self._path = os.fspath(path) if path is not None else None
            self.prefixes = dict(prefixes) if prefixes is not None else config.new_prefix_dict()
            self._hold_version()
        else:
            self._init_store(store, path, prefixes)
        self._union = default_union
        self._overlap = union.Overlap()

    @classmethod
    def from_rdflib(cls, dataset: Any) -> StarLayerDataset:
        """A new in-memory ``StarLayerDataset`` from an rdflib ``Dataset`` / ``ConjunctiveGraph`` / ``StarLayerDataset`` (every graph, empty
        named graphs too, the prefixes its data uses, ``default_union``) or from a plain graph (its triples go to the default graph). Terms as in
        ``StarLayerGraph.from_rdflib``. An ``StarLayerDataset`` is copied."""
        if isinstance(dataset, StarLayerDataset):
            return dataset.copy()
        return _rdflib_bridge("from_rdflib()").dataset_from_rdflib(dataset)

    def _query_store(self) -> ox.Store:
        """The store SPARQL runs on: for a union default graph, one in which a triple held by several graphs is one triple
        (see ``union.py``)."""
        return self._overlap.store(self.store) if self._union else self.store

    def _merged(self) -> bool:
        return self._union and self._overlap.overlapping(self.store)

    @property
    def default_union(self) -> bool:
        """Whether the default graph is the union of all graphs."""
        return self._union

    def _pattern_graph(self) -> Any:
        return None if self._union else ox.DefaultGraph()

    def _add_graph(self) -> Any:
        return ox.DefaultGraph()

    def _quads_in(self, s: Any, p: Any, o: Any, g: Any) -> Iterator[ox.Quad]:
        return self._quads(s, p, o, None if g is ... else g)

    def quads(self, pattern: tuple = (None, None, None, None)) -> Iterator[ox.Quad]:
        """Quads matching ``(s, p, o[, graph])``; graph ``None`` is any graph (the default graph included)."""
        s, p, o = pattern[:3]
        g = terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else None
        return self._quads(s, p, o, g)

    def _serial_items(self, fmt: ox.RdfFormat) -> Iterable[Any]:
        if fmt in formats.QUAD_FORMATS:
            return self.store
        if next(self.store.quads_for_pattern(None, None, None, ox.DefaultGraph()), None) is not None and not any(True for _ in self.store.named_graphs()) \
                or len(self.store) == 0:
            return (ox.Triple(q.subject, q.predicate, q.object) for q in self.store)  # only the default graph has content
        # No multi-graph syntax in a triple format: flatten every graph into one, as the old class did. Which graph a triple
        # came from is not kept; a triple in several graphs is written once. Use trig or nquads to keep the graphs.
        seen: set[ox.Triple] = set()
        flat = []
        for q in self.store:
            t = ox.Triple(q.subject, q.predicate, q.object)
            if t not in seen:
                seen.add(t)
                flat.append(t)
        return flat

    def _pretty_source(self, fmt: ox.RdfFormat) -> Any:
        return self if fmt in formats.QUAD_FORMATS else list(self._serial_items(fmt))

    def named_graphs(self) -> Iterator[Any]:
        """The names of the named graphs of the store, empty ones included (``graphs()`` makes a graph object of each). Oxigraph's own form: ``ox.named_graphs()``."""
        return iter(self.store.named_graphs())

    def add_graph(self, identifier: Any) -> StarLayerDataset:
        """Create an empty named graph, so it is listed before it holds a triple. Oxigraph's own form: ``ox.add_graph(name)``."""
        self.store.add_graph(terms.graph_name(identifier))
        union.touch(self.store)
        return self

    def clear_graph(self, identifier: Any = None) -> StarLayerDataset:
        """Remove the triples of one graph (the default graph when ``identifier`` is None) and keep the graph; ``remove_graph`` drops it. Oxigraph's own form: ``ox.clear_graph(name)``."""
        self.store.clear_graph(terms.graph_name(identifier))
        union.touch(self.store)
        return self

    def remove_graph(self, identifier: Any) -> StarLayerDataset:
        """Remove a named graph with its triples (the default graph is emptied). ``ox.remove_graph(name)`` is Oxigraph's own form."""
        name = terms.graph_name(identifier)
        if isinstance(name, ox.DefaultGraph):
            self.store.clear_graph(name)
        else:
            self.store.remove_graph(name)
        union.touch(self.store)
        return self

    def remove(self, pattern: tuple) -> StarLayerDataset:
        """Remove every quad matching ``(s, p, o[, graph])`` (``None`` is a wildcard).

        Without a graph, a union dataset matches in every graph; otherwise only the default graph is searched."""
        s, p, o = pattern[:3]
        g = terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else self._pattern_graph()
        for q in list(self._quads(s, p, o, g)):
            self.store.remove(q)
        union.touch(self.store)
        return self

    @property
    def default_graph(self) -> StarLayerGraph:
        """The dataset's default graph as a ``StarLayerGraph`` (re-made on each access; it shares this dataset's ``prefixes``)."""
        return _sharing(StarLayerGraph(self.store), self.prefixes)

    def to_graph(self) -> StarLayerGraph:
        """Every triple of every graph merged into one new in-memory ``StarLayerGraph`` (provenance by graph is lost; equal triples
        collapse). It is a copy: it can be queried or compared on its own."""
        g = StarLayerGraph(prefixes=dict(self.prefixes))
        g.extend(ox.Triple(q.subject, q.predicate, q.object) for q in self.store)
        return g

    # The reifier methods keep provenance here: each returns a StarLayerDataset whose graphs hold the matching reifier triples, as the
    # old StarLayerDataset did (the ``reification.*`` functions on a dataset yield the flat terms).
    def _reifier_dataset(self, pick: Any) -> StarLayerDataset:
        result = StarLayerDataset(default_union=self._union, prefixes=dict(self.prefixes))
        for g in self.graphs():
            triples = list(pick(g))
            if triples:
                result.graph(g.identifier).extend(triples)
        return result

    def reifiers(self, tt: Any = None, predicate: Any = None, object: Any = None) -> StarLayerDataset:  # noqa: A002
        """A dataset of every matching reifier's triples (its ``rdf:reifies`` links and annotations), each kept in the graph it
        came from. ``list(reification.reifiers(ds))`` gives the reifier nodes alone."""
        return self._reifier_dataset(lambda g: (t for r in g.reifiers(tt, predicate, object) for t in g.triples((r, None, None))))

    def reified_triples(self, reifier: Any = None) -> StarLayerDataset:
        """A dataset of the ``reifier rdf:reifies <triple term>`` triples of ``reifier`` (of every reifier, with none), per graph."""
        def pick(g: Any) -> Any:
            if reifier is None:
                return ((r, terms.RDF_REIFIES, tt) for tt in g.reified_triples() for r in g.reifiers(tt))
            return ((terms.term(reifier), terms.RDF_REIFIES, tt) for tt in g.reified_triples(reifier))

        return self._reifier_dataset(pick)

    def annotations(self, tt: Any = None) -> StarLayerDataset:
        """A dataset of the annotation triples ``(reifier, predicate, value)`` of every reifier of ``tt`` (of any triple term, with none), per graph."""
        return self._reifier_dataset(lambda g: g.annotations(tt))

    # ---- graph management ---------------------------------------------------------------------------------------
    def graph(self, identifier: Any = None) -> StarLayerGraph:
        """One graph of the dataset as a ``StarLayerGraph`` (created, empty, if it does not exist yet); shares this dataset's ``prefixes`` dict."""
        name = terms.graph_name(identifier)
        if not isinstance(name, ox.DefaultGraph):
            self.store.add_graph(name)
        return _sharing(StarLayerGraph(self.store, identifier=name), self.prefixes)

    def graphs(self) -> list[StarLayerGraph]:
        """The default graph, then every named graph (empty ones included)."""
        return [self.graph(None), *(_sharing(StarLayerGraph(self.store, identifier=n), self.prefixes) for n in self.store.named_graphs())]

    def graph_names(self) -> list[Any]:
        """The names of the named graphs, empty ones included (the default graph is not listed)."""
        return list(self.store.named_graphs())

    def has_graph(self, identifier: Any) -> bool:
        """Whether ``identifier`` names a graph of the dataset; the default graph always exists."""
        name = terms.graph_name(identifier)
        return isinstance(name, ox.DefaultGraph) or name in set(self.store.named_graphs())

    def clear(self) -> StarLayerDataset:
        """Remove every quad and every named graph."""
        self.store.clear()
        union.touch(self.store)
        return self

    def _engine_graph_name(self, union: Any, default: Any) -> Any:
        return union if self._union else default

    def _sparql_view(self) -> Any:
        from starlayer.shacl.engine.oxigraph_view import DEFAULT, OxigraphGraph

        if self._merged():  # a triple in two graphs: its SPARQL runs on the merged copy, where it is one triple
            return OxigraphGraph(self._overlap.store(self.store), DEFAULT)
        return self.engine_view()

    def _query_default_graph(self) -> Any:
        return None

    def _combine(self, fn: Any, other: StarLayerDataset) -> StarLayerDataset:
        return StarLayerDataset(store=fn(self.store, other.store), default_union=self._union)

    def copy(self) -> StarLayerDataset:
        """An independent in-memory copy of this dataset, including empty named graphs, prefixes and ``default_union``."""
        d = StarLayerDataset(default_union=self._union)
        d.store.extend(self.store)
        for name in self.store.named_graphs():  # empty named graphs have no quad to carry them
            d.store.add_graph(name)
        d.prefixes.clear()
        d.prefixes.update(self.prefixes)
        return d

    def __reduce__(self) -> Any:
        """Pickle: every quad, the named graphs (also empty ones), ``default_union`` and the prefixes. A dataset opened with
        ``path=`` is refused (``TypeError``), see ``_refuse_path_pickle``."""
        self._refuse_path_pickle()
        return (_rebuild_dataset, (self._union, dict(self.prefixes), list(self.store), list(self.store.named_graphs())))

    def __repr__(self) -> str:
        """A short form with the quad count."""
        return f"<StarLayerDataset ({len(self.store)} quads)>"


def _rebuild_graph(identifier: Any, prefixes: dict[str, str], quads: list[ox.Quad]) -> StarLayerGraph:
    g = StarLayerGraph(identifier=identifier, prefixes=prefixes)
    g.store.extend(quads)
    return g


def _rebuild_dataset(default_union: bool, prefixes: dict[str, str], quads: list[ox.Quad], names: list[Any]) -> StarLayerDataset:
    d = StarLayerDataset(default_union=default_union, prefixes=prefixes)
    d.store.extend(quads)
    for name in names:
        d.store.add_graph(name)
    return d
