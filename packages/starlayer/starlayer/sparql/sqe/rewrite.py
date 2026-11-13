"""Query rewriting on the parse tree that ``sqe:`` is encoded from: a correlated ``FILTER [NOT] EXISTS`` becomes a join.

Why: Oxigraph evaluates ``FILTER EXISTS { ... FILTER(?b > ?a) }`` (the inner FILTER names a variable of the enclosing
group) once per outer solution, with the outer row pushed down; at 20k triples that is 6-20x slower than the same
question asked as a join (``docs/working/oxigraph-upstream-issues.md``). The rewrite asks the question once::

    { A  FILTER EXISTS { Q } }      ->   { A  { SELECT DISTINCT ?v... WHERE { A  Q } } }
    { A  FILTER NOT EXISTS { Q } }  ->   { A  MINUS { SELECT DISTINCT ?v... WHERE { A  Q } } }

``A`` is the group's own triple patterns, ``?v...`` the variables ``A`` and ``Q`` share. The rewrite is exact, not an
approximation, and is made only where that is easy to see; every other query is sent as written. All of these must hold:

- the group is a plain group of triple patterns (variables, IRIs, literals as terms, no blank nodes, no paths) and FILTERs,
  so every variable of ``A`` is bound in every solution (a variable that may be unbound would make the join multiply rows);
- ``Q`` is triple patterns (blank nodes and paths allowed) and FILTERs; nested ``EXISTS`` inside those FILTERs may not hold
  ``BIND``, sub-selects, ``VALUES``, ``GRAPH`` or ``SERVICE``, and no FILTER calls ``RAND``/``UUID``/``STRUUID``/``BNODE``
  (the rewrite changes how often they are evaluated);
- the ``EXISTS`` is the whole FILTER expression, and some FILTER of ``Q`` mentions a variable of ``A`` (otherwise Oxigraph
  is already fast and nothing is gained);
- the group is not the right side of ``OPTIONAL`` (there the FILTER is the left join's condition and sees variables of the
  left side, which ``A`` does not hold), nor inside ``GRAPH``, ``SERVICE`` or another ``EXISTS`` (variables bound outside
  the group are visible to its FILTER);
- no ``initBindings`` are in use (the caller passes ``text`` only when there are none).

Anything unexpected (a parse error, a rendering that does not parse again) returns the original text.

Switch off with ``STARLAYER_EXISTS_REWRITE=0``.
"""

from __future__ import annotations

import os
import re

import pyoxigraph as ox

from ..parse_sparql import Node, SparqlSyntaxError, ast_to_triples, parse_sparql
from ._memtree import TreeIndex

BNode, Literal, URIRef, Variable = ox.BlankNode, ox.Literal, ox.NamedNode, ox.Variable

_EXISTS_WORD = re.compile(r"(?i)\bEXISTS\b")
_NONDETERMINISTIC = {"RAND", "UUID", "STRUUID", "BNODE"}
_NO_NESTED = {"Bind", "SubSelect", "Values", "Graph", "Service"}


def rewrite_enabled() -> bool:
    """Whether the EXISTS rewrite is on; ``STARLAYER_EXISTS_REWRITE`` set to ``0``, ``false`` or ``False`` turns it off."""
    return os.environ.get("STARLAYER_EXISTS_REWRITE", "1") not in ("0", "false", "False")


def rewrite_exists_text(text: str, *, prefixes=None, base: str | None = None) -> str:
    """``text`` with its correlated ``FILTER [NOT] EXISTS`` blocks rewritten as joins, or ``text`` itself when there is
    nothing to rewrite or anything is in doubt (the rewrite only makes the query faster). ``prefixes`` are the prefix declarations the query text relies on."""
    if not rewrite_enabled() or not _EXISTS_WORD.search(text):
        return text
    try:
        head = "".join(f"PREFIX {k}: <{v}>\n" for k, v in (prefixes or {}).items())
        tree = parse_sparql(head + text, base)
        if tree.kind not in ("SelectQuery", "AskQuery", "ConstructQuery") or not _rewrite_node(tree, True):
            return text
        from .to_text import sqe_tree_to_text

        triples, root = ast_to_triples(tree)
        out = sqe_tree_to_text(TreeIndex(triples), root)
        parse_sparql(out, base)  # what is sent must itself be well-formed
        return out
    except (ImportError, SparqlSyntaxError, ValueError, KeyError, NotImplementedError, RecursionError, TypeError, AttributeError):
        return text


