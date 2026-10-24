"""Recursive shapes are cut where the data cycles, not where the shapes repeat (GitHub issue #26).

pySHACL 0.40.1 backs out of a self-referencing shape from the sequence of shapes alone, so a chain of three or more nodes with a
violation at the end was reported as conforming. The oracle here is the same schema written out as many distinct copies of the
shape (no recursion at all): on data without a cycle the recursive shape must give the same answer.
"""

import warnings

import pyshacl
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rdflib import Graph
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl.native_components import register_native_components
from starlayer.shacl.recursion import revisits

PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
RECURSIVE = (
    "ex:P a sh:NodeShape ; sh:targetClass ex:Person ; "
    "sh:property [ sh:path ex:name ; sh:minCount 1 ] , [ sh:path ex:friend ; sh:node ex:P ] ."
)


def _graph(ttl: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _validate(shapes: str, data: str):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any ShapeRecursionWarning fails the test
        return StarShaclSchema(shacl_graph=_graph(shapes)).validate(data_graph=_graph(data), meta_shacl=False, ignore_imports=True)


def _chain(length: int, *, last_has_name: bool, cycle: bool = False) -> str:
    """n0 (the only Person, so the only target) -> n1 -> ... -> n<length>. Every node has a name except, optionally, the last."""
    text = "ex:n0 a ex:Person ; ex:name 'x' ; ex:friend ex:n1 . "
    for i in range(1, length):
        text += f"ex:n{i} ex:name 'x' ; ex:friend ex:n{i + 1} . "
    last = f"ex:n{length}"
    text += f"{last} ex:name 'x'" if last_has_name else f"{last} a ex:Thing"
    text += " ; ex:friend ex:n0 ." if cycle else " ."
    return text


@pytest.mark.parametrize("length", [1, 2, 3, 4, 6, 10, 40])
def test_a_violation_at_the_end_of_a_chain_is_found_at_any_length(length) -> None:
    assert not _validate(RECURSIVE, _chain(length, last_has_name=False)).conforms


@pytest.mark.parametrize("length", [1, 3, 10])
def test_a_valid_chain_conforms_and_meets_no_cycle(length) -> None:
    result = _validate(RECURSIVE, _chain(length, last_has_name=True))
    assert result.conforms
    assert result.diagnostics.recursion_revisits == 0


def test_plain_pyshacl_in_the_same_process_is_correct_too() -> None:
    """The regression that began this: once StarLayer had registered its components, plain pySHACL cut a chain of 2 as well."""
    register_native_components()
    shapes = Graph().parse(data=PREFIXES + RECURSIVE, format="turtle")
    data = Graph().parse(data=PREFIXES + _chain(5, last_has_name=False), format="turtle")
    assert not pyshacl.validate(data, shacl_graph=shapes)[0]


@pytest.mark.parametrize("length", [1, 2, 5])
def test_a_cycle_that_is_valid_conforms_and_the_revisit_is_counted(length) -> None:
    result = _validate(RECURSIVE, _chain(length, last_has_name=True, cycle=True))
    assert result.conforms
    assert result.diagnostics.recursion_revisits > 0


def test_a_cycle_with_a_violation_in_it_is_found() -> None:
    data = "ex:a a ex:Person ; ex:name 'A' ; ex:friend ex:b . ex:b a ex:Person ; ex:friend ex:a ."
    assert not _validate(RECURSIVE, data).conforms


def test_a_node_reached_through_another_target_is_not_mistaken_for_a_cycle() -> None:
    """alice and bob are both targets of the shape. alice -> bob is not a cycle, so alice's sh:node result must be there."""
    result = _validate(RECURSIVE, "ex:alice a ex:Person ; ex:name 'A' ; ex:friend ex:bob . ex:bob a ex:Person .")
    assert result.diagnostics.recursion_revisits == 0
    focus = {str(f) for f in result.report_graph.objects(None, pyshacl_sh("focusNode"))}
    assert {"http://example.org/alice", "http://example.org/bob"} <= focus


def pyshacl_sh(term: str):
    from rdflib import Namespace

    return Namespace("http://www.w3.org/ns/shacl#")[term]


def test_mutual_recursion_between_two_shapes() -> None:
    shapes = (
        "ex:A a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] , [ sh:path ex:friend ; sh:node ex:B ] . "
        "ex:B a sh:NodeShape ; sh:property [ sh:path ex:name ; sh:minCount 1 ] , [ sh:path ex:friend ; sh:node ex:A ] ."
    )
    assert not _validate(shapes, _chain(6, last_has_name=False)).conforms
    assert _validate(shapes, _chain(6, last_has_name=True)).conforms
    assert _validate(shapes, _chain(3, last_has_name=True, cycle=True)).conforms


@pytest.mark.parametrize(
    "shape",
    [
        "sh:or ( [ sh:property [ sh:path ex:friend ; sh:node ex:P ] ] [ sh:property [ sh:path ex:name ; sh:minCount 99 ] ] ) ; sh:property [ sh:path ex:name ; sh:minCount 1 ]",
        "sh:and ( [ sh:property [ sh:path ex:friend ; sh:node ex:P ] ] ) ; sh:property [ sh:path ex:name ; sh:minCount 1 ]",
        "sh:xone ( [ sh:property [ sh:path ex:friend ; sh:node ex:P ] ] [ sh:property [ sh:path ex:name ; sh:minCount 99 ] ] ) ; sh:property [ sh:path ex:name ; sh:minCount 1 ]",
        "sh:property [ sh:path ex:name ; sh:minCount 1 ] , [ sh:path ex:friend ; sh:not [ sh:not [ sh:node ex:P ] ] ]",
    ],
    ids=["or", "and", "xone", "not"],
)
def test_recursion_through_the_logical_constraints_finds_the_violation(shape) -> None:
    shapes = f"ex:P a sh:NodeShape ; sh:targetClass ex:Person ; {shape} ."
    assert not _validate(shapes, _chain(5, last_has_name=False)).conforms
    assert _validate(shapes, _chain(5, last_has_name=True)).conforms


def test_no_shape_recursion_warning_is_raised() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        StarShaclSchema(shacl_graph=_graph(RECURSIVE)).validate(
            data_graph=_graph(_chain(8, last_has_name=False, cycle=True)), meta_shacl=False, ignore_imports=True
        )
    assert not [w for w in caught if "Recursive" in str(w.message)]


def test_a_nested_shapes_graph_is_checked_against_shacl_shacl_at_depth() -> None:
    from starlayer import starontology

    def nested(depth: int) -> str:
        shape = '[ sh:minCount "x" ]'
        for i in range(depth):
            shape = f"[ {('sh:and', 'sh:or', 'sh:xone')[i % 3]} ( {shape} ) ]"
        return f"ex:S a sh:NodeShape ; sh:and ( {shape} ) ."

    for depth in (0, 2, 4, 6):
        result = StarShaclSchema(shacl_graph=starontology.get_ontology_graph("shacl_shacl")).validate(
            data_graph=_graph(nested(depth)), meta_shacl=False, ignore_imports=True
        )
        assert not result.conforms


# --- the oracle: the recursive shape against the same schema written as distinct, non-recursive copies ------------------
DEPTH = 5  # nodes n0..n5, edges only forward, so the data has no cycle and is at most DEPTH hops deep


def _unrolled() -> str:
    text = ""
    for i in range(DEPTH + 1):
        target = "sh:targetClass ex:Person ; " if i == 0 else ""
        node = f", [ sh:path ex:friend ; sh:node ex:P{i + 1} ]" if i < DEPTH else ""
        text += f"ex:P{i} a sh:NodeShape ; {target}sh:property [ sh:path ex:name ; sh:minCount 1 ] {node} . "
    return text


@st.composite
def _acyclic_data(draw):
    lines = ["ex:n0 a ex:Person ."]
    for i in range(DEPTH + 1):
        if draw(st.booleans()) or i == 0:
            lines.append(f"ex:n{i} ex:name 'x' .")
        for j in range(i + 1, DEPTH + 1):
            if draw(st.integers(0, 3)) == 0:
                lines.append(f"ex:n{i} ex:friend ex:n{j} .")
    return " ".join(lines)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_acyclic_data())
def test_on_data_without_a_cycle_the_recursive_shape_agrees_with_the_unrolled_one(data) -> None:
    recursive = _validate(RECURSIVE, data)
    assert recursive.diagnostics.recursion_revisits == 0
    assert recursive.conforms == _validate(_unrolled(), data).conforms, data
