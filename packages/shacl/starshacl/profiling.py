"""Support for SHACL 1.2 Profiling (https://www.w3.org/TR/shacl12-profiling/).

docs/shacl12-gap-matrix.md's Profiling row and "Not Covered / Deferred"
table investigated this document to the same depth as the other five
SHACL 1.2 documents and concluded no *mandatory* validator runtime
behavior is missing: S2's packaging conventions (sh:ShapesGraph/
sh:DataGraph grouping, rdfs:isDefinedBy/rdfs:member, owl:imports) are
SHOULD-level organizational metadata with no defined effect on
validation, and S3/S4 (declaring/using SHACL feature profiles) describe
how other specs and tooling use SHACL, not processor behavior.

That still leaves two genuinely useful, spec-shaped things an
implementation *can* do that this module provides:

1. ``declared_conformance_profile()`` - starshacl's own self-declaration
   (S3, "Profiles of SHACL") of which named SHACL 1.2 feature profiles it
   implements, as a small bundled RDF document
   (assets/shacl12-conformance-profile.ttl) using the same dx-prof
   vocabulary the spec itself uses, rather than only the prose gap matrix.
2. ``derive_conforms_to()`` - S5.5's sh:conformsTo inference rule. This is
   MAY-level (S2.8) and mechanically just an ordinary SPARQL CONSTRUCT
   rule - starshacl's own sh:SPARQLRule engine could already execute a
   rule of this exact shape - but it can never fire against a plain
   validation report graph as produced, since that report has no
   sh:usedDataGraph/sh:usedShapesGraph/sh:validationReport identity
   linking it back to caller-meaningful graph IRIs unless the caller opts
   in. ``StarShaclValidator.validate()``'s own ``data_graph_iri=``/
   ``shapes_graph_iri=`` keyword arguments (SHACL 1.2 Core S6.7.1.5-6.7.1.6,
   see ``validator.py::_annotate_used_graphs_and_configuration``) already
   add the ``sh:usedDataGraph``/``sh:usedShapesGraph`` half of that identity
   when supplied - ``derive_conforms_to()`` reads those straight off the
   report when present, so a caller who already validated with those
   kwargs doesn't have to repeat the IRIs here. The one link neither
   mechanism supplies on its own is ``sh:validationReport`` (a data-graph
   *resource* pointing at its own report) - genuinely new identity this
   function adds, since nothing else in the pipeline has a reason to.
"""

from __future__ import annotations

import os
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

_SH = "http://www.w3.org/ns/shacl#"
_SH_ValidationReport = URIRef(_SH + "ValidationReport")
_SH_validationReport = URIRef(_SH + "validationReport")
_SH_usedDataGraph = URIRef(_SH + "usedDataGraph")
_SH_usedShapesGraph = URIRef(_SH + "usedShapesGraph")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_CONFORMANCE_PROFILE_PATH = os.path.join(_ASSETS_DIR, "shacl12-conformance-profile.ttl")

# Verbatim from SHACL 1.2 Profiling S5.5 (https://www.w3.org/TR/shacl12-profiling/),
# modulo prefix declarations rdflib's parser requires inline.
_CONFORMS_TO_SHAPES_GRAPH_RULE = """
PREFIX sh: <http://www.w3.org/ns/shacl#>
CONSTRUCT { ?x sh:conformsTo ?z }
WHERE {
    ?x sh:validationReport ?y .
    ?y sh:usedShapesGraph ?z ;
       sh:conforms true .
}
"""

_CONFORMS_TO_SPECIFICATION_RULE = """
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX prof: <http://www.w3.org/ns/dx/prof/>
PREFIX dcterms: <http://purl.org/dc/terms/>
CONSTRUCT { ?x dcterms:conformsTo ?spec }
WHERE {
    ?x sh:conformsTo ?shapesGraph .
    ?shapesGraph prof:isProfileOf ?spec .
}
"""


def declared_conformance_profile() -> Graph:
    """A fresh copy of starshacl's bundled self-declared SHACL 1.2
    conformance statement (S3). Parses the bundled asset fresh on every
    call rather than caching - matching this project's convention
    elsewhere (see meta_shapes.py::build_meta_shapes_graph) of never
    sharing one mutable graph object across callers.
    """
    graph = Graph()
    graph.parse(_CONFORMANCE_PROFILE_PATH, format="turtle")
    return graph


