"""starlayer.graph.interop: the RDF 1.2 Interoperability "basic encoding" over pyoxigraph terms."""

from __future__ import annotations

import random
import warnings

import pyoxigraph as ox
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from starlayer.graph.interop import (
    DIRLANG_NS,
    RDF_PROPOSITION_FORM,
    BasicEncodingError,
    decode_directions,
    encode_directions,
    export_rdf11,
    from_basic,
    has_triple_terms,
    to_basic,
)

from ._interop_corpus import bnode_labels, gen_dataset, iri

DG = ox.DefaultGraph()
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
TYPE = ox.NamedNode(RDF + "type")
SUBJ = ox.NamedNode(RDF + "propositionFormSubject")
PRED = ox.NamedNode(RDF + "propositionFormPredicate")
OBJ = ox.NamedNode(RDF + "propositionFormObject")
B = ox.BlankNode


def q(s, p, o, g=DG):
    return ox.Quad(s, p, o, g)


def tt(s, p, o):
    return ox.Triple(s, p, o)


class TestToBasic:
    def test_one_triple_term_becomes_a_blank_node_with_four_description_triples(self):
        t = tt(iri("s"), iri("p"), iri("o"))
        out = to_basic([q(iri("a"), iri("says"), t)])
        assert len(out) == 5 and not has_triple_terms(out)
        main = out[0]
        b = main.object
        assert isinstance(b, ox.BlankNode)
        assert {(x.predicate, x.object) for x in out[1:] if x.subject == b} == {
            (TYPE, RDF_PROPOSITION_FORM), (SUBJ, iri("s")), (PRED, iri("p")), (OBJ, iri("o"))}

    def test_the_fresh_node_is_not_in_the_input(self):
        t = tt(B("x"), iri("p"), B("y"))
        for _ in range(20):
            out = to_basic([q(iri("a"), iri("says"), t), q(B("x"), iri("p"), B("y"))])
            fresh = out[0].object
            assert fresh.value not in {"x", "y"}

    def test_nested_triple_term_is_encoded_inner_first(self):
        inner = tt(iri("s"), iri("p"), iri("o"))
        outer = tt(iri("x"), iri("y"), inner)
        out = to_basic([q(iri("a"), iri("says"), outer)], bnode_prefix="t")
        assert not has_triple_terms(out)
        forms = [x.subject for x in out if x.predicate == TYPE]
        assert len(forms) == 2
        outer_b = out[0].object
        obj_of_outer = next(x.object for x in out if x.subject == outer_b and x.predicate == OBJ)
        assert obj_of_outer in forms and obj_of_outer != outer_b

    def test_repeated_identical_triple_term_shares_one_blank_node_per_graph(self):
        t = tt(iri("s"), iri("p"), iri("o"))
        out = to_basic([q(iri("a"), iri("p1"), t), q(iri("b"), iri("p2"), t), q(iri("c"), iri("p3"), t, iri("g"))], bnode_prefix="t")
        assert out[0].object == out[5].object  # same graph, same node
        assert sum(1 for x in out if x.predicate == TYPE and x.graph_name == DG) == 1
        g_nodes = {x.subject for x in out if x.predicate == TYPE and x.graph_name == iri("g")}
        assert len(g_nodes) == 1 and g_nodes != {out[0].object}  # a different graph gets its own node
        assert all(x.graph_name == iri("g") for x in out if x.subject in g_nodes)

    def test_bnode_prefix_is_deterministic_and_skips_labels_in_use(self):
        t = tt(iri("s"), iri("p"), B("t0"))
        data = [q(iri("a"), iri("p"), t)]
        first = to_basic(data, bnode_prefix="t")
        assert first == to_basic(data, bnode_prefix="t")
        assert first[0].object == B("t1")  # t0 is in use inside the triple term

    def test_dataset_without_triple_terms_is_unchanged(self):
        data = [q(iri("a"), iri("p"), ox.Literal("x"), iri("g"))]
        assert to_basic(data) == data

    def test_accepts_store_dataset_and_triples(self):
        t = tt(iri("s"), iri("p"), iri("o"))
        quad = q(iri("a"), iri("p"), t)
        store = ox.Store()
        store.add(quad)
        assert len(to_basic(store)) == len(to_basic(ox.Dataset([quad]))) == 5
        assert len(to_basic([ox.Triple(iri("a"), iri("p"), t)])) == 5

    def test_input_using_the_vocabulary_is_refused(self):
        clash = q(iri("a"), TYPE, RDF_PROPOSITION_FORM)
        with pytest.raises(BasicEncodingError):
            to_basic([clash, q(iri("a"), iri("p"), tt(iri("s"), iri("p"), iri("o")))])
        assert to_basic([clash]) == [clash]  # no triple term: nothing to encode, so no clash


