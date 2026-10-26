"""Compatibility shims for confirmed bugs in rdflib's SPARQL builtin functions
and expression error handling (``rdflib.plugins.sparql.operators``,
``aggregates``, ``algebra``). GitHub issue #76 (the second bug hunt); every
bug reproduces against plain ``rdflib.Graph().query()``. Write-ups with
standalone repros: ``docs/upstream-issues/rdflib-upstream-issues.md``.

What a SPARQL error means here: an expression that raises ``SPARQLError``
leaves a ``BIND``/projection target unbound, drops the row under ``FILTER``,
and is skipped by ``COALESCE`` (SPARQL 1.1/1.2 Query, 17.2). The bugs below
are cases where rdflib instead returned a wrong value or let a Python
exception (``AttributeError``, ``ValueError``, ``RecursionError``) abort the
whole query.

Same idempotent apply-once pattern as ``operator_patches.py``: a module-level
``_xxx_patch_status: bool | None`` flag plus a marker attribute on the patched
callable.
"""

from __future__ import annotations

import functools
from types import SimpleNamespace

from rdflib import RDF, Literal
from rdflib.namespace import XSD
from rdflib.plugins.sparql.sparql import NotBoundError, SPARQLError, SPARQLTypeError

_MARK = "_starlayer_graph_builtin_error_patch"


def _marked(fn):
    setattr(fn, _MARK, True)
    return fn


def _is_marked(fn) -> bool:
    return bool(getattr(fn, _MARK, False))


def _expression_comp(name: str):
    from rdflib.plugins.sparql import parser as rdflib_sparql_parser

    from starlayer.graph.query.operator_patches import _find_comp

    comp = _find_comp(rdflib_sparql_parser.Expression, name)
    if comp is None:
        raise LookupError(name)
    return comp


# ---------------------------------------------------------------------------
# Ill-typed numeric literals and ill-typed dateTimes are errors
# ---------------------------------------------------------------------------

_numeric_patch_status: bool | None = None


def patch_ill_typed_literals_are_errors() -> bool:
    """``numeric()`` returned the ``Literal`` itself for an ill-typed numeric
    such as ``"abc"^^xsd:integer`` (rdflib's ``toPython`` falls back to the
    literal), so ``+`` recursed until ``RecursionError`` and ``isNumeric``
    answered true. ``datetime()``/``date()`` did the same for an ill-typed
    ``xsd:dateTime``, so ``DAY()``/``YEAR()`` and friends died with
    ``AttributeError``. SPARQL 1.1 Query 17.3: an ill-typed literal is a type
    error. All of these now raise ``SPARQLError``.
    """
    global _numeric_patch_status
    if _numeric_patch_status is not None:
        return _numeric_patch_status
    try:
        from rdflib.plugins.sparql import aggregates, operators

        if _is_marked(operators.numeric):
            _numeric_patch_status = True
            return True

        original_numeric = operators.numeric
        original_datetime = operators.datetime
        original_date = operators.date

        @_marked
        def _numeric(expr):
            value = original_numeric(expr)
            if isinstance(value, Literal):
                raise SPARQLTypeError(f"{expr!r} is an ill-typed numeric literal")
            return value

        @_marked
        def _datetime(e):
            value = original_datetime(e)
            if isinstance(value, Literal):
                raise SPARQLError(f"{e!r} is an ill-typed dateTime literal")
            return value

        @_marked
        def _date(e):
            value = original_date(e)
            if isinstance(value, Literal):
                raise SPARQLError(f"{e!r} is an ill-typed date literal")
            return value

        operators.numeric = _numeric
        aggregates.numeric = _numeric
        operators.datetime = _datetime
        operators.date = _date
        _numeric_patch_status = True
    except Exception:
        _numeric_patch_status = False
    return _numeric_patch_status


# ---------------------------------------------------------------------------
# SUBSTR
# ---------------------------------------------------------------------------

_substr_patch_status: bool | None = None


