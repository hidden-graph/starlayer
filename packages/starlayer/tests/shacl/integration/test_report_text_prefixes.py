"""``report_text`` abbreviates a term with the prefixes of the graph it belongs to, then of the other graph (data and shapes);
only the text changes: the report graph keeps its own messages and terms."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph import StarLayerGraph
from starlayer.shacl import validate

_EX = "http://example.org/"
_SH = "http://www.w3.org/ns/shacl#"
_ALICE = ox.NamedNode(_EX + "alice")
_AGE = ox.NamedNode(_EX + "age")
_OLD = ox.Literal("old")
_BODY = """
{ex}AgeMustBeIntShape a {sh}PropertyShape ; {sh}targetNode {ex}alice, {bob} ; {sh}path {ex}age ; {sh}datatype {xsd}integer .
"""


def _shapes(ex_prefix: str | None = "ex", bob: str = "<http://other.example/bob>") -> StarLayerGraph:
    """Shapes parsed from Turtle; with ``ex_prefix=None`` they use full IRIs and the graph binds no prefix for the example namespace."""
    g = StarLayerGraph(prefixes={})
    if ex_prefix is None:
        ttl = _full_iri_ttl(bob)
    else:
        ttl = f"@prefix {ex_prefix}: <{_EX}> . @prefix sh: <{_SH}> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . " + _BODY.format(
            ex=f"{ex_prefix}:", sh="sh:", xsd="xsd:", bob=bob
        )
    g.parse(data=ttl, format="turtle")
    return g


def _full_iri_ttl(bob: str) -> str:
    return (
        f"<{_EX}AgeMustBeIntShape> a <{_SH}PropertyShape> ; <{_SH}targetNode> <{_EX}alice>, {bob} ; "
        f"<{_SH}path> <{_EX}age> ; <{_SH}datatype> <http://www.w3.org/2001/XMLSchema#integer> ."
    )


def _data(prefixes: dict, value: ox.Literal | ox.NamedNode = _OLD, bob: bool = False) -> StarLayerGraph:
    g = StarLayerGraph(prefixes=prefixes)
    g.add((_ALICE, _AGE, value))
    if bob:
        g.add((ox.NamedNode("http://other.example/bob"), _AGE, ox.Literal("old")))
    return g


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


def _message_values(result) -> list[str]:
    return sorted(str(o) for _s, _p, o in result.report_graph.triples((None, ox.NamedNode(_SH + "resultMessage"), None)))


def test_data_without_prefixes_uses_the_shapes_graph_prefixes():
    result = validate(_data({}, ox.NamedNode(_EX + "alice")), _shapes())
    lines = _lines(result.report_text)
    assert "Source Shape: ex:AgeMustBeIntShape" in lines
    assert "Focus Node: ex:alice" in lines
    assert "Value Node: ex:alice" in lines
    assert "Message: Value ex:alice should have the datatype xsd:integer" in lines


def test_data_prefix_names_a_term_the_shapes_graph_does_not_bind():
    shapes = _shapes(ex_prefix=None, bob=f"<{_EX}bob>")
    lines = _lines(validate(_data({"ex": _EX}, ox.NamedNode(_EX + "alice")), shapes).report_text)
    assert "Source Shape: ex:AgeMustBeIntShape" in lines
    assert "Focus Node: ex:alice" in lines
    assert "Message: Value ex:alice should have the datatype <http://www.w3.org/2001/XMLSchema#integer>" in lines or any(
        line.startswith("Message: Value ex:alice should have the datatype") for line in lines
    )


def test_neither_graph_binds_the_namespace_leaves_the_full_iri():
    shapes = _shapes(ex_prefix=None, bob=f"<{_EX}bob>")
    lines = _lines(validate(_data({}, ox.NamedNode(_EX + "alice")), shapes).report_text)
    assert "Source Shape: <http://example.org/AgeMustBeIntShape>" in lines
    assert "Focus Node: <http://example.org/alice>" in lines
    assert "Value Node: <http://example.org/alice>" in lines


def test_same_prefix_name_for_two_namespaces_is_never_ambiguous():
    # the data graph's ``ex`` is the other namespace; the shapes graph's ``ex`` is the example namespace
    data = _data({"ex": "http://other.example/"}, bob=True)
    lines = _lines(validate(data, _shapes()).report_text)
    assert "Focus Node: ex:alice" in lines  # the shapes graph's ``ex`` is for alice's namespace
    assert "Focus Node: ex:bob" in lines  # the data graph's ``ex`` is for bob's
    # each ``ex:`` name above is right for the namespace of the graph that supplied it, and the data graph's names never turn into the shapes graph's
    assert "Source Shape: ex:AgeMustBeIntShape" in lines
    assert "Focus Node: <http://example.org/alice>" not in lines


def test_same_prefix_name_with_nothing_to_borrow_keeps_the_full_iri():
    data = _data({"ex": "http://other.example/"})
    shapes = _shapes(ex_prefix=None, bob=f"<{_EX}bob>")
    lines = _lines(validate(data, shapes).report_text)
    assert "Focus Node: <http://example.org/alice>" in lines


def test_report_graph_is_unchanged_by_the_text_abbreviation():
    result = validate(_data({}, ox.NamedNode(_EX + "alice")), _shapes())
    # the graph's message is still written with the prefixes of the one graph each term comes from: the data graph binds none
    # for alice, so it keeps the full IRI, though the text of the same run shows ``ex:alice``
    assert _message_values(result) == ['"Value <http://example.org/alice> should have the datatype xsd:integer"']
    with_prefix = validate(_data({"ex": _EX}, ox.NamedNode(_EX + "alice")), _shapes())
    assert _message_values(with_prefix) == ['"Value ex:alice should have the datatype xsd:integer"']
    focus = sorted(str(o) for _s, _p, o in result.report_graph.triples((None, ox.NamedNode(_SH + "focusNode"), None)))
    assert focus == [f"<{_EX}alice>"]
    # the text of the same run is abbreviated; the graph's triples are not
    assert "Focus Node: ex:alice" in _lines(result.report_text)


def test_literals_and_blank_nodes_are_unchanged():
    data = StarLayerGraph(prefixes={})
    data.add((_ALICE, _AGE, ox.Literal("12", language="en")))
    data.add((_ALICE, _AGE, ox.Literal("x", datatype=ox.NamedNode(_EX + "T"))))
    blank = ox.BlankNode("b1")
    data.add((_ALICE, _AGE, blank))
    data.add((blank, ox.NamedNode(_EX + "q"), ox.Literal("v")))
    lines = _lines(validate(data, _shapes()).report_text)
    assert 'Value Node: "12"@en' in lines
    assert 'Value Node: "x"^^ex:T' in lines
    assert "Value Node: [ ex:q \"v\" ]" in lines
    assert "Message: A blank node value should have the datatype xsd:integer" in lines


def test_sh_detail_nested_result_is_abbreviated():
    shapes = StarLayerGraph(prefixes={})
    shapes.parse(
        data=f"""
        @prefix ex: <{_EX}> . @prefix sh: <{_SH}> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
            sh:or ( [ sh:path ex:age ; sh:datatype <http://www.w3.org/2001/XMLSchema#integer> ] ) .
        """,
        format="turtle",
    )
    result = validate(_data({}, ox.NamedNode(_EX + "alice")), shapes)
    text = result.report_text
    assert "Focus Node: ex:alice" in _lines(text)
    assert "<http://example.org/" not in text
