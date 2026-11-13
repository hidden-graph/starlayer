"""Compatibility for tests that read engine results through ``rd(...)``: results are pyoxigraph terms already, so these are identities."""

from __future__ import annotations


def rd(graph):
    """``graph`` itself (engine results hold pyoxigraph terms, which is what the tests compare with)."""
    return graph


def rdn(terms):
    """``terms`` itself."""
    return terms
