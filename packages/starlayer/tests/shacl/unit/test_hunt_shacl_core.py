"""Regression tests from the SHACL engine constraint-component bug hunt."""

from __future__ import annotations

import warnings

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.plan import ShapeError

warnings.filterwarnings("ignore")

PFX = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def graph(text: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + text, format="turtle")
    return g


def _pattern_conforms(pattern: str, value: str, flags: str = "") -> bool:
    lit = (
        value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\x1c", "\\u001C").replace("\xa0", "\\u00A0")
    )
    flag = f' ; sh:flags "{flags}"' if flags else ""
    shapes = graph(
        f'ex:S sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:pattern """{pattern.replace(chr(92), chr(92) * 2)}"""{flag} ] .'
    )
    return validate(graph(f'ex:n ex:p "{lit}" .'), shapes).conforms


@pytest.mark.parametrize(
    ("pattern", "value", "flags", "expected"),
    [
        ("a$", "a\n", "", False),
        ("a$", "a", "", True),
        ("a$", "a\nb", "m", True),
        ("^.$", "\r", "", False),
        ("^.$", "\r", "s", True),
        ("^.$", "x", "", True),
        ("^\\s$", "\xa0", "", False),
        ("^\\s$", "\x1c", "", False),
        ("^\\s$", "\t", "", True),
        ("^\\S$", "\xa0", "", True),
        ("^\\w$", "_", "", False),
        ("^\\w$", "a", "", True),
        ("^[\\w]$", "_", "", False),
        ("^\\W$", "_", "", True),
        ("^a\\.b$", "a.b", "", True),
        ("^a\\$$", "a$", "", True),
        ("^[.$]$", "$", "", True),
    ],
)
def test_pattern_follows_xpath(pattern, value, flags, expected):
    assert _pattern_conforms(pattern, value, flags) is expected


# ---- sh:ignoredProperties without sh:closed ----------------------------------------------------------------------------


def test_ignored_properties_without_closed_does_not_apply():
    shapes = graph("ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:ignoredProperties (ex:p) .")
    assert validate(graph("ex:n ex:p 1 ."), shapes).conforms


# ---- ill-formed sh:qualified*Count -------------------------------------------------------------------------------------


@pytest.mark.parametrize("predicate", ["sh:qualifiedMinCount", "sh:qualifiedMaxCount"])
@pytest.mark.parametrize("lexical", ["--5", "²", "٣", "abc", "+-1", ""])
def test_ill_formed_qualified_count_is_a_shape_error(predicate, lexical):
    shapes = graph(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; "
        f'sh:qualifiedValueShape [ sh:minLength 1 ] ; {predicate} "{lexical}"^^xsd:integer ] .'
    )
    with pytest.raises(ShapeError):
        validate(graph('ex:a ex:p "x" .'), shapes)


def test_signed_qualified_count_is_accepted():
    shapes = graph(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; "
        'sh:qualifiedValueShape [ sh:minLength 1 ] ; sh:qualifiedMinCount "+1"^^xsd:integer ] .'
    )
    assert validate(graph('ex:a ex:p "x" .'), shapes).conforms


# ---- sh:rootClass as a list ----------------------------------------------------------------------------------------------

_ROOT_DATA = "ex:z ex:holds ex:Dog . ex:Dog rdfs:subClassOf ex:Mammal . ex:Mammal rdfs:subClassOf ex:Animal ."


def _root_class(root: str) -> bool:
    shapes = graph(f"ex:S a sh:NodeShape ; sh:targetNode ex:z ; sh:property [ sh:path ex:holds ; sh:rootClass {root} ] .")
    return validate(graph(_ROOT_DATA), shapes).conforms


def test_root_class_list_is_expanded():
    assert _root_class("ex:Animal") is True
    assert _root_class("(ex:Animal ex:Plant)") is True
    assert _root_class("(ex:Plant ex:Fungus)") is False


def test_root_class_malformed_list_is_a_shape_error():
    with pytest.raises(ShapeError):
        _root_class('("a" ex:Animal)')


# ---- sh:closed sh:ByTypes with indirect instances of rdfs:Class -------------------------------------------------------


