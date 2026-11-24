import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor
from starlayer.shacl.engine.terms import text
from tests.support.terms import RDF, NamedNode, Namespace, lit

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
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
# Since 2026-11-23 all of it is on a sh:ValidationActivity that prov:generated
# the report (Profiling "Persisting validation results with context"), never on
# the report node.
PROV = Namespace("http://www.w3.org/ns/prov#")
AGENT = NamedNode("https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/shacl")
OLD = (SH.usedDataGraph, SH.usedShapesGraph, SH.usedConfiguration)


def _report_node(g):
    return next(g.subjects(RDF.type, SH.ValidationReport))


def _activity(g):
    """The one activity of the report graph; its ``prov:generated`` is the report node."""
    found = list(g.subjects(RDF.type, SH.ValidationActivity))
    assert len(found) == 1
    assert (found[0], PROV.generated, _report_node(g)) in g
    return found[0]


def _valid_data() -> StarLayerGraph:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, lit(30)))
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


@pytest.mark.parametrize(
    ("kwargs", "data", "shapes", "config"),
    [
        ({"data_graph_iri": "http://example.org/d"}, True, False, False),
        ({"shapes_graph_resource": "http://example.org/s"}, False, True, False),
        ({"data_graph_iri": "http://example.org/d", "shapes_graph_resource": "http://example.org/s"}, True, True, False),
        ({"include_used_configuration": True}, False, False, True),
        (
            {"data_graph_iri": "http://example.org/d", "shapes_graph_resource": "http://example.org/s", "include_used_configuration": True},
            True,
            True,
            True,
        ),
    ],
)
def test_activity_carries_exactly_the_known_names_and_the_agent(kwargs, data, shapes, config) -> None:
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(data_graph=_valid_data(), meta_shacl=False, **kwargs)
    g = result.report_graph
    activity = _activity(g)
    assert (activity, RDF.type, SH.ValidationActivity) in g
    assert [o for o in g.objects(activity, SH.usedDataGraph)] == ([NamedNode("http://example.org/d")] if data else [])
    assert [o for o in g.objects(activity, SH.usedShapesGraph)] == ([NamedNode("http://example.org/s")] if shapes else [])
    configs = list(g.objects(activity, SH.usedConfiguration))
    assert len(configs) == (1 if config else 0)
    assert list(g.objects(activity, PROV.wasAssociatedWith)) == [AGENT]
    assert (AGENT, RDF.type, SH.ValidationAgent) in g
    # the report node keeps none of the old report-node properties
    for predicate in OLD:
        assert list(g.triples((_report_node(g), predicate, None))) == []
    # no time or other run-dependent value
    assert list(g.triples((activity, PROV.startedAtTime, None))) == []
    assert list(g.triples((None, PROV.generatedAtTime, None))) == []
    assert (data and shapes) == ((NamedNode("http://example.org/d"), SH.conformsToShapesGraph, NamedNode("http://example.org/s")) in g)


def test_no_activity_without_names_or_configuration_request() -> None:
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(data_graph=_valid_data(), meta_shacl=False)
    g = result.report_graph
    assert list(g.triples((None, RDF.type, SH.ValidationActivity))) == []
    assert list(g.triples((None, PROV.generated, None))) == []
    assert list(g.triples((None, RDF.type, SH.ValidationAgent))) == []


def test_activity_report_serialises_with_the_prov_prefix() -> None:
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(
        data_graph=_valid_data(), meta_shacl=False, data_graph_iri="http://example.org/d"
    )
    ttl = result.report_graph.serialize(format="turtle")
    assert "prov:generated" in ttl and "@prefix prov:" in ttl


def test_non_conforming_run_has_the_activity_but_no_conforms_to_shapes_graph() -> None:
    bad = StarLayerGraph()
    bad.add((EX.alice, EX.age, lit("old")))
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(
        data_graph=bad, meta_shacl=False, data_graph_iri="http://example.org/d", shapes_graph_resource="http://example.org/s"
    )
    assert (_activity(result.report_graph), SH.usedDataGraph, NamedNode("http://example.org/d")) in result.report_graph
    assert list(result.report_graph.triples((None, SH.conformsToShapesGraph, None))) == []