class TestFromBasic:
    def test_round_trip_nested_shared_and_graphs(self):
        inner = tt(iri("s"), iri("p"), B("n"))
        outer = tt(B("m"), iri("y"), inner)
        data = [q(iri("a"), iri("says"), outer), q(iri("b"), iri("says"), outer), q(iri("c"), iri("says"), inner, iri("g")),
                q(B("m"), iri("name"), ox.Literal("x"))]
        assert set(from_basic(to_basic(data))) == set(data)

    @given(st.integers(0, 10**6))
    @settings(max_examples=150, deadline=None)
    def test_round_trip_is_the_identity_on_random_datasets(self, seed):
        data = gen_dataset(random.Random(seed))
        basic = to_basic(data)
        assert not has_triple_terms(basic)
        assert set(from_basic(basic)) == set(data)

    def test_blank_node_labels_of_the_encoding_do_not_matter(self):
        t = tt(iri("s"), iri("p"), iri("o"))
        data = [q(iri("a"), iri("p"), t)]
        assert set(from_basic(to_basic(data))) == set(from_basic(to_basic(data, bnode_prefix="zz")))

    def _form(self, b="f", s=None, p=None, o=None):
        s = iri("s") if s is None else s
        p = iri("p") if p is None else p
        o = iri("o") if o is None else o
        return [q(B(b), TYPE, RDF_PROPOSITION_FORM), q(B(b), SUBJ, s), q(B(b), PRED, p), q(B(b), OBJ, o)]

    def test_a_well_formed_form_decodes(self):
        out = from_basic(self._form() + [q(iri("a"), iri("p"), B("f"))])
        assert out == [q(iri("a"), iri("p"), tt(iri("s"), iri("p"), iri("o")))]

    @pytest.mark.parametrize("drop", [SUBJ, PRED, OBJ])
    def test_missing_component_is_refused(self, drop):
        data = [x for x in self._form() if x.predicate != drop] + [q(iri("a"), iri("p"), B("f"))]
        with pytest.raises(BasicEncodingError, match="need 1"):
            from_basic(data)

    def test_two_objects_is_ambiguous(self):
        data = self._form() + [q(B("f"), OBJ, iri("o2")), q(iri("a"), iri("p"), B("f"))]
        with pytest.raises(BasicEncodingError, match="2 values"):
            from_basic(data)

    def test_description_without_type_is_refused(self):
        with pytest.raises(BasicEncodingError, match="no rdf:type"):
            from_basic([q(B("f"), SUBJ, iri("s"))])

    def test_cycle_is_refused(self):
        data = ([q(B("f"), TYPE, RDF_PROPOSITION_FORM), q(B("f"), SUBJ, iri("s")), q(B("f"), PRED, iri("p")), q(B("f"), OBJ, B("g")),
                 q(B("g"), TYPE, RDF_PROPOSITION_FORM), q(B("g"), SUBJ, iri("s")), q(B("g"), PRED, iri("p")), q(B("g"), OBJ, B("f")),
                 q(iri("a"), iri("p"), B("f"))])
        with pytest.raises(BasicEncodingError, match="cyclic"):
            from_basic(data)

    def test_unreferenced_form_is_refused(self):
        with pytest.raises(BasicEncodingError, match="not referenced"):
            from_basic(self._form())

    def test_form_with_other_statements_is_refused(self):
        with pytest.raises(BasicEncodingError, match="other statements"):
            from_basic(self._form() + [q(iri("a"), iri("p"), B("f")), q(B("f"), iri("label"), ox.Literal("x"))])

    def test_form_as_a_triple_term_subject_is_refused(self):
        data = self._form("f") + self._form("g", s=B("f")) + [q(iri("a"), iri("p"), B("g"))]
        with pytest.raises(BasicEncodingError, match="subject"):
            from_basic(data)

    def test_literal_subject_and_non_iri_predicate_are_refused(self):
        with pytest.raises(BasicEncodingError):
            from_basic(self._form(s=ox.Literal("x")) + [q(iri("a"), iri("p"), B("f"))])
        with pytest.raises(BasicEncodingError):
            from_basic(self._form(p=B("p")) + [q(iri("a"), iri("p"), B("f"))])

    def test_form_as_graph_name_is_refused(self):
        with pytest.raises(BasicEncodingError, match="graph name"):
            from_basic(self._form() + [q(iri("a"), iri("p"), B("f")), q(iri("a"), iri("p"), iri("o"), B("f"))])

    def test_iri_named_forms_need_the_option(self):
        f = ox.NamedNode("http://e/tt#1")
        data = [q(f, TYPE, RDF_PROPOSITION_FORM), q(f, SUBJ, iri("s")), q(f, PRED, iri("p")), q(f, OBJ, iri("o")), q(iri("a"), iri("p"), f)]
        with pytest.raises(BasicEncodingError):
            from_basic(data)
        assert from_basic(data, accept_iri_nodes=True) == [q(iri("a"), iri("p"), tt(iri("s"), iri("p"), iri("o")))]


