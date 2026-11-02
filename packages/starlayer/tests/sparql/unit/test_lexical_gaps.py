"""Regression tests for the rdflib lexical defects repaired in ``_grammar12._fix_rdflib_lexical_gaps``
(upstream-issues items 19 to 21) and for a bare ``~`` in a reified triple (SPARQL 1.2 ``Reifier``)."""

from __future__ import annotations

import pytest
import starlayer.sparql  # noqa: F401 - installs the grammar fixes
from rdflib import RDF, XSD, BNode, Literal, URIRef
from starlayer.sparql.srl import parse_ruleset

PRE = "PREFIX : <http://e/>\n"


def _objects(text: str):
    rs = parse_ruleset(PRE + text, validate=False)
    return [t.object for t in rs.data[0].triples]


@pytest.mark.parametrize(
    ("lexical", "datatype"),
    [("-1.5", XSD.decimal), ("-0.5", XSD.decimal), ("-.5", XSD.decimal), ("-1", XSD.integer)],
)
def test_negative_numbers(lexical, datatype):
    (obj,) = _objects(f"DATA {{ :a :b {lexical} }}")
    assert obj == Literal(lexical.replace("-.", "-0."), datatype=datatype)


@pytest.mark.parametrize(
    ("source", "value"),
    [(r'"a\'b"', "a'b"), (r"'a\"b'", 'a"b'), (r'"a\"b"', 'a"b'), (r'"tab\t"', "tab\t")],
)
def test_string_escapes(source, value):
    (obj,) = _objects(f"DATA {{ :a :b {source} }}")
    assert obj == Literal(value)


def test_unicode_escapes():
    (obj,) = _objects(r'DATA { :a :b "é \U0001F600" }')
    assert obj == Literal("é 😀")


def test_local_name_escapes():
    rs = parse_ruleset(PRE + r"DATA { :a\-b :c\.d :e%20f }", validate=False)
    (t,) = rs.data[0].triples
    assert (t.subject, t.predicate, t.object) == (
        URIRef("http://e/a-b"),
        URIRef("http://e/c.d"),
        URIRef("http://e/e%20f"),
    )


def test_plain_sparql_gets_the_same_fixes():
    from rdflib.plugins.sparql import prepareQuery

    q = prepareQuery(PRE + r"""SELECT * WHERE { ?s ?p -1.5, "a\'b" . :a\-b ?p ?o }""")
    triples = q.algebra.p.p.triples
    assert (triples[0][2], triples[1][2]) == (Literal("-1.5", datatype=XSD.decimal), Literal("a'b"))
    assert triples[2][0] == URIRef("http://e/a-b")


def test_bare_tilde_in_a_reified_triple_names_a_fresh_reifier():
    rs = parse_ruleset(PRE + "RULE { ?x :p ?y } WHERE { << ?x :q ?y ~ >> :source ?s }", validate=False)
    triples = rs.rules[0].body
    reifies = [t for t in triples if t.predicate == URIRef(str(RDF._NS) + "reifies")]
    assert len(reifies) == 1
    assert isinstance(reifies[0].subject, BNode)