def test_report_text_provenance_reads_the_activity() -> None:
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(
        data_graph=_valid_data(), meta_shacl=False, data_graph_iri="http://example.org/d", shapes_graph_resource="http://example.org/s"
    )
    text_out = result.report_text
    assert "Provenance:" in text_out
    assert "Used Data Graph: ex:d" in text_out
    assert "Used Shapes Graph: ex:s" in text_out


def test_used_data_graph_and_shapes_graph_absent_by_default() -> None:
    validator = StarShaclProcessor(shacl_graph=_shapes())
    result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedDataGraph, None))) == []
    assert list(result.report_graph.triples((None, SH.usedShapesGraph, None))) == []


def test_used_data_graph_and_shapes_graph_added_when_iris_supplied() -> None:
    validator = StarShaclProcessor(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        data_graph_iri="http://example.org/graphs/data1",
        shapes_graph_resource="http://example.org/graphs/shapes1",
    )

    report_node = _activity(result.report_graph)
    assert (report_node, SH.usedDataGraph, NamedNode("http://example.org/graphs/data1")) in result.report_graph
    assert (report_node, SH.usedShapesGraph, NamedNode("http://example.org/graphs/shapes1")) in result.report_graph


def test_used_data_graph_accepts_a_real_uriref_and_versioned_literal() -> None:
    # The spec explicitly allows "the version IRI of a data/shapes graph"
    # as a value too - a Literal in the general case, not always a NamedNode.
    validator = StarShaclProcessor(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        data_graph_iri=NamedNode("http://example.org/graphs/data1"),
        shapes_graph_resource=lit("http://example.org/graphs/shapes1#v2"),
    )

    report_node = _activity(result.report_graph)
    assert (report_node, SH.usedDataGraph, NamedNode("http://example.org/graphs/data1")) in result.report_graph
    assert (
        report_node,
        SH.usedShapesGraph,
        lit("http://example.org/graphs/shapes1#v2"),
    ) in result.report_graph


def test_used_configuration_absent_by_default() -> None:
    validator = StarShaclProcessor(shacl_graph=_shapes())
    result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

    assert list(result.report_graph.triples((None, SH.usedConfiguration, None))) == []
    assert list(result.report_graph.triples((None, RDF.type, SH.ProcessorConfiguration))) == []


def test_used_configuration_added_when_opted_in() -> None:
    validator = StarShaclProcessor(shacl_graph=_shapes())
    result = validator.validate(
        data_graph=_valid_data(),
        meta_shacl=False,
        include_used_configuration=True,
    )

    report_node = _activity(result.report_graph)
    config_nodes = list(result.report_graph.objects(report_node, SH.usedConfiguration))
    assert len(config_nodes) == 1
    assert (config_nodes[0], RDF.type, SH.ProcessorConfiguration) in result.report_graph


OPTION = "urn:starlayer:shacl-engine:option:"


def _options(report_graph) -> dict:
    """The recorded options of the one configuration node, by name, with their lexical values."""
    activity = _activity(report_graph)
    (config,) = report_graph.objects(activity, SH.usedConfiguration)
    return {predicate.value[len(OPTION):]: value.value for predicate, value in report_graph.predicate_objects(config) if predicate.value.startswith(OPTION)}


def test_the_options_the_agent_and_the_regime_print_as_prefixed_names() -> None:
    from starlayer.graph import ENTAILMENT

    processor = StarShaclProcessor(shacl_graph=_shapes(), inference=ENTAILMENT.RDFS)
    text_ = processor.validate(data_graph=_valid_data(), include_used_configuration=True).report_graph.serialize(format="turtle")
    for expected in ("slopt:abortOnFirst", "starlayer:shacl a sh:ValidationAgent", "slopt:inference ent:RDFS"):
        assert expected in text_, expected


