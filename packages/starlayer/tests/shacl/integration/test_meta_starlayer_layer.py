"""The two meta checks that call StarLayer-internal SPARQL functions (an invalid ``sh:pattern`` / ``sh:flags``, the text of an embedded query) are shapes of the
private layer ``shacl_shacl_starlayer``, kept out of ``shacl_shacl`` so that stays standard SHACL and SPARQL."""

import pyoxigraph as ox
import pytest
from starlayer import starontology
from starlayer.errors import ShapeError
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import ExecutionError, MetaShaclError, StarShaclProcessor
from starlayer.shacl.engine.api import validate as engine_validate
from starlayer.shacl.engine.builtin_functions import (
    ARGUMENT_COUNT_PROBLEM,
    BUILTIN_FUNCTIONS,
    REGEX_PROBLEM,
    SPARQL_PROBLEM,
    TIME_ZONE_PROBLEM,
)
from starlayer.shacl.meta_shapes import meta_validate, sparql_query_problems

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
        return meta_validate(shapes, meta_shapes_extra=extra)[1]
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
    assert set(BUILTIN_FUNCTIONS) == {REGEX_PROBLEM, SPARQL_PROBLEM, TIME_ZONE_PROBLEM, ARGUMENT_COUNT_PROBLEM}
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


# --- what the engine refuses in the queries it runs, and the number of arguments of an expression ----------------------------------
# The engine refuses these when it runs the query (SPARQL Extensions, "Pre-binding of Variables"), so a shapes graph that only fails then passes every other
# check. The private layer asks the engine's own check (sparql_support.restriction_problem), once it knows where the query is used.

DATA = "ex:a a ex:C ; ex:p 1 ."
HEAD = PRE + "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix sparql: <http://www.w3.org/ns/sparql#> .\n"


def engine_text(body: str) -> str | None:
    """What the engine raises (a ShapeError, or an ExecutionError for a rule) for the shapes graph, or None when it accepts it."""
    shapes = Graph().parse(data=HEAD + body, format="turtle")
    try:
        StarShaclProcessor(shacl_graph=shapes).validate(data_graph=graph(DATA), rules=True)
    except (ShapeError, ExecutionError) as error:
        return str(error)
    return None


def meta_lines(body: str) -> list[str]:
    try:
        meta_validate(Graph().parse(data=HEAD + body, format="turtle"))
    except MetaShaclError as error:
        return list(error.problems)
    return []


def constraint(query: str) -> str:
    return f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:select """{query}""" ] .'


