"""Fix for rdflib's grammar of a negated property set with an inverse member (``!(^:p)``, ``!(:p|^:q)``).

rdflib's grammar writes ``Comp("InversePath", "^" + (iri | A))``: the IRI after ``^`` is not a named parameter, so the
parsed node is an empty ``InversePath_{}`` and the IRI is lost. ``translatePath`` has no case for that name either, so
evaluation and every renderer crash (``TypeError: 'NoneType' object is not callable``, GitHub issue #77). The node is
rebuilt as ``PathEltOrInverse`` with a named ``part``, which ``translatePath`` already turns into an ``InvPath``;
``NegatedPath.eval`` (see ``evaluate_patches``) handles an ``InvPath`` member.

The grammar object is mutated in place, once, before any query is parsed. Idempotent, like the other patches.
"""

from __future__ import annotations

_status: bool | None = None
_mulpath_status: bool | None = None


def patch_negated_set_inverse_member() -> bool:
    """Rebuild the ``^`` alternative of ``PathOneInPropertySet``. True if applied or already applied."""
    global _status
    if _status is not None:
        return _status
    try:
        from rdflib.plugins.sparql import parser
        from rdflib.plugins.sparql.parserutils import Comp, Param

        members = parser.PathOneInPropertySet
        replaced = False
        for index, expr in enumerate(members.exprs):
            if isinstance(expr, Comp) and expr.name == "InversePath":
                members.exprs[index] = Comp("PathEltOrInverse", "^" + Param("part", parser.iri | parser.A))
                replaced = True
        _status = replaced or any(isinstance(e, Comp) and e.name == "PathEltOrInverse" for e in members.exprs)
    except Exception:
        _status = False
    return _status


def patch_repetition_paths_are_distinct() -> bool:
    """``:a :p* ?y`` over a cycle returned the start node twice (the zero-length match and the cycle back to it) while
    ``:a :p+ ?y`` and ``?x :p* ?y FILTER(?x = :a)`` gave each node once. SPARQL 1.1 section 18.4 evaluates ``*``, ``+`` and
    ``?`` over the *set* of reachable nodes (ALP is a visited set), so the result of the outermost evaluation is made
    distinct (GitHub issue #77). Wraps ``MulPath.eval``; the recursive calls inside rdflib are left alone."""
    global _mulpath_status
    if _mulpath_status is not None:
        return _mulpath_status
    try:
        from rdflib.paths import MulPath

        original = MulPath.eval
        if getattr(original, "_starlayer_graph_mulpath_patch", False):
            _mulpath_status = True
            return True

        def _eval(self, graph, subj=None, obj=None, first=True):
            if not first:
                yield from original(self, graph, subj, obj, first)
                return
            seen = set()
            for pair in original(self, graph, subj, obj, first):
                if pair not in seen:
                    seen.add(pair)
                    yield pair

        _eval._starlayer_graph_mulpath_patch = True  # type: ignore[attr-defined]
        MulPath.eval = _eval
        _mulpath_status = True
    except Exception:
        _mulpath_status = False
    return _mulpath_status
