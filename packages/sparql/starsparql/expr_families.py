"""``_EXPR_NODE_FAMILY``: name -> argument-signature family, for every one
of rdflib's 63 expression builtins. Shared, dependency-free source of truth
for both ``shapes.py`` (generates per-builtin SHACL shapes from it) and
``ontology.py`` (generates per-builtin ``rdfs:subClassOf`` declarations from
it) — lives in its own module, not either of those, specifically so
``ontology.py`` never needs ``pyshacl`` (a ``shapes.py``-only dependency)
just to read this table.

``from_rdf._discover_expr_evalfns()`` is the live source of truth for the
*name list* (rebuilt by walking rdflib's own pyparsing grammar, so it can't
drift out of sync with whatever rdflib version is installed); the family for
each name was confirmed by building a real query exercising it and
inspecting the decoded algebra node's own keys directly — not guessed from
the name, since that's genuinely unreliable here (e.g. ``Builtin_REPLACE``'s
keys are ``arg``/``pattern``/``replacement``/``flags``, not
``arg1``..``arg4``; ``Builtin_BNODE``'s sole argument is optional unlike
every other one-arg builtin).
"""

from __future__ import annotations

_EXPR_NODE_FAMILY: dict[str, str] = {
    # zero-arg
    "Builtin_NOW": "ZeroArg", "Builtin_UUID": "ZeroArg",
    "Builtin_STRUUID": "ZeroArg", "Builtin_RAND": "ZeroArg",
    # one-arg (salg:arg, required)
    "Builtin_STR": "OneArg", "Builtin_LCASE": "OneArg", "Builtin_UCASE": "OneArg",
    "Builtin_ABS": "OneArg", "Builtin_CEIL": "OneArg", "Builtin_FLOOR": "OneArg",
    "Builtin_ROUND": "OneArg", "Builtin_isIRI": "OneArg", "Builtin_isURI": "OneArg",
    "Builtin_isBLANK": "OneArg", "Builtin_isLITERAL": "OneArg", "Builtin_isNUMERIC": "OneArg",
    "Builtin_BOUND": "OneArg", "Builtin_DATATYPE": "OneArg", "Builtin_LANG": "OneArg",
    "Builtin_ENCODE_FOR_URI": "OneArg", "Builtin_MD5": "OneArg", "Builtin_SHA1": "OneArg",
    "Builtin_SHA256": "OneArg", "Builtin_SHA384": "OneArg", "Builtin_SHA512": "OneArg",
    "Builtin_STRLEN": "OneArg", "Builtin_YEAR": "OneArg", "Builtin_MONTH": "OneArg",
    "Builtin_DAY": "OneArg", "Builtin_HOURS": "OneArg", "Builtin_MINUTES": "OneArg",
    "Builtin_SECONDS": "OneArg", "Builtin_TIMEZONE": "OneArg", "Builtin_TZ": "OneArg",
    "Builtin_IRI": "OneArg", "Builtin_URI": "OneArg",
    # one-arg, but optional (BNODE() vs BNODE(?x) - see _OptionalOneArgExprBodyShape)
    "Builtin_BNODE": "OptionalOneArg",
    # unary (salg:expr, required)
    "UnaryNot": "Unary", "UnaryMinus": "Unary", "UnaryPlus": "Unary",
    # two-arg (salg:arg1/arg2)
    "Builtin_STRSTARTS": "TwoArg", "Builtin_STRENDS": "TwoArg", "Builtin_CONTAINS": "TwoArg",
    "Builtin_STRBEFORE": "TwoArg", "Builtin_STRAFTER": "TwoArg", "Builtin_STRLANG": "TwoArg",
    "Builtin_STRDT": "TwoArg", "Builtin_sameTerm": "TwoArg", "Builtin_LANGMATCHES": "TwoArg",
    # three-arg (salg:arg1/arg2/arg3)
    "Builtin_IF": "ThreeArg",
    # variadic (salg:arg is a list)
    "Builtin_CONCAT": "VariadicArg", "Builtin_COALESCE": "VariadicArg",
    # unique key names
    "Builtin_REGEX": "Regex", "Builtin_REPLACE": "Replace", "Builtin_SUBSTR": "Substr",
    "Builtin_EXISTS": "Exists", "Builtin_NOTEXISTS": "Exists",
    "Function": "Function",
    "RelationalExpression": "Relational",
    "ConditionalAndExpression": "Conditional", "ConditionalOrExpression": "Conditional",
    "AdditiveExpression": "Arithmetic", "MultiplicativeExpression": "Arithmetic",
}
