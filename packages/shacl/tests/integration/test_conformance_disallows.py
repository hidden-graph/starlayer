import pytest
from rdflib import Literal, Namespace

from starshacl import StarShaclValidator
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# SHACL 1.2 Core adds sh:conformanceDisallows to the validation report: the
# set of severities whose presence makes sh:conforms false, defaulting to
# {sh:Violation, sh:Warning, sh:Info} if the report doesn't state one.
# pySHACL's allow_warnings/allow_infos options already implement the
# underlying behavior (confirmed directly: a Warning-only result already
# flips sh:conforms to false by default) - this only makes the actual set it
# used explicit in the report.


def _shapes_with_warning_severity() -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:age ;
                sh:datatype xsd:integer ;
                sh:severity sh:Warning ;
              ] .
        """,
        format="turtle",
    )
    return shapes


def _data_with_bad_age() -> StarLayerGraph:
    data = StarLayerGraph()
    data.add((EX.alice, EX.age, Literal("not a number")))
    return data


def test_default_conformance_disallows_includes_all_three_severities() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_with_bad_age(), shacl_graph=_shapes_with_warning_severity(), meta_shacl=False
    )

    disallowed = {o for _, _, o in result.report_graph.triples((None, SH.conformanceDisallows, None))}
    assert disallowed == {SH.Violation, SH.Warning, SH.Info}


def test_default_conforms_is_false_for_warning_only_result() -> None:
    # A Warning-severity-only result flips sh:conforms to false by default,
    # matching the spec's default disallow set including sh:Warning.
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_with_bad_age(), shacl_graph=_shapes_with_warning_severity(), meta_shacl=False
    )

    assert result.conforms is False


def test_allow_warnings_removes_warning_from_disallowed_set_and_conforms() -> None:
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_with_bad_age(),
        shacl_graph=_shapes_with_warning_severity(),
        meta_shacl=False,
        allow_warnings=True,
    )

    disallowed = {o for _, _, o in result.report_graph.triples((None, SH.conformanceDisallows, None))}
    assert disallowed == {SH.Violation, SH.Info}
    assert result.conforms is True


def _shapes_with_severity(severity: str) -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(
        data=f"""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ;
              sh:targetNode ex:alice ;
              sh:property [
                sh:path ex:age ;
                sh:datatype xsd:integer ;
                sh:severity sh:{severity} ;
              ] .
        """,
        format="turtle",
    )
    return shapes


@pytest.mark.parametrize("severity", ["Debug", "Trace"])
def test_debug_and_trace_severities_never_block_conforms(severity: str) -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's severity-004/
    severity-005 fixtures: sh:Debug and sh:Trace are SHACL 1.2 Core's two
    new severity levels, below sh:Warning - unlike sh:Warning/sh:Info
    (which block sh:conforms *by default*, only excluded via
    allow_warnings/allow_infos), sh:Debug/sh:Trace must never block
    sh:conforms at all, unconditionally - regardless of any flag, since
    pySHACL doesn't know they exist and so never puts them in the "allowed"
    exception set the way it does for sh:Info/sh:Warning. The violation
    itself must still be reported (present in sh:result, with the correct
    sh:resultSeverity) - only the aggregate sh:conforms is affected.
    """
    validator = StarShaclValidator()
    result = validator.validate(
        data_graph=_data_with_bad_age(), shacl_graph=_shapes_with_severity(severity), meta_shacl=False
    )

    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH[severity]}
