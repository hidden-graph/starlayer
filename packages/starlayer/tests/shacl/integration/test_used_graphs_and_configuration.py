import pytest
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Core sections 6.7.1.5-6.7.1.8 (added to the published spec
# 2026-08-03, found via a spec-drift audit - see docs/shacl12-gap-matrix.md)
# add sh:usedDataGraph/sh:usedShapesGraph/sh:usedConfiguration/
# sh:ProcessorConfiguration to the validation report vocabulary: all
# optional (MAY) provenance metadata a processor can choose to populate.
# sh:usedDataGraph/sh:usedShapesGraph need the caller to supply IRI identity
# for graphs that are normally anonymous in-memory rdflib.Graphs - no
# default/invented IRI. sh:usedConfiguration/sh:ProcessorConfiguration is
# opt-in (include_used_configuration=True) since the spec leaves its
# properties fully undefined - an empty blank node by default on every
# report would be pure noise.


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


def test_used_data_graph_and_shapes_graph_absent_by_default() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedDataGraph, None))) == []
    assert list(result.report_graph.triples((None, SH.usedShapesGraph, None))) == []


def test_used_data_graph_and_shapes_graph_added_when_iris_supplied() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        data_graph_iri="http://example.org/graphs/data1",
        shapes_graph_resource="http://example.org/graphs/shapes1",
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.report_graph
    assert (report_node, SH.usedShapesGraph, URIRef("http://example.org/graphs/shapes1")) in result.report_graph


def test_used_data_graph_accepts_a_real_uriref_and_versioned_literal() -> None:
    # The spec explicitly allows "the version IRI of a data/shapes graph"
    # as a value too - a Literal in the general case, not always a URIRef.
    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        data_graph_iri=URIRef("http://example.org/graphs/data1"),
        shapes_graph_resource=Literal("http://example.org/graphs/shapes1#v2"),
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.report_graph
    assert (
        report_node,
        SH.usedShapesGraph,
        Literal("http://example.org/graphs/shapes1#v2"),
    ) in result.report_graph


def test_used_configuration_absent_by_default() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedConfiguration, None))) == []
    assert list(result.report_graph.triples((None, RDF.type, SH.ProcessorConfiguration))) == []


def test_used_configuration_added_when_opted_in() -> None:
    validator = StarShaclSchema(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        include_used_configuration=True,
    )

    report_node = next(result.report_graph.subjects(RDF.type, SH.ValidationReport))
    config_nodes = list(result.report_graph.objects(report_node, SH.usedConfiguration))
    assert len(config_nodes) == 1
    assert (config_nodes[0], RDF.type, SH.ProcessorConfiguration) in result.report_graph


def test_used_data_graph_and_shapes_graph_work_through_apply_rules() -> None:
    # apply_rules() forwards arbitrary kwargs through to validate() via
    # resolve_mode_options/**options - confirm that path actually
    # reaches the new named parameters, not just validate() called directly.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:R a sh:NodeShape ;
              sh:targetSubjectsOf ex:parent ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject sh:this ; sh:predicate ex:hasParent ; sh:object [ sh:path ex:parent ] ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.parent, EX.carol))

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(
        data_graph=data,
        data_graph_iri="http://example.org/graphs/data1",
    )

    report_node = next(result.validation.report_graph.subjects(RDF.type, SH.ValidationReport))
    assert (report_node, SH.usedDataGraph, URIRef("http://example.org/graphs/data1")) in result.validation.report_graph


