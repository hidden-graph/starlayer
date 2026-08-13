"""Targeted compatibility shims for confirmed bugs in plain rdflib's own
``_AlgebraTranslator``/``translateAlgebra`` (``rdflib.plugins.sparql.algebra``)
— algebra-tree-back-to-SPARQL-text serialization, not evaluation. See
``docs/rdflib-upstream-issues.md`` issues 3, 4, and 6 for the full write-up
of each, including standalone plain-rdflib reproductions.

None of these bugs is in a code path *this repo itself* exercises directly
today — starlayergraph never calls ``translateAlgebra``/``_AlgebraTranslator``
anywhere in its own pipeline (confirmed: no reference to either name in
``starlayergraph/`` outside this file). All were found while building triple-term
support in the downstream ``starsparql`` project, which *does* use
``_AlgebraTranslator`` directly (subclassing it in its own
``serialize12.py``); issues 3 and 6 already have independent workarounds
there (issue 7's empty-``PV`` fix does not — that project's own ``Project``
handling is about a different, CONSTRUCT-specific empty-``PV`` case, not
this one). Patching here too is still worthwhile, matching
``operator_patches.py``'s own stated rationale: any *other* current or
future consumer of this package that calls ``translateAlgebra``/
``_AlgebraTranslator`` directly (not through that specific downstream
subclass) gets correct behavior for free, rather than silently inheriting
these bugs — and per direct instruction, this pipeline (parse SPARQL 1.2 →
this project's own RDF algebra representation → ``translateAlgebra``-based
regeneration → execution) is intended to become the path *every* SPARQL
query through starlayergraph goes through, not just this specific downstream
project's own test suite, which makes fixing these here rather than only in
one consumer's own workaround the right call.

Same idempotent apply-once pattern as ``operator_patches.py``: a
module-level ``_xxx_patch_status: bool | None`` flag plus a marker attribute
on the patched callable, so repeated calls are safe no-ops. Unlike
``operator_patches.py``'s ``Comp.setEvalFn`` technique (that file patches
pyparsing grammar nodes), this patches a plain Python method on
``_AlgebraTranslator`` directly: the original bound method is captured once,
and the replacement delegates to it for every node type except the two
specific ``node.name`` values these two bugs live in - so any future rdflib
fix, or any other branch's behavior, passes through completely unaffected.
"""

from __future__ import annotations

import re

from rdflib import Variable
from rdflib.plugins.sparql.algebra import _AlgebraTranslator
from rdflib.plugins.sparql.parserutils import CompValue

_algebra_translator_patch_status: bool | None = None

# rdflib's own internal naming convention for the synthetic result variable
# of an implicit aggregate (see algebra.py::translateAggregates - "aggvar =
# Variable('__agg_%d__' % ...)"). An Extend node whose expr is one of these
# is never a real, user-written BIND - it's rdflib wrapping a GROUP BY'd
# variable that's *also* directly projected in an implicit SAMPLE() (or
# wrapping a genuine aggregate function's own result var) so it can be
# treated uniformly as "just another projected expression." See Issue 7 in
# docs/rdflib-upstream-issues.md for the full writeup of why the patched
# "Extend" branch below can't treat this case the same as an ordinary BIND.
_AGG_RESULT_VAR_RE = re.compile(r"^__agg_\d+__$")


def _is_aggregate_result_var(expr: object) -> bool:
    return isinstance(expr, Variable) and bool(_AGG_RESULT_VAR_RE.match(str(expr)))


