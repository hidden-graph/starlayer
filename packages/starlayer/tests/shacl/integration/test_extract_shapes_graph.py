"""Coverage for StarShaclSchema.extract_shapes_graph() - pulls one named
sh:ShapesGraph "module" back out of a larger shacl_graph that bundles
several modules together (the inverse of SHACL 1.2 Profiling S2's own
packaging convention). Built on StarLayerGraph.cbd() - see that method's
own docstring for the Concise Bounded Description algorithm this relies
on (follows blank-node objects recursively, never named-IRI ones).
"""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema, extract_subgraph

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")

pyshacl = pytest.importorskip("pyshacl")


def _two_module_graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:ModuleA a sh:ShapesGraph ; rdfs:member ex:PersonShape .
            ex:PersonShape a sh:NodeShape ;
                sh:targetClass ex:Person ;
                sh:property [ sh:path ex:name ; sh:minCount 1 ] .

            ex:ModuleB a sh:ShapesGraph ; rdfs:member ex:CompanyShape .
            ex:CompanyShape a sh:NodeShape ;
                sh:targetClass ex:Company ;
                sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    return g


def test_extracts_only_the_named_modules_own_shape() -> None:
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    extracted = schema.extract_shapes_graph(EX.ModuleB)

    assert extracted is not None
    assert (EX.CompanyShape, None, None) in [(s, p, o) for s, p, o in [(s, p, o) for s, p, o in extracted]] or any(
        True for _ in extracted.triples((EX.CompanyShape, None, None))
    )
    assert not any(True for _ in extracted.triples((EX.PersonShape, None, None)))


def test_extracted_module_includes_the_shapesgraph_and_member_triples() -> None:
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    extracted = schema.extract_shapes_graph(EX.ModuleB)

    assert (EX.ModuleB, RDFS.member, EX.CompanyShape) in extracted
    assert (EX.CompanyShape, SH.targetClass, EX.Company) in extracted


def test_nested_blank_node_property_shape_is_included() -> None:
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    extracted = schema.extract_shapes_graph(EX.ModuleB)

    prop_nodes = list(extracted.objects(EX.CompanyShape, SH.property))
    assert len(prop_nodes) == 1
    assert (prop_nodes[0], SH.path, EX.name) in extracted
    assert (prop_nodes[0], SH.minCount, None) in extracted or any(
        True for _ in extracted.triples((prop_nodes[0], SH.minCount, None))
    )


def _adult_shapes_graph() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            ex:AdultShapesGraph a sh:ShapesGraph ;
                rdfs:member ex:AdultShape .

            ex:AdultShape a sh:NodeShape ;
                sh:targetClass ex:Adult ;
                sh:property ex:AdultAgeShape .

            ex:AdultAgeShape a sh:PropertyShape ;
                sh:path ex:age ;
                sh:datatype xsd:integer ;
                sh:minInclusive 18 .
        """,
        format="turtle",
    )
    return g


def test_named_nested_property_shape_is_left_dangling_by_design() -> None:
    """A member shape's own sh:property can point at a *named* property
    shape (not a blank node) - extract_shapes_graph() deliberately does
    NOT recurse into it (CBD alone won't follow a named-IRI object
    either). SHACL 1.2 Profiling itself gives no completeness rule for
    this (confirmed directly against the spec text - S2.7 "Calculating
    Dependencies" is a literal TODO), so there's no closure to compute;
    leaving the reference dangling is what lets a caller extract one
    shape and then inject their own replacement for whatever it points
    at, without a stale copy of the old definition silently riding
    along and conflicting with the injected one."""
    schema = StarShaclSchema(shacl_graph=_adult_shapes_graph())
    extracted = schema.extract_shapes_graph(EX.AdultShapesGraph)

    assert (EX.AdultShape, SH.property, EX.AdultAgeShape) in extracted
    assert not any(True for _ in extracted.triples((EX.AdultAgeShape, None, None)))


def test_caller_can_inject_a_replacement_for_a_dangling_named_shape_reference() -> None:
    """The actual motivating workflow: extract one shape, then inject a
    *different* definition for a named shape it references - the point
    of leaving that reference dangling rather than auto-closing it."""
    schema = StarShaclSchema(shacl_graph=_adult_shapes_graph())
    extracted = schema.extract_shapes_graph(EX.AdultShapesGraph)

    # inject a stricter replacement AdultAgeShape (minInclusive 21, not 18) -
    # if the old definition had been dragged along too, this would leave two
    # conflicting sh:minInclusive triples on the same shape instead of one
    extracted.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:AdultAgeShape a sh:PropertyShape ;
                sh:path ex:age ;
                sh:datatype xsd:integer ;
                sh:minInclusive 21 .
        """,
        format="turtle",
    )
    assert len(list(extracted.triples((EX.AdultAgeShape, SH.minInclusive, None)))) == 1

    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:bob a ex:Adult ; ex:age 19 .", format="turtle")
    result = StarShaclSchema(shacl_graph=extracted).validate(data_graph=data, meta_shacl=False)
    assert result.conforms is False  # 19 < 21, the injected replacement constraint, not the original 18


