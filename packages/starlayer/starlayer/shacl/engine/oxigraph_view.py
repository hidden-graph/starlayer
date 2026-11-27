"""``OxigraphGraph``: a ``GraphView`` straight over a ``pyoxigraph.Store`` (no rdflib graph in between).

Terms handed to and from the engine are pyoxigraph terms (``engine_terms = True``): the view returns the store's terms
as they are, with no conversion. ``to_ox`` converts the tuples a caller passes in (graph names, ``add``, pre-bindings).

Known, parked limitations (oxigraph/oxigraph#526): Oxigraph normalizes literals on storage ("04"^^xsd:integer becomes
"4", "1"^^xsd:boolean becomes "true", some ill-formed literals are rewritten or dropped), so ``preserves_lexical_forms``
is False. Oxigraph also reports ``"x"`` and ``"x"^^xsd:string`` as the same term.

Graph selection: ``graph_name=UNION`` (the default) reads the union of all graphs, de-duplicating triples that occur in
several graphs; ``graph_name=DEFAULT`` reads the default graph; an IRI/blank node reads that named graph.

``query``: SPARQL runs natively through ``Store.query``. Pre-bound variables use pyoxigraph's ``substitutions``
(RDF-dev SEP-0007). Limitation of the library: a substituted variable must appear in a SELECT projection (use
``SELECT *`` or project it); ASK and CONSTRUCT have no such restriction.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyoxigraph as ox

from starlayer.graph import lexical
from starlayer.graph._detached import detached
from starlayer.shacl.engine.terms import (
    to_engine,
)

UNION = object()
DEFAULT = object()



# Terms handed to and from the engine are pyoxigraph terms: the view returns store terms as they are. ``to_ox``
# converts the tuples a caller may pass (graph names, ``add``, pre-bindings); rdflib terms are refused.
to_ox = to_engine


_WORD = re.compile(r"[A-Za-z_]+")
_SELECT_NEXT = re.compile(r"(?:\s|#[^\n]*\n)*SELECT\b", re.I)


_BLANKS = re.compile(r"(?:\s|#[^\n]*\n)*")


def _close_brace(text: str, k: int) -> int:
    """The index of the ``}`` that closes the ``{`` at ``text[k]`` (strings, IRIs and comments skipped); ``len(text)`` if none."""
    from starlayer.graph.execution.run import _IRI_AT, _STRING_AT

    depth, i, n = 0, k, len(text)
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        m = _STRING_AT.match(text, i) if c in "\"'" else _IRI_AT.match(text, i) if c == "<" else None
        if m is not None:
            i = m.end()
            continue
        depth += (c == "{") - (c == "}")
        if depth == 0:
            return i
        i += 1
    return n


def inject_everywhere(text: str, values: str, *, skip_exists: bool = False) -> str:
    """``text`` with the ``values`` clause (``VALUES (?x) { (t) }``) put at the start of every group graph pattern, so a pre-bound
    variable is bound inside nested groups too, as SHACL 1.2 SPARQL Appendix A defines pre-binding (Oxigraph's ``substitutions``
    do not reach a group that holds only a ``FILTER``). Not in a sub-select's opening brace, a ``VALUES`` data block, a
    ``CONSTRUCT`` template or a ``{|`` annotation block. ``CONSTRUCT WHERE { P }`` is first written out as
    ``CONSTRUCT { P } WHERE { VALUES ... P }``. Strings, IRIs and comments are skipped.

    ``skip_exists``: leave the groups inside ``EXISTS { }`` and ``NOT EXISTS { }`` alone. They are evaluated with the solution they are
    asked about substituted in, which binds the variable already, so the clause adds nothing there for one row; with a clause of many rows
    (``sparql_query_batch``) it would be joined for each solution, and the work grows with the square of the rows."""
    from starlayer.graph.execution.run import _IRI_AT, _STRING_AT

    out: list[str] = []
    i, n = 0, len(text)
    after_values = construct = False
    exists_at, exists_depth = -1, 0  # where the ``{`` that opens an EXISTS operand is; how many braces deep inside one
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(text[i:j])
            i = j
            continue
        m = _STRING_AT.match(text, i) if c in "\"'" else _IRI_AT.match(text, i) if c == "<" else None
        if m is not None:
            out.append(m.group(0))
            i = m.end()
            continue
        if c.isalpha() or c == "_":
            w = _WORD.match(text, i)
            word = w.group(0) if w else c
            j = i + len(word)
            upper = word.upper()
            before, after = text[i - 1 : i] if i else "", text[j : j + 1]
            # a keyword is a whole word: not part of a prefixed name or a variable (``ex:has-values``, ``?values``, ``a1values``)
            if not (before.isalnum() or before in ("?", "$", ":", "_", "-")) and not (after.isalnum() or after in ("_", "-", ":")):
                if upper == "VALUES":
                    after_values = True
                elif upper == "EXISTS" and skip_exists:
                    exists_at = _BLANKS.match(text, j).end()
                elif upper == "CONSTRUCT":
                    construct = True
                elif upper == "WHERE" and construct:
                    construct = False
                    k = _BLANKS.match(text, j).end()
                    if text[k : k + 1] == "{":  # the short form: the pattern is also the template
                        end = _close_brace(text, k)
                        body = text[k + 1 : end]
                        out.append("{" + body + "} WHERE { " + values + " " + body + "}")
                        i = end + 1
                        continue
            out.append(text[i:j])
            i = j
            continue
        out.append(c)
        i += 1
        if c == "}" and exists_depth:
            exists_depth -= 1
        if c == "{" and (exists_depth or i - 1 == exists_at):
            exists_depth += 1  # inside an EXISTS operand: nothing is added to it or to any group nested in it
            after_values = False
            continue
        if c == "{":
            skip = after_values or construct or text[i : i + 1] == "|" or _SELECT_NEXT.match(text, i) is not None
            if after_values:
                after_values = False
            elif construct:
                construct = False
            if not skip:
                out.append(" " + values + " ")
    return "".join(out)


class OxigraphGraph:
    """A ``GraphView`` and ``SparqlCapable`` data graph over a ``pyoxigraph.Store``, returning the store's own terms."""

    engine_terms = True
    preserves_lexical_forms = False
    native_sparql = True

    def __init__(self, store: ox.Store | None = None, graph_name: Any = UNION) -> None:
        """Wrap a store, creating an empty one if none is given.

        Args:
            graph_name: ``UNION`` (default) reads every graph, ``DEFAULT`` the default graph only, any other value that named graph.
        """
        self.store = store if store is not None else ox.Store()
        from starlayer.graph.execution import union

        self._overlap = union.Overlap()
        self._version = union.version_of(self.store)  # holds the count of literals loaded in another form (graph/lexical.py) as long as this view lives
        self.graph_name = graph_name
        if graph_name is UNION:
            self._graph = None
        elif graph_name is DEFAULT:
            self._graph = ox.DefaultGraph()
        else:
            self._graph = to_ox(graph_name)

    # ---- constructors -------------------------------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path, *, graph_name: Any = UNION, base_iri: str | None = None) -> OxigraphGraph:
        """Load a Turtle / TriG / N-Triples / N-Quads file (by extension). A triple-only format goes to the default
        graph, or to ``graph_name`` when that is a named graph."""
        path = Path(path)
        fmt = ox.RdfFormat.from_extension(path.suffix.lstrip(".")) or ox.RdfFormat.TURTLE
        target = graph_name if graph_name not in (UNION, DEFAULT) else None
        store = ox.Store()
        store.load(path=os.fspath(path), format=fmt, base_iri=base_iri, to_graph=to_ox(target))
        graph = cls(store, graph_name)
        lexical.report(ox.parse(path=os.fspath(path), format=fmt, base_iri=base_iri), store)  # a second read of the file, to see what the store rewrote
        return graph

    @classmethod
    def from_text(
        cls, text: str, *, format: str = "turtle", graph_name: Any = UNION, base_iri: str | None = None
    ) -> OxigraphGraph:
        """Build a graph from RDF text, loading into the default graph or into ``graph_name`` when that is a named graph.

        Args:
            format: ``"turtle"``, ``"trig"`` or ``"nt"``.
        """
        fmt = {"turtle": ox.RdfFormat.TURTLE, "trig": ox.RdfFormat.TRIG, "nt": ox.RdfFormat.N_TRIPLES}[format]
        target = graph_name if graph_name not in (UNION, DEFAULT) else None
        store = ox.Store()
        store.load(text.encode(), format=fmt, base_iri=base_iri, to_graph=to_ox(target))
        graph = cls(store, graph_name)
        lexical.report(ox.parse(text.encode(), format=fmt, base_iri=base_iri), store)  # a second read of the text, to see what the store rewrote
        return graph

    @classmethod
    def from_graph(cls, graph: Any, *, graph_name: Any = UNION) -> OxigraphGraph:
        """Copy the triples of an Oxigraph-backed graph (anything with ``.triples((None, None, None))`` that yields pyoxigraph terms) in."""
        store = ox.Store()
        target = ox.DefaultGraph() if graph_name in (UNION, DEFAULT) else to_ox(graph_name)
        store.bulk_extend(
            ox.Quad(s, p, o, target) for s, p, o in graph.triples((None, None, None))
        )
        return cls(store, graph_name)

    def add(self, triple: tuple[Any, Any, Any]) -> None:
        """Add a triple to the selected graph (the default graph when reading the union)."""
        g = ox.DefaultGraph() if self._graph is None else self._graph
        rewrites = lexical.Rewrites()
        self.store.add(next(iter(lexical.watch((ox.Quad(*(to_ox(t) for t in triple), g),), rewrites))))
        rewrites.emit(self.store)
        from starlayer.graph.execution import union

        union.touch(self.store)  # a dataset over this store drops its deduplicated copy

    # ---- GraphView ----------------------------------------------------------------------------------------------
    def _quads(self, s: Any, p: Any, o: Any) -> Iterator[ox.Quad]:
        return detached(self._raw_quads(s, p, o))  # (an unexhausted reader must not hold a thread-bound store iterator)

    def _raw_quads(self, s: Any, p: Any, o: Any) -> Iterator[ox.Quad]:
        # Oxigraph raises on a literal / triple term subject or a non-IRI predicate; RDF graphs simply have no match.
        s, p, o = to_ox(s), to_ox(p), to_ox(o)  # a caller may still pass rdflib terms (identity on engine terms)
        if isinstance(s, (ox.Literal, ox.Triple)) or (p is not None and not isinstance(p, ox.NamedNode)):
            return iter(())
        return self.store.quads_for_pattern(s, p, o, self._graph)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
        """The triples matching ``pattern`` (``None`` is a wildcard), each once even when several graphs hold it."""
        s, p, o = pattern
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(s, p, o):
            key = (q.subject, q.predicate, q.object)
            if seen is not None:
                if key in seen:
                    continue
                seen.add(key)
            yield q.subject, q.predicate, q.object

    def objects(self, subject: Any = None, predicate: Any = None) -> Iterator[Any]:
        """The objects of the triples matching ``subject`` and ``predicate``; a triple held by several graphs is not repeated."""
        # Only the object is converted; with subject and predicate fixed the union de-duplicates on the object alone.
        if subject is None or predicate is None:
            for _s, _p, o in self.triples((subject, predicate, None)):
                yield o
            return
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(subject, predicate, None):
            o = q.object
            if seen is not None:
                if o in seen:
                    continue
                seen.add(o)
            yield o

    def subjects(self, predicate: Any = None, object: Any = None) -> Iterator[Any]:
        """The subjects of the triples matching ``predicate`` and ``object``; a triple held by several graphs is not repeated."""
        if predicate is None or object is None:
            for s, _p, _o in self.triples((None, predicate, object)):
                yield s
            return
        seen: set | None = set() if self._graph is None else None
        for q in self._quads(None, predicate, object):
            s = q.subject
            if seen is not None:
                if s in seen:
                    continue
                seen.add(s)
            yield s

    def predicate_objects(self, subject: Any = None) -> Iterator[tuple[Any, Any]]:
        """The (predicate, object) pairs of the triples matching ``subject``."""
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        """Whether the triple is in the selected graph; a wildcard (``None``) in a position matches anything."""
        s, p, o = triple
        return next(self._raw_quads(s, p, o), None) is not None

    def __len__(self) -> int:
        """The number of distinct triples in the selected graph; a triple held by several graphs counts once."""
        return sum(1 for _ in self.triples((None, None, None)))

    # ---- SPARQL -------------------------------------------------------------------------------------------------
    def _target(self, base_iri: str | None, custom_functions: Any) -> tuple[Any, dict[str, Any]]:
        """The store a query runs on and its keyword arguments (the graph it reads, ``base_iri``, ``custom_functions``)."""
        kwargs: dict[str, Any] = {}
        if base_iri is not None:
            kwargs["base_iri"] = base_iri
        if custom_functions:
            kwargs["custom_functions"] = custom_functions
        store = self.store
        if self._graph is None:
            # Oxigraph's union default graph counts a triple once per graph that holds it; the view is a set, so a store
            # with such a triple is queried through its merged copy, whose default graph is the set (see ``union.py``)
            if self._overlap.overlapping(store):
                store = self._overlap.store(store)
            else:
                kwargs["use_default_graph_as_union"] = True
        else:
            kwargs["default_graph"] = self._graph
        return store, kwargs

    def _run(self, text: str, init_bindings: dict[str, Any] | None, base_iri: str | None, custom_functions: Any) -> Any:
        """The raw pyoxigraph result. Pre-bound variables use ``substitutions``; Oxigraph requires a substituted variable to
        be projected, so for one that is not, the binding goes in as ``VALUES`` (a blank node, which cannot be written there,
        is added to the projection and dropped again): the same fallback as ``StarLayerGraph.query``."""
        subs = {ox.Variable(str(k).lstrip("?$")): to_ox(v) for k, v in (init_bindings or {}).items()} or None
        store, kwargs = self._target(base_iri, custom_functions)
        from starlayer.graph.execution import run as oxrun

        if subs and not any(oxrun._has_blank(v) for v in subs.values()):
            # pre-binding as the draft defines it: the binding is part of every group (see ``inject_everywhere``)
            header = " ".join("?" + v.value for v in subs)
            row = " ".join(oxrun._sparql_term(t) for t in subs.values())
            return store.query(inject_everywhere(text, f"VALUES ({header}) {{ ({row}) }}"), **kwargs)  # str-ok: SPARQL text
        try:
            return store.query(text, **kwargs, **({"substitutions": subs} if subs else {}))
        except RuntimeError as exc:
            if not subs or "projection" not in f"{exc}":  # str-ok: an exception message
                raise
            from starlayer.graph.execution import run as oxrun
            from starlayer.graph.execution.sparql_text import inject_init_bindings

            if any(oxrun._has_blank(v) for v in subs.values()):
                return oxrun._query_widening(store, text, kwargs, subs, exc)
            injected = inject_init_bindings(text, {k.value: oxrun._sparql_term(v) for k, v in subs.items()})
            return store.query(injected, **kwargs)

    def sparql_query(self, text: str, init_bindings: dict[str, Any] | None = None, custom_functions: Any = None) -> Any:
        """The ``SparqlCapable`` hook (see ``interface.py``): SELECT/ASK with pre-bound variables, run natively.
        ``custom_functions`` maps function IRIs to Python callables (pyoxigraph ``custom_functions``)."""
        from starlayer.shacl.engine.interface import Solutions

        result = self._run(text, init_bindings, None, custom_functions)
        if isinstance(result, ox.QueryBoolean):
            return Solutions(boolean=bool(result))
        names = tuple(v.value for v in result.variables)
        rows = tuple({n: sol[n] for n in names if sol[n] is not None} for sol in result)
        return Solutions(variables=names, rows=rows)

    def sparql_query_batch(
        self, text: str, name: str | tuple[str, ...], nodes: list, init_bindings: dict[str, Any] | None = None, custom_functions: Any = None
    ) -> tuple[tuple[str, ...], dict[Any, list[dict[str, Any]]]] | None:
        """The ``SparqlBatchCapable`` hook (see ``interface.py``): the SELECT ``text`` run once for many values of the pre-bound variable ``name``.

        Each node of ``nodes`` is pre-bound as ``sparql_query`` would pre-bind it (a ``VALUES`` block at the start of every group, but not in an
        ``EXISTS``); here the block has one row per node, so the store makes one pass for all of them. ``name`` may be a tuple of variable names,
        and ``nodes`` then tuples of terms (``?this`` and ``?value`` of a validator). ``init_bindings`` are the other pre-bound variables, with the
        same value in every row. Returns ``(projected variable names, {node: its rows})`` where a row is what ``sparql_query`` gives (unbound
        variables absent) and a node is a term, or a tuple of terms for a tuple of names; or ``None`` when the answer cannot be given node by node:
        a node that cannot be written in ``VALUES`` (a blank node, a triple term holding one), a query that does not project the names, or a row
        whose names are not one of the nodes."""
        from starlayer.graph.execution import run as oxrun

        columns_in = (name,) if isinstance(name, str) else tuple(name)
        nodes = [tuple(to_ox(t) for t in (n if isinstance(name, tuple) else (n,))) for n in nodes]
        others = {str(k).lstrip("?$"): to_ox(v) for k, v in (init_bindings or {}).items() if str(k).lstrip("?$") not in columns_in}
        if any(oxrun._has_blank(t) for n in nodes for t in n) or any(oxrun._has_blank(v) for v in others.values()):
            return None
        store, kwargs = self._target(None, custom_functions)
        columns = [*columns_in, *others]
        header = " ".join("?" + c for c in columns)
        tail = "".join(" " + oxrun._sparql_term(others[c]) for c in others)
        rows = " ".join("(" + " ".join(oxrun._sparql_term(t) for t in n) + tail + ")" for n in nodes)
        result = store.query(inject_everywhere(text, f"VALUES ({header}) {{ {rows} }}", skip_exists=True), **kwargs)  # str-ok: SPARQL text
        names = tuple(v.value for v in result.variables)
        if not all(c in names for c in columns_in):
            return None
        keys = {n if isinstance(name, tuple) else n[0] for n in nodes}
        grouped: dict[Any, list[dict[str, Any]]] = {}
        for sol in result:
            row = {n: sol[n] for n in names if sol[n] is not None}
            key = tuple(row.get(c) for c in columns_in) if isinstance(name, tuple) else row.get(name)
            grouped.setdefault(key, []).append(row)
        if not set(grouped) <= keys:
            return None  # (a node the store gives back in another form than it was given: the nodes cannot be told apart)
        return names, grouped

    def sparql_construct_batch(
        self, text: str, name: str, nodes: list, init_bindings: dict[str, Any] | None = None, custom_functions: Any = None
    ) -> list[tuple[Any, Any, Any]] | None:
        """The CONSTRUCT ``text`` run once for many values of the pre-bound variable ``name`` (as ``sparql_query_batch`` does for a SELECT): the triples
        of all of them, each once, in the order the store gives them. The triples of a CONSTRUCT are a set, so these are the triples the runs for
        the nodes one by one give together. ``None`` when a node or a binding cannot be written in ``VALUES`` (a blank node), or the text is not a CONSTRUCT."""
        from starlayer.graph.execution import run as oxrun

        nodes = [to_ox(n) for n in nodes]
        others = {str(k).lstrip("?$"): to_ox(v) for k, v in (init_bindings or {}).items() if str(k).lstrip("?$") != name}
        if any(oxrun._has_blank(v) for v in (*nodes, *others.values())):
            return None
        store, kwargs = self._target(None, custom_functions)
        columns = [name, *others]
        tail = "".join(" " + oxrun._sparql_term(others[c]) for c in others)
        rows = " ".join("(" + oxrun._sparql_term(n) + tail + ")" for n in nodes)
        result = store.query(inject_everywhere(text, f"VALUES ({' '.join('?' + c for c in columns)}) {{ {rows} }}", skip_exists=True), **kwargs)  # str-ok: SPARQL text
        if not isinstance(result, ox.QueryTriples):
            return None
        return list(dict.fromkeys(map(tuple, result)))  # (a triple of the store is a sequence of its three terms)

    def query(
        self, text: str, init_bindings: dict[str, Any] | None = None, *, base_iri: str | None = None, custom_functions: Any = None
    ) -> Any:
        """Run SPARQL natively. SELECT -> ``list[dict[str, term]]`` (unbound variables absent); ASK -> ``bool``;
        CONSTRUCT/DESCRIBE -> ``list[(s, p, o)]``. ``init_bindings`` maps variable names (with or without ``?``/``$``)
        to engine terms."""
        result = self._run(text, init_bindings, base_iri, custom_functions)
        if isinstance(result, ox.QueryBoolean):
            return bool(result)
        if hasattr(result, "variables"):
            names = [v.value for v in result.variables]
            return [{n: sol[n] for n in names if sol[n] is not None} for sol in result]
        return [(t.subject, t.predicate, t.object) for t in result]
