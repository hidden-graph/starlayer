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
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

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


class TestDefaultValueFallback:
    """sh:defaultValue: the third step of SHACL 1.2 Core's own "Value Nodes
    of Property Shapes" algorithm - "if the set is still empty and d is the
    value of sh:defaultValue ..., then add the output nodes of
    evalExpr(d, ...)" - the only one of the three steps that's conditional.

    Found missing entirely (2026-09-09) by trying to write a notebook demo
    for it: this file's own module docstring, and
    ``_patch_shape_value_nodes_for_sh_values``'s docstring in validator.py,
    both already quoted this exact three-step algorithm - but the patch
    itself only ever implemented steps 1 and 2 (path values, sh:values),
    never step 3. A live check (a property shape with sh:defaultValue and
    sh:hasValue matching it, and no stored value at all) confirmed
    validate() reported a violation instead of conforming - a real,
    previously-undetected gap between the documented algorithm and the
    actual code, not merely an absent example.
    """

    def test_default_value_fills_in_when_no_real_value_is_stored(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
                  sh:property [ sh:path ex:status ; sh:defaultValue "active" ; sh:hasValue "active" ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.add((EX.alice, EX.dummy, EX.dummy))

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

        assert result.conforms is True
        # The fallback is a validation-time virtual value only - never
        # materialized as a real triple in the caller's own data graph.
        assert list(data.triples((None, EX.status, None))) == []

    def test_default_value_is_ignored_once_a_real_value_exists(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
                  sh:property [ sh:path ex:status ; sh:defaultValue "active" ; sh:hasValue "active" ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.parse(data='@prefix ex: <http://example.org/> . ex:bob ex:status "suspended" .', format="turtle")

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

        # bob's real, stored "suspended" is what's checked - the default
        # "active" never gets a chance to paper over it.
        assert result.conforms is False

    def test_default_value_is_ignored_once_sh_values_computes_something(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
                ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
                  sh:property [ sh:path ex:friendCount ; sh:datatype xsd:integer ;
                                sh:values [ sh:sparqlExpr "1 + 1" ] ;
                                sh:defaultValue 999 ; sh:hasValue 2 ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.add((EX.alice, EX.dummy, EX.dummy))

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

        # sh:values already produced 2 (a non-empty set), so step 3 never
        # runs - the shape conforms via the computed value, not the default.
        assert result.conforms is True

    def test_default_value_alone_with_no_sh_values_at_all_still_falls_back(self) -> None:
        """The gate must trigger on sh:defaultValue alone, not just when
        sh:values is also present - a plain property shape carrying only
        sh:defaultValue (the common, simpler case) needs the same fallback.
        """
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
                  sh:property [ sh:path ex:role ; sh:defaultValue "guest" ; sh:hasValue "guest" ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.add((EX.alice, EX.dummy, EX.dummy))

        result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)

        assert result.conforms is True


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