def _substr_evalfn(e, ctx):
    from rdflib.plugins.sparql.operators import numeric, string

    a = string(e.arg)
    start = numeric(e.start)
    # SUBSTR's signature takes xsd:integer positions (SPARQL 1.1 17.4.3.3),
    # so a decimal or double position is a type error, not a rounding.
    if not isinstance(start, int) or isinstance(start, bool):
        raise SPARQLTypeError(f"SUBSTR: start must be xsd:integer, got {e.start!r}")
    length = e.length
    if length is not None:
        length = numeric(length)
        if not isinstance(length, int) or isinstance(length, bool):
            raise SPARQLTypeError(f"SUBSTR: length must be xsd:integer, got {e.length!r}")
    # fn:substring keeps the characters at 1-based positions p with
    # start <= p < start + length. Python slicing treats a negative index as
    # counting from the end, so clamp both bounds instead of subtracting.
    first = max(start, 1)
    if length is None:
        text = str(a)[first - 1 :]
    else:
        last = start + length  # exclusive
        text = str(a)[first - 1 : max(last - 1, 0)] if last > first else ""
    return Literal(text, lang=a.language, datatype=a.datatype)


def patch_substr_xpath_semantics() -> bool:
    """``SUBSTR("abc", 0, 2)`` must be ``"a"`` (fn:substring keeps positions
    ``start <= p < start + length``); rdflib slices with the raw index so a
    start below 1 gave ``""`` or a Python negative-index slice. Also makes a
    non-integer position a type error, as the ``xsd:integer`` signature
    requires. Replaces ``operators.Builtin_SUBSTR`` too, because the
    directional-literal ``SUBSTR`` in ``custom_functions.py`` calls it.
    """
    global _substr_patch_status
    if _substr_patch_status is not None:
        return _substr_patch_status
    try:
        from rdflib.plugins.sparql import operators

        comp = _expression_comp("Builtin_SUBSTR")
        if _is_marked(comp.evalfn):
            _substr_patch_status = True
            return True
        _marked(_substr_evalfn)
        comp.setEvalFn(_substr_evalfn)
        operators.Builtin_SUBSTR = _substr_evalfn
        _substr_patch_status = True
    except Exception:
        _substr_patch_status = False
    return _substr_patch_status


# ---------------------------------------------------------------------------
# TIMEZONE
# ---------------------------------------------------------------------------

_timezone_patch_status: bool | None = None


def _timezone_evalfn(e, ctx):
    from rdflib.plugins.sparql import operators

    dt = operators.datetime(e.arg)
    if not dt.tzinfo:
        raise SPARQLError(f"dateTime has no timezone: {dt!r}")
    total = int(dt.utcoffset().total_seconds())
    sign = "-" if total < 0 else ""
    hours, rest = divmod(abs(total), 3600)
    minutes, seconds = divmod(rest, 60)
    body = (f"{hours}H" if hours else "") + (f"{minutes}M" if minutes else "") + (f"{seconds}S" if seconds else "")
    return Literal(f"{sign}PT{body or '0S'}", datatype=XSD.dayTimeDuration)


def patch_timezone_keeps_minutes() -> bool:
    """``TIMEZONE("...-05:30"^^xsd:dateTime)`` is ``"-PT5H30M"``; rdflib
    computed the minutes with Python 3 true division (a float, never truthy
    at the right moment) and lost them, and answered ``P0D`` for a zero
    offset where fn:timezone-from-dateTime gives ``PT0S``.
    """
    global _timezone_patch_status
    if _timezone_patch_status is not None:
        return _timezone_patch_status
    try:
        comp = _expression_comp("Builtin_TIMEZONE")
        if _is_marked(comp.evalfn):
            _timezone_patch_status = True
            return True
        _marked(_timezone_evalfn)
        comp.setEvalFn(_timezone_evalfn)
        _timezone_patch_status = True
    except Exception:
        _timezone_patch_status = False
    return _timezone_patch_status


# ---------------------------------------------------------------------------
# STRDT
# ---------------------------------------------------------------------------

_strdt_patch_status: bool | None = None


