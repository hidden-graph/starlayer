"""Tree-layer tests (T, R, O, V in the plan's P/T/R/O/V/N): does the ``manch:`` tree faithfully carry
everything the parser accepts?

Four independent properties per corpus case, each its own test so a failure names the broken layer:

- ``validates``    the tree ``manchester_parse_to_tree`` produces passes ``manchester_validate``.
- ``owl_matches``  ``manchester_tree_to_owl(tree)`` is isomorphic to ``parse_manchester(text)`` - the
                   silent-loss probe: anything the parser compiled that never reached the tree shows up
                   here as a missing triple.
- ``text_roundtrip`` ``manchester_tree_to_text(tree)`` re-parses to the same OWL graph.
- ``fixpoint``     text -> tree -> text -> tree -> text is stable after the first pass.

A case whose direct parse fails is skipped here (the differential test owns that failure).
"""

from __future__ import annotations

import pytest
from starlayer.graph.compare import isomorphic
from starlayer.graph.parsers.errors import ManchesterSyntaxError

from .corpus import CASES
from .helpers import parse_to_graph, to_graph
from .known_failures import TREE_FAILURES
from .wip.manchester import (
    manchester_parse_to_tree,
    manchester_tree_to_owl,
    manchester_tree_to_text,
    manchester_validate,
)


def _prepare(case, check: str, request):
    key = f"{case.id}::{check}"
    if key in TREE_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=TREE_FAILURES[key], strict=True))
    try:
        direct = parse_to_graph(case.text)
    except ManchesterSyntaxError:
        pytest.skip("direct parse fails; owned by test_mc_differential")
    return direct


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_validates(case, request):
    _prepare(case, "validates", request)
    tree = manchester_parse_to_tree(case.text)
    conforms, _report, text = manchester_validate(tree)
    assert conforms, text[:600]


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_to_owl_matches_direct_parse(case, request):
    direct = _prepare(case, "owl_matches", request)
    tree = manchester_parse_to_tree(case.text)
    via_tree = manchester_tree_to_owl(tree)
    assert isomorphic(direct, to_graph(via_tree)), "OWL from the tree differs from compiling the text directly"


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_text_roundtrip(case, request):
    direct = _prepare(case, "text_roundtrip", request)
    tree = manchester_parse_to_tree(case.text)
    rendered = manchester_tree_to_text(tree)
    assert isomorphic(direct, parse_to_graph(rendered)), f"re-parsed render differs; rendered:\n{rendered}"


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_second_pass_is_stable(case, request):
    _prepare(case, "fixpoint", request)
    text1 = manchester_tree_to_text(manchester_parse_to_tree(case.text))
    text2 = manchester_tree_to_text(manchester_parse_to_tree(text1))
    assert text1 == text2
