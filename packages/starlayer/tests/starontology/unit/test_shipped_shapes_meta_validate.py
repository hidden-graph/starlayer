"""Every SHACL shapes graph StarLayer ships must itself be a well-formed
shapes graph, checked with the project's own meta-SHACL preflight.

``meta_shacl`` is off by default in ``validate()`` (a development-time check),
and internal validators such as ``srl_validate`` rely on the shipped shapes
being sound without re-checking them on every call. This test is that check,
run once in the fast tier instead.

The list is read from the registry, so a newly registered shapes graph is
covered automatically.
"""

from __future__ import annotations

import warnings

import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph
from starlayer.shacl.meta_shapes import meta_validate

_SHAPES_GRAPHS = sorted([name for name in starontology._REGISTRY if name.endswith("_shacl")])


def test_the_registry_has_shapes_graphs_to_check() -> None:
    assert len(_SHAPES_GRAPHS) >= 7, _SHAPES_GRAPHS


@pytest.mark.parametrize("name", _SHAPES_GRAPHS)
def test_shipped_shapes_graph_passes_meta_shacl(name: str) -> None:
    graph = starontology.get_ontology_graph(name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            conforms, _report_graph, report_text = meta_validate(graph)
        except Exception as exc:  # meta_validate raises on a malformed shapes graph
            pytest.fail(f"{name} is not a well-formed shapes graph:\n{exc}")
    assert conforms, f"{name} is not a well-formed shapes graph:\n{report_text}"


def test_the_check_does_reject_a_malformed_shapes_graph() -> None:
    """Guards the test above against passing vacuously."""
    graph = StarLayerGraph()
    graph.parse(
        data='''
            @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .
            ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount "not a number" ] .
        ''',
        format="turtle",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(Exception, match="MetaSHACL"):
            meta_validate(graph)
