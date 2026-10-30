"""The draft's own code examples: each must parse, plan, and survive the text and tree round trips."""

from __future__ import annotations

import pytest

from .corpus import PRELUDE
from .grammar import SPEC_EXAMPLES
from .helpers import (
    canonical_blank_nodes,
    expression_results,
    parse_ruleset,
    ruleset_to_text,
    srl_parse_to_tree,
    srl_tree_to_text,
    srl_validate,
)
from .known_failures import SPEC_EXAMPLE_FAILURES

BLOCKS = [e["block"] for e in SPEC_EXAMPLES]
TEXT = {e["block"]: PRELUDE + e["text"] for e in SPEC_EXAMPLES}


@pytest.mark.srl_conformance
def test_all_examples_were_extracted():
    assert len(SPEC_EXAMPLES) == 13


@pytest.mark.srl_conformance
@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: f"block-{b}")
def test_example_parses_and_plans(block):
    ruleset = parse_ruleset(TEXT[block])
    ruleset.plan()


@pytest.mark.srl_conformance
@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: f"block-{b}")
def test_example_round_trips_and_keeps_its_meaning(block, request):
    if block in SPEC_EXAMPLE_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=SPEC_EXAMPLE_FAILURES[block], strict=True))
    original = parse_ruleset(TEXT[block])
    text = ruleset_to_text(original)
    again = parse_ruleset(text)
    assert ruleset_to_text(again) == text
    assert expression_results(original) == expression_results(again)
    graph, root = srl_parse_to_tree(TEXT[block])
    assert srl_validate(graph)[0]
    assert canonical_blank_nodes(srl_tree_to_text(graph, root)) == canonical_blank_nodes(text)
