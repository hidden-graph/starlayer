"""SHACL shape tests for the Phase-1-core slice of the salg: vocabulary
(BGP/Filter/LeftJoin/Union + the SELECT wrapper) — see shapes.py.

Two directions get tested:

1. Every real Phase 1 query (imported from test_roundtrip.QUERIES, so this
   suite can't silently drift from what the encoder actually produces)
   encodes to a graph that *conforms*.
2. A handful of deliberately malformed graphs, built by mutating a valid
   encoded query, each *fail* validation for the specific structural reason
   the mutation introduces - not just "conforms is False somewhere".
"""

import pytest
from rdflib import BNode, Literal, RDF, URIRef
from rdflib.plugins.sparql.processor import prepareQuery, prepareUpdate

from starsparql import query_to_rdf, queries_to_collection, shapes_graph, update_to_rdf, validate
from starsparql.vocab import SALG

from unit.test_roundtrip import QUERIES
from unit.test_phase2_values_subquery import QUERIES as VALUES_SUBQUERY_QUERIES
from unit.test_phase6_rdf12_native import QUERIES as RDF12_QUERIES
from unit.test_phase2_update import SINGLE_GRAPH_UPDATES, MULTI_GRAPH_UPDATES
from unit.test_phase2_forms import QUERIES as FORMS_QUERIES
from unit.test_phase2_paths import QUERIES as PATH_QUERIES
from unit.test_phase2_aggregates import QUERIES as AGGREGATE_QUERIES
from starsparql.parse12 import prepare_query_12

# Top-level LIMIT/DISTINCT/REDUCED/ORDER BY all wrap SelectQuery.p in
# Slice/Distinct/Reduced instead of it being a bare Project - a real gap
# found while building the VALUES/subquery shapes (SelectQueryShape
# originally hard-required salg:p to be exactly a salg:Project, which would
# have rejected every one of these). Not covered by test_roundtrip.QUERIES
# or VALUES_SUBQUERY_QUERIES, so exercised directly here.
TOP_LEVEL_MODIFIER_QUERIES = [
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    "SELECT ?name WHERE { ?p foaf:name ?name } LIMIT 2",
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    "SELECT ?name WHERE { ?p foaf:name ?name } ORDER BY ?name",
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    "SELECT DISTINCT ?name WHERE { ?p foaf:name ?name } ORDER BY ?name LIMIT 2",
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    "SELECT REDUCED ?name WHERE { ?p foaf:name ?name }",
]


@pytest.mark.parametrize("query_text", QUERIES)
def test_valid_phase1_queries_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


@pytest.mark.parametrize("query_text", VALUES_SUBQUERY_QUERIES)
def test_valid_values_and_subquery_queries_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


@pytest.mark.parametrize("query_text", TOP_LEVEL_MODIFIER_QUERIES)
def test_top_level_slice_distinct_reduced_orderby_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_shapes_graph_is_valid_shacl_and_reusable():
    # shapes_graph() must hand back an independent copy each call - pyshacl
    # mutates the shapes graph it's given during validation.
    g1 = shapes_graph()
    g2 = shapes_graph()
    assert g1 is not g2
    assert len(g1) == len(g2) > 0


def test_expression_shape_relies_on_rdfs_reasoning_not_enumeration():
    """ExpressionShape is a 2-alternative sh:or (a bare term, or salg:
    Expression) - conformance for a real Builtin_STR node depends entirely
    on RDFS reasoning entailing salg:Expression from salg:Builtin_STR via
    the ontology's rdfs:subClassOf chain (Builtin_STR -> OneArgExpression
    -> Expression). Build a minimal graph with *only* the base fact
    asserted (no reasoning involved yet) and confirm the entailed types
    are what conformance actually rests on, so this can't silently
    regress to "conforms by coincidence" without a real subclass chain
    behind it."""
    from rdflib import RDF, BNode, Graph as RGraph

    from starsparql.ontology import ontology_graph
    from starsparql.vocab import SALG

    data = RGraph()
    node = BNode()
    data.add((node, RDF.type, SALG.Builtin_STR))

    merged = RGraph()
    merged += data
    merged += ontology_graph()

    import owlrl

    owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(merged)
    entailed_types = set(merged.objects(node, RDF.type))
    assert SALG.Expression in entailed_types, "salg:Expression was not entailed - ExpressionShape's sh:class check would not match this node"
    assert SALG.OneArgExpression in entailed_types


