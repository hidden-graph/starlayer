"""The relevant subgraph of a SPARQL query: the triples of a graph that the query's answer depends on.

``graph.relevant_subgraph(query)`` returns a ``StarLayerGraph`` ``F`` of triples taken from ``graph`` such that the query gives the
same answer on ``F`` as on ``graph``: the same solutions (with their multiplicity) for ``SELECT``, the same truth value for
``ASK``, the same triples for ``CONSTRUCT``. Oxigraph cannot report the triples a query read, so they are computed by queries:

* the **supports**: ``CONSTRUCT`` the query's own triple patterns over the query's own ``WHERE`` group. Every triple that took part
  in a solution is one of the instantiated patterns (a pattern inside an ``OPTIONAL`` that did not match instantiates only if
  all its variables are bound, and a triple that is not in the graph is dropped);
* the **evidence of absence and exclusion**: ``FILTER (NOT) EXISTS`` and ``MINUS`` depend on triples that are *not* part of a
  solution. The group is relaxed (those parts removed), so the solutions they excluded are found too; each excluded solution
  keeps the triples of the excluded group's patterns that matched it, the ones that excluded it. A negation is evaluated against the
  solutions of the group it sits in (for a ``FILTER`` in an ``OPTIONAL``: the row the left side and the group make), not against the whole
  row, so the excluded group is joined with that group's relaxed text: a variable bound only outside the group does not constrain it. A solution that was not
  excluded has no such match in the graph, and none in a subgraph either.

A ``FILTER`` that tests whether a variable is bound (``BOUND``, ``COALESCE``, ``IF``) is relaxed as well, with no group to keep:
a row it excluded keeps the optional triples that made its variable bound, otherwise dropping them would let the row pass.

The result is reproducible: no step chooses. Every way the answer can be derived is kept (two paths that reach the same node both stay,
every triple that makes a node exist stays), so the same query and graph give the same set whatever order the store lists triples in.

Solution modifiers (``ORDER BY``, ``LIMIT``, ``OFFSET``, ``GROUP BY``, ``HAVING``, projection, ``DISTINCT``) are not applied: the
subgraph holds the support of every solution of the group, so they give the same result on it. Pre-bound variables
(``init_bindings``) apply to every query.

Handled: property paths (the edges a walk of the path from the pattern's subject to its object takes, by ``CONSTRUCT`` over the
relaxed group joined with a guard that spells the walk out), sub-selects (the relevant triples of the sub-select as a query
of its own, for all its rows), ``EXISTS`` and ``MINUS`` inside ``OPTIONAL`` and ``UNION`` branches, blank nodes (labelled ones, ``[ ... ]`` and collections ``( ... )`` become variables
and triples). Not computable this way: ``GRAPH``, and ``EXISTS`` outside the ``WHERE`` group (``HAVING``, ``ORDER BY``, a projection). For those the result is every
triple that matches some triple pattern of the query (constants and pre-bound variables fixed, other variables free): larger,
never smaller. ``relevant_triples`` returns which was used.

A ``StarLayerDataset`` gives a ``StarLayerDataset`` of quads (``relevant_quads``). Each support query also says which graph its patterns were
read in: a pattern in ``GRAPH <g>`` or ``GRAPH ?g`` the graph it matched in, and a pattern outside any ``GRAPH`` block the default graph, or
every graph that holds the triple when the dataset is ``default_union`` (or the ``FROM`` graphs; ``FROM NAMED`` limits ``GRAPH ?g`` by the query
itself). A property path, and a negation (``FILTER (NOT) EXISTS``, ``MINUS``) inside a ``GRAPH`` block, are read in that graph. Not computable
on a dataset: a sub-select under a ``FROM`` clause (it reads a dataset its own queries would not name); that, and the other cases above, give
every quad that matches a pattern in a graph the pattern can read.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError
from starlayer.sparql.parse_sparql import (
    Node,
    Tok,
    collections_of,
    parse_sparql,
    tokenize,
)

_Triple = tuple[Any, Any, Any]

#: ``run(construct_text)`` -> the triples a CONSTRUCT query returns
Runner = Callable[[str], Iterable[Any]]  # ``None`` where a runner is taken: no support queries can run, use the pattern fallback


class _NotComputable(Exception):
    """The query uses a construct the support queries cannot follow; the pattern fallback is used."""


def relevant_subgraph(
    graph: Any, query: str, init_bindings: Mapping[str, Any] | None = None, init_ns: Mapping[str, str] | None = None
) -> Any:
    """The triples of ``graph`` that the answer of ``query`` depends on, as a new ``StarLayerGraph``; for a ``StarLayerDataset`` the
    quads, as a new ``StarLayerDataset`` with the same ``default_union``.

    Every derivation is kept and nothing is chosen between them (see the module docstring). ``init_ns`` (prefix to namespace)
    declares prefixes the query text does not, as ``StarLayerGraph.query(initNs=...)`` does.

    Raises ``FormatError`` (kind ``"sparql"``) for text that is not a query, and ``ValueError`` for an update, and ``ExecutionError`` (kind ``"unsupported"``) for a ``DESCRIBE`` or
    a ``SERVICE`` (valid queries the function cannot answer: a ``SERVICE`` depends on a remote graph, so it cannot be reproduced from a
    subgraph of this one)."""
    from starlayer.graph import StarLayerDataset, StarLayerGraph

    bindings = dict(init_bindings or {})
    if init_ns:
        query = "".join(f"PREFIX {p}: <{ns}> " for p, ns in init_ns.items()) + query

    if isinstance(graph, StarLayerDataset):
        quads, _exact = relevant_quads(graph, query, bindings)
        out_dataset = StarLayerDataset(default_union=graph.default_union)
        out_dataset.store.extend(sorted(quads, key=repr))  # a fixed insertion order
        return out_dataset

    def run(text: str) -> Iterable[Any]:
        return graph.query(text, initBindings=bindings)

    triples, _exact = relevant_triples(graph, query, bindings, run)
    out = StarLayerGraph()
    for t in sorted(triples, key=repr):  # a fixed insertion order too
        out.add(t)
    return out


def relevant_quads(dataset: Any, query: str, init_bindings: Mapping[str, Any]) -> tuple[set[ox.Quad], bool]:
    """``(quads, supported)`` for a dataset: the relevant quads, and whether the support queries were used (else the pattern fallback).

    Each support query also says which graph each triple was read from: a pattern in ``GRAPH <g>`` or ``GRAPH ?g`` the graph it
    matched in, and a pattern outside any ``GRAPH`` block the default graph, or every graph that holds the triple when the dataset
    is ``default_union`` (or the ``FROM`` graphs). A triple held in several graphs that the query reads as one is kept in all of them.
    """
    return relevant_triples(dataset, query, init_bindings, lambda text: dataset.query(text, initBindings=init_bindings))  # type: ignore[return-value]


def _is_dataset(target: Any) -> bool:
    from starlayer.graph import StarLayerDataset

    return isinstance(target, StarLayerDataset)


def _parse_checked(query: str) -> Node:
    """The parsed query, which has to be a SELECT, ASK or CONSTRUCT without ``SERVICE``."""
    ast = parse_sparql(query)
    if ast.kind == "DescribeQuery":
        raise ExecutionError("relevant_subgraph does not support DESCRIBE: what a DESCRIBE returns is chosen by the store, not by the patterns of the query",
                             kind="unsupported", context="relevant_subgraph")
    if ast.kind not in ("SelectQuery", "AskQuery", "ConstructQuery"):
        raise ValueError(f"relevant_subgraph needs a SELECT, ASK or CONSTRUCT query, not {ast.kind}")
    if any(_word(t) == "SERVICE" for t in tokenize(query)):
        raise ExecutionError("relevant_subgraph does not support SERVICE: the answer depends on a remote graph that no subgraph of this one holds",
                             kind="unsupported", context="relevant_subgraph")
    return ast


def relevant_triples(
    graph: Any, query: str, init_bindings: Mapping[str, Any], run: Runner | None
) -> tuple[set[_Triple], bool]:
    """``(triples, supported)``: the relevant triples, and whether the support queries were used (else the pattern fallback)."""
    ast = _parse_checked(query)
    fallback = _pattern_quads if _is_dataset(graph) else _pattern_triples
    if run is None:
        return fallback(graph, ast, init_bindings), False
    try:
        return _supports(graph, query, ast, run, init_bindings), True
    except _NotComputable:
        return fallback(graph, ast, init_bindings), False


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


#: functions whose result differs for an unbound variable and a bound one: a filter using them tests for absence
_ABSENCE_TESTS = {"BOUND", "COALESCE", "IF"}


class _Parts:
    """What the scan of the ``WHERE`` group found: spans to cut, and the groups whose matches are evidence."""

    def __init__(self) -> None:
        self.cuts: list[tuple[int, int]] = []  # (first token, last token)
        # each group whose matches are evidence: ("filter" | "minus", token indexes of the braces of the group whose solutions it is
        # evaluated against, its text, the term text of the GRAPH block around it or None)
        self.evidence: list[tuple[str, int, int, str, str | None]] = []
        self.subselects: list[str] = []  # the text of each sub-select, from its SELECT to the end of its body


def _scan(query: str, toks: list[Tok], lo: int, hi: int, quads: bool = False) -> _Parts:
    parts = _Parts()
    stack: list[tuple[str, int]] = []  # (kind, index of the opening brace) of the groups around the token
    i = lo + 1
    while i < hi:
        t = toks[i]
        word = _word(t)
        if word in ("SERVICE", "SELECT") or (word == "GRAPH" and not quads):
            raise _NotComputable(word)
        if t.kind == "P" and t.text == "{" and _word(toks[i + 1]) == "SELECT":
            close = _match(toks, i)
            parts.subselects.append(query[toks[i + 1].pos : toks[close].pos])
            i = close
        elif t.kind == "P" and t.text == "{":
            prev = _word(toks[i - 1])
            in_graph = i >= 2 and _word(toks[i - 2]) == "GRAPH"
            stack.append(("graph" if in_graph else "optional" if prev == "OPTIONAL" else "plain", i))
        elif t.kind == "P" and t.text == "}":
            stack.pop()
        elif word in ("FILTER", "MINUS"):
            end = _match(toks, i + 1) if word == "MINUS" else _filter_end(toks, i)
            span = toks[i : end + 1]
            has_exists = word == "MINUS" or any(_word(s) == "EXISTS" for s in span)
            tests_absence = any(_word(s) in _ABSENCE_TESTS for s in span)
            if tests_absence and not has_exists:
                parts.cuts.append((i, end))  # relaxed like a negation, with no group of its own to keep
                i = end
            elif has_exists:
                parts.cuts.append((i, end))
                # The solutions the negation compares with. A FILTER sees the solutions of its own group, except in an OPTIONAL group,
                # where it is part of the left join and sees the row the left side and the group make together: the group around the
                # OPTIONAL. MINUS removes solutions of the group it sits in.
                around = stack[:-1] if (word == "FILTER" and stack and stack[-1][0] == "optional") else stack
                group_lo, group_hi = (around[-1][1], _match(toks, around[-1][1])) if around else (lo, hi)
                # the negation's group is read in the graph of the GRAPH block around it: the term before that block's brace
                graph_text = next((query[toks[b - 1].pos : toks[b - 1].pos + len(toks[b - 1].text)] for kind, b in reversed(around) if kind == "graph"), None)
                for k in range(i, end + 1):
                    if _word(toks[k]) == "EXISTS" or (word == "MINUS" and k == i):
                        inner_open = k + 1
                        inner_close = _match(toks, inner_open)
                        inner = toks[inner_open : inner_close + 1]
                        if any(_word(s) in ("EXISTS", "MINUS", "OPTIONAL", "SELECT", "GRAPH", "SERVICE") for s in inner[1:-1]):
                            raise _NotComputable("nested negation or OPTIONAL inside an EXISTS / MINUS group")
                        kind = "minus" if word == "MINUS" else "filter"
                        parts.evidence.append((kind, group_lo, group_hi, query[inner[0].pos : inner[-1].pos + 1], graph_text))
                i = end
        i += 1
    return parts


def _term_text(term: Any) -> str:
    if isinstance(term, ox.Variable):
        return f"?{term.value}"
    if isinstance(term, (ox.NamedNode, ox.Literal)):
        return str(term)  # N-Triples form
    raise _NotComputable("blank node or triple term in a pattern")


class _Fresh:
    """Variable names for the intermediate nodes of a path."""

    def __init__(self) -> None:
        self.n = 0

    def var(self) -> str:
        self.n += 1
        return f"?__pv{self.n}"


def _path_text(path: Any) -> str:
    if isinstance(path, ox.NamedNode):
        return str(path)
    if not isinstance(path, Node):
        raise _NotComputable("unknown path")
    k = path.kind
    if k == "PathInverse":
        return f"^({_path_text(path.f['arg'])})"
    if k == "PathSequence":
        return "(" + "/".join(_path_text(a) for a in path.f["args"]) + ")"
    if k == "PathAlternative":
        return "(" + "|".join(_path_text(a) for a in path.f["args"]) + ")"
    if k == "PathElt":
        return f"({_path_text(path.f['path'])}){path.f['mod']}"
    raise _NotComputable(f"path {k}")  # a negated property set: its edges are every edge but a few


_NODE_MARK = ox.NamedNode("urn:starlayer:relevant:node")


def _nullable(path: Any) -> bool:
    """True if the path can match with the same node at both ends (a zero-length walk)."""
    if isinstance(path, ox.NamedNode):
        return False
    k = path.kind
    if k == "PathInverse":
        return _nullable(path.f["arg"])
    if k == "PathSequence":
        return all(_nullable(a) for a in path.f["args"])
    if k == "PathAlternative":
        return any(_nullable(a) for a in path.f["args"])
    if k == "PathElt":
        return path.f["mod"] in ("*", "?") or _nullable(path.f["path"])
    return False


def _edges(path: Any, a: str, b: str, fresh: _Fresh) -> list[tuple[list[str], list[str]]]:
    """``(template triples as (subject, predicate, object) texts, guard conjuncts)`` pairs whose ``CONSTRUCT`` over a group joined with the guards gives the edges the path
    walks from ``a`` to ``b`` (term texts). The guards bind the intermediate variables the template uses and keep them on walks
    that really connect the endpoints."""
    if isinstance(path, ox.NamedNode):
        return [([(a, str(path), b)], [])]
    k = path.kind
    if k == "PathInverse":
        return _edges(path.f["arg"], b, a, fresh)
    if k == "PathSequence":
        steps = path.f["args"]
        nodes = [a] + [fresh.var() for _ in steps[:-1]] + [b]
        chain = [f"{nodes[i]} {_path_text(step)} {nodes[i + 1]} ." for i, step in enumerate(steps)]
        return [
            (template, guards + chain)
            for i, step in enumerate(steps)
            for template, guards in _edges(step, nodes[i], nodes[i + 1], fresh)
        ]
    if k == "PathAlternative":
        return [
            (template, guards + [f"{a} {_path_text(alt)} {b} ."])
            for alt in path.f["args"]
            for template, guards in _edges(alt, a, b, fresh)
        ]
    if k == "PathElt":
        inner = path.f["path"]
        if path.f["mod"] == "?":
            return [(t, g + [f"{a} {_path_text(inner)} {b} ."]) for t, g in _edges(inner, a, b, fresh)]
        x, y = fresh.var(), fresh.var()
        walk = [f"{a} ({_path_text(inner)})* {x} .", f"{x} {_path_text(inner)} {y} .", f"{y} ({_path_text(inner)})* {b} ."]
        return [(t, g + walk) for t, g in _edges(inner, x, y, fresh)]
    raise _NotComputable(f"path {k}")


def _patterns(
    ast: Node, graph: str | None = None
) -> tuple[list[tuple[str, str, str, str | None]], list[tuple[str, Any, str, str | None]]]:
    """The triple patterns of a parsed group as ``(subject, predicate, object, graph)`` texts, and its property-path patterns as
    ``(subject text, path, object text, graph)``; ``graph`` is the term of the ``GRAPH`` block around the pattern, else the given ``graph``."""
    lines: list[tuple[str, str, str, str | None]] = []
    paths: list[tuple[str, Any, str, str | None]] = []

    def walk(item: Any, graph: str | None) -> None:
        if isinstance(item, Node):
            if item.kind == "SubSelect":
                return  # its patterns belong to the sub-select's own support queries
            if item.kind == "TriplePattern":
                p = item.f["p"]
                s_text, o_text = _term_text(item.f["s"]), _term_text(item.f["o"])
                if isinstance(p, Node):
                    paths.append((s_text, p, o_text, graph))
                else:
                    lines.append((s_text, _term_text(p), o_text, graph))
            inner = _term_text(item.f["term"]) if item.kind == "Graph" else graph
            for value in item.f.values():
                walk(value, inner)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value, graph)

    walk(ast, graph)
    return list(dict.fromkeys(lines)), paths


#: the predicate of the template triple ``graph MARK <<( s p o )>>`` that a support query on a dataset gives for a pattern it read
_QUAD_MARK = ox.NamedNode("urn:starlayer:relevant:quad")
#: the graph of that triple for a pattern outside any ``GRAPH`` block
_DEFAULT_MARK = ox.NamedNode("urn:starlayer:relevant:default")


def _holders(dataset: Any, triple: _Triple, graph: Any, from_graphs: list[Any]) -> list[ox.Quad]:
    """The quads of ``dataset`` for a triple a support query read from ``graph`` (``_DEFAULT_MARK``: the graph the query reads by default)."""
    s, p, o = triple
    if graph != _DEFAULT_MARK:
        return list(dataset.quads((s, p, o, graph)))
    if from_graphs:
        return [q for name in from_graphs for q in dataset.quads((s, p, o, name))]
    return list(dataset.quads((s, p, o, None if dataset.default_union else ox.DefaultGraph())))


def _without_labelled_blank_nodes(query: str) -> str:
    """The query with each ``_:label`` written as a variable: in a pattern a blank node is a variable that is never projected, and
    as a variable the support queries can name it."""
    out, cursor = [], 0
    for t in tokenize(query):
        if t.kind == "BNODE":
            out.append(query[cursor : t.pos])
            out.append("?__bn_" + t.text[2:])
            cursor = t.pos + len(t.text)
    out.append(query[cursor:])
    return "".join(out)


def _mentions(graph: Any, node: Any) -> list[_Triple]:
    """Every triple of ``graph`` that has ``node`` as subject or object: each is a way for the node to exist in the graph, and the
    result must not depend on which one a store happens to list first."""
    return [(t[0], t[1], t[2]) for pattern in ((node, None, None), (None, None, node)) for t in graph.triples(pattern)]


def _quad_mentions(dataset: Any, node: Any, graph: Any, from_graphs: list[Any]) -> list[ox.Quad]:
    """``_mentions`` on a dataset: the quads that have ``node`` as subject or object in the graph the query read it from."""
    out: list[ox.Quad] = []
    for pattern in ((node, None, None), (None, None, node)):
        for q in _holders(dataset, (pattern[0], pattern[1], pattern[2]), graph, from_graphs):
            out.append(q)
    return out


_ELEMENT_WORDS = {"OPTIONAL", "MINUS", "FILTER", "BIND", "VALUES", "GRAPH", "SERVICE"}


def _statement_end(toks: list[Tok], after: int) -> int:
    """The index of the token that ends the triples statement a bracket or collection closing at ``after`` belongs to: the '.' or the
    token that starts the next element of the group (a keyword or a brace). Extra triples go in front of it."""
    for k in range(after + 1, len(toks)):
        t = toks[k]
        if (t.kind == "P" and t.text in (".", "{", "}")) or _word(t) in _ELEMENT_WORDS or t.kind == "EOF":
            return k
    raise _NotComputable("a pattern outside a group")


def _without_collections(query: str) -> str:
    """The query with each collection ``( a b )`` of a triples block written as a variable and its ``rdf:first`` / ``rdf:rest`` triples
    as statements of their own at the end of the statement it was in, as ``_without_anonymous_blank_nodes`` does for ``[ ]``."""
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    n = 0
    while True:
        toks = tokenize(query)
        lo, hi = _where_group(toks)
        inside = [c for c in collections_of(query) if toks[lo].pos < c[0] < toks[hi].pos]
        if not inside:
            return query
        open_at, spans, close_at = inside[0]  # the first to close has no collection inside it
        close_tok = next(i for i, t in enumerate(toks) if t.pos == close_at)
        items = [query[a:b] for a, b in spans]
        if not items:
            head, extra = f"<{rdf}nil>", ""
        else:
            names = [f"?__l{n + k + 1}" for k in range(len(items))]
            n += len(items)
            head = names[0]
            rest = names[1:] + [f"<{rdf}nil>"]
            extra = " . " + " . ".join(
                f"{name} <{rdf}first> {item} . {name} <{rdf}rest> {nxt}" for name, item, nxt in zip(names, items, rest, strict=True)
            )
        end = _statement_end(toks, close_tok)
        query = query[:open_at] + head + query[close_at + 1 : toks[end].pos] + extra + " " + query[toks[end].pos :]


def _without_anonymous_blank_nodes(query: str) -> str:
    """The query with each ``[ ... ]`` written as a variable and the properties inside it as a statement of their own, put at the
    end of the statement the bracket was in: ``?s :p [ :q ?o ] ; :r ?x .`` becomes ``?s :p ?v ; :r ?x . ?v :q ?o .``. (Collections,
    ``( ... )``, are left; their patterns carry blank nodes and take the fallback.)"""
    n = 0
    while True:
        toks = tokenize(query)
        opens = [i for i, t in enumerate(toks) if t.kind == "P" and t.text == "["]
        if not opens:
            return query
        i = opens[-1]  # the last bracket has no bracket inside it
        j = next(k for k in range(i + 1, len(toks)) if toks[k].kind == "P" and toks[k].text == "]")
        n += 1
        var = f"?__an{n}"
        inner = query[toks[i + 1].pos : toks[j].pos].strip()
        end = _statement_end(toks, j)
        extra = f" . {var} {inner}" if inner else ""
        query = (
            query[: toks[i].pos]
            + var
            + query[toks[j].pos + 1 : toks[end].pos]
            + extra
            + " "
            + query[toks[end].pos :]
        )


def _variables(text: str) -> set[str]:
    """The names of the variables a piece of query text mentions (``?x`` and ``$x`` are the same variable)."""
    return {t.text[1:] for t in tokenize(text) if t.kind == "VAR"}


def _supports(graph: Any, query: str, ast: Node, run: Runner, bindings: Mapping[str, Any]) -> set[Any]:
    """The triples of ``graph`` the support queries find; for a dataset (``quads``) the quads, each pattern read in the graph it names."""
    quads = _is_dataset(graph)
    query = _without_labelled_blank_nodes(_without_anonymous_blank_nodes(_without_collections(query)))
    toks = tokenize(query)
    lo, hi = _where_group(toks)
    form = next(k for k, t in enumerate(toks) if _word(t) in ("SELECT", "ASK", "CONSTRUCT"))
    prologue = query[: toks[form].pos]
    datasets = list(ast.f.get("datasets") or []) if quads else []  # (named, iri) of each FROM / FROM NAMED
    from_graphs = [iri for named, iri in datasets if not named]
    if any(_word(t) == "EXISTS" for k, t in enumerate(toks) if k < lo or k > hi) or (any(_word(t) == "FROM" for t in toks) and not quads):
        raise _NotComputable("EXISTS outside the WHERE group, or a dataset clause")
    if datasets and any(_word(toks[k]) == "SELECT" for k in range(lo + 1, hi)):
        raise _NotComputable("a sub-select under a FROM clause: it reads the same dataset, which its own queries would not name")
    if _word(toks[lo + 1]) == "SELECT":  # the whole body is a sub-select: its rows are the outer query's rows
        inner = prologue + query[toks[lo + 1].pos : toks[hi].pos]
        return relevant_triples(graph, inner, bindings, run)[0]

    parts = _scan(query, toks, lo, hi, quads)
    dataset_clause = " ".join(("FROM NAMED " if named else "FROM ") + str(iri) for named, iri in datasets)

    def cut_text(first_brace: int, last_brace: int) -> str:
        """The text between two braces with the relaxed parts (the cuts inside them) removed."""
        pieces: list[str] = []
        cursor = toks[first_brace].pos + 1
        for first, last in sorted(parts.cuts):
            if first_brace < first and last < last_brace:
                pieces.append(query[cursor : toks[first].pos])
                cursor = toks[last].pos + len(toks[last].text)
        pieces.append(query[cursor : toks[last_brace].pos])
        return "".join(pieces)

    relaxed = cut_text(lo, hi)

    def parsed(group_text: str) -> Node:
        return parse_sparql(f"{prologue} SELECT * WHERE {{ {group_text} }}")

    fresh = _Fresh()
    queries: list[str] = []

    def template(s: str, p: str, o: str, graph_text: str | None) -> str:
        """One template triple: the pattern itself, or on a dataset ``graph MARK <<( s p o )>>`` (a triple term is an object only)."""
        if not quads:
            return f"{s} {p} {o} ."
        return f"{graph_text or _DEFAULT_MARK} {_QUAD_MARK} <<( {s} {p} {o} )>> ."

    def construct(lines: list[str], where: str) -> str:
        return f"{prologue} CONSTRUCT {{ {' '.join(lines)} }} {dataset_clause} WHERE {{ {where} }}"

    def add(
        lines: list[tuple[str, str, str, str | None]], paths: list[tuple[str, Any, str, str | None]], where: str
    ) -> None:
        if lines:
            queries.append(construct([template(*line) for line in lines], where))
        for s_text, path, o_text, graph_text in paths:
            if _nullable(path):
                # a walk of length zero matches a node that is in the graph, so where the two ends are the same node it is one way
                # the row exists: the node has to stay in the graph
                mark = f"<{_NODE_MARK.value}>"
                queries.append(construct([template(mark, mark, s_text, graph_text)], f"{where} FILTER(sameTerm({s_text}, {o_text}))"))
            for edges, guards in _edges(path, s_text, o_text, fresh):
                guard_text = " ".join(guards)
                if graph_text is not None and guards:
                    guard_text = f"GRAPH {graph_text} {{ {guard_text} }}"  # the walk is read in the graph of its pattern
                queries.append(construct([template(*edge, graph_text) for edge in edges], f"{where} {guard_text}"))

    body_lines, body_paths = _patterns(parsed(relaxed))
    add(body_lines, body_paths, f"{{ {relaxed} }}")
    for kind, group_lo, group_hi, group, graph_text in parts.evidence:
        context = cut_text(group_lo, group_hi)
        if kind == "minus" and not _variables(group) & _variables("{" + context + "}"):
            continue  # MINUS compares on the variables shared with the group's solutions; with none shared it removes nothing
        inner_lines, inner_paths = _patterns(parsed(group), graph_text)
        where = f"{{ {context} }} {group}"
        add(inner_lines, inner_paths, f"GRAPH {graph_text} {{ {where} }}" if graph_text else where)

    found: set[Any] = set()
    nodes: list[tuple[Any, Any]] = []
    for text in queries:
        for t in run(text):
            if quads:
                inner = t[2]  # the triple term <<( s p o )>>
                triple, read_in = (inner.subject, inner.predicate, inner.object), t[0]
            else:
                triple, read_in = (t[0], t[1], t[2]), None
            if triple[1] == _NODE_MARK:
                nodes.append((triple[2], read_in))
            elif quads:
                found.update(_holders(graph, triple, read_in, from_graphs))
            elif triple in graph:
                found.add(triple)
    for node, read_in in nodes:  # a zero-length walk needs the node in the graph: every triple that mentions it is a way to have it
        found.update(_quad_mentions(graph, node, read_in, from_graphs) if quads else _mentions(graph, node))
    for sub in parts.subselects:
        found |= relevant_triples(graph, prologue + sub, bindings, run)[0]
    return found


# ------------------------------------------------------------------------------------------------------ the fallback


_DEFAULT = object()  #: the graph a pattern outside any ``GRAPH`` block reads


def _read_patterns(ast: Node) -> list[tuple[Node, Any]]:
    """Every triple pattern of the query with the graph it reads: ``_DEFAULT``, or the term of the ``GRAPH`` block around it."""
    found: list[tuple[Node, Any]] = []

    def walk(item: Any, graph: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "TriplePattern":
                found.append((item, graph))
            inner = item.f["term"] if item.kind == "Graph" else graph
            for value in item.f.values():
                walk(value, inner)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value, graph)

    walk(ast, _DEFAULT)
    return found


def _spo_patterns(pattern: Node, bindings: Mapping[str, Any]) -> list[tuple[Any, Any, Any]]:
    """The ``(s, p, o)`` patterns a triple pattern can read, ``None`` for any: constants and pre-bound variables are fixed."""

    def fixed(term: Any) -> Any:
        if isinstance(term, (ox.NamedNode, ox.Literal)):
            return term
        if isinstance(term, ox.Variable) and term.value in bindings:
            return bindings[term.value]
        return None  # a free variable, a path, a triple term: any

    if isinstance(pattern.f.get("p"), Node):  # a path walks through nodes the pattern does not name: every edge of its predicates
        predicates = [] if _nullable(pattern.f["p"]) else _path_predicates(pattern.f["p"])  # a zero-length walk: every node
        return [(None, predicate, None) for predicate in predicates or [None]]
    return [tuple(fixed(pattern.f.get(k)) for k in ("s", "p", "o"))]  # type: ignore[misc]


def _pattern_triples(graph: Any, ast: Node, bindings: Mapping[str, Any]) -> set[_Triple]:
    """Every triple of ``graph`` that matches some triple pattern of the query (a superset of what the query reads)."""
    reads: set[_Triple] = set()
    for pattern, _graph in _read_patterns(ast):
        for spo in _spo_patterns(pattern, bindings):
            reads.update((t[0], t[1], t[2]) for t in graph.triples(spo))
    return reads


def _pattern_quads(dataset: Any, ast: Node, bindings: Mapping[str, Any]) -> set[ox.Quad]:
    """Every quad of ``dataset`` that matches some triple pattern of the query, in a graph its pattern can read.

    A pattern outside a ``GRAPH`` block reads the default graph, or every graph when the dataset is ``default_union`` or the query has
    a ``FROM`` clause. A pattern in ``GRAPH <iri>`` reads that graph, and one in ``GRAPH ?g`` every named graph (the one a pre-bound
    ``?g`` names, if there is one).
    """
    restricted = bool(ast.f.get("datasets"))
    reads: set[ox.Quad] = set()
    for pattern, graph in _read_patterns(ast):
        named_only = False
        if graph is _DEFAULT:
            scope = None if dataset.default_union or restricted else ox.DefaultGraph()
        elif isinstance(graph, ox.Variable):
            scope = bindings.get(graph.value)
            named_only = scope is None
        else:
            scope = graph
        for spo in _spo_patterns(pattern, bindings):
            reads.update(q for q in dataset.quads((*spo, scope)) if not (named_only and q.graph_name == ox.DefaultGraph()))
    return reads


def _path_predicates(path: Any) -> list[Any]:
    """The predicates a path names; empty if it contains a negated property set (any predicate can be walked)."""
    out: list[Any] = []

    def walk(item: Any) -> bool:
        if isinstance(item, ox.NamedNode):
            out.append(item)
        elif isinstance(item, Node):
            if item.kind == "PathNegatedPropertySet":
                return False
            return all(walk(v) for v in item.f.values())
        elif isinstance(item, (list, tuple)):
            return all(walk(v) for v in item)
        return True

    return out if walk(path) else []
