"""The namespaces and shared terms of the SPARQL-as-RDF vocabularies, as pyoxigraph terms (no rdflib).

``SQE`` (the public ``sqe:`` query tree), ``SPEXPR`` (the expression, variable and property-path vocabulary that ``sqe:``,
``srl:`` and ``salg:`` share) and ``SALG`` (the internal algebra encoding, kept here only because ``salg:`` is built on the
same module). The design notes (how a variable, a bare Python string, a property path or a VALUES row is encoded) are in
``sqe/vocab.py`` and, for the algebra encoding, in ``_vocab_rdflib.py``.

The rdflib-based code that is still to be converted (salg, SRL, the algebra encoder and decoder) reads the same namespaces as
rdflib terms from ``_vocab_rdflib.py``; the IRIs are identical.

Encoding of the two values that are not RDF terms:

- a SPARQL variable is ``Literal(name, datatype=spexpr:Variable)`` (``VARIABLE_DATATYPE``);
- a bare Python string (an operator symbol, a modifier keyword) is ``Literal(text, datatype=spexpr:PlainString)``
  (``PY_STR_DATATYPE``).
"""

from __future__ import annotations

from ._oxterms import NS

SALG = NS("https://github.com/hidden-graph/starlayer/ns/sparql/algebra#")
SQE = NS("https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#")
SPEXPR = NS("https://github.com/hidden-graph/starlayer/ns/sparql/expr#")

VARIABLE_DATATYPE = SPEXPR.Variable
PY_STR_DATATYPE = SPEXPR.PlainString

__all__ = ["PY_STR_DATATYPE", "SALG", "SPEXPR", "SQE", "VARIABLE_DATATYPE"]
