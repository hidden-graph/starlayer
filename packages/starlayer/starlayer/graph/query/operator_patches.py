"""Targeted compatibility shims for confirmed bugs in plain rdflib's own
SPARQL arithmetic/numeric-function evaluation (``rdflib.plugins.sparql``) -
not bugs in this repo's own query rewriting. Found via the W3C SHACL 1.2
test suite's Node Expressions and Rules fixtures
(``docs/w3c-shacl12-test-suite-plan.md`` in the ``starShacl`` repo); each
bug reproduces against plain ``rdflib.Graph().query()`` with no
starlayer.graph/pySHACL involvement.

Every patch here follows the same idempotent apply-once pattern used elsewhere
in this project for third-party monkeypatches: a module-level
``_xxx_patch_status: bool | None`` flag plus a marker attribute on the
patched callable, so repeated calls (e.g. from multiple import sites) are
safe no-ops.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

from rdflib import BNode, Literal
from rdflib.namespace import XSD
from rdflib.plugins.sparql import operators as _rdflib_operators
from rdflib.plugins.sparql.datatypes import type_promotion
from rdflib.plugins.sparql.parserutils import Comp
from rdflib.plugins.sparql.sparql import SPARQLError


def numeric(expr):
    """rdflib's ``operators.numeric`` looked up at call time, so the strict
    version installed by ``builtin_error_patches`` is the one used here."""
    return _rdflib_operators.numeric(expr)


def _iter_subexpressions(pyparsing_element):
    exprs = getattr(pyparsing_element, "exprs", None)
    if exprs:
        yield from exprs
    sub = getattr(pyparsing_element, "expr", None)
    if sub is not None:
        yield sub


def _find_comp(root, name, _seen=None):
    """Locate a named ``Comp`` grammar node inside rdflib's already-built
    pyparsing SPARQL grammar tree.

    ``Comp.postParse`` reads ``self.evalfn`` fresh on every parse (it's a
    plain mutable instance attribute, not a closure baked in at
    grammar-definition time), so calling ``.setEvalFn()`` on the node found
    here changes behavior for every future ``.query()`` call.

    Args:
        root: The pyparsing grammar node to search from.
        name: The ``Comp`` node's ``.name`` to match.
        _seen: Internal recursion guard - set of already-visited node ids.

    Returns:
        The matching ``Comp`` node, or ``None`` if not found.
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
    omits the trailing ``.0``.

    Args:
        literal: The ``Literal`` to canonicalize.

    Returns:
        A re-lexicalized ``Literal`` with a trailing ``.0`` if ``literal``
        is ``xsd:decimal``-typed and missing a decimal point; otherwise
        ``literal`` unchanged.
    """
    if literal.datatype == XSD.decimal and "." not in str(literal):
        return Literal(f"{literal}.0", datatype=XSD.decimal)
    return literal


_multiplicative_expression_patch_status: bool | None = None


def _float_divide(a: float, b: float) -> float:
    """IEEE 754 division, as XPath op:numeric-divide defines it for double and
    float (Python raises ``ZeroDivisionError`` instead of returning INF/NaN)."""
    if b == 0:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def _non_finite_lexical(value: float) -> str:
    """The XSD lexical form of INF, -INF and NaN (rdflib writes ``inf``/``nan``)."""
    if math.isnan(value):
        return "NaN"
    return "INF" if value > 0 else "-INF"


def patch_multiplicative_expression_type_promotion() -> bool:
    """Fix a confirmed rdflib bug: ``MultiplicativeExpression`` (the ``*``/
    ``/`` operators) never applies SPARQL 1.1's numeric type-promotion rules
    the way ``AdditiveExpression`` (``+``/``-``) already does - it always
    computes via ``Decimal`` and returns ``Literal(res)`` with no explicit
    ``datatype=``, so rdflib infers ``xsd:decimal`` from the Python
    ``Decimal`` type regardless of the operands' actual datatypes. Per
    SPARQL 1.1's op:numeric-multiply, ``xsd:integer * xsd:integer`` must
    stay ``xsd:integer`` - stock rdflib instead returns
    ``"42"^^xsd:decimal`` for ``6 * 7``, not ``"42"^^xsd:integer``.

    Division is different: op:numeric-divide always promotes to at least
    ``xsd:decimal`` even for two integers (this part of rdflib's behavior
    is already correct) - but the whole-number *lexical form* it produces
    for that case is separately broken (see
    ``patch_decimal_result_lexical_form`` below) and is also fixed here,
    since both live in the same function.

    Idempotent and defensive, matching the established
    ``starlayer.shacl.validator`` patch idiom - returns ``False`` without
    raising if rdflib's internals don't match what this shim expects.
    """
    global _multiplicative_expression_patch_status
    if _multiplicative_expression_patch_status is not None:
        return _multiplicative_expression_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = rdflib_sparql_parser.MultiplicativeExpression
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayer_graph_multiplicative_type_promotion_patch", False):
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
                for op_, f in zip(e.op, other, strict=True):
                    n = numeric(f)
                    if type(n) == float:  # noqa: E721
                        res = float(res)
                    if op_ == "*":
                        res = res * n
                        dt = type_promotion(dt, f.datatype)
                    else:
                        promoted = type_promotion(dt, f.datatype)
                        if promoted in (XSD.double, XSD.float):
                            # op:numeric-divide on doubles/floats never
                            # raises: x/0 is INF, -INF or NaN.
                            res = _float_divide(float(res), float(n))
                        else:
                            res = res / n
                        dt = XSD.decimal if promoted == XSD.integer else promoted
            except (InvalidOperation, ZeroDivisionError) as exc:
                raise SPARQLError("divide by 0") from exc
            if isinstance(res, float) and not math.isfinite(res):
                return Literal(_non_finite_lexical(res), datatype=dt, normalize=False)
            return _canonicalize_decimal_lexical_form(Literal(res, datatype=dt))

        _patched_multiplicative_expression._starlayer_graph_multiplicative_type_promotion_patch = True  # type: ignore[attr-defined]
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
    decimal form ``"4.0"``. rdflib's own default datatype inference for a
    ``Decimal`` value has the same gap (``Literal(Decimal(42))``
    lexicalizes as ``"42"``, not ``"42.0"``) - the fractional-zero digit
    only survives if it's already present in whatever value is handed to
    ``Decimal(...)``/``Literal(...)``, which these functions never do.

    Idempotent and defensive, matching the established
    ``starlayer.shacl.validator`` patch idiom.
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

        if getattr(comps["Builtin_CEIL"].evalfn, "_starlayer_graph_decimal_lexical_form_patch", False):
            _decimal_result_lexical_form_patch_status = True
            return True

        def _make_patched(name, transform):
            def _patched(expr, ctx):
                l_ = expr.arg
                result = Literal(transform(numeric(l_)), datatype=l_.datatype)
                return _canonicalize_decimal_lexical_form(result)

            _patched._starlayer_graph_decimal_lexical_form_patch = True  # type: ignore[attr-defined]
            return _patched

        for name, transform in targets.items():
            comps[name].setEvalFn(_make_patched(name, transform))

        _decimal_result_lexical_form_patch_status = True
    except Exception:
        _decimal_result_lexical_form_patch_status = False

    return _decimal_result_lexical_form_patch_status


_integer_cast_patch_status: bool | None = None


def patch_integer_cast_from_numeric_and_boolean() -> bool:
    """Fix a confirmed rdflib bug: ``xsd:integer(x)`` casts through
    ``int(<lexical form>)``, so a cast from an ``xsd:decimal``, ``xsd:double``,
    ``xsd:float`` or ``xsd:boolean`` is an error (``xsd:integer(16.0934)``,
    ``xsd:integer(true)``) although SPARQL 1.1 §17.5 (via XPath casting) allows
    each of these: a number is truncated toward zero, ``true`` is 1 and
    ``false`` is 0. ``NaN`` and the infinities stay errors. A string argument
    is still cast from its lexical form, so ``xsd:integer("16.0934")``
    remains an error, as it should.

    Wraps rdflib's registered ``xsd:integer`` cast, handling only those source
    types and deferring to the original for everything else. Idempotent and
    defensive, like the other patches in this module.
    """
    global _integer_cast_patch_status
    if _integer_cast_patch_status is not None:
        return _integer_cast_patch_status

    try:
        from rdflib.plugins.sparql import operators as rdflib_operators

        original, raw = rdflib_operators._CUSTOM_FUNCTIONS[XSD.integer]
        if getattr(original, "_starlayer_graph_integer_cast_patch", False):
            _integer_cast_patch_status = True
            return True

        def _patched_integer_cast(e, ctx):
            args = e.expr
            if args and len(args) == 1 and isinstance(args[0], Literal):
                arg = args[0]
                if arg.datatype in (XSD.decimal, XSD.double, XSD.float):
                    value = arg.toPython()
                    try:
                        return Literal(int(value), datatype=XSD.integer)
                    except (ValueError, OverflowError, TypeError, InvalidOperation):
                        raise SPARQLError(f"Cannot cast {arg!r} to xsd:integer") from None
                if arg.datatype == XSD.boolean:
                    return Literal(int(bool(arg.toPython())), datatype=XSD.integer)
            return original(e, ctx)

        _patched_integer_cast._starlayer_graph_integer_cast_patch = True  # type: ignore[attr-defined]
        rdflib_operators.register_custom_function(XSD.integer, _patched_integer_cast, override=True, raw=True)
        _integer_cast_patch_status = True
    except Exception:
        _integer_cast_patch_status = False

    return _integer_cast_patch_status


_strlang_empty_tag_patch_status: bool | None = None


def patch_strlang_rejects_empty_language_tag() -> bool:
    """Fix a confirmed rdflib bug: ``STRLANG("a", "")`` returns the plain
    string ``"a"`` (an empty ``lang=`` is treated as no language), but an empty
    language tag is not a valid tag, so the call is an error and the result
    unbound (SPARQL 1.2 Query, ``STRLANG``).

    Wraps rdflib's ``Builtin_STRLANG`` evaluation function and raises
    ``SPARQLError`` for an empty tag; everything else is delegated unchanged.
    Idempotent and defensive, like the other patches in this module.
    """
    global _strlang_empty_tag_patch_status
    if _strlang_empty_tag_patch_status is not None:
        return _strlang_empty_tag_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = _find_comp(rdflib_sparql_parser.Expression, "Builtin_STRLANG")
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayer_graph_strlang_empty_tag_patch", False):
            _strlang_empty_tag_patch_status = True
            return True

        def _patched_strlang(e, ctx):
            if str(e.arg2) == "":
                raise SPARQLError("STRLANG: the language tag must not be empty")
            try:
                return original_evalfn(e, ctx)
            except ValueError as exc:
                # rdflib raises ValueError for a tag that is not valid BCP 47
                # ("!!", "e n", "en--ltr"); that must be a SPARQL error (the
                # result is unbound), not an exception that aborts the query.
                raise SPARQLError(f"STRLANG: invalid language tag: {exc}") from exc

        _patched_strlang._starlayer_graph_strlang_empty_tag_patch = True  # type: ignore[attr-defined]
        comp.setEvalFn(_patched_strlang)
        _strlang_empty_tag_patch_status = True
    except Exception:
        _strlang_empty_tag_patch_status = False

    return _strlang_empty_tag_patch_status


_sameterm_string_patch_status: bool | None = None


def _string_identity_key(term):
    """A literal with no language and datatype ``xsd:string`` is the same RDF
    term as the simple literal of that text (RDF 1.1/1.2 Concepts); map both to
    one key. Other terms are returned unchanged."""
    if (
        isinstance(term, Literal)
        and term.language is None
        and term.datatype in (None, XSD.string)
    ):
        return ("string", str(term))
    # Language tags compare case-insensitively (RDF 1.2 Concepts); a
    # directional literal keeps its tag inside a synthetic datatype IRI, so
    # lower-case it here.
    from starlayer.graph.query.builtin_error_patches import (
        normalise_directional_language,
    )

    return normalise_directional_language(term)


def patch_sameterm_simple_literal_is_xsd_string() -> bool:
    """Fix a confirmed rdflib bug: ``sameTerm("foo", "foo"^^xsd:string)`` is
    false because rdflib compares ``Literal("foo") == Literal("foo",
    datatype=XSD.string)`` as different terms, though RDF Concepts defines a
    simple literal as shorthand for the ``xsd:string`` literal.

    Fixes ``sameTerm()`` only. Matching a triple pattern against stored data
    still distinguishes the two forms, because the store compares them as
    different terms; correcting that means changing ``Literal`` itself.
    Idempotent and defensive, like the other patches in this module.
    """
    global _sameterm_string_patch_status
    if _sameterm_string_patch_status is not None:
        return _sameterm_string_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        comp = _find_comp(rdflib_sparql_parser.Expression, "Builtin_sameTerm")
        original_evalfn = comp.evalfn
        if getattr(original_evalfn, "_starlayer_graph_sameterm_string_patch", False):
            _sameterm_string_patch_status = True
            return True

        def _patched_sameterm(e, ctx):
            return Literal(_string_identity_key(e.arg1) == _string_identity_key(e.arg2))

        _patched_sameterm._starlayer_graph_sameterm_string_patch = True  # type: ignore[attr-defined]
        comp.setEvalFn(_patched_sameterm)
        _sameterm_string_patch_status = True
    except Exception:
        _sameterm_string_patch_status = False

    return _sameterm_string_patch_status


_triple_term_not_iri_patch_status: bool | None = None


def _is_encoded_triple_term(term) -> bool:
    from rdflib import URIRef

    from starlayer.graph.model.encoding import TT_NS

    return isinstance(term, URIRef) and str(term).startswith(TT_NS)


def patch_triple_terms_are_not_iris() -> bool:
    """Fix a leak of the internal triple-term encoding: on the rdf-1.1 backend a triple term is a ``tt:`` IRI, so
    ``isIRI(?t)`` was true and ``STR(?t)`` returned the internal IRI text. The term kinds are disjoint in SPARQL 1.2
    (17.4.2.3: ``isIRI`` is true only for an IRI) and ``STR`` applies to IRIs and literals only, so ``isIRI`` is false and
    ``STR`` an error for a triple term, as in Oxigraph (GitHub issue #74). ``STR`` of a blank node is an error too (rdflib
    returns the label; the native backends already give an error; GitHub issue #75).

    Wraps rdflib's ``Builtin_isIRI`` and ``Builtin_STR`` evaluation functions; idempotent and defensive like the others here.
    """
    global _triple_term_not_iri_patch_status
    if _triple_term_not_iri_patch_status is not None:
        return _triple_term_not_iri_patch_status

    try:
        from rdflib.plugins.sparql import parser as rdflib_sparql_parser

        is_iri = _find_comp(rdflib_sparql_parser.Expression, "Builtin_isIRI")
        str_comp = _find_comp(rdflib_sparql_parser.Expression, "Builtin_STR")
        if getattr(is_iri.evalfn, "_starlayer_graph_tt_not_iri_patch", False):
            _triple_term_not_iri_patch_status = True
            return True
        original_is_iri, original_str = is_iri.evalfn, str_comp.evalfn

        def _patched_is_iri(e, ctx):
            if _is_encoded_triple_term(e.arg):
                return Literal(False)
            return original_is_iri(e, ctx)

        def _patched_str(e, ctx):
            if _is_encoded_triple_term(e.arg):
                raise SPARQLError("STR: a triple term has no string form")
            if isinstance(e.arg, BNode):
                # SPARQL 1.1 17.4.2.5: STR is defined for IRIs and literals only; rdflib returns the label (GitHub issue #75)
                raise SPARQLError("STR: a blank node has no string form")
            return original_str(e, ctx)

        _patched_is_iri._starlayer_graph_tt_not_iri_patch = True  # type: ignore[attr-defined]
        _patched_str._starlayer_graph_tt_not_iri_patch = True  # type: ignore[attr-defined]
        is_iri.setEvalFn(_patched_is_iri)
        str_comp.setEvalFn(_patched_str)
        _triple_term_not_iri_patch_status = True
    except Exception:
        _triple_term_not_iri_patch_status = False

    return _triple_term_not_iri_patch_status


def apply_all_operator_patches() -> None:
    """Apply every patch in this module. Called eagerly from ``starlayer.graph/__init__.py`` so
    every consumer of this package gets spec-correct arithmetic, regardless
    of whether they use any triple-term-specific feature.
    """
    patch_multiplicative_expression_type_promotion()
    patch_decimal_result_lexical_form()
    patch_integer_cast_from_numeric_and_boolean()
    patch_strlang_rejects_empty_language_tag()
    patch_sameterm_simple_literal_is_xsd_string()
    patch_triple_terms_are_not_iris()
