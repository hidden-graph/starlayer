"""Gaps found by the B1 classification (``docs/working/b1-classification.md``, branch ``mig-b1-gaps``): pickle and deepcopy,
``from_rdflib`` / ``to_rdflib``, the ``VERSION`` line on write, the basic encoding on a plain ``turtle`` parse, exception types
and the SHACL report. Each is a property of ``OxGraph`` / ``OxDataset`` alone."""

from __future__ import annotations

import copy
import pickle

import pyoxigraph as ox
import pytest
from starlayer.graph import interop
from starlayer.graph.oxgraph import OxDataset, OxGraph

EX = "http://example.org/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

DOC12 = f"""@prefix : <{EX}> .
:a :p :b .
:a :q <<( :x :y :z )>> .
:a :r "x"@en--ltr .
_:n :p "plain" .
"""

TRIG12 = f"""@prefix : <{EX}> .
:a :p :b .
GRAPH :g1 {{ :a :q <<( :x :y :z )>> . _:n :p "x"@ar--rtl }}
GRAPH :g2 {{ :c :p :d }}
"""


def _graph() -> OxGraph:
    g = OxGraph()
    g.parse(data=DOC12, format="turtle")
    g.bind("ex", EX)
    return g


def _dataset(union: bool = True) -> OxDataset:
    d = OxDataset(default_union=union)
    d.parse(data=TRIG12, format="trig")
    d.store.add_graph(ox.NamedNode(EX + "empty"))
    d.bind("ex", EX)
    return d


def _quads(x) -> set:
    return set(x.store) if isinstance(x, OxDataset) else set(x.quads())


# ---- O2: pickle, copy.copy, copy.deepcopy -----------------------------------------------------------------------------------


@pytest.mark.parametrize("clone", [lambda x: pickle.loads(pickle.dumps(x)), copy.deepcopy, copy.copy],
                         ids=["pickle", "deepcopy", "copy"])
class TestRoundTrip:
    def test_graph_with_triple_term_and_prefixes(self, clone):
        g = _graph()
        c = clone(g)
        assert isinstance(c, OxGraph) and c is not g and c.store is not g.store
        assert _quads(c) == _quads(g)
        assert any(isinstance(o, ox.Triple) for _, _, o in c.triples())
        assert c.prefixes == g.prefixes and c.prefixes is not g.prefixes
        assert c.identifier == g.identifier

    def test_blank_node_labels_survive(self, clone):
        g = _graph()
        assert {s for s, _, _ in clone(g).triples() if isinstance(s, ox.BlankNode)} == {
            s for s, _, _ in g.triples() if isinstance(s, ox.BlankNode)}

    def test_named_graph_view_keeps_its_identifier_and_only_its_triples(self, clone):
        d = _dataset()
        view = d.graph(EX + "g1")
        c = clone(view)
        assert c.identifier == ox.NamedNode(EX + "g1")
        assert len(c) == len(view) == 2
        assert {q.graph_name for q in c.quads()} == {ox.NamedNode(EX + "g1")}

    def test_copy_is_independent(self, clone):
        g = _graph()
        c = clone(g)
        n = len(g)
        c.add((ox.NamedNode(EX + "s"), ox.NamedNode(EX + "p"), ox.NamedNode(EX + "o")))
        c.bind("zz", "http://zz/")
        assert len(g) == n and "zz" not in g.prefixes

    @pytest.mark.parametrize("union", [True, False])
    def test_dataset(self, clone, union):
        d = _dataset(union)
        c = clone(d)
        assert isinstance(c, OxDataset) and c.store is not d.store
        assert _quads(c) == _quads(d)
        assert set(c.store.named_graphs()) == set(d.store.named_graphs())
        assert ox.NamedNode(EX + "empty") in set(c.store.named_graphs())  # an empty named graph has no quad
        assert c.default_union is union
        assert c.prefixes == d.prefixes and c.prefixes is not d.prefixes
        assert len(c) == len(d)
        assert any(isinstance(q.object, ox.Triple) for q in c.store)

    def test_dataset_graph_names_and_directions(self, clone):
        c = clone(_dataset())
        assert {str(n) for n in c.graph_names()} >= {f"<{EX}g1>", f"<{EX}g2>", f"<{EX}empty>"}
        assert any(q.object == ox.Literal("x", language="ar", direction=ox.BaseDirection.RTL) for q in c.store)

    def test_a_clone_is_a_working_graph(self, clone):
        c = clone(_dataset())
        rows = list(c.query(f"SELECT ?o WHERE {{ GRAPH <{EX}g2> {{ ?s ?p ?o }} }}"))
        assert [str(r["o"]) for r in rows] == [f"<{EX}d>"]
        assert c.serialize(format="nq").count(" .\n") == len(c.store)