def test_the_configuration_records_every_option_in_effect_with_its_default() -> None:
    result = StarShaclProcessor(shacl_graph=_shapes()).validate(data_graph=_valid_data(), include_used_configuration=True)
    assert _options(result.report_graph) == {
        "abortOnFirst": "false", "inplace": "false", "maxValidationDepth": "500",
        "subclassOfInShapesGraph": "false", "ignoreImports": "false", "metaShacl": "false",
    }


def test_the_configuration_records_the_settings_that_were_turned_on() -> None:
    from starlayer.graph import ENTAILMENT

    processor = StarShaclProcessor(shacl_graph=_shapes(), inference=ENTAILMENT.RDFS, subclass_of_in_shapes_graph=True, meta_shacl=True)
    options = _options(processor.validate(data_graph=_valid_data(), include_used_configuration=True, abort_on_first=True).report_graph)
    assert options["subclassOfInShapesGraph"] == "true" and options["metaShacl"] == "true" and options["abortOnFirst"] == "true"
    assert options["inference"] == "http://www.w3.org/ns/entailment/RDFS"
    assert "engine" not in options and "timeout" not in options  # the OWL-Direct settings are recorded only for that regime


def test_the_configuration_records_the_owl_direct_settings_for_that_regime() -> None:
    from starlayer.graph import ENTAILMENT

    pytest.importorskip("jpype")
    processor = StarShaclProcessor(shacl_graph=_shapes(), inference=ENTAILMENT["OWL-Direct"])
    options = _options(processor.validate(data_graph=_valid_data(), include_used_configuration=True).report_graph)
    assert options["engine"] == "hermit" and options["recompute"] == "onChange"


def test_the_owl_direct_settings_are_picked_out_only_for_that_regime() -> None:
    from starlayer.graph.entailment import ENTAILMENT, OWL_DIRECT_REGIME
    from starlayer.shacl.engine.api import _owl_direct_options

    assert _owl_direct_options([OWL_DIRECT_REGIME, ENTAILMENT.RDFS.value], "hermit", 30, "onChange") == {"engine": "hermit", "timeout": 30, "recompute": "onChange"}
    assert _owl_direct_options(ENTAILMENT.RDFS, "hermit", None, "onChange") == {}
    assert _owl_direct_options(None, "hermit", None, "onChange") == {}


def test_the_configuration_of_apply_rules_records_the_rule_limits() -> None:
    processor = StarShaclProcessor(shacl_graph=_shapes())
    result = processor.apply_rules(data_graph=_valid_data(), include_used_configuration=True, max_iterations=50)
    options = _options(result.validation.report_graph)
    assert options["maxIterations"] == "50" and options["rules"] == "true" and "maxTriples" not in options


def test_used_data_graph_and_shapes_graph_work_through_apply_rules() -> None:
    # apply_rules() forwards arbitrary kwargs through to validate() via
    # resolve_mode_options/**options - confirm that path actually
    # reaches the new named parameters, not just validate() called directly.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
            ex:R a sh:NodeShape ;
              sh:targetSubjectsOf ex:parent ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:hasParent ; sh:object [ shnex:pathValues ex:parent ] ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.parent, EX.carol))

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.apply_rules(
        data_graph=data,
        data_graph_iri="http://example.org/graphs/data1",
    )

    report_node = _activity(result.validation.report_graph)
    assert (report_node, SH.usedDataGraph, NamedNode("http://example.org/graphs/data1")) in result.validation.report_graph


