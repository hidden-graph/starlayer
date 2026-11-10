"""Pretty Turtle / TriG over pyoxigraph terms.

Oxigraph's serializer is a streaming writer: it writes one statement at a time and cannot fold a blank node into ``[ ... ]``,
an RDF list into ``( ... )`` or a reifier into ``{| ... |}``. :func:`pretty_turtle` and :func:`pretty_trig` read the whole graph
(or dataset) first and lay it out the way the older rdflib-based writer (``starlayer.graph.serializers.turtle12``) did, written
over ``pyoxigraph`` terms with no rdflib import. They are what ``StarLayerGraph.serialize(..., pretty=True)`` calls.

Input: a ``pyoxigraph.Store`` or ``Dataset``, an ``StarLayerGraph`` / ``StarLayerDataset``, or any iterable of ``Quad`` / ``Triple`` (or 3- and
4-tuples of terms). Output: ``str``.

Layout, ``style="turtle"`` (the default)
    * ``@version "1.2" .`` (when the data has a triple term or a base-direction literal), ``@base``, then ``@prefix`` lines
      (sorted by prefix; only prefixes the body uses unless ``only_used=False``), a blank line, then one block per subject.
    * a subject's predicates are grouped with ``;`` (``rdf:type`` first, written ``a``, then by IRI), its objects with ``,``;
      predicate lines are indented four spaces. Subjects are ordered IRIs, then blank nodes, then reified triples.
    * a blank node referenced once, in its own graph, is written ``[ ... ]`` inside its parent; a well-formed RDF list
      (every cell has only ``rdf:first`` and ``rdf:rest``, each referenced once, ending in ``rdf:nil``) is written
      ``( a b c )``; ``rdf:nil`` is ``()`` where the grammar allows a collection. Everything else (shared blank nodes, cycles,
      malformed lists, blank nodes inside triple terms or used as graph names) is written with a ``_:bN`` label; blank nodes
      are relabelled ``b0, b1, ...`` in output order (``keep_bnode_labels=True`` keeps the input labels, at the price of
      an order that depends on them).
    * RDF 1.2: a triple term is ``<<( s p o )>>``. A reifier of an asserted triple is folded into ``s p o {| ... |}`` (named:
      ``s p o ~ :r {| ... |}``; no annotations: ``~``); a reifier of an unasserted triple, with annotations, becomes the subject
      ``<< s p o >> p o`` (named: ``<< s p o ~ :r >>``); a bare blank-node reifier referenced once is written ``<< s p o >>``
      in object position. A reifier that cannot be folded (it reifies two triples, is shared, ...) stays ``_:b rdf:reifies <<( ... )>>``.
    * ``1``, ``1.5``, ``1.5e3`` and ``true`` are written bare ONLY when the literal's lexical form is exactly the Turtle token
      (``"+1"^^xsd:integer`` is ``+1``; ``"1"^^xsd:boolean``, ``"1."^^xsd:decimal`` and ``"01.5E+2"`` that is not a Turtle double
      keep ``"..."^^xsd:...``): the lexical form is never normalised. Multi-line strings use ``\"\"\"..\"\"\"``.
    * ``width`` (default 100; ``None`` never wraps) breaks an object list or an ``( ... )`` list that is too long, one item
      per line.

TriG: the default graph's statements first (unwrapped), then ``GRAPH <name> { ... }`` blocks, sorted by name. A blank node
that is shared between graphs, or is a graph name, is labelled.

Determinism: the output depends only on the graph's structure, not on blank-node labels or input order (blank nodes are ordered
by a structural signature: their colour after colour refinement to a fixpoint, ``_Writer._refine``), so
``pretty(parse(pretty(x))) == pretty(x)``. Limits: blank nodes that colour refinement cannot tell apart (symmetric ones, whose
order does not show in the output, and rare regular structures) are ordered as they came in, and a blank-node chain longer than
64 steps is told apart only as far as 64 rounds reach.
"""

from __future__ import annotations

import gc
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urljoin

import pyoxigraph as ox

__all__ = ["pretty_trig", "pretty_turtle", "serialize_pretty"]

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_XSD = "http://www.w3.org/2001/XMLSchema#"
_TYPE = _RDF + "type"
_REIFIES = _RDF + "reifies"
_FIRST = _RDF + "first"
_REST = _RDF + "rest"
_NIL = _RDF + "nil"
_XSD_STRING = _XSD + "string"

_NN, _BN, _LIT, _TRIPLE = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple
_DEFAULT = ox.DefaultGraph()

