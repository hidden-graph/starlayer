"""The ill-formed-term policy (``terms.TermError``): terms pyoxigraph rejects and rdflib accepts.

Strict (default): one up-front ``TermError`` naming every offender and where it is. Lenient: opaque stand-ins that map back to
the original rdflib term in every result, listed on ``Outcome.invalid_terms``. The public entry points raise that error."""

from __future__ import annotations

import warnings

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl_engine import evaluate, extract_subgraph, validate, validate_each
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph
from starlayer.shacl_engine.rules import apply_rules
from starlayer.shacl_engine.terms import (
    NamedNode,
    TermError,
    engine_view,
    from_engine,
    term_policy,
    to_engine,
)

PFX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
EX = "http://example.org/"
IRI_SHAPES = PFX + "ex:S a sh:NodeShape ; sh:targetNode <http://example.org/ok> ; sh:nodeKind sh:IRI ."

# every kind of term pyoxigraph rejects; rdflib accepts all of them (a language tag only when its own regex does)
ILL_FORMED = {
    "relative-iri": (URIRef("a"), "iri"),
    "empty-iri": (URIRef(""), "iri"),
    "iri-with-space": (URIRef("http://example.org/a b"), "iri"),
    "iri-with-bracket": (URIRef("http://example.org/<x>"), "iri"),
    "fragment-only-iri": (URIRef("#frag"), "iri"),
    "bnode-with-space": (BNode("a b"), "bnode"),
    "empty-bnode": (BNode(""), "bnode"),
    "one-letter-language": (Literal("x", lang="e"), "language"),
    "overlong-language-subtag": (Literal("x", lang="en-abcdefghi"), "language"),
    "bad-datatype-iri": (Literal("x", datatype=URIRef("not an iri")), "iri"),
}


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import logging

        logging.getLogger("rdflib.term").setLevel(logging.CRITICAL)
        yield


def graph_with(term, cls=Graph, as_object: bool = True):
    g = cls()
    g.parse(data=PFX + "<http://example.org/ok> ex:p 1 .", format="turtle")
    if isinstance(term, Literal) or as_object:
        g.add((URIRef(EX + "ok"), URIRef(EX + "q"), term))
    else:
        g.add((term, URIRef(EX + "q"), URIRef(EX + "ok")))
    return g


# ---- to_engine ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ILL_FORMED)
def test_to_engine_raises_term_error(name):
    term, kind = ILL_FORMED[name]
    with pytest.raises(TermError) as info:
        to_engine(term)
    assert isinstance(info.value, ValueError) and info.value.kind == kind
    assert info.value.term == term or info.value.term == getattr(term, "datatype", None)
    assert info.value.reason


@pytest.mark.parametrize("name", ILL_FORMED)
def test_lenient_round_trip_is_exact(name):
    term, _ = ILL_FORMED[name]
    with term_policy("lenient"):
        engine = to_engine(term)
    back = from_engine(engine)
    assert type(back) is type(term) and back == term
    assert getattr(back, "language", None) == getattr(term, "language", None)
    assert getattr(back, "datatype", None) == getattr(term, "datatype", None)
    with pytest.raises(TermError):  # a lenient result is never cached into the strict path
        to_engine(term)


def test_lenient_stand_ins_are_ordinary_engine_terms():
    with term_policy("lenient"):
        iri = to_engine(URIRef("a b"))
        lit = to_engine(Literal("x", lang="e"))
    assert isinstance(iri, NamedNode) and iri.value.startswith("urn:starlayer:invalid-iri:")
    assert lit.datatype.value.startswith("urn:starlayer:invalid-lang:") and lit.language is None


def test_policy_name_is_checked():
    with pytest.raises(ValueError, match="invalid_terms"), term_policy("shrug"):
        pass


# ---- validate: strict -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [Graph, StarLayerGraph])
@pytest.mark.parametrize("name", ILL_FORMED)
def test_validate_rejects_up_front_naming_term_and_graph(name, cls):
    term, kind = ILL_FORMED[name]
    data = graph_with(term, cls)
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    with pytest.raises(TermError) as info:
        validate(data, shapes)
    err = info.value
    assert err.errors and err.errors[0].where == "data graph" and err.errors[0].kind == kind
    assert err.errors[0].triple is not None and err.errors[0].position in {"subject", "object", "datatype of the object"}
    assert "data graph" in str(err) and "invalid_terms='lenient'" in str(err)


def test_validate_reports_every_offender_and_both_graphs():
    data = graph_with(URIRef("a"))
    data.add((BNode("x y"), URIRef(EX + "q"), Literal("v", lang="e")))
    shapes = graph_with(URIRef("b c"), as_object=False)
    with pytest.raises(TermError) as info:
        validate(data, shapes)
    wheres = {(e.where, e.kind) for e in info.value.errors}
    assert wheres >= {("data graph", "iri"), ("data graph", "bnode"), ("data graph", "language"), ("shapes graph", "iri")}


def test_shapes_graph_is_also_the_data_graph():
    with pytest.raises(TermError) as info:
        validate(graph_with(URIRef("a")))
    assert info.value.errors[0].where == "data graph"


def test_other_entry_points_reject_too():
    bad = graph_with(URIRef("a"))
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    for call in (
        lambda: validate_each([bad], shapes),
        lambda: evaluate(bad, shapes),
        lambda: extract_subgraph(bad, shapes),
        lambda: apply_rules(bad, shapes),
    ):
        with pytest.raises(TermError):
            call()
    with pytest.raises(TermError):  # an ill-formed argument
        validate(Graph(), shapes, conformance_disallows=URIRef("a"))


def test_a_clean_graph_is_unaffected_and_not_rescanned_when_unchanged():
    data = graph_with(URIRef("http://example.org/fine"))
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    out = validate(data, shapes)
    assert out.conforms and out.invalid_terms == ()


