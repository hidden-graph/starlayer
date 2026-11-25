"""The meta check (``meta_validate()`` / ``meta_shacl=True``) reports an invalid ``sh:pattern`` or ``sh:flags`` as a result of ``stsh:RegexShape`` (the layer
``shacl_shacl_starlayer``, which calls ``stsh:regexProblem``), and the verdict is the engine's own regex compile: the check flags exactly the values for which the
engine raises ``ShapeError``. SPARQL's REGEX disagrees with the engine on valid patterns (``a**``, ``(?<n>a)``, ``a{,3}``, ``\\p{IsBasicLatin}``), so the shape
asks a function instead."""

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaShaclError, ShapeError, StarShaclProcessor
from starlayer.shacl.meta_shapes import meta_validate

SH = "http://www.w3.org/ns/shacl#"
SHAPE = ox.NamedNode("https://github.com/hidden-graph/starlayer/ns/shacl#RegexShape")
PREFIXES = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .\n"

PATTERNS = [
    "a", "^a+$", "(", ")", "[", "]", "[a-z", "a**", "a{,3}", "a{3}", "a{3,", "a{2,1}", "(?<n>a)", "(?:a)", "(?=a)", "*a", "+", "?",
    r"\p{IsBasicLatin}", r"\p{Foo}", r"\p{L}", r"\i\c*", r"[a-z-[aeiou]]", r"\d+", r"\q", "a|", "|", "(a", "a{99999999999}",
]


def _lit(value: str) -> str:
    return ox.Literal(value).__str__()  # str-ok: test turtle


def _graph(body: str) -> Graph:
    graph = Graph()
    graph.parse(data=PREFIXES + body, format="turtle")
    return graph


def _one(pattern: str, flags: str | None = None) -> Graph:
    extra = f" ; sh:flags {_lit(flags)}" if flags is not None else ""
    return _graph(f"ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern {_lit(pattern)}{extra} ] .")


def _engine_rejects(shapes: Graph) -> bool:
    try:
        StarShaclProcessor(shacl_graph=shapes)
    except ShapeError:
        return True
    return False


def _error(shapes: Graph) -> MetaShaclError | None:
    try:
        meta_validate(shapes)
    except MetaShaclError as error:
        return error
    return None


def _regex_results(report: Graph) -> list[dict]:
    out = []
    for result in report.subjects(ox.NamedNode(SH + "sourceShape"), SHAPE):
        out.append({name: next(iter(report.objects(result, ox.NamedNode(SH + name))), None)
                    for name in ("focusNode", "resultPath", "resultMessage", "resultSeverity")})
    return out


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("flags", [None, "i", "x", "q"])
def test_meta_check_flags_exactly_what_the_engine_rejects(pattern, flags):
    shapes = _one(pattern, flags)
    error = _error(shapes)
    assert (error is not None) == _engine_rejects(shapes)
    assert (error is not None) == bool(error and _regex_results(error.report_graph))


def test_the_table_has_valid_and_invalid_patterns():
    rejected = [p for p in PATTERNS if _engine_rejects(_one(p))]
    assert 0 < len(rejected) < len(PATTERNS)
    assert len(PATTERNS) == 29


@pytest.mark.parametrize("flags", ["z", "ii2", "S", " "])
def test_a_bad_flag_is_reported_on_sh_flags(flags):
    shapes = _one("a", flags)
    assert _engine_rejects(shapes)
    error = _error(shapes)
    (result,) = _regex_results(error.report_graph)
    assert result["resultPath"] == ox.NamedNode(SH + "flags")
    assert "invalid sh:flags" in result["resultMessage"].value


def test_result_in_the_report_graph_and_in_problems():
    error = _error(_one("("))
    (result,) = _regex_results(error.report_graph)
    # like any result, the report carries the description of a blank focus node (the engine copies it so a tool can show the node), and nothing else of the shapes
    assert set(error.report_graph.subjects(ox.NamedNode(SH + "pattern"), None)) == {result["focusNode"]}
    assert isinstance(result["focusNode"], ox.BlankNode)
    assert result["resultPath"] == ox.NamedNode(SH + "pattern")
    assert result["resultSeverity"] == ox.NamedNode(SH + "Violation")
    assert "invalid sh:pattern '('" in result["resultMessage"].value
    assert "unterminated subpattern" in result["resultMessage"].value
    assert error.problems == (f"the property shape of ex:S for ex:p, sh:pattern: {result['resultMessage'].value}",)
    assert "Conforms: False" in error.report_text
    assert result["resultMessage"].value in error.report_text
    report = next(iter(error.report_graph.subjects(ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), ox.NamedNode(SH + "ValidationReport"))))
    assert next(iter(error.report_graph.objects(report, ox.NamedNode(SH + "conforms")))).value == "false"


def test_the_flags_of_the_same_node_are_used():
    """``(`` is a literal with ``q``, and a pattern with a space is valid with ``x`` flags alike; only the node's own flags decide."""
    assert _error(_one("(", "q")) is None
    assert _error(_one("(")) is not None
    assert _error(_one("a**", "q")) is None


def test_a_valid_pattern_gives_no_result():
    assert meta_validate(_one(r"^[a-z]+\d*$", "i")).conforms is True


def test_the_result_is_an_ordinary_sparql_constraint_result():
    error = _error(_one("("))
    report = error.report_graph
    (result,) = report.subjects(ox.NamedNode(SH + "sourceShape"), SHAPE)
    assert (result, ox.NamedNode(SH + "sourceConstraintComponent"), ox.NamedNode(SH + "SPARQLConstraintComponent")) in set(report.triples((result, None, None)))


@pytest.mark.parametrize("body", [
    'ex:S a sh:NodeShape ; sh:and ( [ sh:pattern "(" ] ) .',
    'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern "(" ] .',
    'ex:S a sh:NodeShape ; sh:node [ sh:pattern "(" ] .',
    'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:node [ sh:property [ sh:path ex:q ; sh:pattern "(" ] ] ] .',
])
def test_a_pattern_in_a_nested_shape_is_found(body):
    error = _error(_graph(body))
    assert error is not None
    assert len(_regex_results(error.report_graph)) == 1
    assert len(error.problems) == 1


def test_meta_shacl_on_a_processor_raises_meta_shacl_error():
    with pytest.raises(MetaShaclError, match="invalid sh:pattern '\\('"):
        StarShaclProcessor(shacl_graph=_one("("), meta_shacl=True)