def patch_strdt_requires_string_and_iri() -> bool:
    """``STRDT("a", 1)`` built a literal with datatype ``<1>``. STRDT takes a
    simple literal / ``xsd:string`` and an IRI (SPARQL 1.1 17.4.2.8); any
    other argument is a type error.
    """
    global _strdt_patch_status
    if _strdt_patch_status is not None:
        return _strdt_patch_status
    try:
        from rdflib import URIRef

        comp = _expression_comp("Builtin_STRDT")
        if _is_marked(comp.evalfn):
            _strdt_patch_status = True
            return True

        def _strdt(e, ctx):
            lexical, datatype = e.arg1, e.arg2
            if not isinstance(lexical, Literal) or lexical.language or lexical.datatype not in (None, XSD.string):
                raise SPARQLTypeError(f"STRDT: lexical form must be a simple literal or xsd:string, got {lexical!r}")
            if not isinstance(datatype, URIRef):
                raise SPARQLTypeError(f"STRDT: datatype must be an IRI, got {datatype!r}")
            return Literal(str(lexical), datatype=datatype)

        comp.setEvalFn(_marked(_strdt))
        _strdt_patch_status = True
    except Exception:
        _strdt_patch_status = False
    return _strdt_patch_status


# ---------------------------------------------------------------------------
# Aggregates: SUM / AVG errors leave the value unbound
# ---------------------------------------------------------------------------

_aggregate_patch_status: bool | None = None


def patch_sum_avg_errors_are_unbound() -> bool:
    """``SUM``/``AVG`` over a non-numeric value raised out of ``query()`` (or
    ``AVG`` silently skipped it), losing every row of the query. SPARQL 1.1
    Query 18.5 defines SUM/AVG through ``op:numeric-add``, which errors on a
    non-numeric operand, and an error in an aggregate makes that one value
    unbound (a ``HAVING`` condition over it then drops that group only).
    Count, Min, Max, Sample and GroupConcat are unchanged.
    """
    global _aggregate_patch_status
    if _aggregate_patch_status is not None:
        return _aggregate_patch_status
    try:
        from rdflib.plugins.sparql import aggregates as agg
        from rdflib.plugins.sparql.datatypes import type_promotion
        from rdflib.plugins.sparql.evalutils import _eval

        if _is_marked(agg.Sum.update):
            _aggregate_patch_status = True
            return True

        def _use_row(self, row):
            try:
                return _eval(self.expr, row) not in self.seen
            except SPARQLError:
                return True  # update() records the error or skips the unbound row

        def _set_value(self, bindings):
            if not self._error:
                bindings[self.var] = self.get_value()

        def _term(self, row):
            """(value, number) of this row, or None for an unbound row."""
            value = _eval(self.expr, row)
            return value, agg.numeric(value)

        def _sum_update(self, row, aggregator):
            if self._error:
                return
            try:
                value, number = _term(self, row)
                dt = value.datatype if self.datatype is None else type_promotion(self.datatype, value.datatype)
                self.value = sum(agg.type_safe_numbers(self.value, number))
                self.datatype = dt
                if self.distinct:
                    self.seen.add(value)
            except NotBoundError:
                pass
            except (SPARQLError, TypeError, ArithmeticError):
                self._error = True

        def _avg_update(self, row, aggregator):
            if self._error:
                return
            try:
                value, number = _term(self, row)
                dt = value.datatype if self.datatype is None else type_promotion(self.datatype, value.datatype)
                self.sum = sum(agg.type_safe_numbers(self.sum, number))
                self.datatype = dt
                if self.distinct:
                    self.seen.add(value)
                self.counter += 1
            except NotBoundError:
                pass
            except (SPARQLError, TypeError, ArithmeticError):
                self._error = True

        for cls, update in ((agg.Sum, _sum_update), (agg.Average, _avg_update)):
            cls._error = False
            cls.use_row = _use_row
            cls.set_value = _set_value
            cls.update = _marked(update)
        _aggregate_patch_status = True
    except Exception:
        _aggregate_patch_status = False
    return _aggregate_patch_status


_extremum_patch_status: bool | None = None


