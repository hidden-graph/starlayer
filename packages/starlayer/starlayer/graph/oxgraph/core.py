"""``OxGraph`` (one graph of a store) and ``OxDataset`` (the whole store): composition wrappers over a ``pyoxigraph.Store``.

Terms are pyoxigraph terms. rdflib is not imported here; a caller may still pass rdflib / StarLayer terms, which are converted
on the way in (see ``terms.term``). Names are working names, to become ``StarLayerGraph`` / ``StarLayerDataset`` at the switch.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pyoxigraph as ox

from starlayer.graph.backends._versions import require_supported_pyoxigraph
from starlayer.graph.oxgraph import config, formats, run, terms
from starlayer.graph.oxgraph.result import Result

require_supported_pyoxigraph()

_ABSOLUTE_IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")
_TURTLE_LIKE = (ox.RdfFormat.TURTLE, ox.RdfFormat.TRIG)


def as_store(x: Any) -> ox.Store:
    """The ``pyoxigraph.Store`` behind a wrapper, an ``OxigraphGraph`` view, or a bare store."""
    if isinstance(x, ox.Store):
        return x
    s = getattr(x, "store", None)
    if isinstance(s, ox.Store):
        return s
    raise TypeError(f"expected an OxGraph, OxDataset or pyoxigraph.Store, not {type(x).__name__}")


_IRI_OR_STRING = re.compile(
    r'"""(?:[^"\\]|\\.|"(?!""))*"""'  # long strings first
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


def _no_backend(backend: Any) -> None:
    if backend is not None:
        raise TypeError(
            f"backend={backend!r} is not an option of the Oxigraph wrapper: it is always an Oxigraph store speaking RDF 1.2. "
            "Choose the storage with store= (a pyoxigraph.Store) or path= (an on-disk store); for a remote SPARQL endpoint use "
            "the HTTP functions of starlayer.graph.backends.native (http_select, http_update, ...)"
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
        return {"path": text}, text
    raise TypeError(f"cannot read RDF from {type(obj).__name__}")


class _Base:
    """What the graph view and the dataset share. Subclasses define ``_pattern_graph`` and ``_union``."""

    #: the engine's term model is pyoxigraph's (``shacl_engine`` reads these)
    engine_terms = True
    preserves_lexical_forms = False
    native_sparql = True

    store: ox.Store
    prefixes: dict[str, str]

    # ---- construction ------------------------------------------------------------------------------------------
    def _init_store(self, store: Any, path: Any, prefixes: dict[str, str] | None) -> None:
        if store is not None and path is not None:
            raise ValueError("give a store or a path, not both")
        self.store = as_store(store) if store is not None else ox.Store(os.fspath(path) if path is not None else None)
        self.prefixes = prefixes if prefixes is not None else config.new_prefix_dict()

    def as_store(self) -> ox.Store:
        return self.store

    # ---- StarLayer helpers (thin delegates; the code lives in oxgraph/helpers/) -------------------------------------
    def infer(self, entailment: Any = None, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import entailment as m
        return m.infer(self, m.ENTAILMENT.RDFS if entailment is None else entailment, **kw)

    def derive_shape(self, *a: Any, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import shapes
        return shapes.derive_shape(self, *a, **kw)

    def owl_imports(self) -> tuple[Any, ...]:
        from starlayer.graph.oxgraph.helpers import imports
        return imports.owl_imports(self)

    def has_import_locally(self, iri: Any) -> bool:
        from starlayer.graph.oxgraph.helpers import imports
        return imports.has_import_locally(self, iri)

    def resolve_imports(self, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import imports
        return imports.resolve_imports(self, **kw)

    def skolemize(self, *a: Any, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import rewrite
        return rewrite.skolemize(self, *a, **kw)

    def de_skolemize(self, *a: Any, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import rewrite
        return rewrite.de_skolemize(self, *a, **kw)

    def cbd(self, resource: Any, **kw: Any) -> Any:
        from starlayer.graph.oxgraph.helpers import rewrite
        return rewrite.cbd(self, resource, **kw)

    def empty_like(self) -> Any:
        from starlayer.graph.oxgraph.helpers import rewrite
        return rewrite.empty_like(self)

    def qname(self, uri: Any) -> str:
        from starlayer.graph.oxgraph.helpers import qnames
        return qnames.qname(self.prefixes, uri)

    def compute_qname(self, uri: Any, generate: bool = True) -> tuple[str, str, str]:
        from starlayer.graph.oxgraph.helpers import qnames
        return qnames.compute_qname(self.prefixes, uri, generate)

    def expand_curie(self, curie: str) -> Any:
        from starlayer.graph.oxgraph.helpers import qnames
        return qnames.expand_curie(self.prefixes, curie)

    def qname_term(self, term: Any) -> str:
        """The prefixed N3 form of any term (IRI, blank node, literal, triple term) using this graph's prefixes; an IRI with no
        fitting prefix is ``<iri>``. pyoxigraph terms have no ``n3()``: this replaces ``term.n3(namespace_manager)``, and
        ``str(term)`` replaces ``term.n3()``."""
        from starlayer.graph.oxgraph.helpers import qnames
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
        pat = terms.in_pattern(s, p, o)
        if pat is None:
            return iter(())
        return self.store.quads_for_pattern(*pat, self._pattern_graph() if g is ... else g)

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
        """Quads matching ``(s, p, o)`` or ``(s, p, o, graph)``; ``None`` is a wildcard. On a graph view the graph is fixed."""
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
        return sum(1 for _ in self._quads(None, None, None))

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, (ox.Triple, ox.Quad)):
            item = tuple(item)
        if len(item) == 4:  # a graph view contains nothing of another graph (``_quads_in`` is empty for a foreign graph)
            return next(self._quads_in(*item[:3], terms.graph_name(item[3])), None) is not None
        return next(self._quads(*item), None) is not None

    def objects(self, subject: Any = None, predicate: Any = None, unique: bool = False) -> Iterator[Any]:
        seen: set | None = set() if (unique or self._union) else None
        for q in self._quads(subject, predicate, None):
            if seen is not None:
                if q.object in seen:
                    continue
                seen.add(q.object)
            yield q.object

    def subjects(self, predicate: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:
        seen: set | None = set() if (unique or self._union) else None
        for q in self._quads(None, predicate, object):
            if seen is not None:
                if q.subject in seen:
                    continue
                seen.add(q.subject)
            yield q.subject

    def predicates(self, subject: Any = None, object: Any = None, unique: bool = False) -> Iterator[Any]:
        seen: set | None = set() if (unique or self._union) else None
        for q in self._quads(subject, None, object):
            if seen is not None:
                if q.predicate in seen:
                    continue
                seen.add(q.predicate)
            yield q.predicate

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
        ``rdf:first`` or with several ``rdf:first`` / ``rdf:rest`` raises ``ValueError``."""
        head = terms.term(head)
        seen: set = set()
        while head != terms.RDF_NIL:
            if head in seen:
                raise ValueError(f"cycle in the RDF list at {head}")
            seen.add(head)
            firsts = list(self.objects(head, terms.RDF_FIRST, unique=True))
            rests = list(self.objects(head, terms.RDF_REST, unique=True))
            if len(firsts) != 1 or len(rests) != 1:
                raise ValueError(f"{head} is not a well-formed list node ({len(firsts)} rdf:first, {len(rests)} rdf:rest)")
            yield firsts[0]
            head = rests[0]

    # ---- writing ------------------------------------------------------------------------------------------------
    def _quad(self, triple: Any, g: Any, strict: bool = True) -> ox.Quad:
        """The quad for a triple (into graph ``g``) or a quad. With ``strict`` a quad that is not in this graph (a view of
        another graph) raises ``ValueError``: a view never writes outside itself."""
        if isinstance(triple, ox.Quad):
            q = triple
        elif len(triple) == 4:
            q = ox.Quad(*(terms.term(t) for t in triple[:3]), terms.graph_name(triple[3]))
        else:
            s, p, o = triple
            return ox.Quad(terms.term(s), terms.term(p), terms.term(o), g)
        if strict and not self._accepts(q):
            raise ValueError(f"this is a view of graph {self._add_graph()}; it cannot add a quad of graph {q.graph_name}")
        return q

    def add(self, triple: Any) -> Any:
        self.store.add(self._quad(triple, self._add_graph()))
        return self

    def extend(self, triples: Iterable[Any]) -> Any:
        """Add many triples (or quads on a dataset) in one transaction."""
        g = self._add_graph()
        self.store.extend(self._quad(t, g) for t in triples)
        return self

    def addN(self, quads: Iterable[Any]) -> Any:  # noqa: N802
        """rdflib's name: add ``(s, p, o, graph)`` quads. On a graph view only quads for this graph are added."""
        self.store.extend(q for q in (self._quad(q, self._add_graph(), False) for q in quads) if self._accepts(q))
        return self

    def _accepts(self, quad: ox.Quad) -> bool:
        return True

    def remove(self, pattern: tuple[Any, Any, Any]) -> Any:
        """Remove every statement matching the pattern (``None`` is a wildcard), as rdflib's ``remove`` does. On a graph view a
        pattern naming another graph matches nothing and removes nothing (it never reaches into the other graph)."""
        doomed = list(self._quads_in(*pattern[:3], terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else ...))
        for q in doomed:
            self.store.remove(q)
        return self

    # ---- parse / serialize --------------------------------------------------------------------------------------
    def parse(self, source: Any = None, format: str | None = None, *, data: Any = None, file: Any = None,  # noqa: A002
              base: str | None = None, publicID: str | None = None, rename_blank_nodes: bool = True) -> Any:  # noqa: N803
        """Parse a document into this graph. ``source`` is a path, URL or file object; or give ``data=`` (str / bytes) or
        ``file=``. ``format`` is a name (``formats.py``) or an ``RdfFormat``; omitted it is guessed from the file name, else
        Turtle. Blank nodes are scoped to the document (renamed per parse unless ``rename_blank_nodes=False``). The prefixes the
        document declares are copied into ``self.prefixes``. A triple format loads into the default graph of a dataset or into
        this graph; a quad format loads each quad into its graph, and into a single graph view only if it has no named graphs."""
        kw, hint = _read_input(data, source, file)
        if formats.is_manchester(format) or (format is None and hint and str(hint).lower().endswith((".omn", ".manchester"))):
            return self._parse_manchester(kw, hint, base or publicID)
        guessed = formats.format_from_path(hint) if hint else None
        fmt = formats.to_format(format, default=guessed or ox.RdfFormat.TURTLE)
        direct = isinstance(self._add_graph(), ox.DefaultGraph)  # quads can go to the store untouched (the fast path)
        extra = {"without_named_graphs": True} if (direct and not isinstance(self, OxDataset)) else {}
        parser = ox.parse(format=fmt, base_iri=base or publicID, rename_blank_nodes=rename_blank_nodes, **extra, **kw)
        try:
            if direct:
                self.store.extend(parser)
            else:
                move = self._retarget(self._add_graph())
                self.store.extend(move(q) for q in parser)
        except SyntaxError as e:
            if "named graph" in str(e).lower():
                raise ValueError("the document has named graphs; parse it into an OxDataset") from e
            raise
        self.prefixes.update(parser.prefixes or {})
        return self

    _default_format = "turtle"

    def _parse_manchester(self, kw: dict[str, Any], hint: str | None, base: str | None) -> Any:
        """OWL 2 Manchester Syntax: the parser (``parsers/manchester_parser.py``) is independent of the store and builds the
        triples, which are added here. It has no named graphs, so a dataset gets them in its default graph."""
        from starlayer.graph.parsers.manchester_parser import parse_manchester

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
                  encoding: str = "utf-8", pretty: bool | str = False) -> str | None:
        """Write the graph. ``destination`` None returns a ``str``; a path or file object is written and ``None`` returned.
        Prefixes are the graph's dict plus ``prefixes`` (the per-call override); ``only_used=True`` declares only those the
        output uses (Turtle, TriG). ``rdf_version="1.1"`` exports through ``starlayer.graph.interop`` (the basic encoding of
        triple terms), so the output contains no triple term. ``pretty=True`` lays Turtle / TriG out with
        ``oxgraph.pretty`` (nested blank nodes, lists, annotations; see that module)."""
        if formats.is_manchester(format):
            from starlayer.graph.oxgraph import _rdflib_bridge
            from starlayer.graph.serializers.manchester import serialize_manchester

            return self._write(serialize_manchester(_rdflib_bridge.to_starlayer_graph(self)).encode("utf-8"), destination, encoding)
        fmt = formats.to_format(format or self._default_format)
        if rdf_version not in (None, "1.1", "rdf-1.1", "1.2", "rdf-1.2"):
            raise ValueError(f"unknown rdf_version {rdf_version!r}")
        pfx = {**self.prefixes, **{str(k): str(v) for k, v in (prefixes or {}).items()}}
        items = self._serial_items(fmt)
        if pretty:  # pretty Turtle / TriG (RDF 1.2): oxgraph/pretty.py
            from starlayer.graph.oxgraph.pretty import serialize_pretty

            source = self._pretty_source(fmt)
            if rdf_version in ("1.1", "rdf-1.1"):  # pretty-print the basic encoding, so the output has no triple term either
                from starlayer.graph import interop

                source = interop.encode_directions(interop.to_basic(self._serial_items(fmt)))
            raw = serialize_pretty(source, fmt, pfx or None, base, only_used, pretty).encode("utf-8")
        elif rdf_version in ("1.1", "rdf-1.1"):
            # Triple terms by the Interoperability draft's basic encoding, base-direction literals by the interop
            # policy (a datatype IRI form by default); the result contains neither.
            from starlayer.graph import interop

            raw = interop.export_rdf11(items, fmt, None, pfx or None, base)
        else:
            raw = ox.serialize(items, None, fmt, prefixes=pfx or None, base_iri=base)
        if only_used and fmt in _TURTLE_LIKE and pfx:
            raw = _strip_unused_prefixes(raw.decode("utf-8")).encode("utf-8")
        return self._write(raw, destination, encoding)

    @staticmethod
    def _write(raw: bytes, destination: Any, encoding: str) -> str | None:
        if destination is None:
            return raw.decode("utf-8")
        if isinstance(destination, (str, os.PathLike)):
            with open(destination, "wb") as fh:
                fh.write(raw)
        else:
            try:
                destination.write(raw)
            except TypeError:
                destination.write(raw.decode(encoding))
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
        from starlayer.graph.oxgraph.pretty import _IRI_BAD, _PN_PREFIX

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
        fmt = ox.RdfFormat.TRIG if isinstance(self, OxDataset) else ox.RdfFormat.TURTLE
        text = _strip_unused_prefixes(ox.serialize(self._serial_items(fmt), None, fmt, prefixes=self.prefixes).decode("utf-8"))
        import re

        out = {m.group(1): m.group(2) for m in re.finditer(r"(?m)^@prefix ([^\s:]*): <([^>]*)> \.$", text)}
        return sorted(out.items())

    # ---- SPARQL -------------------------------------------------------------------------------------------------
    def query(self, text: str, initNs: Mapping[str, str] | None = None, initBindings: Mapping[Any, Any] | None = None,  # noqa: N803
              base: str | None = None, *, entailment: Any = None) -> Result:
        """Run SPARQL ``text`` on Oxigraph as it is. ``initNs`` overrides the graph's prefixes for this call; ``initBindings``
        pre-binds variables (``substitutions``, with the ``VALUES`` fallback). A graph view queries its own graph as the default
        graph; a dataset the default graph, or the union of all graphs when ``default_union``."""
        if entailment is not None:
            raise NotImplementedError("query-time entailment is not built in the Oxigraph wrapper (see docs/working/oxgraph-wrapper.md)")
        return run.query(self.store, text, prefixes=self.prefixes, init_ns=initNs, init_bindings=initBindings, base=base,
                         default_graph=self._query_default_graph(), union=self._union)

    def _query_default_graph(self) -> Any:
        return None

    def update(self, text: str, initNs: Mapping[str, str] | None = None, base: str | None = None) -> None:  # noqa: N803
        """Run SPARQL Update ``text`` on the store. It acts on the whole store, also from a named-graph view (use ``WITH <g>``
        or ``GRAPH`` in the text to aim it). On a ``default_union`` dataset the ``WHERE`` of an ``INSERT`` / ``DELETE`` operation
        reads the union of all graphs, as ``query()`` does (done by adding ``USING`` clauses; see
        ``run.union_update_text`` for how, and its limits)."""
        run.update(self.store, text, prefixes=self.prefixes, init_ns=initNs, base=base, union=self._union)

    # ---- RDF 1.2 reifiers (thin functions in reification.py) -----------------------------------------------------
    def add_reification(self, reifier: Any, triple_term: Any) -> Any:
        from starlayer.graph.oxgraph import reification

        return reification.add_reification(self, reifier, triple_term)

    def reifiers(self, TT: Any = None, predicate: Any = None, object: Any = None) -> Iterator[Any]:  # noqa: N803, A002
        from starlayer.graph.oxgraph import reification

        return reification.reifiers(self, TT, predicate, object)

    def reifications(self, s: Any = None, p: Any = None, o: Any = None) -> Iterator[ox.Triple]:
        from starlayer.graph.oxgraph import reification

        return reification.reifications(self, s, p, o)

    def reifier_annotations(self, TT: Any) -> Iterator[tuple[Any, Any, Any]]:  # noqa: N803
        from starlayer.graph.oxgraph import reification

        return reification.reifier_annotations(self, TT)

    def reified_triples(self, reifier: Any) -> Iterator[ox.Triple]:
        from starlayer.graph.oxgraph import reification

        return reification.reified_triples(self, reifier)

    def remove_reification(self, reifier: Any, triple_term: Any = None) -> Any:
        from starlayer.graph.oxgraph import reification

        return reification.remove_reification(self, reifier, triple_term)

    def triple_terms(self, subject: Any = None, predicate: Any = None, object: Any = None) -> Iterator[ox.Triple]:  # noqa: A002
        from starlayer.graph.oxgraph import reification

        return reification.triple_terms(self, subject, predicate, object)

    def has_triple_term(self, subject: Any, predicate: Any, object: Any) -> bool:  # noqa: A002
        from starlayer.graph.oxgraph import reification

        return reification.has_triple_term(self, subject, predicate, object)

    # ---- the shacl_engine's graph view -------------------------------------------------------------------------
    def engine_view(self) -> Any:
        from starlayer.shacl_engine.oxigraph_view import DEFAULT, UNION, OxigraphGraph

        return OxigraphGraph(self.store, self._engine_graph_name(UNION, DEFAULT))

    def sparql_query(self, text: str, init_bindings: Mapping[str, Any] | None = None) -> Any:
        """The engine's ``SparqlCapable`` hook."""
        return self.engine_view().sparql_query(text, init_bindings)

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
        self.extend(other.quads() if isinstance(self, OxDataset) else other.triples())
        return self

    def _combine(self, fn: Any, other: Any) -> Any:
        raise NotImplementedError

    def copy(self) -> Any:
        """An in-memory copy (new store) with a copy of the prefixes."""
        raise NotImplementedError

    __hash__ = object.__hash__

    def __eq__(self, other: Any) -> bool:
        return self is other


