"""The report graph is written when it is first read (or in the call, with ``build="graph"``), is the same either way, and never reads the
shapes or the data graph after the call."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph.compare import isomorphic
from starlayer.shacl import StarShaclProcessor, apply_rules
from starlayer.shacl import validate as public_validate
from starlayer.shacl.engine import api
from starlayer.shacl.engine.api import validate as engine_validate
from starlayer.shacl.engine.terms import SH
from starlayer.shacl.results import ValidationReport

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
SHAPES = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:age ; sh:datatype xsd:integer ] ; "
    "sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:severity sh:Warning ] ."
)
DATA = 'ex:a a ex:C ; ex:age "x" . [ a ex:C ; ex:age "y" ; ex:note [ ex:deep "z" ] ] .'


def graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + ttl, format="turtle")
    return g


@pytest.fixture
def writes(monkeypatch) -> list:
    """The report graphs written so far (the engine's ``write_report`` is counted)."""
    done: list = []
    original = api.write_report
    monkeypatch.setattr(api, "write_report", lambda content: done.append(original(content)) or done[-1])
    return done


def test_the_graph_is_written_on_first_read_and_only_once(writes) -> None:
    outcome = engine_validate(graph(DATA), graph(SHAPES))
    assert writes == []
    first = outcome.report_graph
    assert len(writes) == 1 and outcome.report_graph is first and len(writes) == 1


def test_the_results_and_conforms_need_no_graph(writes) -> None:
    outcome = engine_validate(graph(DATA), graph(SHAPES))
    assert outcome.conforms is False and len(outcome.results) == 4
    assert writes == []


@pytest.mark.parametrize("build", ["graph", "text"])
def test_build_writes_the_graph_in_the_call(writes, build: str) -> None:
    outcome = engine_validate(graph(DATA), graph(SHAPES), build=build)
    assert len(writes) == 1
    assert (outcome._report_text is not None) == (build == "text")


def test_an_unknown_build_is_refused() -> None:
    with pytest.raises(ValueError, match="build must be"):
        engine_validate(graph(DATA), graph(SHAPES), build="everything")


def test_a_graph_written_later_is_the_one_written_in_the_call() -> None:
    lazy = engine_validate(graph(DATA), graph(SHAPES), include_used_configuration=True, data_graph_iri="http://example.org/d", shapes_graph_iri="http://example.org/s")
    eager = engine_validate(graph(DATA), graph(SHAPES), include_used_configuration=True, data_graph_iri="http://example.org/d", shapes_graph_iri="http://example.org/s", build="graph")
    assert len(lazy.report_graph) == len(eager.report_graph) > 20
    assert isomorphic(lazy.report_graph, eager.report_graph)


def test_a_graph_written_later_does_not_read_the_graphs_again() -> None:
    """The data graph and the shapes graph are emptied after the call; the graph written then is the one written in the call (the blank focus
    nodes' closures are in it)."""
    expected = engine_validate(graph(DATA), graph(SHAPES), build="graph").report_graph
    data, shapes = graph(DATA), graph(SHAPES)
    outcome = engine_validate(data, shapes)
    data.remove((None, None, None))
    shapes.remove((None, None, None))
    late = outcome.report_graph
    assert len(late) == len(expected) > 20 and isomorphic(late, expected)


def test_the_prefixes_are_those_at_the_call() -> None:
    data = graph(DATA)
    data.bind("zz", "http://example.org/zz#")
    outcome = engine_validate(data, graph(SHAPES))
    data.bind("zz", "http://example.org/changed#", override=True)
    assert dict(outcome.report_graph.namespaces())["zz"] == "http://example.org/zz#"


def test_the_public_report_is_lazy_and_the_conformance_floor_is_in_the_graph_when_it_is_written(monkeypatch) -> None:
    done: list = []
    original = api.write_report
    monkeypatch.setattr(api, "write_report", lambda content: done.append(1) or original(content))
    report = public_validate(graph(DATA), graph(SHAPES))
    assert done == [] and report.conforms is False
    written = report.report_graph
    assert len(done) == 1 and report.report_graph is written
    top = next(iter(written.subjects(None, SH.ValidationReport)))
    assert (top, SH.conformanceDisallows, SH.Violation) in written and (top, SH.conformanceDisallows, SH.Warning) in written
    eager = public_validate(graph(DATA), graph(SHAPES), build="graph")
    assert isomorphic(written, eager.report_graph)


def test_the_public_build_options(writes, monkeypatch) -> None:
    texts: list = []
    from starlayer.shacl.engine import text as text_module

    original = text_module.report_text
    monkeypatch.setattr(text_module, "report_text", lambda *a, **k: texts.append(1) or original(*a, **k))
    public_validate(graph(DATA), graph(SHAPES))
    assert writes == [] and texts == []
    public_validate(graph(DATA), graph(SHAPES), build="graph")
    assert len(writes) == 1 and texts == []
    public_validate(graph(DATA), graph(SHAPES), build="text")
    assert len(writes) == 2 and len(texts) == 1
    StarShaclProcessor(shacl_graph=graph(SHAPES)).validate(graph(DATA), build="graph")
    assert len(writes) == 3
    with pytest.raises(ValueError, match="build must be"):
        public_validate(graph(DATA), graph(SHAPES), build="x")


def test_apply_rules_does_not_take_build() -> None:
    with pytest.raises(TypeError, match="validate"):
        apply_rules(graph(DATA), graph(SHAPES), build="graph")


def test_diagnostics_count_the_graph_and_write_it() -> None:
    report = public_validate(graph(DATA), graph(SHAPES))
    assert callable(report._diagnostics)
    assert report.diagnostics.report_triples == len(report.report_graph)


def test_a_report_takes_the_graph_and_the_diagnostics_as_values_or_functions() -> None:
    built = []
    lazy = ValidationReport(True, lambda: built.append(1) or StarLayerGraph(), "t", None, lambda: None)
    assert built == [] and lazy.report_graph is lazy.report_graph and built == [1]
    plain = ValidationReport(True, {"a": 1}, "t")
    assert plain.report_graph == {"a": 1}


# The meta check: the report graph of a shapes graph that conforms is never asked for, so it is never written.
OK_SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."
BAD_SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:minCount 1 ] ."


def test_a_shapes_graph_that_conforms_is_checked_without_writing_a_report_graph(writes) -> None:
    from starlayer.shacl import meta_validate

    report = meta_validate(graph(OK_SHAPES))
    assert report.conforms is True and writes == []
    written = report.report_graph
    assert len(writes) == 1 and report.report_graph is written and len(written) > 0
    assert report.diagnostics.report_triples == len(written)


def test_the_error_for_a_shapes_graph_that_does_not_conform_carries_its_report_graph(writes) -> None:
    from starlayer.errors import MetaShaclError
    from starlayer.shacl import meta_validate

    with pytest.raises(MetaShaclError) as error:
        meta_validate(graph(BAD_SHAPES))
    assert len(writes) == 1 and any(error.value.report_graph.subjects(None, SH.ValidationResult))
    assert error.value.problems and "Conforms: False" in error.value.report_text


def test_the_scoped_meta_check_is_lazy_too(writes) -> None:
    from starlayer.shacl import meta_scope, meta_validate
    from starlayer.shacl.engine.terms import boolean

    shapes = graph(OK_SHAPES)
    added = [(ox.NamedNode("http://example.org/S"), SH.deactivated, boolean(True))]
    assert meta_scope(shapes, add=added).nodes
    assert meta_validate(shapes, add=added).conforms is True and writes == []
