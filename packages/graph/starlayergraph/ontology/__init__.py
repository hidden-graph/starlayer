"""An RDFS ontology (classes/subclasses, properties with no domain/range
where they're reused across heterogeneous node types) for the ``manch:``
vocabulary - an RDF representation of an OWL 2 Manchester Syntax document's
own internal AST (frames, clauses, class expressions), mirroring the sibling
``starsparql`` package's ``salg:`` vocabulary for SPARQL query algebra (see
that package's ``ontology/__init__.py`` for the full design rationale this
one deliberately follows - same reasoning, same discipline, not re-derived).

The ontology itself lives in ``manchester-ast-ontology.ttl``, next to this
file - a plain, standalone Turtle file, not a Python string, so it's directly
usable by any RDF tool without going through this module at all. This module
is just a thin loader (``ontology_graph()``); unlike ``salg:``'s 63
expression builtins, Manchester's own vocabulary (~30 concrete classes) is
small enough to hand-author entirely, with no generated section.

**Fidelity scope, confirmed with the user before building this**: this
encodes the parser's *existing* internal AST as-is (``And``/``Or``/``Not``/
``Some``/``Only``/etc., already built as transient tuples then discarded by
``parsers/manchester_parser.py``) - not a new, non-desugaring surface
tokenizer pass. `onlysome` is already desugared into ``And(Some, Only)`` at
parse time, `that` into `and`, and `SuperClassOf:`/`SubClassOf:` spelling
isn't tracked past parse time - none of that is recoverable here, matching
the same fidelity bar `salg:` itself has for SPARQL (it doesn't preserve
original whitespace/comments/every algebra-optimization choice either - it
encodes the algebra tree, one step removed from raw text, same as this AST is
one step removed from raw Manchester text).

**Why most properties have no ``rdfs:domain``/``rdfs:range`` - the same two
reasons ``salg:`` documents, re-confirmed for this vocabulary rather than
assumed to carry over automatically:**

1. *Heterogeneous reuse.* ``manch:value``/``manch:annotations`` (on
   ``manch:ClauseItem``) are reused across every clause-item type regardless
   of what kind of value it holds (a class expression, a property expression,
   a data range, a bare name) - the same "declaring one domain/range would be
   actively wrong, not just imprecise" reasoning applies.
2. *Entailment defeating dispatch shapes.* Any property feeding into a
   ``sh:class``-checked position (``manch:operands`` items feeding
   ``ClassExpressionShape``, etc.) must not have that class declared as its
   ``rdfs:range``, for the identical reason ``salg:arg``/``salg:expr`` don't:
   RDFS entailment runs before SHACL validation and would pre-satisfy the very
   check meant to catch a malformed value.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

ONTOLOGY_TTL_PATH = Path(__file__).parent / "manchester-ast-ontology.ttl"
SKOS_ONTOLOGY_TTL_PATH = Path(__file__).parent / "skos-ontology.ttl"


def ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the RDFS ontology in
    ``manchester-ast-ontology.ttl``."""
    g = Graph()
    g.parse(source=str(ONTOLOGY_TTL_PATH), format="turtle")
    return g


def skos_ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the OWL/RDFS ontology in
    ``skos-ontology.ttl`` - a direct restatement of the W3C SKOS Reference's
    own formal axioms over the real ``skos:`` namespace (unlike the
    Manchester-specific ``ontology_graph()`` above, this ontology is *about*
    an existing external vocabulary, not one this project invented - see
    that file's own module docstring/comments for the full rationale and
    per-axiom spec citations)."""
    g = Graph()
    g.parse(source=str(SKOS_ONTOLOGY_TTL_PATH), format="turtle")
    return g


# Re-exported so `starlayergraph.ontology.list_shacl_libraries()`/
# `get_shacl_library()` work without a caller needing to know the registry
# lives in its own submodule - see registry.py's own docstring for the full
# design (why this lives here rather than in starshacl/starsparql, why
# every loader is lazy, and what's deliberately not yet registered).
from starlayergraph.ontology.registry import (  # noqa: E402
    ShaclLibrary,
    get_shacl_library,
    list_shacl_libraries,
)
