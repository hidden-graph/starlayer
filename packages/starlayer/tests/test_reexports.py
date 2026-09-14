"""starlayer's __init__.py re-exports names from starlayergraph/starshacl by
reference, not by copy or redefinition - these tests lock in `is` identity
(not just equal behavior) so a future refactor can't quietly turn a
re-export into a separate, divergent copy."""

import starlayergraph
import starshacl

import starlayer


def test_reexports_are_the_same_objects_not_copies() -> None:
    for name in starlayer.__all__:
        source = starshacl if name == "StarShaclValidator" else starlayergraph
        assert getattr(starlayer, name) is getattr(source, name), name


def test_all_matches_actual_module_exports() -> None:
    exported = {name for name in dir(starlayer) if not name.startswith("_")}
    assert exported == set(starlayer.__all__)


def test_graph_and_validator_work_together_through_the_single_import() -> None:
    from starlayer import Namespace, StarLayerGraph, StarShaclValidator

    ex = Namespace("http://example.org/")
    data = StarLayerGraph()
    data.add((ex.alice, ex.knows, ex.bob))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:knows .
        """,
        format="turtle",
    )

    result = StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True
