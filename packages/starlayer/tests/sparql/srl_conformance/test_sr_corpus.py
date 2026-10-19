"""Every corpus case must parse, round-trip through text, and survive the ``srl:`` tree.

Five independent properties per case, each its own test so a failure names the broken layer:

- ``parses``    ``parse_ruleset`` accepts it (including the section 4.2 well-formedness check and the
                ``srl:`` shapes, which ``validate=True`` runs).
- ``fixpoint``  rendering to text and re-parsing reaches a fixpoint: the text re-parses, renders to the same
                text, and the tree is the same on the next pass. (Not "same tree as the source": equivalent
                surface forms legitimately parse to differently shaped trees, e.g. ``1`` and ``"1"^^xsd:integer``.)
- ``meaning``   every FILTER/SET expression evaluates the same before and after the text round trip. This is
                what catches a renderer that loses parentheses or drops a function call.
- ``tree``      the ``srl:`` tree validates, and decoding it gives exactly the text the ruleset renders to.
- ``encoding``  the tree built from the text equals the tree built from the parsed ruleset.
"""

from __future__ import annotations

import pytest

from .corpus import CASES
from .helpers import (
    canonical_blank_nodes,
    expression_results,
    isomorphic,
    parse_ruleset,
    parsed,
    ruleset_to_text,
    srl_parse_to_tree,
    srl_tree_to_text,
    srl_validate,
    tree_of,
)
from .known_failures import CORPUS_FAILURES


def _expect(case, check, request):
    key = f"{case.id}::{check}"
    if key in CORPUS_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=CORPUS_FAILURES[key], strict=True))


@pytest.mark.srl_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_parses(case, request):
    _expect(case, "parses", request)
    parsed(case.text)


@pytest.mark.srl_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_text_reaches_a_fixpoint(case, request):
    _expect(case, "fixpoint", request)
    text1 = ruleset_to_text(parsed(case.text))
    second = parse_ruleset(text1)
    text2 = ruleset_to_text(second)
    assert text1 == text2, f"second render differs:\n{text1}\n----\n{text2}"
    assert isomorphic(tree_of(second), tree_of(parse_ruleset(text2)))


@pytest.mark.srl_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_text_round_trip_preserves_meaning(case, request):
    _expect(case, "meaning", request)
    original = parsed(case.text)
    rendered = parse_ruleset(ruleset_to_text(original))
    assert expression_results(original) == expression_results(rendered)


@pytest.mark.srl_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_round_trip(case, request):
    _expect(case, "tree", request)
    graph, root = srl_parse_to_tree(case.text)
    conforms, _report, report_text = srl_validate(graph)
    assert conforms, report_text[:500]
    assert canonical_blank_nodes(srl_tree_to_text(graph, root)) == canonical_blank_nodes(ruleset_to_text(parsed(case.text)))


@pytest.mark.srl_conformance
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_text_and_ruleset_encode_to_the_same_tree(case, request):
    _expect(case, "encoding", request)
    graph, _ = srl_parse_to_tree(case.text)
    assert isomorphic(graph, tree_of(parsed(case.text)))
