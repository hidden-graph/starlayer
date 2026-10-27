"""Parser/serializer round trips, prefixes and @base (GitHub issues #132 and #133, third hunt)."""

from __future__ import annotations

import io

import pytest
from rdflib import BNode, Literal, URIRef
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.compare import isomorphic
from starlayer.graph.model.triple import TripleTerm

pytestmark = pytest.mark.graph

_RR = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")


def _e(name: str) -> URIRef:
    return URIRef("http://e/" + name)


def _quads(ds: StarLayerDataset) -> set[tuple[str, str, str, str]]:
    return {(str(s), str(p), str(o), str(c.identifier)) for c in ds.contexts() for s, p, o in c}


# --- @base, publicID and relative namespaces in TriG / Turtle (#132)


@pytest.mark.parametrize("form", ["<g> { <a> <b> <c> }", "GRAPH <g> { <a> <b> <c> }"])
@pytest.mark.parametrize("directive", ["@base <http://ex.org/dir/> .", "BASE <http://ex.org/dir/>"])
def test_trig_graph_block_resolves_against_base(form: str, directive: str) -> None:
    ds = StarLayerDataset().parse(data=f"{directive}\n{form}\n", format="trig12")
    d = "http://ex.org/dir/"
    assert _quads(ds) == {(d + "a", d + "b", d + "c", d + "g")}


def test_trig_dot_dot_reference_in_a_graph_block() -> None:
    ds = StarLayerDataset().parse(data="@base <http://ex.org/dir/> .\nGRAPH <h> { <a> <b> <../c> }", format="trig12")
    assert ("http://ex.org/dir/a", "http://ex.org/dir/b", "http://ex.org/c", "http://ex.org/dir/h") in _quads(ds)


def test_base_changes_between_blocks() -> None:
    text = "@base <http://one/> .\n<g> { <a> <p> <b> }\n@base <http://two/> .\n<g> { <a> <p> <b> }\n"
    quads = _quads(StarLayerDataset().parse(data=text, format="trig12"))
    assert ("http://one/a", "http://one/p", "http://one/b", "http://one/g") in quads
    assert ("http://two/a", "http://two/p", "http://two/b", "http://two/g") in quads


def test_trig_on_a_graph_uses_base_too() -> None:
    g = StarLayerGraph().parse(data="@base <http://ex.org/dir/> .\n<a> <b> <c> .", format="trig12")
    assert set(g) == {(URIRef("http://ex.org/dir/a"), URIRef("http://ex.org/dir/b"), URIRef("http://ex.org/dir/c"))}


def test_public_id_is_the_base_for_trig_on_a_graph_and_a_dataset() -> None:
    expected = (URIRef("http://pub.org/x/a"), URIRef("http://pub.org/x/p"), URIRef("http://pub.org/b"))
    g = StarLayerGraph().parse(data="<a> <p> <../b> .", format="trig12", publicID="http://pub.org/x/")
    assert set(g) == {expected}
    for fmt in ("trig12", "turtle12"):
        ds = StarLayerDataset().parse(data="<a> <p> <../b> .", format=fmt, publicID="http://pub.org/x/")
        assert set(ds.default_graph) == {expected}


def test_public_id_resolves_a_graph_name() -> None:
    ds = StarLayerDataset().parse(data="<g> { <a> <p> <b> }", format="trig12", publicID="http://pub.org/x/")
    assert _quads(ds) == {("http://pub.org/x/a", "http://pub.org/x/p", "http://pub.org/x/b", "http://pub.org/x/g")}


@pytest.mark.parametrize("fmt", ["turtle12", "trig12"])
def test_relative_prefix_namespace_keeps_its_fragment_separator(fmt: str) -> None:
    data = "@base <http://b/x/y> .\n@prefix r: <#> .\nr:a r:b r:c ."
    g = StarLayerGraph().parse(data=data, format=fmt)
    assert set(g) == {(URIRef("http://b/x/y#a"), URIRef("http://b/x/y#b"), URIRef("http://b/x/y#c"))}


