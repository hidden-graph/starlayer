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

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.Caren, EX.friend, EX.Bob) in result.data_graph
    assert (EX.Debbie, EX.friend, EX.Caren) in result.data_graph


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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.Caren, EX.friend, EX.Bob) not in result.data_graph


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

    result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert (EX.Bob, EX.reverseFriend, EX.Alice) in result.data_graph
    from rdflib import Literal

    assert (EX.Alice, EX.greeted, Literal("hi")) in result.data_graph