# ---- the walk ---------------------------------------------------------------------------------------------------------

def _rewrite_node(node: Node, rewritable: bool) -> bool:
    """Rewrite the group of ``node.f['where']`` (when ``rewritable``) and every isolated group below it. True if changed."""
    changed = False
    where = node.f.get("where")
    if isinstance(where, list):
        changed = _rewrite_group(where, rewritable)
    return changed


def _rewrite_group(where: list, rewritable: bool) -> bool:
    changed = False
    for el in list(where):
        if not isinstance(el, Node):
            continue
        if el.kind == "Union":
            for alt in el.f["alts"]:
                changed |= _rewrite_group(alt, True)
        elif el.kind == "Minus":
            changed |= _rewrite_group(el.f["where"], True)
        elif el.kind == "Optional":
            changed |= _rewrite_group(el.f["where"], False)
        elif el.kind == "SubSelect":
            changed |= _rewrite_group(el.f["where"], True)
        # Graph, Service and EXISTS bodies are left alone: variables bound outside the group are visible inside them.
    if rewritable:
        changed |= _rewrite_here(where)
    return changed


def _simple_term(t) -> bool:
    return isinstance(t, (Variable, URIRef, Literal))


def _vars(x, out: set) -> set:
    """Every variable anywhere under ``x`` (over-approximate on purpose, nested EXISTS bodies included)."""
    if isinstance(x, Variable):
        out.add(x)
    elif isinstance(x, Node):
        for v in x.f.values():
            _vars(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _vars(v, out)
    return out


def _kinds_ok(x) -> bool:
    """No nondeterministic call, and no pattern kind inside a nested EXISTS that substitution treats differently."""
    if isinstance(x, Node):
        if x.kind in _NO_NESTED or x.kind.removeprefix("Builtin_").upper() in _NONDETERMINISTIC:
            return False
        return all(_kinds_ok(v) for v in x.f.values())
    if isinstance(x, (list, tuple)):
        return all(_kinds_ok(v) for v in x)
    return True


def _inner_ok(x) -> bool:
    """A node inside a FILTER expression: nested EXISTS bodies must use only the whitelisted kinds."""
    return _kinds_ok(x)


def _rewrite_here(where: list) -> bool:
    triples, candidates = [], []
    for el in where:
        if isinstance(el, Node) and el.kind == "TriplePattern":
            if not (_simple_term(el.f["s"]) and isinstance(el.f["p"], (Variable, URIRef)) and _simple_term(el.f["o"])):
                return False
            triples.append(el)
        elif isinstance(el, Node) and el.kind == "Filter":
            e = el.f["expr"]
            if isinstance(e, Node) and e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
                candidates.append(el)
        else:
            return False
    if not triples or not candidates:
        return False
    a_vars = _vars(triples, set())
    changed = False
    for filt in candidates:
        e = filt.f["expr"]
        q = e.f["graph"]
        q_triples, q_filters = [], []
        for x in q:
            if isinstance(x, Node) and x.kind == "TriplePattern":
                if not (_ok_q_term(x.f["s"]) and _ok_q_term(x.f["o"])):
                    break
                q_triples.append(x)
            elif isinstance(x, Node) and x.kind == "Filter":
                q_filters.append(x)
            else:
                break
        else:
            if not q_filters or not q_triples:
                continue
            if not all(_inner_ok(f) for f in q_filters):
                continue
            if not any(_vars(f, set()) & a_vars for f in q_filters):
                continue
            shared = sorted(_vars(q, set()) & a_vars, key=lambda v: v.value)
            sub = Node(
                "SubSelect", modifier="DISTINCT", projection=[Node("ProjectVar", var=v) for v in shared], datasets=[],
                where=[*triples, *q_triples, *q_filters], group_by=None, having=None, order_by=None, limit=None,
                offset=None, values=None,
            )
            where.remove(filt)
            where.append(Node("Minus", where=[sub]) if e.kind == "Builtin_NOTEXISTS" else Node("Union", alts=[[sub]]))
            changed = True
    return changed


def _ok_q_term(t) -> bool:
    return isinstance(t, (Variable, URIRef, Literal, BNode))
