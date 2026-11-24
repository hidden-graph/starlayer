"""``StarShaclProcessor(allow_warnings=, allow_infos=)``: constructor defaults of the conformance options, overridden per call."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.shacl import StarShaclProcessor

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
DATA = PFX + "ex:a a ex:T ."


def shapes(severity: str) -> str:
    return (
        PFX
        + f"ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:severity {severity} ] ."
    )


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=ttl, format="turtle")
    return graph


def proc(severity: str, **kw) -> StarShaclProcessor:
    return StarShaclProcessor(g(shapes(severity)), **kw)


def conforms(p: StarShaclProcessor, **kw) -> bool:
    return p.validate(g(DATA), **kw).conforms


def test_default_unchanged() -> None:
    assert not conforms(proc("sh:Warning"))
    assert not conforms(proc("sh:Info"))
    assert not conforms(proc("sh:Violation", allow_warnings=True, allow_infos=True))


def test_constructor_allow_warnings() -> None:
    p = proc("sh:Warning", allow_warnings=True)
    assert conforms(p)
    assert not conforms(p, allow_warnings=False)  # the call beats the constructor
    assert not conforms(proc("sh:Warning", allow_warnings=False))
    assert conforms(proc("sh:Warning"), allow_warnings=True)


def test_constructor_allow_warnings_also_allows_infos() -> None:
    assert conforms(proc("sh:Info", allow_warnings=True))


def test_constructor_allow_infos() -> None:
    p = proc("sh:Info", allow_infos=True)
    assert conforms(p)
    assert not conforms(p, allow_infos=False)
    assert not conforms(proc("sh:Warning", allow_infos=True))  # infos only: a warning still blocks


def test_call_can_allow_what_constructor_did_not() -> None:
    p = proc("sh:Warning", allow_infos=True)
    assert conforms(p, allow_warnings=True)


def test_apply_rules_follows_constructor() -> None:
    p = proc("sh:Warning", allow_warnings=True)
    assert p.apply_rules(g(DATA)).validation.conforms
    assert not p.apply_rules(g(DATA), allow_warnings=False).validation.conforms
    assert not proc("sh:Warning").apply_rules(g(DATA)).validation.conforms
    assert proc("sh:Info", allow_infos=True).apply_rules(g(DATA)).validation.conforms


@pytest.mark.parametrize("mode", ["validation", "rules", "debug"])
def test_mode_preset_does_not_reset_it(mode: str) -> None:
    p = proc("sh:Warning", allow_warnings=True)
    assert conforms(p, mode=mode)
    assert not conforms(p, mode=mode, allow_warnings=False)


def test_unknown_constructor_keyword_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        StarShaclProcessor(g(shapes("sh:Warning")), allow_warning=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        proc("sh:Warning", allow_warnings=True).validate(g(DATA), allow_warning=True)


@pytest.mark.parametrize("severity", ["sh:Debug", "sh:Trace"])
def test_debug_and_trace_never_block(severity: str) -> None:
    assert conforms(proc(severity))
    assert conforms(proc(severity, allow_warnings=False, allow_infos=False))