class TestUsedGraphsFallBackToGraphIdentifier:
    """sh:usedDataGraph/sh:usedShapesGraph also fall back to data_graph.identifier
    /shacl_graph.identifier (2026-10-09), when it's a real NamedNode the caller
    explicitly gave the graph at construction - never the default random
    BNode every rdflib Graph otherwise gets. An explicit data_graph_iri=/
    shapes_graph_resource= is never overridden by this fallback."""

    def test_falls_back_to_identifier_when_a_real_uriref(self) -> None:
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, lit(30)))
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

        result = StarShaclProcessor(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

        assert (None, SH.usedDataGraph, EX.MyDataGraph) in result.report_graph
        assert (None, SH.usedShapesGraph, EX.MyShapesGraph) in result.report_graph

    def test_default_bnode_identifier_is_never_used(self) -> None:
        validator = StarShaclProcessor(shacl_graph=_shapes())
        result = validator.validate(data_graph=_valid_data(), meta_shacl=False)

        assert not any(True for _ in result.report_graph.triples((None, SH.usedDataGraph, None)))
        assert not any(True for _ in result.report_graph.triples((None, SH.usedShapesGraph, None)))

    def test_explicit_iri_is_never_overridden_by_identifier(self) -> None:
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, lit(30)))

        result = StarShaclProcessor(shacl_graph=_shapes()).validate(
            data_graph=data,
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/explicit",
        )

        used = list(result.report_graph.triples((None, SH.usedDataGraph, None)))
        assert len(used) == 1
        assert text(used[0][2]) == "http://example.org/graphs/explicit"

    def test_bare_validate_function_also_falls_back_to_identifier(self) -> None:
        from starlayer.shacl.validator import validate as bare_validate

        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, lit(30)))

        result = bare_validate(data, _shapes(), meta_shacl=False)

        assert (None, SH.usedDataGraph, EX.MyDataGraph) in result.report_graph


