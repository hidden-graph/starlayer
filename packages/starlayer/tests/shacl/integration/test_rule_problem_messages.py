"""What a tool can say about a rule that is wrong: each defect of a rule, a template or a query is a result of its own, with a message that names it
(GitHub: the workbench audit of rule validation)."""

import pytest
from rdflib import Graph, URIRef
from starlayer.shacl import MetaShaclError, ShapeError, meta_shapes
from starlayer.shacl.meta_shapes import (
    meta_validate,
    parameter_value_shapes,
    sparql_query_problems,
)
from starlayer.shacl_engine.terms import text

PRE = """@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:R .
"""
TEMPLATE = 'ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:parameter [ sh:path ex:p ] ; sh:construct "CONSTRUCT { $this ex:q $p } WHERE { }" .\n'


def messages(turtle: str) -> list[str]:
    """The messages of every result of the shapes about shapes (with the template and parameter shapes) over ``turtle``."""
    shapes = Graph().parse(data=PRE + turtle, format="turtle")
    try:
        _conforms, _report, text = meta_validate(shapes, extra_graphs=[parameter_value_shapes(shapes)])
    except MetaShaclError as exc:  # a violation makes the shapes graph invalid; the report is in the message
        text = str(exc)
    return sorted(line.split("Message:", 1)[1].strip() for line in text.splitlines() if "Message:" in line)


@pytest.mark.parametrize("turtle, expected", [
    ('ex:R a sh:SPARQLRule .', "A SPARQL rule has exactly one sh:construct"),
    ('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { } WHERE { }", "CONSTRUCT { ?a ?b ?c } WHERE { }" .', "A SPARQL rule has exactly one sh:construct"),
    ('ex:R a sh:TripleRule ; sh:subject sh:this, ex:a ; sh:predicate ex:q ; sh:object 1 .', "A triple rule has at most one sh:subject."),
    ('ex:R a sh:TripleRule ; sh:subject sh:this ; sh:predicate "q" ; sh:object 1 .', "A triple whose predicate is a literal is skipped"),
    ('ex:R a sh:TripleRule ; sh:subject "s" ; sh:predicate ex:q ; sh:object 1 .', "A triple whose subject is a literal is skipped"),
    (TEMPLATE + 'ex:T2 a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:construct "CONSTRUCT { } WHERE { }" .\nex:R a ex:T, ex:T2 ; ex:p ex:a .', "an instance of more than one"),
    ('ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:parameter [ sh:path ex:p ] ; sh:construct "CONSTRUCT { $this ex:q $other } WHERE { }" .\nex:R a ex:T ; ex:p ex:a .', "$other, which no parameter binds"),
])
def test_a_defect_of_a_rule_is_reported_with_a_message_that_names_it(turtle, expected):
    found = messages(turtle)
    assert any(expected in m for m in found), found


@pytest.mark.parametrize("turtle", [
    'ex:R a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:q ; sh:object 1 .',
    'ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:q 1 } WHERE { }" .',
    TEMPLATE + "ex:R a ex:T ; ex:p ex:a .",
    # a variable the query's own pattern binds is not a problem
    'ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:parameter [ sh:path ex:p ] ; sh:construct "CONSTRUCT { ?o $p ?s } WHERE { ?s $p ?o }" .\nex:R a ex:T ; ex:p ex:knows .',
])
def test_a_well_formed_rule_has_nothing_to_report(turtle):
    assert messages(turtle) == []


def problems(turtle: str):
    return [(text(n).rsplit("/", 1)[-1], text(p).rsplit("#", 1)[-1], m) for n, p, m in sparql_query_problems(Graph().parse(data=PRE + turtle, format="turtle"))]


def test_a_query_that_is_not_sparql_is_a_problem_of_the_node_that_holds_it():
    found = problems('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:q 1 WHERE {" .')
    assert [(n, p) for n, p, _m in found] == [("R", "construct")] and "not valid SPARQL" in found[0][2]


def test_a_query_of_another_form_than_its_property_says_is_a_problem():
    found = problems('ex:R a sh:SPARQLRule ; sh:construct "SELECT * WHERE { ?s ?p ?o }" .')
    assert found and "must hold a CONSTRUCT query, but this is a SELECT query" in found[0][2]
    assert problems('ex:C sh:select "ASK { ?s ?p ?o }" .') and "must hold a SELECT query" in problems('ex:C sh:select "ASK { ?s ?p ?o }" .')[0][2]


def test_a_prefix_the_file_binds_is_known_to_its_queries_but_an_unknown_one_is_not():
    assert problems('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:q 1 } WHERE { }" .') == []
    found = problems('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this foo:q 1 } WHERE { }" .')
    assert found and "foo" in found[0][2]


def test_check_sparql_query_text_still_raises_the_first_problem():
    shapes = Graph().parse(data=PRE + 'ex:R a sh:SPARQLRule ; sh:construct "SELECT * WHERE { ?s ?p ?o }" .', format="turtle")
    with pytest.raises(ShapeError, match="must hold a CONSTRUCT query"):
        meta_shapes.check_sparql_query_text(shapes)


def test_a_node_that_holds_prefix_declarations_is_inferred_to_be_a_prefix_set():
    from rdflib import RDF
    from starlayer.shacl.shape_types import infer_types

    shapes = Graph().parse(data=PRE + 'ex:Prefixes sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .', format="turtle")
    inferred = infer_types(shapes)
    assert (URIRef("http://example.org/Prefixes"), RDF.type, URIRef("https://github.com/hidden-graph/starlayer/ns/shacl#PrefixSet")) in inferred
    assert (URIRef("http://example.org/Prefixes"), RDF.type, URIRef("https://github.com/hidden-graph/starlayer/ns/shacl#PrefixSet")) not in shapes, "inferred, not written"


def test_an_entailment_nothing_provides_is_a_warning_and_the_regimes_it_provides_are_not():
    from starlayer.graph.graph.entailment_regimes import SUPPORTED_REGIMES

    def about_entailment(turtle):
        return [m for m in messages(turtle) if "entailment" in m]

    assert about_entailment("ex:G a sh:ShapesGraph ; sh:entailment <http://www.w3.org/ns/entailment/D> .")
    for regime in SUPPORTED_REGIMES:
        assert about_entailment(f"ex:G a sh:ShapesGraph ; sh:entailment <{regime}> .") == [], regime
    assert about_entailment("ex:G a sh:ShapesGraph ; sh:entailment sh:RulesEntailment .") == []
    assert about_entailment("ex:Set a sh:RuleSet .\nex:G a sh:ShapesGraph ; sh:entailment ex:Set .") == []
