import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import StarLayerGraph
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import StarShaclProcessor
from tests.support.terms import NamedNode, Namespace, lit

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
# SHACL 1.2 Core: a shapes graph can cross-reference reusable modules via
# owl:imports, optionally redirected through owl:versionIRI so a versioned
# module can declare its own canonical (unversioned) IRI for the purpose of
# following *its* further owl:imports statements. These tests mirror the
# spec's own worked example (myapp -> company/v2 -[owl:versionIRI]-> company
# -> base) using an in-memory graph_loader, since starlayer.shacl delegates actual
# retrieval policy to the caller rather than fetching URLs itself.

MYAPP = NamedNode("http://example.com/shapes/myapp")
COMPANY_V2 = NamedNode("http://example.com/shapes/company/v2")
COMPANY = NamedNode("http://example.com/shapes/company")
BASE = NamedNode("http://example.com/shapes/base")


def _myapp_shapes() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            <http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/company/v2> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [
                sh:path ex:worksFor ;
                sh:class ex:Company ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _company_v2_graph() -> Graph:
    graph = Graph()
    graph.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            <http://example.com/shapes/company> owl:versionIRI <http://example.com/shapes/company/v2> ;
              owl:imports <http://example.com/shapes/base> .

            ex:CompanyShape a sh:NodeShape ;
              sh:targetClass ex:Company ;
              sh:property [
                sh:path ex:name ;
                sh:minCount 1 ;
                sh:datatype xsd:string ;
              ] .
        """,
        format="turtle",
    )
    return graph


def _base_graph() -> Graph:
    graph = Graph()
    graph.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            <http://example.com/shapes/base> a owl:Ontology .
            ex:BaseShape a sh:NodeShape ;
              sh:targetClass ex:Thing ;
              sh:property [
                sh:path ex:id ;
                sh:minCount 1 ;
              ] .
        """,
        format="turtle",
    )
    return graph


_GRAPHS_BY_IRI = {
    COMPANY_V2: _company_v2_graph,
    BASE: _base_graph,
}


def _loader(iri):
    factory = _GRAPHS_BY_IRI.get(iri)  # the loader is handed a pyoxigraph NamedNode
    return factory() if factory else None


def test_transitive_import_closure_with_version_iri_redirect_enforces_imported_constraints() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Acme a ex:Company .
            ex:Bob a ex:Person ; ex:worksFor ex:Acme .
        """,
        format="turtle",
    )

    validator = StarShaclProcessor(shacl_graph=_myapp_shapes())
    result = validator.validate(
        data_graph=data,
        meta_shacl=False,
        shapes_graph_loader=_loader,
    )

    # ex:Acme is missing ex:name (required by the imported CompanyShape, two
    # import hops away via the versionIRI redirect), so the closure must
    # have actually been merged in for this to fail.
    assert result.conforms is False
    components = {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))}
    assert SH.MinCountConstraintComponent in components


def test_without_loader_or_ignore_imports_raises() -> None:
    """2026-10-08: validate() used to silently proceed with owl:imports
    left unresolved, so a shape referencing something only defined in the
    unresolved import would simply never fire - no indication anything
    was skipped. Now raises by default instead, since that silent
    incompleteness is a real risk, not hypothetical (see the test below
    for exactly the case this was protecting against)."""
    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> .\nex:Bob a ex:Person .", format="turtle")

    validator = StarShaclProcessor(shacl_graph=_myapp_shapes())

    with pytest.raises(ExecutionError, match="owl:imports") as caught:
        validator.validate(data_graph=data, meta_shacl=False)
    assert caught.value.kind == "import"
    assert caught.value.unresolved == (COMPANY_V2,)


def test_ignore_imports_true_restores_the_old_silent_pass_through() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Acme a ex:Company .
            ex:Bob a ex:Person ; ex:worksFor ex:Acme .
        """,
        format="turtle",
    )

    validator = StarShaclProcessor(shacl_graph=_myapp_shapes())
    result = validator.validate(data_graph=data, meta_shacl=False, ignore_imports=True)

    # Explicitly opted out of resolving: the imported CompanyShape's
    # sh:minCount on ex:name never gets merged in, so Acme's missing
    # ex:name is invisible - same behavior the old default used to give
    # unconditionally, now only when asked for.
    assert result.conforms is True


def test_bare_validate_function_raises_too() -> None:
    """Same check, same message, in the module-level validate() - a
    separate implementation from the method, not one delegating to the
    other (see starlayer/shacl/CLAUDE.md's "two-step flip" note), so both
    needed the identical fix."""
    from starlayer.shacl import validate

    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> .\nex:Bob a ex:Person .", format="turtle")

    with pytest.raises(ExecutionError, match="owl:imports") as caught:
        validate(data, _myapp_shapes(), meta_shacl=False)
    assert caught.value.kind == "import"