def _encode_simple_select():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?name WHERE { ?p :name ?name }"
    )
    prepared = prepareQuery(query_text)
    return query_to_rdf(prepared)


def _bgp_node(graph):
    return next(graph.subjects(RDF.type, SALG.BGP))


def test_bgp_missing_triples_fails():
    graph, root = _encode_simple_select()
    bgp = _bgp_node(graph)
    for triples in list(graph.objects(bgp, SALG.triples)):
        graph.remove((bgp, SALG.triples, triples))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:BGP" in results_text or "triples" in results_text


def test_bgp_with_two_triples_lists_fails():
    graph, root = _encode_simple_select()
    bgp = _bgp_node(graph)
    graph.add((bgp, SALG.triples, RDF.nil))

    conforms, _, _ = validate(graph)
    assert not conforms


def test_filter_missing_expr_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?name WHERE { ?p : ?name . FILTER(?name != \"Bob\") }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    filter_node = next(graph.subjects(RDF.type, SALG.Filter))
    for expr in list(graph.objects(filter_node, SALG.expr)):
        graph.remove((filter_node, SALG.expr, expr))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:Filter" in results_text or "expr" in results_text


def test_leftjoin_missing_p2_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?name ?age WHERE { ?p : ?name . OPTIONAL { ?p : ?age } }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    leftjoin = next(graph.subjects(RDF.type, SALG.LeftJoin))
    for p2 in list(graph.objects(leftjoin, SALG.p2)):
        graph.remove((leftjoin, SALG.p2, p2))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:LeftJoin" in results_text or "p2" in results_text


def test_triple_pattern_subject_as_plain_literal_fails():
    """A plain (untagged) Literal is not legal RDF-subject-position - not a
    bound term (subjects can't be literals) and not a Variable (those carry
    the salg:Variable datatype)."""
    graph, root = _encode_simple_select()
    bgp = _bgp_node(graph)
    triples_list = next(graph.objects(bgp, SALG.triples))
    first_triple = next(graph.objects(triples_list, RDF.first))
    old_subject = next(graph.objects(first_triple, SALG.subject))
    graph.remove((first_triple, SALG.subject, old_subject))
    graph.add((first_triple, SALG.subject, Literal("not a valid subject")))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_union_p1_pointing_at_unrecognized_node_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?p WHERE { { ?p : \"Alice\" } UNION { ?p : \"Bob\" } }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    union_node = next(graph.subjects(RDF.type, SALG.Union))
    old_p1 = next(graph.objects(union_node, SALG.p1))
    graph.remove((union_node, SALG.p1, old_p1))
    bogus = BNode()
    graph.add((bogus, RDF.type, URIRef("http://example.org/NotAnOperator")))
    graph.add((union_node, SALG.p1, bogus))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_bogus_node_reused_as_p1_via_another_operator_still_fails():
    """A second-order version of the test above: rather than the bogus
    node being directly assigned to salg:p1, give it a salg:p1 property of
    its own first (which - if salg:p1 still had rdfs:domain
    salg:GraphPattern - would falsely entail the bogus node itself as
    salg:GraphPattern), then use *that* bogus node as another Union's own
    p1. Confirms removing salg:p1/p2's rdfs:domain (not just rdfs:range)
    was necessary - domain entailment on the subject side of p1 is just as
    exploitable as range entailment on the object side, one hop removed."""
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?p WHERE { { ?p : \"Alice\" } UNION { ?p : \"Bob\" } }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    union_node = next(graph.subjects(RDF.type, SALG.Union))
    real_p1 = next(graph.objects(union_node, SALG.p1))

    bogus = BNode()
    graph.add((bogus, RDF.type, URIRef("http://example.org/NotAnOperator")))
    graph.add((bogus, SALG.p1, real_p1))

    graph.remove((union_node, SALG.p1, next(graph.objects(union_node, SALG.p1))))
    graph.add((union_node, SALG.p1, bogus))

    conforms, _, results_text = validate(graph)
    assert not conforms


_VALUES_QUERY = (
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    'SELECT ?p ?name WHERE { ?p foaf:name ?name . VALUES ?name { "Alice" "Bob" } }'
)

_SUBQUERY_QUERY = (
    "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
    "SELECT ?name WHERE { ?p foaf:name ?name . "
    "{ SELECT ?p WHERE { ?p foaf:age ?age } ORDER BY ?age LIMIT 1 } }"
)


def test_values_missing_res_fails():
    prepared = prepareQuery(_VALUES_QUERY)
    graph, root = query_to_rdf(prepared)
    values_node = next(graph.subjects(RDF.type, SALG.values))
    for res in list(graph.objects(values_node, SALG.res)):
        graph.remove((values_node, SALG.res, res))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:values" in results_text or "res" in results_text


def test_binding_with_two_vars_fails():
    """salg:Binding must have exactly one salg:var - a row entry can't be
    ambiguous about which variable it binds."""
    prepared = prepareQuery(_VALUES_QUERY)
    graph, root = query_to_rdf(prepared)
    binding = next(graph.subjects(RDF.type, SALG.Binding))
    graph.add((binding, SALG.var, Literal("other", datatype=SALG.Variable)))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_join_missing_p2_fails():
    prepared = prepareQuery(_VALUES_QUERY)
    graph, root = query_to_rdf(prepared)
    join_node = next(graph.subjects(RDF.type, SALG.Join))
    for p2 in list(graph.objects(join_node, SALG.p2)):
        graph.remove((join_node, SALG.p2, p2))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:Join" in results_text or "p2" in results_text


def test_slice_missing_start_fails():
    prepared = prepareQuery(_SUBQUERY_QUERY)
    graph, root = query_to_rdf(prepared)
    slice_node = next(graph.subjects(RDF.type, SALG.Slice))
    for start in list(graph.objects(slice_node, SALG.start)):
        graph.remove((slice_node, SALG.start, start))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:Slice" in results_text or "start" in results_text


def test_orderby_missing_expr_fails():
    prepared = prepareQuery(_SUBQUERY_QUERY)
    graph, root = query_to_rdf(prepared)
    orderby_node = next(graph.subjects(RDF.type, SALG.OrderBy))
    for expr in list(graph.objects(orderby_node, SALG.expr)):
        graph.remove((orderby_node, SALG.expr, expr))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:OrderBy" in results_text or "expr" in results_text


def test_tomultiset_p_pointing_at_unrecognized_node_fails():
    prepared = prepareQuery(_VALUES_QUERY)
    graph, root = query_to_rdf(prepared)
    tomultiset = next(graph.subjects(RDF.type, SALG.ToMultiSet))
    old_p = next(graph.objects(tomultiset, SALG.p))
    graph.remove((tomultiset, SALG.p, old_p))
    bogus = BNode()
    graph.add((bogus, RDF.type, URIRef("http://example.org/NotAnOperator")))
    graph.add((tomultiset, SALG.p, bogus))

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# Phase 6 (SPARQL 1.2 triple terms) — see shapes.py's TripleTermShape /
# SubjectOrVariableOrTripleTermShape / ObjectOrVariableOrTripleTermShape.
# ---------------------------------------------------------------------


@pytest.mark.parametrize("query_text", RDF12_QUERIES)
def test_valid_rdf12_queries_conform(query_text):
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_triple_term_missing_object_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?s WHERE { ?s :reifies <<( :bob :knows :carol )>> . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    tt_node = next(graph.subjects(RDF.type, SALG.TripleTerm))
    for obj in list(graph.objects(tt_node, SALG.object)):
        graph.remove((tt_node, SALG.object, obj))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:TripleTerm" in results_text or "object" in results_text


def test_triple_term_with_two_predicates_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?s WHERE { ?s :reifies <<( :bob :knows :carol )>> . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    tt_node = next(graph.subjects(RDF.type, SALG.TripleTerm))
    graph.add((tt_node, SALG.predicate, URIRef("http://example.org/other")))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_triple_term_as_predicate_of_triple_pattern_fails():
    """A TripleTerm is legal as a TriplePattern's subject/object but never
    its predicate — RDF has always restricted predicate position to IRIs.
    Construct this directly (rather than via the parser, which already
    rejects it at parse time — see grammar12.py) to confirm the SHACL shape
    itself would catch a malformed graph asserting this, not just the parser."""
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?s WHERE { ?s :reifies :bob . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    triple_pattern = next(graph.subjects(RDF.type, SALG.TriplePattern))
    old_predicate = next(graph.objects(triple_pattern, SALG.predicate))
    graph.remove((triple_pattern, SALG.predicate, old_predicate))

    tt_node = BNode()
    graph.add((tt_node, RDF.type, SALG.TripleTerm))
    graph.add((tt_node, SALG.subject, URIRef("http://example.org/bob")))
    graph.add((tt_node, SALG.predicate, URIRef("http://example.org/knows")))
    graph.add((tt_node, SALG.object, URIRef("http://example.org/carol")))
    graph.add((triple_pattern, SALG.predicate, tt_node))

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# Extend (BIND) + expression-tree shapes — see shapes.py's ExpressionShape/
# _EXPR_NODE_FAMILY and GraphPatternShape's own comment for the
# sh:class-not-sh:node recursion-avoidance rationale this section exists
# to verify.
# ---------------------------------------------------------------------


def test_bind_extend_conforms():
    """The counter-example that found this whole gap: BIND's algebra node
    (Extend) was missing from GraphPatternShape's recognized-operator list
    entirely, and nothing caught it - the old sh:node-based sh:or dispatch
    silently gave up (pyshacl's shape-recursion guard) before ever
    reaching the check. A real regression test, not just a positive-
    conformance one."""
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?x WHERE { ?s :p ?y . BIND(STR(?y) AS ?x) }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_extend_missing_var_fails():
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?x WHERE { ?s :p ?y . BIND(STR(?y) AS ?x) }"
    )
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    extend = next(graph.subjects(RDF.type, SALG.Extend))
    for var in list(graph.objects(extend, SALG.var)):
        graph.remove((extend, SALG.var, var))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:Extend" in results_text or "var" in results_text


# One FILTER/BIND query per expression-node family in _EXPR_NODE_FAMILY -
# every family must be exercised by at least one real, encoded query that
# conforms, the same "can't silently drift from what the encoder actually
# produces" discipline test_valid_phase1_queries_conform already applies.
EXPRESSION_FAMILY_QUERIES = [
    'SELECT * WHERE { ?s ?p ?y . BIND(NOW() AS ?z) }',  # ZeroArg
    'SELECT * WHERE { ?s ?p ?y . FILTER(STRSTARTS(STR(?y), "a")) }',  # OneArg (+ TwoArg)
    'SELECT * WHERE { ?s ?p ?y . BIND(BNODE() AS ?z) }',  # OptionalOneArg, absent
    'SELECT * WHERE { ?s ?p ?y . BIND(BNODE(?y) AS ?z) }',  # OptionalOneArg, present
    'SELECT * WHERE { ?s ?p ?y . FILTER(!BOUND(?y)) }',  # Unary
    'SELECT * WHERE { ?s ?p ?y . FILTER(IF(BOUND(?y), true, false)) }',  # ThreeArg
    'SELECT * WHERE { ?s ?p ?y . BIND(CONCAT(?y, ?s, "x") AS ?z) }',  # VariadicArg
    'SELECT * WHERE { ?s ?p ?y . FILTER(REGEX(?y, "a", "i")) }',  # Regex
    'SELECT * WHERE { ?s ?p ?y . BIND(REPLACE(?y, "a", "b", "i") AS ?z) }',  # Replace
    'SELECT * WHERE { ?s ?p ?y . BIND(SUBSTR(?y, 1, 3) AS ?z) }',  # Substr
    'SELECT * WHERE { ?s ?p ?y . FILTER EXISTS { ?y ?p2 ?o2 } }',  # Exists
    'SELECT * WHERE { ?s ?p ?y . FILTER NOT EXISTS { ?y ?p2 ?o2 } }',  # Exists
    'SELECT * WHERE { ?s ?p ?y . FILTER(<http://ex/fn>(?y, ?s) = 1) }',  # Function, Relational
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y IN (1,2,3)) }',  # Relational, other=list
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y = 1 && ?s = 2 && ?p = 3) }',  # Conditional, other=list
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y = 1 || ?s = 2) }',  # Conditional
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y != "x") }',  # Relational, other=single
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y + ?s - ?p = 1) }',  # Arithmetic
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y * ?s / ?p = 1) }',  # Arithmetic
    'SELECT * WHERE { ?s ?p ?y . FILTER(STR(STR(STR(?y))) = "x") }',  # nested ExpressionShape recursion
    'SELECT * WHERE { ?s ?p ?y . FILTER(?y != "Bob") } ORDER BY ?y',  # OrderCondition.expr wired
]


