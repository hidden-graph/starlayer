"""Every SPARQL (1.1 and 1.2) function name with a small example call, and whether SRL's BuiltInCall
production (spec [118], W3C WD 14 October 2026) includes it.

``SPEC`` is read from the vendored grammar table, not typed in, so it moves with the spec.
"""

from __future__ import annotations

import re

from .grammar import PRODUCTIONS

# The quoted keywords of the BuiltInCall production, minus the structural ones.
SPEC: frozenset[str] = frozenset(re.findall(r"'([A-Za-z_0-9]+)'", PRODUCTIONS["BuiltInCall"]))

CALLS: dict[str, str] = {
    # in the spec's BuiltInCall
    "STR": "STR(?y)", "LANG": "LANG(?y)", "LANGMATCHES": 'LANGMATCHES(?y, "en")', "LANGDIR": "LANGDIR(?y)",
    "DATATYPE": "DATATYPE(?y)", "IRI": "IRI(?y)", "URI": "URI(?y)", "BNODE": "BNODE()", "ABS": "ABS(?y)",
    "CEIL": "CEIL(?y)", "FLOOR": "FLOOR(?y)", "ROUND": "ROUND(?y)", "CONCAT": "CONCAT(?y, ?y)",
    "SUBSTR": "SUBSTR(?y, 1)", "STRLEN": "STRLEN(?y)", "REPLACE": 'REPLACE(?y, "a", "b")', "UCASE": "UCASE(?y)",
    "LCASE": "LCASE(?y)", "ENCODE_FOR_URI": "ENCODE_FOR_URI(?y)", "CONTAINS": "CONTAINS(?y, ?y)",
    "STRSTARTS": "STRSTARTS(?y, ?y)", "STRENDS": "STRENDS(?y, ?y)", "STRBEFORE": "STRBEFORE(?y, ?y)",
    "STRAFTER": "STRAFTER(?y, ?y)", "YEAR": "YEAR(?y)", "MONTH": "MONTH(?y)", "DAY": "DAY(?y)",
    "HOURS": "HOURS(?y)", "MINUTES": "MINUTES(?y)", "SECONDS": "SECONDS(?y)", "TIMEZONE": "TIMEZONE(?y)",
    "TZ": "TZ(?y)", "NOW": "NOW()", "UUID": "UUID()", "STRUUID": "STRUUID()", "IF": "IF(?y, ?y, ?y)",
    "STRLANG": 'STRLANG(?y, "en")', "STRLANGDIR": 'STRLANGDIR(?y, "en", "ltr")', "STRDT": "STRDT(?y, :t)",
    "sameTerm": "sameTerm(?y, ?y)", "isIRI": "isIRI(?y)", "isURI": "isURI(?y)", "isBLANK": "isBLANK(?y)",
    "isLITERAL": "isLITERAL(?y)", "isNUMERIC": "isNUMERIC(?y)", "hasLANG": "hasLANG(?y)",
    "hasLANGDIR": "hasLANGDIR(?y)", "REGEX": 'REGEX(?y, "a")', "isTRIPLE": "isTRIPLE(?y)",
    "TRIPLE": "TRIPLE(?y, :p, ?y)", "SUBJECT": "SUBJECT(?y)", "PREDICATE": "PREDICATE(?y)", "OBJECT": "OBJECT(?y)",
    # in SPARQL but not in the spec's BuiltInCall
    "BOUND": "BOUND(?y)", "COALESCE": "COALESCE(?y, ?y)", "RAND": "RAND()", "MD5": "MD5(?y)", "SHA1": "SHA1(?y)",
    "SHA256": "SHA256(?y)", "SHA384": "SHA384(?y)", "SHA512": "SHA512(?y)",
    "EXISTS": "EXISTS { ?x :q ?y }", "NOT EXISTS": "NOT EXISTS { ?x :q ?y }",
    "COUNT": "COUNT(?y)", "SUM": "SUM(?y)", "MIN": "MIN(?y)", "MAX": "MAX(?y)", "AVG": "AVG(?y)",
    "SAMPLE": "SAMPLE(?y)", "GROUP_CONCAT": "GROUP_CONCAT(?y)",
}

IN_SPEC = {name: call for name, call in CALLS.items() if name in SPEC}
NOT_IN_SPEC = {name: call for name, call in CALLS.items() if name not in SPEC}
