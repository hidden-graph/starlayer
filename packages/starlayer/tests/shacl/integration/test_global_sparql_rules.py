""""Global" (shape-independent) sh:SPARQLRule (SHACL 1.2): a rule node that
exists standalone, never referenced by any shape's own sh:rule property,
meant to execute once against the whole graph regardless of shape targeting.
Found missing entirely via the W3C SHACL 1.2 test suite's global-symmetric
fixture - pySHACL's own gather_rules() only discovers rules reachable via
some shape's sh:rule, so a standalone rule node is invisible to it and
silently never executes.
"""

import pytest
from rdflib import Namespace
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl import StarShaclSchema

EX = Namespace("http://example.org/")

pyshacl = pytest.importorskip("pyshacl")


def test_global_rule_runs_once_against_whole_graph() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:SymmetricPropertyRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { ?o ?p ?s . }
                WHERE { ?p a ex:SymmetricProperty . ?s ?p ?o . }
              \"\"\" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:friend a ex:SymmetricProperty .
            ex:Bob ex:friend ex:Caren .
            ex:Caren ex:friend ex:Debbie .
        """,
        format="turtle",
    )

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)

    assert (EX.Caren, EX.friend, EX.Bob) in result.inferred_graph
    assert (EX.Debbie, EX.friend, EX.Caren) in result.inferred_graph


def test_global_rule_discovered_from_data_graph_itself_when_shacl_graph_is_none() -> None:
    """2026-10-08: shacl_graph=None falls back to data_graph itself as the
    rules source - this is the one case the earlier fallback fix actually
    mattered for (not just convenience): a shape-attached sh:rule already
    ran correctly with shacl_graph=None even before the fix, since pySHACL
    discovers it internally via the data graph's own embedded shapes, but
    a *global*, shape-independent SPARQLRule like this one is found only
    by this module's own normalized_shapes-driven discovery - which used
    to stay None (and thus skip global-rule discovery entirely) whenever
    shacl_graph was omitted."""
    data_with_embedded_rule = StarLayerGraph()
    data_with_embedded_rule.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:SymmetricPropertyRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { ?o ?p ?s . }
                WHERE { ?p a ex:SymmetricProperty . ?s ?p ?o . }
              \"\"\" .
            ex:friend a ex:SymmetricProperty .
            ex:Bob ex:friend ex:Caren .
            ex:Caren ex:friend ex:Debbie .
        """,
        format="turtle",
    )

    result = StarShaclSchema().apply_rules(data_graph=data_with_embedded_rule, meta_shacl=False)

    assert (EX.Caren, EX.friend, EX.Bob) in result.inferred_graph
    assert (EX.Debbie, EX.friend, EX.Caren) in result.inferred_graph


def test_global_rule_deactivated_produces_nothing() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:SymmetricPropertyRule a sh:SPARQLRule ;
              sh:deactivated true ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { ?o ?p ?s . }
                WHERE { ?p a ex:SymmetricProperty . ?s ?p ?o . }
              \"\"\" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:friend a ex:SymmetricProperty .
            ex:Bob ex:friend ex:Caren .
        """,
        format="turtle",
    )

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)

    assert (EX.Caren, EX.friend, EX.Bob) not in result.inferred_graph


def test_shape_attached_rule_still_works_alongside_a_global_one() -> None:
    """Confirms this fix doesn't interfere with pySHACL's own normal,
    shape-attached sh:rule execution - both should apply independently.
    """
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:GlobalRule a sh:SPARQLRule ;
              sh:construct \"\"\"
                PREFIX ex: <http://example.org/>
                CONSTRUCT { ?o ex:reverseFriend ?s . }
                WHERE { ?s ex:friend ?o . }
              \"\"\" .
            ex:S a sh:NodeShape ; sh:targetNode ex:Alice ;
              sh:rule [
                a sh:SPARQLRule ;
                sh:construct \"\"\"
                    PREFIX ex: <http://example.org/>
                    CONSTRUCT { $this ex:greeted "hi" . }
                    WHERE { }
                \"\"\" ;
              ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:Alice ex:friend ex:Bob .
        """,
        format="turtle",
    )

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data, meta_shacl=False)

    assert (EX.Bob, EX.reverseFriend, EX.Alice) in result.inferred_graph
    from rdflib import Literal

    assert (EX.Alice, EX.greeted, Literal("hi")) in result.inferred_graph
