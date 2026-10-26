"""Regression tests for GitHub issues #139 (API contracts) and #140 (regressions): copies and pickles of a graph,
illegal triple positions, REGEX/REPLACE/ROUND/FLOOR/CEIL errors, ordering of language-tagged strings, and parser speed.

The oracle for the builtins is the XPath fn:matches/fn:replace/fn:round text that SPARQL 1.1 17.4 points to."""

import copy
import math
import pickle
import time

import pytest
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD
from starlayer.graph import StarLayerDataset, StarLayerGraph, TripleTerm
from starlayer.graph.parsers.syntax import split_statements_with_lines

A, B, C = (URIRef("http://e/" + x) for x in "abc")


def _value(expression: str, graph=None):
    graph = graph if graph is not None else StarLayerGraph()
    rows = list(graph.query(f"PREFIX xsd: <{XSD}> SELECT (({expression}) AS ?r) {{}}"))
    return rows[0][0]


# --- copy, deepcopy and pickle --------------------------------------------------------------------


@pytest.mark.parametrize("duplicate", [copy.copy, copy.deepcopy, lambda g: pickle.loads(pickle.dumps(g))])
def test_copy_of_graph_keeps_type_and_triple_terms(duplicate):
    graph = StarLayerGraph()
    term = TripleTerm(URIRef("urn:x"), URIRef("urn:y"), URIRef("urn:z"))
    graph.add((URIRef("urn:a"), URIRef("urn:b"), term))
    graph.bind("ex", "urn:ex#")
    clone = duplicate(graph)
    assert type(clone) is StarLayerGraph
    assert len(clone) == 1
    assert list(clone) == [(URIRef("urn:a"), URIRef("urn:b"), term)]
    assert dict(clone.namespaces()).get("ex") == URIRef("urn:ex#")


def test_deepcopy_is_independent():
    graph = StarLayerGraph()
    graph.add((A, B, C))
    clone = copy.deepcopy(graph)
    clone.add((A, B, A))
    assert len(graph) == 1 and len(clone) == 2


def test_deepcopy_of_dataset_keeps_triple_terms():
    dataset = StarLayerDataset()
    term = TripleTerm(URIRef("urn:x"), URIRef("urn:y"), URIRef("urn:z"))
    dataset.add((A, B, term, URIRef("urn:g")))
    clone = copy.deepcopy(dataset)
    assert type(clone) is StarLayerDataset
    assert [q[:3] for q in clone.quads()] == [(A, B, term)]


# --- illegal subject and predicate -----------------------------------------------------------------


@pytest.mark.parametrize(
    "triple", [(Literal("a"), B, C), (A, Literal("p"), C), (A, BNode(), C)], ids=["literal-subject", "literal-predicate", "bnode-predicate"]
)
def test_add_rejects_illegal_subject_or_predicate(triple):
    graph = StarLayerGraph()
    with pytest.raises(ValueError):
        graph.add(triple)
    with pytest.raises(ValueError):
        graph.addN([(*triple, graph)])
    with pytest.raises(ValueError):
        StarLayerDataset().add(triple)
    assert len(graph) == 0


# --- REGEX and REPLACE ---------------------------------------------------------------------------


def _names():
    graph = StarLayerGraph()
    graph.parse(data='@prefix : <http://e/> . :a :name "alpha(1)" . :b :name "beta" .', format="turtle")
    return graph


@pytest.mark.parametrize("pattern", ["(", "[", r"\p{L}+", "*a"])
def test_invalid_regex_drops_the_row_and_does_not_abort(pattern):
    graph = _names()
    query = 'SELECT ?s WHERE { ?s <http://e/name> ?n FILTER(REGEX(?n, "%s")) }' % pattern.replace("\\", "\\\\")
    assert list(graph.query(query)) == []
    unbound = list(graph.query('SELECT (REPLACE(?n, "%s", "x") AS ?r) WHERE { ?s <http://e/name> ?n }' % pattern.replace("\\", "\\\\")))
    assert [row[0] for row in unbound] == [None, None]


def test_invalid_regex_pattern_from_data_does_not_abort():
    graph = _names()
    graph.add((C, URIRef("http://e/pat"), Literal("(")))
    rows = list(graph.query("SELECT ?n WHERE { ?c <http://e/pat> ?p . ?s <http://e/name> ?n FILTER(REGEX(?n, ?p)) }"))
    assert rows == []


def test_invalid_regex_flag_is_an_error():
    assert list(_names().query('SELECT ?s WHERE { ?s <http://e/name> ?n FILTER(REGEX(?n, "a", "z")) }')) == []


def test_regex_valid_patterns_still_match():
    graph = _names()
    assert len(list(graph.query('SELECT ?s WHERE { ?s <http://e/name> ?n FILTER(REGEX(?n, "ALPHA", "i")) }'))) == 1
    assert len(list(graph.query('SELECT ?s WHERE { ?s <http://e/name> ?n FILTER(REGEX(?n, "(1)", "q")) }'))) == 1


def test_replace_dollar_zero_is_the_whole_match():
    assert str(_value("REPLACE('abc', 'b', '<$0>')")) == "a<b>c"


def test_replace_groups_and_escapes():
    assert str(_value(r"REPLACE('abc', '(a)(b)', '$2$1$3\\$')")) == "ba$c"


