"""Regression tests for the io hunt: parsing, serialization, pretty printing, interop, dirlangstring."""

from __future__ import annotations

import copy
import http.server
import io
import pickle
import threading
import warnings
import xml.etree.ElementTree as ET

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.model.dirlangstring import (
    DIRLANG_NS,
    DirLangString,
    decode_dirlangstring,
)
from starlayer.graph.model.triple import TripleTerm
from starlayer.graph.oxgraph.pretty import pretty_turtle


def test_jsonld_dataset_keeps_named_graph():
    d = StarLayerDataset()
    d.parse(data='<http://g> { <http://a> <http://p> "x" }', format="trig")
    text = d.serialize(format="json-ld")
    h = StarLayerDataset()
    h.parse(data=text, format="json-ld")
    assert [q.graph_name for q in h.store] == [ox.NamedNode("http://g")]


def _serve(body: bytes):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/turtle")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_parse_url_uses_location_as_base():
    srv = _serve(b"<a> <p> <b> .\n")
    try:
        g = StarLayerGraph()
        g.parse(f"http://127.0.0.1:{srv.server_port}/dir/doc.ttl")
        assert [t[0].value for t in g.triples((None, None, None))] == [f"http://127.0.0.1:{srv.server_port}/dir/a"]
    finally:
        srv.shutdown()


def test_parse_local_file_uses_location_as_base(tmp_path):
    p = tmp_path / "d.ttl"
    p.write_text("<a> <p> <b> .\n")
    expected = (tmp_path / "a").as_uri()
    g = StarLayerGraph()
    g.parse(str(p))
    assert [t[0].value for t in g.triples((None, None, None))] == [expected]
    h = StarLayerGraph()
    h.parse(p.as_uri())
    assert [t[0].value for t in h.triples((None, None, None))] == [expected]
    k = StarLayerGraph()
    k.parse(str(p), base="http://x/")  # an explicit base still wins
    assert [t[0].value for t in k.triples((None, None, None))] == ["http://x/a"]


@pytest.mark.parametrize("pfx", ["1a", "a b", "a:b"])
def test_serialize_invalid_prefix_name_gives_parseable_turtle(pfx):
    g = StarLayerGraph()
    g.parse(data='<http://e/a> <http://e/p> "x" .', format="turtle")
    try:
        text = g.serialize(prefixes={pfx: "http://e/"})
    except ValueError:
        return
    StarLayerGraph().parse(data=text, format="turtle")


def test_serialize_invalid_prefix_name_from_constructor():
    g = StarLayerGraph(prefixes={"1a": "http://e/"})
    g.parse(data='<http://e/a> <http://e/p> "x" .', format="turtle")
    try:
        text = g.serialize()
    except ValueError:
        return
    StarLayerGraph().parse(data=text, format="turtle")


def test_pretty_trig_blank_graph_names_order_independent():
    A, P, B = ox.NamedNode("http://e/a"), ox.NamedNode("http://e/p"), ox.NamedNode("http://e/b")
    g1, g2 = ox.BlankNode("g1"), ox.BlankNode("g2")
    q1 = ox.Quad(A, P, ox.Literal("one"), g1)
    q2 = ox.Quad(B, P, ox.Literal("two"), g2)

    def text(order):
        d = StarLayerDataset()
        for q in order:
            d.store.add(q)
        return d.serialize(format="trig", pretty=True)

    assert text([q1, q2]) == text([q2, q1])


def test_triple_term_eq_invalid_tuple():
    tt = TripleTerm(ox.NamedNode("http://a"), ox.NamedNode("http://p"), ox.Literal("o"))
    assert (tt == ("not", "a", "triple")) is False
    assert tt not in [("x", "y", "z")]
    assert tt == (ox.NamedNode("http://a"), ox.NamedNode("http://p"), ox.Literal("o"))


def _warns(q):
    g = StarLayerGraph()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        g.query(q)
    return [str(x.message) for x in w]