class OxGraph(_Base):
    """One graph of a store: the default graph (``identifier=None``) or the named graph ``identifier`` (a ``NamedNode``,
    ``BlankNode``, or an IRI string)."""

    def __init__(self, store: Any = None, path: Any = None, identifier: Any = None, *, prefixes: dict[str, str] | None = None,
                 backend: str | None = None) -> None:
        _no_backend(backend)
        self._init_store(store, path, prefixes)
        self._g = terms.graph_name(identifier)

    @property
    def identifier(self) -> Any:
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
                raise ValueError("the document has named graphs; parse it into an OxDataset")
            return ox.Quad(q.subject, q.predicate, q.object, target)

        return move

    def _serial_items(self, fmt: ox.RdfFormat) -> Iterable[Any]:
        if fmt in formats.QUAD_FORMATS:
            return self._quads(None, None, None)
        return (ox.Triple(q.subject, q.predicate, q.object) for q in self._quads(None, None, None))

    def _query_default_graph(self) -> Any:
        return self._g

    def _engine_graph_name(self, union: Any, default: Any) -> Any:
        return default if isinstance(self._g, ox.DefaultGraph) else self._g

    def clear(self) -> OxGraph:
        self.store.clear_graph(self._g)
        return self

    def _combine(self, fn: Any, other: OxGraph) -> OxGraph:
        a, b = ox.Store(), ox.Store()
        a.extend(ox.Quad(*t, ox.DefaultGraph()) for t in self.triples())
        b.extend(ox.Quad(*t, ox.DefaultGraph()) for t in other.triples())
        return OxGraph(store=fn(a, b))

    def copy(self) -> OxGraph:
        g = OxGraph()
        g.extend(self.triples())
        g.prefixes.clear()
        g.prefixes.update(self.prefixes)
        return g

    def __repr__(self) -> str:
        return f"<OxGraph {self._g} ({len(self)} triples)>"


