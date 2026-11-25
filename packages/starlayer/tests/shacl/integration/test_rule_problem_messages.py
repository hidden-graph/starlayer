"""What a tool can say about a rule that is wrong: each defect of a rule, a template or a query is a result of its own, with a message that names it
(GitHub: the workbench audit of rule validation)."""

import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaShaclError
from starlayer.shacl.engine.terms import text
from starlayer.shacl.meta_shapes import (
    meta_validate,
    parameter_value_shapes,
    sparql_query_problems,
)
from tests.support.terms import NamedNode

PRE = """@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:R .
"""
TEMPLATE = 'ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:parameter [ sh:path ex:p ] ; sh:construct "CONSTRUCT { $this ex:q $p } WHERE { }" .\n'


def messages(turtle: str) -> list[str]:
    """The messages of every result of the shapes about shapes (with the template and parameter shapes) over ``turtle``."""
    shapes = Graph().parse(data=PRE + turtle, format="turtle")
    try:
        _conforms, _report, text = meta_validate(shapes, meta_shapes_extra=[parameter_value_shapes(shapes)])
    except MetaShaclError as exc:  # a violation makes the shapes graph invalid; the report is in the message
        text = exc.report_text
    # the defects of the embedded SPARQL are results of the same check now; these tests are about the shapes of shapes
    kept, in_sparql = [], False
    for line in text.splitlines():
        if line and not line.startswith("\t"):
            in_sparql = "SPARQLQueryTextShape" in line
        if "Message:" in line and not in_sparql:
            kept.append(line.split("Message:", 1)[1].strip())
    return sorted(kept)


@pytest.mark.parametrize("turtle, expected", [
    ('ex:R a sh:SPARQLRule .', "A SPARQL rule has exactly one sh:construct"),
    ('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { } WHERE { }", "CONSTRUCT { ?a ?b ?c } WHERE { }" .', "A SPARQL rule has exactly one sh:construct"),
    ('ex:R a sh:TripleRule ; sh:subject [ shnex:var "focusNode" ], ex:a ; sh:predicate ex:q ; sh:object 1 .', "A triple rule has at most one sh:subject."),
    ('ex:R a sh:TripleRule ; sh:subject [ shnex:var "focusNode" ] ; sh:predicate "q" ; sh:object 1 .', "A triple whose predicate is a literal is skipped"),
    ('ex:R a sh:TripleRule ; sh:subject "s" ; sh:predicate ex:q ; sh:object 1 .', "A triple whose subject is a literal is skipped"),
    (TEMPLATE + 'ex:T2 a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:construct "CONSTRUCT { } WHERE { }" .\nex:R a ex:T, ex:T2 ; ex:p ex:a .', "an instance of more than one"),
    ('ex:T a sh:SPARQLRuleTemplate ; rdfs:subClassOf sh:Rule ; sh:parameter [ sh:path ex:p ] ; sh:construct "CONSTRUCT { $this ex:q $other } WHERE { }" .\nex:R a ex:T ; ex:p ex:a .', "$other, which no parameter binds"),
])
def test_a_defect_of_a_rule_is_reported_with_a_message_that_names_it(turtle, expected):
    found = messages(turtle)
    assert any(expected in m for m in found), found