def patch_min_max_group_concat_terms_and_errors() -> bool:
    """``MIN``/``MAX`` wrapped their result in ``Literal(value)``, so the minimum of IRIs came back as a plain string
    literal and the minimum of triple terms as a literal holding the internal ``tt:`` hash IRI; ``GROUP_CONCAT`` and
    ``MIN``/``MAX`` also put the *error message* of a failed argument into the result (``GROUP_CONCAT(STR(?o))`` over a
    triple term returned ``"... STR: a triple term has no string form"``, ``MAX(STR(?o))`` returned the message itself)
    because ``_eval`` hands back a ``SPARQLError`` as a value. SPARQL 1.1 Query 18.5: ``Min``/``Max`` return a term of
    the group (its own type), and an error in an aggregate argument makes the aggregate an error, so it is unbound
    (GitHub issue #134). A triple term has no string form either, so ``GROUP_CONCAT(?o)`` over one is an error too.
    A triple term sorts after every other kind of term (SPARQL 1.2 15.1 ORDER BY); the order among triple terms is not
    defined by the spec and follows the content-addressed hash here.
    """
    global _extremum_patch_status
    if _extremum_patch_status is not None:
        return _extremum_patch_status
    try:
        from rdflib import URIRef
        from rdflib.plugins.sparql import aggregates as agg
        from rdflib.plugins.sparql.evalutils import _eval
        from rdflib.term import Identifier

        from starlayer.graph.model.encoding import TT_NS

        if _is_marked(agg.Extremum.update):
            _extremum_patch_status = True
            return True

        original_val = agg._val

        def _is_tt(value) -> bool:
            return isinstance(value, URIRef) and str(value).startswith(TT_NS)

        def _val(value):
            if _is_tt(value):
                return (4, value)
            return original_val(value)

        def _extremum_update(self, row, aggregator):
            if self._error:
                return
            try:
                value = _eval(self.expr, row)
                if isinstance(value, NotBoundError):
                    return
                if isinstance(value, SPARQLError):
                    self._error = True
                    return
                self.value = value if self.value is None else self.compare(self.value, value)
            except NotBoundError:
                pass
            except SPARQLError:
                self._error = True

        def _extremum_set_value(self, bindings):
            if self._error or self.value is None:
                return
            bindings[self.var] = self.value if isinstance(self.value, Identifier) else Literal(self.value)

        def _concat_update(self, row, aggregator):
            if self._error:
                return
            try:
                value = _eval(self.expr, row)
                if isinstance(value, NotBoundError):
                    return
                if isinstance(value, SPARQLError) or _is_tt(value):
                    self._error = True
                    return
                self.value.append(value)
                if self.distinct:
                    self.seen.add(value)
            except NotBoundError:
                pass
            except SPARQLError:
                self._error = True

        def _concat_set_value(self, bindings):
            if not self._error:
                bindings[self.var] = self.get_value()

        agg._val = _val
        agg.Extremum._error = False
        agg.Extremum.set_value = _extremum_set_value
        agg.Extremum.update = _marked(_extremum_update)
        agg.GroupConcat._error = False
        agg.GroupConcat.set_value = _concat_set_value
        agg.GroupConcat.update = _marked(_concat_update)
        _extremum_patch_status = True
    except Exception:
        _extremum_patch_status = False
    return _extremum_patch_status


# ---------------------------------------------------------------------------
# Relational operators: IN / NOT IN, ordering of mixed types, directional
# literal equality; logical-and error handling
# ---------------------------------------------------------------------------

_relational_patch_status: bool | None = None

_NUMERIC_DATATYPES = frozenset(
    {
        XSD.float, XSD.double, XSD.decimal, XSD.integer, XSD.nonPositiveInteger,
        XSD.negativeInteger, XSD.nonNegativeInteger, XSD.positiveInteger,
        XSD.unsignedLong, XSD.unsignedInt, XSD.unsignedShort, XSD.unsignedByte,
        XSD.long, XSD.int, XSD.short, XSD.byte,
    }
)  # fmt: skip


def _ordering_class(term) -> str | None:
    """The comparison class of ``term`` for ``<``/``>``/``<=``/``>=`` (SPARQL
    1.1 17.3: numerics, simple literals / ``xsd:string``, ``xsd:boolean``,
    ``xsd:dateTime``), or None for anything else (left to rdflib)."""
    if not isinstance(term, Literal) or term.language:
        return None
    datatype = term.datatype
    if datatype is None or datatype == XSD.string:
        return "string"
    if datatype == XSD.boolean:
        return "boolean"
    if datatype == XSD.dateTime:
        return "dateTime"
    if datatype in _NUMERIC_DATATYPES:
        return "numeric"
    return None


