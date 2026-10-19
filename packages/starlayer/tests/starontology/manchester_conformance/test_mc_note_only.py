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
from .known_failures import ORACLE_REJECTS

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


CHECKS = {
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
    assert case_id in ORACLE_REJECTS, "only for cases the oracle rejects"
    if ORACLE_REJECTS[case_id][:1] == "F":
        request.applymarker(pytest.mark.xfail(reason=ORACLE_REJECTS[case_id], strict=True))
    g = parse_to_graph(CASE[case_id].text)
    CHECKS[case_id](g)


@pytest.mark.manchester_conformance
def test_every_note_allowed_reject_has_a_check():
    needs = {
        cid for cid, why in ORACLE_REJECTS.items()
        if "Output checked by test_mc_note_only.py" in why or why[:1] == "F"
    }
    assert needs <= set(CHECKS), f"oracle-rejected, Note-allowed cases with no expectation: {sorted(needs - set(CHECKS))}"


# Silence the unused-import linter for names used only in type positions above.
_ = (RDF,)