def test_replace_flags_are_flags():
    assert str(_value("REPLACE('abcB', 'b', '[$0]', 'i')")) == "a[b]c[B]"


@pytest.mark.parametrize("pattern", ["x*", ""])
def test_replace_with_zero_length_match_is_an_error(pattern):
    assert _value(f"REPLACE('abc', '{pattern}', '-')") is None


def test_replace_with_invalid_replacement_string_is_an_error():
    assert _value("REPLACE('abc', 'b', '$')") is None


# --- ROUND, FLOOR, CEIL -----------------------------------------------------------------------------


@pytest.mark.parametrize("function", ["ROUND", "FLOOR", "CEIL"])
@pytest.mark.parametrize("lexical", ["INF", "-INF"])
def test_rounding_infinity_is_itself(function, lexical):
    value = _value(f"{function}('{lexical}'^^xsd:double)")
    assert value.toPython() == float(lexical.lower().replace("inf", "inf"))


@pytest.mark.parametrize("function", ["ROUND", "FLOOR", "CEIL"])
def test_rounding_nan_is_nan(function):
    assert math.isnan(_value(f"{function}('NaN'^^xsd:double)").toPython())


@pytest.mark.parametrize("function", ["ROUND", "FLOOR", "CEIL"])
def test_rounding_a_huge_double_is_itself(function):
    assert _value(f"{function}(1e300)").toPython() == 1e300


def test_rounding_ordinary_values_unchanged():
    assert float(_value("ROUND(2.5)")) == 3 and float(_value("ROUND(-2.5)")) == -2
    assert float(_value("FLOOR(-2.1)")) == -3 and float(_value("CEIL(2.1)")) == 3


def test_rounding_special_double_in_data_does_not_abort_the_query():
    graph = StarLayerGraph()
    graph.add((A, B, Literal("NaN", datatype=XSD.double)))
    graph.add((A, B, Literal("1e999", datatype=XSD.double)))
    rows = list(graph.query("SELECT ?o (ROUND(?o) AS ?r) WHERE { ?s ?p ?o }"))
    assert len(rows) == 2


# --- ordering of a language-tagged string against a number --------------------------------------------


def test_language_tagged_string_is_not_greater_than_a_number():
    graph = StarLayerGraph()
    graph.parse(data='@prefix : <http://e/> . :a :r 1, 2.5, "x", "abc"@en-US .', format="turtle")
    rows = graph.query("SELECT ?o WHERE { <http://e/a> <http://e/r> ?o FILTER(?o > 1) }")
    assert [str(r[0]) for r in rows] == ["2.5"]


# --- the Turtle splitter is linear -----------------------------------------------------------------------


def test_split_statements_line_numbers():
    text = "@prefix : <http://e/> .\n:a :p :b .\n\n:c :p :d .\n"
    assert [line for _, line in split_statements_with_lines(text)] == [1, 2, 4]


def test_split_statements_line_numbers_do_not_rescan_the_prefix(monkeypatch):
    from starlayer.graph.parsers import syntax

    line = ":s :p :o .\n"
    document = line * 100_000
    # Hand the line counter many statement offsets without the (separately linear) splitter: counting newlines from the
    # start of the document for every statement is quadratic, about 5 GB of scanning here.
    monkeypatch.setattr(syntax, "_split_statements_impl", lambda data: ((":s :p :o", i * len(line)) for i in range(100_000)))
    start = time.perf_counter()
    pairs = split_statements_with_lines(document)
    assert time.perf_counter() - start < 3
    assert pairs[-1][1] == 100_000


# --- encoders and decoders of SPARQL as RDF -------------------------------------------------------------


def test_query_encoders_raise_type_errors():
    from rdflib.plugins.sparql import prepareQuery
    from starlayer.sparql import from_rdf, to_rdf

    with pytest.raises(TypeError):
        to_rdf.query_to_rdf(None)
    with pytest.raises(TypeError):
        to_rdf.update_to_rdf(None)
    with pytest.raises(TypeError):
        to_rdf.queries_to_collection("SELECT * { ?s ?p ?o }")
    with pytest.raises(ValueError):
        from_rdf.rdf_to_query(StarLayerGraph(), BNode())
    with pytest.raises(ValueError):
        from_rdf.rdf_to_update(StarLayerGraph(), BNode())
    with pytest.raises(ValueError):
        from_rdf.rdf_to_query(StarLayerGraph(), None)
    graph, root = to_rdf.query_to_rdf(prepareQuery("SELECT * { ?s ?p ?o }"))
    assert from_rdf.rdf_to_query(graph, root) is not None


# --- OWL RL reports an inconsistency once ------------------------------------------------------------------


def test_owl_rl_inconsistency_message_is_not_repeated_per_pass():
    from starlayer.graph import ENTAILMENT

    graph = StarLayerGraph()
    graph.parse(
        data="@prefix ex: <http://e/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
        "ex:Dog owl:disjointWith ex:Cat . ex:fido a ex:Dog, ex:Cat .",
        format="turtle",
    )
    closed = graph.infer(entailment=ENTAILMENT["OWL-RDF-Based"])
    messages = list(closed.triples((None, URIRef("http://www.daml.org/2002/03/agents/agent-ont#error"), None)))
    assert len(messages) == 1
