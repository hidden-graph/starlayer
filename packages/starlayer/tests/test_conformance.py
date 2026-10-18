"""starlayer.conformance.declared_conformance() - a multi-resource,
SHACL-1.2-Profiling-S3-style self-declaration: one graph with three real
resources (starlayer.shacl, starlayer.graph, starlayer.sparql), each
asserting dcterms:conformsTo only the spec documents specific to what
that subpackage actually implements - not one flattened "whole library"
node (see this module's own CLAUDE.md entry for why that design was
chosen over the original flat one). A minority of exclusions also get an
explicit conformance:doesNotConformTo triple (project-minted, no standard
predicate exists) rather than only prose - see this module's own
docstring for exactly which two cases qualify and why the rest don't."""

from rdflib import URIRef
from rdflib.namespace import RDFS
from starlayer import conformance

DCTERMS = conformance.DCTERMS

_SHACL_SUBJECT = conformance.SHACL_SUBJECT

_EXPECTED_SHACL_CLAIMS = {
    URIRef("https://www.w3.org/TR/shacl12-ui"),
    URIRef("http://www.w3.org/ns/shacl/profile/core"),
    URIRef("http://www.w3.org/ns/shacl/profile/sparql"),
    URIRef("http://www.w3.org/ns/shacl/profile/node-expr"),
    URIRef("http://www.w3.org/ns/shacl/profile/rules"),
    URIRef("http://www.w3.org/ns/shacl/profile/profiling"),
}
_EXPECTED_RDF12_CORE = {
    URIRef(f"https://www.w3.org/TR/{name}")
    for name in ("rdf12-concepts", "rdf12-schema", "rdf12-turtle", "rdf12-n-triples", "rdf12-xml")
}
_EXPECTED_SPARQL12 = {URIRef(f"https://www.w3.org/TR/{name}") for name in ("sparql12-query", "sparql12-update")}
_EXPECTED_GRAPH_EXTRA = {URIRef(f"https://www.w3.org/TR/{name}") for name in ("rdf-canon", "sparql12-protocol")}
_EXPECTED_SPARQL_EXTRA = {URIRef("https://www.w3.org/TR/sparql12-rl")}
_EXPECTED_ENTAILMENT_REGIMES = {
    URIRef("http://www.w3.org/ns/entailment/RDF"),
    URIRef("http://www.w3.org/ns/entailment/RDFS"),
    URIRef("http://www.w3.org/ns/entailment/OWL-RDF-Based"),
    URIRef("http://www.w3.org/ns/entailment/OWL-Direct"),
}
_EXPECTED_GRAPH = _EXPECTED_RDF12_CORE | _EXPECTED_GRAPH_EXTRA | _EXPECTED_ENTAILMENT_REGIMES
_EXPECTED_SPARQL = _EXPECTED_SPARQL12 | _EXPECTED_SPARQL_EXTRA


def test_shacl_resource_claims_the_five_profiles_and_the_ui_specification() -> None:
    graph = conformance.declared_conformance()
    claimed = set(graph.objects(_SHACL_SUBJECT, DCTERMS.conformsTo))
    assert claimed == _EXPECTED_SHACL_CLAIMS


def test_graph_resource_has_every_expected_document_and_regime() -> None:
    graph = conformance.declared_conformance()
    claimed = set(graph.objects(conformance.GRAPH_SUBJECT, DCTERMS.conformsTo))
    assert claimed == _EXPECTED_GRAPH


def test_sparql_resource_has_every_expected_document() -> None:
    graph = conformance.declared_conformance()
    claimed = set(graph.objects(conformance.SPARQL_SUBJECT, DCTERMS.conformsTo))
    assert claimed == _EXPECTED_SPARQL


def test_entailment_regimes_are_individual_iris_not_the_whole_document() -> None:
    """SPARQL 1.2 Entailment Regimes itself (the document) must never be
    claimed - only the four individually-supported regime IRIs, and they
    must be exactly the regimes the library's code supports
    (SUPPORTED_REGIMES), so the declaration can't drift from the code."""
    from starlayer.graph.graph.entailment_regimes import SUPPORTED_REGIMES

    graph = conformance.declared_conformance()
    claimed = set(graph.objects(conformance.GRAPH_SUBJECT, DCTERMS.conformsTo))

    claimed_regimes = {c for c in claimed if str(c).startswith("http://www.w3.org/ns/entailment/")}
    assert claimed_regimes == set(SUPPORTED_REGIMES)
    assert not any(True for _ in graph.triples((None, DCTERMS.conformsTo, URIRef("https://www.w3.org/TR/sparql12-entailment"))))
    # the known-but-unsupported D regime must never appear
    assert URIRef("http://www.w3.org/ns/entailment/D") not in claimed


