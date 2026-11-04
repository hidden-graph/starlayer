"""Parser/serializer round trips, prefixes and @base (GitHub issues #132 and #133, third hunt)."""

from __future__ import annotations

import pytest
from rdflib import Literal, URIRef
from starlayer.graph import StarLayerDataset, StarLayerGraph

pytestmark = pytest.mark.graph

_RR = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")


def _e(name: str) -> URIRef:
    return URIRef("http://e/" + name)


def _quads(ds: StarLayerDataset) -> set[tuple[str, str, str, str]]:
    return {(str(s), str(p), str(o), str(c.identifier)) for c in ds.contexts() for s, p, o in c}


# --- @base, publicID and relative namespaces in TriG / Turtle (#132)




















# --- writers and prefixes that are not valid names (#132)

_BAD_PREFIXES = ["x.", "a:b", "1x", "_", "-x", "xml", "xmlns"]






@pytest.mark.parametrize("prefix", ["1x", "-x", "a:b", "xml", "xmlns", "x."])
def test_rdfxml_writer_survives_a_prefix_that_is_not_an_ncname(prefix: str) -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind(prefix, "http://ex.org/ns/", override=True)
    g.add((URIRef("http://ex.org/s"), URIRef("http://ex.org/ns/p"), Literal("v")))
    out = g.serialize(format="rdfxml12")
    assert set(StarLayerGraph().parse(data=out, format="rdfxml12")) == set(g)
















# --- used_prefixes / reduce_prefixes (#132)








# --- control characters (#133)

_CONTROL = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x00", "\x01", "\x1f", "\x85", " ", " "]








@pytest.mark.parametrize("char", ["\x00", "\x08", "\x0b", "\x0c", "\x1f"])
def test_xml_writers_refuse_a_character_xml_cannot_carry(char: str) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal(f"a{char}b")))
    with pytest.raises(ValueError, match="XML 1.0"):
        g.serialize(format="rdfxml12")




# --- bytes in, bytes out, base (#133, #132)

_NT = b"<http://e/s> <http://e/p> <http://e/o> ."


def test_parse_accepts_utf8_bytes_with_a_byte_order_mark() -> None:
    data = b'\xef\xbb\xbf<http://e/s> <http://e/p> "caf\xc3\xa9" .'
    assert [o.value for _s, _p, o in StarLayerGraph().parse(data=data, format="nt12")] == ["café"]


