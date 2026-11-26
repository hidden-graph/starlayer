"""``Result.serialize``: SPARQL Results JSON, XML, CSV and TSV for SELECT and ASK, RDF syntaxes for CONSTRUCT and DESCRIBE."""

from __future__ import annotations

import io
import json

import pyoxigraph as ox
import pytest
from starlayer.graph import StarLayerGraph

DATA = '<urn:a> <urn:p> "x"@en--rtl, "y"@fr, 5, <<( <urn:s> <urn:p> <urn:o> )>>, _:b, "q\\"u,o\\nte" .'
SELECT = "SELECT ?s ?o ?u WHERE { ?s <urn:p> ?o OPTIONAL { ?s <urn:zz> ?u } }"


@pytest.fixture
def g():
    graph = StarLayerGraph()
    graph.parse(data=DATA, format="turtle12")
    return graph


def _bindings(text):
    """Oxigraph's own JSON for the same query, with blank node ids left out (they differ between runs of a store)."""
    out = []
    for binding in json.loads(text)["results"]["bindings"]:
        out.append(json.dumps({k: {kk: vv for kk, vv in v.items() if not (kk == "value" and v["type"] == "bnode")} for k, v in binding.items()}, sort_keys=True))
    return sorted(out)


def test_json_is_what_oxigraph_writes_for_the_same_query(g):
    ours = g.query(SELECT).serialize()
    theirs = g.store.query(SELECT).serialize(format=ox.QueryResultsFormat.JSON).decode()
    assert json.loads(ours)["head"] == json.loads(theirs)["head"]
    assert _bindings(ours) == _bindings(theirs)


@pytest.mark.parametrize("format", ["csv", "tsv", "xml", "text/csv", ".tsv", "application/sparql-results+xml", ox.QueryResultsFormat.CSV])
def test_each_results_format_matches_what_oxigraph_writes(g, format):
    ours = g.query("SELECT ?o WHERE { ?s <urn:p> ?o FILTER(isLiteral(?o)) }").serialize(format=format)
    from starlayer.graph.execution.result import results_format

    theirs = g.store.query("SELECT ?o WHERE { ?s <urn:p> ?o FILTER(isLiteral(?o)) }").serialize(format=results_format(format)).decode()
    assert sorted(ours.splitlines()) == sorted(theirs.splitlines())


def test_the_rows_can_still_be_read_after_and_before_serializing(g):
    result = g.query(SELECT)
    rows_before = list(result)
    text = result.serialize()
    assert list(result) == rows_before and json.loads(text)["results"]["bindings"]
    fresh = g.query(SELECT)
    assert fresh.serialize() and len(fresh) == len(rows_before)


def test_a_directional_literal_and_a_triple_term_survive_the_json(g):
    parsed = ox.parse_query_results(g.query(SELECT).serialize(), format=ox.QueryResultsFormat.JSON)
    objects = {sol["o"] for sol in parsed}
    assert ox.Literal("x", language="en", direction=ox.BaseDirection.RTL) in objects
    assert ox.Triple(ox.NamedNode("urn:s"), ox.NamedNode("urn:p"), ox.NamedNode("urn:o")) in objects


def test_a_pre_bound_query_whose_extra_column_is_hidden_serializes_without_it(g):
    result = g.query("SELECT ?o WHERE { ?s <urn:p> ?o }", initBindings={"s": ox.NamedNode("urn:a"), "extra": ox.BlankNode("k")})
    assert json.loads(result.serialize())["head"]["vars"] == ["o"]


def test_ask_in_every_results_format(g):
    assert json.loads(g.query("ASK { ?s ?p ?o }").serialize()) == {"head": {}, "boolean": True}
    assert "<boolean>false</boolean>" in g.query("ASK { <urn:none> ?p ?o }").serialize(format="xml")
    assert g.query("ASK { ?s ?p ?o }").serialize(format="tsv").strip() == "true"


def test_to_a_path_and_to_a_file_object(g, tmp_path):
    path = tmp_path / "out.csv"
    assert g.query("SELECT ?o WHERE { <urn:a> <urn:p> 5 BIND(5 AS ?o) }").serialize(path, format="csv") is None
    assert path.read_bytes() == b"o\r\n5\r\n"
    binary, text = io.BytesIO(), io.StringIO()
    g.query("ASK {}").serialize(binary)
    g.query("ASK {}").serialize(text)
    assert binary.getvalue().decode() == text.getvalue()


def test_construct_and_describe_are_written_as_rdf(g):
    built = g.query("CONSTRUCT { ?s <urn:q> 5 } WHERE { ?s <urn:p> 5 }")
    assert built.serialize(format="nt").strip() == '<urn:a> <urn:q> "5"^^<http://www.w3.org/2001/XMLSchema#integer> .'
    described = g.query("DESCRIBE <urn:a>")
    assert "urn:p" in described.serialize()


def test_an_unknown_format_and_stray_options_are_errors(g):
    with pytest.raises(ValueError, match="unknown query results format"):
        g.query("ASK {}").serialize(format="docx")
    with pytest.raises(TypeError):
        g.query("ASK {}").serialize(prefixes={})


def test_reading_rows_or_triples_of_the_wrong_query_form_is_a_value_error(g):
    """A result in a state the read cannot use (an ASK has no rows, a SELECT has no triples) is a ``ValueError``, not a ``TypeError``."""
    with pytest.raises(ValueError, match="ASK result has no rows"):
        g.query("ASK {}").rows
    with pytest.raises(ValueError, match="ASK result has no rows"):
        g.query("ASK {}").bindings
    with pytest.raises(ValueError, match="SELECT result has no triples"):
        g.query("SELECT * WHERE {}").triples
