"""Targeted compatibility shims for confirmed bugs in plain rdflib's own
SPARQL arithmetic/numeric-function evaluation (``rdflib.plugins.sparql``) -
not bugs in this repo's own query rewriting. Found via the W3C SHACL 1.2
test suite's Node Expressions and Rules fixtures
(``docs/w3c-shacl12-test-suite-plan.md`` in the ``starShacl`` repo), and
confirmed independently of any starlayergraph/pyshacl-starlayergraph code with plain
``rdflib.Graph().query()`` reproductions.

Both patches follow the same idempotent apply-once pattern used elsewhere
in this project for third-party monkeypatches: a module-level
``_xxx_patch_status: bool | None`` flag plus a marker attribute on the
patched callable, so repeated calls (e.g. from multiple import sites) are
safe no-ops.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

from rdflib import Literal
from rdflib.namespace import XSD
from rdflib.plugins.sparql.datatypes import type_promotion
from rdflib.plugins.sparql.operators import numeric
from rdflib.plugins.sparql.parserutils import Comp
from rdflib.plugins.sparql.sparql import SPARQLError


def _iter_subexpressions(pyparsing_element):
    exprs = getattr(pyparsing_element, "exprs", None)
    if exprs:
        yield from exprs
    sub = getattr(pyparsing_element, "expr", None)
    if sub is not None:
        yield sub


def _find_comp(root, name, _seen=None):
    """Locate a named ``Comp`` grammar node inside rdflib's already-built
    pyparsing SPARQL grammar tree. ``Comp.postParse`` reads ``self.evalfn``
    fresh on every parse (it's a plain mutable instance attribute, not a
    closure baked in at grammar-definition time), so calling
    ``.setEvalFn()`` on the node found here changes behavior for every
    future ``.query()`` call - confirmed empirically before relying on it.
    """
    if _seen is None:
        _seen = set()
    if id(root) in _seen:
        return None
    _seen.add(id(root))
    if isinstance(root, Comp) and root.name == name:
        return root
    for sub in _iter_subexpressions(root):
        found = _find_comp(sub, name, _seen)
        if found is not None:
            return found
    return None


def _canonicalize_decimal_lexical_form(literal: Literal) -> Literal:
    """XSD decimal's canonical lexical form requires a decimal point with
    at least one digit on each side (e.g. ``"42.0"``, not ``"42"``) - but
    rdflib's own CEIL/FLOOR/ROUND/division construct a whole-number decimal
    result via a Python ``int``/exact ``Decimal``, whose default string form
    omits the trailing ``.0``. A no-op for any non-decimal-typed or
    already-fractional literal.
    """
    if literal.datatype == XSD.decimal and "." not in str(literal):
        return Literal(f"{literal}.0", datatype=XSD.decimal)
    return literal


_multiplicative_expression_patch_status: bool | None = None


def patch_multiplicative_expression_type_promotion() -> bool:
    """Fix a confirmed rdflib bug: ``MultiplicativeExpression`` (the ``*``/
    ``/`` operators) never applies SPARQL 1.1's numeric type-promotion rules
    the way ``AdditiveExpression`` (``+``/``-``) already does - it always
    computes via ``Decimal`` and returns ``Literal(res)`` with no explicit
    ``datatype=``, so rdflib infers ``xsd:decimal`` from the Python
    ``Decimal`` type regardless of the operands' actual datatypes. Per
    SPARQL 1.1's op:numeric-multiply, ``xsd:integer * xsd:integer`` must
    stay ``xsd:integer`` - confirmed live against plain
    ``rdflib.Graph().query()`` (7.6.0), no starlayergraph/pyshacl-starlayergraph
    involved: ``6 * 7`` returns ``"42"^^xsd:decimal``, not
    ``"42"^^xsd:integer``.

    Division is different: op:numeric-divide always promotes to at least
    ``xsd:decimal`` even for two integers (this part of rdflib's behavior
    is already correct) - but the whole-number *lexical form* it produces
    for that case is separately broken (see
    ``patch_decimal_result_lexical_form`` below) and is also fixed here,
    since both live in the same function.

    Idempotent and defensive, matching the established
    ``pyshacl_starlayergraph/validator.py`` patch idiom - returns ``False``
    without raising if rdflib's internals don't match what this shim
    expects.
    """
    global _multiplicative_expression_patch_status
    if _multiplicative_expression_patch_status is not None:
        return _multiplicative_expression_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = rdflib_sparql_parser.MultiplicativeExpression
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayergraph_multiplicative_type_promotion_patch", False):
            _multiplicative_expression_patch_status = True
            return True

        def _patched_multiplicative_expression(e, ctx):
            expr = e.expr
            other = e.other
            if other is None:
                return expr
            try:
                res: Decimal | float = Decimal(numeric(expr))
                dt = expr.datatype
                for op_, f in zip(e.op, other):
                    n = numeric(f)
                    if type(n) == float:  # noqa: E721
                        res = float(res)
                    if op_ == "*":
                        res = res * n
                        dt = type_promotion(dt, f.datatype)
                    else:
                        res = res / n
                        promoted = type_promotion(dt, f.datatype)
                        dt = XSD.decimal if promoted == XSD.integer else promoted
            except (InvalidOperation, ZeroDivisionError):
                raise SPARQLError("divide by 0")
            return _canonicalize_decimal_lexical_form(Literal(res, datatype=dt))

        _patched_multiplicative_expression._starlayergraph_multiplicative_type_promotion_patch = True  # type: ignore[attr-defined]
        comp.setEvalFn(_patched_multiplicative_expression)
        _multiplicative_expression_patch_status = True
    except Exception:
        _multiplicative_expression_patch_status = False

    return _multiplicative_expression_patch_status


_decimal_result_lexical_form_patch_status: bool | None = None


def patch_decimal_result_lexical_form() -> bool:
    """Fix a confirmed rdflib bug: ``Builtin_CEIL``/``Builtin_FLOOR``/
    ``Builtin_ROUND`` correctly preserve the argument's ``xsd:decimal``
    datatype, but construct the result via ``Literal(int(...), datatype=...)``
    - a raw Python ``int`` lexicalizes as e.g. ``"4"``, not the canonical
    decimal form ``"4.0"``. Confirmed live: ``Literal(Decimal(42))``
    (rdflib's own default datatype inference for a ``Decimal`` value)
    already lexicalizes as ``"42"``, not ``"42.0"`` - the fractional-zero
    digit only survives if it's already present in whatever value is
    handed to ``Decimal(...)``/``Literal(...)``, which these functions
    never do.

    Idempotent and defensive, matching the established
    ``pyshacl_starlayergraph/validator.py`` patch idiom.
    """
    global _decimal_result_lexical_form_patch_status
    if _decimal_result_lexical_form_patch_status is not None:
        return _decimal_result_lexical_form_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        targets = {
            "Builtin_CEIL": lambda v: int(math.ceil(v)),
            "Builtin_FLOOR": lambda v: int(math.floor(v)),
            "Builtin_ROUND": lambda v: int(
                Decimal(v).quantize(1, ROUND_HALF_UP if v > 0 else ROUND_HALF_DOWN)
            ),
        }

        comps = {}
        for name in targets:
            comp = _find_comp(rdflib_sparql_parser.BuiltInCall, name)
            if comp is None:
                _decimal_result_lexical_form_patch_status = False
                return False
            comps[name] = comp

        if getattr(comps["Builtin_CEIL"].evalfn, "_starlayergraph_decimal_lexical_form_patch", False):
            _decimal_result_lexical_form_patch_status = True
            return True

        def _make_patched(name, transform):
            def _patched(expr, ctx):
                l_ = expr.arg
                result = Literal(transform(numeric(l_)), datatype=l_.datatype)
                return _canonicalize_decimal_lexical_form(result)

            _patched._starlayergraph_decimal_lexical_form_patch = True  # type: ignore[attr-defined]
            return _patched

        for name, transform in targets.items():
            comps[name].setEvalFn(_make_patched(name, transform))

        _decimal_result_lexical_form_patch_status = True
    except Exception:
        _decimal_result_lexical_form_patch_status = False

    return _decimal_result_lexical_form_patch_status


def apply_all_operator_patches() -> None:
    """Apply both patches. Called eagerly from ``starlayergraph/__init__.py`` so
    every consumer of this package gets spec-correct arithmetic, regardless
    of whether they use any triple-term-specific feature.
    """
    patch_multiplicative_expression_type_promotion()
    patch_decimal_result_lexical_form()