@pytest.mark.parametrize("turtle", [
    'ex:R a sh:TripleRule ; sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:q ; sh:object 1 .',
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


def test_a_prefix_the_file_binds_is_not_known_to_its_queries_unless_declared():
    # the engine resolves only sh:declare / sh:prefixes (CLAUDE.md: no ambient lookup), so this check must not accept a bare @prefix
    found = problems('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:q 1 } WHERE { }" .')
    assert found and "ex" in found[0][2]
    found = problems('ex:R a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this foo:q 1 } WHERE { }" .')
    assert found and "foo" in found[0][2]
    declared = 'ex:R a sh:SPARQLRule ; sh:prefixes ex:P ; sh:construct "CONSTRUCT { $this ex:q 1 } WHERE { }" .\nex:P sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .'
    assert problems(declared) == []


def test_a_node_that_holds_prefix_declarations_is_inferred_to_be_a_prefix_set():
    from starlayer.shacl.shape_types import infer_types
    from tests.support.terms import RDF

    shapes = Graph().parse(data=PRE + 'ex:Prefixes sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .', format="turtle")
    inferred = infer_types(shapes)
    assert (NamedNode("http://example.org/Prefixes"), RDF.type, NamedNode("https://github.com/hidden-graph/starlayer/ns/shacl#PrefixSet")) in inferred
    assert (NamedNode("http://example.org/Prefixes"), RDF.type, NamedNode("https://github.com/hidden-graph/starlayer/ns/shacl#PrefixSet")) not in shapes, "inferred, not written"


def test_an_entailment_nothing_provides_is_a_warning_and_the_regimes_it_provides_are_not():
    from starlayer.graph.entailment import SUPPORTED_REGIMES

    def about_entailment(turtle):
        return [m for m in messages(turtle) if "entailment" in m]

    assert about_entailment("ex:G a sh:ShapesGraph ; sh:entailment <http://www.w3.org/ns/entailment/D> .")
    for regime in SUPPORTED_REGIMES:
        assert about_entailment(f"ex:G a sh:ShapesGraph ; sh:entailment <{regime}> .") == [], regime
    assert about_entailment("ex:G a sh:ShapesGraph ; sh:entailment sh:RulesEntailment .") == []
    assert about_entailment("ex:Set a sh:RuleSet .\nex:G a sh:ShapesGraph ; sh:entailment ex:Set .") == []


# One MetaShaclError for everything wrong with a shapes graph: the shapes-of-shapes violations and the defects of its embedded SPARQL.
XSD_PRE = "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
TWO_DEFECTS_AND_A_VIOLATION = XSD_PRE + """
ex:T a sh:NodeShape ; sh:targetClass ex:C ;
  sh:property [ sh:path ex:p ; sh:datatype xsd:string, xsd:integer ; sh:sparql [ sh:select "SELECT WHERE {{{" ] ] ;
  sh:rule [ a sh:SPARQLRule ; sh:construct "SELECT * WHERE { ?s ?p ?o }" ] .
"""


def shapes_of(turtle: str) -> Graph:
    return Graph().parse(data=PRE.split("ex:S a")[0] + turtle, format="turtle")


def test_every_sparql_defect_and_every_meta_shape_violation_is_in_one_error():
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes_of(TWO_DEFECTS_AND_A_VIOLATION))
    problems_found = raised.value.problems
    assert len(problems_found) == 3, problems_found
    assert sum("sh:datatype" in line for line in problems_found) == 1
    assert sum("sh:select value is not valid SPARQL" in line for line in problems_found) == 1
    assert sum("sh:construct must hold a CONSTRUCT query, but this is a SELECT query" in line for line in problems_found) == 1
    assert "3 problems" in str(raised.value) and all("- " + line in str(raised.value) for line in problems_found)
    assert "Results (3)" in raised.value.report_text and raised.value.report_text.count("SPARQLQueryTextShape") == 2


def test_the_sparql_problems_name_the_node_and_the_predicate_like_the_others():
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes_of(TWO_DEFECTS_AND_A_VIOLATION))
    lines = [line for line in raised.value.problems if "SPARQL" in line or "CONSTRUCT" in line]
    assert any(line.startswith("the sh:sparql of the property shape of ex:T for ex:p, sh:select: ") for line in lines), lines
    assert any(line.startswith("the sh:rule of ex:T, sh:construct: ") for line in lines), lines
    assert not any("BlankNode" in line or "_:" in line for line in raised.value.problems)


def test_a_shapes_graph_with_only_sparql_defects_is_a_meta_shacl_error():
    shapes = shapes_of('ex:C sh:select "SELECT WHERE {{{" .\nex:D sh:ask "not sparql at all" .')
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes)
    assert len(raised.value.problems) == 2
    assert sorted(line.split(": ")[0] for line in raised.value.problems) == ["ex:C, sh:select", "ex:D, sh:ask"]
    assert not isinstance(raised.value, ValueError)


@pytest.mark.parametrize("turtle, fragment", [
    ('ex:C sh:ask "SELECT * WHERE { ?s ?p ?o }" .', "sh:ask must hold a ASK query, but this is a SELECT query"),
    ('ex:R sh:construct "SELECT * WHERE { ?s ?p ?o }" .', "sh:construct must hold a CONSTRUCT query, but this is a SELECT query"),
    ('@prefix shui: <http://www.w3.org/ns/shacl-ui/> .\nex:P sh:path ex:p ; shui:searchQuery "SELECT WHERE {" .', "shui:searchQuery value is not valid SPARQL"),
])
def test_ask_construct_and_search_query_defects_are_reported_too(turtle, fragment):
    with pytest.raises(MetaShaclError) as raised:
        meta_validate(shapes_of(turtle))
    assert any(fragment in line for line in raised.value.problems), raised.value.problems


def test_a_processor_with_meta_shacl_rejects_a_sparql_only_defect_at_creation():
    from starlayer.shacl import StarShaclProcessor

    with pytest.raises(MetaShaclError, match="sh:select value is not valid SPARQL"):
        StarShaclProcessor(shacl_graph=shapes_of('ex:C sh:select "SELECT WHERE {{{" .'), meta_shacl=True)


def test_validate_with_meta_shacl_reports_the_sparql_defects_with_the_other_problems():
    from starlayer.shacl import validate

    with pytest.raises(MetaShaclError) as raised:
        validate(Graph(), shacl_graph=shapes_of(TWO_DEFECTS_AND_A_VIOLATION), meta_shacl=True)
    assert len(raised.value.problems) == 3