# Turtle's own bare tokens; a literal is written bare only when its lexical form matches exactly (so it re-reads identically)
_INTEGER_RE = re.compile(r"[+-]?[0-9]+")
_DECIMAL_RE = re.compile(r"[+-]?[0-9]*\.[0-9]+")
_DOUBLE_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)[eE][+-]?[0-9]+")

_PN_CHARS_BASE = (
    "A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02ff\u0370-\u037d\u037f-\u1fff\u200c-\u200d\u2070-\u218f"
    "\u2c00-\u2fef\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufffd\U00010000-\U000effff"
)
_PN_CHARS_U = _PN_CHARS_BASE + "_"
_PN_CHARS = _PN_CHARS_U + "\\-0-9\u00b7\u0300-\u036f\u203f-\u2040"
# Turtle PN_LOCAL without backslash escapes (a name that needs one is written as <IRI>)
_PN_LOCAL = re.compile(
    rf"(?:[{_PN_CHARS_U}:0-9]|%[0-9A-Fa-f]{{2}})"
    rf"(?:(?:[{_PN_CHARS}.:]|%[0-9A-Fa-f]{{2}})*(?:[{_PN_CHARS}:]|%[0-9A-Fa-f]{{2}}))?"
)
_PN_PREFIX = re.compile(rf"(?:[{_PN_CHARS_BASE}](?:[{_PN_CHARS}.]*[{_PN_CHARS}])?)?")
_BNODE_LABEL = re.compile(rf"[{_PN_CHARS_U}0-9](?:[{_PN_CHARS}.]*[{_PN_CHARS}])?")

# characters a string must not carry raw: C0 controls (but TAB, LF, CR have their own handling), DEL, NEL, LS, PS
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x85\u2028\u2029]")
_IRI_BAD = re.compile("[\x00-\x20<>\"{}|^`\\\\\x7f]")
# A relative reference is written only if it re-resolves to the IRI. Not one whose first segment holds a colon (RFC 3986 section
# 4.2: ``a_b:c`` or ``:a`` would be read as having a scheme or as absolute; any colon before the first ``/ ? #`` counts, not only
# a letter-led scheme), nor one starting with ``/`` ``#`` ``?``, nor a dot segment.
_REL_UNSAFE = re.compile(r"[^/?#]*:|[/#?]|\.\.?(?:/|$)")

_INDENT = "    "


# ---------------------------------------------------------------------------------------------------------------------------
# names: prefixes, IRIs, base
# ---------------------------------------------------------------------------------------------------------------------------
class _Names:
    """The prefix bindings and base a writer may use. A prefix that is not a valid PN_PREFIX is renamed ``pfxN``; ``rdf`` and
    ``xsd`` are bound automatically (and declared only when used) unless the caller binds their namespaces."""

    def __init__(self, prefixes: Mapping[str, Any] | None, base: str | None, auto: bool = True) -> None:
        given = {str(k): str(getattr(v, "value", v)) for k, v in (prefixes or {}).items()}
        bound: list[tuple[str, str]] = []
        invalid = []
        for p, ns in sorted(given.items()):
            (bound if _PN_PREFIX.fullmatch(p) else invalid).append((p, ns))
        taken = set(given)
        n = 0
        for _p, ns in sorted(invalid, key=lambda t: (t[1], t[0])):
            n += 1
            while f"pfx{n}" in taken:
                n += 1
            taken.add(f"pfx{n}")
            bound.append((f"pfx{n}", ns))
        self.auto: set[str] = set()
        if auto:
            have = {ns for _, ns in bound}
            for p, ns in (("rdf", _RDF), ("xsd", _XSD)):
                if ns not in have and p not in taken:
                    bound.append((p, ns))
                    self.auto.add(p)
        self.pairs = sorted(bound)
        self.by_len = sorted(bound, key=lambda t: (-len(t[1]), t[0]))
        self.base = base or None
        self.used: set[str] = set()
        self._cache: dict[str, tuple[str, str | None]] = {}

    def reset(self) -> None:
        self.used = set()

    def iri(self, v: str) -> str:
        hit = self._cache.get(v)
        if hit is None:
            hit = self._cache[v] = self._make(v)
        if hit[1] is not None:
            self.used.add(hit[1])
        return hit[0]

    def _make(self, v: str) -> tuple[str, str | None]:
        for prefix, ns in self.by_len:
            if len(ns) < len(v) and v.startswith(ns):
                local = v[len(ns):]
                if _PN_LOCAL.fullmatch(local):
                    return f"{prefix}:{local}", prefix
        return self.iri_ref(v), None

    def iri_ref(self, v: str) -> str:
        base = self.base
        if base and v.startswith(base) and len(v) > len(base):
            rest = v[len(base):]
            if not _REL_UNSAFE.match(rest) and urljoin(base, rest) == v:
                v = rest
        return "<" + _IRI_BAD.sub(lambda m: f"\\u{ord(m.group()):04X}", v) + ">"


