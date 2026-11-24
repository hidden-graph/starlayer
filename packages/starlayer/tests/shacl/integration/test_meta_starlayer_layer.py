"""The two meta checks that call StarLayer-internal SPARQL functions (an invalid ``sh:pattern`` / ``sh:flags``, the text of an embedded query) are shapes of the
private layer ``shacl_shacl_starlayer``, kept out of ``shacl_shacl`` so that stays standard SHACL and SPARQL."""

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaShaclError, StarShaclProcessor
from starlayer.shacl.engine.api import validate as engine_validate
from starlayer.shacl.engine.builtin_functions import (
    BUILTIN_FUNCTIONS,
    REGEX_PROBLEM,
    SPARQL_PROBLEM,
    TIME_ZONE_PROBLEM,
)
from starlayer.shacl.engine.plan import ShapeError
from starlayer.shacl.meta_shapes import meta_validate

SH = "http://www.w3.org/ns/shacl#"
STSH = "https://github.com/hidden-graph/starlayer/ns/shacl#"
REGEX_SHAPE, QUERY_SHAPE = ox.NamedNode(STSH + "RegexShape"), ox.NamedNode(STSH + "SPARQLQueryTextShape")
PRE = ("@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
       "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n")
EX_PREFIX = 'ex:P sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .\n'


def graph(body: str) -> Graph:
    return Graph().parse(data=PRE + body, format="turtle")


def sources(report) -> set:
    return set(report.objects(None, ox.NamedNode(SH + "sourceShape")))


def meta_report(shapes: Graph, extra=()):
    try:
        return meta_validate(shapes, extra_graphs=extra)[1]
    except MetaShaclError as error:
        return error.report_graph


