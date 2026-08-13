"""An RDFS ontology (classes/subclasses, properties/subproperties,
domain/range) for the ``salg:`` vocabulary. Not just documentation:
``shapes.py``'s ``validate()`` actually loads this as an ``ont_graph`` and
runs pyshacl with ``inference="rdfs"`` on — real RDFS reasoning over the
data graph before validating it, which is what lets ``GraphPatternShape``/
``ExpressionShape``/``SubSelectShape`` be a single ``sh:class`` check
against an abstract superclass instead of enumerating every concrete
operator/builtin by name. See ``GraphPatternShape``'s own comment in
``shapes.py`` for the full story of why that dispatch mechanism needed
fixing in the first place (a real, previously-undetected gap it caused),
and ``validate()``'s own docstring for how reasoning plugs into it.

The ontology itself lives in ``salg-ontology.ttl``, next to this file — a
plain, standalone Turtle file, not a Python string, so it's directly usable
by any RDF tool without going through this module at all. This module is
just a thin loader (``ontology_graph()``) plus the generator
(``_generate_expression_class_turtle()``) used to produce that file's
generated section — see the comment inside ``salg-ontology.ttl`` itself for
how to regenerate it if ``expr_families._EXPR_NODE_FAMILY`` changes.

Scope mostly matches ``shapes.py``'s own coverage — Phase 1 core
graph-pattern operators, VALUES/subqueries, triple terms, and all 63
expression builtins — not the wider vocabulary ``to_rdf.py`` can technically
encode but nothing validates yet (property paths, aggregates, Update). The
one deliberate exception: ``salg:Query``'s four form-specific subclasses
(``SelectQuery``/``ConstructQuery``/``AskQuery``/``DescribeQuery``) are all
declared here — a class only needs a place in this hierarchy to be findable
via ``?q a salg:Query`` and RDFS subclass reasoning, not a corresponding
SHACL shape — even though only ``SelectQuery`` has one
(``SelectQueryShape``); the other three are documentation/query-by-type
only until their own shapes are written. The 63 expression-builtin subclass
declarations are *generated* from ``expr_families._EXPR_NODE_FAMILY`` (the
exact same table ``shapes.py`` uses to generate its own per-builtin shapes)
rather than hand-duplicated, so the two files can't silently drift apart —
same discipline used throughout this project's SHACL work.

**A note on ``rdfs:domain``/``rdfs:range`` and why most properties have
neither — two distinct, both real, reasons, both found by actually
running reasoning against `validate()`, not by inspection.**

1. *Heterogeneous reuse.* Several ``salg:`` properties (``salg:p``,
   ``salg:expr``, ``salg:subject``/``object``, ``salg:PV``, ``salg:var``,
   ``salg:flags``, ...) are, by this project's own generic-mirror design
   (see ``vocab.py``), reused across structurally unrelated node types
   with genuinely different value types (or, for ``PV``/``var``/
   ``flags``, a small fixed handful of otherwise-unrelated classes
   sharing no other superclass) depending on which node uses them.
   Declaring a single ``rdfs:domain``/``rdfs:range`` for those — or,
   worse, declaring *multiple* ``rdfs:domain`` triples on one property
   hoping it reads as "any of these" — is actively wrong, not just
   imprecise: RDFS domain entailment fires once per ``rdfs:domain``
   triple independently (not as a union), so two domain declarations on
   one property make every use of it get typed as *both* classes
   *simultaneously*. Confirmed as a real bug the moment reasoning was
   turned on (an ``Extend`` node falsely entailed ``rdf:type
   salg:Binding`` too, since ``salg:var`` had ``rdfs:domain`` declared
   for both).

2. *Entailment defeating the very validation it's meant to assist.* Any
   property whose value (for range) or subject (for domain) is
   *also independently checked* elsewhere via `sh:class`/`sh:node`
   against that same class (or any of its subclasses, since subclass
   entailment always propagates upward) must not have that
   domain/range declared — because RDFS entailment runs *before* SHACL
   validation, it will pre-emptively add the "correct" type to *any*
   value regardless of what it actually is, silently making the SHACL
   check pass unconditionally. Confirmed as a real, reproducible bug via
   a negative test that stopped correctly failing the moment
   ``salg:p1``/``salg:p2`` were given ``rdfs:range salg:GraphPattern``:
   a deliberately-malformed value with no legitimate operator type at
   all was auto-entailed ``salg:GraphPattern`` simply for *being* the
   object of a ``salg:p1`` triple, which is exactly what
   ``GraphPatternShape``'s own ``sh:class salg:GraphPattern`` check
   exists to catch. This applies to *every* property feeding into an
   ``sh:class``-checked expression/pattern position (``salg:arg``/
   ``arg1``/``arg2``/``arg3``, ``salg:expr``, ``salg:op``, ``salg:other``,
   ``salg:p1``/``p2``, and several more), not just those two — see each
   property's own comment in ``salg-ontology.ttl`` for the specific
   reasoning. ``salg:triples``' ``rdfs:range rdf:List`` is a safe
   exception: nothing validates ``.triples`` via type-based ``sh:class``
   dispatch (``TriplePatternListShape`` walks the list structurally via
   ``sh:sparql``, never checking ``rdf:type`` at all), so there's no
   check for range entailment to defeat.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from .expr_families import _EXPR_NODE_FAMILY

ONTOLOGY_TTL_PATH = Path(__file__).parent / "salg-ontology.ttl"


def _generate_expression_class_turtle() -> str:
    """The 63 ``rdfs:subClassOf`` declarations linking each real expression
    builtin class (``salg:Builtin_STR``, ...) to its family's intermediate
    class (``salg:OneArgExpression``, ...) - generated from
    ``expr_families._EXPR_NODE_FAMILY`` (the exact table ``shapes.py`` itself
    generates its per-builtin shapes from) rather than hand-listed. Used to
    (re)produce the generated section of ``salg-ontology.ttl`` - not called
    by ``ontology_graph()`` itself, which just loads that file directly.
    """
    declarations = []
    for name, family in _EXPR_NODE_FAMILY.items():
        # RelationalExpression is the one family whose sole member shares
        # the family's own name - it's declared directly in the hand-written
        # part of salg-ontology.ttl as a plain salg:Expression subclass, no
        # intermediate wrapper.
        if family == "Relational":
            continue
        declarations.append(f"salg:{name} rdfs:subClassOf salg:{family}Expression .")
    return "\n".join(declarations) + "\n"


def ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the RDFS ontology in ``salg-ontology.ttl``."""
    g = Graph()
    g.parse(source=str(ONTOLOGY_TTL_PATH), format="turtle")
    return g