def test_relative_prefix_namespace_in_a_trig_graph_block_and_name() -> None:
    ds = StarLayerDataset().parse(data="@base <http://b/x/y> .\n@prefix r: <#> .\nr:g { r:a r:b r:c }", format="trig12")
    assert _quads(ds) == {("http://b/x/y#a", "http://b/x/y#b", "http://b/x/y#c", "http://b/x/y#g")}


def test_prefix_name_with_an_interior_dot_parses() -> None:
    for text in ("@prefix a.b: <http://e/> . a.b:x a.b:p a.b:y .", "PREFIX a.b: <http://e/>\na.b:x a.b:p a.b:y ."):
        assert len(StarLayerGraph().parse(data=text, format="turtle12")) == 1
    ds = StarLayerDataset().parse(data="@prefix a.b: <http://e/> . a.b:g { a.b:x a.b:p a.b:y }", format="trig12")
    assert _quads(ds) == {("http://e/x", "http://e/p", "http://e/y", "http://e/g")}


# --- writers and prefixes that are not valid names (#132)

_BAD_PREFIXES = ["x.", "a:b", "1x", "_", "-x", "xml", "xmlns"]


@pytest.mark.parametrize("prefix", _BAD_PREFIXES)
@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12", "trig12"])
def test_turtle_writers_survive_a_prefix_that_is_not_a_pn_prefix(prefix: str, fmt: str) -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind(prefix, "http://ex.org/", override=True)
    g.add((URIRef("http://ex.org/a"), URIRef("http://ex.org/p"), URIRef("http://ex.org/b")))
    g.add((URIRef("http://ex.org/a"), URIRef("http://ex.org/q"), Literal(1)))
    out = g.serialize(format=fmt)
    if prefix not in ("xml", "xmlns"):  # these two are valid in Turtle
        assert f"@prefix {prefix}:" not in out
    assert set(StarLayerGraph().parse(data=out, format=fmt)) == set(g)


def test_underscore_prefix_does_not_turn_iris_into_blank_nodes() -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind("_", "http://ex.org/")
    g.add((URIRef("http://ex.org/a"), URIRef("http://ex.org/p"), URIRef("http://ex.org/b")))
    back = StarLayerGraph().parse(data=g.serialize(format="turtle12"), format="turtle12")
    assert set(back) == set(g)


@pytest.mark.parametrize("prefix", ["1x", "-x", "a:b", "xml", "xmlns", "x."])
def test_rdfxml_writer_survives_a_prefix_that_is_not_an_ncname(prefix: str) -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind(prefix, "http://ex.org/ns/", override=True)
    g.add((URIRef("http://ex.org/s"), URIRef("http://ex.org/ns/p"), Literal("v")))
    out = g.serialize(format="rdfxml12")
    assert set(StarLayerGraph().parse(data=out, format="rdfxml12")) == set(g)


def test_rdfxml_prefixes_do_not_leak_between_serializations() -> None:
    first = StarLayerGraph(bind_namespaces="none")
    first.bind("old", "http://ex.org/ns/")
    first.add((URIRef("http://ex.org/s"), URIRef("http://ex.org/ns/p"), Literal("v")))
    first.serialize(format="rdfxml12")
    second = StarLayerGraph(bind_namespaces="none")
    second.bind("new", "http://ex.org/ns/")
    second.add((URIRef("http://ex.org/s"), URIRef("http://ex.org/ns/p"), Literal("v")))
    out = second.serialize(format="rdfxml12")
    assert "xmlns:new=" in out and "xmlns:old=" not in out


@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12", "trig12"])
def test_empty_prefix_datatype_keeps_its_colon(fmt: str) -> None:
    g = StarLayerGraph().parse(data='@prefix : <http://e/> . :s :p "x"^^:dt , "y"^^<http://e/dt.z> .', format="turtle12")
    out = g.serialize(format=fmt)
    assert "^^dt" not in out
    assert set(StarLayerGraph().parse(data=out, format=fmt)) == set(g)