class TestUsedGraphsFallBackToGraphIdentifier:
    """sh:usedDataGraph/sh:usedShapesGraph also fall back to data_graph.identifier
    /shacl_graph.identifier (2026-10-09), when it's a real URIRef the caller
    explicitly gave the graph at construction - never the default random
    BNode every rdflib Graph otherwise gets. An explicit data_graph_iri=/
    shapes_graph_resource= is never overridden by this fallback."""

    def test_falls_back_to_identifier_when_a_real_uriref(self) -> None:
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, Literal(30)))
        shapes = StarLayerGraph(identifier=EX.MyShapesGraph)
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

        result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

        assert (None, SH.usedDataGraph, EX.MyDataGraph) in result.report_graph
        assert (None, SH.usedShapesGraph, EX.MyShapesGraph) in result.report_graph

    def test_default_bnode_identifier_is_never_used(self) -> None:
        validator = StarShaclSchema(shacl_graph=_shapes())
        result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

        assert not any(True for _ in result.report_graph.triples((None, SH.usedDataGraph, None)))
        assert not any(True for _ in result.report_graph.triples((None, SH.usedShapesGraph, None)))

    def test_explicit_iri_is_never_overridden_by_identifier(self) -> None:
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, Literal(30)))

        result = StarShaclSchema(shacl_graph=_shapes()).validate(
            data_graph=data,
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/explicit",
        )

        used = list(result.report_graph.triples((None, SH.usedDataGraph, None)))
        assert len(used) == 1
        assert str(used[0][2]) == "http://example.org/graphs/explicit"

    def test_bare_validate_function_also_falls_back_to_identifier(self) -> None:
        from starlayer.shacl.validator import validate as bare_validate

        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, Literal(30)))

        result = bare_validate(data, _shapes(), meta_shacl=False)

        assert (None, SH.usedDataGraph, EX.MyDataGraph) in result.report_graph


class TestAutomaticConformsToDerivation:
    """validate() automatically derives and merges SHACL 1.2 Profiling
    S5.5's sh:conformsTo triple into report_graph (2026-10-09), whenever
    both data_graph_iri=/shapes_graph_resource= resolve to real values - no
    separate derive_conforms_to() call needed. Fires on either the IRIs
    being given explicitly, or via the .identifier fallback/shapes_graph_resource=
    naming a real module (2026-10-10, see TestValidateShapesGraph in
    test_extract_shapes_graph.py for the full module-vs-tag design) - the
    merge itself doesn't care which path produced them."""

    def test_both_iris_given_conforming_report_gets_conforms_to(self) -> None:
        result = StarShaclSchema(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert result.conforms is True
        assert (
            URIRef("http://example.org/graphs/data1"),
            SH.conformsTo,
            URIRef("http://example.org/graphs/shapes1"),
        ) in result.report_graph

    def test_only_one_iri_given_no_conforms_to_attempted(self) -> None:
        """derive_conforms_to() would raise ValueError if only one graph
        identity were resolvable - this must never be attempted unless
        both are present, not just left to fail silently."""
        result = StarShaclSchema(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
        )
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsTo, None)))

    def test_neither_iri_given_no_conforms_to(self) -> None:
        result = StarShaclSchema(shacl_graph=_shapes()).validate(data_graph=_valid_data(), meta_shacl=False)
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsTo, None)))

    def test_non_conforming_report_gets_no_conforms_to(self) -> None:
        bad_shapes = StarLayerGraph()
        bad_shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
                ex:S a sh:NodeShape ;
                  sh:targetNode ex:alice ;
                  sh:property [ sh:path ex:age ; sh:datatype xsd:string ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        result = StarShaclSchema(shacl_graph=bad_shapes).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert result.conforms is False
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsTo, None)))

    def test_bare_validate_function_also_derives_automatically(self) -> None:
        from starlayer.shacl.validator import validate as bare_validate

        result = bare_validate(
            _valid_data(),
            _shapes(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_iri="http://example.org/graphs/shapes1",
        )
        assert (
            URIRef("http://example.org/graphs/data1"),
            SH.conformsTo,
            URIRef("http://example.org/graphs/shapes1"),
        ) in result.report_graph

    def test_fires_via_the_identifier_fallback_too(self) -> None:
        """The merge is keyed off the resolved data_graph_iri/shapes_graph_iri
        values, not off whether the caller passed them explicitly - so the
        same-day .identifier fallback (see TestUsedGraphsFallBackToGraphIdentifier
        above) triggers this derivation too, with no extra wiring needed."""
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, Literal(30)))
        shapes = StarLayerGraph(identifier=EX.MyShapesGraph)
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
        result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
        assert (EX.MyDataGraph, SH.conformsTo, EX.MyShapesGraph) in result.report_graph