class TestAutomaticConformsToDerivation:
    """validate() automatically derives and merges SHACL 1.2 Profiling
    S5.7's sh:conformsToShapesGraph triple into report_graph (2026-10-09), whenever
    both data_graph_iri=/shapes_graph_resource= resolve to real values - no
    separate derive_conforms_to() call needed. Fires on either the IRIs
    being given explicitly, or via the .identifier fallback/shapes_graph_resource=
    naming a real module (2026-10-10, see TestValidateShapesGraph in
    test_extract_shapes_graph.py for the full module-vs-tag design) - the
    merge itself doesn't care which path produced them."""

    def test_both_iris_given_conforming_report_gets_conforms_to(self) -> None:
        result = StarShaclProcessor(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert result.conforms is True
        assert (
            NamedNode("http://example.org/graphs/data1"),
            SH.conformsToShapesGraph,
            NamedNode("http://example.org/graphs/shapes1"),
        ) in result.report_graph
        # the draft has no sh:validationReport and no sh:conformsTo (it is sh:conformsToShapesGraph)
        assert not any(True for _ in result.report_graph.triples((None, SH.validationReport, None)))
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsTo, None)))

    def test_only_one_iri_given_no_conforms_to_attempted(self) -> None:
        """derive_conforms_to() would raise ValueError if only one graph
        identity were resolvable - this must never be attempted unless
        both are present, not just left to fail silently."""
        result = StarShaclProcessor(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
        )
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsToShapesGraph, None)))

    def test_neither_iri_given_no_conforms_to(self) -> None:
        result = StarShaclProcessor(shacl_graph=_shapes()).validate(data_graph=_valid_data(), meta_shacl=False)
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsToShapesGraph, None)))

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
        result = StarShaclProcessor(shacl_graph=bad_shapes).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert result.conforms is False
        assert not any(True for _ in result.report_graph.triples((None, SH.conformsToShapesGraph, None)))

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
            NamedNode("http://example.org/graphs/data1"),
            SH.conformsToShapesGraph,
            NamedNode("http://example.org/graphs/shapes1"),
        ) in result.report_graph

    def test_fires_via_the_identifier_fallback_too(self) -> None:
        """The merge is keyed off the resolved data_graph_iri/shapes_graph_iri
        values, not off whether the caller passed them explicitly - so the
        same-day .identifier fallback (see TestUsedGraphsFallBackToGraphIdentifier
        above) triggers this derivation too, with no extra wiring needed."""
        data = StarLayerGraph(identifier=EX.MyDataGraph)
        data.add((EX.alice, EX.age, lit(30)))
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
        result = StarShaclProcessor(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
        assert (EX.MyDataGraph, SH.conformsToShapesGraph, EX.MyShapesGraph) in result.report_graph


class TestValidateSpecificationGraphParameter:
    """specification_graph= is deliberately *not* a StarShaclProcessor
    construction-time property or a validate() parameter - it was
    briefly both (2026-10-10), reverted the same day: "what specification
    does this data conform to" is a publishing decision about the result,
    not an intrinsic fact about how to validate (unlike shacl_graph/
    ont_graph/inference), so binding it at construction would make every
    validate() call on one schema instance always assert the same
    external-spec claim whether or not that caller wanted it. The real,
    supported path is calling profiling.derive_conforms_to()
    explicitly, after validate() returns - see its own module docstring.
    sh:conformsToShapesGraph (S5.7's rule) is unaffected either way; it never
    depended on specification_graph. The bare module-level validate()
    function still keeps its own per-call specification_graph= - it has
    no "schema" object for this reasoning to apply to."""

    from tests.support.terms import Namespace as _Namespace

    DCTERMS = _Namespace("http://purl.org/dc/terms/")
    PROF = _Namespace("http://www.w3.org/ns/dx/prof/")

    def _specification_graph(self, shapes_graph_iri, specification_iri):
        from starlayer.graph import StarLayerGraph as Graph

        graph = Graph()
        graph.add((shapes_graph_iri, self.PROF.isProfileOf, specification_iri))
        return graph

    def test_schema_rejects_specification_graph_as_a_construction_kwarg(self) -> None:
        with pytest.raises(TypeError):
            StarShaclProcessor(shacl_graph=_shapes(), specification_graph=StarLayerGraph())

    def test_explicit_derive_conforms_to_after_validate_derives_dcterms_conforms_to(self) -> None:
        from starlayer.shacl.profiling import derive_conforms_to

        shapes_iri = NamedNode("http://example.org/graphs/shapes1")
        spec_iri = NamedNode("http://example.org/specs/my-spec")
        result = StarShaclProcessor(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource=shapes_iri,
        )
        assert result.conforms is True
        assert (NamedNode("http://example.org/graphs/data1"), SH.conformsToShapesGraph, shapes_iri) in result.report_graph
        # dcterms:conformsTo is absent until the application asks for it -
        # validate() itself never derives it.
        assert not any(True for _ in result.report_graph.triples((None, self.DCTERMS.conformsTo, None)))

        derived = derive_conforms_to(
            result.report_graph,
            specification_graph=self._specification_graph(shapes_iri, spec_iri),
        )
        for t in derived:
            result.report_graph.add(t)
        assert (NamedNode("http://example.org/graphs/data1"), self.DCTERMS.conformsTo, spec_iri) in result.report_graph

    def test_no_specification_graph_only_sh_conforms_to_as_before(self) -> None:
        """validate() alone, with no application-level derive_conforms_to()
        call afterward, never produces dcterms:conformsTo."""
        result = StarShaclProcessor(shacl_graph=_shapes()).validate(
            data_graph=_valid_data(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_resource="http://example.org/graphs/shapes1",
        )
        assert not any(True for _ in result.report_graph.triples((None, self.DCTERMS.conformsTo, None)))

    def test_bare_validate_function_also_accepts_specification_graph(self) -> None:
        from starlayer.shacl.validator import validate as bare_validate

        shapes_iri = NamedNode("http://example.org/graphs/shapes1")
        spec_iri = NamedNode("http://example.org/specs/my-spec")
        result = bare_validate(
            _valid_data(),
            _shapes(),
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/data1",
            shapes_graph_iri=shapes_iri,
            specification_graph=self._specification_graph(shapes_iri, spec_iri),
        )
        assert (NamedNode("http://example.org/graphs/data1"), self.DCTERMS.conformsTo, spec_iri) in result.report_graph