@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12", "trig12"])
def test_xsd_prefix_is_declared_for_a_typed_literal_only_inside_a_triple_term(fmt: str) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), TripleTerm(_e("b"), _e("p"), Literal(1))))
    out = g.serialize(format=fmt)
    assert set(StarLayerGraph().parse(data=out, format=fmt)) == set(g)
    nested = StarLayerGraph()
    nested.add((_e("s"), _e("p"), TripleTerm(_e("b"), _e("p"), TripleTerm(_e("c"), _e("d"), Literal(2.5)))))
    assert set(StarLayerGraph().parse(data=nested.serialize(format=fmt), format=fmt)) == set(nested)


def test_rebinding_a_prefix_after_a_serialize_uses_the_new_name() -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind("g", "http://g.org/")
    g.add((URIRef("http://g.org/a"), URIRef("http://g.org/p"), Literal("x")))
    g.serialize(format="turtle12")
    g.bind("h", "http://g.org/", override=True, replace=True)
    for fmt in ("turtle12", "longturtle12"):
        out = g.serialize(format=fmt)
        assert "h:a" in out and "g:a" not in out


def test_rebinding_a_prefix_to_another_namespace_still_parses_back() -> None:
    ds = StarLayerDataset(bind_namespaces="none")
    ds.bind("g", "http://g.org/")
    ds.graph(URIRef("http://g.org/n")).add((URIRef("http://g.org/a"), URIRef("http://g.org/p"), Literal("x")))
    ds.serialize(format="trig12")
    ds.bind("g", "http://other.org/", override=True, replace=True)
    out = ds.serialize(format="trig12")
    assert _quads(StarLayerDataset().parse(data=out, format="trig12")) == _quads(ds)


@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12", "trig12"])
def test_dirlangstring_in_a_nested_triple_term(fmt: str) -> None:
    text = '@prefix : <http://e/> . :s :p <<( :a :b <<( :x :y "l"@en--ltr )>> )>> .'
    g = StarLayerGraph().parse(data=text, format="turtle12")
    out = g.serialize(format=fmt)
    assert "dirlang" not in out and "@en--ltr" in out
    assert set(StarLayerGraph().parse(data=out, format=fmt)) == set(g)


def test_reifier_also_inside_a_triple_term_is_not_folded() -> None:
    b = BNode("r")
    g = StarLayerGraph()
    g.add((b, _RR, TripleTerm(_e("a"), _e("q"), _e("c"))))
    g.add((_e("s"), _e("p"), TripleTerm(b, _e("q"), _e("c"))))
    h = StarLayerGraph()
    h.add((b, _RR, TripleTerm(_e("a"), _e("q"), Literal("x"))))
    h.add((b, _e("p"), TripleTerm(b, _e("q"), _e("c"))))
    for graph in (g, h):
        for fmt in ("turtle12", "trig12"):
            assert isomorphic(graph, StarLayerGraph().parse(data=graph.serialize(format=fmt), format=fmt))


# --- used_prefixes / reduce_prefixes (#132)


def test_used_prefixes_agrees_with_the_writer_for_reifiers_and_lists() -> None:
    annotated = StarLayerGraph().parse(data="@prefix ex: <http://e/> . ex:a ex:p ex:b {| ex:q ex:c |} .", format="turtle12")
    assert [p for p, _ in annotated.used_prefixes()] == ["ex"]
    assert [p for p, _ in annotated.reduce_prefixes().namespaces()] == ["ex"]
    listed = StarLayerGraph().parse(data="@prefix ex: <http://e/> . ex:a ex:p (1 2 ex:c) .", format="turtle12")
    assert [p for p, _ in listed.used_prefixes()] == ["ex"]
    typed = StarLayerGraph().parse(data='@prefix ex: <http://e/> . ex:a ex:p "1"^^<http://www.w3.org/2001/XMLSchema#byte> .', format="turtle12")
    assert "xsd" in [p for p, _ in typed.used_prefixes()]


