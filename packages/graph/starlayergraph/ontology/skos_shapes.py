"""SHACL shapes checking the W3C SKOS Reference's own numbered "Documented
Consistency and Integrity Conditions" (https://www.w3.org/TR/skos-reference/)
against a plain SKOS graph. Mirrors the sibling ``manchester_shapes.py``
module's loader/validate shape exactly - see that module's own docstring for
the design rationale, not re-derived here.

Unlike ``manch:``/``salg:``, SKOS needs no encode/decode layer at all - a
SKOS thesaurus is already plain RDF the moment it's authored. This module is
purely a validator: does a given graph satisfy SKOS's own formal semantics.

Scope: the spec's own numbered integrity conditions only (S9, S13, S14,
S19/S20, S27, S46 - see ``skos_shapes.ttl``'s own per-shape comments), not
vocabulary-specific best practices (e.g. "a Concept should have a
prefLabel") and not S32-S35's ``skos:memberList``/``skos:member``
consistency (a real, documented gap - see ``skos_shapes.ttl``'s module
comment).

**Deliberately no ``ont_graph``/``inference="rdfs"``, unlike ``manch:``/
``salg:``'s own ``validate()``** - ``skos-ontology.ttl`` faithfully restates
the real spec's S19/S20 ``rdfs:domain``/``range`` axioms, but feeding that
ontology into an RDFS-inference validation pass would auto-entail exactly
the ``skos:Concept`` type the S19/S20 shape exists to check for, making it
tautologically vacuous - confirmed empirically while building this (see
``skos_shapes.ttl``'s own module comment for the full account). Every shape
here is written to be self-sufficient against the bare data graph instead.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from rdflib import Graph

try:
    from pyshacl import validate as _pyshacl_validate
    from pyshacl.errors import ShapeRecursionWarning
except ImportError as exc:  # pragma: no cover - exercised only when pyshacl isn't installed
    raise ImportError(
        "starlayergraph.ontology.skos_shapes requires pyshacl - install with "
        "`pip install -e '.[test]'` or `pip install pyshacl`"
    ) from exc

SKOS_SHAPES_TTL_PATH = Path(__file__).parent / "skos_shapes.ttl"
SHAPES_TURTLE = SKOS_SHAPES_TTL_PATH.read_text()


def shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the shapes above (SHACL graphs are
    mutated by pyshacl during validation, so callers get their own copy
    rather than a shared module-level instance)."""
    g = Graph()
    g.parse(data=SHAPES_TURTLE, format="turtle")
    return g


def validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` (any SKOS thesaurus - hand-authored, parsed
    from RDF/XML or Turtle, whatever) against the shapes above.

    Deliberately no ``ont_graph``/``inference`` - see this module's own
    docstring for why (RDFS domain/range entailment from
    ``skos-ontology.ttl``'s own faithfully-restated S19/S20 axioms would
    make the S19/S20 SHACL shape tautologically vacuous).

    Returns ``(conforms, results_graph, results_text)`` - the same shape
    ``pyshacl.validate`` itself returns.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        conforms, results_graph, results_text = _pyshacl_validate(
            data_graph,
            shacl_graph=shapes_graph(),
            advanced=True,
            max_validation_depth=100,
        )
    return conforms, results_graph, results_text