def test_extracted_module_validates_independently() -> None:
    """The extracted module is a genuine, standalone, usable shapes graph
    - not just a bag of triples that happens to look right."""
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    extracted = schema.extract_shapes_graph(EX.ModuleB)

    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:acme a ex:Company .", format="turtle")

    result = StarShaclSchema(shacl_graph=extracted).validate(data_graph=data, meta_shacl=False)
    assert result.conforms is False  # missing ex:name, caught by the extracted CompanyShape


def test_returns_none_for_an_iri_not_typed_sh_shapesgraph() -> None:
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    # PersonShape exists, but isn't itself typed a sh:ShapesGraph.
    assert schema.extract_shapes_graph(EX.PersonShape) is None


def test_returns_none_for_an_unknown_iri() -> None:
    schema = StarShaclSchema(shacl_graph=_two_module_graph())
    assert schema.extract_shapes_graph(EX.NotRegistered) is None


def test_raises_without_a_bound_shacl_graph() -> None:
    schema = StarShaclSchema()
    with pytest.raises(ValueError, match="extract_shapes_graph"):
        schema.extract_shapes_graph(EX.ModuleA)


def test_does_not_mutate_the_original_shacl_graph() -> None:
    original = _two_module_graph()
    before = set(original)
    StarShaclSchema(shacl_graph=original).extract_shapes_graph(EX.ModuleB)
    assert set(original) == before


def test_owl_imports_to_a_module_absent_entirely_raises() -> None:
    """extract_shapes_graph() takes no loader= and only ever chases an
    import that's already a sh:ShapesGraph node co-located in the same
    shacl_graph (see the owl:imports-transitive-membership tests below) -
    but unlike the dangling-member case elsewhere in this file, an
    unresolvable owl:imports target is treated as an error (2026-10-09),
    not silently skipped: a sh:ShapesGraph declaring owl:imports is
    asserting a real dependency on another packaging module. An import
    target with zero triples describing it anywhere in shacl_graph raises -
    call resolve_imports(loader=...) first if it genuinely needs fetching
    from elsewhere."""
    from rdflib.namespace import OWL

    g = _two_module_graph()
    g.add((EX.ModuleB, OWL.imports, EX.SomeOtherModule))

    schema = StarShaclSchema(shacl_graph=g)
    with pytest.raises(ValueError, match="SomeOtherModule"):
        schema.extract_shapes_graph(EX.ModuleB)


def test_owl_imports_to_a_module_present_but_not_typed_shapesgraph_raises() -> None:
    """The same strict check applies even when the imported IRI has real
    content in shacl_graph - just not a sh:ShapesGraph type declaration -
    not only when it's entirely absent. Presence alone isn't enough; it
    has to actually be typed a sh:ShapesGraph to count."""
    from rdflib.namespace import OWL, RDF

    g = _two_module_graph()
    g.add((EX.ModuleB, OWL.imports, EX.SomeOtherModule))
    g.add((EX.SomeOtherModule, RDFS.member, EX.SomeShape))
    g.add((EX.SomeShape, RDF.type, SH.NodeShape))

    schema = StarShaclSchema(shacl_graph=g)
    with pytest.raises(ValueError, match="SomeOtherModule"):
        schema.extract_shapes_graph(EX.ModuleB)