def test_reduce_prefixes_keep_is_a_name_not_a_set_of_characters() -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.bind("ex", "http://ex.org/")
    g.bind("e", "http://e.org/")
    g.bind("x", "http://x.org/")
    assert [p for p, _ in g.reduce_prefixes(keep="ex").namespaces()] == ["ex"]
    assert list(g.reduce_prefixes(keep=None).namespaces()) == []
    assert [p for p, _ in g.reduce_prefixes(keep=["e", "x"]).namespaces()] == ["e", "x"]


def test_no_internal_bindings_with_bind_namespaces_none() -> None:
    doc = "@prefix q: <http://q/> . q:a q:b q:c ."
    g = StarLayerGraph(bind_namespaces="none").parse(data=doc, format="turtle12")
    assert [p for p, _ in g.namespaces()] == ["q"]
    d = StarLayerDataset(bind_namespaces="none").parse(data=doc, format="trig12")
    assert [p for p, _ in d.namespaces()] == ["q"]
    tt = StarLayerGraph(bind_namespaces="none").parse(data="@prefix q: <http://q/> . q:a q:b <<( q:c q:d q:e )>> .", format="turtle12")
    assert [p for p, _ in tt.namespaces()] == ["q"]


# --- control characters (#133)

_CONTROL = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x00", "\x01", "\x1f", "\x85", " ", " "]


@pytest.mark.parametrize("char", _CONTROL)
@pytest.mark.parametrize("fmt", ["nt12", "nq12", "turtle12", "longturtle12", "trig12"])
def test_control_characters_round_trip_in_line_formats(char: str, fmt: str) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal(f"a{char}b")))
    out = g.serialize(format=fmt)
    assert char not in out
    assert {str(o) for _s, _p, o in StarLayerGraph().parse(data=out, format=fmt)} == {f"a{char}b"}


@pytest.mark.parametrize("char", ["\x0b", "\x0c", "\x1c", "\x85", " "])
def test_nt_parser_splits_lines_on_cr_and_lf_only(char: str) -> None:
    data = f'<http://e/s> <http://e/p> "a{char}b" .\n<http://e/s> <http://e/p> "c" .\r\n'
    assert len(StarLayerGraph().parse(data=data, format="nt12")) == 2
    quads = data.replace(" .\n", " <http://e/g> .\n").replace(" .\r\n", " <http://e/g> .\r\n")
    assert len(StarLayerGraph().parse(data=quads, format="nq12")) == 2


def test_dataset_trig_keeps_a_control_character_in_a_literal() -> None:
    ds = StarLayerDataset()
    ds.graph(_e("g")).add((_e("s"), _e("p"), Literal("a\x0cb c")))
    back = StarLayerDataset().parse(data=ds.serialize(format="trig12"), format="trig12")
    assert {str(o) for c in back.contexts() for _s, _p, o in c} == {"a\x0cb c"}


@pytest.mark.parametrize("char", ["\x00", "\x08", "\x0b", "\x0c", "\x1f"])
@pytest.mark.parametrize("fmt", ["trix12", "rdfxml12"])
def test_xml_writers_refuse_a_character_xml_cannot_carry(char: str, fmt: str) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal(f"a{char}b")))
    with pytest.raises(ValueError, match="XML 1.0"):
        g.serialize(format=fmt)
    ds = StarLayerDataset()
    ds.graph(_e("g")).add((_e("s"), _e("p"), Literal(f"a{char}b")))
    if fmt == "trix12":
        with pytest.raises(ValueError, match="XML 1.0"):
            ds.serialize(format=fmt)


def test_xml_writers_still_write_tab_newline_and_cr() -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal("a\tb\nc\rd")))
    for fmt in ("trix12", "rdfxml12"):
        assert {str(o) for _s, _p, o in StarLayerGraph().parse(data=g.serialize(format=fmt), format=fmt)} == {"a\tb\nc\rd"}


