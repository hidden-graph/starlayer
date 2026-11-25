"""Lexical edge cases of the SRL parser (negative numbers, string and unicode escapes, local-name escapes; once upstream-issues
items 19 to 21 against rdflib's grammar) and a bare ``~`` in a reified triple (SPARQL 1.2 ``Reifier``)."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.sparql._oxterms import RDF, XSD
from starlayer.sparql.srl import parse_ruleset

PRE = "PREFIX : <http://e/>\n"


def _objects(text: str):
    rs = parse_ruleset(PRE + text)
    return [t.object for t in rs.data[0].triples]


@pytest.mark.parametrize(
    ("lexical", "datatype"),
    [("-1.5", XSD.decimal), ("-0.5", XSD.decimal), ("-.5", XSD.decimal), ("-1", XSD.integer)],
)
def test_negative_numbers(lexical, datatype):
    (obj,) = _objects(f"DATA {{ :a :b {lexical} }}")
    # lexical fidelity: the form is kept as written ("-.5" stays "-.5"), the value is the same
    assert obj.value == lexical
    assert obj.datatype == datatype


@pytest.mark.parametrize(
    ("source", "value"),
    [(r'"a\'b"', "a'b"), (r"'a\"b'", 'a"b'), (r'"a\"b"', 'a"b'), (r'"tab\t"', "tab\t")],
)
def test_string_escapes(source, value):
    (obj,) = _objects(f"DATA {{ :a :b {source} }}")
    assert obj == ox.Literal(value)


def test_unicode_escapes():
    (obj,) = _objects(r'DATA { :a :b "é \U0001F600" }')
    assert obj == ox.Literal("é 😀")


def test_local_name_escapes():
    rs = parse_ruleset(PRE + r"DATA { :a\-b :c\.d :e%20f }")
    (t,) = rs.data[0].triples
    assert (t.subject, t.predicate, t.object) == (
        ox.NamedNode("http://e/a-b"),
        ox.NamedNode("http://e/c.d"),
        ox.NamedNode("http://e/e%20f"),
    )


def test_bare_tilde_in_a_reified_triple_names_a_fresh_reifier():
    rs = parse_ruleset(PRE + "RULE { ?x :p ?y } WHERE { << ?x :q ?y ~ >> :source ?s }")
    triples = rs.rules[0].body
    reifies = [t for t in triples if t.predicate == RDF.reifies]
    assert len(reifies) == 1
    assert isinstance(reifies[0].subject, ox.BlankNode)


def test_evaluation_compares_values_not_lexical_forms():
    from starlayer.graph import StarLayerGraph as Graph

    rs = parse_ruleset(
        PRE + "RULE { ?s :neg true } WHERE { ?s :v ?n FILTER(?n < 0 && ?n = -0.5) }\nDATA { :a :v -.5 . :b :v .5 }",
    )
    out = rs.infer(Graph())
    assert (ox.NamedNode("http://e/a"), ox.NamedNode("http://e/neg"), ox.Literal("true", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))) in out
    assert (ox.NamedNode("http://e/b"), ox.NamedNode("http://e/neg"), ox.Literal("true", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))) not in out
