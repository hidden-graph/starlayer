"""The namespaces and shared terms of the SPARQL-as-RDF vocabularies, as pyoxigraph terms (no rdflib).

``SQE`` (the public ``sqe:`` query tree) and ``SPEXPR`` (the expression, variable and property-path vocabulary that ``sqe:``
and ``srl:`` share). The design notes (how a variable, a bare Python string, a property path or a VALUES row is encoded) are in
``sqe/vocab.py``.

Encoding of the two values that are not RDF terms:

- a SPARQL variable is ``Literal(name, datatype=spexpr:Variable)`` (``VARIABLE_DATATYPE``);
- a bare Python string (an operator symbol, a modifier keyword) is ``Literal(text, datatype=spexpr:PlainString)``
  (``PY_STR_DATATYPE``).
"""

from __future__ import annotations

from ._oxterms import NS

SQE = NS("https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#")
SPEXPR = NS("https://github.com/hidden-graph/starlayer/ns/sparql/expr#")

VARIABLE_DATATYPE = SPEXPR.Variable
PY_STR_DATATYPE = SPEXPR.PlainString

__all__ = ["PY_STR_DATATYPE", "SPEXPR", "SQE", "VARIABLE_DATATYPE"]