def _find_report_node(report_graph: Any) -> Any:
    for node in report_graph.subjects(RDF.type, _SH_ValidationReport):
        return node
    return None


def derive_conforms_to(
    report_graph: Any,
    *,
    data_graph: str | URIRef | None = None,
    shapes_graph: str | URIRef | None = None,
    specification_graph: Any | None = None,
) -> Graph:
    """Derive ``sh:conformsTo`` triples from a validation report, per
    SHACL 1.2 Profiling S5.5.

    ``report_graph`` is a plain SHACL validation report graph (e.g.
    ``ValidationResult.report_graph``). ``data_graph``/``shapes_graph``
    name the data/shapes graphs as RDF resources - IRIs or IRI-like
    strings, using whatever identity scheme the caller's application
    already uses (a dataset-catalog IRI, a named-graph IRI - there is no
    single right default). Both are optional here: if the report was
    produced by ``validate(..., data_graph_iri=..., shapes_graph_iri=...)``,
    the matching ``sh:usedDataGraph``/``sh:usedShapesGraph`` triples are
    already on the report and are read from there when the corresponding
    argument is omitted - only pass them explicitly for a report that
    wasn't given that identity at validation time. Raises ``ValueError``
    if ``report_graph`` has no ``sh:ValidationReport`` node, or if a graph
    IRI is neither supplied nor recoverable from the report.

    Only conforming reports (``sh:conforms true``) produce a
    ``sh:conformsTo`` triple, matching the rule's own WHERE clause - a
    non-conformant report derives nothing.

    If ``specification_graph`` is given - any graph asserting
    ``prof:isProfileOf`` on ``shapes_graph`` itself (e.g. a
    ``prof:Profile`` declaration for the shapes graph the caller
    validated against) - the second S5.5 rule also runs once the first
    has fired, additionally deriving ``dcterms:conformsTo`` triples to
    whatever specification(s) ``shapes_graph`` is declared a profile of.
    Not the same relationship ``declared_conformance_profile()`` records
    (that one is *this library's* own conformance to named SHACL 1.2
    feature profiles, a different resource than ``shapes_graph``) - pass
    a graph relating ``shapes_graph`` itself to whatever it profiles.

    Returns a new graph containing only the newly derived triples -
    ``report_graph``/``specification_graph`` are read, never mutated.
    """
    report_node = _find_report_node(report_graph)
    if report_node is None:
        raise ValueError("report_graph has no sh:ValidationReport node - nothing to derive sh:conformsTo from.")

    if data_graph is None:
        data_graph = next(report_graph.objects(report_node, _SH_usedDataGraph), None)
        if data_graph is None:
            raise ValueError(
                "data_graph not supplied and report_graph has no sh:usedDataGraph - "
                "pass data_graph= explicitly, or re-run validate(..., data_graph_iri=...)."
            )
    if shapes_graph is None:
        shapes_graph = next(report_graph.objects(report_node, _SH_usedShapesGraph), None)
        if shapes_graph is None:
            raise ValueError(
                "shapes_graph not supplied and report_graph has no sh:usedShapesGraph - "
                "pass shapes_graph= explicitly, or re-run validate(..., shapes_graph_iri=...)."
            )

    data_graph_iri = data_graph if isinstance(data_graph, URIRef) else URIRef(str(data_graph))
    shapes_graph_iri = shapes_graph if isinstance(shapes_graph, URIRef) else URIRef(str(shapes_graph))

    scratch = Graph()
    scratch += report_graph
    scratch.add((data_graph_iri, _SH_validationReport, report_node))
    scratch.add((report_node, _SH_usedShapesGraph, shapes_graph_iri))
    if specification_graph is not None:
        scratch += specification_graph

    derived = Graph()
    for triple in scratch.query(_CONFORMS_TO_SHAPES_GRAPH_RULE):
        derived.add(triple)

    if specification_graph is not None:
        scratch += derived
        for triple in scratch.query(_CONFORMS_TO_SPECIFICATION_RULE):
            derived.add(triple)

    return derived