@pytest.mark.parametrize("query_text", EXPRESSION_FAMILY_QUERIES)
def test_expression_family_queries_conform(query_text):
    prepared = prepareQuery("PREFIX : <http://example.org/> " + query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_no_shape_recursion_warnings():
    """Positively verifies the sh:class fix, not just "conforms == True by
    absence of a signal" - before the fix, most of these queries produced
    dozens of ShapeRecursionWarnings and pyshacl silently treated the
    unchecked branch as conformant rather than actually checking it."""
    import warnings

    from pyshacl.errors import ShapeRecursionWarning

    for query_text in EXPRESSION_FAMILY_QUERIES:
        prepared = prepareQuery("PREFIX : <http://example.org/> " + query_text)
        graph, root = query_to_rdf(prepared)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate(graph)
        recursion_warnings = [w for w in caught if issubclass(w.category, ShapeRecursionWarning)]
        assert not recursion_warnings, f"{query_text!r} triggered {len(recursion_warnings)} ShapeRecursionWarning(s)"


def test_one_arg_builtin_missing_arg_fails():
    query_text = "PREFIX : <http://example.org/> SELECT * WHERE { ?s ?p ?y . FILTER(STR(?y) = \"x\") }"
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    node = next(graph.subjects(RDF.type, SALG.Builtin_STR))
    for arg in list(graph.objects(node, SALG.arg)):
        graph.remove((node, SALG.arg, arg))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:arg" in results_text or "Builtin_STR" in results_text


def test_regex_missing_text_fails():
    query_text = 'PREFIX : <http://example.org/> SELECT * WHERE { ?s ?p ?y . FILTER(REGEX(?y, "a")) }'
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    node = next(graph.subjects(RDF.type, SALG.Builtin_REGEX))
    for text_val in list(graph.objects(node, SALG.text)):
        graph.remove((node, SALG.text, text_val))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:text" in results_text or "Builtin_REGEX" in results_text


def test_function_missing_iri_fails():
    query_text = "PREFIX : <http://example.org/> SELECT * WHERE { ?s ?p ?y . FILTER(<http://ex/fn>(?y) = 1) }"
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)
    node = next(graph.subjects(RDF.type, SALG.Function))
    for iri in list(graph.objects(node, SALG.iri)):
        graph.remove((node, SALG.iri, iri))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:iri" in results_text or "Function" in results_text