def normalise_directional_language(term):
    """``term`` with the language tag of a directional literal lower-cased.

    A directional literal is stored with its (language, direction) packed into
    a synthetic datatype IRI (see ``model.encoding``), so rdflib compares the
    tag's case; RDF 1.2 Concepts compares language tags case-insensitively.
    Any other term is returned unchanged.
    """
    if isinstance(term, Literal) and term.datatype is not None:
        from starlayer.graph.model.encoding import (
            decode_dirlang_datatype,
            encode_dirlang_datatype,
        )

        decoded = decode_dirlang_datatype(term.datatype)
        if decoded is not None and decoded[0] != decoded[0].lower():
            return Literal(str(term), datatype=encode_dirlang_datatype(decoded[0].lower(), decoded[1]))
    return term


def _graph_of(ctx):
    return getattr(ctx, "graph", None) or getattr(getattr(ctx, "ctx", None), "graph", None)


def _value_equal(graph, a, b) -> bool:
    """The ``=`` operator for one ``IN`` list member (RDFterm-equal)."""
    from rdflib.term import Node

    if not isinstance(a, Node) or not isinstance(b, Node):
        raise SPARQLError(f"I cannot compare this non-node: {a!r} {b!r}")
    a, b = normalise_directional_language(a), normalise_directional_language(b)
    try:
        if graph is not None:
            from starlayer.graph.query.evaluate_patches import _tt_aware_eq

            return bool(_tt_aware_eq(graph, a, b))
        return bool(a.eq(b))
    except TypeError as exc:
        raise SPARQLError(*exc.args) from exc


def _in_evalfn(expr, other, negate: bool, ctx):
    """``expr IN (other...)`` as the chain of ``=`` tests it is defined as
    (17.4.1.9): true if any member is equal; otherwise an error if any test
    raised one; otherwise false. ``NOT IN`` is its negation."""
    if isinstance(expr, SPARQLError):
        raise expr
    members = [] if other == RDF.nil else other
    graph = _graph_of(ctx)
    error = None
    for member in members:
        if isinstance(member, SPARQLError):
            error = member
            continue
        try:
            if _value_equal(graph, expr, member):
                return Literal(not negate)
        except SPARQLError as exc:
            error = exc
    if error is not None:
        raise error
    return Literal(negate)


def patch_relational_operators_follow_spec() -> bool:
    """Wraps ``RelationalExpression`` and ``ConditionalAndExpression``.

    * ``IN`` / ``NOT IN`` compared terms (``1 IN (1.0)`` was false) and
      swallowed an error in the list (``2 IN (1/0, 1)`` was false, not an
      error). Both are now chains of ``=`` tests (SPARQL 1.1 17.4.1.9).
    * ``<``/``>``/``<=``/``>=`` between a numeric, a string, a boolean and a
      dateTime of different classes (``"x" > 1``) used rdflib's cross-type
      sort order and answered true; the operator mapping (17.3) defines no
      such comparison, so it is a type error.
    * ``=`` / ``!=`` between directional literals that differ only in the case
      of the language tag compared the packed datatype IRI and answered false.
    * ``&&`` returned an error for ``1/0 && false``; the truth table (17.2)
      gives false (error && false = false).
    """
    global _relational_patch_status
    if _relational_patch_status is not None:
        return _relational_patch_status
    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser
        from rdflib.plugins.sparql.operators import EBV

        comp = rdflib_sparql_parser.RelationalExpression
        original = comp.evalfn
        if _is_marked(original):
            _relational_patch_status = True
            return True

        def _relational(e, ctx):
            op = e.op
            if op is None or e.other is None:
                return original(e, ctx)
            expr, other = e.expr, e.other
            if op in ("IN", "NOT IN"):
                return _in_evalfn(expr, other, op == "NOT IN", ctx)
            if op in ("<", ">", "<=", ">="):
                left, right = _ordering_class(expr), _ordering_class(other)
                if left is not None and right is not None and left != right:
                    raise SPARQLTypeError(f"cannot order a {left} against a {right}: {expr!r} {op} {other!r}")
            elif op in ("=", "!="):
                expr, other = normalise_directional_language(expr), normalise_directional_language(other)
            return original(SimpleNamespace(expr=expr, other=other, op=op), ctx)

        comp.setEvalFn(_marked(_relational))

        and_comp = rdflib_sparql_parser.ConditionalAndExpression

        def _and(e, ctx):
            expr, other = e.expr, e.other
            if other is None:
                return expr
            error = None
            for operand in [expr, *other]:
                try:
                    if not EBV(operand):
                        return Literal(False)
                except SPARQLError as exc:
                    error = exc
            if error is not None:
                raise error
            return Literal(True)

        and_comp.setEvalFn(_marked(_and))
        _relational_patch_status = True
    except Exception:
        _relational_patch_status = False
    return _relational_patch_status


