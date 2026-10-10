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

_SHACL_SUBJECT = URIRef("https://github.com/hidden-graph/starlayer/tree/main/packages/shacl")

_EXPECTED_SHACL_PROFILES = {
    URIRef("http://www.w3.org/ns/shacl/profile/core"),
    URIRef("http://www.w3.org/ns/shacl/profile/sparql"),
    URIRef("http://www.w3.org/ns/shacl/profile/node-expr"),
    URIRef("http://www.w3.org/ns/shacl/profile/rules"),
    URIRef("http://www.w3.org/ns/shacl/profile/profiling"),
}
_EXPECTED_RDF12_CORE = {URIRef(url) for url in conformance.RDF12_CORE_TR_URLS}
_EXPECTED_SPARQL12 = {URIRef(url) for url in conformance.SPARQL12_TR_URLS}
_EXPECTED_GRAPH_EXTRA = {URIRef(url) for url in conformance.GRAPH_EXTRA_TR_URLS}
_EXPECTED_SPARQL_EXTRA = {URIRef(url) for url in conformance.SPARQL_EXTRA_TR_URLS}
_EXPECTED_ENTAILMENT_REGIMES = {
    URIRef("http://www.w3.org/ns/entailment/RDF"),
    URIRef("http://www.w3.org/ns/entailment/RDFS"),
    URIRef("http://www.w3.org/ns/entailment/OWL-RDF-Based"),
    URIRef("http://www.w3.org/ns/entailment/OWL-Direct"),
}
_EXPECTED_GRAPH = _EXPECTED_RDF12_CORE | _EXPECTED_GRAPH_EXTRA | _EXPECTED_ENTAILMENT_REGIMES
_EXPECTED_SPARQL = _EXPECTED_SPARQL12 | _EXPECTED_SPARQL_EXTRA


def test_shacl_resource_has_all_five_profiles() -> None:
    graph = conformance.declared_conformance()
    claimed = set(graph.objects(_SHACL_SUBJECT, DCTERMS.conformsTo))
    assert claimed == _EXPECTED_SHACL_PROFILES


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
    claimed - only the four individually-supported regime IRIs, reused
    from the real SUPPORTED_REGIMES constant, not hand-copied."""
    from starlayer.graph.graph.entailment_regimes import SUPPORTED_REGIMES

    graph = conformance.declared_conformance()
    claimed = set(graph.objects(conformance.GRAPH_SUBJECT, DCTERMS.conformsTo))

    assert set(SUPPORTED_REGIMES).issubset(claimed)
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


def test_shacl_resource_is_reused_verbatim_not_hand_copied() -> None:
    """Confirms starlayer.shacl's own resource here is the exact same
    declaration declared_conformance_profile() itself returns (same
    subject, same triples) - not a separately-maintained copy that could
    silently drift."""
    from starlayer.shacl.shacl_profiling import declared_conformance_profile

    shacl_declaration = declared_conformance_profile()

    graph = conformance.declared_conformance()
    for triple in shacl_declaration:
        assert triple in graph


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


def test_shacl_resource_does_not_conform_to_ui_profile_explicitly() -> None:
    """conformance:doesNotConformTo makes the UI Profile exclusion a real,
    queryable triple, not just prose in the asset's header comment."""
    graph = conformance.declared_conformance()
    assert (
        _SHACL_SUBJECT,
        conformance.DOES_NOT_CONFORM_TO,
        URIRef("http://www.w3.org/ns/shacl/profile/ui"),
    ) in graph


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