def test_pickle_protocols_and_nested_use():
    d = _dataset()
    for proto in range(2, pickle.HIGHEST_PROTOCOL + 1):
        assert _quads(pickle.loads(pickle.dumps(d, protocol=proto))) == _quads(d)
    both = pickle.loads(pickle.dumps({"g": _graph(), "d": d}))  # inside another structure, with shared members
    assert isinstance(both["g"], OxGraph) and isinstance(both["d"], OxDataset)


def test_deepcopy_of_a_graph_opened_with_a_path_is_an_in_memory_copy(tmp_path):
    g = OxGraph(path=tmp_path / "db")
    g.parse(data=DOC12, format="turtle")
    c = copy.deepcopy(g)
    assert c._path is None and _quads(c) == _quads(g)
    ds = OxDataset(path=tmp_path / "db2")
    ds.parse(data=TRIG12, format="trig")
    assert _quads(copy.copy(ds)) == _quads(ds) and copy.copy(ds)._path is None


def test_pickle_of_a_graph_opened_with_a_path_is_refused(tmp_path):
    for obj in (OxGraph(path=tmp_path / "a"), OxDataset(path=tmp_path / "b")):
        with pytest.raises(TypeError, match="on-disk store.*\\.copy\\(\\)"):
            pickle.dumps(obj)
    # the refusal does not damage the object, and its .copy() pickles
    g = OxGraph(path=tmp_path / "c")
    g.parse(data=DOC12, format="turtle")
    with pytest.raises(TypeError):
        pickle.dumps(g)
    assert _quads(pickle.loads(pickle.dumps(g.copy()))) == _quads(g)


def test_copy_method_keeps_the_identifier():
    view = _dataset().graph(EX + "g1")
    assert view.copy().identifier == view.identifier


# ---- B2 / O6: from_rdflib, to_rdflib ----------------------------------------------------------------------------------------


class TestFromRdflib:
    def test_graph(self):
        import rdflib
        from rdflib import Literal, URIRef

        r = rdflib.Graph()
        r.bind("ex", EX)
        r.add((URIRef(EX + "a"), URIRef(EX + "p"), Literal("v", lang="en")))
        r.add((URIRef(EX + "a"), URIRef(EX + "q"), Literal(5)))
        g = OxGraph.from_rdflib(r)
        assert isinstance(g, OxGraph) and len(g) == 2
        assert g.prefixes["ex"] == EX
        assert (ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.Literal("v", language="en")) in g
        assert g.identifier == ox.DefaultGraph()
        r.add((URIRef(EX + "a"), URIRef(EX + "z"), Literal("late")))
        assert len(g) == 2  # a copy

    def test_graph_with_an_iri_identifier(self):
        import rdflib
        from rdflib import URIRef

        r = rdflib.Graph(identifier=URIRef(EX + "ident"))
        r.add((URIRef(EX + "a"), URIRef(EX + "p"), URIRef(EX + "b")))
        assert OxGraph.from_rdflib(r).identifier == ox.NamedNode(EX + "ident")


    def test_an_ox_graph_is_copied(self):
        g = _graph()
        c = OxGraph.from_rdflib(g)
        assert c is not g and _quads(c) == _quads(g)
        with pytest.raises(TypeError, match="rdflib graph"):
            OxGraph.from_rdflib(_dataset())

    def test_dataset(self):
        import rdflib
        from rdflib import Literal, URIRef

        r = rdflib.Dataset(default_union=True)
        r.default_graph.add((URIRef(EX + "a"), URIRef(EX + "p"), URIRef(EX + "b")))
        r.graph(URIRef(EX + "g1")).add((URIRef(EX + "c"), URIRef(EX + "p"), Literal("x")))
        r.graph(URIRef(EX + "empty"))
        r.bind("ex", EX)
        d = OxDataset.from_rdflib(r)
        assert d.default_union is True
        assert set(d.store.named_graphs()) == {ox.NamedNode(EX + "g1"), ox.NamedNode(EX + "empty")}
        assert len(d.store) == 2 and d.prefixes["ex"] == EX
        assert ox.Quad(ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.NamedNode(EX + "b"), ox.DefaultGraph()) in d.store
        assert OxDataset.from_rdflib(rdflib.Dataset()).default_union is False

    def test_dataset_from_a_plain_graph_and_from_an_ox_dataset(self):
        import rdflib
        from rdflib import URIRef

        r = rdflib.Graph(identifier=URIRef(EX + "ident"))
        r.add((URIRef(EX + "a"), URIRef(EX + "p"), URIRef(EX + "b")))
        d = OxDataset.from_rdflib(r)
        assert list(d.store.named_graphs()) == [] and len(d.store) == 1
        src = _dataset()
        c = OxDataset.from_rdflib(src)
        assert c is not src and c.store is not src.store and _quads(c) == _quads(src)

    def test_an_illegal_term_is_an_error(self):
        import rdflib
        from rdflib import URIRef
        from starlayer.shacl_engine.terms import TermError

        r = rdflib.Graph()
        r.add((URIRef("not an iri"), URIRef(EX + "p"), URIRef(EX + "b")))
        with pytest.raises(TermError):
            OxGraph.from_rdflib(r)