# --- bytes in, bytes out, base (#133, #132)

_NT = b"<http://e/s> <http://e/p> <http://e/o> ."


@pytest.mark.parametrize("fmt", ["nt12", "turtle12", "longturtle12", "trig12"])
def test_parse_accepts_bytes_and_binary_streams(fmt: str) -> None:
    assert len(StarLayerGraph().parse(data=_NT, format=fmt)) == 1
    assert len(StarLayerGraph().parse(source=io.BytesIO(_NT), format=fmt)) == 1
    assert len(StarLayerGraph().parse(file=io.BytesIO(_NT), format=fmt)) == 1
    assert len(StarLayerDataset().parse(data=_NT, format="trig12")) == 1


def test_parse_accepts_utf8_bytes_with_a_byte_order_mark() -> None:
    data = b'\xef\xbb\xbf<http://e/s> <http://e/p> "caf\xc3\xa9" .'
    assert [str(o) for _s, _p, o in StarLayerGraph().parse(data=data, format="nt12")] == ["café"]


@pytest.mark.parametrize("fmt", ["turtle12", "nt12", "rdfxml12"])
def test_serialize_encoding_gives_bytes(fmt: str) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal("café")))
    out = g.serialize(format=fmt, encoding="utf-8")
    assert isinstance(out, bytes)
    assert out.decode("utf-8") == g.serialize(format=fmt)
    ds = StarLayerDataset()
    ds.graph(_e("g")).add((_e("s"), _e("p"), Literal("x")))
    assert isinstance(ds.serialize(format="nq12", encoding="utf-8"), bytes)


def test_serialize_destination_may_be_a_stream_or_a_path(tmp_path) -> None:
    g = StarLayerGraph()
    g.add((_e("s"), _e("p"), Literal("café")))
    binary = io.BytesIO()
    assert g.serialize(destination=binary, format="nt12") is g
    assert binary.getvalue().decode("utf-8") == g.serialize(format="nt12")
    text = io.StringIO()
    g.serialize(destination=text, format="turtle12")
    assert text.getvalue() == g.serialize(format="turtle12")
    path = tmp_path / "out.ttl"
    g.serialize(destination=str(path), format="turtle12", encoding="utf-8")
    assert path.read_text(encoding="utf-8") == g.serialize(format="turtle12")
    ds = StarLayerDataset()
    ds.graph(_e("g")).add((_e("s"), _e("p"), Literal("x")))
    sink = io.BytesIO()
    ds.serialize(destination=sink, format="trig12")
    assert sink.getvalue().decode("utf-8") == ds.serialize(format="trig12")


@pytest.mark.parametrize("fmt", ["turtle12", "longturtle12", "trig12"])
def test_serialize_base_is_honoured_and_round_trips(fmt: str) -> None:
    g = StarLayerGraph(bind_namespaces="none")
    g.add((URIRef("http://e.org/a"), URIRef("http://e.org/p"), URIRef("http://e.org/dir/b")))
    g.add((URIRef("http://e.org/a"), URIRef("http://e.org/p"), URIRef("http://other.org/c")))
    g.add((URIRef("http://e.org/a"), URIRef("http://e.org/p"), URIRef("http://e.org/dir/")))  # no prefixed name: written as <dir/>
    out = g.serialize(format=fmt, base="http://e.org/")
    assert "@base <http://e.org/> ." in out and "<dir/>" in out
    assert set(StarLayerGraph().parse(data=out, format=fmt)) == set(g)
    ds = StarLayerDataset(bind_namespaces="none")
    ds.graph(URIRef("http://e.org/n")).add((URIRef("http://e.org/a"), URIRef("http://e.org/p"), URIRef("http://e.org/dir/b")))
    assert "@base <http://e.org/> ." in ds.serialize(format="trig12", base="http://e.org/")
