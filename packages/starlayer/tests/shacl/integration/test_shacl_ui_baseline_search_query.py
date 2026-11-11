"""SHACL UI, AutoCompleteEditor's score rules: "the presence of shui:searchQuery raises the AutoCompleteEditor's score". The generic
catalog (``shacl_ui_baseline``) scores AutoCompleteEditor 4 for a property shape that has ``shui:searchQuery``, above the constraint
defaults (3)."""

from starlayer import starontology
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.shacl.ui_widget_selection import SHUI, select_widget
from starlayer.shacl_engine.terms import NS

EX = NS("http://example.org/")
PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shui: <http://www.w3.org/ns/shacl-ui/> .\n"
)


def _shapes(extra: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=PREFIXES + f"ex:P sh:path ex:assignee ; sh:class ex:Person {extra} .", format="turtle")
    return g


def _pick(extra: str):
    return select_widget(
        shape_node=EX.P, shapes_graph=_shapes(extra), scoring_graph=starontology.get_ontology_graph("shacl_ui_baseline"), role="editor"
    )


def test_a_class_without_a_search_query_gets_the_instances_select():
    assert _pick("") == SHUI.InstancesSelectEditor


def test_a_search_query_makes_it_an_auto_complete():
    assert _pick('; shui:searchQuery "SELECT ?value WHERE { ?value a <http://example.org/Person> }"') == SHUI.AutoCompleteEditor


# ---- the well-formedness of the value (SHACL UI, Search Query): a SELECT on a property shape, with $searchTerm and $language free

def _problems(query: str):
    from starlayer.shacl.meta_shapes import sparql_query_problems

    g = StarLayerGraph()
    g.parse(data=PREFIXES + f'ex:P a sh:PropertyShape ; sh:path ex:p ; shui:searchQuery """{query}""" .', format="turtle")
    return [message for _node, _predicate, message in sparql_query_problems(g)]


def test_a_search_query_may_use_the_placeholders():
    query = "SELECT DISTINCT ?value WHERE { ?value a <http://example.org/Person> ; <http://www.w3.org/2000/01/rdf-schema#label> ?l . " \
            "FILTER(CONTAINS(LCASE(?l), LCASE($searchTerm))) FILTER(LANGMATCHES(LANG(?l), $language)) }"
    assert _problems(query) == []


def test_a_search_query_that_is_not_a_select_is_a_problem():
    assert any("must hold a SELECT query" in m for m in _problems("ASK { ?s ?p ?o }"))


def test_a_search_query_that_is_not_sparql_is_a_problem():
    assert any("not valid SPARQL" in m for m in _problems("SELECT WHERE {"))


def test_other_unbound_variables_in_a_search_query_are_still_reported():
    assert any("fails SPARQL structural validation" in m for m in _problems("SELECT ?value WHERE { ?value a ?c FILTER(?value != $other) }"))


# ---- stsh:SearchQueryShape and stsh:SuggestedValuesShape (in shacl_shacl_ui) check the shape of the values

def _violations(shapes_ttl: str) -> set[str]:
    from starlayer.shacl import validate

    data = StarLayerGraph()
    data.parse(data=PREFIXES + "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + shapes_ttl, format="turtle")
    result = validate(data, starontology.get_ontology_graph("shacl_shacl_ui"), meta_shacl=False)
    comments = {str(m) for m in result.report_graph.objects(None, NS("http://www.w3.org/ns/shacl#").resultMessage)}
    return comments | {str(p) for p in result.report_graph.objects(None, NS("http://www.w3.org/ns/shacl#").resultPath)}


def test_a_well_formed_search_query_and_suggested_values_are_accepted():
    ttl = 'ex:P a sh:PropertyShape ; sh:path ex:p ; shui:searchQuery "SELECT ?v WHERE { ?v ?p ?o }" ; shui:suggestedValues ( "a" ex:b ) .'
    assert _violations(ttl) == set()


def test_a_search_query_on_a_node_shape_is_a_violation():
    assert _violations('ex:N a sh:NodeShape ; shui:searchQuery "SELECT ?v WHERE { ?v ?p ?o }" .')


def test_a_search_query_that_is_not_a_string_is_a_violation():
    assert _violations("ex:P a sh:PropertyShape ; sh:path ex:p ; shui:searchQuery 1 .")


def test_two_search_queries_are_a_violation():
    assert _violations('ex:P a sh:PropertyShape ; sh:path ex:p ; shui:searchQuery "SELECT ?a WHERE { ?a ?b ?c }", "SELECT ?b WHERE { ?a ?b ?c }" .')


def test_a_suggested_value_that_is_a_blank_node_is_a_violation():
    assert _violations("ex:P a sh:PropertyShape ; sh:path ex:p ; shui:suggestedValues ( [] ) .")