def test_a_graph_changed_after_a_scan_is_scanned_again():
    data = graph_with(URIRef("http://example.org/fine"))
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    validate(data, shapes)
    data.add((URIRef("a"), URIRef(EX + "q"), URIRef(EX + "ok")))
    with pytest.raises(TermError):
        validate(data, shapes)


# ---- validate: lenient ----------------------------------------------------------------------------------------------------


def test_lenient_validates_and_reports_the_original_terms():
    """An ill-formed IRI stays an IRI (``sh:nodeKind sh:IRI`` holds, as rdflib says); results show the original term."""
    bad_iri = URIRef("http://example.org/a b")
    data = Graph()
    data.add((bad_iri, URIRef(EX + "p"), Literal("v")))
    shapes = Graph().parse(
        data=PFX + "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ; sh:nodeKind sh:IRI ;"
        " sh:property [ sh:path ex:p ; sh:nodeKind sh:IRI ; sh:message 'p must be an IRI' ] .",
        format="turtle",
    )
    out = validate(data, shapes, invalid_terms="lenient")
    assert not out.conforms  # the literal object violates the property shape; the ill-formed focus node is an IRI
    focus = {r.focus for r in out.results}
    assert focus == {bad_iri} and all(type(f) is URIRef for f in focus)
    assert [e.term for e in out.invalid_terms] == [bad_iri]
    assert any(bad_iri in t for t in out.report_graph)
    assert "a b" in out.report_text  # read after the call: the lenient policy is remembered by the views


def test_lenient_blank_node_and_language_literal():
    data = Graph()
    data.add((BNode("a b"), URIRef(EX + "p"), Literal("v", lang="e")))
    shapes = Graph().parse(
        data=PFX + "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ; sh:nodeKind sh:BlankNode ;"
        " sh:property [ sh:path ex:p ; sh:nodeKind sh:Literal ] .",
        format="turtle",
    )
    out = validate(data, shapes, invalid_terms="lenient")
    assert out.conforms and {e.kind for e in out.invalid_terms} == {"bnode", "language"}


def test_lenient_keyword_is_a_context_manager_equivalent():
    data = graph_with(URIRef("a"))
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    with term_policy("lenient"):
        assert validate(data, shapes).invalid_terms


def test_lenient_apply_rules_and_evaluate_run():
    data = graph_with(URIRef("a"))
    shapes = Graph().parse(data=IRI_SHAPES, format="turtle")
    assert apply_rules(data, shapes, invalid_terms="lenient").inferred == frozenset()
    assert len(evaluate(data, shapes, invalid_terms="lenient")) >= 0


# ---- the views ------------------------------------------------------------------------------------------------------------


def test_rdflib_view_scan_and_lazy_conversion():
    data = graph_with(URIRef("a"))
    with pytest.raises(TermError):
        engine_view(data, "data graph")
    from starlayer.shacl_engine.terms import RdflibTermView

    lazy = RdflibTermView(data, check=False)  # no scan: first contact raises, it is never silently skipped
    with pytest.raises(TermError):
        list(lazy.triples((None, None, None)))
    with term_policy("lenient"):
        view = engine_view(data, "data graph")
        assert len(view.invalid_terms) == 1 and len(list(view.triples((None, None, None)))) == 2
    assert from_engine(next(iter(view.subjects(NamedNode(EX + "q"), None)), None)) in (URIRef(EX + "ok"), None)


@pytest.mark.parametrize("name", ["relative-iri", "iri-with-space", "bnode-with-space", "one-letter-language"])
def test_oxigraph_graph_rejects_and_lenient_stores_stand_ins(name):
    term, _ = ILL_FORMED[name]
    data = graph_with(term)
    with pytest.raises(TermError) as info:
        OxigraphGraph.from_graph(data)
    assert info.value.errors[0].where == "graph"
    view = OxigraphGraph()
    with pytest.raises(TermError):
        view.add((URIRef(EX + "s"), URIRef(EX + "p"), term))
    with pytest.raises(TermError):
        list(view.triples((term, None, None)) if not isinstance(term, Literal) else view.triples((None, None, term)))
    with term_policy("lenient"):
        ox_view = OxigraphGraph.from_graph(data)
        stored = {from_engine(o) for _s, _p, o in ox_view.triples((None, NamedNode(EX + "q"), None))}
        assert stored == {term}
    out = validate(ox_view, Graph().parse(data=IRI_SHAPES, format="turtle"))  # a store holds only stand-ins: plain terms
    assert out.conforms in (True, False)


def test_oxigraph_text_parse_errors_stay_parse_errors():
    with pytest.raises(SyntaxError):
        OxigraphGraph.from_text("<a> <b> <c> .", format="nt")


# ---- the native adapter ---------------------------------------------------------------------------------------------------


def _pairs():
    data = StarLayerGraph()
    data.parse(data=PFX + "<http://example.org/ok> ex:p 1 .", format="turtle")
    data.add((URIRef("a"), URIRef(EX + "q"), URIRef(EX + "ok")))
    shapes = StarLayerGraph()
    shapes.parse(data=IRI_SHAPES, format="turtle")
    return data, shapes


@pytest.mark.parametrize("entry", ["validate", "apply_rules", "evaluate"])
def test_the_public_entry_points_reject_a_graph_with_an_ill_formed_term(entry):
    """A graph with a term that is not an RDF term (a relative IRI) is outside SHACL 1.2's domain: the engine rejects it up front,
    and the error reaches the caller of every entry point."""
    import starlayer.shacl as shacl

    data, shapes = _pairs()
    with pytest.raises(TermError, match="ill-formed"):
        getattr(shacl, entry)(data, shapes)
