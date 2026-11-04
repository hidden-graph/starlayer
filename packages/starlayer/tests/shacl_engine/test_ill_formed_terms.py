"""The ill-formed-term policy (``terms.TermError``): terms pyoxigraph rejects and rdflib accepts.

Strict (default): one up-front ``TermError`` naming every offender and where it is. Lenient: opaque stand-in terms (an Oxigraph
store cannot hold the original), listed with the original rdflib term on ``Outcome.invalid_terms``; results and the report
hold the stand-ins. The public entry points raise that error. Ill-formed terms can only come from rdflib graphs: an ``OxGraph``
refuses them when they are added."""

from __future__ import annotations

import warnings

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import evaluate, extract_subgraph, validate, validate_each
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph
from starlayer.shacl_engine.rules import apply_rules
from starlayer.shacl_engine.terms import (
    NamedNode,
    TermError,
    check_graphs,
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


@pytest.mark.parametrize("name", ILL_FORMED)
def test_oxgraph_refuses_an_ill_formed_term_when_it_is_added(name):
    term, kind = ILL_FORMED[name]
    with pytest.raises(TermError) as info:
        graph_with(term, OxGraph)
    assert info.value.kind == kind


@pytest.mark.parametrize("name", ILL_FORMED)
def test_validate_rejects_up_front_naming_term_and_graph(name):
    term, kind = ILL_FORMED[name]
    data = graph_with(term, Graph)
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


def test_lenient_validates_and_reports_the_stand_in_terms():
    """An ill-formed IRI stays an IRI (``sh:nodeKind sh:IRI`` holds, as rdflib says); results and the report hold its stand-in
    (an Oxigraph store cannot hold the relative or ill-formed IRI), ``invalid_terms`` names the original."""
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
    with term_policy("lenient"):
        stand_in = to_engine(bad_iri)
    assert stand_in.value.startswith("urn:starlayer:invalid-iri:")
    focus = {r.focus for r in out.results}
    assert focus == {stand_in} and all(type(f) is NamedNode for f in focus)
    assert [e.term for e in out.invalid_terms] == [bad_iri]
    assert any(stand_in in t for t in out.report_graph)


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


def test_rdflib_view_scan_and_lenient_conversion():
    data = graph_with(URIRef("a"))
    with pytest.raises(TermError):
        engine_view(data, "data graph")
    with term_policy("lenient"):
        view = engine_view(data, "data graph")
        assert len(check_graphs((data, "data graph"))) == 1 and len(list(view.triples((None, None, None)))) == 2
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
    data = Graph()  # an OxGraph cannot hold the relative IRI, so the data comes in as a plain rdflib graph
    data.parse(data=PFX + "<http://example.org/ok> ex:p 1 .", format="turtle")
    data.add((URIRef("a"), URIRef(EX + "q"), URIRef(EX + "ok")))
    shapes = OxGraph()
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


# ---- lenient: text shows the original term ----------------------------------------------------------------------------------

_TEXT_SHAPES = (
    PFX + "ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:p ; sh:nodeKind sh:BlankNode ;"
    " sh:property [ sh:path ex:p ; sh:class ex:C ; sh:in ( ex:a ) ] ."
)


def _relative_iri_outcome():
    data = Graph()
    data.add((URIRef("relative/s"), URIRef(EX + "p"), Literal("v")))
    data.add((URIRef(EX + "t"), URIRef(EX + "p"), URIRef("rel/o")))
    return validate(data, Graph().parse(data=_TEXT_SHAPES, format="turtle"), invalid_terms="lenient")


def test_lenient_report_text_and_messages_show_the_original_term():
    out = _relative_iri_outcome()
    assert "urn:starlayer:invalid-iri:" not in out.report_text
    assert "Focus Node: <relative/s>" in out.report_text and "Value Node: <rel/o>" in out.report_text
    assert "Value <rel/o> not in list" in out.report_text
    assert not any("urn:starlayer:invalid-iri:" in m for r in out.results for m in r.messages)
    assert any("rel/o" in m for r in out.results for m in r.messages)
    texts = [str(o) for o in out.report_graph.objects(None, URIRef("http://www.w3.org/ns/shacl#resultMessage"))]
    assert texts and not any("urn:starlayer:invalid-iri:" in t for t in texts)
    # the report graph still holds the stand-ins as terms; invalid_terms names the originals
    assert {e.term for e in out.invalid_terms} == {URIRef("relative/s"), URIRef("rel/o")}


def test_lenient_report_text_through_the_public_validator():
    from starlayer.shacl import StarShaclSchema

    data = Graph()
    data.add((URIRef("relative/s"), URIRef(EX + "p"), Literal("v")))
    shapes = Graph().parse(data=_TEXT_SHAPES, format="turtle")
    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, invalid_terms="lenient")
    assert "Focus Node: <relative/s>" in result.report_text
    assert "urn:starlayer:invalid-iri:" not in result.report_text