# ---------------------------------------------------------------------------------------------------------------------------
# input
# ---------------------------------------------------------------------------------------------------------------------------
def _as_node(x: Any) -> Any:
    if isinstance(x, str):
        return _NN(x)
    return x


def _collect(data: Any, graph: Any) -> tuple[list[tuple[Any, Any, Any, Any]], Any]:
    """``(quads, prefixes)``: the distinct ``(g, s, p, o)`` of the input, and the prefix dict the input carries (or None)."""
    prefixes = getattr(data, "prefixes", None)
    if isinstance(data, (ox.Store, ox.Dataset)):
        it: Iterable[Any] = data
    elif hasattr(data, "store") and hasattr(data, "identifier"):  # a graph view: its triples, as default-graph statements
        it = (ox.Quad(q.subject, q.predicate, q.object, _DEFAULT)
              for q in data.store.quads_for_pattern(None, None, None, data.identifier))
    elif hasattr(data, "store"):
        it = data.store
    else:
        it = data
    out: dict[tuple[Any, Any, Any, Any], None] = {}
    want = None if graph is ... else (_DEFAULT if graph is None else _as_node(graph))
    for q in it:
        if isinstance(q, ox.Quad):
            g, s, p, o = q.graph_name, q.subject, q.predicate, q.object
        elif isinstance(q, ox.Triple):
            g, s, p, o = _DEFAULT, q.subject, q.predicate, q.object
        elif len(q) == 3:
            g, (s, p, o) = _DEFAULT, q
        else:
            s, p, o, g = q
            g = _DEFAULT if g is None else _as_node(g)
        if want is not None and g != want:
            continue
        out[(g, s, p, o)] = None
    return list(out), prefixes


# ---------------------------------------------------------------------------------------------------------------------------
# the writer
# ---------------------------------------------------------------------------------------------------------------------------
def _walk_tt(t: Any) -> Iterable[Any]:
    """Every term of a triple term, at any depth (the nested triple terms included)."""
    for part in (t.subject, t.predicate, t.object):
        yield part
        if isinstance(part, _TRIPLE):
            yield from _walk_tt(part)


