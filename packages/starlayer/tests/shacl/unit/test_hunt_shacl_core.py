"""Regression tests from the SHACL engine constraint-component bug hunt."""

from __future__ import annotations

import warnings

import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl_engine import validate

warnings.filterwarnings("ignore")

PFX = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def graph(text: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PFX + text, format="turtle")
    return g


def _pattern_conforms(pattern: str, value: str, flags: str = "") -> bool:
    lit = (
        value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\x1c", "\\u001C").replace("\xa0", "\\u00A0")
    )
    flag = f' ; sh:flags "{flags}"' if flags else ""
    shapes = graph(
        f'ex:S sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:pattern """{pattern.replace(chr(92), chr(92) * 2)}"""{flag} ] .'
    )
    return validate(graph(f'ex:n ex:p "{lit}" .'), shapes).conforms


@pytest.mark.parametrize(
    ("pattern", "value", "flags", "expected"),
    [
        ("a$", "a\n", "", False),
        ("a$", "a", "", True),
        ("a$", "a\nb", "m", True),
        ("^.$", "\r", "", False),
        ("^.$", "\r", "s", True),
        ("^.$", "x", "", True),
        ("^\\s$", "\xa0", "", False),
        ("^\\s$", "\x1c", "", False),
        ("^\\s$", "\t", "", True),
        ("^\\S$", "\xa0", "", True),
        ("^\\w$", "_", "", False),
        ("^\\w$", "a", "", True),
        ("^[\\w]$", "_", "", False),
        ("^\\W$", "_", "", True),
        ("^a\\.b$", "a.b", "", True),
        ("^a\\$$", "a$", "", True),
        ("^[.$]$", "$", "", True),
    ],
)
def test_pattern_follows_xpath(pattern, value, flags, expected):
    assert _pattern_conforms(pattern, value, flags) is expected
