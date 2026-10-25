"""sh:targetWhere decides which nodes are targets by validating them against the where-shape ONLY (GitHub issue #53).

The nested validation used to run the whole shapes graph, so a violation of any unrelated shape on a candidate node made that
node look non-conforming to the where-shape, and it silently stopped being a target.
"""

import pytest
from rdflib import Graph, Namespace
from starlayer.shacl import StarShaclSchema, validate

SH = Namespace("http://www.w3.org/ns/shacl#")
P = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "


def _g(ttl: str) -> Graph:
    return Graph().parse(data=P + ttl, format="turtle")


def _reported(shapes: str, data: str, *, method: bool) -> set[tuple[str, str]]:
    """(focus node, source shape) of every result, by last path segment."""
    d, s = _g(data), _g(shapes)
    result = StarShaclSchema(shacl_graph=s).validate(data_graph=d, meta_shacl=False) if method else validate(d, s, meta_shacl=False)
    g = result.report_graph
    return {(str(g.value(r, SH.focusNode)).rsplit("/", 1)[-1], str(g.value(r, SH.sourceShape)).rsplit("/", 1)[-1]) for r in g.subjects(SH.focusNode)}


BOTH = pytest.mark.parametrize("method", [False, True], ids=["function", "method"])
DATA = "ex:i a ex:C . ex:j a ex:C ."
WHERE = "ex:S a sh:NodeShape ; sh:targetWhere [ sh:class ex:C ] ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] ."


def _s_foci(shapes: str, data: str, method: bool) -> set[str]:
    # the result's source shape for a property shape is a blank node, so identify S's results by their message
    d, s = _g(data), _g(shapes)
    result = StarShaclSchema(shacl_graph=s).validate(data_graph=d, meta_shacl=False) if method else validate(d, s, meta_shacl=False)
    g = result.report_graph
    return {str(g.value(r, SH.focusNode)).rsplit("/", 1)[-1] for r in g.subjects(SH.focusNode) if "S needs a name" in {str(m) for m in g.objects(r, SH.resultMessage)}}


@BOTH
def test_the_shapes_alone_target_both_nodes(method) -> None:
    assert _s_foci(WHERE, DATA, method) == {"i", "j"}


@BOTH
def test_an_unrelated_shape_that_fails_on_a_candidate_does_not_remove_it_as_a_target(method) -> None:
    unrelated = "ex:O a sh:NodeShape ; sh:targetNode ex:i ; sh:class ex:Z ."
    assert _s_foci(WHERE + unrelated, DATA, method) == {"i", "j"}


@BOTH
def test_unrelated_shapes_with_class_and_subjects_of_targets_do_not_interfere(method) -> None:
    unrelated = (
        "ex:O1 a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:other ; sh:minCount 1 ] . "
        "ex:O2 a sh:NodeShape ; sh:targetSubjectsOf rdfs:label ; sh:class ex:Z ."
    )
    assert _s_foci(WHERE + unrelated, DATA + " ex:i rdfs:label 'x' .", method) == {"i", "j"}


@BOTH
def test_a_candidate_that_really_fails_the_where_shape_is_still_not_a_target(method) -> None:
    where = "ex:S a sh:NodeShape ; sh:targetWhere [ sh:property [ sh:path ex:ok ; sh:minCount 1 ] ] ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] ."
    data = "ex:i ex:ok 1 . ex:j ex:other 1 ."
    assert _s_foci(where, data, method) == {"i"}


@BOTH
def test_the_where_shape_may_refer_to_other_shapes(method) -> None:
    where = (
        "ex:S a sh:NodeShape ; sh:targetWhere [ sh:node ex:IsC ] ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] . "
        "ex:IsC a sh:NodeShape ; sh:class ex:C ."
    )
    assert _s_foci(where, "ex:i a ex:C . ex:j a ex:D .", method) == {"i"}


@BOTH
def test_a_shape_the_where_shape_refers_to_does_not_bring_its_own_targets(method) -> None:
    """ex:k fails ex:IsC, a shape that targets it directly, but satisfies the where-shape through the other branch of the sh:or.
    ex:IsC failing on its own target says nothing about whether ex:k conforms to the where-shape."""
    where = (
        "ex:S a sh:NodeShape ; sh:targetWhere [ sh:or ( ex:IsC ex:IsD ) ] ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] . "
        "ex:IsC a sh:NodeShape ; sh:targetNode ex:k ; sh:class ex:C . ex:IsD a sh:NodeShape ; sh:class ex:D ."
    )
    assert _s_foci(where, "ex:k a ex:D .", method) == {"k"}


@BOTH
def test_the_where_shape_with_and_or_not_and_lists(method) -> None:
    where = (
        "ex:S a sh:NodeShape ; sh:targetWhere [ sh:and ( ex:A [ sh:not ex:B ] ) ] ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] . "
        "ex:A a sh:NodeShape ; sh:class ex:C . ex:B a sh:NodeShape ; sh:class ex:D ."
    )
    assert _s_foci(where, "ex:i a ex:C . ex:j a ex:C, ex:D . ex:k a ex:D .", method) == {"i"}


# --- which node failed, when the report cannot say: a property shape inside a property shape reports on the VALUE node
def _targets_for(where: str, data: str, method: bool) -> set[str]:
    shapes = (
        f"ex:S a sh:NodeShape ; sh:targetWhere {where} ; sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:message 'S needs a name' ] . "
        "ex:N a sh:NodeShape ; sh:class ex:C ."
    )
    return _s_foci(shapes, data, method)


@BOTH
def test_a_node_that_fails_only_through_a_nested_property_shape_is_not_a_target(method) -> None:
    """ex:A has the value ex:B and ex:B lacks ex:q, so ex:A fails; the report names ex:B, which has no ex:p and conforms."""
    where = "[ sh:property [ sh:path ex:p ; sh:property [ sh:path ex:q ; sh:minCount 1 ] ] ]"
    assert _targets_for(where, "ex:A ex:p ex:B . ex:B ex:other 1 .", method) == {"B"}


@BOTH
def test_a_nested_property_shape_where_every_candidate_conforms(method) -> None:
    where = "[ sh:property [ sh:path ex:p ; sh:property [ sh:path ex:q ; sh:minCount 1 ] ] ]"
    assert _targets_for(where, "ex:A ex:p ex:B . ex:B ex:q 1 .", method) == {"A", "B"}


@BOTH
def test_a_value_node_of_a_failing_node_conforms_by_itself(method) -> None:
    where = "[ sh:property [ sh:path ex:friend ; sh:node ex:N ] ]"
    assert _targets_for(where, "ex:A ex:friend ex:B . ex:B ex:other 1 .", method) == {"B"}


@BOTH
def test_a_value_class_violation_is_the_candidates_not_the_value_nodes(method) -> None:
    where = "[ sh:property [ sh:path ex:friend ; sh:class ex:C ] ]"
    assert _targets_for(where, "ex:A ex:friend ex:B . ex:B ex:other 1 .", method) == {"B"}
