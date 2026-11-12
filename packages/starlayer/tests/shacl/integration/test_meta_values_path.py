"""Meta-shapes: ``sh:values`` and ``sh:defaultValue`` derive a property of the focus node, so ``sh:path`` must be a
single IRI (GitHub issue #204). Any other path used to derive nothing, silently."""

from __future__ import annotations

import pytest
from starlayer import StarLayerGraph
from starlayer.shacl import MetaShaclError
from starlayer.shacl.meta_shapes import meta_validate

PREFIXES = """
@prefix ex: <http://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""

PATHS = {
    "sequence": "( ex:myPath ex:name )",
    "inverse": "[ sh:inversePath ex:myPath ]",
    "alternative": "[ sh:alternativePath ( ex:myPath ex:other ) ]",
    "zero-or-more": "[ sh:zeroOrMorePath ex:other ]",
    "one-or-more": "[ sh:oneOrMorePath ex:other ]",
    "zero-or-one": "[ sh:zeroOrOnePath ex:other ]",
}


def _meta(path: str, predicate: str) -> tuple[bool, str]:
    shapes = StarLayerGraph()
    shapes.parse(
        data=PREFIXES
        + f"ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path {path} ; {predicate} 100 ] .",
        format="turtle12",
    )
    try:
        conforms, _graph, text = meta_validate(shapes)
    except MetaShaclError as error:  # meta_validate raises when the shapes graph is not well formed
        return False, str(error)
    return conforms, text


@pytest.mark.parametrize("predicate", ["sh:values", "sh:defaultValue"])
class TestPathOfAComputedValue:
    def test_a_single_iri_is_accepted(self, predicate: str) -> None:
        conforms, text = _meta("ex:myPath", predicate)
        assert conforms, text

    @pytest.mark.parametrize("kind", PATHS)
    def test_any_other_path_is_a_violation_with_the_reason(self, predicate: str, kind: str) -> None:
        conforms, text = _meta(PATHS[kind], predicate)
        assert not conforms
        assert f"{predicate} derives a property of the focus node, so sh:path must be a single property" in text
        assert "Violation" in text

    def test_the_other_predicate_is_not_blamed(self, predicate: str) -> None:
        other = "sh:defaultValue" if predicate == "sh:values" else "sh:values"
        _conforms, text = _meta(PATHS["sequence"], predicate)
        assert f"{other} derives a property" not in text