class TestExportRdf11:
    DATA = [q(iri("a"), iri("says"), tt(iri("s"), iri("p"), B("x"))), q(B("x"), iri("name"), ox.Literal("Bob"))]

    @pytest.mark.parametrize("fmt", ["turtle", "ntriples", "rdfxml"])
    def test_triple_formats_have_no_triple_term_and_parse_back_as_rdf11(self, fmt):
        out = export_rdf11(self.DATA, fmt)
        assert b"<<" not in out
        rdf_format = {"turtle": ox.RdfFormat.TURTLE, "ntriples": ox.RdfFormat.N_TRIPLES, "rdfxml": ox.RdfFormat.RDF_XML}[fmt]
        parsed = list(ox.parse(out, format=rdf_format, rename_blank_nodes=False))
        assert len(parsed) == 6
        assert not any(isinstance(x.object, ox.Triple) for x in parsed)

    @pytest.mark.parametrize("fmt", ["trig", "nquads"])
    def test_quad_formats_keep_named_graphs(self, fmt):
        data = self.DATA + [q(iri("a"), iri("says"), tt(iri("s"), iri("p"), iri("o")), iri("g"))]
        out = export_rdf11(data, fmt)
        assert b"<<" not in out
        assert b"http://e/g" in out

    def test_named_graph_is_refused_for_a_triple_format(self):
        with pytest.raises(ValueError, match="named graphs"):
            export_rdf11([q(iri("a"), iri("p"), iri("o"), iri("g"))], "turtle")

    def test_export_is_semantically_the_basic_encoding(self):
        out = export_rdf11(self.DATA, "nquads")
        parsed = list(ox.parse(out, format=ox.RdfFormat.N_QUADS, rename_blank_nodes=False))
        assert set(from_basic(parsed)) == set(self.DATA)

    def test_destination_and_prefixes(self, tmp_path):
        path = tmp_path / "o.ttl"
        assert export_rdf11(self.DATA, "turtle", str(path), prefixes={"e": "http://e/"}) is None
        text = path.read_text()
        assert "e:says" in text

    def test_store_input(self):
        store = ox.Store()
        for x in self.DATA:
            store.add(x)
        assert b"<<" not in export_rdf11(store, ox.RdfFormat.N_TRIPLES)

    def test_unknown_format_is_refused(self):
        with pytest.raises(ValueError):
            export_rdf11(self.DATA, ox.RdfFormat.JSON_LD)