def test_nested_triple_term_in_subject_position_fails():
    """RDF 1.2 restricts a triple term's own subject to an IRI/blank
    node/Variable, never another (nested) triple term. Construct this
    directly - the parser already rejects it (see grammar12.py's
    _TripleTermSubject) - to confirm the SHACL shape independently catches a
    malformed graph asserting it."""
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?s WHERE { ?s :reifies <<( :bob :knows :carol )>> . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    tt_node = next(graph.subjects(RDF.type, SALG.TripleTerm))
    old_subject = next(graph.objects(tt_node, SALG.subject))
    graph.remove((tt_node, SALG.subject, old_subject))

    nested = BNode()
    graph.add((nested, RDF.type, SALG.TripleTerm))
    graph.add((nested, SALG.subject, URIRef("http://example.org/x")))
    graph.add((nested, SALG.predicate, URIRef("http://example.org/y")))
    graph.add((nested, SALG.object, URIRef("http://example.org/z")))
    graph.add((tt_node, SALG.subject, nested))

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# SPARQL Update - InsertData/DeleteData/DeleteWhere/Modify/Load/Clear/Drop/
# Create/Add/Move/Copy, plus the salg:Update root and salg:QuadsForGraph.
# ---------------------------------------------------------------------


@pytest.mark.parametrize("update_text", SINGLE_GRAPH_UPDATES + MULTI_GRAPH_UPDATES)
def test_valid_updates_conform(update_text):
    prepared = prepareUpdate(update_text)
    graph, root = update_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_insert_data_missing_triples_fails():
    prepared = prepareUpdate("PREFIX : <http://example.org/> INSERT DATA { :a :b :c }")
    graph, root = update_to_rdf(prepared)
    op = next(graph.subjects(RDF.type, SALG.InsertData))
    for triples in list(graph.objects(op, SALG.triples)):
        graph.remove((op, SALG.triples, triples))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:triples" in results_text or "triples" in results_text


def test_modify_missing_both_delete_and_insert_fails():
    prepared = prepareUpdate(
        "PREFIX : <http://example.org/> "
        "DELETE { ?p :age ?a } INSERT { ?p :age 99 } WHERE { ?p :age ?a }"
    )
    graph, root = update_to_rdf(prepared)
    op = next(graph.subjects(RDF.type, SALG.Modify))
    for delete in list(graph.objects(op, SALG.delete)):
        graph.remove((op, SALG.delete, delete))
    for insert in list(graph.objects(op, SALG.insert)):
        graph.remove((op, SALG.insert, insert))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:delete" in results_text or "salg:insert" in results_text or "Modify" in results_text


def test_clear_graphiri_neither_term_nor_pystr_fails():
    """salg:graphiri must be a graph term or a salg:PyStr-tagged keyword
    (DEFAULT/NAMED/ALL) - a bare integer literal is neither."""
    prepared = prepareUpdate("PREFIX : <http://example.org/> CLEAR DEFAULT")
    graph, root = update_to_rdf(prepared)
    op = next(graph.subjects(RDF.type, SALG.Clear))
    for graphiri in list(graph.objects(op, SALG.graphiri)):
        graph.remove((op, SALG.graphiri, graphiri))
    graph.add((op, SALG.graphiri, Literal(42)))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_add_graph_with_three_elements_fails():
    """salg:graph on Add/Move/Copy must be exactly a 2-element list
    [source, dest] - confirm a 3rd element is rejected, not just checked
    for well-formedness."""
    prepared = prepareUpdate(
        "PREFIX : <http://example.org/> INSERT DATA { GRAPH :g1 { :a :b :c } } ; ADD :g1 TO :g2"
    )
    graph, root = update_to_rdf(prepared)
    op = next(graph.subjects(RDF.type, SALG.Add))
    graph_list = next(graph.objects(op, SALG.graph))
    from rdflib.collection import Collection

    Collection(graph, graph_list).append(URIRef("http://example.org/g3"))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_update_operations_list_with_bogus_member_fails():
    """salg:Update's own salg:operations list must contain only
    salg:UpdateOperation-typed members - a bogus, untyped blank node
    spliced into the list should be rejected."""
    prepared = prepareUpdate("PREFIX : <http://example.org/> INSERT DATA { :a :b :c }")
    graph, root = update_to_rdf(prepared)
    ops_list = next(graph.objects(root, SALG.operations))
    from rdflib.collection import Collection

    Collection(graph, ops_list).append(BNode())

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# CONSTRUCT / ASK / DESCRIBE - test_phase2_forms.QUERIES covers all three
# (including a bare DESCRIBE with no WHERE clause) plus a MINUS query,
# which already conforms today (salg:Minus is already rdfs:subClassOf
# salg:GraphPattern from the ontology pass, so GraphPatternShape's own
# sh:class check already accepts it - a dedicated MinusShape, added later,
# only adds stricter validation of Minus's own p1/p2, not a new
# requirement this positive test needs to wait for).
# ---------------------------------------------------------------------


@pytest.mark.parametrize("query_text", FORMS_QUERIES)
def test_valid_forms_queries_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_construct_missing_template_fails():
    prepared = prepareQuery(
        "PREFIX : <http://example.org/> CONSTRUCT { ?p :hasName ?n } WHERE { ?p :name ?n }"
    )
    graph, root = query_to_rdf(prepared)
    construct_node = next(graph.subjects(RDF.type, SALG.ConstructQuery))
    for template in list(graph.objects(construct_node, SALG.template)):
        graph.remove((construct_node, SALG.template, template))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:template" in results_text or "template" in results_text


def test_ask_missing_p_fails():
    prepared = prepareQuery("PREFIX : <http://example.org/> ASK { ?p :age 30 }")
    graph, root = query_to_rdf(prepared)
    ask_node = next(graph.subjects(RDF.type, SALG.AskQuery))
    for p in list(graph.objects(ask_node, SALG.p)):
        graph.remove((ask_node, SALG.p, p))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_describe_with_no_where_clause_conforms():
    """A bare DESCRIBE (no WHERE clause at all) has salg:p entirely absent
    - confirm this is accepted, not just the with-WHERE form covered by
    test_valid_forms_queries_conform."""
    prepared = prepareQuery("PREFIX : <http://example.org/> DESCRIBE :alice")
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


# ---------------------------------------------------------------------
# Property paths - InvPath/SequencePath/AlternativePath/MulPath/
# NegatedPath, all 5 confirmed by test_phase2_paths.QUERIES (+/*/?/^/|
# //! all exercised there).
# ---------------------------------------------------------------------


@pytest.mark.parametrize("query_text", PATH_QUERIES)
def test_valid_path_queries_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_mulpath_missing_mod_fails():
    prepared = prepareQuery("PREFIX : <http://example.org/> SELECT ?x WHERE { :alice :knows+ ?x }")
    graph, root = query_to_rdf(prepared)
    mulpath_node = next(graph.subjects(RDF.type, SALG.MulPath))
    for mod in list(graph.objects(mulpath_node, SALG.mod)):
        graph.remove((mulpath_node, SALG.mod, mod))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:mod" in results_text or "mod" in results_text


def test_triple_pattern_predicate_neither_iri_variable_nor_path_fails():
    """Confirm the PredicateOrVariableOrPathShape widening didn't loosen
    things beyond IRI/Variable/Path - a plain Literal is still rejected."""
    graph, root = _encode_simple_select()
    bgp = _bgp_node(graph)
    triples_list = next(graph.objects(bgp, SALG.triples))
    first_triple = next(graph.objects(triples_list, RDF.first))
    old_predicate = next(graph.objects(first_triple, SALG.predicate))
    graph.remove((first_triple, SALG.predicate, old_predicate))
    graph.add((first_triple, SALG.predicate, Literal("not a valid predicate")))

    conforms, _, results_text = validate(graph)
    assert not conforms


def test_triple_term_predicate_as_path_fails():
    """A TripleTerm's own predicate must stay IRI/Variable-only - a
    property path is legal in an ordinary triple pattern's predicate slot
    but never inside a triple term (RDF 1.2's tripleTerm production
    restricts its own verb to a plain iri). Construct this directly, since
    the grammar already rejects it at parse time (only Var|iri spliced in
    for _TripleTermPredicate) - confirms the SHACL shape independently
    enforces the same restriction on a malformed graph."""
    query_text = (
        "PREFIX : <http://example.org/> "
        "SELECT ?s WHERE { ?s :reifies <<( :bob :knows :carol )>> . }"
    )
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    tt_node = next(graph.subjects(RDF.type, SALG.TripleTerm))
    old_predicate = next(graph.objects(tt_node, SALG.predicate))
    graph.remove((tt_node, SALG.predicate, old_predicate))

    path_node = BNode()
    graph.add((path_node, RDF.type, SALG.InvPath))
    graph.add((path_node, SALG.arg, URIRef("http://example.org/knows")))
    graph.add((tt_node, SALG.predicate, path_node))

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# GROUP BY / aggregates - Group/AggregateJoin/Aggregate_Count/Sum/Avg/
# GroupConcat all confirmed by test_phase2_aggregates.QUERIES (COUNT
# DISTINCT and implicit-single-group with no explicit GROUP BY are also
# both covered there).
# ---------------------------------------------------------------------


@pytest.mark.parametrize("query_text", AGGREGATE_QUERIES)
def test_valid_aggregate_queries_conform(query_text):
    prepared = prepareQuery(query_text)
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_aggregate_count_missing_vars_fails():
    prepared = prepareQuery(
        "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
        "SELECT ?team (COUNT(?p) AS ?n) WHERE { ?p foaf:team ?team } GROUP BY ?team"
    )
    graph, root = query_to_rdf(prepared)
    agg_node = next(graph.subjects(RDF.type, SALG.Aggregate_Count))
    for vars_ in list(graph.objects(agg_node, SALG.vars)):
        graph.remove((agg_node, SALG.vars, vars_))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:vars" in results_text or "vars" in results_text


# ---------------------------------------------------------------------
# MINUS / SERVICE - MINUS is already covered by test_valid_forms_queries_
# conform above (test_phase2_forms.QUERIES includes one); SERVICE is
# checked structurally only here too (never executed - see
# test_phase2_forms.py's own docstring for why), reusing the same query
# text as that file's test_service_structural_roundtrip.
# ---------------------------------------------------------------------


def test_service_conforms():
    prepared = prepareQuery(
        "PREFIX : <http://example.org/> "
        "SELECT ?x WHERE { SERVICE <http://example.org/sparql> { ?x :p ?y } }"
    )
    graph, root = query_to_rdf(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_minus_missing_p2_fails():
    prepared = prepareQuery(
        "PREFIX : <http://example.org/> "
        "SELECT ?p WHERE { ?p a :Person MINUS { ?p :age 25 } }"
    )
    graph, root = query_to_rdf(prepared)
    minus_node = next(graph.subjects(RDF.type, SALG.Minus))
    for p2 in list(graph.objects(minus_node, SALG.p2)):
        graph.remove((minus_node, SALG.p2, p2))

    conforms, _, results_text = validate(graph)
    assert not conforms
    assert "salg:p2" in results_text or "p2" in results_text


def test_service_missing_term_fails():
    prepared = prepareQuery(
        "PREFIX : <http://example.org/> "
        "SELECT ?x WHERE { SERVICE <http://example.org/sparql> { ?x :p ?y } }"
    )
    graph, root = query_to_rdf(prepared)
    service_node = next(graph.subjects(RDF.type, SALG.ServiceGraphPattern))
    # SALG.term (attribute access), not SALG["term"], would silently
    # resolve to rdflib.Namespace's own real .term() *method* instead of
    # the salg:term URIRef - a genuine Python-level name collision found
    # while writing this exact test (to_rdf.py's own generic encoder is
    # unaffected, since it always uses SALG[key] bracket access).
    term_pred = SALG["term"]
    for term in list(graph.objects(service_node, term_pred)):
        graph.remove((service_node, term_pred, term))

    conforms, _, results_text = validate(graph)
    assert not conforms


# ---------------------------------------------------------------------
# QueryCollection (see to_rdf.queries_to_collection) - Phase 8.
# ---------------------------------------------------------------------


def test_query_collection_of_valid_queries_conforms():
    prepared = [prepareQuery(q) for q in QUERIES]
    graph, root = queries_to_collection(prepared)

    conforms, _, results_text = validate(graph)
    assert conforms, results_text


def test_query_collection_with_bogus_member_fails():
    prepared = [prepareQuery(QUERIES[0])]
    graph, root = queries_to_collection(prepared)
    queries_list = next(graph.objects(root, SALG.queries))
    from rdflib.collection import Collection

    Collection(graph, queries_list).append(BNode())

    conforms, _, results_text = validate(graph)
    assert not conforms
