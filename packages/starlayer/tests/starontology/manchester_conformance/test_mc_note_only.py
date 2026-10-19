"""Checks for constructs the W3C Note allows but the OWL API oracle rejects.

There is no oracle output to diff against for these, so each case asserts the structure the Note's
grammar and the OWL 2 RDF mapping imply. A case whose ``ORACLE_REJECTS`` reason starts with an ``F<n>``
finding code is a known gap and is applied as a strict xfail.
"""

from __future__ import annotations

import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from .corpus import CASES
from .helpers import parse_to_graph
from .known_failures import ORACLE_DEVIATIONS, ORACLE_REJECTS

EX = "http://example.org/o#"
CASE = {c.id: c for c in CASES}


def _restriction(g, prop, kind):
    return [r for r in g.subjects(OWL.onProperty, URIRef(EX + prop)) if (r, kind, None) in g]


def _filler(g, prop, kind):
    (r,) = _restriction(g, prop, kind)
    return g.value(r, kind)


def check_some_chained(g):
    inner = _filler(g, "p", OWL.someValuesFrom)
    assert isinstance(inner, BNode)
    assert g.value(inner, OWL.onProperty) == URIRef(EX + "q")
    assert g.value(inner, OWL.someValuesFrom) == URIRef(EX + "B")


def check_some_not(g):
    comp = _filler(g, "p", OWL.someValuesFrom)
    assert g.value(comp, OWL.complementOf) == URIRef(EX + "B")


def _intersection_members(g, owner):
    cls = g.value(URIRef(EX + owner), OWL.equivalentClass)
    return list(Collection(g, g.value(cls, OWL.intersectionOf)))


def check_that_not(g):
    members = _intersection_members(g, "A")
    assert URIRef(EX + "B") in members and len(members) == 2
    (neg,) = [m for m in members if isinstance(m, BNode)]
    restriction = g.value(neg, OWL.complementOf)
    assert g.value(restriction, OWL.onProperty) == URIRef(EX + "p")
    assert g.value(restriction, OWL.someValuesFrom) == URIRef(EX + "C")


def check_that_and_not(g):
    members = _intersection_members(g, "A")
    assert URIRef(EX + "B") in members and len(members) == 3
    assert sum(1 for m in members if (m, OWL.complementOf, None) in g) == 1


def _range_is(datatype):
    def check(g):
        assert (URIRef(EX + "d"), RDFS.range, datatype) in g
        assert (URIRef(EX + "d"), RDFS.range, URIRef(EX + str(datatype).rsplit("#", 1)[1])) not in g
    return check


def check_short_name_in_restriction(g):
    assert _filler(g, "d", OWL.someValuesFrom) == XSD.integer


def check_short_name_in_facet(g):
    (dt,) = list(g.objects(URIRef(EX + "d"), RDFS.range))
    assert g.value(dt, OWL.onDatatype) == XSD.integer


def check_short_names_in_literals(g):
    values = {(str(o), o.datatype) for o in g.objects(URIRef(EX + "i"), URIRef(EX + "d")) if isinstance(o, Literal)}
    assert values == {("5", XSD.integer), ("1.5", XSD.decimal), ("2.5", XSD.float), ("x", XSD.string)}, values


def check_value_nodeid(g):
    assert isinstance(_filler(g, "p", OWL.hasValue), BNode)


def check_annotation_target_forms(g):
    targets = list(g.objects(URIRef(EX + "A"), URIRef(EX + "note")))
    assert any(isinstance(t, BNode) for t in targets) and Literal("lit") in targets


def _facet_check(*expected):
    """The datatype restriction on d has exactly these (facet, lexical) values, each an xsd:integer literal."""

    def check(g):
        (dt,) = list(g.objects(URIRef(EX + "d"), RDFS.range))
        cells = list(Collection(g, g.value(dt, OWL.withRestrictions)))
        got = {}
        for cell in cells:
            ((p, o),) = [(p, o) for p, o in g.predicate_objects(cell)]
            got[p] = o
        assert got == {XSD[name]: Literal(lex, datatype=XSD.integer) for name, lex in expected}, got

    return check


def _annotated_same_as_once(g):
    i, j = URIRef(EX + "i"), URIRef(EX + "j")
    assert (i, OWL.sameAs, j) in g
    axioms = [a for a in g.subjects(RDF.type, OWL.Axiom)]
    assert len(axioms) == 1, "an annotated pairwise axiom is reified exactly once"
    (a,) = axioms
    assert g.value(a, OWL.annotatedSource) == i and g.value(a, OWL.annotatedTarget) == j
    assert (a, URIRef(EX + "note"), Literal("x")) in g


def _annotated_chain_list_is_untyped(g):
    p = URIRef(EX + "p")
    chain = g.value(p, OWL.propertyChainAxiom)
    assert chain is not None and (chain, RDF.type, RDF.List) not in g
    (a,) = list(g.subjects(RDF.type, OWL.Axiom))
    assert g.value(a, OWL.annotatedTarget) == chain and g.value(a, OWL.annotatedSource) == p


CHECKS = {
    "facet-length": _facet_check(("length", "5")),
    "facet-minlength": _facet_check(("minLength", "1")),
    "facet-maxlength": _facet_check(("maxLength", "9")),
    "facet-min-and-max-length": _facet_check(("minLength", "1"), ("maxLength", "9")),
    "ind-sameas-annotated": _annotated_same_as_once,
    "misc-sameindividual-annotated": _annotated_same_as_once,
    "op-chain-annotated": _annotated_chain_list_is_untyped,
    "r-some-chained": check_some_chained,
    "r-some-not-filler": check_some_not,
    "that-not": check_that_not,
    "that-and-not": check_that_and_not,
    "range-short-integer": _range_is(XSD.integer),
    "range-short-decimal": _range_is(XSD.decimal),
    "range-short-float": _range_is(XSD.float),
    "range-short-string": _range_is(XSD.string),
    "dr-short-datatype-name": check_short_name_in_restriction,
    "facet-on-short-datatype": check_short_name_in_facet,
    "lit-typed-short-datatype-names": check_short_names_in_literals,
    "r-value-nodeid": check_value_nodeid,
    "lit-annotation-target-forms": check_annotation_target_forms,
}


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case_id", sorted(CHECKS))
def test_note_allowed_construct(case_id, request):
    assert case_id in ORACLE_REJECTS or case_id in ORACLE_DEVIATIONS, "only for rejected or deviating cases"
    if ORACLE_REJECTS.get(case_id, "")[:1] == "F":
        request.applymarker(pytest.mark.xfail(reason=ORACLE_REJECTS[case_id], strict=True))
    g = parse_to_graph(CASE[case_id].text)
    CHECKS[case_id](g)


@pytest.mark.manchester_conformance
def test_every_note_allowed_reject_has_a_check():
    needs = {
        cid for cid, why in ORACLE_REJECTS.items()
        if "Output checked by test_mc_note_only.py" in why or why[:1] == "F"
    }
    needs |= set(ORACLE_DEVIATIONS)
    assert needs <= set(CHECKS), f"cases with no spec-derived expectation: {sorted(needs - set(CHECKS))}"


# Silence the unused-import linter for names used only in type positions above.
_ = (RDF,)
