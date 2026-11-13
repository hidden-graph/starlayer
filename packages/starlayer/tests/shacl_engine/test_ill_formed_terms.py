"""The ill-formed-term policy (``terms.TermError``): terms pyoxigraph rejects and rdflib accepts.

Strict (default): one up-front ``TermError`` naming every offender and where it is. Lenient: opaque stand-in terms (an Oxigraph
store cannot hold the original), listed with the original rdflib term on ``Outcome.invalid_terms``; results and the report
hold the stand-ins. The public entry points raise that error. Ill-formed terms can only come from rdflib graphs: an ``StarLayerGraph``
refuses them when they are added."""

from __future__ import annotations

import warnings

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.graph.oxgraph._rdflib_bridge import foreign_to_engine
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.oxigraph_view import OxigraphGraph
from starlayer.shacl_engine.terms import (
    NamedNode,
    TermError,
    from_engine,
    term_policy,
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
        foreign_to_engine(term)
    assert isinstance(info.value, ValueError) and info.value.kind == kind
    assert info.value.term == term or info.value.term == getattr(term, "datatype", None)
    assert info.value.reason


@pytest.mark.parametrize("name", ILL_FORMED)
def test_lenient_round_trip_is_exact(name):
    term, _ = ILL_FORMED[name]
    with term_policy("lenient"):
        engine = foreign_to_engine(term)
    back = from_engine(engine)
    assert type(back) is type(term) and back == term
    assert getattr(back, "language", None) == getattr(term, "language", None)
    assert getattr(back, "datatype", None) == getattr(term, "datatype", None)
    with pytest.raises(TermError):  # a lenient result is never cached into the strict path
        foreign_to_engine(term)


def test_lenient_stand_ins_are_ordinary_engine_terms():
    with term_policy("lenient"):
        iri = foreign_to_engine(URIRef("a b"))
        lit = foreign_to_engine(Literal("x", lang="e"))
    assert isinstance(iri, NamedNode) and iri.value.startswith("urn:starlayer:invalid-iri:")
    assert lit.datatype.value.startswith("urn:starlayer:invalid-lang:") and lit.language is None


def test_policy_name_is_checked():
    with pytest.raises(ValueError, match="invalid_terms"), term_policy("shrug"):
        pass


# ---- validate: strict -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ILL_FORMED)
def test_oxgraph_refuses_an_ill_formed_term_when_an_rdflib_graph_is_converted(name):
    term, kind = ILL_FORMED[name]
    with pytest.raises(TermError) as info:
        StarLayerGraph.from_rdflib(graph_with(term, Graph))
    assert info.value.kind == kind


def test_oxgraph_does_not_take_an_rdflib_term_at_all():
    with pytest.raises(TypeError, match="rdflib term"):
        graph_with(URIRef(EX + "fine"), StarLayerGraph)


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


# ---- validate: lenient ----------------------------------------------------------------------------------------------------


# ---- the views ------------------------------------------------------------------------------------------------------------


def test_oxigraph_text_parse_errors_stay_parse_errors():
    with pytest.raises(SyntaxError):
        OxigraphGraph.from_text("<a> <b> <c> .", format="nt")


# ---- the native adapter ---------------------------------------------------------------------------------------------------


def _pairs():
    data = Graph()  # an StarLayerGraph cannot hold the relative IRI, so the data comes in as a plain rdflib graph
    data.parse(data=PFX + "<http://example.org/ok> ex:p 1 .", format="turtle")
    data.add((URIRef("a"), URIRef(EX + "q"), URIRef(EX + "ok")))
    shapes = StarLayerGraph()
    shapes.parse(data=IRI_SHAPES, format="turtle")
    return data, shapes


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

