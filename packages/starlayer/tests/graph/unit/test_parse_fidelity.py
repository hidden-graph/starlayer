"""The plain format names (turtle, ttl, nt, nquads, trig, xml) keep every literal's lexical form as written (Stage 0.4)."""

from __future__ import annotations

import pytest
import rdflib
from rdflib import Graph, Literal, URIRef
from starlayer.graph.graph import StarLayerDataset, StarLayerGraph

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
WANTED = {(v, X + t) for v, t in CASES}


def _forms(triples):
    return {(str(o), str(o.datatype)) for _s, _p, o in triples}


@pytest.mark.parametrize("fmt, data", [
    ("turtle", TTL), ("ttl", TTL), ("text/turtle", TTL), ("turtle12", TTL),
    ("nt", NT), ("ntriples", NT), ("nt12", NT), ("application/n-triples", NT),
    ("nquads", NQ), ("nq12", NQ), ("trig", TRIG), ("trig12", TRIG),
    ("xml", XML), ("application/rdf+xml", XML), ("rdfxml12", XML),
])
def test_graph_parse_keeps_lexical_forms(fmt, data):
    g = StarLayerGraph().parse(data=data, format=fmt)
    assert _forms(g.triples((None, None, None))) == WANTED


@pytest.mark.parametrize("fmt, data", [("turtle", TTL), ("ttl", TTL), ("nt", NT), ("xml", XML), ("trig", TRIG), ("nquads", NQ)])
def test_dataset_parse_keeps_lexical_forms(fmt, data):
    ds = StarLayerDataset().parse(data=data, format=fmt)
    assert _forms(t[:3] for t in ds.quads((None, None, None, None))) == WANTED


def test_a_file_with_a_known_extension_is_parsed_faithfully_without_a_format(tmp_path):
    path = tmp_path / "d.ttl"
    path.write_text(TTL)
    assert _forms(StarLayerGraph().parse(str(path)).triples((None, None, None))) == WANTED
    assert _forms(StarLayerGraph().parse(location=str(path), format="turtle").triples((None, None, None))) == WANTED


def test_plain_rdflib_in_the_same_process_still_normalises():
    StarLayerGraph().parse(data=XML, format="xml")
    g = Graph().parse(data=XML, format="xml")
    assert rdflib.NORMALIZE_LITERALS is True
    assert {str(o) for _s, _p, o in g} >= {"4", "true", "false"}


def test_nothing_is_renormalised_on_copy_or_serialization_round_trip():
    g = StarLayerGraph().parse(data=TTL, format="turtle")
    copy = StarLayerGraph()
    for t in g:
        copy.add(t)
    again = StarLayerGraph().parse(data=copy.serialize(format="turtle12"), format="turtle")
    assert _forms(again.triples((None, None, None))) == WANTED
    nt = StarLayerGraph().parse(data=g.serialize(format="nt12"), format="nt")
    assert _forms(nt.triples((None, None, None))) == WANTED


def test_a_query_result_does_not_change_a_stored_lexical_form():
    g = StarLayerGraph().parse(data=TTL, format="turtle")
    rows = {(str(r[0]), str(r[0].datatype)) for r in g.query("SELECT ?o WHERE { ?s ?p ?o }")}
    assert ("04", X + "integer") in rows and ("none", X + "boolean") in rows


def test_the_literal_term_is_the_one_written():
    g = StarLayerGraph().parse(data=TTL, format="turtle")
    assert Literal("04", datatype=URIRef(X + "integer"), normalize=False) in set(g.objects())