def validator(kind: str, query: str) -> str:
    return (f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; ex:flag 1 . ex:Comp a sh:ConstraintComponent ; sh:parameter [ sh:path ex:flag ] ; sh:validator [ sh:{kind} """{query}""" ] .')


def rule(construct: str, *, shape: bool = True) -> str:
    holder = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:R ." if shape else ""
    return f'{holder} ex:R a sh:SPARQLRule ; sh:construct """{construct}""" .'


def expression(query: str) -> str:
    return f'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ sh:select """{query}""" ] .'


# (what the query does wrong, where it is used, the text the engine gives); the first column names the case
RESTRICTED = [
    ("service in a constraint", constraint("SELECT $this WHERE { SERVICE <http://127.0.0.1:1/sparql> { ?s ?p ?o } }"), "SERVICE is not allowed"),
    ("minus in a constraint", constraint("SELECT $this WHERE { $this ex:p ?o MINUS { ?o ex:q ?r } }"), "MINUS is not allowed"),
    ("this assigned in a constraint", constraint("SELECT $this WHERE { BIND (ex:a AS $this) }"), "must not assign the pre-bound variable ?this"),
    ("this given by a select expression", constraint("SELECT (ex:a AS $this) WHERE { }"), "must not assign the pre-bound variable ?this"),
    ("values of this in a constraint", constraint("SELECT $this WHERE { VALUES $this { ex:a } }"), "VALUES must not mention the pre-bound variable ?this"),
    ("a select that does not project this", constraint("SELECT ?x WHERE { ?x ?p ?o }"), "must project ?this"),
    ("service in the ask of a validator", validator("ask", "ASK { SERVICE <http://127.0.0.1:1/sparql> { ?s ?p ?o } }"), "SERVICE is not allowed"),
    ("value assigned in the ask of a validator", validator("ask", "ASK { BIND (true AS $value) FILTER ($value) }"), "must not assign the pre-bound variable ?value"),
    ("values of value in the ask of a validator", validator("ask", "ASK { VALUES $value { 1 } }"), "VALUES must not mention the pre-bound variable ?value"),
    ("a select validator that does not project this", validator("select", "SELECT ?x WHERE { ?x ?p ?o }"), "must project ?this"),
    ("minus in a rule of a shape", rule("CONSTRUCT { ?x ex:q ?y } WHERE { ?x ex:p ?y MINUS { ?y ex:r ?z } }"), "MINUS is not allowed"),
    ("this assigned in a rule of a shape", rule("CONSTRUCT { $this ex:q ?y } WHERE { BIND (1 AS $this) BIND (2 AS ?y) }"), "must not assign the pre-bound variable ?this"),
    ("service in a rule no shape holds", rule("CONSTRUCT { ?x ex:q ?y } WHERE { ?x ex:p ?y . SERVICE <http://127.0.0.1:1/sparql> { ?x ?p ?y } }", shape=False), "SERVICE is not allowed"),
    ("minus in a node expression", expression("SELECT ?x WHERE { ?x ex:p ?o MINUS { ?o ex:q ?r } }"), "MINUS is not allowed"),
    ("service in a node expression", expression("SELECT ?x WHERE { SERVICE <http://127.0.0.1:1/sparql> { ?x ?p ?o } }"), "SERVICE is not allowed"),
]

ALLOWED = [
    ("a values over other variables", constraint("SELECT $this WHERE { VALUES ?other { 1 2 } $this ex:p ?other }")),
    ("value assigned in a select constraint (it is not pre-bound there)", constraint("SELECT $this ?value WHERE { BIND (1 AS ?value) }")),
    ("select star", constraint("SELECT * WHERE { $this ex:p ?o }")),
    ("another variable assigned in an ask", validator("ask", "ASK { BIND (true AS ?other) FILTER (?other) }")),
    ("minus in a rule no shape holds (nothing is pre-bound)", rule("CONSTRUCT { ?x ex:q ?y } WHERE { ?x ex:p ?y MINUS { ?y ex:r ?z } }", shape=False)),
    ("this assigned in a rule no shape holds", rule("CONSTRUCT { ?x ex:q ?y } WHERE { BIND (ex:a AS ?x) BIND (1 AS ?y) }", shape=False)),
    ("a deactivated constraint", 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:sparql [ sh:deactivated true ; sh:select "SELECT ?x WHERE { MINUS { ?x ?p ?o } }" ] .'),
    ("a rule of a deactivated shape", "ex:S a sh:NodeShape ; sh:deactivated true ; sh:targetNode ex:a ; sh:rule ex:R . ex:R a sh:SPARQLRule ; sh:construct \"CONSTRUCT { ?x ex:q ?y } WHERE { ?x ex:p ?y MINUS { ?y ex:r ?z } }\" ."),
    ("a query nothing uses", 'ex:Q sh:select "SELECT ?x WHERE { MINUS { ?x ?p ?o } }" .'),
]


@pytest.mark.parametrize("name, body, said", RESTRICTED, ids=[case[0] for case in RESTRICTED])
def test_a_query_the_engine_refuses_to_run_is_found(name, body, said):
    body = EX_PREFIX + 'ex:S2 sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .\n' + body
    body = body.replace("sh:select", "sh:prefixes ex:P ; sh:select", 1) if "sh:prefixes" not in body else body
    body = body.replace("sh:ask", "sh:prefixes ex:P ; sh:ask", 1) if " sh:ask" in body else body
    body = body.replace("sh:construct", "sh:prefixes ex:P ; sh:construct", 1) if " sh:construct" in body else body
    refused = engine_text(body)
    assert refused is not None and said in refused
    lines = meta_lines(body)
    assert [line for line in lines if said in line], lines
    tool = [problem for _node, _predicate, problem in sparql_query_problems(Graph().parse(data=HEAD + body, format="turtle"))]
    assert [problem for problem in tool if said in problem], tool


@pytest.mark.parametrize("name, body", ALLOWED, ids=[case[0] for case in ALLOWED])
def test_a_query_the_engine_runs_is_not_found(name, body):
    body = EX_PREFIX + body
    body = body.replace("sh:select", "sh:prefixes ex:P ; sh:select", 1) if "sh:prefixes" not in body else body
    body = body.replace("sh:ask", "sh:prefixes ex:P ; sh:ask", 1) if " sh:ask" in body else body
    body = body.replace("sh:construct", "sh:prefixes ex:P ; sh:construct", 1) if " sh:construct" in body else body
    assert engine_text(body) is None
    assert meta_lines(body) == []


def test_the_restrictions_are_the_engines_own_check():
    from starlayer.shacl.engine import sparql_support

    assert sparql_support.restriction_problem("SELECT $this WHERE { VALUES $this { 1 } }", ["this"]) == "VALUES must not mention the pre-bound variable ?this in a SHACL SPARQL query"
    assert sparql_support.restriction_problem("SELECT ?x WHERE { }", ["this"], require_this=True) == "a SHACL SPARQL SELECT query must project ?this"
    assert sparql_support.restriction_problem("SELECT ?x WHERE { MINUS { ?x ?p ?o } }", [], pre_binding=False) is None
    assert sparql_support.restriction_problem("SELECT ?x WHERE {", ["this"]) is None  # a query that does not parse is for the other check


ARITY_SHELL = 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:expression [ %s ] .'


@pytest.mark.parametrize(
    "bad, good",
    [
        ("sparql:if ( true 1 )", "sparql:if ( true 1 2 )"),
        ("sparql:if ( true 1 2 3 )", "sparql:if ( true 1 2 )"),
        ("sparql:bound ( 1 2 )", "sparql:bound ( 1 )"),
        ("sparql:bound ( )", "sparql:bound ( 1 )"),
        ("sparql:hasLang ( 1 2 3 )", "sparql:hasLang ( 1 2 )"),
        ("sparql:equals ( 1 2 3 )", "sparql:equals ( 1 2 )"),
        ("sparql:equals 1", "sparql:equals ( 1 2 )"),
        ("sparql:logical-not ( 1 2 )", "sparql:logical-not ( true )"),
        ("sparql:unary-minus ( 1 2 )", "sparql:unary-minus ( 1 )"),
        ("shnex:conformsToShape ( 1 )", "shnex:conformsToShape ( 1 ex:T )"),
    ],
)
def test_a_call_with_the_wrong_number_of_arguments_is_found(bad, good):
    shell = ARITY_SHELL + " ex:T a sh:NodeShape ."
    refused = engine_text(shell % bad)
    assert refused is not None and "needs a list of" in refused
    assert [line for line in meta_lines(shell % bad) if "needs a list of" in line]
    assert engine_text(shell % good) is None or "needs a list of" not in engine_text(shell % good)
    assert meta_lines(shell % good) == []


def test_a_call_with_no_fixed_count_takes_any_number_of_arguments():
    for call in ("sparql:coalesce ( 1 2 3 4 )", "sparql:logical-and ( true true true )", "sparql:concat ( 'a' 'b' 'c' )"):
        assert meta_lines(ARITY_SHELL % call) == []


def test_the_targets_of_the_argument_count_shape_are_the_operators_with_a_count():
    from starlayer.shacl.engine.expressions import ARITY

    layer = starontology._load_private("shacl_shacl_starlayer")
    targets = {term.value for term in layer.objects(ox.NamedNode(STSH + "ArgumentCountShape"), ox.NamedNode(SH + "targetSubjectsOf"))}
    assert targets == {pred.value for pred in ARITY}


def test_the_argument_count_function_agrees_with_the_engine_table():
    from starlayer.shacl.engine.expressions import ARITY

    function = BUILTIN_FUNCTIONS[ARGUMENT_COUNT_PROBLEM]
    for pred, counts in ARITY.items():
        assert all(function(pred, ox.Literal(str(n), datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))) is None for n in counts)
        wrong = max(counts) + 1
        assert "needs a list of" in function(pred, ox.Literal(str(wrong), datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))).value
    assert function(ox.NamedNode("http://www.w3.org/ns/sparql#coalesce"), ox.Literal("9", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))) is None
    assert function(ox.NamedNode("http://www.w3.org/ns/sparql#if"), ox.Literal("x")) is None
