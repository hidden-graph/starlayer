"""Leftover of issue #94: a SHACL path that goes through a triple term must not follow the adapter's
rdf:subject/predicate/object support triples (a triple term is not a resource with properties)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from starlayer import StarLayerGraph
from starlayer.shacl import validate

pytestmark = pytest.mark.shacl

PREFIXES = (
    "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
)
DATA = 'ex:a ex:p <<( ex:s ex:q "hello" )>> .'


def conforms(path: str, constraint: str) -> bool:
    data = StarLayerGraph().parse(data=PREFIXES + DATA, format="turtle12")
    shapes = Graph().parse(
        data=PREFIXES + f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path {path} ; {constraint} ] .",
        format="turtle",
    )
    return validate(data, shapes).conforms


def test_a_path_through_a_triple_term_has_no_values():
    assert conforms("(ex:p rdf:object)", "sh:maxCount 0") is True
    assert conforms("(ex:p rdf:subject)", "sh:maxCount 0") is True
    assert conforms("(ex:p rdf:predicate)", "sh:maxCount 0") is True


def test_a_required_value_through_a_triple_term_is_missing():
    assert conforms("(ex:p rdf:subject)", "sh:minCount 1") is False


def test_a_path_that_does_not_use_those_predicates_is_unchanged():
    assert conforms("ex:p", "sh:minCount 1") is True
    assert conforms("ex:p", "sh:maxCount 1") is True
