"""sh:values (SHACL 1.2 Core): a property shape's own effective value set
computed via sh:select/sh:sparqlExpr instead of read from the data graph via
sh:path - every other constraint on that shape (sh:datatype, sh:hasValue,
etc.) then runs unmodified against the computed values. Found missing
entirely via the W3C SHACL 1.2 test suite's property-select-001/
property-sparqlExpr-001 fixtures - pySHACL has no notion of this predicate
at all.

Distinct from sh:PropertyRule's own, unrelated "new sh:values" mechanism
(a sh:rule shorthand for *constructing* new triples during apply_rules(),
still not implemented - see tests/integration/test_rule_condition.py's
test_property_rule_sh_values_is_not_implemented) - these two features are
coincidentally both named sh:values but serve entirely different purposes.
"""

import pytest
from rdflib import Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayer_graph import StarLayerGraph

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def test_values_select_computes_the_checked_value_set() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:Person-fullName a sh:PropertyShape ;
              sh:targetClass ex:Person ;
              sh:path ex:fullName ;
              sh:values [
                sh:select "SELECT ?fullName WHERE { $this ex:firstName ?first ; ex:lastName ?last . BIND (CONCAT(?first, \\" \\", ?last) AS ?fullName) . }"
              ] ;
              sh:datatype xsd:string ;
              sh:hasValue "John Muir" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:JohnMuir a ex:Person ; ex:firstName "John" ; ex:lastName "Muir" .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is True


def test_values_select_violates_when_computed_value_does_not_match() -> None:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Person-fullName a sh:PropertyShape ;
              sh:targetClass ex:Person ;
              sh:path ex:fullName ;
              sh:values [
                sh:select "SELECT ?fullName WHERE { $this ex:firstName ?first ; ex:lastName ?last . BIND (CONCAT(?first, \\" \\", ?last) AS ?fullName) . }"
              ] ;
              sh:hasValue "John Muir" .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(
        data="""
            @prefix ex: <http://example.org/> .
            ex:JaneDoe a ex:Person ; ex:firstName "Jane" ; ex:lastName "Doe" .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert SH.HasValueConstraintComponent in {
        o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
    }


def test_values_sparql_expr_computes_a_single_scalar_value() -> None:
    # len("http://example.org/") == 19, so ex:Fiver (5-char local name) is
    # exactly 24 characters total, and ex:Big (3-char local name) is 22 -
    # chosen precisely so the expected pass/violate split is checkable by
    # inspection, not by running STRLEN by hand.
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:Resource-uriLength a sh:PropertyShape ;
              sh:targetNode ex:Fiver, ex:Big ;
              sh:path ex:uriLength ;
              sh:values [ sh:sparqlExpr "STRLEN(STR($this))" ] ;
              sh:datatype xsd:integer ;
              sh:hasValue 24 .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.Fiver, EX.dummy, EX.dummy))
    data.add((EX.Big, EX.dummy, EX.dummy))

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

    assert result.conforms is False
    assert {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))} == {EX.Big}


def test_property_rule_sh_values_remains_a_separate_unimplemented_mechanism() -> None:
    """Sanity check that this fix didn't accidentally touch sh:PropertyRule's
    own, unrelated sh:values mechanism (still correctly unimplemented - see
    tests/integration/test_rule_condition.py's own dedicated test).
    """
    from pyshacl.errors import RuleLoadError

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
              sh:rule [ a sh:PropertyRule ; sh:path ex:computed ; sh:values ex:alice ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.add((EX.alice, EX.dummy, EX.dummy))

    with pytest.raises(RuleLoadError):
        StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=False)