class _Writer:
    def __init__(self, quads: list[tuple[Any, Any, Any, Any]], names: _Names, *, width: int | None,
                 keep_labels: bool, trig: bool) -> None:
        self.names = names
        self.width = width
        self.keep_labels = keep_labels
        self.trig = trig
        self.quads = quads
        self._stats()
        self._signatures()
        self._keys: dict[Any, tuple] = {}

    # ---- statistics ----------------------------------------------------------------------------------------------------
    def _stats(self) -> None:
        by_sg: dict[Any, dict[Any, dict[Any, list[Any]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        objrefs: dict[Any, int] = defaultdict(int)
        ref_of: dict[Any, tuple[Any, Any, Any]] = {}
        ttref: set = set()
        gref: set = set()
        subj_graphs: dict[Any, set] = defaultdict(set)
        v12 = False
        for g, s, p, o in self.quads:
            by_sg[g][s][p].append(o)
            if isinstance(g, _BN):
                gref.add(g)
            if isinstance(s, _BN):
                subj_graphs[s].add(g)
            if isinstance(o, _BN):
                objrefs[o] += 1
                ref_of[o] = (s, p, g)
            elif isinstance(o, _TRIPLE):
                v12 = True
                for part in _walk_tt(o):
                    if isinstance(part, _BN):
                        ttref.add(part)
                    elif isinstance(part, _LIT) and part.direction is not None:
                        v12 = True
            elif isinstance(o, _LIT) and o.direction is not None:
                v12 = True
        self.by_sg, self.objrefs, self.ref_of, self.ttref, self.gref, self.subj_graphs = (
            by_sg, objrefs, ref_of, ttref, gref, subj_graphs)
        self.v12 = v12

    def _signatures(self) -> None:
        self._colors: dict[Any, str] | None = None

    #: most refinement rounds; a blank-node chain longer than this is told apart only as far as it reaches (see ``_refine``)
    _MAX_ROUNDS = 64

    def _refine(self) -> dict[Any, str]:
        """Colour every blank node by its structure, by colour refinement (1-dimensional Weisfeiler-Leman): a node's colour is
        a hash of its own colour and of the sorted ``(direction, predicate, neighbour colour)`` list of its edges (blank nodes
        in triple terms and as graph names included). Rounds repeat until the partition stops getting finer, so two blank
        nodes differ in colour whenever their neighbourhoods differ at any distance (a fixed depth of 3 told apart only
        chains that differ within 3 steps, and ties were then broken by input order). Labels never enter, so the colours, and
        the ordering made from them, depend on structure only. Each round is linear in the number of edges and the number of
        rounds is the longest distance that still separates two nodes, capped at ``_MAX_ROUNDS``; nodes still tied at the end
        are interchangeable for 1-WL (automorphic nodes, whose order cannot change the output; only regular non-automorphic
        structures or chains longer than the cap could still tie, and then the order falls back to the input order)."""
        out: dict[Any, list[tuple[Any, Any]]] = defaultdict(list)
        inc: dict[Any, list[tuple[str, Any, Any]]] = defaultdict(list)
        gcontent: dict[Any, list[tuple[Any, Any, Any]]] = defaultdict(list)  # a blank graph name: what its graph holds
        nodes: set = set()
        for g, s, p, o in self.quads:
            if isinstance(g, _BN):
                gcontent[g].append((s, p, o))
            if isinstance(s, _BN):
                out[s].append((p, o))
                nodes.add(s)
            if isinstance(o, _BN):
                inc[o].append(("i", p, s))
                nodes.add(o)
            elif isinstance(o, _TRIPLE):
                for part in _walk_tt(o):
                    if isinstance(part, _BN):
                        inc[part].append(("t", p, s))
                        nodes.add(part)
            if isinstance(g, _BN):
                inc[g].append(("g", g, g))
                nodes.add(g)
        color = dict.fromkeys(nodes, "0")

        def rep(t: Any, me: Any) -> str:
            if isinstance(t, _NN):
                return "N" + t.value
            if isinstance(t, _BN):
                return "self" if t == me else "B" + color[t]
            if isinstance(t, _LIT):
                return f"L{t.value}\x00{t.datatype.value}\x00{t.language}\x00{t.direction}"
            return f"T({rep(t.subject, me)} {rep(t.predicate, me)} {rep(t.object, me)})"

        classes = 1 if nodes else 0
        for _ in range(self._MAX_ROUNDS):
            new: dict[Any, str] = {}
            for b in nodes:
                parts = [f"o {rep(p, b)} {rep(o, b)}" for p, o in out.get(b, ())]
                parts += [f"{k} {rep(p, b)} {rep(s, b)}" for k, p, s in inc.get(b, ())]
                parts += [f"c {rep(s, b)} {rep(p, b)} {rep(o, b)}" for s, p, o in gcontent.get(b, ())]
                parts.sort()
                new[b] = hashlib.sha1((color[b] + "\n" + "\n".join(parts)).encode("utf-8", "surrogatepass")).hexdigest()[:16]
            n_classes = len(set(new.values()))
            color = new
            if n_classes <= classes:
                break
            classes = n_classes
        self._colors = color
        return color

    def _sig(self, b: Any) -> str:
        """A label-independent signature of blank node ``b`` (its refined colour, see ``_refine``)."""
        colors = self._colors if self._colors is not None else self._refine()
        return colors.get(b, "0")

    def key(self, t: Any) -> tuple:
        k = self._keys.get(t)
        if k is None:
            if isinstance(t, _NN):
                k = (0, t.value)
            elif isinstance(t, _BN):
                k = (1, t.value if self.keep_labels else self._sig(t))
            elif isinstance(t, _LIT):
                k = (2, t.value, t.datatype.value, t.language or "", str(t.direction or ""))
            elif isinstance(t, _TRIPLE):
                k = (3, self.key(t.subject), self.key(t.predicate), self.key(t.object))
            else:
                k = (4, str(t))
            self._keys[t] = k
        return k

    # ---- planning ------------------------------------------------------------------------------------------------------
    def _plan(self) -> None:
        by_sg = self.by_sg
        nofold = self.nofold
        self._inline_cache: dict[Any, bool] = {}
        self.list_heads: dict[Any, list[Any]] = {}
        self.list_cells: set = set()
        self.annot: dict[tuple, list[Any]] = defaultdict(list)  # (g, s, p, o) -> reifiers folded onto it
        self.fold_kind: dict[tuple, str] = {}  # (g, r) -> "annot" | "subj" | "obj"
        self.fold_tt: dict[tuple, Any] = {}

        # --- lists
        cand: dict[Any, tuple[Any, Any]] = {}
        for g, subs in by_sg.items():
            for b, preds in subs.items():
                if not isinstance(b, _BN) or b in self.nolist or len(preds) != 2 or b in self.ttref or b in self.gref:
                    continue
                f, r = preds.get(_NN(_FIRST)), preds.get(_NN(_REST))
                if f is None or r is None or len(f) != 1 or len(r) != 1 or self.objrefs[b] != 1:
                    continue
                if self.ref_of[b][2] != g or self.subj_graphs[b] != {g}:
                    continue
                cand[b] = (f[0], r[0])
        valid: dict[Any, bool] = {}
        for c in cand:
            if c in valid:
                continue
            path, node, ok = [], c, False
            while True:
                if node in valid:
                    ok = valid[node]
                    break
                if node in path or node not in cand:
                    break
                path.append(node)
                rest = cand[node][1]
                if isinstance(rest, _NN) and rest.value == _NIL:
                    ok = True
                    break
                node = rest
            for n in path:
                valid[n] = ok
        for c in cand:
            if not valid.get(c):
                continue
            s, p, _g = self.ref_of[c]
            if s in cand and p.value == _REST:
                continue  # interior cell of another list
            items, cells, node = [], [], c
            while True:
                items.append(cand[node][0])
                cells.append(node)
                rest = cand[node][1]
                if isinstance(rest, _BN):
                    node = rest
                else:
                    break
            self.list_heads[c] = items
            self.list_cells.update(cells)

        # --- blank nodes written inline
        # (a list cell is not inline: it is part of its list)

        # --- reifiers
        rtype = _NN(_REIFIES)
        for g, subs in by_sg.items():
            for r, preds in subs.items():
                rs = preds.get(rtype)
                if not rs or len(rs) != 1 or not isinstance(rs[0], _TRIPLE) or (g, r) in nofold:
                    continue
                tt = rs[0]
                if isinstance(r, _BN):
                    if r in self.ttref or r in self.gref or self.subj_graphs[r] != {g} or r in self.list_cells:
                        continue
                    n = self.objrefs[r]
                    others = len(preds) > 1
                else:
                    n = 0
                    others = len(preds) > 1
                asserted = self._base_printable(g, tt)
                if n == 0 and asserted:
                    kind = "annot"
                elif n == 0 and others:
                    kind = "subj"
                elif n == 1 and not others and isinstance(r, _BN) and self._inline_candidate(r):
                    kind = "obj"
                else:
                    continue
                self.fold_kind[(g, r)] = kind
                self.fold_tt[(g, r)] = tt
                if kind == "annot":
                    self.annot[(g, tt.subject, tt.predicate, tt.object)].append(r)
        self._inline_cache = {}

    def _base_printable(self, g: Any, tt: Any) -> bool:
        """Is the triple ``tt`` asserted in graph ``g`` and written as an ordinary statement (not folded into a list)?"""
        s = tt.subject
        if s in self.list_cells or not isinstance(s, (_NN, _BN)):
            return False
        return tt.object in self.by_sg.get(g, {}).get(s, {}).get(tt.predicate, ())

    def _inline_candidate(self, b: Any) -> bool:
        hit = self._inline_cache.get(b)
        if hit is None:
            hit = False
            if (isinstance(b, _BN) and self.objrefs.get(b) == 1 and b not in self.ttref and b not in self.gref
                    and b not in self.noinline and b not in self.list_cells and b not in self.list_heads):
                g = self.ref_of[b][2]
                hit = self.subj_graphs.get(b, {g}) <= {g}
            self._inline_cache[b] = hit
        return hit

    # ---- terms ---------------------------------------------------------------------------------------------------------
    def label(self, b: Any) -> str:
        lab = self.labels.get(b)
        if lab is None:
            if self.keep_labels and _BNODE_LABEL.fullmatch(b.value):
                lab = "_:" + b.value
            else:
                lab = f"_:b{len(self.labels)}"
            self.labels[b] = lab
        return lab

    def literal(self, t: Any, short: bool = False) -> str:
        v = t.value
        dt = t.datatype.value
        if t.language is not None:
            suffix = "@" + t.language + (f"--{t.direction}" if t.direction is not None else "")
            return self._quoted(v, short) + suffix
        if dt == _XSD + "boolean" and v in ("true", "false"):
            return v
        if (dt == _XSD + "integer" and _INTEGER_RE.fullmatch(v)) or (dt == _XSD + "decimal" and _DECIMAL_RE.fullmatch(v)) \
                or (dt == _XSD + "double" and _DOUBLE_RE.fullmatch(v)):
            return v
        if dt == _XSD_STRING:
            return self._quoted(v, short)
        return f"{self._quoted(v, short)}^^{self.names.iri(dt)}"

    def _quoted(self, v: str, short: bool = False) -> str:
        # (inside a triple term the short form is always used: Oxigraph's parser rejects a long string there)
        if not short and ("\n" in v or "\r" in v):
            e = v.replace("\\", "\\\\").replace("\r", "\\r")
            # a run of 3+ quotes, or any run at the end, would meet the closing delimiter: escape those runs
            e = re.sub(r'"+', lambda m: '\\"' * len(m.group()) if len(m.group()) >= 3 or m.end() == len(e) else m.group(), e)
            return '"""' + _CONTROL.sub(lambda m: f"\\u{ord(m.group()):04X}", e) + '"""'
        e = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return '"' + _CONTROL.sub(lambda m: f"\\u{ord(m.group()):04X}", e) + '"'

    def flat(self, t: Any, *, nil_ok: bool = False, short: bool = False) -> str:
        """A term with no layout: IRI, label, literal, or a triple term ``<<( s p o )>>``."""
        if isinstance(t, _NN):
            if nil_ok and t.value == _NIL:
                return "()"
            return self.names.iri(t.value)
        if isinstance(t, _BN):
            return self.label(t)
        if isinstance(t, _LIT):
            return self.literal(t, short)
        return f"<<( {self.flat(t.subject)} {self.flat(t.predicate)} {self.flat(t.object, short=True)} )>>"

    def reified(self, tt: Any, reifier: Any = None) -> str:
        """``<< s p o >>`` or ``<< s p o ~ r >>`` (the reified-triple syntax)."""
        tail = f" ~ {self.flat(reifier)}" if reifier is not None else ""
        return f"<< {self.flat(tt.subject)} {self.flat(tt.predicate)} {self.flat(tt.object, short=True)}{tail} >>"

    def pred(self, p: Any) -> str:
        if p.value == _TYPE:
            return "a"
        return self.flat(p)

    def node(self, t: Any, g: Any, ind: str) -> str:
        """An object: a plain term, or ``[ ... ]``, ``( ... )`` or ``<< s p o >>`` for what was folded into it."""
        if isinstance(t, _BN):
            if t in self.list_heads:
                self.printed.add(t)
                return self.list_text(self.list_heads[t], g, ind)
            if self._inline_candidate(t):
                if (g, t) in self.fold_kind and self.fold_kind[(g, t)] == "obj":
                    self.printed.add((g, t))
                    return self.reified(self.fold_tt[(g, t)])
                self.printed.add(t)
                return self.bracket(t, g, ind)
            return self.label(t)
        return self.flat(t, nil_ok=True)

    def list_text(self, items: list[Any], g: Any, ind: str) -> str:
        parts = [self.node(i, g, ind + _INDENT) for i in items]
        one = "( " + " ".join(parts) + " )"
        if self.width and len(ind) + len(one) > self.width and len(parts) > 1 or any("\n" in p for p in parts):
            return "(\n" + "\n".join(f"{ind}{_INDENT}{p}" for p in parts) + f"\n{ind})"
        return one

    def bracket(self, b: Any, g: Any, ind: str) -> str:
        items = self.prop_items(g, b, ind + _INDENT)
        if not items:
            return "[]"
        body = " ;\n".join(f"{ind}{_INDENT}{i}" for i in items)
        return f"[\n{body}\n{ind}]"

    def prop_items(self, g: Any, s: Any, ind: str, *, skip_reifies: bool = False) -> list[str]:
        """``["pred obj, obj", ...]`` for subject ``s`` in graph ``g``; nested layouts are indented from ``ind``."""
        preds = self.by_sg[g][s]
        order = sorted(preds, key=lambda p: (0 if p.value == _TYPE else 1, p.value))
        out = []
        for p in order:
            objs = preds[p]
            if skip_reifies and p.value == _REIFIES:
                objs = [o for o in objs if o != self.fold_tt.get((g, s))]
                if not objs:
                    continue
            texts = []
            for o in (sorted(objs, key=self.key) if len(objs) > 1 else objs):
                text = self.node(o, g, ind)
                if self.annot:
                    text += self.annotations(g, s, p, o, ind)
                texts.append(text)
            out.append(f"{self.pred(p)} {self.join(texts, ind)}")
        return out

    def join(self, texts: list[str], ind: str) -> str:
        one = ", ".join(texts)
        if self.width and len(texts) > 1 and "\n" not in one and len(ind) + len(one) > self.width:
            return (",\n" + ind + _INDENT).join(texts)
        return one

    def annotations(self, g: Any, s: Any, p: Any, o: Any, ind: str) -> str:
        rs = self.annot.get((g, s, p, o))
        if not rs:
            return ""
        # a bare reifier (``~`` or ``~ :r``) must not be followed by an anonymous block, which would attach to it: bare ones last
        infos = []
        for r in rs:
            self.printed.add((g, r))
            inner = self.prop_items(g, r, ind + _INDENT, skip_reifies=True)
            infos.append((0 if inner and isinstance(r, _BN) else 1 if inner else 2, self.key(r), r, inner))
        infos.sort(key=lambda i: i[:2])
        out = []
        for _c, _k, r, inner in infos:
            named = isinstance(r, _NN)
            head = f"~ {self.flat(r)}" if named else "~"
            if not inner:
                out.append(head)
            else:
                if any("\n" in i for i in inner):  # a nested [ ... ] inside: one annotation per line
                    block = "{|\n" + " ;\n".join(f"{ind}{_INDENT}{i}" for i in inner) + f"\n{ind}|}}"
                else:
                    block = "{| " + " ; ".join(inner) + " |}"
                out.append((head + " " if named else "") + block)
        return " " + " ".join(out)

    # ---- statements ----------------------------------------------------------------------------------------------------
    def statements(self, g: Any, bi: str) -> list[str]:
        subs = self.by_sg.get(g, {})
        roots: list[tuple[tuple, Any, Any]] = []
        for s in subs:
            if (g, s) in self.fold_kind and self.fold_kind[(g, s)] != "subj":
                continue
            if isinstance(s, _BN) and (self._inline_candidate(s) or s in self.list_cells or s in self.list_heads):
                continue
            if self.fold_kind.get((g, s)) == "subj":
                roots.append(((3, self.key(self.fold_tt[(g, s)]), self.key(s)), s, "subj"))
            else:
                roots.append((self.key(s), s, None))
        roots.sort(key=lambda r: r[0])
        out = []
        for _k, s, kind in roots:
            ind = bi + _INDENT
            if kind == "subj":
                self.printed.add((g, s))
                tt = self.fold_tt[(g, s)]
                head = self.reified(tt, s if isinstance(s, _NN) else None)
                items = self.prop_items(g, s, ind, skip_reifies=True)
            else:
                head = self.flat(s, nil_ok=True) if not isinstance(s, _BN) else self.label(s)
                items = self.prop_items(g, s, ind)
            if not items:
                continue
            first = f"{bi}{head} {items[0]}"
            rest = [f"{ind}{i}" for i in items[1:]]
            out.append(" ;\n".join([first, *rest]) + " .")
            out.append("")
        return out

    # ---- document ------------------------------------------------------------------------------------------------------
    def unreached(self) -> bool:
        """Demote what a pass did not reach (a cycle of inline blank nodes, a reifier inside its own annotation)."""
        again = False
        for head in self.list_heads:
            if head not in self.printed:
                again = True
                node = head
                while node in self.list_cells and node not in self.nolist:
                    self.nolist.add(node)
                    self.noinline.add(node)
                    rest = self.by_sg[self.ref_of[node][2]][node][_NN(_REST)][0]
                    node = rest
        for b in list(self.objrefs):
            if self._inline_candidate(b) and b not in self.printed and (self.ref_of[b][2], b) not in self.printed:
                self.noinline.add(b)
                again = True
        for key in self.fold_kind:
            if key not in self.printed:
                self.nofold.add(key)
                again = True
        return again

    def render(self) -> tuple[str, bool]:
        self.noinline: set = set()
        self.nolist: set = set()
        self.nofold: set = set()
        graphs = sorted(self.by_sg, key=lambda g: (0,) if g == _DEFAULT else (1, *self.key(g)))
        for _round in range(6):
            self._plan()
            self.names.reset()
            self.labels: dict[Any, str] = {}
            self.printed: set = set()
            body: list[str] = []
            for g in graphs:
                if g == _DEFAULT or not self.trig:
                    body.extend(self.statements(g, ""))
                else:
                    inner = self.statements(g, _INDENT)
                    while inner and inner[-1] == "":
                        inner.pop()
                    body.append(f"GRAPH {self.flat(g)} {{")
                    body.extend(inner)
                    body.append("}")
                    body.append("")
            if not self.unreached():
                return "\n".join(body), True
        raise AssertionError("pretty writer did not converge")  # pragma: no cover


def _header(w: _Writer, only_used: bool) -> list[str]:
    names = w.names
    lines = []
    if w.v12:
        lines.append('@version "1.2" .')
    if names.base:
        lines.append(f"@base <{names.base}> .")
    for prefix, ns in names.pairs:
        if only_used or prefix in names.auto:
            if prefix not in names.used:
                continue
        lines.append(f"@prefix {prefix}: <{ns}> .")
    return lines


def _render(data: Any, *, prefixes: Mapping[str, Any] | None, base_iri: str | None, only_used: bool, width: int | None,
            keep_bnode_labels: bool, graph: Any, trig: bool) -> str:
    gc_was = gc.isenabled()
    gc.disable()  # millions of short-lived objects: the cyclic collector only slows the run down (about 25%)
    try:
        return _render_inner(data, prefixes, base_iri, only_used, width, keep_bnode_labels, graph, trig)
    finally:
        if gc_was:
            gc.enable()


def _render_inner(data: Any, prefixes: Mapping[str, Any] | None, base_iri: str | None, only_used: bool, width: int | None,
                  keep_bnode_labels: bool, graph: Any, trig: bool) -> str:
    quads, carried = _collect(data, graph)
    if not trig:
        if graph is ...:
            if any(q[0] != _DEFAULT for q in quads):
                raise ValueError("the data has named graphs: use pretty_trig, or select one with graph=")
        else:  # the one selected graph, as a plain graph
            quads = [(_DEFAULT, *q[1:]) for q in quads]
    names = _Names(carried if prefixes is None else prefixes, base_iri)
    w = _Writer(quads, names, width=width, keep_labels=keep_bnode_labels, trig=trig)
    body, _ = w.render()
    head = _header(w, only_used)
    text = "\n".join(head) + ("\n\n" if head else "") + body
    return text.rstrip("\n") + "\n" if text.strip() else ""


def pretty_turtle(data: Any, *, prefixes: Mapping[str, Any] | None = None, base_iri: str | None = None, only_used_prefixes: bool = True,
                  width: int | None = 100, keep_bnode_labels: bool = False, graph: Any = ...) -> str:
    """Pretty Turtle 1.2 for a graph. ``data`` is a Store / Dataset / StarLayerGraph / StarLayerDataset or an iterable of Quad / Triple;
    ``prefixes`` defaults to the ones ``data`` carries (an StarLayerGraph's); ``graph`` picks one graph (None: the default graph) of data
    that has several, otherwise named graphs raise ``ValueError``. See the module docstring for the layout."""
    return _render(data, prefixes=prefixes, base_iri=base_iri, only_used=only_used_prefixes, width=width,
                   keep_bnode_labels=keep_bnode_labels, graph=graph, trig=False)


def pretty_trig(data: Any, *, prefixes: Mapping[str, Any] | None = None, base_iri: str | None = None, only_used_prefixes: bool = True,
                width: int | None = 100, keep_bnode_labels: bool = False) -> str:
    """Pretty TriG 1.2 for a dataset: the default graph unwrapped, each named graph in a ``GRAPH name { ... }`` block."""
    return _render(data, prefixes=prefixes, base_iri=base_iri, only_used=only_used_prefixes, width=width,
                   keep_bnode_labels=keep_bnode_labels, graph=..., trig=True)


def serialize_pretty(data: Any, fmt: ox.RdfFormat, prefixes: Mapping[str, Any] | None, base: str | None, only_used: bool,
                     pretty: Any) -> str:
    """The hook ``StarLayerGraph.serialize(pretty=...)`` calls: ``pretty`` is True or "turtle"."""
    if pretty not in (True, "turtle"):
        raise ValueError(f"unknown pretty style {pretty!r}: use True")
    fn = pretty_trig if fmt == ox.RdfFormat.TRIG else pretty_turtle
    if fmt not in (ox.RdfFormat.TURTLE, ox.RdfFormat.TRIG):
        raise ValueError("pretty output is Turtle or TriG only")
    return fn(data, prefixes=prefixes, base_iri=base, only_used_prefixes=only_used)
