"""Differential: which functions does the SRL parser accept, against the spec's BuiltInCall production?

SRL's expression grammar is rdflib's. The spec says it is SPARQL's "unchanged", but its BuiltInCall is a
*subset* (no BOUND, COALESCE, RAND, the hash functions, EXISTS or aggregates). Both directions can go wrong:
a function the spec includes that we cannot represent, and a SPARQL-only function that leaks through.
"""

from __future__ import annotations

import pytest

from .builtins_table import IN_SPEC, NOT_IN_SPEC
from .corpus import PRELUDE
from .helpers import parse_ruleset, srl_parse_to_tree, srl_validate
from .known_failures import BUILTIN_FAILURES, BUILTIN_LEAKS


def _rule(call: str) -> str:
    return PRELUDE + f"RULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y FILTER ({call}) }}"


@pytest.mark.srl_conformance
@pytest.mark.parametrize("name", sorted(IN_SPEC))
def test_spec_function_parses_and_encodes(name, request):
    if name in BUILTIN_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=BUILTIN_FAILURES[name], strict=True))
    text = _rule(IN_SPEC[name])
    parse_ruleset(text)
    graph, _ = srl_parse_to_tree(text)
    assert srl_validate(graph)[0]


@pytest.mark.srl_conformance
@pytest.mark.parametrize("name", sorted(NOT_IN_SPEC))
def test_function_outside_the_spec_is_rejected(name, request):
    if name in BUILTIN_LEAKS:
        request.applymarker(pytest.mark.xfail(reason=BUILTIN_LEAKS[name], strict=True))
    with pytest.raises(Exception) as caught:  # noqa: PT011 - any SRLError subclass; checked below
        parse_ruleset(_rule(NOT_IN_SPEC[name]))
    assert type(caught.value).__name__ in {"SRLParseError", "SRLError"}


@pytest.mark.srl_conformance
def test_the_spec_function_list_has_the_expected_size():
    """Guards the extraction of the BuiltInCall keywords from the vendored grammar (53 at the 2026-10-14 draft)."""
    from .builtins_table import SPEC

    assert len(SPEC) >= 50 and {"STR", "TRIPLE", "hasLANGDIR", "isNUMERIC"} <= SPEC
    assert not (SPEC & {"BOUND", "COALESCE", "RAND", "EXISTS"})