class TestToRdflib:
    def test_graph_presents_rdf12_as_rdf11(self):
        import rdflib
        from rdflib import URIRef

        g = _graph()
        r = g.to_rdflib()
        assert type(r) is rdflib.Graph
        assert r.namespace_manager.store.namespace("ex") == URIRef(EX)
        # the triple term is the basic encoding: a blank node described by rdf:PropositionForm
        forms = list(r.subjects(URIRef(RDF + "type"), URIRef(RDF + "PropositionForm")))
        assert len(forms) == 1
        assert (None, URIRef(RDF + "propositionFormSubject"), URIRef(EX + "x")) in r
        # the directional literal is its datatype-IRI form
        objs = [o for o in r.objects(URIRef(EX + "a"), URIRef(EX + "r"))]
        assert len(objs) == 1 and str(objs[0]) == "x" and str(objs[0].datatype).startswith(interop.DIRLANG_NS)
        # no triple term and no directional literal survives
        assert all(type(t).__name__ != "TripleTerm" for tr in r for t in tr)

    def test_equals_the_interop_encoding(self):
        g = _graph()
        r = g.to_rdflib(bnode_prefix="tt")
        expected = interop.to_rdf11(list(g.quads()), bnode_prefix="tt")
        assert len(r) == len(expected)
        assert {str(s) for s in r.subjects() if str(s).startswith("tt")} == {"tt0"}

    def test_graph_without_rdf12_is_unchanged(self):
        import rdflib

        g = OxGraph()
        g.parse(data=f"@prefix : <{EX}> . :a :p :b, 7 .", format="turtle")
        r = g.to_rdflib()
        assert isinstance(r, rdflib.Graph) and len(r) == 2

    def test_named_graph_view_keeps_its_identifier(self):
        from rdflib import URIRef

        r = _dataset().graph(EX + "g1").to_rdflib()
        assert r.identifier == URIRef(EX + "g1")

    def test_dataset(self):
        import rdflib
        from rdflib import URIRef

        d = _dataset(union=False)
        r = d.to_rdflib()
        assert isinstance(r, rdflib.Dataset) and r.default_union is False
        assert {g.identifier for g in r.graphs()} >= {URIRef(EX + "g1"), URIRef(EX + "g2"), URIRef(EX + "empty")}
        assert len(r.graph(URIRef(EX + "g2"))) == 1
        # g1 holds `:a :q <<( :x :y :z )>>` (the triple and the 4-triple encoding) and `_:n :p "x"@ar--rtl`: 1 + 4 + 1 triples
        assert len(r.graph(URIRef(EX + "g1"))) == 6

    def test_round_trip_restores_directions_not_triple_terms(self):
        g = _graph()
        back = OxGraph.from_rdflib(g.to_rdflib())
        assert (ox.NamedNode(EX + "a"), ox.NamedNode(EX + "r"),
                ox.Literal("x", language="en", direction=ox.BaseDirection.LTR)) in back
        assert not any(isinstance(o, ox.Triple) for _, _, o in back.triples())
        # interop.from_basic turns the encoding back into the triple term
        assert interop.has_triple_terms(interop.from_basic(list(back.quads())))


# ---- O3: the VERSION line on write; no RDF12ConformanceWarning ----------------------------------------------------------------

