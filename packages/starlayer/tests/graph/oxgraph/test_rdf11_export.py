"""``serialize(rdf_version="1.1")`` goes through the interop export: no triple term and no base-direction literal remain."""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import OxDataset, OxGraph

REIFIES = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies>"
TTL = f'<http://e/r> {REIFIES} <<( <http://e/s> <http://e/p> <http://e/o> )>> . <http://e/s> <http://e/p> "x"@en--ltr .'


def test_rdf12_output_keeps_triple_terms() -> None:
    g = OxGraph()
    g.parse(data=TTL, format="turtle")
    assert "<<(" in g.serialize(format="turtle")


def test_rdf11_output_has_no_triple_term_and_no_directional_literal() -> None:
    g = OxGraph()
    g.parse(data=TTL, format="turtle")
    out = g.serialize(format="turtle", rdf_version="1.1")
    assert "<<(" not in out and "@en--ltr" not in out
    assert "PropositionForm" in out  # the basic encoding of the triple term


@pytest.mark.parametrize("fmt", ["nt", "turtle", "rdfxml"])
def test_rdf11_output_in_triple_formats(fmt: str) -> None:
    g = OxGraph()
    g.parse(data=TTL, format="turtle")
    assert "<<(" not in g.serialize(format=fmt, rdf_version="1.1")


def test_rdf11_output_of_a_dataset_keeps_graph_names() -> None:
    d = OxDataset()
    d.parse(data=f"<http://e/r> {REIFIES} <<( <http://e/s> <http://e/p> <http://e/o> )>> <http://e/g> .", format="nq")
    out = d.serialize(format="nq", rdf_version="1.1")
    assert "<<(" not in out and "<http://e/g>" in out


def test_unknown_version_is_refused() -> None:
    with pytest.raises(ValueError, match="rdf_version"):
        OxGraph().serialize(format="turtle", rdf_version="1.3")
