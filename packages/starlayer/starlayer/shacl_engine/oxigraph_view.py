"""``OxigraphGraph``: a ``GraphView`` straight over a ``pyoxigraph.Store`` (no rdflib graph in between).

Terms handed to and from the engine are pyoxigraph terms (``engine_terms = True``): the view returns the store's terms
as they are, with no conversion. ``to_ox`` / ``from_ox`` only convert rdflib / StarLayer terms a caller passes in.

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

from starlayer.shacl_engine.terms import (
    check_graphs,
    from_engine,
    to_engine,
)

UNION = object()
DEFAULT = object()



# Terms handed to and from the engine are pyoxigraph terms: the view returns store terms as they are. ``to_ox`` /
# ``from_ox`` convert the rdflib / StarLayer terms a caller may still pass (graph names, ``add``, pre-bindings).
to_ox = to_engine
from_ox = from_engine


_WORD = re.compile(r"[A-Za-z_]+")
_SELECT_NEXT = re.compile(r"(?:\s|#[^\n]*\n)*SELECT\b", re.I)


def inject_everywhere(text: str, values: str) -> str:
    """``text`` with the ``values`` clause (``VALUES (?x) { (t) }``) put at the start of every group graph pattern, so a pre-bound
    variable is bound inside nested groups too, as SHACL 1.2 SPARQL Appendix A defines pre-binding (Oxigraph's ``substitutions``
    do not reach a group that holds only a ``FILTER``). Not in a sub-select's opening brace, a ``VALUES`` data block or a
    ``CONSTRUCT`` template. Strings, IRIs and comments are skipped."""
    from starlayer.graph.oxgraph.run import _IRI_AT, _STRING_AT

    out: list[str] = []
    i, n = 0, len(text)
    after_values = construct = construct_where = False
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
            if text[i - 1 : i] not in "?$:" or i == 0:
                if upper == "VALUES":
                    after_values = True
                elif upper == "CONSTRUCT":
                    construct = True
                elif upper == "WHERE" and construct:
                    construct, construct_where = False, True
            out.append(text[i:j])
            i = j
            continue
        out.append(c)
        i += 1
        if c == "{":
            skip = after_values or construct or construct_where or _SELECT_NEXT.match(text, i) is not None
            if after_values:
                after_values = False
            elif construct:
                construct = False
            elif construct_where:
                construct_where = False
            if not skip:
                out.append(" " + values + " ")
    return "".join(out)


class OxigraphGraph:
    engine_terms = True
    preserves_lexical_forms = False
    native_sparql = True

    def __init__(self, store: ox.Store | None = None, graph_name: Any = UNION) -> None:
        self.store = store if store is not None else ox.Store()
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
        return cls(store, graph_name)

    @classmethod
    def from_text(
        cls, text: str, *, format: str = "turtle", graph_name: Any = UNION, base_iri: str | None = None
    ) -> OxigraphGraph:
        fmt = {"turtle": ox.RdfFormat.TURTLE, "trig": ox.RdfFormat.TRIG, "nt": ox.RdfFormat.N_TRIPLES}[format]
        target = graph_name if graph_name not in (UNION, DEFAULT) else None
        store = ox.Store()
        store.load(text.encode(), format=fmt, base_iri=base_iri, to_graph=to_ox(target))
        return cls(store, graph_name)

    @classmethod
    def from_graph(cls, graph: Any, *, graph_name: Any = UNION) -> OxigraphGraph:
        """Copy the triples of an rdflib / StarLayerGraph (anything with ``.triples((None, None, None))``) in. A term that is
        not an RDF term (relative IRI ...) raises ``TermError`` naming every offender (or, under ``term_policy("lenient")``,
        is stored as the opaque stand-in ``from_engine`` maps back); a store cannot hold it. ``add`` and pattern lookups
        raise ``TermError`` for such a term too."""
        check_graphs((graph, "graph"))
        store = ox.Store()
        target = ox.DefaultGraph() if graph_name in (UNION, DEFAULT) else to_ox(graph_name)
        store.bulk_extend(
            ox.Quad(to_ox(s), to_ox(p), to_ox(o), target) for s, p, o in graph.triples((None, None, None))
        )
        return cls(store, graph_name)

    def add(self, triple: tuple[Any, Any, Any]) -> None:
        g = ox.DefaultGraph() if self._graph is None else self._graph
        self.store.add(ox.Quad(*(to_ox(t) for t in triple), g))
        from starlayer.graph.oxgraph import union

        union.touch()  # a dataset over this store drops its deduplicated copy

    # ---- GraphView ----------------------------------------------------------------------------------------------
    def _quads(self, s: Any, p: Any, o: Any) -> Iterator[ox.Quad]:
        # Oxigraph raises on a literal / triple term subject or a non-IRI predicate; RDF graphs simply have no match.
        s, p, o = to_ox(s), to_ox(p), to_ox(o)  # a caller may still pass rdflib terms (identity on engine terms)
        if isinstance(s, (ox.Literal, ox.Triple)) or (p is not None and not isinstance(p, ox.NamedNode)):
            return iter(())
        return self.store.quads_for_pattern(s, p, o, self._graph)

    def triples(self, pattern: tuple[Any, Any, Any]) -> Iterator[tuple[Any, Any, Any]]:
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
        for _s, p, o in self.triples((subject, None, None)):
            yield p, o

    def __contains__(self, triple: tuple[Any, Any, Any]) -> bool:
        s, p, o = triple
        return next(iter(self._quads(s, p, o)), None) is not None

    def __len__(self) -> int:
        return sum(1 for _ in self.triples((None, None, None)))

    # ---- SPARQL -------------------------------------------------------------------------------------------------
    def _run(self, text: str, init_bindings: dict[str, Any] | None, base_iri: str | None, custom_functions: Any) -> Any:
        """The raw pyoxigraph result. Pre-bound variables use ``substitutions``; Oxigraph requires a substituted variable to
        be projected, so for one that is not, the binding goes in as ``VALUES`` (a blank node, which cannot be written there,
        is added to the projection and dropped again): the same fallback as ``OxGraph.query``."""
        subs = {ox.Variable(str(k).lstrip("?$")): to_ox(v) for k, v in (init_bindings or {}).items()} or None
        kwargs: dict[str, Any] = {}
        if base_iri is not None:
            kwargs["base_iri"] = base_iri
        if custom_functions:
            kwargs["custom_functions"] = custom_functions
        if self._graph is None:
            kwargs["use_default_graph_as_union"] = True
        else:
            kwargs["default_graph"] = self._graph
        from starlayer.graph.oxgraph import run as oxrun

        if subs and not any(oxrun._has_blank(v) for v in subs.values()):
            # pre-binding as the draft defines it: the binding is part of every group (see ``inject_everywhere``)
            header = " ".join("?" + v.value for v in subs)
            row = " ".join(oxrun._sparql_term(t) for t in subs.values())
            return self.store.query(inject_everywhere(text, f"VALUES ({header}) {{ ({row}) }}"), **kwargs)  # str-ok: SPARQL text
        try:
            return self.store.query(text, **kwargs, **({"substitutions": subs} if subs else {}))
        except RuntimeError as exc:
            if not subs or "projection" not in f"{exc}":  # str-ok: an exception message
                raise
            from starlayer.graph.oxgraph import run as oxrun
            from starlayer.graph.oxgraph.sparql_text import inject_init_bindings

            if any(oxrun._has_blank(v) for v in subs.values()):
                return oxrun._query_widening(self.store, text, kwargs, subs, exc)
            injected = inject_init_bindings(text, {k.value: oxrun._sparql_term(v) for k, v in subs.items()})
            return self.store.query(injected, **kwargs)

    def sparql_query(self, text: str, init_bindings: dict[str, Any] | None = None, custom_functions: Any = None) -> Any:
        """The ``SparqlCapable`` hook (see ``interface.py``): SELECT/ASK with pre-bound variables, run natively.
        ``custom_functions`` maps function IRIs to Python callables (pyoxigraph ``custom_functions``)."""
        from starlayer.shacl_engine.interface import Solutions

        result = self._run(text, init_bindings, None, custom_functions)
        if isinstance(result, ox.QueryBoolean):
            return Solutions(boolean=bool(result))
        names = tuple(v.value for v in result.variables)
        rows = tuple({n: sol[n] for n in names if sol[n] is not None} for sol in result)
        return Solutions(variables=names, rows=rows)

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