_FORMATS = {"turtle": '@version "1.2" .', "trig": '@version "1.2" .', "nt": 'VERSION "1.2"', "nq": 'VERSION "1.2"'}


@pytest.mark.parametrize("fmt", list(_FORMATS))
class TestVersionLine:
    def test_written_when_the_data_has_a_triple_term_or_a_direction(self, fmt):
        for data in (f"@prefix : <{EX}> . :a :q <<( :x :y :z )>> .", f'@prefix : <{EX}> . :a :q "x"@en--ltr .', DOC12):
            g = OxGraph()
            g.parse(data=data, format="turtle")
            text = g.serialize(format=fmt)
            assert text.startswith(_FORMATS[fmt] + "\n")
            assert text.count("VERSION") + text.count("@version") == 1

    def test_not_written_for_rdf11_data_unless_asked(self, fmt):
        g = OxGraph()
        g.parse(data=f'@prefix : <{EX}> . :a :p :b, "s", "t"@en, 4 .', format="turtle")
        assert "VERSION" not in g.serialize(format=fmt) and "@version" not in g.serialize(format=fmt)
        asked = g.serialize(format=fmt, rdf_version="1.2")
        assert asked.startswith(_FORMATS[fmt] + "\n")
        assert g.serialize(format=fmt, rdf_version=None).count("ersion") == 0

    def test_a_literal_that_looks_like_a_triple_term_is_not_one(self, fmt):
        g = OxGraph()
        g.add((ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.Literal("<<( x )>> and @en--ltr")))
        assert "ersion" not in g.serialize(format=fmt)

    def test_never_written_for_rdf_version_1_1(self, fmt):
        assert "ersion" not in _graph().serialize(format=fmt, rdf_version="1.1")
        assert "ersion" not in _graph().serialize(format=fmt, rdf_version="1.1", pretty=fmt in ("turtle", "trig"))

    def test_round_trips_through_the_parser(self, fmt):
        g = _graph()
        for pretty in (False, True) if fmt in ("turtle", "trig") else (False,):
            text = g.serialize(format=fmt, pretty=pretty)
            back = OxGraph()
            back.parse(data=text, format=fmt)
            assert len(back) == len(g)
            assert any(isinstance(o, ox.Triple) for _, _, o in back.triples())
        plain = OxGraph()
        plain.add((ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.NamedNode(EX + "b")))
        again = OxGraph()
        again.parse(data=plain.serialize(format=fmt, rdf_version="1.2"), format=fmt)
        assert len(again) == 1

    def test_dataset_writes_it_for_quad_formats_and_flattened_triple_formats(self, fmt):
        d = _dataset()
        text = d.serialize(format=fmt)
        assert text.startswith(_FORMATS[fmt] + "\n")
        parsed = OxDataset()
        parsed.parse(data=text, format=fmt)
        assert len(parsed.store) > 0


@pytest.mark.parametrize("fmt", ["turtle", "trig"])
def test_pretty_output_has_the_version_line_once(fmt):
    text = _graph().serialize(format=fmt, pretty=True)
    assert text.startswith('@version "1.2" .\n') and text.count("@version") == 1
    assert OxGraph().serialize(format=fmt, pretty=True, rdf_version="1.2").startswith('@version "1.2" .\n')


def test_only_used_prefixes_keeps_the_version_line_first():
    text = _graph().serialize(format="turtle", only_used=True)
    assert text.startswith('@version "1.2" .\n@prefix : ')
    assert "@prefix ex:" not in text


def test_rdf_xml_and_json_ld_have_no_version_line():
    g = OxGraph()
    g.add((ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), ox.NamedNode(EX + "b")))
    for fmt in ("xml", "json-ld"):
        text = g.serialize(format=fmt, rdf_version="1.2")
        assert "VERSION" not in text and "@version" not in text


def test_a_wrong_version_label_is_read_without_a_warning(recwarn):
    # RDF12ConformanceWarning is gone: the label is a hint (RDF 1.2 Concepts 2.1)
    g = OxGraph()
    g.parse(data=f'@version "1.2-basic" .\n@prefix : <{EX}> . :a :q <<( :x :y :z )>> .', format="turtle")
    g.parse(data=f'VERSION "1.1"\n<{EX}a> <{EX}q> <<( <{EX}x> <{EX}y> <{EX}z> )>> .\n', format="nt")
    assert len(g) == 1
    assert not [w for w in recwarn.list if "VERSION" in str(w.message) or "Conformance" in w.category.__name__]


