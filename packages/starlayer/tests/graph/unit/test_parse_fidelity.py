"""The plain format names (turtle, ttl, nt, nquads, trig, xml) read a literal into Oxigraph's canonical lexical form
(owner decision O1, 2026-11-06: fidelity to the old rdflib class is not a goal). An ill-formed literal ("none"^^xsd:boolean)
and a dateTime are kept as written; the canonical forms are in CANON."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
import rdflib
from rdflib import Graph
from starlayer.graph.oxgraph import OxDataset, OxGraph

X = "http://www.w3.org/2001/XMLSchema#"
CASES = [("04", "integer"), ("1", "boolean"), ("none", "boolean"), ("4.0", "decimal"), ("+1.50", "double"), ("2020-01-01T00:00:00Z", "dateTime")]
_OBJECTS = ", ".join(f'"{v}"^^x:{t}' for v, t in CASES)
TTL = f"@prefix x: <{X}> . <http://e/s> <http://e/p> {_OBJECTS} ."
NT = "".join(f'<http://e/s> <http://e/p> "{v}"^^<{X}{t}> .\n' for v, t in CASES)
NQ = NT.replace(" .\n", " <http://e/g> .\n")
TRIG = f"@prefix x: <{X}> . <http://e/g> {{ <http://e/s> <http://e/p> {_OBJECTS} }}"
XML = (
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:x="http://e/"><rdf:Description rdf:about="http://e/s">'
    + "".join(f'<x:p rdf:datatype="{X}{t}">{v}</x:p>' for v, t in CASES)
    + "</rdf:Description></rdf:RDF>"
)
# what Oxigraph stores for CASES: 04 -> 4, "1" boolean -> true, 4.0 decimal -> 4, +1.50 double -> 1.5
CANON = {("4", "integer"), ("true", "boolean"), ("none", "boolean"), ("4", "decimal"), ("1.5", "double"), ("2020-01-01T00:00:00Z", "dateTime")}
WANTED = {(v, X + t) for v, t in CANON}


def _forms(triples):
    return {(o.value, o.datatype.value) for _s, _p, o in triples}


@pytest.mark.parametrize("fmt, data", [
    ("turtle", TTL), ("ttl", TTL), ("text/turtle", TTL), ("turtle12", TTL),
    ("nt", NT), ("ntriples", NT), ("nt12", NT), ("application/n-triples", NT),
    ("xml", XML), ("application/rdf+xml", XML), ("rdfxml12", XML),
])
def test_graph_parse_keeps_lexical_forms(fmt, data):
    g = OxGraph().parse(data=data, format=fmt)
    assert _forms(g.triples((None, None, None))) == WANTED


@pytest.mark.parametrize("fmt, data", [("turtle", TTL), ("ttl", TTL), ("nt", NT), ("xml", XML), ("trig", TRIG), ("trig12", TRIG), ("nquads", NQ), ("nq12", NQ)])
def test_dataset_parse_keeps_lexical_forms(fmt, data):
    ds = OxDataset().parse(data=data, format=fmt)
    assert _forms((q.subject, q.predicate, q.object) for q in ds.quads((None, None, None, None))) == WANTED


def test_a_file_with_a_known_extension_is_parsed_faithfully_without_a_format(tmp_path):
    path = tmp_path / "d.ttl"
    path.write_text(TTL)
    assert _forms(OxGraph().parse(str(path)).triples((None, None, None))) == WANTED
    assert _forms(OxGraph().parse(str(path), format="turtle").triples((None, None, None))) == WANTED


def test_plain_rdflib_in_the_same_process_still_normalises():
    OxGraph().parse(data=XML, format="xml")
    g = Graph().parse(data=XML, format="xml")
    assert rdflib.NORMALIZE_LITERALS is True
    assert {str(o) for _s, _p, o in g} >= {"4", "true", "false"}


def test_nothing_is_renormalised_on_copy_or_serialization_round_trip():
    g = OxGraph().parse(data=TTL, format="turtle")
    copy = OxGraph()
    for t in g:
        copy.add(t)
    again = OxGraph().parse(data=copy.serialize(format="turtle12"), format="turtle")
    assert _forms(again.triples((None, None, None))) == WANTED
    nt = OxGraph().parse(data=g.serialize(format="nt12"), format="nt")
    assert _forms(nt.triples((None, None, None))) == WANTED


def test_a_query_result_does_not_change_a_stored_lexical_form():
    g = OxGraph().parse(data=TTL, format="turtle")
    rows = {(r[0].value, r[0].datatype.value) for r in g.query("SELECT ?o WHERE { ?s ?p ?o }")}
    assert rows == WANTED


def test_the_literal_term_is_the_one_written():
    g = OxGraph().parse(data=TTL, format="turtle")
    assert ox.Literal("4", datatype=ox.NamedNode(X + "integer")) in set(g.objects())
    assert ox.Literal("04", datatype=ox.NamedNode(X + "integer")) not in set(g.objects())