def test_closed_by_types_class_typed_with_subclass_of_rdfs_class():
    shapes = graph(
        """
        ex:MyClassKind rdfs:subClassOf rdfs:Class .
        ex:Base a ex:MyClassKind ; sh:property [ sh:path ex:q ] .
        ex:C a ex:MyClassKind ; rdfs:subClassOf ex:Base ; sh:property [ sh:path ex:p ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed sh:ByTypes .
        """
    )
    assert validate(graph("ex:a a ex:C ; ex:p 1 ; ex:q 2 ."), shapes).conforms
    assert not validate(graph("ex:a a ex:C ; ex:p 1 ; ex:r 2 ."), shapes).conforms


# ---- base direction of a filled sh:message ------------------------------------------------------------------------------


@pytest.mark.parametrize("message", ['"bad {$this}"@ar--rtl', '"bad"@ar--rtl', '"bad {$this}"@en--ltr'])
def test_sparql_message_keeps_its_base_direction(message):
    shapes = graph(
        f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:message {message} ; '
        'sh:select "SELECT $this WHERE { $this <http://example.org/p> ?v }" ] .'
    )
    out = validate(graph("ex:a ex:p 1 ."), shapes)
    messages = [m for r in out.results for m in r.messages]
    assert messages
    assert [str(m.direction).lower().rsplit(".", 1)[-1] for m in messages] == [message[-3:]]


# ---- sh:uniqueValuesFor when the focus node is not a target of the shape ------------------------------------------------

_UNIQUE_SHAPES = """
ex:S a sh:NodeShape ; sh:targetNode ex:a, ex:b ; sh:uniqueValuesFor ex:id .
ex:R a sh:NodeShape ; sh:targetNode ex:z ; sh:node ex:S .
"""


def _unique_foci(data: str) -> list[str]:
    out = validate(graph(data), graph(_UNIQUE_SHAPES))

    def flatten(results):
        for r in results:
            yield r
            yield from flatten(r.details)

    return sorted(
        str(r.focus.value).rsplit("/", 1)[-1]
        for r in flatten(out.results)
        if r.component.value.endswith("UniqueValuesForConstraintComponent")
    )


def test_unique_values_for_reports_a_sh_node_focus_that_duplicates_a_target():
    assert _unique_foci('ex:a ex:id "1" . ex:b ex:id "2" . ex:z ex:id "1" .') == ["z"]


def test_unique_values_for_still_needs_another_node_with_the_same_values():
    assert _unique_foci('ex:a ex:id "1" . ex:b ex:id "2" . ex:z ex:id "3" .') == []
    assert _unique_foci('ex:a ex:id "1" . ex:b ex:id "1" . ex:z ex:id "3" .') == ["a", "b"]


def _chain(n: int):
    data = "".join(f"ex:n{i} ex:next ex:n{i + 1} .\n" for i in range(n))
    shapes = "ex:S a sh:NodeShape ; sh:targetNode ex:n0 ; sh:property [ sh:path ex:next ; sh:node ex:S ] ."
    return graph(data), graph(shapes)


def test_recursive_sh_node_chain_below_the_depth_limit_does_not_hit_the_python_stack():
    d, s = _chain(200)
    assert validate(d, s).conforms


def test_recursive_chain_past_the_depth_limit_is_a_shape_error_not_a_recursion_error():
    d, s = _chain(60)
    with pytest.raises(ShapeError):
        validate(d, s, max_validation_depth=20)


def test_chain_deeper_than_the_default_depth_limit_is_a_shape_error():
    d, s = _chain(300)
    with pytest.raises(ShapeError):
        validate(d, s)


_FN_SHAPES = """
@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
ex:count a sh:ListParameterExpressionFunction ;
  sh:bodyExpression [ shnex:count [ shnex:instancesOf [ shnex:arg 0 ] ] ] ;
  sh:parameter [ a sh:Parameter ; sh:path shnex:arg0 ] .
ex:S a sh:NodeShape ; sh:targetNode ex:t ; sh:sparql ex:Q .
ex:Q sh:select "PREFIX ex: <http://example.org/> SELECT $this ?value WHERE { BIND (ex:count(ex:C) AS ?value) }" .
"""


def test_a_shared_plan_runs_a_shacl_function_body_against_each_call_s_own_data_graph():
    shapes = graph(_FN_SHAPES)

    def counts(data: str, cache):
        return sorted(int(r.value.value) for r in validate(graph(data), shapes, plan_cache=cache).results)

    three = "ex:a a ex:C . ex:b a ex:C . ex:c a ex:C ."
    fresh = counts(three, None)
    cache: dict = {}
    counts("ex:a a ex:C .", cache)
    assert counts(three, cache) == fresh == [3]