def test_sound_shapes_with_sound_queries_pass():
    shapes = shapes_of('ex:C sh:select "SELECT $this WHERE { $this ?p ?o }" .\nex:R a sh:SPARQLRule ; sh:prefixes ex:P ; sh:construct "CONSTRUCT { $this ex:q 1 } WHERE { }" .\n'
                       'ex:P sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/" ] .')
    conforms, _report, _text = meta_validate(shapes)
    assert conforms


# --- the defects of the embedded SPARQL are results of the report graph ---------------------------------------------------------

PRE_S = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .\nex:S a sh:NodeShape ; sh:targetClass ex:Person .\n"
SH_NS = "http://www.w3.org/ns/shacl#"
QUERY_SHAPE = "https://github.com/hidden-graph/starlayer/ns/shacl#SPARQLQueryTextShape"
BAD_SELECT = 'ex:S sh:select "SELECT ?this WHERE { ?this ?" .'
TWO_DATATYPES = 'ex:S sh:property [ sh:path ex:a ; sh:datatype "x" ], [ sh:path ex:b ; sh:datatype "y" ] .'


def _failure(turtle: str) -> MetaShaclError:
    shapes = Graph().parse(data=PRE_S + turtle, format="turtle")
    with pytest.raises(MetaShaclError) as caught:
        meta_validate(shapes)
    return caught.value


def _results(report) -> list[dict]:
    sh = lambda name: NamedNode(SH_NS + name)  # noqa: E731
    out = []
    for result in report.subjects(NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), sh("ValidationResult")):
        out.append({key: next(iter(report.objects(result, sh(name))), None) for key, name in (
            ("focus", "focusNode"), ("path", "resultPath"), ("message", "resultMessage"),
            ("severity", "resultSeverity"), ("shape", "sourceShape"))})
    return out


@pytest.mark.parametrize("turtle, predicate", [
    ('ex:S sh:select "SELECT ?this WHERE { ?this ?" .', "http://www.w3.org/ns/shacl#select"),
    ('ex:S sh:ask "ASK { ?this ?" .', "http://www.w3.org/ns/shacl#ask"),
    ('ex:S sh:construct "CONSTRUCT { ?this ?" .', "http://www.w3.org/ns/shacl#construct"),
    ('ex:S <http://www.w3.org/ns/shacl-ui/searchQuery> "SELECT ?this WHERE { ?this ?" .', "http://www.w3.org/ns/shacl-ui/searchQuery"),
])
def test_a_sparql_defect_is_a_result_of_the_report_graph(turtle, predicate):
    error = _failure(turtle)
    found = [r for r in _results(error.report_graph) if r["shape"] == NamedNode(QUERY_SHAPE)]
    assert len(found) == 1, error.problems
    (one,) = found
    assert one["focus"] == NamedNode("http://example.org/S")
    assert one["path"] == NamedNode(predicate)
    assert one["severity"] == NamedNode(SH_NS + "Violation")
    assert text(one["message"]) in error.problems[0]
    assert text(one["message"]) in error.report_text
    reports = list(error.report_graph.subjects(NamedNode(SH_NS + "conforms"), None))
    assert len(reports) == 1
    assert [text(o) for o in error.report_graph.objects(reports[0], NamedNode(SH_NS + "conforms"))] == ["false"]


def test_a_mixed_graph_has_both_kinds_of_result_and_both_kinds_of_line():
    error = _failure(BAD_SELECT + "\n" + TWO_DATATYPES)
    results = _results(error.report_graph)
    assert sum(r["shape"] == NamedNode(QUERY_SHAPE) for r in results) == 1
    assert sum(r["path"] == NamedNode(SH_NS + "datatype") for r in results) == 2
    assert len(error.problems) == 3
    assert sum("sh:datatype" in line for line in error.problems) == 2
    assert sum(line.startswith("ex:S, sh:select:") for line in error.problems) == 1


def test_the_error_carries_the_report_graph_the_engine_built():
    from starlayer.shacl.engine.meta import meta_validate as engine_meta_validate

    shapes = Graph().parse(data=PRE_S + BAD_SELECT, format="turtle")
    outcome = engine_meta_validate(shapes)
    with pytest.raises(MetaShaclError) as caught:
        outcome.raise_if_invalid()
    assert caught.value.report_graph is outcome.report_graph
    assert len(_results(outcome.report_graph)) == 1


def test_a_sound_graph_returns_a_report_without_results():
    shapes = Graph().parse(data=PRE_S + 'ex:S sh:select "SELECT ?this WHERE { ?this a ?c }" .', format="turtle")
    conforms, report, _text = meta_validate(shapes)
    assert conforms is True
    assert _results(report) == []
