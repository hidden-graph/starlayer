"""The lexical-fidelity warning names the caller's line (this file), whichever public entry point is used, not a starlayer module."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("pyoxigraph")

from starlayer.graph import StarLayerGraph  # noqa: E402
from starlayer.shacl import (  # noqa: E402
    StarShaclProcessor,
    apply_rules,
    validate,
    validate_each,
)
from starlayer.shacl.engine import api  # noqa: E402
from starlayer.shacl.engine.oxigraph_view import OxigraphGraph  # noqa: E402
from starlayer.shacl.engine.terms import StarLayerFidelityWarning  # noqa: E402

PFX = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> .\n"
DATA = PFX + '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . ex:a ex:p "04"^^xsd:integer .\n'
SHAPES = PFX + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:hasValue 4 ] .\n"


def _graph(text):
    with warnings.catch_warnings():  # the warning at load is not the one under test
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        return StarLayerGraph().parse(data=text, format="turtle")


def _engine_graph(text):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        return OxigraphGraph.from_text(text)


def _fidelity(caught):
    return [w for w in caught if issubclass(w.category, StarLayerFidelityWarning)]


def _record(call):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    found = _fidelity(caught)
    assert len(found) == 1
    return found[0]


ENTRY_POINTS = {
    "module validate": lambda: validate(_graph(DATA), _graph(SHAPES)),
    "module validate_each": lambda: validate_each([_graph(DATA)], _graph(SHAPES)),
    "module apply_rules": lambda: apply_rules(_graph(DATA), _graph(SHAPES)),
    "processor validate": lambda: StarShaclProcessor(_graph(SHAPES)).validate(_graph(DATA)),
    "processor validate_each": lambda: StarShaclProcessor(_graph(SHAPES)).validate_each([_graph(DATA)]),
    "processor apply_rules": lambda: StarShaclProcessor(_graph(SHAPES)).apply_rules(_graph(DATA)),
    "engine api.validate": lambda: api.validate(_engine_graph(DATA), _engine_graph(SHAPES)),
}


@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_warning_is_reported_in_the_callers_file(name):
    warning = _record(ENTRY_POINTS[name])
    assert warning.filename == __file__


def test_warning_line_is_the_calling_line():
    def call():
        validate(_graph(DATA), _graph(SHAPES))  # the line the warning must name

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    (warning,) = _fidelity(caught)
    with open(__file__) as source:
        assert "the line the warning must name" in source.read().splitlines()[warning.lineno - 1]


def test_advanced_deprecation_is_still_reported_in_the_callers_file():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        validate(_graph(DATA), _graph(SHAPES), advanced=False)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning) and "advanced" in str(w.message)]
    assert len(deprecations) == 1 and deprecations[0].filename == __file__
