"""starontology.skos

SHACL validation of a SKOS graph against the W3C SKOS Reference's own
numbered "Documented Consistency and Integrity Conditions"
(https://www.w3.org/TR/skos-reference/). Moved here (2026-10-03) from
starlayer.ontology.skos_shapes, for the same reason manch:'s manchester_validate()
lives in starontology.manchester - validating a vocabulary against its own
shapes is an ontology-management concern, not a starlayer.graph/.sparql one.

Unlike ``manch:``/``srl:``, SKOS needs no encode/decode/tree layer at all -
a SKOS thesaurus is already plain RDF the moment it's authored. So this
module is thinner than either of those: one entry point, not four or seven.

One entry point:

- ``skos_validate(data_graph) -> (conforms, report_graph, report_text)`` -
  structural + the spec's own numbered integrity conditions (S9, S13, S14,
  S19/S20, S27, S37, S46), ``skos:memberList``/``skos:member`` consistency
  (the spec's own §9.4 prose expectation, not a numbered condition), plus a
  small set of non-normative best-practice recommendations (e.g. "a Concept
  should have a prefLabel") - the latter are ``sh:severity sh:Info``, so
  they never flip ``conforms`` (``allow_infos=True`` below) - see
  ``skos_shapes.ttl``'s own per-shape comments for the full list.

No public ``ontology_graph()``/``shapes_graph()`` here (same decision as
``starontology.manchester``/``starlayer.sparql.srl``) - get those two
graphs from ``starontology`` directly instead: ``get_ontology_graph(
"skos_owl")`` / ``get_ontology_graph("skos_shacl")``.

**Deliberately no ``ont_graph``/``inference=ENTAILMENT.RDFS`` in
``skos_validate()``, unlike ``manch:``/``salg:``/``srl:``'s own** -
``skos-ontology.ttl``
faithfully restates the real spec's S19/S20 ``rdfs:domain``/``range``
axioms, but feeding that ontology into an RDFS-inference validation pass
would auto-entail exactly the ``skos:Concept`` type the S19/S20 shape
exists to check for, making it tautologically vacuous - confirmed
empirically while building this (see ``skos_shapes.ttl``'s own module
comment for the full account). Every shape there is written to be
self-sufficient against the bare data graph instead - this is also why
``skos_validate()`` here needs no combining-with-another-vocabulary's-shapes
logic the way ``srl.srl_validate()`` does for ``srl:``+``salg:``.
"""

from __future__ import annotations

import warnings

from rdflib import Graph

from . import get_ontology_graph


def skos_validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` (any SKOS thesaurus - hand-authored, parsed
    from RDF/XML or Turtle, whatever) against the shapes in
    ``skos_shapes.ttl``.

    Deliberately no ``ont_graph``/``inference`` - see this module's own
    docstring for why (RDFS domain/range entailment from
    ``skos-ontology.ttl``'s own faithfully-restated S19/S20 axioms would
    make the S19/S20 SHACL shape tautologically vacuous).

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` -
    this validates a caller-supplied ``data_graph`` that may be genuine
    RDF 1.2 content, which only ``starlayer.shacl`` understands correctly.

    Returns ``(conforms, results_graph, results_text)``, unpacked from
    ``starlayer.shacl``'s own ``ValidationResult``.

    ``allow_infos=True`` is passed through unconditionally - without it,
    pyshacl's own ``conforms`` computation doesn't distinguish severity
    levels at all (confirmed empirically: an ``sh:Info``-severity result
    still flips ``conforms`` to ``False`` by default). Without this, the
    best-practice shapes in ``skos_shapes.ttl`` (``sh:severity sh:Info``)
    would make an otherwise entirely valid thesaurus that merely skips a
    recommendation report ``conforms == False`` - defeating the entire
    point of using ``sh:Info`` instead of the default ``sh:Violation``.
    """
    from pyshacl.errors import ShapeRecursionWarning

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starlayer.shacl.validate(
            data_graph,
            shacl_graph=get_ontology_graph("skos_shacl"),
            advanced=True,
            max_validation_depth=100,
            allow_infos=True,
        )
    return result.conforms, result.report_graph, result.report_text