def test_version_1_2_basic_allows_directional_literal():
    assert not _warns('VERSION "1.2-basic" SELECT * WHERE { ?s ?p "x"@en--ltr }')


def test_version_1_1_arithmetic_double_minus_is_not_a_directional_literal():
    assert not _warns('VERSION "1.1" SELECT ?x WHERE { BIND(5--3 AS ?x) }')


def test_version_1_1_still_warns_for_directional_literal():
    assert _warns('VERSION "1.1" SELECT * WHERE { ?s ?p "x"@en--ltr }')


def test_pretty_keep_bnode_labels_no_collision():
    P, Q, Z = ox.NamedNode("http://e/p"), ox.NamedNode("http://e/q"), ox.NamedNode("http://e/z")
    odd, b0 = ox.BlankNode("a:b"), ox.BlankNode("b0")
    triples = [ox.Triple(odd, P, ox.Literal("odd")), ox.Triple(b0, P, ox.Literal("zero")),
               ox.Triple(Z, P, odd), ox.Triple(Z, Q, odd), ox.Triple(Z, P, b0), ox.Triple(Z, Q, b0)]
    txt = pretty_turtle(triples, keep_bnode_labels=True)
    back = list(ox.parse(txt, format=ox.RdfFormat.TURTLE))
    assert len({t.subject for t in back if isinstance(t.subject, ox.BlankNode)}) == 2


@pytest.mark.parametrize("tail", ["en--up", "--ltr", "en--", "--"])
def test_decode_dirlangstring_malformed_is_none(tail):
    assert decode_dirlangstring(ox.Literal("x", datatype=ox.NamedNode(DIRLANG_NS + tail))) is None


def test_decode_dirlangstring_valid():
    r = decode_dirlangstring(ox.Literal("x", datatype=ox.NamedNode(DIRLANG_NS + "en--ltr")))
    assert r == DirLangString("x", "en", "ltr")


def test_only_used_keeps_prefix_after_escaped_apostrophe():
    g = StarLayerGraph()
    g.add((ox.NamedNode("http://b.org/it's"), ox.NamedNode("http://a.org/p"), ox.Literal("it's")))
    text = g.serialize(format="turtle", prefixes={"a": "http://a.org/", "b": "http://b.org/"}, only_used=True)
    h = StarLayerGraph()
    h.parse(data=text, format="turtle")
    assert set(h.triples((None, None, None))) == set(g.triples((None, None, None)))


@pytest.mark.parametrize("kw", [{"base": "http://e/a b"}, {"prefixes": {"x": "http://e/a b"}}, {"prefixes": {"x": "rel/"}}])
def test_pretty_invalid_base_or_namespace_raises(kw):
    g = StarLayerGraph()
    g.add((ox.NamedNode("http://e/s"), ox.NamedNode("http://e/p"), ox.Literal("x")))
    with pytest.raises(ValueError):
        g.serialize(format="turtle", pretty=True, **kw)


def test_xml_blank_node_label_not_ncname_round_trips():
    g = StarLayerGraph()
    n = ox.BlankNode("1")
    g.add((n, ox.NamedNode("http://e/p"), n))
    text = g.serialize(format="xml")
    h = StarLayerGraph()
    h.parse(data=text, format="xml")
    ((s, _, o),) = h.triples((None, None, None))
    assert s == o and isinstance(s, ox.BlankNode)


def test_xml_non_utf8_encoding_declaration_matches():
    g = StarLayerGraph()
    g.parse(data='<http://e/a> <http://e/p> "café" .', format="turtle")
    buf = io.BytesIO()
    g.serialize(buf, format="xml", encoding="latin-1")
    root = ET.fromstring(buf.getvalue())
    assert "café" in "".join(root.itertext())


def test_dirlangstring_pickle_and_copy():
    d = DirLangString("x", "en", "ltr")
    assert pickle.loads(pickle.dumps(d)) == d
    assert copy.copy(d) == d
    assert copy.deepcopy(d) == d
