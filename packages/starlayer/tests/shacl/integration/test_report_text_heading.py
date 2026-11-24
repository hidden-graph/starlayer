"""The first line of each result block in ``report_text`` names the constraint component as a prefixed name (as the
``Severity:`` line is written), not as a local name followed by the full IRI."""

from __future__ import annotations

from starlayer.graph import StarLayerGraph
from starlayer.shacl import validate

_PREFIXES = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> ."
_SHAPES = _PREFIXES + " ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:n ; sh:minCount 1 {extra} ] ."
_DATA = "@prefix ex: <http://example.org/> . ex:a a ex:P ."


def _headings(shapes_ttl: str, shapes_prefixes=None, data_ttl: str = _DATA) -> list[str]:
    data = StarLayerGraph()
    data.parse(data=data_ttl, format="turtle")
    shapes = StarLayerGraph() if shapes_prefixes is None else StarLayerGraph(prefixes=shapes_prefixes)
    shapes.parse(data=shapes_ttl, format="turtle")
    text = validate(data, shapes).report_text
    return [line for line in text.splitlines() if " in " in line and line.endswith(":") and not line.startswith("\\t")]


def test_violation_heading_is_a_prefixed_name():
    assert _headings(_SHAPES.format(extra="")) == ["Constraint Violation in sh:MinCountConstraintComponent:"]


def test_warning_severity_gives_validation_result():
    shapes = _SHAPES.format(extra="; sh:severity sh:Warning")
    assert _headings(shapes) == ["Validation Result in sh:MinCountConstraintComponent:"]


def test_unbound_prefix_falls_back_to_one_full_iri():
    shapes = (
        "<http://example.org/S> a <http://www.w3.org/ns/shacl#NodeShape> ; <http://www.w3.org/ns/shacl#targetClass> <http://example.org/P> ;"
        " <http://www.w3.org/ns/shacl#property> [ <http://www.w3.org/ns/shacl#path> <http://example.org/n> ;"
        " <http://www.w3.org/ns/shacl#minCount> 1 ] ."
    )
    data = "<http://example.org/a> a <http://example.org/P> ."
    (heading,) = _headings(shapes, shapes_prefixes={}, data_ttl=data)
    assert heading == "Constraint Violation in <http://www.w3.org/ns/shacl#MinCountConstraintComponent>:"


_CUSTOM = (
    _PREFIXES
    + """
    ex:NoFoo a sh:ConstraintComponent ;
        sh:parameter [ sh:path ex:noFoo ] ;
        sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { FILTER(false) }" ] .
    ex:S a sh:NodeShape ; sh:targetClass ex:P ; ex:noFoo true .
    """
)


def test_user_defined_component_in_another_namespace_is_a_prefixed_name():
    assert _headings(_CUSTOM) == ["Constraint Violation in ex:NoFoo:"]