def test_rdfs_isdefinedby_inverse_direction_is_honored() -> None:
    """A shape can declare itself part of a ShapesGraph via the inverse
    rdfs:isDefinedBy relationship, instead of (or alongside) the
    ShapesGraph declaring it via rdfs:member - both are real SHACL 1.2
    Profiling S2 packaging mechanisms."""
    g = StarLayerGraph()
    g.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:ModuleC a sh:ShapesGraph .
            ex:WidgetShape a sh:NodeShape ;
                rdfs:isDefinedBy ex:ModuleC ;
                sh:targetClass ex:Widget ;
                sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        """,
        format="turtle",
    )

    schema = StarShaclSchema(shacl_graph=g)
    extracted = schema.extract_shapes_graph(EX.ModuleC)

    assert extracted is not None
    assert (EX.WidgetShape, RDFS.isDefinedBy, EX.ModuleC) in extracted
    assert (EX.WidgetShape, SH.targetClass, EX.Widget) in extracted
    prop_nodes = list(extracted.objects(EX.WidgetShape, SH.property))
    assert len(prop_nodes) == 1
    assert (prop_nodes[0], SH.path, EX.name) in extracted


def test_owl_imports_transitively_pulls_in_another_locally_present_modules_members() -> None:
    """If ModuleA owl:imports ModuleB, and both are already co-located in
    the same shacl_graph, ModuleB's own members count as part of
    ModuleA's extracted module too - the third documented mechanism."""
    from rdflib.namespace import OWL

    g = _two_module_graph()
    g.add((EX.ModuleA, OWL.imports, EX.ModuleB))

    schema = StarShaclSchema(shacl_graph=g)
    extracted = schema.extract_shapes_graph(EX.ModuleA)

    assert (EX.ModuleA, OWL.imports, EX.ModuleB) in extracted
    assert (EX.ModuleA, RDFS.member, EX.PersonShape) in extracted
    assert (EX.ModuleB, RDFS.member, EX.CompanyShape) in extracted
    assert (EX.PersonShape, SH.targetClass, EX.Person) in extracted
    assert (EX.CompanyShape, SH.targetClass, EX.Company) in extracted


def test_owl_imports_cycle_does_not_hang() -> None:
    """ModuleA and ModuleB importing each other must terminate, not loop
    forever chasing the same pair of nodes back and forth."""
    from rdflib.namespace import OWL

    g = _two_module_graph()
    g.add((EX.ModuleA, OWL.imports, EX.ModuleB))
    g.add((EX.ModuleB, OWL.imports, EX.ModuleA))

    schema = StarShaclSchema(shacl_graph=g)
    extracted = schema.extract_shapes_graph(EX.ModuleA)

    assert (EX.PersonShape, SH.targetClass, EX.Person) in extracted
    assert (EX.CompanyShape, SH.targetClass, EX.Company) in extracted


class TestValidateShapesGraph:
    """StarShaclSchema.validate(shapes_graph_resource=...) - one parameter, two
    possible meanings depending on what's actually true of this
    instance's own bound shacl_graph (2026-10-10, replacing the former
    separate shapes_graph_module=/shapes_graph_iri= pair - see CLAUDE.md's
    dated entry for why keeping them independently settable was a real
    correctness gap, not just a naming one):

    - If shapes_graph names a real `a sh:ShapesGraph` module within the
      bound shacl_graph: that module is what gets validated against
      (a convenience wrapping extract_shapes_graph() + validate()
      together), and its own IRI becomes the report's sh:usedShapesGraph
      identity - there's only one fact here, so there's no second,
      separately-overridable value for it.
    - Otherwise, once a real shacl_graph is bound: shapes_graph is read
      purely as a report-provenance identity (the old shapes_graph_iri=
      behavior) and validation proceeds against the whole bound
      shacl_graph unchanged.
    - With no bound shacl_graph at all: raises - there's no evidence
      either way about what shapes_graph should mean, and silently
      falling back to "just a tag" would let the report claim
      sh:usedShapesGraph for a run that validated against nothing at all
      (pyshacl trivially "conforms" against a None shapes graph)."""

    def test_validates_against_only_the_named_module(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())

        acme = StarLayerGraph()
        acme.parse(data="@prefix ex: <http://example.org/> . ex:acme a ex:Company .", format="turtle")

        # ex:acme has no ex:name - fails CompanyShape's own sh:minCount 1,
        # but ModuleA's PersonShape (a different module) never applies
        result = schema.validate(data_graph=acme, meta_shacl=False, shapes_graph_resource=EX.ModuleB)
        assert result.conforms is False

    def test_conforms_when_the_module_alone_is_satisfied(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())

        acme = StarLayerGraph()
        acme.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )

        result = schema.validate(data_graph=acme, meta_shacl=False, shapes_graph_resource=EX.ModuleB)
        assert result.conforms is True

    def test_falls_back_to_tag_only_for_an_iri_not_typed_sh_shapesgraph(self) -> None:
        """Not a module within the bound shacl_graph - validated against
        the whole thing instead (empty data, so trivially conforms), with
        the given IRI used purely as the report's own identity. This used
        to raise ("not typed a sh:ShapesGraph") before the
        shapes_graph_iri= unification - a real shacl_graph being bound
        makes "this must be an external identity" a safe inference now,
        not a guess."""
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        data = StarLayerGraph()
        result = schema.validate(data_graph=data, meta_shacl=False, shapes_graph_resource=EX.NotRegistered)
        assert result.conforms is True
        assert (None, SH.usedShapesGraph, EX.NotRegistered) in result.report_graph

    def test_raises_without_a_bound_shacl_graph(self) -> None:
        """Unlike the "not a real module" case above, no bound shacl_graph
        at all leaves no evidence either way about what shapes_graph_resource=
        should mean - still raises, since pyshacl trivially "conforms"
        against a None shapes graph and a silent tag-only fallback here
        would let the report falsely claim a module was used."""
        schema = StarShaclSchema()
        data = StarLayerGraph()
        with pytest.raises(ValueError, match="shapes_graph_resource="):
            schema.validate(data_graph=data, meta_shacl=False, shapes_graph_resource=EX.ModuleB)

    def test_does_not_mutate_or_replace_the_bound_shacl_graph(self) -> None:
        original = _two_module_graph()
        schema = StarShaclSchema(shacl_graph=original)
        before = set(original)

        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:acme a ex:Company .", format="turtle")
        schema.validate(data_graph=data, meta_shacl=False, shapes_graph_resource=EX.ModuleB)

        assert schema.shacl_graph is original
        assert set(original) == before

    def test_module_selection_is_the_reports_own_identity(self) -> None:
        """shapes_graph_resource= naming a real module directly becomes the
        report's sh:usedShapesGraph identity - not a separate value that
        happens to default to it, since there's only one fact here to
        report in the first place."""
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        acme = StarLayerGraph()
        acme.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )

        result = schema.validate(data_graph=acme, meta_shacl=False, shapes_graph_resource=EX.ModuleB)
        used = list(result.report_graph.triples((None, SH.usedShapesGraph, None)))
        assert len(used) == 1
        assert used[0][2] == EX.ModuleB