class TestValidateSpecificationGraphParameter:
    """specification_graph= is deliberately *not* a StarShaclSchema
    construction-time property or a validate() parameter - it was
    briefly both (2026-10-10), reverted the same day: "what specification
    does this data conform to" is a publishing decision about the result,
    not an intrinsic fact about how to validate (unlike shacl_graph/
    ont_graph/inference), so binding it at construction would make every
    validate() call on one schema instance always assert the same
    external-spec claim whether or not that caller wanted it. The real,
    supported path is calling shacl_profiling.derive_conforms_to()
    explicitly, after validate() returns - see its own module docstring.
    sh:conformsTo (S5.5's first rule) is unaffected either way; it never
    depended on specification_graph. The bare module-level validate()
    function still keeps its own per-call specification_graph= - it has
    no "schema" object for this reasoning to apply to."""

    from rdflib import Namespace as _Namespace

    DCTERMS = _Namespace("http://purl.org/dc/terms/")
    PROF = _Namespace("http://www.w3.org/ns/dx/prof/")

    def _specification_graph(self, shapes_graph_iri, specification_iri):
        from rdflib import Graph

        graph = Graph()
        graph.add((shapes_graph_iri, self.PROF.isProfileOf, specification_iri))
        return graph

    def test_schema_rejects_specification_graph_as_a_construction_kwarg(self) -> None:
        with pytest.raises(TypeError):
            StarShaclSchema(shacl_graph=_shapes(), specification_graph=StarLayerGraph())

    def test_explicit_derive_conforms_to_after_validate_derives_dcterms_conforms_to(self) -> None:
        from starlayer.shacl.shacl_profiling import derive_conforms_to

        shapes_iri = URIRef("http://example.org/graphs/shapes1")
        spec_iri = URIRef("http://example.org/specs/my-spec")
        result = StarShaclSchema(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource=shapes_iri,
        )
        assert result.conforms is True
        assert (URIRef("http://example.org/graphs/data1"), SH.conformsTo, shapes_iri) in result.report_graph
        # dcterms:conformsTo is absent until the application asks for it -
        # validate() itself never derives it.
        assert not any(True for _ in result.report_graph.triples((None, self.DCTERMS.conformsTo, None)))

        derived = derive_conforms_to(
            result.report_graph,
            specification_graph=self._specification_graph(shapes_iri, spec_iri),
        )
        for t in derived:
            result.report_graph.add(t)
        assert (URIRef("http://example.org/graphs/data1"), self.DCTERMS.conformsTo, spec_iri) in result.report_graph

    def test_no_specification_graph_only_sh_conforms_to_as_before(self) -> None:
        """validate() alone, with no application-level derive_conforms_to()
        call afterward, never produces dcterms:conformsTo."""
        result = StarShaclSchema(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert not any(True for _ in result.report_graph.triples((None, self.DCTERMS.conformsTo, None)))

    def test_bare_validate_function_also_accepts_specification_graph(self) -> None:
        from starlayer.shacl.validator import validate as bare_validate

        shapes_iri = URIRef("http://example.org/graphs/shapes1")
        spec_iri = URIRef("http://example.org/specs/my-spec")
        result = bare_validate(
            _valid_data(),
            _shapes(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_iri=shapes_iri,
            specification_graph=self._specification_graph(shapes_iri, spec_iri),
        )
        assert (URIRef("http://example.org/graphs/data1"), self.DCTERMS.conformsTo, spec_iri) in result.report_graph