def patch_algebra_translator_bugs() -> bool:
    """Fix three confirmed rdflib bugs in ``_AlgebraTranslator.sparql_query_text``:

    1. The ``"BGP"`` branch joins each triple's text with no separator
       between one triple's trailing ``"."`` and the next triple's leading
       term - so a triple ending in a blank-node object immediately
       followed by a triple whose subject is a blank node produces text
       rdflib's own SPARQL parser can't re-tokenize (``_:x._:x`` instead of
       ``_:x. _:x``). See ``docs/rdflib-upstream-issues.md`` issue 3.

    2. The ``"RelationalExpression"`` branch (``IN``/``NOT IN`` among other
       relational operators) guards its list-handling code with
       ``isinstance(list, type(node.other))`` - backwards from the intended
       ``isinstance(node.other, list)`` (never ``True`` for any value,
       since the class ``list`` is never an instance of itself), making the
       correct branch dead code - every multi-value ``IN``/``NOT IN`` falls
       through to ``self.convert_node_arg(node.other)``, which has no case
       for a bare list at all, and raises. See
       ``docs/rdflib-upstream-issues.md`` issue 6.

    3. The ``"Extend"`` branch (``BIND``/``SELECT (expr AS ?v)``) locates
       the variable it needs to wrap by searching the *already-accumulated
       output text* for a bare occurrence of ``var.n3()`` and replacing it
       in place with ``"(expr AS var)"`` - not idempotent-safe (the
       replacement text itself still contains that same substring) and not
       scoped per-branch, so when multiple sibling ``UNION`` branches each
       independently ``BIND`` the same projected variable name, a later
       branch's replacement matches *inside* an earlier branch's own,
       already-completed replacement instead of a fresh occurrence -
       producing invalid, arbitrarily-nested output. See
       ``docs/rdflib-upstream-issues.md`` issue 4.

    Idempotent and defensive, matching the established
    ``operator_patches.py`` idiom - returns ``False`` without raising if
    rdflib's internals don't match what this shim expects.
    """
    global _algebra_translator_patch_status
    if _algebra_translator_patch_status is not None:
        return _algebra_translator_patch_status

    try:
        original_sparql_query_text = _AlgebraTranslator.sparql_query_text
        if getattr(original_sparql_query_text, "_starlayergraph_algebra_translator_patch", False):
            _algebra_translator_patch_status = True
            return True

        def _patched_sparql_query_text(self, node):
            # NOTE: every branch below must either `return node` (only
            # correct when the branch is fully self-contained, with no
            # not-yet-resolved child placeholder left behind - see "BGP")
            # or `return None` explicitly (never just fall off the end of
            # the `if`) once it has done its own work - falling through to
            # the final `return original_sparql_query_text(self, node)`
            # unconditionally would run the *original*, buggy logic a
            # second time on the same node, on top of this patch's own
            # fix. Confirmed a real, reproducible bug when first tried:
            # omitting the explicit `return None` after the "Extend"
            # branch's own fix still let the original "Extend" branch run
            # too, via this exact fallthrough - producing both the
            # corrected in-place BIND *and* the original buggy nested-AS
            # text in the same output.
            if isinstance(node, CompValue) and node.name == "BGP":
                # Same four _replace calls the original "BGP" branch makes,
                # in the same order - only the triples separator differs
                # (". " instead of ".").
                triples = "".join(
                    triple[0].n3() + " " + triple[1].n3() + " " + triple[2].n3() + ". "
                    for triple in node.triples
                )
                self._replace("{BGP}", triples)
                self._replace("-*-SELECT-*-", "SELECT", count=-1)
                self._replace("{GroupBy}", "", count=-1)
                self._replace("{Having}", "", count=-1)
                return node

            if (
                isinstance(node, CompValue)
                and node.name == "RelationalExpression"
                and isinstance(node.other, list)
            ):
                expr = self.convert_node_arg(node.expr)
                other = (
                    "("
                    + ", ".join(self.convert_node_arg(item) for item in node.other)
                    + ")"
                )
                self._replace(
                    "{RelationalExpression}",
                    "{left} {operator} {right}".format(left=expr, operator=node.op, right=other),
                )
                # Deliberately NOT `return node` here (unlike the "BGP"
                # branch above, which has no CompValue children at all):
                # node.expr/node.other's own items can themselves be
                # CompValue nodes (e.g. a nested TripleTerm-shaped value,
                # or any other sub-expression) - convert_node_arg() already
                # inserts a bare "{SomeNode}" placeholder for any such
                # argument, which needs _traverse's own later per-child
                # recursion to resolve. Returning early here would leave
                # that placeholder as literal, unresolved text in the
                # final output - confirmed a real, reproducible bug when
                # first tried (this project's own CLAUDE.md documents the
                # identical trap for a different branch, "isTRIPLE"/etc,
                # in the downstream starsparql project).
                return None

            if (
                isinstance(node, CompValue)
                and node.name == "Extend"
                and _is_aggregate_result_var(node.expr)
            ):
                # An implicit-aggregate-wrapping Extend (rdflib's own
                # "SELECT ?p ... GROUP BY ?p" -> implicit SAMPLE(?p)
                # machinery, or any genuine aggregate function's own result
                # var) - never legal as an ordinary in-place BIND (SPARQL's
                # grammar doesn't permit an Aggregate inside BIND's
                # Expression at all, only directly in a SELECT-list/HAVING/
                # ORDER BY position), so this branch's own general "render
                # as an in-place BIND" fix (see below) is wrong here
                # specifically. Falls through to the original, unpatched
                # logic instead, whose "-*-select-*-"-anchored search-and-
                # wrap approach - despite being the very thing this file
                # otherwise replaces - is also what performs the paired
                # "(SAMPLE(x) as x)" suppression the "AggregateJoin" branch
                # depends on (a literal-text match against exactly the
                # lowercase-`as`, no-`BIND(`-wrapper shape the *original*
                # Extend branch produces - this branch's own `BIND(... AS
                # ...)` shape never matches it, silently defeating the
                # suppression and leaking a spurious
                # `BIND(SAMPLE(?p) AS ?p)` into the output). See Issue 7 in
                # docs/rdflib-upstream-issues.md.
                return original_sparql_query_text(self, node)

            if isinstance(node, CompValue) and node.name == "Extend":
                # Renders as an explicit, in-place `BIND(expr AS var) .`
                # statement at this node's own position in the tree -
                # using the standard "{NodeName}" placeholder convention
                # every other branch (Join/LeftJoin/Union/Graph/...)
                # already uses for referencing a child - instead of the
                # original branch's approach of searching the
                # already-accumulated text for a bare occurrence of
                # `var.n3()` (inserted earlier, verbatim, by "Project"'s
                # own PV rendering) and wrapping it in place with
                # "(expr AS var)". See docs/rdflib-upstream-issues.md
                # issue 4 for the full root-cause writeup: that search
                # step is not idempotent-safe (its own replacement text
                # still contains the same variable-name substring it
                # searched for) and not scoped per-branch (its
                # "-*-select-*- occurrence count" heuristic for guessing
                # which occurrence to target breaks down once more than
                # one sibling subquery/UNION branch has contributed its
                # own marker) - both compound when multiple UNION branches
                # each independently BIND the same projected variable
                # name, producing invalid, arbitrarily-nested output
                # ("(a AS (b AS ?v))" instead of two separate BINDs).
                #
                # This form is always a safe, general substitution
                # regardless of the original SPARQL syntax
                # ("SELECT (expr AS ?v) ..." or an ordinary in-place
                # "BIND(expr AS ?v)" both collapse to the identical
                # "Extend" algebra shape, and SPARQL treats the two textual
                # forms as fully equivalent for a single Extend) - and,
                # unlike the original approach, it never needs to locate
                # or rely on "Project"'s own PV-list text at all: a bare
                # "?v" already correctly appears there (from "Project"'s
                # own, unmodified rendering of node.PV), and a variable
                # that is *also* bound by an ordinary BIND elsewhere in the
                # WHERE clause is completely ordinary, valid SPARQL.
                # No trailing "." here (unlike most other statement-like
                # branches in this file/rdflib's own convention) -
                # deliberately: SPARQL's own grammar makes the separator
                # between a GraphPatternNotTriples element (BIND is one)
                # and whatever follows optional
                # (`GraphPatternNotTriples '.'? TriplesBlock?`, repeated
                # zero or more times with no required separator between
                # repetitions), and `)` (BIND's own closing paren) is
                # already an unambiguous token boundary against anything
                # that can follow. Confirmed necessary, not just
                # stylistic: starlayergraph's own `sparql12_to_11.py` rewriter
                # (`_rewrite_bind_accessors`) matches the literal text
                # shape `BIND(SUBJECT(?tt) AS ?s)` and substitutes it
                # *wholesale* with `?tt <rdf:subject> ?s .` - including its
                # *own* trailing period - so a trailing "." emitted here
                # too produced a real, reproducible double-period
                # (`?s . .`, a syntax error) once this branch's output fed
                # into that specific downstream rewriter.
                self._replace(
                    "{Extend}",
                    "{" + node.p.name + "}BIND(" + self.convert_node_arg(node.expr) + " AS " + node.var.n3() + ")",
                )
                # Deliberately NOT `return node`, for the same reason as
                # the "RelationalExpression" branch above: `node.p` (a
                # child pattern - BGP/ToMultiSet/Join/etc) is only
                # referenced here as a bare "{NodeName}" placeholder, not
                # actually resolved - _traverse's own later recursion into
                # node.p is what fills it in. Confirmed a real,
                # reproducible bug when first tried: returning early here
                # left a literal, unresolved "{ToMultiSet}"/"{BGP}" in the
                # output, and separately meant _traverse never reached the
                # BGP branch's own "-*-select-*- -> SELECT" marker
                # cleanup, leaving the literal marker text in the output
                # too.
                return None

            if isinstance(node, CompValue) and node.name == "Project" and not node.PV:
                # "Project"'s own PV (projected-variables) list is only ever
                # empty for a "SELECT *" query whose WHERE pattern contains
                # zero variables anywhere (a fully-ground BGP, e.g.
                # `SELECT * WHERE { :a :b :c . }`) - for any pattern with at
                # least one variable, rdflib's own translateQuery already
                # expands "*" into the concrete variable list at algebra-
                # construction time (confirmed: PV is never `[]` for
                # "SELECT * WHERE { ?s ?p ?o }"), so this branch only fires
                # for that one narrow, but valid and unremarkable, shape.
                # The original branch (below, still used for the non-empty
                # case) builds the projection text via
                # `" ".join(project_variables)`, which is simply the empty
                # string when `node.PV` is `[]` - producing `SELECT {...}`
                # with no `*` at all, which rdflib's own parser then can't
                # re-parse (`Expected SelectQuery, found '{'`). See Issue 7
                # in docs/rdflib-upstream-issues.md for the full writeup.
                # SPARQL's grammar requires a SelectClause to be either `*`
                # or a non-empty Var/`(Expression AS Var)` list - an empty
                # PV is unambiguous, there's no other query shape it could
                # represent - so rendering it as `*` unconditionally is
                # always correct, not just a heuristic guess.
                order_by_pattern = "ORDER BY {OrderConditions}" if node.p.name == "OrderBy" else ""
                self._replace(
                    "{Project}",
                    "* {{" + node.p.name + "}}{GroupBy}" + order_by_pattern + "{Having}",
                )
                return None

            return original_sparql_query_text(self, node)

        _patched_sparql_query_text._starlayergraph_algebra_translator_patch = True  # type: ignore[attr-defined]
        _AlgebraTranslator.sparql_query_text = _patched_sparql_query_text
        _algebra_translator_patch_status = True
    except Exception:
        _algebra_translator_patch_status = False

    return _algebra_translator_patch_status
