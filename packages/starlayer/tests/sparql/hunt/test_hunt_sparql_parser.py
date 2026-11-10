"""Regression tests for bugs found in the SPARQL parser area (hunt)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.sparql.parse_sparql import parse_sparql


def _resolved(base, ref):
    return parse_sparql(f"BASE <{base}> SELECT * {{ <{ref}> ?p ?o }}").f["where"][0].f["s"].value


@pytest.mark.parametrize(
    ("base", "ref"),
    [
        ("http://a/b/c/", "a//b"),
        ("http://a//b", "g"),
        ("http://a/b/c/d#f", ""),
        ("urn:x:y", "g"),
        ("urn:x:y", "#s"),
        ("urn:x:y", "?y"),
        ("http://a/b/c/d;p?q", "../../g"),
        ("http://a/b/c/d;p?q", "../../../g"),
        ("http://a/b/c/d;p?q", "./g/."),
        ("http://a/b/c/d;p?q", "g;x=1/../y"),
        ("http://a/b/c/d;p?q", "?y"),
        ("http://a/b/c/d;p?q", "//g"),
        ("http://a", "g"),
        ("http://a/b/c/d", "#"),
    ],
)
def test_relative_iri_resolution_is_rfc3986(base, ref):
    want = list(ox.Store().query(f"BASE <{base}> SELECT (<{ref}> AS ?x) {{}}"))[0]["x"].value
    assert _resolved(base, ref) == want


def test_base_dot_segments_resolve_per_rfc3986():
    # 5.2.3 merge, then 5.2.4: /b/../g is /g (Oxigraph keeps /b/../g, which is not the RFC result)
    assert _resolved("http://a/b/../c", "g") == "http://a/g"
