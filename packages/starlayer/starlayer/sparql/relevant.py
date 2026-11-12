"""The relevant subgraph of a SPARQL query: the triples of a graph that the query's answer depends on.

``relevant_subgraph(graph, query)`` returns a ``StarLayerGraph`` ``F`` of triples taken from ``graph`` such that the query gives the
same answer on ``F`` as on ``graph``: the same solutions (with their multiplicity) for ``SELECT``, the same truth value for
``ASK``, the same triples for ``CONSTRUCT``. Oxigraph cannot report the triples a query read, so they are computed by queries:

* the **supports**: ``CONSTRUCT`` the query's own triple patterns over the query's own ``WHERE`` group. Every triple that took part
  in a solution is one of the instantiated patterns (a pattern inside an ``OPTIONAL`` that did not match instantiates only if
  all its variables are bound, and a triple that is not in the graph is dropped);
* the **evidence of absence and exclusion**: ``FILTER (NOT) EXISTS`` and ``MINUS`` depend on triples that are *not* part of a
  solution. The group is relaxed (those parts removed), so the solutions they excluded are found too; each excluded solution
  keeps the triples of the excluded group's patterns that matched it, the ones that excluded it. A solution that was not
  excluded has no such match in the graph, and none in a subgraph either.

Solution modifiers (``ORDER BY``, ``LIMIT``, ``OFFSET``, ``GROUP BY``, ``HAVING``, projection, ``DISTINCT``) are not applied: the
subgraph holds the support of every solution of the group, so they give the same result on it. Pre-bound variables
(``init_bindings``) apply to every query.

Not computable this way: a property path (its edges are not template triples), a sub-select, ``GRAPH``, ``SERVICE``, a blank node
or a triple term in a pattern, ``EXISTS`` anywhere but a plain group (not inside ``OPTIONAL``) or outside the ``WHERE`` group. For
those the result is every triple that matches some triple pattern of the query (constants and pre-bound variables fixed, other
variables free; a blank node in a pattern is a variable): larger, never smaller. ``relevant_triples`` returns which was used.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pyoxigraph as ox

from starlayer.sparql.parse_sparql import Node, Tok, parse_sparql, tokenize

_Triple = tuple[Any, Any, Any]

#: ``run(construct_text)`` -> the triples a CONSTRUCT query returns
Runner = Callable[[str], Iterable[Any]]  # ``None`` where a runner is taken: no support queries can run, use the pattern fallback


class _NotComputable(Exception):
    """The query uses a construct the support queries cannot follow; the pattern fallback is used."""


def relevant_subgraph(
    graph: Any, query: str, init_bindings: Mapping[str, Any] | None = None, init_ns: Mapping[str, str] | None = None
) -> Any:
    """The relevant subgraph of ``query`` in ``graph`` (see the module docstring), as a ``StarLayerGraph``. ``init_ns`` (prefix to
    namespace) declares prefixes the query text does not, as ``StarLayerGraph.query(initNs=...)`` does.

    Raises ``SparqlSyntaxError`` for text that is not a query, and ``ValueError`` for an update or a ``DESCRIBE``."""
    from starlayer.graph.oxgraph import StarLayerGraph

    bindings = dict(init_bindings or {})
    if init_ns:
        query = "".join(f"PREFIX {p}: <{ns}> " for p, ns in init_ns.items()) + query

    def run(text: str) -> Iterable[Any]:
        return graph.query(text, initBindings=bindings)

    triples, _exact = relevant_triples(graph, query, bindings, run)
    out = StarLayerGraph()
    for t in triples:
        out.add(t)
    return out


def relevant_triples(
    graph: Any, query: str, init_bindings: Mapping[str, Any], run: Runner | None
) -> tuple[set[_Triple], bool]:
    """``(triples, supported)``: the relevant triples, and whether the support queries were used (else the pattern fallback)."""
    ast = parse_sparql(query)
    if ast.kind not in ("SelectQuery", "AskQuery", "ConstructQuery"):
        raise ValueError(f"relevant_subgraph needs a SELECT, ASK or CONSTRUCT query, not {ast.kind}")
    if run is None:
        return _pattern_triples(graph, ast, init_bindings), False
    try:
        return _supports(graph, query, ast, run), True
    except _NotComputable:
        return _pattern_triples(graph, ast, init_bindings), False


# ---------------------------------------------------------------------------------------------------- the support queries


def _match(toks: list[Tok], open_index: int) -> int:
    """The index of the bracket closing the one at ``open_index`` (``{`` / ``(`` / ``[``)."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    depth = 0
    for j in range(open_index, len(toks)):
        t = toks[j]
        if t.kind == "P" and t.text in pairs:
            depth += 1
        elif t.kind == "P" and t.text in ("}", ")", "]"):
            depth -= 1
            if depth == 0:
                return j
    raise _NotComputable("unbalanced brackets")


def _word(tok: Tok) -> str:
    return tok.text.upper() if tok.kind == "W" else ""


def _where_group(toks: list[Tok]) -> tuple[int, int]:
    """The token indexes of the braces of the query's ``WHERE`` group."""
    depth = 0
    first_brace = None
    for i, t in enumerate(toks):
        if t.kind == "P" and t.text in ("{", "("):
            if t.text == "{" and depth == 0 and first_brace is None:
                first_brace = i
            depth += 1
        elif t.kind == "P" and t.text in ("}", ")"):
            depth -= 1
        elif depth == 0 and _word(t) == "WHERE" and i + 1 < len(toks) and toks[i + 1].text == "{":
            return i + 1, _match(toks, i + 1)
    if first_brace is None:
        raise _NotComputable("no WHERE group")
    return first_brace, _match(toks, first_brace)


def _filter_end(toks: list[Tok], i: int) -> int:
    """The index of the last token of the ``FILTER`` constraint starting at ``i``."""
    j = i + 1
    if _word(toks[j]) == "NOT":
        j += 1
    if _word(toks[j]) == "EXISTS":
        return _match(toks, j + 1)
    while not (toks[j].kind == "P" and toks[j].text == "("):  # a built-in call or a function IRI, then its arguments
        j += 1
    return _match(toks, j)


class _Parts:
    """What the scan of the ``WHERE`` group found: spans to cut, and the groups whose matches are evidence."""

    def __init__(self) -> None:
        self.cuts: list[tuple[int, int]] = []  # (first token, last token)
        self.evidence: list[str] = []  # the text of each excluded group, braces included


def _scan(query: str, toks: list[Tok], lo: int, hi: int) -> _Parts:
    parts = _Parts()
    stack: list[str] = []
    i = lo + 1
    while i < hi:
        t = toks[i]
        word = _word(t)
        if word in ("GRAPH", "SERVICE", "SELECT"):
            raise _NotComputable(word)
        if t.kind == "BNODE" or (t.kind == "P" and t.text == "["):
            raise _NotComputable("blank node in a pattern")
        if t.kind == "P" and t.text == "{":
            prev = _word(toks[i - 1])
            stack.append("optional" if prev == "OPTIONAL" else "plain")
        elif t.kind == "P" and t.text == "}":
            stack.pop()
        elif word in ("FILTER", "MINUS"):
            end = _match(toks, i + 1) if word == "MINUS" else _filter_end(toks, i)
            span = toks[i : end + 1]
            has_exists = word == "MINUS" or any(_word(s) == "EXISTS" for s in span)
            if has_exists:
                if "optional" in stack:
                    raise _NotComputable("EXISTS or MINUS inside OPTIONAL")
                parts.cuts.append((i, end))
                for k in range(i, end + 1):
                    if _word(toks[k]) == "EXISTS" or (word == "MINUS" and k == i):
                        inner_open = k + 1
                        inner_close = _match(toks, inner_open)
                        inner = toks[inner_open : inner_close + 1]
                        if any(_word(s) in ("EXISTS", "MINUS", "OPTIONAL", "SELECT", "GRAPH", "SERVICE") for s in inner[1:-1]):
                            raise _NotComputable("nested negation or OPTIONAL inside an EXISTS / MINUS group")
                        parts.evidence.append(query[inner[0].pos : inner[-1].pos + 1])
                i = end
        i += 1
    return parts


def _term_text(term: Any) -> str:
    if isinstance(term, ox.Variable):
        return f"?{term.value}"
    if isinstance(term, (ox.NamedNode, ox.Literal)):
        return str(term)  # N-Triples form
    raise _NotComputable("blank node or triple term in a pattern")


def _patterns(ast: Node) -> tuple[list[str], set[ox.NamedNode]]:
    """The triple-pattern template lines of a parsed group, and the predicates of its property-path patterns."""
    lines: list[str] = []
    path_predicates: set[ox.NamedNode] = set()

    def walk(item: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "SubSelect":
                raise _NotComputable("sub-select")
            if item.kind == "TriplePattern":
                p = item.f["p"]
                if isinstance(p, Node):
                    path_predicates.update(_path_iris(p))
                else:
                    lines.append(f"{_term_text(item.f['s'])} {_term_text(p)} {_term_text(item.f['o'])} .")
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(ast)
    return list(dict.fromkeys(lines)), path_predicates


def _path_iris(path: Node) -> set[ox.NamedNode]:
    out: set[ox.NamedNode] = set()

    def walk(item: Any) -> None:
        if isinstance(item, ox.NamedNode):
            out.add(item)
        elif isinstance(item, Node):
            if item.kind in ("NegatedPropertySet", "NegPropertySet"):
                raise _NotComputable("negated property set")
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(path)
    return out


def _supports(graph: Any, query: str, ast: Node, run: Runner) -> set[_Triple]:
    toks = tokenize(query)
    lo, hi = _where_group(toks)
    if any(_word(t) in ("EXISTS", "FROM") for k, t in enumerate(toks) if k < lo or k > hi):
        raise _NotComputable("EXISTS outside the WHERE group, or a dataset clause")
    form = next(k for k, t in enumerate(toks) if _word(t) in ("SELECT", "ASK", "CONSTRUCT"))
    prologue = query[: toks[form].pos]

    parts = _scan(query, toks, lo, hi)
    pieces: list[str] = []
    cursor = toks[lo].pos + 1
    for first, last in sorted(parts.cuts):
        pieces.append(query[cursor : toks[first].pos])
        cursor = toks[last].pos + len(toks[last].text)
    pieces.append(query[cursor : toks[hi].pos])
    relaxed = "".join(pieces)

    def parsed(group_text: str) -> Node:
        return parse_sparql(f"{prologue} SELECT * WHERE {{ {group_text} }}")

    body_lines, path_predicates = _patterns(parsed(relaxed))
    queries: list[str] = []
    if body_lines:
        queries.append(f"{prologue} CONSTRUCT {{ {' '.join(body_lines)} }} WHERE {{ {{ {relaxed} }} }}")
    for group in parts.evidence:
        inner_lines, inner_paths = _patterns(parsed(group))
        path_predicates |= inner_paths
        if inner_lines:
            queries.append(f"{prologue} CONSTRUCT {{ {' '.join(inner_lines)} }} WHERE {{ {{ {relaxed} }} {group} }}")

    found: set[_Triple] = set()
    for text in queries:
        for t in run(text):
            triple = (t[0], t[1], t[2])
            if triple in graph:
                found.add(triple)
    for predicate in path_predicates:
        found.update((t[0], t[1], t[2]) for t in graph.triples((None, predicate, None)))
    return found


# ------------------------------------------------------------------------------------------------------ the fallback


def _pattern_triples(graph: Any, ast: Node, bindings: Mapping[str, Any]) -> set[_Triple]:
    """Every triple of ``graph`` that matches some triple pattern of the query (a superset of what the query reads)."""
    patterns: list[Node] = []

    def walk(item: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "TriplePattern":
                patterns.append(item)
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(ast)

    def fixed(term: Any) -> Any:
        if isinstance(term, (ox.NamedNode, ox.Literal)):
            return term
        if isinstance(term, ox.Variable) and term.value in bindings:
            return bindings[term.value]
        return None  # a free variable, a path, a triple term: any

    reads: set[_Triple] = set()
    for pattern in patterns:
        s, p, o = (fixed(pattern.f.get(k)) for k in ("s", "p", "o"))
        reads.update((t[0], t[1], t[2]) for t in graph.triples((s, p, o)))
    return reads