def test_pre_resolved_imports_are_satisfied_without_a_loader() -> None:
    """The two-call pattern: the caller resolves the imports into the shapes graph first. The ``owl:imports`` triples stay in the
    graph (a true fact about the document), but each imported IRI is now a subject (or the ``owl:versionIRI`` of a present ontology), so
    ``validate()`` has nothing left to resolve and needs neither a loader nor ``ignore_imports``."""
    pre_resolved = _myapp_shapes().resolve_imports(loader=_loader, mode="full")
    assert COMPANY_V2 in {i for i in pre_resolved.owl_imports()}

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Acme a ex:Company .
            ex:Bob a ex:Person ; ex:worksFor ex:Acme .
        """,
        format="turtle",
    )

    validator = StarShaclProcessor(shacl_graph=pre_resolved)
    assert validator.validate(data_graph=data, meta_shacl=False).conforms is False  # the merged CompanyShape catches Acme
    assert validator.validate(data_graph=data, meta_shacl=False, ignore_imports=True).conforms is False


def test_unresolvable_import_raises_even_with_a_loader() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            <http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/does-not-exist> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [ sh:path ex:name ; sh:minCount 1 ; ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> .\nex:Bob a ex:Person .", format="turtle")

    with pytest.raises(ExecutionError) as caught:  # a loader that returns None: not satisfied (the processor says so when it is built)
        StarShaclProcessor(shacl_graph=shapes, shapes_graph_loader=lambda iri: None)
    assert caught.value.kind == "import"
    assert [i.value for i in caught.value.unresolved] == ["http://example.com/shapes/does-not-exist"]
    # ignore_imports=True: nothing is loaded or checked, Bob is still missing ex:name per the local shape
    validator = StarShaclProcessor(shacl_graph=shapes)
    assert validator.validate(data_graph=data, meta_shacl=False, ignore_imports=True).conforms is False


def test_self_importing_graph_does_not_infinite_loop() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            <http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/myapp> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [ sh:path ex:name ; sh:minCount 1 ; ] .
        """,
        format="turtle",
    )

    def loader(iri):
        graph = Graph()
        graph.parse(
            data="""
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                <http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/myapp> .
            """,
            format="turtle",
        )
        return graph

    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> .\nex:Bob a ex:Person ; ex:name \"Bob\" .", format="turtle")

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(data_graph=data, meta_shacl=False, shapes_graph_loader=loader)

    assert result.conforms is True


def test_multi_hop_import_chain_without_any_version_iri_redirect() -> None:
    """Every existing multi-hop test above goes through the ``owl:versionIRI``
    redirect at its second hop, so ``_resolve_shapes_graph_imports``'s
    fallback branch (``canonical_id = target_iri`` when the imported graph
    declares no ``owl:versionIRI`` pointing back at the IRI it was fetched
    as) was never actually exercised - this chain (``myapp -> mid -> base``)
    has no ``owl:versionIRI`` triple anywhere, so ``mid``'s own
    ``owl:imports base`` is only found by looking it up under the plain
    fetched IRI itself.
    """
    mid_iri = NamedNode("http://example.com/shapes/mid")

    def loader(iri):
        iri = iri  # the loader is handed a pyoxigraph NamedNode
        if iri == mid_iri:
            graph = Graph()
            graph.parse(
                data="""
                    @prefix owl: <http://www.w3.org/2002/07/owl#> .
                    @prefix sh: <http://www.w3.org/ns/shacl#> .
                    @prefix ex: <http://example.org/> .

                    <http://example.com/shapes/mid> owl:imports <http://example.com/shapes/base> .

                    ex:CompanyShape a sh:NodeShape ;
                      sh:targetClass ex:Company ;
                      sh:property [ sh:path ex:name ; sh:minCount 1 ; ] .
                """,
                format="turtle",
            )
            return graph
        if iri == BASE:
            return _base_graph()
        return None

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

            <http://example.com/shapes/myapp> owl:imports <http://example.com/shapes/mid> .

            ex:PersonShape a sh:NodeShape ;
              sh:targetClass ex:Person ;
              sh:property [ sh:path ex:worksFor ; sh:class ex:Company ; ] .
        """,
        format="turtle",
    )

    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Acme a ex:Company, ex:Thing ; ex:name "Acme Corp" .
            ex:Bob a ex:Person ; ex:worksFor ex:Acme .
        """,
        format="turtle",
    )

    validator = StarShaclProcessor(shacl_graph=shapes)
    result = validator.validate(
        data_graph=data, meta_shacl=False, shapes_graph_loader=loader
    )

    # ex:Acme already satisfies mid's own CompanyShape (has ex:name) - the
    # only possible violation is base's BaseShape (targetClass ex:Thing,
    # requires ex:id), which is reachable only via mid's own owl:imports
    # base, resolved through the no-versionIRI fallback branch. If that
    # fallback were broken, base would never be fetched and this would
    # conform (false pass), same failure mode as the happy-path test above.
    assert result.conforms is False
    violations = list(result.report_graph.triples((None, SH.resultPath, EX.id)))
    assert len(violations) == 1


