"""``_EXPR_NODE_FAMILY``: name -> argument-signature family, for every SPARQL expression builtin (the node names are the parser's, and the
class names of the tree: ``STR``, ``REPLACE``, ``isIRI``, ...). The one source of truth for ``expr_validation.py``, which generates the per-builtin
SHACL shapes of the shared ``spexpr:`` vocabulary from it. The family for each name is the shape of the parser's node, not guessed
from the name (``REPLACE``'s fields are ``arg``/``pattern``/``replacement``/``flags``, not ``arg1``..``arg4``;
``BNODE``'s sole argument is optional unlike every other one-arg builtin).
"""

from __future__ import annotations

_EXPR_NODE_FAMILY: dict[str, str] = {
    # zero-arg
    "NOW": "ZeroArg", "UUID": "ZeroArg",
    "STRUUID": "ZeroArg", "RAND": "ZeroArg",
    # one-arg (salg:arg, required)
    "STR": "OneArg", "LCASE": "OneArg", "UCASE": "OneArg",
    "ABS": "OneArg", "CEIL": "OneArg", "FLOOR": "OneArg",
    "ROUND": "OneArg", "isIRI": "OneArg", "isURI": "OneArg",
    "isBLANK": "OneArg", "isLITERAL": "OneArg", "isNUMERIC": "OneArg",
    "BOUND": "OneArg", "DATATYPE": "OneArg", "LANG": "OneArg",
    "ENCODE_FOR_URI": "OneArg", "MD5": "OneArg", "SHA1": "OneArg",
    "SHA256": "OneArg", "SHA384": "OneArg", "SHA512": "OneArg",
    "STRLEN": "OneArg", "YEAR": "OneArg", "MONTH": "OneArg",
    "DAY": "OneArg", "HOURS": "OneArg", "MINUTES": "OneArg",
    "SECONDS": "OneArg", "TIMEZONE": "OneArg", "TZ": "OneArg",
    "IRI": "OneArg", "URI": "OneArg",
    # RDF 1.2 (SPARQL 1.2 sec 17.4): triple-term accessors and base-direction functions
    "isTRIPLE": "OneArg", "SUBJECT": "OneArg", "PREDICATE": "OneArg",
    "OBJECT": "OneArg", "LANGDIR": "OneArg", "hasLANG": "OneArg",
    "hasLANGDIR": "OneArg",
    # one-arg, but optional (BNODE() vs BNODE(?x) - see _OptionalOneArgExprBodyShape)
    "BNODE": "OptionalOneArg",
    # unary (salg:expr, required)
    "UnaryNot": "Unary", "UnaryMinus": "Unary", "UnaryPlus": "Unary",
    # two-arg (salg:arg1/arg2)
    "STRSTARTS": "TwoArg", "STRENDS": "TwoArg", "CONTAINS": "TwoArg",
    "STRBEFORE": "TwoArg", "STRAFTER": "TwoArg", "STRLANG": "TwoArg",
    "STRDT": "TwoArg", "sameTerm": "TwoArg", "LANGMATCHES": "TwoArg",
    # three-arg (salg:arg1/arg2/arg3)
    "IF": "ThreeArg",
    # variadic (salg:arg is a list)
    "CONCAT": "VariadicArg", "COALESCE": "VariadicArg",
    # unique key names
    "STRLANGDIR": "StrLangDir",
    "REGEX": "Regex", "REPLACE": "Replace", "SUBSTR": "Substr",
    "FunctionCall": "FunctionCall",
    "RelationalExpression": "Relational",
    "ConditionalAndExpression": "Conditional", "ConditionalOrExpression": "Conditional",
    "AdditiveExpression": "Arithmetic", "MultiplicativeExpression": "Arithmetic",
}
