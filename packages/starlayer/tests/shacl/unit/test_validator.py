
import pytest
from rdflib import Graph, Literal, Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import ShapeError
from starlayer.shacl_engine.terms import from_engine
from starlayer.shacl.validator import StarShaclSchema, evaluate, validate, validate_each

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


class TestBareFunctionsWorkWithoutStarShaclSchema:
    """validate()/validate_each()/evaluate() are now the real
    implementations, not thin wrappers around StarShaclSchema (2026-10-07
    - see starlayer/shacl/CLAUDE.md's dated entry; StarShaclSchema's own
    methods are untouched for now, step 2 of a two-step flip). These
    tests call the bare functions directly, with no StarShaclSchema
    instance involved anywhere, confirming step 1 stands on its own."""

    def _shapes(self) -> StarLayerGraph:
        g = StarLayerGraph()
        g.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:PersonShape a sh:NodeShape ;
                    sh:targetClass ex:Person ;
                    sh:property [ sh:path ex:name ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        return g

    def test_bare_validate_conforms_true(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:bob a ex:Person ; ex:name \"Bob\" .", format="turtle")

        result = validate(data, self._shapes(), meta_shacl=False)

        assert result.conforms is True

    def test_bare_validate_conforms_false(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle")

        result = validate(data, self._shapes(), meta_shacl=False)

        assert result.conforms is False

    def test_bare_validate_matches_schema_method_result(self) -> None:
        shapes = self._shapes()
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle")

        bare_result = validate(data, shapes, meta_shacl=False)
        method_result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)

        assert bare_result.conforms == method_result.conforms is False

    def test_bare_validate_each(self) -> None:
        shapes = self._shapes()
        conforming = StarLayerGraph()
        conforming.parse(
            data="@prefix ex: <http://example.org/> . ex:bob a ex:Person ; ex:name \"Bob\" .", format="turtle"
        )
        violating = StarLayerGraph()
        violating.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Person .", format="turtle")

        results = validate_each([violating, conforming], shapes, meta_shacl=False)

        assert results[0].conforms is False
        assert results[1].conforms is True

    def test_bare_evaluate_computes_sh_values(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
                ex:FriendCountShape a sh:NodeShape ;
                    sh:targetClass ex:Person ;
                    sh:property [
                        sh:path ex:friendCount ;
                        sh:values [ shnex:count [ shnex:pathValues ex:friend ] ]
                    ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:carol a ex:Person ; ex:friend ex:dave, ex:erin .",
            format="turtle",
        )

        result = evaluate(data, shapes)

        assert [from_engine(o) for o in result.objects(EX.carol, EX.friendCount)] == [Literal(2)]
        # The caller's own data_graph is never mutated - evaluate() always
        # returns a throwaway copy, per its own documented contract.
        assert (EX.carol, EX.friendCount, Literal(2)) not in data






def test_module_level_validate_each_matches_starlayershacl_method() -> None:
    from starlayer.shacl import validate_each

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://example.org/> .
        ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    conforming = StarLayerGraph()
    conforming.parse(
        data='@prefix ex: <http://example.org/> . ex:alice a ex:Person ; ex:name "Alice" .',
        format="turtle",
    )
    violating = StarLayerGraph()
    violating.parse(data="@prefix ex: <http://example.org/> . ex:bob a ex:Person .", format="turtle")

    results = validate_each([conforming, violating], shacl_graph=shapes)

    assert results[0].conforms is True
    assert results[1].conforms is False














































def test_validate_reification_required_violation_when_no_reifier_exists() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert any(
        from_engine(o) == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
    # sh:value is the plain failing value, not the reified (focus, path,
    # value) triple term - confirmed against the W3C SHACL 1.2 test suite's
    # own reifierShape-001/002 fixtures (tests/w3c_shacl12/), which fixed a
    # real bug here: this assertion previously (wrongly) expected the
    # encoded triple term itself.
    assert any(from_engine(o) == Literal("A") for _, _, o in result.report_graph.triples((None, SH.value, None)))


def test_validate_reifier_shape_violation_survives_advanced_mode() -> None:
    # Found 2026-07-31 via the W3C SHACL 1.2 test suite: advanced=True makes
    # pyshacl.validator.Validator unconditionally clone the data graph
    # ("Forcing clone of DataGraph because advanced mode is enabled" - so
    # SHACL-AF rules don't mutate the caller's original graph).
    # RdfLibDataGraph.clone() builds the copy via pySHACL's own
    # rdfutil.clone.clone_graph(), which produces a *plain* rdflib.Graph -
    # it has no notion of starShacl's _SparqlAwareEncodedGraph wrapper or its
    # _tt_adapter back-reference, even though the clone's actual (encoded)
    # triples are faithfully copied. Without _tt_adapter,
    # ReifierShapeConstraintComponent's reifier lookup can never re-encode a
    # (focus, path, value) tuple into the matching stored URI, so it always
    # finds zero reifiers and reports vacuous conformance regardless of
    # whether one actually exists.
    #
    # Needs an *existing* reifier to expose this (unlike the
    # sh:reificationRequired "no reifier at all" case, which returns the same
    # empty reifier set whether or not the lookup key is correctly encoded,
    # and so can't tell the two cases apart) - reuses the same shapes/data as
    # test_validate_reifier_shape_violation_when_reifier_does_not_conform,
    # differing only by advanced=True. Fixed by
    # validator.py::_patch_rdflib_data_graph_clone_preserves_tt_adapter.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False, advanced=True)

    assert result.conforms is False
    assert any(
        from_engine(o) == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )
    assert any(from_engine(o) == Literal("A") for _, _, o in result.report_graph.triples((None, SH.value, None)))


def test_validate_reification_required_conforms_when_reifier_exists() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_validate_reifier_shape_violation_when_reifier_does_not_conform() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:value "A" {| ex:source ex:Somewhere |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is False
    assert any(
        from_engine(o) == SH.ReifierShapeConstraintComponent
        for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    )


def test_validate_reifier_shape_conforms_when_reifier_conforms() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:alice ex:value "A" {| ex:date "2019-12-05"^^xsd:date |} .
        """,
        format="turtle12",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:value ;
                sh:reifierShape ex:ProvenanceShape ;
              ] .

            ex:ProvenanceShape a sh:NodeShape ;
              sh:property [
                sh:path ex:date ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False)

    assert result.conforms is True


def test_validate_hard_fails_when_reification_path_is_not_simple_iri() -> None:
    data = StarLayerGraph()
    data.add((EX.alice, EX.value, Literal("A")))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            ex:ReificationShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path [ sh:inversePath ex:value ] ;
                sh:reificationRequired true ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    with pytest.raises(ShapeError, match="IRI path"):
        _ = validator.validate(data_graph=data, meta_shacl=False)


def test_apply_rules_evaluates_shnex_filter_shape_in_a_rule() -> None:
    # shnex:filterShape keeps only the nodes that conform to the shape: only ex:bob
    # (a genuine ex:Adult) is filtered in, excluding ex:carol.
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:alice ex:knows ex:bob, ex:carol .
            ex:bob a ex:Adult .
        """,
        format="turtle",
    )

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .

            ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .

            ex:FilterExprShape a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:rule [
                a sh:TripleRule ;
                sh:subject [ shnex:var "focusNode" ] ;
                sh:predicate ex:derivedAdultFriends ;
                sh:object [ shnex:filterShape ex:AdultShape ; shnex:nodes [ shnex:pathValues ex:knows ] ] ;
              ] .
        """,
        format="turtle",
    )

    validator = StarShaclSchema(shacl_graph=shapes)
    result = validator.apply_rules(data_graph=data, meta_shacl=False)

    derived = {from_engine(o) for _, _, o in result.inferred_graph.triples((EX.alice, EX.derivedAdultFriends, None))}
    assert derived == {EX.bob}




class TestBoundDataGraphAndInference:
    """2026-10-08: StarShaclSchema gained two new constructor-only
    parameters - data_graph (an optional default every processing
    method's own data_graph parameter now falls back to) and inference
    (moved here from a per-method inference= keyword every processing
    method used to take individually). Together these let a caller
    construct one schema and call several different methods against the
    same data without repeating it, and without repeating an entailment
    regime either."""

    def _shapes(self) -> StarLayerGraph:
        g = StarLayerGraph()
        g.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:PersonShape a sh:NodeShape ;
                    sh:targetClass ex:Person ;
                    sh:property [ sh:path ex:name ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        return g

    def _data(self, name_present: bool) -> StarLayerGraph:
        g = StarLayerGraph()
        triples = "ex:alice a ex:Person ." + (' ex:alice ex:name "Alice" .' if name_present else "")
        g.parse(data=f"@prefix ex: <http://example.org/> . {triples}", format="turtle")
        return g

    def test_validate_uses_bound_data_graph_when_omitted(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        assert schema.validate().conforms is True

    def test_target_nodes_uses_bound_data_graph_when_omitted(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        assert tuple(from_engine(n) for n in schema.target_nodes(shape_node=EX.PersonShape)) == (EX.alice,)

    def test_per_call_data_graph_overrides_the_bound_default(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        assert schema.validate(self._data(name_present=False)).conforms is False
        # the bound default is untouched - a later call with no argument
        # still uses it, not whatever was last passed explicitly.
        assert schema.validate().conforms is True

    def test_multiple_methods_share_one_bound_data_graph(self) -> None:
        """The motivating use case: construct once, call several
        different processing methods, none of them repeating data_graph."""
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        assert schema.validate().conforms is True
        assert tuple(from_engine(n) for n in schema.target_nodes(shape_node=EX.PersonShape)) == (EX.alice,)
        assert schema.evaluate() is not None
        assert schema.apply_rules().validation.conforms is True

    def test_no_data_graph_anywhere_raises_a_clear_error(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes())
        with pytest.raises(ValueError, match="No data_graph given"):
            schema.validate()

    def test_inference_bound_at_construction_feeds_validate(self) -> None:
        from starlayer.graph.graph.entailment_regimes import ENTAILMENT

        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:worksAt rdfs:domain ex:Person .
                ex:alice ex:worksAt ex:Acme .
            """,
            format="turtle",
        )
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=data, inference=ENTAILMENT.RDFS)
        # ex:alice only becomes a target of PersonShape via RDFS domain
        # inference, and then fails it (no ex:name) - without inference
        # bound at construction, this would trivially conform instead.
        assert schema.validate().conforms is False

    def test_inference_passed_per_call_raises_type_error(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        with pytest.raises(TypeError, match="inference"):
            schema.validate(inference=None)
        with pytest.raises(TypeError):
            schema.evaluate(inference=None)
        with pytest.raises(TypeError):
            schema.target_nodes(shape_node=EX.PersonShape, inference=None)

    def test_validate_each_falls_back_to_bound_data_graph(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._shapes(), data_graph=self._data(name_present=True))
        results = schema.validate_each()
        assert results[0].conforms is True




class TestInputsAndHelpers:
    """Behaviour of the public entry points that does not depend on the engine's internals."""

    SHAPES = (
        "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
    )

    def _graph(self, ttl: str) -> StarLayerGraph:
        g = StarLayerGraph()
        g.parse(data=ttl, format="turtle12")
        return g

    def test_apply_rules_rejects_a_data_graph_that_is_not_a_starlayer_graph(self) -> None:
        from starlayer.shacl import apply_rules

        with pytest.raises(TypeError, match=r"data_graph must be an OxGraph"):
            apply_rules(((EX.s, EX.p, EX.o),))

    def test_the_schema_rejects_inference_per_call(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._graph(self.SHAPES))
        with pytest.raises(TypeError, match="no longer accepts inference"):
            schema.validate(data_graph=self._graph("@prefix ex: <http://example.org/> ."), inference="x")

    def test_target_nodes_reads_the_shapes_from_the_data_graph_when_there_are_none(self) -> None:
        from starlayer.shacl import target_nodes

        both = self._graph(self.SHAPES + " ex:alice a ex:Person .")
        assert tuple(from_engine(n) for n in target_nodes(data_graph=both, shape_node=EX.S)) == (EX.alice,)

    def test_the_schema_resolves_target_nodes_over_its_bound_shapes(self) -> None:
        schema = StarShaclSchema(shacl_graph=self._graph(self.SHAPES))
        data = self._graph("@prefix ex: <http://example.org/> . ex:alice a ex:Person . ex:bob a ex:Person .")
        assert {from_engine(n) for n in schema.target_nodes(data_graph=data, shape_node=EX.S)} == {EX.alice, EX.bob}

    def test_inplace_adds_the_inferred_triples_to_the_callers_graph(self) -> None:
        shapes = self._graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:R . "
            "ex:R a sh:SPARQLRule ; sh:construct 'CONSTRUCT { $this <http://example.org/seen> true } WHERE { }' ."
        )
        data = self._graph("@prefix ex: <http://example.org/> . ex:alice a ex:Person .")
        result = validate(data, shapes, mode="rules", meta_shacl=False)
        assert result.data_graph is data
        assert (EX.alice, EX.seen, Literal(True)) in data

    def test_apply_rules_stops_a_runaway_rule_at_max_iterations(self) -> None:
        from starlayer.shacl import RuleError, apply_rules

        shapes = self._graph(
            "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
            "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:next ; sh:rule ex:R . "
            "ex:R a sh:SPARQLRule ; sh:construct 'CONSTRUCT { ?o <http://example.org/next> <http://example.org/z> } "
            "WHERE { $this <http://example.org/next> ?o }' ."
        )
        data = self._graph("@prefix ex: <http://example.org/> . ex:a ex:next ex:b . ex:b ex:next ex:c . ex:c ex:next ex:d .")
        with pytest.raises(RuleError, match="fixpoint"):
            apply_rules(data, shapes, max_iterations=1)
