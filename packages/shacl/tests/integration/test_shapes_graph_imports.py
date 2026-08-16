import pytest
from rdflib import Graph, Namespace, URIRef
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Core: a shapes graph can cross-reference reusable modules via
# owl:imports, optionally redirected through owl:versionIRI so a versioned
# module can declare its own canonical (unversioned) IRI for the purpose of
# following *its* further owl:imports statements. These tests mirror the
# spec's own worked example (myapp -> company/v2 -[owl:versionIRI]-> company
# -> base) using an in-memory graph_loader, since starshacl delegates actual
# retrieval policy to the caller rather than fetching URLs itself.

MYAPP = URIRef("http://example.com/shapes/myapp")
COMPANY_V2 = URIRef("http://example.com/shapes/company/v2")
COMPANY = URIRef("http://example.com/shapes/company")
BASE = URIRef("http://example.com/shapes/base")


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
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://example.org/> .

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
    factory = _GRAPHS_BY_IRI.get(iri)
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

    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=data,
        shacl_graph=_myapp_shapes(),
        meta_shacl=False,
        shapes_graph_loader=_loader,
    )

    # ex:Acme is missing ex:name (required by the imported CompanyShape, two
    # import hops away via the versionIRI redirect), so the closure must
    # have actually been merged in for this to fail.
    assert result.conforms is False
    components = {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))}
    assert SH.MinCountConstraintComponent in components


def test_without_loader_imports_are_left_unresolved() -> None:
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Acme a ex:Company .
            ex:Bob a ex:Person ; ex:worksFor ex:Acme .
        """,
        format="turtle",
    )

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=_myapp_shapes(), meta_shacl=False)

    # No shapes_graph_loader given: the imported CompanyShape's sh:minCount
    # on ex:name never gets merged in, so Acme's missing ex:name is invisible.
    assert result.conforms is True


def test_unresolvable_import_is_skipped_not_raised() -> None:
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

    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=data, shacl_graph=shapes, meta_shacl=False, shapes_graph_loader=lambda iri: None
    )

    assert result.conforms is False  # Bob is still missing ex:name per the local shape


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

    validator = StarShaclValidator()
    result = validator.validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, shapes_graph_loader=loader)

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
    mid_iri = URIRef("http://example.com/shapes/mid")

    def loader(iri):
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

    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=data, shacl_graph=shapes, meta_shacl=False, shapes_graph_loader=loader
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