def deactivation(*shapes: ox.NamedNode) -> Graph:
    extra = Graph()
    extra.extend([(shape, ox.NamedNode(SH + "deactivated"), ox.Literal("true", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean"))) for shape in shapes])
    return extra


BAD_PATTERN = 'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern "(" ] .'
BAD_QUERY = 'ex:S a sh:NodeShape ; sh:sparql [ sh:select "SELECT $this WHERE { $this ?p" ] .'


def test_the_layer_is_private_and_apart_from_shacl_shacl():
    assert "shacl_shacl_starlayer" not in {info.name for info in starontology.get_ontology_list()}
    assert starontology.get_resource_iri("shacl_shacl_starlayer") is None and starontology.get_raw_url("shacl_shacl_starlayer") is None
    with pytest.raises(KeyError) as unknown:
        starontology.get_ontology_graph("shacl_shacl_starlayer")
    with pytest.raises(KeyError) as other:
        starontology.get_ontology_graph("no_such_graph")
    assert str(unknown.value).replace("shacl_shacl_starlayer", "X") == str(other.value).replace("no_such_graph", "X")
    assert "shacl_shacl_starlayer" not in getattr(starontology, "__all__", ())
    base = starontology.get_ontology_graph("shacl_shacl")
    layer = starontology._load_private("shacl_shacl_starlayer")
    assert len(list(layer.triples((REGEX_SHAPE, None, None)))) > 0 and len(list(layer.triples((QUERY_SHAPE, None, None)))) > 0
    assert not list(base.triples((REGEX_SHAPE, None, None))) and not list(base.triples((QUERY_SHAPE, None, None)))


def test_meta_validate_still_reports_a_bad_pattern_and_a_bad_query_with_the_layer_private():
    assert REGEX_SHAPE in sources(meta_report(graph(BAD_PATTERN)))
    assert QUERY_SHAPE in sources(meta_report(graph(BAD_QUERY)))


def test_shacl_shacl_alone_has_no_function_call_and_misses_only_these_two_checks():
    base = starontology.get_ontology_graph("shacl_shacl")
    assert not [o for o in base.objects(None, None) if isinstance(o, ox.Literal) and ("regexProblem" in o.value or "sparqlProblem" in o.value)]
    for body in (BAD_PATTERN, BAD_QUERY):
        outcome = engine_validate(graph(body), base, rules=False, meta_shacl=False, ignore_imports=True)
        assert not sources(outcome.report_graph) & {REGEX_SHAPE, QUERY_SHAPE}


def test_shacl_shacl_with_the_layer_reports_both():
    base = starontology.get_ontology_graph("shacl_shacl")
    base.extend(list(starontology._load_private("shacl_shacl_starlayer").triples((None, None, None))))
    assert REGEX_SHAPE in sources(engine_validate(graph(BAD_PATTERN), base, rules=False, meta_shacl=False, ignore_imports=True).report_graph)
    assert QUERY_SHAPE in sources(engine_validate(graph(BAD_QUERY), base, rules=False, meta_shacl=False, ignore_imports=True).report_graph)


@pytest.mark.parametrize("body, shape", [(BAD_PATTERN, REGEX_SHAPE), (BAD_QUERY, QUERY_SHAPE)])
def test_deactivating_the_shape_gives_no_result_so_the_shape_does_the_work(body, shape):
    assert shape in sources(meta_report(graph(body)))
    assert shape not in sources(meta_report(graph(body), extra=[deactivation(shape)]))


def test_the_layer_does_not_change_what_meta_validate_says_of_a_sound_graph():
    conforms, _report, _text = meta_validate(graph(EX_PREFIX + 'ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern "^a+$" ; sh:flags "i" ] ; '
                                                   'sh:sparql [ sh:prefixes ex:P ; sh:select "SELECT $this WHERE { $this a ex:Q }" ] .'))
    assert conforms


def test_the_layer_passes_its_own_check():
    layer = Graph()
    layer.extend(list(starontology._load_private("shacl_shacl_starlayer").triples((None, None, None))))
    assert meta_validate(layer)[0]


# --- the functions -------------------------------------------------------------------------------------------------------------

def test_the_functions_are_registered():
    assert set(BUILTIN_FUNCTIONS) == {REGEX_PROBLEM, SPARQL_PROBLEM, TIME_ZONE_PROBLEM}
    assert REGEX_PROBLEM.value == STSH + "regexProblem" and SPARQL_PROBLEM.value == STSH + "sparqlProblem"


def test_a_constraint_in_a_users_own_shapes_graph_can_call_them():
    shapes = graph('''ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:sparql [ sh:prefixes ex:P ; sh:message "{?problem}" ; sh:select """
        SELECT $this ?problem WHERE { $this ex:re ?re . BIND(<https://github.com/hidden-graph/starlayer/ns/shacl#regexProblem>(?re) AS ?problem) FILTER(BOUND(?problem)) }""" ] .
        ''' + EX_PREFIX)
    data = graph('ex:a a ex:C ; ex:re "(" . ex:b a ex:C ; ex:re "a+" .')
    result = StarShaclProcessor(shacl_graph=shapes).validate(data_graph=data)
    assert not result.conforms
    focus = set(result.report_graph.objects(None, ox.NamedNode(SH + "focusNode")))
    assert focus == {ox.NamedNode("http://example.org/a")}


@pytest.mark.parametrize("pattern, flags, bad", [("(", None, True), ("(", "q", False), ("a+", "i", False), ("", "z", True), ("a", "z", False), ("(", "z", True)])  # bad flags are reported once, on sh:flags: the pattern is then tried without them
def test_regex_problem_function(pattern, flags, bad):
    args = [ox.Literal(pattern)] + ([ox.Literal(flags)] if flags is not None else [])
    assert (BUILTIN_FUNCTIONS[REGEX_PROBLEM](*args) is not None) == bad


def test_a_function_with_a_non_string_argument_gives_no_value():
    assert BUILTIN_FUNCTIONS[REGEX_PROBLEM](ox.NamedNode("http://example.org/x")) is None
    assert BUILTIN_FUNCTIONS[SPARQL_PROBLEM](ox.Literal("SELECT * WHERE {}"), ox.NamedNode("http://example.org/notAQueryPredicate")) is None


# --- the embedded SPARQL: prefixes, form ---------------------------------------------------------------------------------------

def query_problems(body: str) -> list[str]:
    try:
        meta_validate(graph(body))
    except MetaShaclError as error:
        return [line for line in error.problems if "sh:select" in line or "sh:ask" in line or "sh:construct" in line]
    return []


def test_a_prefix_declared_with_sh_declare_via_sh_prefixes_passes():
    assert query_problems(EX_PREFIX + 'ex:S sh:sparql [ sh:prefixes ex:P ; sh:select "SELECT $this WHERE { $this a ex:Q }" ] .') == []


def test_an_undeclared_prefix_is_a_problem_even_when_the_file_binds_it():
    (line,) = query_problems('ex:S sh:sparql [ sh:select "SELECT $this WHERE { $this a ex:Q }" ] .')
    assert "sh:select value is not valid SPARQL" in line and "undeclared prefix 'ex'" in line


def test_a_prefix_declared_in_an_imported_holder_passes():
    body = ('ex:P owl:imports ex:Q . ex:Q sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .\n'
            'ex:S sh:sparql [ sh:prefixes ex:P ; sh:select "SELECT $this WHERE { $this a ex:Q }" ] .')
    assert query_problems(body) == []


def test_a_prefix_the_holder_does_not_declare_is_a_problem():
    body = EX_PREFIX + 'ex:S sh:sparql [ sh:prefixes ex:P ; sh:select "SELECT $this WHERE { $this a other:Q }" ] .'
    (line,) = query_problems(body)
    assert "undeclared prefix 'other'" in line


def test_a_select_that_holds_an_ask_is_a_problem():
    lines = [line for line in query_problems('ex:S sh:sparql [ sh:select "ASK { ?s ?p ?o }" ] .') if "this is a ASK query" in line]
    assert len(lines) == 1 and lines[0].endswith("sh:select must hold a SELECT query, but this is a ASK query")


def test_the_parameters_of_a_validator_are_not_unbound():
    body = ('ex:C a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minimum ] ; sh:validator [ sh:select "SELECT $this ?value WHERE { $this ?p ?value . FILTER(?value < $minimum) }" ] .')
    assert query_problems(body) == []
    assert query_problems(body.replace("ex:minimum", "ex:other"))


def test_rdf_rdfs_and_owl_are_not_known_without_a_declaration_and_the_engine_agrees():
    """The engine binds no prefix it was not given, so the check must not either: otherwise a query that passes the meta-shapes fails when run."""
    for prefix in ("rdf:type", "rdfs:label", "owl:Thing"):
        body = f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select "SELECT $this WHERE {{ $this {prefix} ?o }}" ] .'
        (line,) = query_problems(body)
        assert f"undeclared prefix '{prefix.split(':')[0]}'" in line
        with pytest.raises(ShapeError, match="undeclared prefix"):
            StarShaclProcessor(shacl_graph=graph(body)).validate(data_graph=graph("ex:a a ex:C ."))


def test_rdf_type_with_a_declaration_passes_the_check_and_runs():
    body = ('ex:P sh:declare [ sh:prefix "rdf" ; sh:namespace "http://www.w3.org/1999/02/22-rdf-syntax-ns#"^^xsd:anyURI ] .\n'
            'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:prefixes ex:P ; sh:select "SELECT $this WHERE { $this rdf:type ?o FILTER(false) }" ] .')
    assert query_problems(body) == []
    assert StarShaclProcessor(shacl_graph=graph(body)).validate(data_graph=graph("ex:a a ex:C .")).conforms