# ---------------------------------------------------------------------------
# VALUES with no rows or no variables
# ---------------------------------------------------------------------------

_values_patch_status: bool | None = None


def patch_empty_values_clause() -> bool:
    """``VALUES ?a { }`` and ``VALUES () { () }`` crashed (``AttributeError:
    ... has no attribute 'name'``) because ``translateValues`` returned a bare
    ``[]`` instead of a ``Values`` node. Zero rows give no solutions; ``()``
    rows over zero variables each give one empty solution (grammar rules
    InlineDataOneVar / InlineDataFull).
    """
    global _values_patch_status
    if _values_patch_status is not None:
        return _values_patch_status
    try:
        from rdflib.plugins.sparql import algebra

        original = algebra.translateValues
        if _is_marked(original):
            _values_patch_status = True
            return True

        def _translate_values(v):
            if not v.var:
                return algebra.Values([{} for _ in (v.value or [])])
            if not v.value:
                return algebra.Values([])
            return original(v)

        algebra.translateValues = _marked(_translate_values)
        _values_patch_status = True
    except Exception:
        _values_patch_status = False
    return _values_patch_status


# ---------------------------------------------------------------------------
# SELECT * scope and DESCRIBE *
# ---------------------------------------------------------------------------

_select_star_patch_status: bool | None = None


def patch_select_star_scope_and_describe_star() -> bool:
    """``SELECT *`` listed variables that occur only inside a ``FILTER`` (for
    instance in ``FILTER EXISTS { ?o :p ?zz }``) as always-unbound columns;
    the in-scope variables of a group pattern (SPARQL 1.1 18.2.1) come from its
    patterns, not from filters. ``DESCRIBE *`` raised ``TypeError`` because the
    parser leaves its variable list empty; it describes the resources bound to
    the in-scope variables of the WHERE clause.
    """
    global _select_star_patch_status
    if _select_star_patch_status is not None:
        return _select_star_patch_status
    try:
        from rdflib.plugins.sparql import algebra
        from rdflib.plugins.sparql.parserutils import CompValue

        original_find_vars = algebra._findVars
        original_translate = algebra.translate
        if _is_marked(original_find_vars):
            _select_star_patch_status = True
            return True

        def _find_vars(x, res):
            if isinstance(x, CompValue) and x.name == "Filter":
                return x  # stop here: a filter binds nothing
            return original_find_vars(x, res)

        def _translate(q):
            if q.name == "DescribeQuery" and not q.var:
                found: set = set()
                if q.where is not None:
                    algebra.traverse(q.where, functools.partial(_find_vars, res=found))
                q.var = sorted(found)
            return original_translate(q)

        algebra._findVars = _marked(_find_vars)
        algebra.translate = _marked(_translate)
        _select_star_patch_status = True
    except Exception:
        _select_star_patch_status = False
    return _select_star_patch_status


def apply_all_builtin_error_patches() -> None:
    """Apply every patch in this module (called from ``starlayer.graph``)."""
    patch_ill_typed_literals_are_errors()
    patch_substr_xpath_semantics()
    patch_timezone_keeps_minutes()
    patch_strdt_requires_string_and_iri()
    patch_sum_avg_errors_are_unbound()
    patch_min_max_group_concat_terms_and_errors()
    patch_relational_operators_follow_spec()
    patch_empty_values_clause()
    patch_select_star_scope_and_describe_star()
