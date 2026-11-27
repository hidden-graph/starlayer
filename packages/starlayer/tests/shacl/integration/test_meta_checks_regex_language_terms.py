"""The meta check (``meta_validate()`` / ``meta_shacl=True``) rejects a malformed ``sh:languageIn`` range and warns about an unknown
term in the SHACL namespace. Both are shapes in the shapes-for-shapes, so they come back as ordinary ``sh:ValidationResult``s.

The ``sh:pattern`` check is the engine's own compile, not a shape: see ``test_meta_regex_check.py``."""

import re

import pyoxigraph as ox
from starlayer.errors import only_kind
import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import ShapeError
from starlayer.shacl.meta_shapes import meta_validate

SH = "http://www.w3.org/ns/shacl#"
PREFIXES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix shui: <http://www.w3.org/ns/shacl-ui/> .\n"
)
RANGE_MESSAGE = "language range"


def _graph(ttl: str) -> Graph:
    graph = Graph()
    graph.parse(data=PREFIXES + ttl, format="turtle")
    return graph


def _lang_shapes(members: str) -> Graph:
    return _graph(f"ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:languageIn ( {members} ) ] .")


def _deactivate(shape_iri: str) -> Graph:
    return _graph(f"<{shape_iri}> sh:deactivated true .")


def _problems(shapes: Graph, **kwargs) -> tuple[str, ...]:
    try:
        meta_validate(shapes, **kwargs)
    except ShapeError as error:
        only_kind(error, "meta")
        return error.problems
    return ()


def _results(shapes: Graph, **kwargs):
    """The (severity, focus, value, message) of every result of the check, from the report graph."""
    try:
        report = meta_validate(shapes, **kwargs).report_graph
    except ShapeError as error:
        only_kind(error, "meta")
        report = error.report_graph
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

    def one(result, name):
        return next(iter(report.objects(result, ox.NamedNode(SH + name))), None)

    return [(one(r, "resultSeverity"), one(r, "focusNode"), one(r, "value"), one(r, "resultMessage"))
            for r in report.subjects(rdf_type, ox.NamedNode(SH + "ValidationResult"))]


# --- sh:languageIn members -----------------------------------------------------------------------------------------------

LANGUAGE_SHAPE = "https://github.com/hidden-graph/starlayer/ns/shacl#LanguageRangeShape"


@pytest.mark.parametrize("member", ['"en"', '"*"', '"de-CH"', '"zh-Hant-TW"', '"en-x-private1"', '"EN"', '"abcdefgh"'])
def test_language_range_accepted(member):
    assert not _problems(_lang_shapes(member))


@pytest.mark.parametrize("member", ['"e n"', '"-x"', '"en-"', '"1a"', '"toolongsub"', '"en--US"', '"en-toolongsub1"', '""', '"*-CH"', '"en_US"'])
def test_language_range_rejected(member):
    problems = _problems(_lang_shapes(member))
    assert any(RANGE_MESSAGE in line for line in problems), problems


def test_language_range_non_string_member_rejected():
    assert _problems(_lang_shapes("5")), "a number is not a language range"
    assert _problems(_lang_shapes("ex:en")), "an IRI is not a language range"


def test_language_range_check_is_what_rejects_it():
    """Without the new shape the base accepts a malformed string, so the rejection above is its work."""
    shapes = _lang_shapes('"e n"')
    assert _problems(shapes)
    assert not _problems(shapes, meta_shapes_extra=[_deactivate(LANGUAGE_SHAPE)])


def test_language_range_violation_is_in_the_report_text():
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta") as raised:
        meta_validate(_lang_shapes('"e n"'))
    assert RANGE_MESSAGE in raised.value.report_text
    assert "Violation" in raised.value.report_text


def test_unique_lang_must_be_boolean():
    bad = _graph('ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:uniqueLang "yes" ] .')
    assert any("xsd:boolean" in line for line in _problems(bad))
    assert not _problems(_graph("ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:uniqueLang true ] ."))


# --- unknown terms in the SHACL namespace --------------------------------------------------------------------------------

UNKNOWN = "https://github.com/hidden-graph/starlayer/ns/shacl#UnknownShaclTermShape"


def _terms_results(shapes: Graph):
    return [r for r in _results(shapes) if "is not a term of the SHACL vocabulary" in str(r[3])]


def _local(node) -> str:
    return node.value[len(SH):]