class OxDataset(_Base):
    """The whole store. ``default_union`` (default True) makes ``triples`` / ``len`` / ``iter`` / SPARQL's default graph the
    union of all graphs, as the engine's graph view does; False restricts them to the default graph (rdflib's ``Dataset``)."""

    _default_format = "trig"  # a dataset writes its graphs unless asked for a triple format

    def __init__(self, store: Any = None, path: Any = None, default_union: bool = True, *, prefixes: dict[str, str] | None = None,
                 backend: str | None = None) -> None:
        _no_backend(backend)
        self._init_store(store, path, prefixes)
        self._union = default_union

    @property
    def default_union(self) -> bool:
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

    def remove(self, pattern: tuple) -> OxDataset:
        s, p, o = pattern[:3]
        g = terms.graph_name(pattern[3]) if len(pattern) > 3 and pattern[3] is not None else self._pattern_graph()
        for q in list(self._quads(s, p, o, g)):
            self.store.remove(q)
        return self

    @property
    def default_graph(self) -> OxGraph:
        """A view of the dataset's default graph (re-made on each access; it shares this dataset's ``prefixes``)."""
        return OxGraph(self.store, prefixes=self.prefixes)

    def to_graph(self) -> OxGraph:
        """Every triple of every graph merged into one new in-memory ``OxGraph`` (provenance by graph is lost; equal triples
        collapse). It is a copy: it can be queried or compared on its own."""
        g = OxGraph(prefixes=dict(self.prefixes))
        g.extend(ox.Triple(q.subject, q.predicate, q.object) for q in self.store)
        return g

    # The four plural reifier methods keep provenance: each returns an OxDataset whose graphs hold the matching
    # reifier triples, as the old StarLayerDataset did (the ``reification.*`` functions on a dataset yield the flat terms).
    def _reifier_dataset(self, pick: Any) -> OxDataset:
        result = OxDataset(default_union=self._union, prefixes=dict(self.prefixes))
        for g in self.graphs():
            triples = list(pick(g))
            if triples:
                result.graph(g.identifier).extend(triples)
        return result

    def reifiers(self, TT: Any = None, predicate: Any = None, object: Any = None) -> OxDataset:  # noqa: N803, A002
        """A dataset of every matching reifier's triples (its ``rdf:reifies`` links and annotations), each kept in the graph it
        came from. ``list(reification.reifiers(ds))`` gives the reifier nodes alone."""
        return self._reifier_dataset(lambda g: (t for r in g.reifiers(TT, predicate, object) for t in g.triples((r, None, None))))

    def reifications(self, s: Any = None, p: Any = None, o: Any = None) -> OxDataset:
        """A dataset of the ``rdf:reifies`` triples of every reified triple term matching ``s p o``, per graph."""
        return self._reifier_dataset(lambda g: ((r, terms.RDF_REIFIES, tt) for tt in g.reifications(s, p, o) for r in g.reifiers(tt)))

    def reifier_annotations(self, TT: Any) -> OxDataset:  # noqa: N803
        """A dataset of the annotation triples ``(reifier, predicate, value)`` of every reifier of ``TT``, per graph."""
        return self._reifier_dataset(lambda g: g.reifier_annotations(TT))

    def reified_triples(self, reifier: Any) -> OxDataset:
        """A dataset of the ``reifier rdf:reifies <triple term>`` triples of ``reifier``, per graph."""
        return self._reifier_dataset(lambda g: ((terms.term(reifier), terms.RDF_REIFIES, tt) for tt in g.reified_triples(reifier)))

    # ---- graph management ---------------------------------------------------------------------------------------
    def graph(self, identifier: Any = None) -> OxGraph:
        """A view of one graph (created, empty, if it does not exist yet); shares this dataset's ``prefixes`` dict."""
        name = terms.graph_name(identifier)
        if not isinstance(name, ox.DefaultGraph):
            self.store.add_graph(name)
        return OxGraph(self.store, identifier=name, prefixes=self.prefixes)

    def graphs(self) -> list[OxGraph]:
        """The default graph, then every named graph (empty ones included)."""
        return [self.graph(None), *(OxGraph(self.store, identifier=n, prefixes=self.prefixes) for n in self.store.named_graphs())]

    def graph_names(self) -> list[Any]:
        return list(self.store.named_graphs())

    def has_graph(self, identifier: Any) -> bool:
        name = terms.graph_name(identifier)
        return isinstance(name, ox.DefaultGraph) or name in set(self.store.named_graphs())

    def remove_graph(self, identifier: Any) -> OxDataset:
        """Remove a named graph with its triples (the default graph is emptied)."""
        name = terms.graph_name(identifier)
        if isinstance(name, ox.DefaultGraph):
            self.store.clear_graph(name)
        else:
            self.store.remove_graph(name)
        return self

    def clear(self) -> OxDataset:
        self.store.clear()
        return self

    def _engine_graph_name(self, union: Any, default: Any) -> Any:
        return union if self._union else default

    def _query_default_graph(self) -> Any:
        return None

    def _combine(self, fn: Any, other: OxDataset) -> OxDataset:
        return OxDataset(store=fn(self.store, other.store), default_union=self._union)

    def copy(self) -> OxDataset:
        d = OxDataset(default_union=self._union)
        d.store.extend(self.store)
        for name in self.store.named_graphs():  # empty named graphs have no quad to carry them
            d.store.add_graph(name)
        d.prefixes.clear()
        d.prefixes.update(self.prefixes)
        return d

    def __repr__(self) -> str:
        return f"<OxDataset ({len(self.store)} quads)>"