def test_claims_stay_on_their_own_resource_not_cross_contaminated() -> None:
    """The whole point of the per-subpackage design: a SPARQL 1.2 document
    (or an entailment regime IRI) must never end up claimed by the wrong
    resource."""
    graph = conformance.declared_conformance()
    graph_claims = set(graph.objects(conformance.GRAPH_SUBJECT, DCTERMS.conformsTo))
    sparql_claims = set(graph.objects(conformance.SPARQL_SUBJECT, DCTERMS.conformsTo))
    shacl_claims = set(graph.objects(_SHACL_SUBJECT, DCTERMS.conformsTo))

    assert graph_claims.isdisjoint(sparql_claims)
    assert graph_claims.isdisjoint(shacl_claims)
    assert sparql_claims.isdisjoint(shacl_claims)


def test_shacl_resource_matches_declared_conformance_profile() -> None:
    """declared_conformance_profile() returns exactly the starlayer.shacl
    resource's triples from the same profiles document."""
    from starlayer.shacl.shacl_profiling import declared_conformance_profile

    graph = conformance.declared_conformance()
    declared = set(declared_conformance_profile())
    assert declared == set(graph.triples((_SHACL_SUBJECT, None, None)))


def test_each_resource_has_identity_metadata() -> None:
    graph = conformance.declared_conformance()
    for subject in (_SHACL_SUBJECT, conformance.GRAPH_SUBJECT, conformance.SPARQL_SUBJECT):
        assert (subject, RDFS.label, None) in graph
        assert (subject, RDFS.comment, None) in graph
        assert (subject, DCTERMS.modified, None) in graph


def test_each_resource_states_what_it_does_not_claim() -> None:
    """Every resource carries a second rdfs:comment (not just the
    descriptive first one) stating what's deliberately excluded - real
    RDF data on the resource itself, not just source-file header prose a
    caller querying the graph would never see."""
    graph = conformance.declared_conformance()
    for subject in (_SHACL_SUBJECT, conformance.GRAPH_SUBJECT, conformance.SPARQL_SUBJECT):
        comments = list(graph.objects(subject, RDFS.comment))
        assert len(comments) >= 2
        assert any("not claim" in str(c).lower() or "scope reduction" in str(c).lower() for c in comments)


def test_ui_specification_is_claimed_with_its_scope_limits_stated() -> None:
    """SHACL 1.2 User Interfaces is claimed (not the UI Profile, which is a
    different document); the resource's comments state what is not covered."""
    graph = conformance.declared_conformance()
    assert (_SHACL_SUBJECT, DCTERMS.conformsTo, URIRef("https://www.w3.org/TR/shacl12-ui")) in graph
    comments = " ".join(str(c) for c in graph.objects(_SHACL_SUBJECT, RDFS.comment))
    assert "propertyRole" in comments and "scoring catalog" in comments


def test_shacl_resource_neither_claims_nor_excludes_the_ui_profile() -> None:
    """SHACL 1.2 Profiling A.3 defines the UI Profile with no members and no
    conformance requirements, so there is nothing to claim or exclude; the
    resource's comment says so instead."""
    graph = conformance.declared_conformance()
    ui = URIRef("http://www.w3.org/ns/shacl/profile/ui")
    assert (_SHACL_SUBJECT, conformance.DOES_NOT_CONFORM_TO, ui) not in graph
    assert (_SHACL_SUBJECT, DCTERMS.conformsTo, ui) not in graph


def test_graph_resource_does_not_conform_to_d_entailment_explicitly() -> None:
    graph = conformance.declared_conformance()
    assert (
        conformance.GRAPH_SUBJECT,
        conformance.DOES_NOT_CONFORM_TO,
        URIRef("http://www.w3.org/ns/entailment/D"),
    ) in graph


def test_does_not_conform_to_never_contradicts_a_positive_claim() -> None:
    """No (subject, object) pair should ever carry both dcterms:conformsTo
    and conformance:doesNotConformTo - a direct contradiction, and the one
    invariant this predicate's deliberately narrow scope (only cases with
    a real IRI and a total, not scope-limited, exclusion) exists to
    guarantee."""
    graph = conformance.declared_conformance()
    conforms_pairs = {(s, o) for s, _, o in graph.triples((None, DCTERMS.conformsTo, None))}
    does_not_pairs = {(s, o) for s, _, o in graph.triples((None, conformance.DOES_NOT_CONFORM_TO, None))}
    assert conforms_pairs.isdisjoint(does_not_pairs)


def test_fresh_graph_every_call_not_shared() -> None:
    first = conformance.declared_conformance()
    first.remove((conformance.GRAPH_SUBJECT, RDFS.label, None))
    assert not any(True for _ in first.triples((conformance.GRAPH_SUBJECT, RDFS.label, None)))

    second = conformance.declared_conformance()
    assert any(True for _ in second.triples((conformance.GRAPH_SUBJECT, RDFS.label, None)))
