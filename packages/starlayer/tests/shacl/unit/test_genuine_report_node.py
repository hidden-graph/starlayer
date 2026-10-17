"""Choosing "the" sh:ValidationReport node when the report also contains an
incidental one.

A fixture whose data graph already contains a sh:ValidationReport (the W3C
suite's expected-result blocks) gets that block copied into the output report
when a violation's value/focus node is it. Post-processing must then act on the
genuine report - not on whichever typed node comes first, which used to make
sh:targetWhere flaky: _relabel_validation_report_node renamed the incidental
copy to "report", rewriting a data node's identity inside the results.
"""

import pytest
from rdflib import RDF, BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD
from starlayer.shacl.validator import _find_genuine_report_node, _relabel_validation_report_node

SH = "http://www.w3.org/ns/shacl#"
EX = "http://example.org/"


def _report(order: str):
    """A genuine report with one result whose focus node and value are an
    *incidental* ValidationReport-typed data node. `order` decides which of the
    two typed nodes is added to the graph first."""
    genuine, incidental, result = BNode("genuine"), BNode("incidental"), BNode("result")
    g = Graph()

    def add_genuine():
        g.add((genuine, RDF.type, URIRef(SH + "ValidationReport")))
        g.add((genuine, URIRef(SH + "conforms"), Literal(False, datatype=XSD.boolean)))
        g.add((genuine, URIRef(SH + "result"), result))
        g.add((result, RDF.type, URIRef(SH + "ValidationResult")))
        g.add((result, URIRef(SH + "focusNode"), incidental))
        g.add((result, URIRef(SH + "value"), incidental))

    def add_incidental():
        g.add((incidental, RDF.type, URIRef(SH + "ValidationReport")))
        g.add((incidental, URIRef(SH + "conforms"), Literal(False, datatype=XSD.boolean)))

    for part in (add_incidental, add_genuine) if order == "incidental-first" else (add_genuine, add_incidental):
        part()
    return g, genuine, incidental


@pytest.mark.parametrize("order", ["incidental-first", "genuine-first"])
def test_genuine_report_is_chosen_whatever_the_insertion_order(order):
    g, genuine, _ = _report(order)
    assert _find_genuine_report_node(g) == genuine


@pytest.mark.parametrize("order", ["incidental-first", "genuine-first"])
def test_relabel_renames_the_genuine_report_and_leaves_the_data_node_alone(order):
    g, genuine, incidental = _report(order)
    _relabel_validation_report_node(g)
    # the result still names the original data node as its focus node and value
    focus = set(g.objects(None, URIRef(SH + "focusNode")))
    value = set(g.objects(None, URIRef(SH + "value")))
    assert focus == {incidental} and value == {incidental}
    # and it is the genuine report that was renamed
    assert (BNode("report"), RDF.type, URIRef(SH + "ValidationReport")) in g
    assert (genuine, RDF.type, URIRef(SH + "ValidationReport")) not in g


def test_the_librarys_own_report_link_does_not_hide_the_genuine_report():
    """<graph> sh:validationReport <report> points at the genuine report; that
    must not make it look like the incidental one."""
    g, genuine, _ = _report("incidental-first")
    g.add((URIRef(EX + "dataGraph"), URIRef(SH + "validationReport"), genuine))
    assert _find_genuine_report_node(g) == genuine


def test_a_graph_with_one_or_no_report_is_unchanged():
    g = Graph()
    assert _find_genuine_report_node(g) is None
    only = BNode("only")
    g.add((only, RDF.type, URIRef(SH + "ValidationReport")))
    assert _find_genuine_report_node(g) == only
