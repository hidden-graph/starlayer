"""The relevant subgraph of a SPARQL query: the triples of a graph that the query's answer depends on.

``relevant_subgraph(graph, query)`` returns a ``StarLayerGraph`` ``F`` of triples taken from ``graph`` such that the query gives the
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
and triples). Not computable this way: ``GRAPH``, ``SERVICE``, and ``EXISTS`` outside the ``WHERE`` group (``HAVING``, ``ORDER BY``, a projection). For those the result is every
triple that matches some triple pattern of the query (constants and pre-bound variables fixed, other variables free): larger,
never smaller. ``relevant_triples`` returns which was used.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pyoxigraph as ox

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
    for t in sorted(triples, key=repr):  # a fixed insertion order too
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
        return _supports(graph, query, ast, run, init_bindings), True
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


#: functions whose result differs for an unbound variable and a bound one: a filter using them tests for absence
_ABSENCE_TESTS = {"BOUND", "COALESCE", "IF"}


class _Parts:
    """What the scan of the ``WHERE`` group found: spans to cut, and the groups whose matches are evidence."""

    def __init__(self) -> None:
        self.cuts: list[tuple[int, int]] = []  # (first token, last token)
        # each group whose matches are evidence: ("filter" | "minus", token indexes of the braces of the group whose solutions it is
        # evaluated against, its text)
        self.evidence: list[tuple[str, int, int, str]] = []
        self.subselects: list[str] = []  # the text of each sub-select, from its SELECT to the end of its body


def _scan(query: str, toks: list[Tok], lo: int, hi: int) -> _Parts:
    parts = _Parts()
    stack: list[tuple[str, int]] = []  # (kind, index of the opening brace) of the groups around the token
    i = lo + 1
    while i < hi:
        t = toks[i]
        word = _word(t)
        if word in ("GRAPH", "SERVICE", "SELECT"):
            raise _NotComputable(word)
        if t.kind == "P" and t.text == "{" and _word(toks[i + 1]) == "SELECT":
            close = _match(toks, i)
            parts.subselects.append(query[toks[i + 1].pos : toks[close].pos])
            i = close
        elif t.kind == "P" and t.text == "{":
            prev = _word(toks[i - 1])
            stack.append(("optional" if prev == "OPTIONAL" else "plain", i))
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
                for k in range(i, end + 1):
                    if _word(toks[k]) == "EXISTS" or (word == "MINUS" and k == i):
                        inner_open = k + 1
                        inner_close = _match(toks, inner_open)
                        inner = toks[inner_open : inner_close + 1]
                        if any(_word(s) in ("EXISTS", "MINUS", "OPTIONAL", "SELECT", "GRAPH", "SERVICE") for s in inner[1:-1]):
                            raise _NotComputable("nested negation or OPTIONAL inside an EXISTS / MINUS group")
                        kind = "minus" if word == "MINUS" else "filter"
                        parts.evidence.append((kind, group_lo, group_hi, query[inner[0].pos : inner[-1].pos + 1]))
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
    if k == "InvPath":
        return f"^({_path_text(path.f['arg'])})"
    if k == "SequencePath":
        return "(" + "/".join(_path_text(a) for a in path.f["args"]) + ")"
    if k == "AlternativePath":
        return "(" + "|".join(_path_text(a) for a in path.f["args"]) + ")"
    if k == "MulPath":
        return f"({_path_text(path.f['path'])}){path.f['mod']}"
    raise _NotComputable(f"path {k}")  # a negated property set: its edges are every edge but a few


_NODE_MARK = ox.NamedNode("urn:starlayer:relevant:node")


def _nullable(path: Any) -> bool:
    """True if the path can match with the same node at both ends (a zero-length walk)."""
    if isinstance(path, ox.NamedNode):
        return False
    k = path.kind
    if k == "InvPath":
        return _nullable(path.f["arg"])
    if k == "SequencePath":
        return all(_nullable(a) for a in path.f["args"])
    if k == "AlternativePath":
        return any(_nullable(a) for a in path.f["args"])
    if k == "MulPath":
        return path.f["mod"] in ("*", "?") or _nullable(path.f["path"])
    return False


def _edges(path: Any, a: str, b: str, fresh: _Fresh) -> list[tuple[list[str], list[str]]]:
    """``(template lines, guard conjuncts)`` pairs whose ``CONSTRUCT`` over a group joined with the guards gives the edges the path
    walks from ``a`` to ``b`` (term texts). The guards bind the intermediate variables the template uses and keep them on walks
    that really connect the endpoints."""
    if isinstance(path, ox.NamedNode):
        return [([f"{a} {path} {b} ."], [])]
    k = path.kind
    if k == "InvPath":
        return _edges(path.f["arg"], b, a, fresh)
    if k == "SequencePath":
        steps = path.f["args"]
        nodes = [a] + [fresh.var() for _ in steps[:-1]] + [b]
        chain = [f"{nodes[i]} {_path_text(step)} {nodes[i + 1]} ." for i, step in enumerate(steps)]
        return [
            (template, guards + chain)
            for i, step in enumerate(steps)
            for template, guards in _edges(step, nodes[i], nodes[i + 1], fresh)
        ]
    if k == "AlternativePath":
        return [
            (template, guards + [f"{a} {_path_text(alt)} {b} ."])
            for alt in path.f["args"]
            for template, guards in _edges(alt, a, b, fresh)
        ]
    if k == "MulPath":
        inner = path.f["path"]
        if path.f["mod"] == "?":
            return [(t, g + [f"{a} {_path_text(inner)} {b} ."]) for t, g in _edges(inner, a, b, fresh)]
        x, y = fresh.var(), fresh.var()
        walk = [f"{a} ({_path_text(inner)})* {x} .", f"{x} {_path_text(inner)} {y} .", f"{y} ({_path_text(inner)})* {b} ."]
        return [(t, g + walk) for t, g in _edges(inner, x, y, fresh)]
    raise _NotComputable(f"path {k}")


def _patterns(ast: Node) -> tuple[list[str], list[tuple[str, Any, str]]]:
    """The triple-pattern template lines of a parsed group, and its property-path patterns as ``(subject text, path, object text)``."""
    lines: list[str] = []
    paths: list[tuple[str, Any, str]] = []

    def walk(item: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "SubSelect":
                return  # its patterns belong to the sub-select's own support queries
            if item.kind == "TriplePattern":
                p = item.f["p"]
                s_text, o_text = _term_text(item.f["s"]), _term_text(item.f["o"])
                if isinstance(p, Node):
                    paths.append((s_text, p, o_text))
                else:
                    lines.append(f"{s_text} {_term_text(p)} {o_text} .")
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(ast)
    return list(dict.fromkeys(lines)), paths


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


def _supports(graph: Any, query: str, ast: Node, run: Runner, bindings: Mapping[str, Any]) -> set[_Triple]:
    query = _without_labelled_blank_nodes(_without_anonymous_blank_nodes(_without_collections(query)))
    toks = tokenize(query)
    lo, hi = _where_group(toks)
    form = next(k for k, t in enumerate(toks) if _word(t) in ("SELECT", "ASK", "CONSTRUCT"))
    prologue = query[: toks[form].pos]
    if _word(toks[lo + 1]) == "SELECT":  # the whole body is a sub-select: its rows are the outer query's rows
        inner = prologue + query[toks[lo + 1].pos : toks[hi].pos]
        return relevant_triples(graph, inner, bindings, run)[0]
    if any(_word(t) in ("EXISTS", "FROM") for k, t in enumerate(toks) if k < lo or k > hi):
        raise _NotComputable("EXISTS outside the WHERE group, or a dataset clause")

    parts = _scan(query, toks, lo, hi)

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

    def add(lines: list[str], paths: list[tuple[str, Any, str]], where: str) -> None:
        if lines:
            queries.append(f"{prologue} CONSTRUCT {{ {' '.join(lines)} }} WHERE {{ {where} }}")
        for s_text, path, o_text in paths:
            if _nullable(path):
                # a walk of length zero matches a node that is in the graph, so where the two ends are the same node it is one way
                # the row exists: the node has to stay in the graph
                queries.append(
                    f"{prologue} CONSTRUCT {{ <{_NODE_MARK.value}> <{_NODE_MARK.value}> {s_text} }} "
                    f"WHERE {{ {where} FILTER(sameTerm({s_text}, {o_text})) }}"
                )
            for template, guards in _edges(path, s_text, o_text, fresh):
                queries.append(f"{prologue} CONSTRUCT {{ {' '.join(template)} }} WHERE {{ {where} {' '.join(guards)} }}")

    body_lines, body_paths = _patterns(parsed(relaxed))
    add(body_lines, body_paths, f"{{ {relaxed} }}")
    for kind, group_lo, group_hi, group in parts.evidence:
        context = cut_text(group_lo, group_hi)
        if kind == "minus" and not _variables(group) & _variables("{" + context + "}"):
            continue  # MINUS compares on the variables shared with the group's solutions; with none shared it removes nothing
        inner_lines, inner_paths = _patterns(parsed(group))
        add(inner_lines, inner_paths, f"{{ {context} }} {group}")

    found: set[_Triple] = set()
    nodes: list[Any] = []
    for text in queries:
        for t in run(text):
            triple = (t[0], t[1], t[2])
            if triple[1] == _NODE_MARK:
                nodes.append(triple[2])
            elif triple in graph:
                found.add(triple)
    for node in nodes:  # a zero-length walk needs the node in the graph: every triple that mentions it is a way to have it
        found.update(_mentions(graph, node))
    for sub in parts.subselects:
        found |= relevant_triples(graph, prologue + sub, bindings, run)[0]
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
        if isinstance(pattern.f.get("p"), Node):  # a path walks through nodes the pattern does not name: every edge of its predicates
            predicates = [] if _nullable(pattern.f["p"]) else _path_predicates(pattern.f["p"])  # a zero-length walk: every node
            for predicate in predicates or [None]:
                reads.update((t[0], t[1], t[2]) for t in graph.triples((None, predicate, None)))
            continue
        s, p, o = (fixed(pattern.f.get(k)) for k in ("s", "p", "o"))
        reads.update((t[0], t[1], t[2]) for t in graph.triples((s, p, o)))
    return reads


def _path_predicates(path: Any) -> list[Any]:
    """The predicates a path names; empty if it contains a negated property set (any predicate can be walked)."""
    out: list[Any] = []

    def walk(item: Any) -> bool:
        if isinstance(item, ox.NamedNode):
            out.append(item)
        elif isinstance(item, Node):
            if item.kind == "NegatedPath":
                return False
            return all(walk(v) for v in item.f.values())
        elif isinstance(item, (list, tuple)):
            return all(walk(v) for v in item)
        return True

    return out if walk(path) else []
