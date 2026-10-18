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
2. ``derive_conforms_to()`` - S5.5's sh:conformsTo inference rule. This is
   MAY-level (S2.8) and mechanically just an ordinary SPARQL CONSTRUCT
   rule - starlayer.shacl's own sh:SPARQLRule engine could already execute a
   rule of this exact shape - but it can never fire against a plain
   validation report graph as produced, since that report has no
   sh:usedDataGraph/sh:usedShapesGraph/sh:validationReport identity
   linking it back to caller-meaningful graph IRIs unless the caller opts
   in. ``StarShaclSchema.validate()``'s own ``data_graph_iri=``/
   ``shapes_graph_resource=`` keyword arguments (SHACL 1.2 Core S6.7.1.5-6.7.1.6,
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

from typing import TYPE_CHECKING, Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

if TYPE_CHECKING:
    from starlayer.graph import StarLayerGraph

_SH = "http://www.w3.org/ns/shacl#"
_SH_ValidationReport = URIRef(_SH + "ValidationReport")
_SH_validationReport = URIRef(_SH + "validationReport")
_SH_usedDataGraph = URIRef(_SH + "usedDataGraph")
_SH_usedShapesGraph = URIRef(_SH + "usedShapesGraph")
_SH_conformsTo = URIRef(_SH + "conformsTo")
_DCTERMS_conformsTo = URIRef("http://purl.org/dc/terms/conformsTo")

# starlayer.shacl's own resource inside the profiles document
# (starontology.get_conformance_profiles()); declared_conformance_profile()
# returns just that resource's triples.
_SHACL_SUBJECT = URIRef(
    "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/shacl"
)

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

# The second S5.5 rule, extended. S5.5 itself only has the first branch below
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
    ?x sh:conformsTo ?shapesGraph .
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


def declared_conformance_profile() -> StarLayerGraph:
    """A fresh copy of starlayer.shacl's self-declared SHACL 1.2
    conformance statement (S3) - the starlayer.shacl resource in the
    library's one conformance file. Parses the bundled asset fresh on every
    call rather than caching - matching this project's convention
    elsewhere (see starontology/__init__.py::_file_graph) of never
    sharing one mutable graph object across callers.

    Returns a ``StarLayerGraph``, not a plain ``rdflib.Graph`` - this is a
    public, caller-facing result meant to be inspected/serialized/merged,
    not internal plumbing fed straight to pySHACL.

    Returns:
        A fresh StarLayerGraph containing the bundled conformance
        statement.
    """
    from starlayer import starontology
    from starlayer.graph import (
        StarLayerGraph,  # lazy: avoids a circular-import deadlock
    )

    whole = starontology.get_conformance_profiles()
    graph = StarLayerGraph()
    for prefix, namespace in whole.namespaces():
        graph.bind(prefix, namespace)
    for triple in whole.triples((_SHACL_SUBJECT, None, None)):
        graph.add(triple)
    return graph


def _find_report_node(report_graph: Any) -> Any:
    for node in report_graph.subjects(RDF.type, _SH_ValidationReport):
        return node
    return None


def _bind_derived_namespaces(graph: Any, *sources: Any) -> None:
    """Give ``graph`` a clean, deliberate namespace table instead of
    whatever ``StarLayerGraph()``'s own bare-construction default happens
    to be - same pattern (and same motivation) as ``validator.py``'s own
    ``_rebuild_report_namespaces()``, just scoped to what's actually
    available in this module (no ``data_graph``/``shacl_graph``/
    ``ont_graph`` graph objects here, only IRIs - ``report_graph``/
    ``specification_graph`` are the only real graphs this function ever
    sees).

    Args:
        graph: The graph to bind namespaces onto, in place.
        *sources: Graphs whose own bound prefixes are layered on top of
            ``sh``/``prof``/``dcterms`` (bound unconditionally first,
            since every triple this module derives uses at least one of
            them), in the order given, first-bound-wins.
    """
    from rdflib import Namespace
    from rdflib.namespace import NamespaceManager

    nm = NamespaceManager(graph, bind_namespaces="core")
    nm.bind("sh", Namespace(_SH))
    nm.bind("prof", Namespace("http://www.w3.org/ns/dx/prof/"))
    nm.bind("dcterms", Namespace("http://purl.org/dc/terms/"))
    graph.namespace_manager = nm

    for source in sources:
        if source is None:
            continue
        source_nm = getattr(source, "namespace_manager", None)
        if source_nm is None:
            continue
        for prefix, namespace in source_nm.namespaces():
            if nm.store.namespace(prefix) is None:
                nm.bind(prefix, namespace)


def derive_conforms_to(
    report_graph: Any,
    *,
    data_graph: str | URIRef | None = None,
    shapes_graph: str | URIRef | None = None,
    specification_graph: Any | None = None,
    conforms_only: bool = False,
) -> StarLayerGraph:
    """Derive ``sh:conformsTo`` triples from a validation report, per
    SHACL 1.2 Profiling S5.5.

    Only conforming reports (``sh:conforms true``) produce a
    ``sh:conformsTo`` triple, matching the rule's own WHERE clause - a
    non-conformant report derives nothing.

    If ``specification_graph`` is given, the second S5.5 rule also runs
    once the first has fired, additionally deriving ``dcterms:conformsTo``
    triples to whatever ``shapes_graph`` is declared a profile of (the S5.5
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
            ``ValidationResult.report_graph``). Read, never mutated.
        data_graph: The data graph as an RDF resource - an IRI or
            IRI-like string, using whatever identity scheme the caller's
            application already uses (a dataset-catalog IRI, a
            named-graph IRI - there is no single right default).
            Optional: if the report was produced by
            ``validate(..., data_graph_iri=..., shapes_graph_resource=...)``,
            the matching ``sh:usedDataGraph`` triple is already on the
            report and is read from there when this is omitted.
        shapes_graph: The shapes graph as an RDF resource, same
            optionality and fallback as ``data_graph`` (read from the
            report's own ``sh:usedShapesGraph`` when omitted).
        specification_graph: A graph relating ``shapes_graph`` to what it
            profiles - either ``prof:isProfileOf`` on ``shapes_graph``
            itself, or a ``prof:Profile`` that lists it as a
            ``role:validation`` ``prof:hasResource`` artifact (e.g.
            ``starontology.get_conformance_profiles()``) - to
            additionally derive ``dcterms:conformsTo`` triples via S5.5's
            second rule (see above). Read, never mutated. ``None`` (the
            default) skips this second rule entirely.
        conforms_only: If ``True``, the returned graph contains *only* the
            ``sh:conformsTo``/``dcterms:conformsTo`` triples themselves -
            not ``report_graph``, and not even the ``sh:validationReport``
            link this function otherwise adds (that link exists to
            justify the conformance claim with a path back to the report,
            which ``conforms_only`` says isn't wanted) - useful when a
            caller only cares about the conformance claims themselves,
            e.g. to merge into a dataset catalog entry that has no reason
            to reference a SHACL validation report at all. If ``False``
            (the default), the returned graph is ``report_graph`` merged
            with whatever got newly derived - a self-contained,
            immediately printable/serializable result, where the added
            ``sh:validationReport`` link resolves to a real,
            fully-described node rather than a dangling blank-node
            reference.

    Returns:
        A new ``StarLayerGraph``. ``report_graph``/``specification_graph``
        are read, never mutated.

    Raises:
        ValueError: If ``report_graph`` has no ``sh:ValidationReport``
            node, or if a graph identity (``data_graph``/``shapes_graph``)
            is neither supplied nor recoverable from the report.
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
                "pass shapes_graph= explicitly, or re-run validate(..., shapes_graph_resource=...)."
            )

    data_graph_iri = data_graph if isinstance(data_graph, URIRef) else URIRef(str(data_graph))
    shapes_graph_iri = shapes_graph if isinstance(shapes_graph, URIRef) else URIRef(str(shapes_graph))

    # scratch is pure internal working state, never returned or exposed
    # to the caller - a plain Graph is fine here on purpose; only
    # `derived` (the actual return value) needs to be a StarLayerGraph.
    scratch = Graph()
    scratch += report_graph
    scratch.add((data_graph_iri, _SH_validationReport, report_node))
    scratch.add((report_node, _SH_usedShapesGraph, shapes_graph_iri))
    if specification_graph is not None:
        scratch += specification_graph

    from starlayer.graph import (
        StarLayerGraph,  # lazy: avoids a circular-import deadlock
    )

    new_triples = StarLayerGraph()
    # The data-graph-resource -> report link itself is "genuinely new
    # identity this function adds" (see module docstring) - without it,
    # the sh:conformsTo triple the rule below derives would have no RDF
    # path back to the report that justified it. Added to new_triples
    # (not just scratch), so it actually survives into the result rather
    # than only existing long enough for the query below to fire.
    new_triples.add((data_graph_iri, _SH_validationReport, report_node))
    for triple in scratch.query(_CONFORMS_TO_SHAPES_GRAPH_RULE):
        new_triples.add(triple)

    if specification_graph is not None:
        scratch += new_triples
        for triple in scratch.query(_CONFORMS_TO_SPECIFICATION_RULE):
            new_triples.add(triple)

    # conforms_only=True: ONLY the sh:conformsTo/dcterms:conformsTo
    # triples themselves - not report_graph, and not even the
    # sh:validationReport link new_triples otherwise carries (that link
    # exists to justify the claim with a path back to the report, which
    # conforms_only says isn't wanted). The default merges the full
    # new_triples - link included - into a fresh copy of report_graph
    # (never mutating the caller's own object) - self-contained, so that
    # link resolves to a real node instead of a dangling blank-node
    # reference when printed/serialized on its own.
    if conforms_only:
        result = StarLayerGraph()
        for triple in new_triples:
            if triple[1] in (_SH_conformsTo, _DCTERMS_conformsTo):
                result.add(triple)
    else:
        result = StarLayerGraph()
        result += report_graph
        result += new_triples

    # specification_graph first (the caller's own most deliberately-
    # chosen vocabulary - e.g. a business-policy namespace), then
    # report_graph (already reasonably populated if it came from
    # validate(), via that function's own forwarding) - same priority
    # order validator.py's _rebuild_report_namespaces() already settled
    # on for the identical "which source wins a prefix collision" choice.
    _bind_derived_namespaces(result, specification_graph, report_graph)

    return result