def test_unknown_predicate_object_and_type_are_each_reported_once():
    shapes = _graph(
        "ex:S a sh:NodeShape ; sh:minCountt 1 ; sh:nodeKind sh:Iri ; sh:property ex:P .\n"
        "ex:P a sh:Shape2 ; sh:path ex:p ."
    )
    found = {(_local(value), focus.value.rsplit("/", 1)[-1]) for _sev, focus, value, _msg in _terms_results(shapes)}
    assert found == {("minCountt", "S"), ("Iri", "S"), ("Shape2", "P")}
    assert len(_terms_results(shapes)) == 3


def test_unknown_term_result_shape():
    shapes = _graph("ex:S a sh:NodeShape ; sh:minCountt 1 .")
    ((severity, focus, value, message),) = _terms_results(shapes)
    assert severity == ox.NamedNode(SH + "Warning")
    assert focus == ox.NamedNode("http://example.org/S")
    assert value == ox.NamedNode(SH + "minCountt")
    assert message.value == "sh:minCountt is not a term of the SHACL vocabulary"


def test_unknown_object_inside_a_list_is_reported_on_the_list_node():
    shapes = _graph("ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:in ( ex:a sh:Bogus ) ] .")
    ((_sev, focus, value, _msg),) = _terms_results(shapes)
    assert _local(value) == "Bogus"
    assert isinstance(focus, ox.BlankNode)


@pytest.mark.parametrize("ttl", [
    "ex:S a sh:NodeShape ; ex:foo 1 ; ex:bar ex:baz .",
    "ex:S a sh:NodeShape ; shnex:pathValues ex:p ; shui:order 1 .",
    "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; shui:editor shui:TextFieldEditor ] .",
    "ex:S a sh:NodeShape ; sh:nodeKind sh:IRI ; sh:severity sh:Info ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .",
])
def test_other_namespaces_and_known_terms_are_not_reported(ttl):
    assert not _terms_results(_graph(ttl))


def test_a_subject_in_the_shacl_namespace_is_not_checked():
    assert not _terms_results(_graph("sh:Local a sh:NodeShape ; sh:targetClass ex:C ."))


def test_unknown_term_is_a_warning_and_a_warning_makes_the_shapes_graph_invalid():
    shapes = _graph("ex:S a sh:NodeShape ; sh:minCountt 1 .")
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):
        meta_validate(shapes)
    assert _problems(shapes) == ("Warning: ex:S: sh:minCountt is not a term of the SHACL vocabulary",)


def test_unknown_term_check_is_what_reports_it():
    shapes = _graph("ex:S a sh:NodeShape ; sh:minCountt 1 .")
    assert _problems(shapes)
    assert not _problems(shapes, meta_shapes_extra=[_deactivate(UNKNOWN)])


def test_list_in_the_shape_is_the_shipped_vocabulary():
    """The list of known terms is written by the build from the vocabulary; a test fails if the stored shape and the shipped
    ``shacl_vocabulary`` graph drift apart."""
    meta = starontology.get_ontology_graph("shacl_shacl")
    shape = ox.NamedNode(UNKNOWN)
    (sparql,) = meta.objects(shape, ox.NamedNode(SH + "sparql"))
    (select,) = meta.objects(sparql, ox.NamedNode(SH + "select"))
    listed = set(re.findall(r"<(http://www\.w3\.org/ns/shacl#[^>]*)>", select.value))
    vocabulary = starontology.get_ontology_graph("shacl_vocabulary")
    defined = {s.value for s, _p, _o in vocabulary.triples((None, None, None)) if isinstance(s, ox.NamedNode) and s.value.startswith(SH)}
    assert listed == defined
    assert len(defined) > 250


def test_shipped_vocabulary_and_rules_graphs_have_no_unknown_term():
    known = {s.value for s, _p, _o in starontology.get_ontology_graph("shacl_vocabulary").triples((None, None, None)) if isinstance(s, ox.NamedNode)}
    for name in ("shacl_shacl", "shacl_shacl_ui", "shacl_ui_baseline", "shacl_shacl_ui_scores"):
        graph = starontology.get_ontology_graph(name)
        unknown = {
            t.value for s, p, o in graph.triples((None, None, None)) for t in (p, o)
            if isinstance(t, ox.NamedNode) and t.value.startswith(SH) and t.value not in known
        }
        assert not unknown, (name, unknown)
