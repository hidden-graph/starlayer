"""Loading a literal that Oxigraph keeps in another form than written warns at the load (StarLayer issue #190)."""

from __future__ import annotations

import warnings

import pyoxigraph as ox
import pytest

from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.lexical import rewritten_count, stored_form
from starlayer.shacl.engine.terms import StarLayerFidelityWarning

XSD = "http://www.w3.org/2001/XMLSchema#"
PFX = "@prefix ex: <http://example.org/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
EX = "http://example.org/"


def _fidelity(call):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    return [w for w in caught if issubclass(w.category, StarLayerFidelityWarning)]


def _lit(value, datatype="integer"):
    return ox.Literal(value, datatype=ox.NamedNode(XSD + datatype))


def _triple(literal):
    return (ox.NamedNode(EX + "a"), ox.NamedNode(EX + "p"), literal)


def test_parse_warns_once_and_names_the_rewritten_literals():
    g = StarLayerGraph()
    (w,) = _fidelity(lambda: g.parse(data=PFX + 'ex:a ex:p "04"^^xsd:integer, "1"^^xsd:boolean, "4.50"^^xsd:decimal, "x" , 7 .', format="turtle"))
    text = str(w.message)
    assert text.startswith("3 literals were stored in a different form than written")
    assert '"04"^^xsd:integer as "4"' in text and '"1"^^xsd:boolean as "true"' in text and "#190" in text
    assert rewritten_count(g.store) == 3


def test_parse_warns_at_the_callers_line():
    g = StarLayerGraph()
    (w,) = _fidelity(lambda: g.parse(data=PFX + 'ex:a ex:p "04"^^xsd:integer .', format="turtle"))
    assert w.filename == __file__


def test_parse_of_literals_that_are_already_canonical_does_not_warn():
    g = StarLayerGraph()
    assert _fidelity(lambda: g.parse(data=PFX + 'ex:a ex:p 4, true, 4.5, "x", "x"@en, "2026-01-01"^^xsd:date, <http://example.org/b> .', format="turtle")) == []
    assert rewritten_count(g.store) == 0


def test_a_derived_integer_type_is_reported_as_retyped():
    g = StarLayerGraph()
    (w,) = _fidelity(lambda: g.parse(data=PFX + 'ex:a ex:p "300"^^xsd:byte .', format="turtle"))
    assert '"300"^^xsd:byte as "300"^^xsd:integer' in str(w.message)


@pytest.mark.parametrize("write", ["add", "extend", "addN"])
def test_add_extend_and_addN_warn(write):
    g = StarLayerGraph()
    triple = _triple(_lit("05"))
    calls = {
        "add": lambda: g.add(triple),
        "extend": lambda: g.extend([triple]),
        "addN": lambda: g.addN([(*triple, g._add_graph())]),
    }
    (w,) = _fidelity(calls[write])
    assert '"05"^^xsd:integer as "5"' in str(w.message) and rewritten_count(g.store) == 1


def test_the_count_adds_up_over_several_loads():
    g = StarLayerGraph()
    _fidelity(lambda: g.add(_triple(_lit("05"))))
    _fidelity(lambda: g.add(_triple(_lit("06"))))
    assert rewritten_count(g.store) == 2


def test_a_dataset_load_warns():
    d = StarLayerDataset()
    (w,) = _fidelity(lambda: d.parse(data=PFX + 'ex:a ex:p "04"^^xsd:integer .', format="turtle"))
    assert "1 literal was stored" in str(w.message)


def test_the_warning_is_filterable():
    g = StarLayerGraph()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        g.parse(data=PFX + 'ex:a ex:p "04"^^xsd:integer .', format="turtle")
    assert caught == []


def test_a_shapes_graph_load_warns_too():
    shapes = StarLayerGraph()
    (w,) = _fidelity(lambda: shapes.parse(data=PFX + '@prefix sh: <http://www.w3.org/ns/shacl#> . ex:S sh:property [ sh:hasValue "1"^^xsd:boolean ] .', format="turtle"))
    assert '"1"^^xsd:boolean as "true"' in str(w.message)


CASES = [
    ("04", "integer"), ("-0", "integer"), ("0", "integer"), ("-5", "integer"), ("+5", "integer"), ("4", "integer"), ("5", "unsignedByte"),
    ("1", "boolean"), ("true", "boolean"), ("false", "boolean"), ("none", "boolean"),
    ("4.50", "decimal"), ("4.0", "decimal"), ("4", "decimal"), ("-0", "decimal"), ("-0.5", "decimal"), (".5", "decimal"), ("0.5", "decimal"), ("-12.25", "decimal"),
    ("1e3", "double"), ("1.5", "double"), ("1.0", "float"),
    ("2000-01-01T00:00:00.0Z", "dateTime"), ("2000-01-01T00:00:00Z", "dateTime"), ("24:00:00", "time"), ("PT60S", "duration"), ("2026-01-01", "date"),
]


@pytest.mark.parametrize("value, datatype", CASES)
def test_stored_form_matches_what_the_store_returns(value, datatype):
    literal = _lit(value, datatype)
    scratch = ox.Store()
    scratch.add(ox.Quad(*_triple(literal), ox.DefaultGraph()))
    assert stored_form(literal) == next(iter(scratch)).object