class TestBaseDirectionPolicy:
    L = ox.Literal("shalom", language="he", direction=ox.BaseDirection.RTL)

    def test_default_is_the_datatype_form_of_the_old_encoding(self):
        out = export_rdf11([q(iri("a"), iri("p"), self.L)], "ntriples").decode()
        assert f"^^<{DIRLANG_NS}he--rtl>" in out and "--rtl " not in out.replace(f"{DIRLANG_NS}he--rtl", "")

    def test_matches_the_old_encoding_module(self):
        from starlayer.graph.model import encoding as old

        assert DIRLANG_NS == old.DIRLANG_NS
        (out,) = encode_directions([q(iri("a"), iri("p"), self.L)])
        assert str(out.object.datatype.value) == str(old.encode_dirlang_datatype("he", "rtl"))
        assert old.decode_dirlang_datatype(old.URIRef(out.object.datatype.value)) == ("he", "rtl")

    def test_decode_inverts_and_works_inside_triple_terms(self):
        data = [q(iri("a"), iri("p"), tt(iri("s"), iri("p"), self.L)), q(iri("a"), iri("p"), self.L)]
        assert set(decode_directions(encode_directions(data))) == set(data)

    def test_error_policy(self):
        with pytest.raises(ValueError, match="no RDF 1.1 form"):
            export_rdf11([q(iri("a"), iri("p"), self.L)], "ntriples", direction_policy="error")

    def test_drop_policy_keeps_the_language(self):
        out = export_rdf11([q(iri("a"), iri("p"), self.L)], "ntriples", direction_policy="drop").decode()
        assert '"shalom"@he' in out and "--" not in out

    def test_unknown_policy(self):
        with pytest.raises(ValueError):
            encode_directions([], "nope")

    def test_plain_language_literal_untouched(self):
        d = [q(iri("a"), iri("p"), ox.Literal("x", language="en"))]
        assert encode_directions(d) == d


class TestAgainstTheOldEncoding:
    """The old graph classes hold triple terms as content-hash IRIs under tt: with the same vocabulary. Same
    structure, different node naming (IRI versus blank node). The old module has no to_basic()/from_basic()
    functions; its raw triples (rdflib.Graph.triples on a StarLayerGraph) are the encoding."""

    @staticmethod
    def _old_raw(turtle):
        import rdflib
        from starlayer.graph import StarLayerGraph

        g = StarLayerGraph()
        g.parse(data=turtle, format="turtle12")
        conv = {rdflib.URIRef: lambda t: ox.NamedNode(str(t)), rdflib.BNode: lambda t: ox.BlankNode(str(t))}

        def term(t):
            if isinstance(t, rdflib.Literal):
                return ox.Literal(str(t), datatype=ox.NamedNode(str(t.datatype))) if t.datatype else ox.Literal(str(t), language=t.language)
            return conv[type(t)](t)

        return [ox.Quad(term(s), term(p), term(o), DG) for s, p, o in rdflib.Graph.triples(g, (None, None, None))]

    CASES = [
        "<http://e/a> <http://e/p> <<( <http://e/s> <http://e/q> <http://e/o> )>> .",
        "<http://e/a> <http://e/p> <<( _:x <http://e/q> <<( <http://e/s> <http://e/p> \"v\"@en--ltr )>> )>> . _:x <http://e/n> 1 .",
        "<http://e/a> <http://e/p> <<( <http://e/s> <http://e/q> <http://e/o> )>> . <http://e/b> <http://e/r> <<( <http://e/s> <http://e/q> <http://e/o> )>> .",
    ]

    @pytest.mark.parametrize("turtle", CASES)
    def test_same_structure_different_node_names(self, turtle):
        from starlayer.graph.rdfc_native import isomorphic

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            old = self._old_raw(turtle)
        assert any(x.subject.value.startswith("https://github.com/hidden-graph/starlayergraph/ns/tt#") for x in old if isinstance(x.subject, ox.NamedNode))
        original = list(ox.parse(turtle.encode(), format=ox.RdfFormat.TURTLE, rename_blank_nodes=False))
        original = [q(x.subject, x.predicate, x.object) for x in original]
        mine = encode_directions(to_basic(original))
        # same dataset up to blank-node naming once the old IRI nodes are read as blank nodes
        old_as_bnodes = _iri_forms_to_bnodes(old)
        assert isomorphic(old_as_bnodes, mine)
        # and the old encoding decodes with the new from_basic
        assert set(decode_directions(from_basic(old, accept_iri_nodes=True))) == set(original) or isomorphic(
            decode_directions(from_basic(old, accept_iri_nodes=True)), original)


def _iri_forms_to_bnodes(quads):
    ns = "https://github.com/hidden-graph/starlayergraph/ns/tt#"

    def f(t):
        return ox.BlankNode("T" + t.value[len(ns):]) if isinstance(t, ox.NamedNode) and t.value.startswith(ns) else t

    return [ox.Quad(f(x.subject), x.predicate, f(x.object), x.graph_name) for x in quads]


def test_has_blank_node_labels_helper():
    assert bnode_labels([q(B("a"), iri("p"), tt(B("b"), iri("p"), B("c")), B("g"))]) == {"a", "b", "c", "g"}
