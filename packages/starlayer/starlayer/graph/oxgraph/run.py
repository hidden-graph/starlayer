"""SPARQL execution for the wrapper: the text goes to ``Store.query`` / ``Store.update`` as it is, ``initNs`` -> ``prefixes=``,
``base`` -> ``base_iri=``, ``initBindings`` -> ``substitutions=`` with a ``VALUES`` fallback when the variable is not projected.
The result is the wrapper's ``Result`` over pyoxigraph terms.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph import terms
from starlayer.graph.oxgraph import union as union_graph
from starlayer.graph.oxgraph.result import HiddenColumns, Result
from starlayer.graph.oxgraph.sparql_text import (
    check_native_version_conformance,
    inject_init_bindings,
)


def _sparql_term(t: Any) -> str:
    """A term as SPARQL writes it in ``VALUES``: ``str()`` for IRIs and literals, ``<<( s p o )>>`` for a triple term
    (``str(Triple)`` is the bare ``s p o``, which is not a term)."""
    if isinstance(t, ox.Triple):
        return f"<<( {_sparql_term(t.subject)} {_sparql_term(t.predicate)} {_sparql_term(t.object)} )>>"
    return str(t)


def _has_blank(t: Any) -> bool:
    """A blank node cannot be written in ``VALUES`` (in SPARQL a blank node in a query is a variable, not a stored node)."""
    if isinstance(t, ox.BlankNode):
        return True
    return isinstance(t, ox.Triple) and any(_has_blank(x) for x in (t.subject, t.predicate, t.object))


_AGGREGATE = re.compile(r"(?i)(?<![?$\w])(?:(?:COUNT|SUM|MIN|MAX|AVG|SAMPLE|GROUP_CONCAT)\s*\(|GROUP\s+BY\b)")
_PROLOGUE = re.compile(r"(?is)\A(?:\s*(?:PREFIX\s+[^\s:]*:|BASE\b|VERSION\b))*")


def _query_widening(store: ox.Store, text: str, kwargs: dict[str, Any], subs: dict[Any, Any], error: RuntimeError) -> Any:
    names: list[str] = []
    while True:
        m = re.search(r"variable \?(\w+)", str(error))
        if m is None or m.group(1) in names:
            raise error
        names.append(m.group(1))
        try:
            widened = _widen_projection(text, names)
            if widened is None:  # SELECT *: the variable is not in the query at all, so its binding changes nothing
                raw = store.query(text, **kwargs, substitutions={k: v for k, v in subs.items() if k.value not in names} or None)
                return raw
            raw = store.query(widened, **kwargs, substitutions=subs)
        except RuntimeError as e:
            if "projection" not in str(e):
                raise
            error = e
            continue
        return HiddenColumns(raw, set(names))


def _widen_projection(text: str, names: list[str]) -> str | None:
    """``text`` (a SELECT query) with ``names`` added to its projection, so that Oxigraph's ``substitutions`` accepts them;
    None for ``SELECT *``, which projects every variable of the query already."""
    masked = _mask(text)
    start = _PROLOGUE.match(masked).end()  # type: ignore[union-attr]  # the pattern matches the empty string
    m = re.compile(r"(?i)\bSELECT\b(?:\s+(?:DISTINCT|REDUCED)\b)?").search(masked, start)
    if m is None:
        raise NotImplementedError("initBindings with a blank node or a triple term holding one needs a SELECT query here")
    if re.match(r"\s*\*", masked[m.end() :]):
        return None
    if _AGGREGATE.search(masked):
        raise NotImplementedError(
            "initBindings with a blank node for a variable that is not projected, in a query with aggregates: write the variable "
            "into the SELECT list, or use a named node"
        )
    return text[: m.end()] + "".join(f" ?{n}" for n in names) + text[m.end() :]


def _has_from(text: str) -> bool:
    """True when the query has a dataset clause (``FROM`` / ``FROM NAMED``) of its own."""
    return re.search(r"(?i)(?<![\w:?$])FROM\b(?!:)", _mask(text)) is not None


def merge_prefixes(*maps: Mapping[str, str] | None) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for m in maps:
        if m:
            items = m.items() if hasattr(m, "items") else m
            out.update({str(k): str(v) for k, v in items})
    return out or None


def query(store: ox.Store, text: str, *, prefixes: Mapping[str, str] | None, init_ns: Any = None,
          init_bindings: Mapping[Any, Any] | None = None, base: str | None = None, default_graph: Any = None,
          union: bool = False, entailment: Any = None) -> Result:
    if not isinstance(text, str):
        raise NotImplementedError("the wrapper runs query text, not a prepared Query object")
    check_native_version_conformance(text)
    kwargs: dict[str, Any] = {}
    pfx = merge_prefixes(prefixes, init_ns)
    sent = text
    if entailment is not None:  # query-time RDF / RDFS entailment: the query is rewritten, the data is not touched
        from starlayer.sparql.sqe.entailment import rewrite_for_entailment

        sent = rewrite_for_entailment(text, entailment, prefixes=pfx, base=base)
    if pfx:
        kwargs["prefixes"] = pfx
    if base:
        kwargs["base_iri"] = base
    if union and not _has_from(text):  # the flag would override the query's own FROM / FROM NAMED, which define the dataset
        kwargs["use_default_graph_as_union"] = True
    elif default_graph is not None:
        kwargs["default_graph"] = default_graph
    subs = None
    if init_bindings:
        subs = {ox.Variable(str(getattr(k, "value", k)).lstrip("?$")): terms.term(v) for k, v in init_bindings.items()}
    elif "EXISTS" in text.upper():  # a correlated FILTER [NOT] EXISTS is much faster as a join (sparql/sqe/rewrite.py); same rows
        from starlayer.sparql.sqe.rewrite import rewrite_exists_text

        sent = rewrite_exists_text(sent, prefixes=pfx, base=base)
    try:
        raw = store.query(sent, **kwargs, **({"substitutions": subs} if subs else {}))
    except RuntimeError as e:
        if not subs or "projection" not in str(e):
            raise
        # The variable is not projected. Pre-binding it still means "the solutions in which ?x is this term" (what rdflib does).
        # A term that can be written in VALUES goes there; a blank node (or a triple term holding one) cannot be written, so
        # the variable is added to the SELECT list, bound by ``substitutions``, and the extra column is dropped again.
        if any(_has_blank(v) for v in subs.values()):
            raw = _query_widening(store, sent, kwargs, subs, e)
        else:
            injected = inject_init_bindings(sent, {k.value: _sparql_term(v) for k, v in subs.items()})
            raw = store.query(injected, **kwargs)
    return Result(raw, text)


def update(store: ox.Store, text: str, *, prefixes: Mapping[str, str] | None, init_ns: Any = None,
           base: str | None = None, union: bool = False, overlap: Any = None) -> None:
    if not isinstance(text, str):
        raise NotImplementedError("the wrapper runs update text, not a prepared Update object")
    check_native_version_conformance(text)
    kwargs: dict[str, Any] = {}
    pfx = merge_prefixes(prefixes, init_ns)
    if pfx:
        kwargs["prefixes"] = pfx
    if base:
        kwargs["base_iri"] = base
    if not union:
        store.update(text, **kwargs)
        return
    import uuid

    scratch = ox.NamedNode(f"urn:x-starlayer:union-default:{uuid.uuid4()}")
    dedupe = overlap is not None and overlap.overlapping(store)  # a triple in two graphs: the WHERE must see it once
    text, used = union_update_text(store, text, scratch, dedupe=dedupe)
    if used and dedupe:  # the set of the triples of every graph, in one graph that USING names alone
        union_graph.fill_scratch(store, scratch)
    elif used:  # the default graph and blank-node graphs, copied where USING can name them
        store.extend([ox.Quad(q.subject, q.predicate, q.object, scratch) for q in list(store) if not isinstance(q.graph_name, ox.NamedNode)])
    try:
        store.update(text, **kwargs)
    finally:
        if used:
            store.remove_graph(scratch)


# ---- default_union for SPARQL Update ----------------------------------------------------------------------------------
_IRI_AT = re.compile(r'<[^<>\s"{}|^`\\]*>')
_STRING_AT = re.compile(r'"""(?:[^"\\]|\\.|"(?!""))*"""|' + r"'''(?:[^'\\]|\\.|'(?!''))*'''|" + r'"(?:[^"\\\n]|\\.)*"|' + r"'(?:[^'\\\n]|\\.)*'", re.S)


def _mask(text: str) -> str:
    """``text`` with comments, strings, IRIs and everything inside ``{ }`` blanked (same length), so that a keyword found in the
    result is a keyword at brace depth 0. A ``;`` or ``WHERE`` inside a string, IRI or group is not seen."""
    out = list(text)
    i, depth, n = 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
            continue
        m = None
        if c in "\"'":
            m = _STRING_AT.match(text, i)
        elif c == "<":
            m = _IRI_AT.match(text, i)
        if m is not None:
            out[i : m.end()] = " " * (m.end() - i)
            i = m.end()
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth > 0 and c != "\n":
            out[i] = " "
        i += 1
    # a prefixed name outside a group (``PREFIX using: <..>``, ``WITH ex:where``) is not a keyword: blank its letters, keep the colon
    return _PNAME.sub(lambda m: re.sub(r"[^:]", "_", m.group()), "".join(out))


_PNAME = re.compile(r"(?<![\w:.-])[\w.-]*:[\w.:%-]*")


def union_update_text(store: ox.Store, text: str, scratch: ox.NamedNode, dedupe: bool = False) -> tuple[str, bool]:
    """``(text', used)``: ``text`` rewritten so that the ``WHERE`` of each ``INSERT`` / ``DELETE`` ... ``WHERE`` (and ``DELETE
    WHERE``) operation reads the union of all graphs, as ``query()`` does on a ``default_union`` dataset. SPARQL Update has no
    "default graph is the union" switch, but a ``USING <g>`` clause makes the default graph the merge of the listed graphs, so
    one is added for every IRI-named graph, plus ``USING NAMED <g>`` for each (a ``USING`` without ``USING NAMED`` would hide the
    named graphs from ``GRAPH ?g``). ``USING`` can name only IRIs, so the triples of the default graph and of blank-node-named
    graphs are first copied into the ``scratch`` graph, which is listed too; the caller drops it afterwards (``used`` is True
    when it was filled). With ``dedupe`` (a triple is in more than one graph) ``scratch`` holds the set of the triples of every
    graph, the default graph included, and is the only ``USING <g>``, so that a triple held twice is read once. Templates (``INSERT {..}``, ``DELETE {..}``) are unchanged: they write where they always wrote.

    Limits: an operation with its own ``USING`` is left as the author wrote it, and so is a ``WITH`` operation unless the scratch
    graph exists. Then a ``WITH <g>`` operation gets ``USING <g>`` and a ``USING NAMED`` for every IRI-named graph, which is its own
    dataset (the default graph ``g``, the named graphs) without the scratch graph, so that ``GRAPH ?x`` cannot bind it; the graphs
    named by a blank node are not listed, as ``USING NAMED`` takes only IRIs. The graph list and the copy are taken when the update
    starts, so an operation of the request does not see what an earlier operation of the same request wrote to a graph that did not
    exist yet, or to the default graph. The request stays one ``Store.update`` call, which Oxigraph applies atomically.
    """
    named = [g for g in store.named_graphs() if isinstance(g, ox.NamedNode) and next(store.quads_for_pattern(None, None, None, g), None) is not None]
    others = next((q for q in store if not isinstance(q.graph_name, ox.NamedNode)), None) is not None
    blank_graphs = next((q for q in store if isinstance(q.graph_name, ox.BlankNode)), None) is not None
    if not named and not dedupe and not blank_graphs:
        return text, False  # only the default graph (or nothing) has data: union == default graph
    masked = _mask(text)
    bounds = [0, *[m.start() + 1 for m in re.finditer(";", masked)], len(text)]
    pieces: list[str] = []
    with_only: list[int] = []  # indexes in ``pieces`` of operations with a WITH and no USING, which are not rewritten
    used = False
    using = " ".join(([] if dedupe else [f"USING <{g.value}>" for g in named]) + [f"USING NAMED <{g.value}>" for g in named])
    for a, b in zip(bounds, bounds[1:], strict=False):
        seg, mseg = text[a:b], masked[a:b]
        # `masked` already blanked the IRIs, so the prologue is just the PREFIX/BASE words and whitespace
        head = re.sub(r"(?is)\A(?:\s*(?:PREFIX\s+[^\s:]*:|BASE\b|VERSION\b))*", "", mseg).lstrip()
        if re.match(r"(?i)WITH\b", head) and not re.search(r"(?i)\bUSING\b", mseg) and re.search(r"(?i)\bWHERE\b", mseg):
            with_only.append(len(pieces))  # reads its WITH graph and every named graph: the scratch graph must not be one of them
            pieces.append(seg)
            continue
        if not re.match(r"(?i)(?:DELETE|INSERT)\b", head) or re.search(r"(?i)\bUSING\b", mseg):
            pieces.append(seg)  # LOAD, CLEAR, ..., or its own dataset clause
            continue
        dw = re.search(r"(?i)\bDELETE\s+WHERE\b", mseg)
        w = re.search(r"(?i)\bWHERE\b", mseg)
        if w is None:
            pieces.append(seg)  # INSERT DATA / DELETE DATA
            continue
        clause = using + (f" USING <{scratch.value}>" if others or dedupe else "")
        used = used or others or dedupe
        if dw is not None:  # DELETE WHERE { P } has no USING in its grammar: write it as DELETE { P } USING .. WHERE { P }
            lo = mseg.find("{", dw.end())
            if lo < 0:
                pieces.append(seg)  # malformed: Oxigraph reports the SyntaxError
                continue
            depth, hi = 0, lo
            for k in range(lo, len(mseg)):
                depth += mseg[k] == "{"
                depth -= mseg[k] == "}"
                if depth == 0:
                    hi = k
                    break
            pattern = seg[lo : hi + 1]
            pieces.append(seg[: dw.start()] + f"DELETE {pattern} {clause} WHERE {pattern}" + seg[hi + 1 :])
        else:
            pieces.append(seg[: w.start()] + clause + " " + seg[w.start() :])
    if used:
        named_clause = " ".join(f"USING NAMED <{g.value}>" for g in named)
        for i in with_only:
            seg = pieces[i]
            mseg = _mask(seg)
            kw = re.search(r"(?i)\bWITH\b\s*", mseg)  # found in the masked text, so not inside a string or comment
            w = re.search(r"(?i)\bWHERE\b", mseg)
            if kw is not None and w is not None:
                graph = seg[kw.end() :].split(None, 1)[0]  # the IRI or prefixed name, as written
                pieces[i] = seg[: w.start()] + f"USING {graph} {named_clause} " + seg[w.start() :]
    return "".join(pieces), used
