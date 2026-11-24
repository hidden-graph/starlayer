from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor
from tests.support.terms import Namespace

from ._rdflib_view import rd

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

PREFIXES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
"""
LIST_SHAPE = PREFIXES + """
ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:uniqueValuesFor ( ex:first ex:last ) .
"""
SINGLE_SHAPE = PREFIXES + """
ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:uniqueValuesFor ex:id .
"""


def _violating_focus(shapes: str, data: str) -> set:
    sg, dg = StarLayerGraph(), StarLayerGraph()
    sg.parse(data=shapes, format="turtle")
    dg.parse(data=PREFIXES + data, format="turtle")
    result = StarShaclProcessor(shacl_graph=sg).validate(data_graph=dg, meta_shacl=False)
    return {o for _, _, o in rd(result.report_graph).triples((None, SH.focusNode, None))}


def test_partial_missing_duplicates_are_reported() -> None:
    data = 'ex:a a ex:P ; ex:first "Ann" . ex:b a ex:P ; ex:first "Ann" .'
    assert _violating_focus(LIST_SHAPE, data) == {EX.a, EX.b}


def test_all_missing_is_skipped_for_a_list() -> None:
    assert _violating_focus(LIST_SHAPE, "ex:a a ex:P . ex:b a ex:P .") == set()


def test_partial_versus_full_is_not_equal() -> None:
    data = 'ex:a a ex:P ; ex:first "Ann" . ex:b a ex:P ; ex:first "Ann" ; ex:last "Lee" .'
    assert _violating_focus(LIST_SHAPE, data) == set()


def test_full_duplicates_are_reported() -> None:
    data = 'ex:a a ex:P ; ex:first "Ann" ; ex:last "Lee" . ex:b a ex:P ; ex:first "Ann" ; ex:last "Lee" .'
    assert _violating_focus(LIST_SHAPE, data) == {EX.a, EX.b}


def test_single_property_unchanged() -> None:
    dup = 'ex:a a ex:P ; ex:id 1 . ex:b a ex:P ; ex:id 1 . ex:c a ex:P . ex:d a ex:P .'
    assert _violating_focus(SINGLE_SHAPE, dup) == {EX.a, EX.b}


def test_node_outside_the_targets_is_not_a_clash() -> None:
    data = 'ex:a a ex:P ; ex:first "Ann" . ex:z ex:first "Ann" .'
    assert _violating_focus(LIST_SHAPE, data) == set()


def _messages(shapes: str, data: str) -> dict:
    """focus node -> (sh:resultMessage texts, sh:value objects) of its result."""
    sg, dg = StarLayerGraph(), StarLayerGraph()
    sg.parse(data=shapes, format="turtle")
    dg.parse(data=PREFIXES + data, format="turtle")
    report = rd(StarShaclProcessor(shacl_graph=sg).validate(data_graph=dg, meta_shacl=False).report_graph)
    out = {}
    for res, _, focus in report.triples((None, SH.focusNode, None)):
        out[focus] = (
            sorted(m.value for m in report.objects(res, SH.resultMessage)),
            list(report.objects(res, SH.value)),
        )
    return out


class TestClashMessage:
    def test_single_property_names_the_other_node_and_value(self) -> None:
        got = _messages(SINGLE_SHAPE, "ex:a a ex:P ; ex:id 1 . ex:b a ex:P ; ex:id 1 .")
        assert got[EX.a][0] == ["ex:a has the same value as ex:b for ex:id 1"]
        assert got[EX.b][0] == ["ex:b has the same value as ex:a for ex:id 1"]

    def test_list_shows_each_property_and_none_for_a_missing_one(self) -> None:
        data = 'ex:a a ex:P ; ex:first "Ann" . ex:b a ex:P ; ex:first "Ann" .'
        assert _messages(LIST_SHAPE, data)[EX.a][0] == ['ex:a has the same values as ex:b for ex:first "Ann", ex:last (none)']

    def test_list_with_all_values(self) -> None:
        data = 'ex:a a ex:P ; ex:first "Ann" ; ex:last "Lee" . ex:b a ex:P ; ex:first "Ann" ; ex:last "Lee" .'
        assert _messages(LIST_SHAPE, data)[EX.a][0] == ['ex:a has the same values as ex:b for ex:first "Ann", ex:last "Lee"']

    def test_several_clashing_nodes_are_sorted(self) -> None:
        data = "ex:c a ex:P ; ex:id 1 . ex:b a ex:P ; ex:id 1 . ex:a a ex:P ; ex:id 1 ."
        assert _messages(SINGLE_SHAPE, data)[EX.c][0] == ["ex:c has the same value as ex:a, ex:b for ex:id 1"]

    def test_the_shapes_own_message_overrides(self) -> None:
        shape = SINGLE_SHAPE.replace("sh:uniqueValuesFor ex:id", 'sh:message "Duplicate id" ; sh:uniqueValuesFor ex:id')
        got = _messages(shape, "ex:a a ex:P ; ex:id 1 . ex:b a ex:P ; ex:id 1 .")
        assert got[EX.a][0] == ["Duplicate id"]

    def test_there_is_no_sh_value(self) -> None:
        got = _messages(SINGLE_SHAPE, "ex:a a ex:P ; ex:id 1 . ex:b a ex:P ; ex:id 1 .")
        assert got[EX.a][1] == []
