"""Canonical entailment regime IRIs, from the SPARQL 1.2 Entailment Regimes
spec (https://www.w3.org/TR/sparql12-entailment/) - fetched directly, not
invented. These are the values ``infer()``'s ``profile=`` and ``query()``'s
``entailment=`` accept (2026-10-07: replacing this project's own prior
starlayer-internal string keywords, ``'rdfs'``/``'owl-rl'``/``'owl-dl'``/
``'direct'``/``'rdf'`` - a full breaking change, not an added alias), and
the same IRIs a SHACL shapes graph's own ``sh:entailment`` triples carry
(see ``starlayer.shacl.entailment``), so both layers speak one vocabulary
with no separate translation table in between.

``ENTAILMENT`` is an ordinary ``rdflib.Namespace``, not individual module-
level constants - ``http://www.w3.org/ns/entailment/`` {RDF, RDFS} both
collide by bare name with ``rdflib.namespace``'s own commonly-imported
``RDF``/``RDFS`` namespace objects, so every real caller needs the
qualified ``ENTAILMENT.RDF``/``ENTAILMENT.RDFS`` form regardless; the two
hyphenated regime names (``OWL-RDF-Based``/``OWL-Direct``) need bracket
access (``ENTAILMENT["OWL-RDF-Based"]``) since a hyphen isn't valid in a
Python attribute name.

``ENTAILMENT["OWL-RDF-Based"]``'s coverage here is the OWL 2 RL *fragment*
of the full OWL 2 RDF-Based Semantics regime (rule-based, via ``owlrl``) -
not the complete regime, which is undecidable in general. Full OWL 2
RDF-Based Semantics and D-Entailment/RIF Core Entailment have no
implementation here and are not planned - see
``docs/future_enhancements.md``.

``ENTAILMENT["OWL-Direct"]`` unifies what this project previously called
``'owl-dl'`` (``infer()``) and ``'direct'`` (``query()``) - two different
names for the identical OWL 2 Direct Semantics tableau-reasoning regime,
found while replacing the string keywords with these IRIs.

Two values deliberately have no IRI and are not regimes at all: ``None``
(simple entailment / no entailment) and the string ``"native"``
(``query()`` only - delegates entailment to the connected backend/endpoint
rather than naming a regime). Both are unchanged by this migration.
"""

from __future__ import annotations

from rdflib import Namespace

ENTAILMENT = Namespace("http://www.w3.org/ns/entailment/")

# Every regime IRI this project recognizes by name, supported or not -
# used to produce a clear "unsupported regime" error (naming the IRI)
# rather than a generic "unrecognized value" one for a real-but-unbuilt
# regime like D or RIF (which has no IRI at all, so can never reach this
# set in the first place).
KNOWN_REGIMES = frozenset({ENTAILMENT.RDF, ENTAILMENT.RDFS, ENTAILMENT.D, ENTAILMENT["OWL-RDF-Based"], ENTAILMENT["OWL-Direct"]})

# Regimes this project actually implements a materialization/query path
# for. D is intentionally excluded - recognized by IRI, but unsupported
# (see module docstring) - so a caller gets "known but unsupported",
# distinct from "never heard of this IRI at all".
SUPPORTED_REGIMES = frozenset({ENTAILMENT.RDF, ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"], ENTAILMENT["OWL-Direct"]})