class TestShapesGraphOnOtherMethods:
    """shapes_graph_resource= (renamed from shapes_graph_module= 2026-10-10)
    extended consistently (2026-10-09) to every other StarShaclSchema
    method that takes a shapes graph - a thin convenience over
    _resolve_shacl_graph(), the same helper TestValidateShapesGraph above
    exercises through validate(). Unlike validate()'s own dual-purpose
    shapes_graph_resource=, these methods have no report to fall back to tagging -
    a value that isn't really a module still raises here, via
    _resolve_shacl_graph()."""

    def test_target_nodes_scoped_to_one_module(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:acme a ex:Company .", format="turtle")

        nodes = schema.target_nodes(data_graph=data, shape_node=EX.CompanyShape, shapes_graph_resource=EX.ModuleB)
        assert nodes == (EX.acme,)

    def test_evaluate_scoped_to_one_module(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )

        result = schema.evaluate(data_graph=data, shapes_graph_resource=EX.ModuleB)
        assert (EX.acme, EX.name, None) in result or any(True for _ in result.triples((EX.acme, EX.name, None)))

    def test_extract_subgraph_scoped_to_one_module(self) -> None:
        """extract_subgraph() is a plain function, not a StarShaclSchema
        method, so it has no shapes_graph_resource= of its own - scoping to
        one module is two explicit calls instead: extract_shapes_graph()
        pulls the module out, then the bare function is given it directly
        as shacl_graph=. Nothing is lost, it's just no longer a single
        convenience call."""
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )

        module_b = schema.extract_shapes_graph(EX.ModuleB)
        extracted = extract_subgraph(data, shacl_graph=module_b, shape=EX.CompanyShape, focus_node=EX.acme)
        assert len(extracted) > 0
        assert (EX.acme, EX.name, None) in extracted or any(True for _ in extracted.triples((EX.acme, EX.name, None)))

    def test_apply_rules_scoped_to_one_module(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        data = StarLayerGraph()
        data.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )

        result = schema.apply_rules(data_graph=data, shapes_graph_resource=EX.ModuleB)
        assert result.validation.conforms is True

    def test_close_shape_scoped_to_one_module(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        closed = schema.close_shape(EX.CompanyShape, shapes_graph_resource=EX.ModuleB)
        assert (EX.CompanyShape, SH.closed, None) in closed or any(
            True for _ in closed.triples((EX.CompanyShape, SH.closed, None))
        )

    def test_validate_each_forwards_shapes_graph_via_kwargs(self) -> None:
        schema = StarShaclSchema(shacl_graph=_two_module_graph())
        conforming = StarLayerGraph()
        conforming.parse(
            data='@prefix ex: <http://example.org/> . ex:acme a ex:Company ; ex:name "Acme" .', format="turtle"
        )
        missing_name = StarLayerGraph()
        missing_name.parse(data="@prefix ex: <http://example.org/> . ex:other a ex:Company .", format="turtle")

        results = schema.validate_each(
            data_graphs=(conforming, missing_name), meta_shacl=False, shapes_graph_resource=EX.ModuleB
        )
        assert results[0].conforms is True
        assert results[1].conforms is False
