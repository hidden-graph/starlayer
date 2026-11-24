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

1. ``declared_conformance_profile()`` - starlayer.shacl's own self-declaration
   (S3, "Profiles of SHACL") of which named SHACL 1.2 feature profiles it
   implements, as a small bundled RDF document
   (the starlayer.shacl resource in starontology's starlayer-profiles.ttl) using the same dx-prof
   vocabulary the spec itself uses, rather than only the prose gap matrix.
2. ``derive_conforms_to()`` - S5.7's "conforms to shapes graph" rule
   (``sh:conformsToShapesGraph``) and S5.8's "conforms to standard" rule.
   Mechanically these are ordinary SPARQL CONSTRUCT rules, but the first can
   never fire against a plain validation report graph as produced, since that
   report has no ``sh:ValidationActivity`` linking it back to
   caller-meaningful graph IRIs unless the caller opts in.
   ``StarShaclProcessor.validate()``'s own ``data_graph_iri=``/
   ``shapes_graph_resource=`` keyword arguments (see
   ``engine/report.py::annotate_provenance``) write that activity when
   supplied, and ``derive_conforms_to()`` reads the names off it, so a
   caller who already validated with those kwargs doesn't have to repeat the
   IRIs here.
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.graphs import new_graph
from starlayer.shacl.engine.report import PROCESSOR_IRI
from starlayer.shacl.engine.terms import RDF, SH, engine_view, to_engine

_SH = "http://www.w3.org/ns/shacl#"
_SH_ValidationReport = SH.ValidationReport
_SH_usedDataGraph = SH.usedDataGraph
_SH_usedShapesGraph = SH.usedShapesGraph
_SH_conformsToShapesGraph = SH.conformsToShapesGraph
_PROV_generated = ox.NamedNode("http://www.w3.org/ns/prov#generated")
_DCTERMS_conformsTo = ox.NamedNode("http://purl.org/dc/terms/conformsTo")

# starlayer.shacl's own resource inside the profiles document
# (starontology.get_conformance_profiles()); declared_conformance_profile()
# returns just that resource's triples.
_SHACL_SUBJECT = PROCESSOR_IRI

# SHACL 1.2 Profiling S5.7 (rules/conforms-to-sg.sparql in the spec repository): the names are read from the
# sh:ValidationActivity that prov:generated the report, the one form StarLayer writes.
_CONFORMS_TO_SHAPES_GRAPH_RULE = """
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
CONSTRUCT { ?dg sh:conformsToShapesGraph ?sg }
WHERE {
    ?va sh:usedDataGraph ?dg ;
        sh:usedShapesGraph ?sg ;
        prov:generated ?vr .
    ?vr sh:conforms true .
}
"""

# The S5.8 rule, extended. S5.8 itself only has the first branch below
# (a shapes graph that is directly a prof:isProfileOf a specification). The
# second branch is StarLayer's extension: a shapes graph listed as a
# role:validation resource of a prof:Profile means data that conforms to it
# conforms to that profile, and the profile's own prof:isProfileOf chain
# (zero or more steps, so the profile itself is included) carries the claim
# up to the public specification or SHACL profile.
_CONFORMS_TO_SPECIFICATION_RULE = """
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX prof: <http://www.w3.org/ns/dx/prof/>
PREFIX role: <http://www.w3.org/ns/dx/prof/role/>
PREFIX dcterms: <http://purl.org/dc/terms/>
CONSTRUCT { ?x dcterms:conformsTo ?spec }
WHERE {
    ?x sh:conformsToShapesGraph ?shapesGraph .
    {
        ?shapesGraph prof:isProfileOf ?spec .
    } UNION {
        ?profile prof:hasResource ?resource .
        ?resource prof:hasArtifact ?shapesGraph ;
                  prof:hasRole role:validation .
        ?profile prof:isProfileOf* ?spec .
    }
}
"""


def declared_conformance_profile() -> Any:
    """A fresh copy of starlayer.shacl's self-declared SHACL 1.2
    conformance statement (S3) - the starlayer.shacl resource in the
    library's one conformance file. Parses the bundled asset fresh on every
    call rather than caching - matching this project's convention
    elsewhere (see starontology/__init__.py::_file_graph) of never
    sharing one mutable graph object across callers.

    Returns:
        A fresh ``StarLayerGraph`` containing the bundled conformance statement.
    """
    from starlayer import starontology

    whole = starontology.get_conformance_profiles()
    graph = new_graph(whole)
    graph.extend(list(whole.triples((_SHACL_SUBJECT, None, None))))
    return graph


def _find_report_node(report_graph: Any) -> Any:
    for node in report_graph.subjects(RDF.type, _SH_ValidationReport):
        return node
    return None


def _bind_derived_namespaces(graph: Any, *sources: Any) -> None:
    """Give ``graph`` a deliberate namespace table: ``sh``/``prof``/``dcterms`` (every triple this module derives uses at least one
    of them), then the prefixes of ``sources`` in the order given, first bound wins."""
    for prefix, namespace in (("sh", _SH), ("prof", "http://www.w3.org/ns/dx/prof/"), ("dcterms", "http://purl.org/dc/terms/")):
        graph.prefixes[prefix] = namespace
    for source in sources:
        if source is None:
            continue
        for prefix, namespace in source.namespaces():
            graph.prefixes.setdefault(prefix, namespace)


def _iri(value: Any) -> Any:
    """An IRI given as a ``str``, a pyoxigraph ``NamedNode`` or an rdflib ``URIRef``, as a ``NamedNode``."""
    if isinstance(value, ox.NamedNode):
        return value
    if type(value) is str:
        return ox.NamedNode(value)
    return to_engine(value)


def derive_conforms_to(
    report_graph: Any,
    *,
    data_graph: Any | None = None,
    shapes_graph: Any | None = None,
    specification_graph: Any | None = None,
    conforms_only: bool = False,
) -> Any:
    """Derive ``sh:conformsToShapesGraph`` triples from a validation report, per
    SHACL 1.2 Profiling S5.7.

    Only conforming reports (``sh:conforms true``) produce a
    ``sh:conformsToShapesGraph`` triple, matching the rule's own WHERE clause - a
    non-conformant report derives nothing.

    If ``specification_graph`` is given, the S5.8 rule also runs
    once the first has fired, additionally deriving ``dcterms:conformsTo``
    triples to whatever ``shapes_graph`` is declared a profile of (the S5.8
    rule), and also - StarLayer's extension - to the ``prof:Profile`` that
    lists ``shapes_graph`` as a ``role:validation`` resource and to every
    specification or profile that profile ``prof:isProfileOf``, however
    many steps up. This is not the same relationship
    ``declared_conformance_profile()`` records (that one is *this
    library's* own conformance to named SHACL 1.2 feature profiles, a
    different resource than ``shapes_graph``) - pass a graph relating
    ``shapes_graph`` itself to whatever it profiles.

    Args:
        report_graph: A plain SHACL validation report graph (e.g.
            ``ValidationReport.report_graph``). Read, never mutated.
        data_graph: The data graph as an RDF resource - an IRI or
            IRI-like string, using whatever identity scheme the caller's
            application already uses (a dataset-catalog IRI, a
            named-graph IRI - there is no single right default).
            Optional: if the report was produced by
            ``validate(..., data_graph_iri=..., shapes_graph_resource=...)``,
            the matching ``sh:usedDataGraph`` triple is already on the
            report's ``sh:ValidationActivity`` and is read from there when
            this is omitted.
        shapes_graph: The shapes graph as an RDF resource, same
            optionality and fallback as ``data_graph`` (read from the
            report's activity ``sh:usedShapesGraph`` when omitted).
        specification_graph: A graph relating ``shapes_graph`` to what it
            profiles - either ``prof:isProfileOf`` on ``shapes_graph``
            itself, or a ``prof:Profile`` that lists it as a
            ``role:validation`` ``prof:hasResource`` artifact (e.g.
            ``starontology.get_conformance_profiles()``) - to
            additionally derive ``dcterms:conformsTo`` triples via S5.8's
            second rule (see above). Read, never mutated. ``None`` (the
            default) skips this second rule entirely.
        conforms_only: If ``True``, the returned graph contains *only* the
            ``sh:conformsToShapesGraph``/``dcterms:conformsTo`` triples
            themselves, not ``report_graph`` - useful when a caller only cares
            about the conformance claims, e.g. to merge into a dataset catalog
            entry that has no reason to reference a SHACL validation report at
            all. If ``False`` (the default), the returned graph is
            ``report_graph`` merged with whatever got newly derived - a
            self-contained, immediately printable/serializable result.

    Returns:
        A new ``StarLayerGraph``. ``report_graph``/``specification_graph``
        are read, never mutated.

    Raises:
        ValueError: If ``report_graph`` has no ``sh:ValidationReport``
            node, or if a graph identity (``data_graph``/``shapes_graph``)
            is neither supplied nor recoverable from the report.
    """
    report_graph = engine_view(report_graph, "report graph")
    if specification_graph is not None:
        specification_graph = engine_view(specification_graph, "specification graph")
    report_node = _find_report_node(report_graph)
    if report_node is None:
        raise ValueError("report_graph has no sh:ValidationReport node - nothing to derive sh:conformsToShapesGraph from.")

    activities = list(report_graph.subjects(_PROV_generated, report_node))
    if data_graph is None:
        data_graph = next((o for va in activities for o in report_graph.objects(va, _SH_usedDataGraph)), None)
        if data_graph is None:
            raise ValueError(
                "data_graph not supplied and the report's sh:ValidationActivity has no sh:usedDataGraph - "
                "pass data_graph= explicitly, or re-run validate(..., data_graph_iri=...)."
            )
    if shapes_graph is None:
        shapes_graph = next((o for va in activities for o in report_graph.objects(va, _SH_usedShapesGraph)), None)
        if shapes_graph is None:
            raise ValueError(
                "shapes_graph not supplied and the report's sh:ValidationActivity has no sh:usedShapesGraph - "
                "pass shapes_graph= explicitly, or re-run validate(..., shapes_graph_resource=...)."
            )

    data_graph_iri = _iri(data_graph)
    shapes_graph_iri = _iri(shapes_graph)

    # scratch is pure internal working state, never returned or exposed to the caller
    scratch = new_graph()
    scratch.extend(list(report_graph.triples((None, None, None))))
    activity = ox.BlankNode()  # the names, given or read, as the activity the rule reads
    scratch.add((activity, _PROV_generated, report_node))
    scratch.add((activity, _SH_usedDataGraph, data_graph_iri))
    scratch.add((activity, _SH_usedShapesGraph, shapes_graph_iri))
    if specification_graph is not None:
        scratch.extend(list(specification_graph.triples((None, None, None))))

    new_triples: list[tuple[Any, Any, Any]] = [tuple(t) for t in scratch.query(_CONFORMS_TO_SHAPES_GRAPH_RULE)]

    if specification_graph is not None:
        scratch.extend(new_triples)
        new_triples.extend(tuple(t) for t in scratch.query(_CONFORMS_TO_SPECIFICATION_RULE))

    # conforms_only=True: ONLY the derived claims. The default merges them into a fresh copy of report_graph (never mutating
    # the caller's own object).
    result = new_graph()
    if conforms_only:
        result.extend([t for t in new_triples if t[1] in (_SH_conformsToShapesGraph, _DCTERMS_conformsTo)])
    else:
        result.extend(list(report_graph.triples((None, None, None))))
        result.extend(new_triples)

    # specification_graph first (the caller's own most deliberately-chosen vocabulary), then report_graph
    _bind_derived_namespaces(result, specification_graph, report_graph)

    return result