def test_the_rdf_conformance_warning_class_is_gone():
    from starlayer.graph.model import conformance

    assert not hasattr(conformance, "RDF12ConformanceWarning")
    assert hasattr(conformance, "SPARQL12ConformanceWarning")


# ---- O4: a plain turtle parse does not adopt the basic encoding --------------------------------------------------------------

BASIC = f"""@prefix : <{EX}> .
@prefix rdf: <{RDF}> .
:a :q _:b .
_:b a rdf:PropositionForm ; rdf:propositionFormSubject :x ; rdf:propositionFormPredicate :y ; rdf:propositionFormObject :z .
"""


def test_turtle_parse_does_not_adopt_the_basic_encoding():
    g = OxGraph()
    g.parse(data=BASIC, format="turtle")
    assert len(g) == 5
    assert not any(isinstance(o, ox.Triple) for _, _, o in g.triples())
    assert list(g.triples((None, ox.NamedNode(RDF + "type"), ox.NamedNode(RDF + "PropositionForm"))))


def test_from_basic_is_the_way_to_decode_it():
    g = OxGraph()
    g.parse(data=BASIC, format="turtle")
    decoded = interop.from_basic(list(g.quads()))
    assert len(decoded) == 1 and decoded[0].object == ox.Triple(
        ox.NamedNode(EX + "x"), ox.NamedNode(EX + "y"), ox.NamedNode(EX + "z"))


# ---- O5: exception types; no used-graph line in a SHACL report -----------------------------------------------------------------


def test_syntax_errors_are_syntax_error():
    with pytest.raises(SyntaxError):
        OxGraph().parse(data="<a", format="turtle")
    with pytest.raises(SyntaxError):
        OxGraph().update("INSERT DATA {")
    with pytest.raises(SyntaxError):
        OxGraph().query("SELEC * {}")
    with pytest.raises(SyntaxError):  # a blank node shared by two INSERT DATA blocks (SPARQL 1.1 update 3.1.1)
        OxGraph().update("INSERT DATA { _:b <urn:p> 1 } ; INSERT DATA { _:b <urn:p> 2 }")
    with pytest.raises(ValueError):
        OxGraph().parse(data="", format="no-such-format")


_SHAPES = f"""@prefix ex: <{EX}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:n ; sh:minCount 1 ] ."""


def test_shacl_report_on_an_oxgraph_has_no_used_graph_line_unless_the_caller_names_one():
    from starlayer.shacl import validate

    data, shapes = OxGraph(), OxGraph()
    data.parse(data=f"@prefix ex: <{EX}> . ex:a a ex:P .", format="turtle")
    shapes.parse(data=_SHAPES, format="turtle")
    text = validate(data, shapes).report_text
    assert "Used Data Graph" not in text and "Provenance" not in text
    named = validate(data, shapes, data_graph_iri=EX + "data1").report_text
    assert "Used Data Graph: ex:data1" in named


# ---- the equivalents named in oxgraph-wrapper.md for old-class API that is not ported -----------------------------------------


def test_documented_equivalents():
    g = _graph()
    g.bind("unused", "http://unused.example/")
    keep = {"ex"}
    for p in set(g.prefixes) - {p for p, _ in g.used_prefixes()} - keep:  # reduce_prefixes(keep=...)
        g.unbind(p)
    assert set(g.prefixes) == {"", "ex"}
    tt = ox.Triple(ox.NamedNode(EX + "x"), ox.NamedNode(EX + "y"), ox.NamedNode(EX + "z"))
    assert list(g.triple_terms(None, ox.NamedNode(EX + "y"), None)) == [tt]  # a wildcard match on a triple term
    r = ox.BlankNode()  # add_reifier_annotation + add_reification
    g.add((r, ox.NamedNode(EX + "confidence"), ox.Literal("0.9")))
    g.add_reification(r, tt)
    assert (r, ox.NamedNode(EX + "confidence"), ox.Literal("0.9")) in set(g.reifier_annotations(tt))
    from starlayer.graph import isomorphic
    from starlayer.graph.rdfc_native import isomorphic as quads_isomorphic

    a, b = OxGraph(), OxGraph()
    a.parse(data=f"<{EX}s> <{EX}p> [ <{EX}q> 1 ] .", format="turtle")
    b.parse(data=f"<{EX}s> <{EX}p> [ <{EX}q> 1 ] .", format="turtle")
    assert isomorphic(a, b) and quads_isomorphic(a.quads(), b.quads())
