import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator, declared_conformance_profile, derive_conforms_to

SH = Namespace("http://www.w3.org/ns/shacl#")
PROF = Namespace("http://www.w3.org/ns/dx/prof/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")

_LIBRARY_IRI = URIRef("https://github.com/hidden-graph/starlayer/tree/main/packages/shacl")
_DECLARED_PROFILES = (
    URIRef("http://www.w3.org/ns/shacl/profile/core"),
    URIRef("http://www.w3.org/ns/shacl/profile/sparql"),
    URIRef("http://www.w3.org/ns/shacl/profile/node-expr"),
    URIRef("http://www.w3.org/ns/shacl/profile/rules"),
)
_UNDECLARED_PROFILES = (
    URIRef("http://www.w3.org/ns/shacl/profile/ui"),
    URIRef("http://www.w3.org/ns/shacl/profile/profiling"),
)


def _valid_data() -> StarLayerGraph:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, Literal(30)))
    return data


def _shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] .
        """,
        format="turtle",
    )
    return shapes


def _conformant_report(*, conforms: bool = True) -> Graph:
    graph = Graph()
    report_node = URIRef("urn:test:report")
    graph.add((report_node, RDF.type, SH.ValidationReport))
    graph.add((report_node, SH.conforms, Literal(conforms)))
    return graph


def test_declared_conformance_profile_asserts_the_four_implemented_profiles() -> None:
    graph = declared_conformance_profile()
    declared = set(graph.objects(_LIBRARY_IRI, DCTERMS.conformsTo))
    for profile_iri in _DECLARED_PROFILES:
        assert profile_iri in declared


def test_declared_conformance_profile_deliberately_excludes_ui_and_profiling() -> None:
    graph = declared_conformance_profile()
    declared = set(graph.objects(_LIBRARY_IRI, DCTERMS.conformsTo))
    for profile_iri in _UNDECLARED_PROFILES:
        assert profile_iri not in declared


def test_declared_conformance_profile_returns_independent_copies() -> None:
    first = declared_conformance_profile()
    first.add((_LIBRARY_IRI, DCTERMS.conformsTo, URIRef("http://www.w3.org/ns/shacl/profile/ui")))

    second = declared_conformance_profile()

    assert (_LIBRARY_IRI, DCTERMS.conformsTo, URIRef("http://www.w3.org/ns/shacl/profile/ui")) not in second


def test_derive_conforms_to_from_conformant_report_produces_the_triple() -> None:
    report = _conformant_report(conforms=True)
    data_graph = URIRef("urn:test:data")
    shapes_graph = URIRef("urn:test:shapes")

    # Adversarial check per this repo's testing discipline: the triple must
    # not already be sitting in the input report, otherwise the assertion
    # below wouldn't actually be exercising derive_conforms_to.
    assert (data_graph, SH.conformsTo, shapes_graph) not in report

    derived = derive_conforms_to(report, data_graph=data_graph, shapes_graph=shapes_graph)

    assert (data_graph, SH.conformsTo, shapes_graph) in derived
    # The input report itself must not be mutated.
    assert (data_graph, SH.conformsTo, shapes_graph) not in report


def test_derive_conforms_to_from_non_conformant_report_derives_nothing() -> None:
    report = _conformant_report(conforms=False)

    derived = derive_conforms_to(report, data_graph="urn:test:data", shapes_graph="urn:test:shapes")

    assert len(derived) == 0


def test_derive_conforms_to_raises_without_validation_report_node() -> None:
    empty_report = Graph()

    with pytest.raises(ValueError):
        derive_conforms_to(empty_report, data_graph="urn:test:data", shapes_graph="urn:test:shapes")


def test_derive_conforms_to_raises_when_no_graph_iri_available() -> None:
    report = _conformant_report(conforms=True)

    with pytest.raises(ValueError):
        derive_conforms_to(report)


def test_derive_conforms_to_reads_graph_iris_from_report_when_omitted() -> None:
    # The realistic path: validate() was called with data_graph_iri=/
    # shapes_graph_iri=, so sh:usedDataGraph/sh:usedShapesGraph are already
    # on the report - derive_conforms_to() shouldn't need them repeated.
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_valid_data(),
        shacl_graph=_shapes(),
        meta_shacl=False,
        data_graph_iri="http://example.org/graphs/data1",
        shapes_graph_iri="http://example.org/graphs/shapes1",
    )
    assert result.conforms is True

    derived = derive_conforms_to(result.report_graph)

    assert (
        URIRef("http://example.org/graphs/data1"),
        SH.conformsTo,
        URIRef("http://example.org/graphs/shapes1"),
    ) in derived


def test_derive_conforms_to_with_specification_graph_derives_dcterms_conforms_to() -> None:
    report = _conformant_report(conforms=True)
    data_graph = URIRef("urn:test:data")
    shapes_graph = URIRef("urn:test:shapes")
    specification = URIRef("urn:test:some-specification")

    spec_graph = Graph()
    spec_graph.add((shapes_graph, PROF.isProfileOf, specification))

    # Adversarial check: confirm the second-rule derivation genuinely
    # depends on specification_graph being passed, not something that
    # would fall out of the first rule alone.
    without_spec = derive_conforms_to(report, data_graph=data_graph, shapes_graph=shapes_graph)
    assert (data_graph, DCTERMS.conformsTo, specification) not in without_spec

    with_spec = derive_conforms_to(
        report, data_graph=data_graph, shapes_graph=shapes_graph, specification_graph=spec_graph
    )

    assert (data_graph, SH.conformsTo, shapes_graph) in with_spec
    assert (data_graph, DCTERMS.conformsTo, specification) in with_spec