def test_imports_already_co_located_in_shacl_graph_need_no_loader_and_do_not_raise() -> None:
    """2026-10-08: owl:imports isn't only used for genuinely external
    references needing a loader - two shapes-graph "modules" that import
    each other are often just loaded together into one single graph,
    with nothing external to fetch. Found as a real false-positive risk
    via direct testing, not hypothetical: without has_import_locally(),
    this would incorrectly raise (nothing was ever actually missing)."""
    from tests.support.terms import OWL, RDF

    shapes = StarLayerGraph()
    shapes.add((EX.ModuleA, OWL.imports, EX.ModuleB))
    shapes.add((EX.ModuleA, RDF.type, SH.ShapesGraph))
    shapes.add((EX.PersonShape, RDF.type, SH.NodeShape))
    shapes.add((EX.PersonShape, SH.targetClass, EX.Person))
    shapes.add((EX.PersonShape, SH.property, EX.NameProp))
    shapes.add((EX.NameProp, SH.path, EX.name))
    shapes.add((EX.NameProp, SH.minCount, lit(1)))

    # ModuleB is already co-located right here too - a different "module"
    # declaring its own shape, not fetched from anywhere.
    shapes.add((EX.ModuleB, RDF.type, SH.ShapesGraph))
    shapes.add((EX.CompanyShape, RDF.type, SH.NodeShape))
    shapes.add((EX.CompanyShape, SH.targetClass, EX.Company))
    shapes.add((EX.CompanyShape, SH.property, EX.NameProp2))
    shapes.add((EX.NameProp2, SH.path, EX.name))
    shapes.add((EX.NameProp2, SH.minCount, lit(1)))

    data = StarLayerGraph()
    data.parse(
        data="@prefix ex: <http://example.org/> .\nex:bob a ex:Person .\nex:acme a ex:Company .",
        format="turtle",
    )

    validator = StarShaclProcessor(shacl_graph=shapes)
    # No shapes_graph_loader, no ignore_imports - must not raise, since
    # ModuleB's own content is already right here in shapes.
    result = validator.validate(data_graph=data, meta_shacl=False)

    # ex:acme is missing ex:name, caught by ModuleB's own co-located
    # CompanyShape - proof the shape actually applied, not just that
    # validate() happened not to crash.
    assert result.conforms is False


# --- the one import rule (decision 2026-11-26) on the other SHACL paths ---

_PERSON_DATA = "@prefix ex: <http://example.org/> .\nex:Bob a ex:Person ."


def _data() -> StarLayerGraph:
    return StarLayerGraph().parse(data=_PERSON_DATA, format="turtle")


def test_a_loader_that_raises_is_wrapped_with_the_original_as_cause() -> None:
    def broken(iri):
        raise OSError("no such file")

    with pytest.raises(ExecutionError, match="no such file") as caught:
        StarShaclProcessor(shacl_graph=_myapp_shapes()).validate(data_graph=_data(), meta_shacl=False, shapes_graph_loader=broken)
    assert caught.value.kind == "import" and isinstance(caught.value.__cause__, OSError)
    assert caught.value.unresolved == (COMPANY_V2,)


def test_the_application_reads_unresolved_imports_and_validates_again_with_a_loader_that_knows_more() -> None:
    from starlayer.graph import unresolved_imports

    shapes = _myapp_shapes()
    with pytest.raises(ExecutionError) as caught:
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_data(), meta_shacl=False)
    assert caught.value.unresolved == unresolved_imports(shapes) == (COMPANY_V2,)
    assert StarShaclProcessor(shacl_graph=shapes).validate(data_graph=_data(), meta_shacl=False, shapes_graph_loader=_loader).conforms


def test_the_imports_of_the_ontology_graph_are_resolved_or_raise() -> None:
    from starlayer.shacl import validate

    shapes = StarLayerGraph().parse(data="@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . ex:S a sh:NodeShape ; sh:targetClass ex:Person .", format="turtle")
    ont = StarLayerGraph()
    ont.add((NamedNode("http://example.org/ont"), NamedNode("http://www.w3.org/2002/07/owl#imports"), NamedNode("http://example.org/ont-lib")))
    with pytest.raises(ExecutionError) as caught:
        validate(_data(), shapes, ont_graph=ont, meta_shacl=False)
    assert caught.value.kind == "import" and [i.value for i in caught.value.unresolved] == ["http://example.org/ont-lib"]
    assert validate(_data(), shapes, ont_graph=ont, meta_shacl=False, ignore_imports=True).conforms


def test_apply_rules_and_validate_each_resolve_or_raise_too() -> None:
    from starlayer.graph import StarLayerDataset
    from starlayer.shacl import apply_rules

    with pytest.raises(ExecutionError) as caught:
        apply_rules(_data(), _myapp_shapes())
    assert caught.value.kind == "import"
    dataset = StarLayerDataset()
    dataset.add_graph(NamedNode("http://example.org/g1")).extend(list(_data().triples()))
    with pytest.raises(ExecutionError):
        StarShaclProcessor(shacl_graph=_myapp_shapes()).validate_each(dataset)

