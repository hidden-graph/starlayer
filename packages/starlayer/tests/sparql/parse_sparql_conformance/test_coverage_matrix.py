"""Production coverage matrix for the SPARQL 1.2 Query grammar (the hand-written parser ``parse_sparql``).

Mirrors ``tests/sparql/srl_conformance/test_sr_coverage_matrix.py``: the spine is the W3C grammar table
(``vendor/sparql12-query-productions.json``, 194 productions); each production must be claimed by at least one case
in ``corpus.py``; every case parses (or, for the negative ones, is rejected); and where a production has a dedicated
method in the parser the claim is checked by tracing: that method must run on at least one of the cases claiming it.
"""

from __future__ import annotations

import sys

import pytest
from starlayer.sparql.parse_sparql import SparqlSyntaxError, parse_sparql
from starlayer.sparql.sqe import sqe_tree_to_text

from .corpus import BUILTINS, CASES, P
from .grammar import ALL_ROWS, PRODUCTIONS, UPDATE_ONLY

# production -> parser methods, any one of which must run (productions absent here are lexical or have no own method)
METHODS: dict[str, tuple[str, ...]] = {
    "QueryUnit": ("parse_query",), "Query": ("parse_query",), "Prologue": ("parse_prologue",),
    "BaseDecl": ("parse_prologue",), "PrefixDecl": ("parse_prologue",), "VersionDecl": ("parse_prologue",),
    "SelectQuery": ("select_query",), "SubSelect": ("_group_body",), "SelectClause": ("select_clause",),
    "ConstructQuery": ("construct_query",), "DescribeQuery": ("describe_query",), "DatasetClause": ("dataset_clauses",),
    "WhereClause": ("where_clause",), "SolutionModifier": ("solution_modifier",), "ValuesClause": ("values_clause",),
    "TriplesTemplate": ("triples_template",), "ConstructTemplate": ("triples_template",),
    "GroupGraphPattern": ("group_graph_pattern",), "GroupGraphPatternSub": ("_group_body",),
    "TriplesBlock": ("triples_same_subject",), "TriplesSameSubject": ("triples_same_subject",),
    "TriplesSameSubjectPath": ("triples_same_subject",),
    "GraphPatternNotTriples": ("graph_pattern_not_triples",), "Filter": ("graph_pattern_not_triples",),
    "InlineData": ("inline_data",), "DataBlock": ("inline_data",), "DataBlockValue": ("data_value",),
    "Reifier": ("reifier_id",), "Constraint": ("constraint",), "FunctionCall": ("function_call",),
    "ExpressionList": ("expression_list",), "PropertyListNotEmpty": ("property_list",),
    "PropertyListPathNotEmpty": ("property_list",), "Verb": ("verb_simple",), "VerbPath": ("verb_path",),
    "Path": ("path_alternative",), "PathAlternative": ("path_alternative",), "PathSequence": ("path_sequence",),
    "PathEltOrInverse": ("path_elt_or_inverse",), "PathElt": ("path_elt",), "PathPrimary": ("path_primary",),
    "PathOneInPropertySet": ("path_one_in_set",), "TriplesNode": ("triples_node",), "Collection": ("triples_node",),
    "BlankNodePropertyList": ("triples_node",), "AnnotationPath": ("annotations",), "Annotation": ("annotations",),
    "ReifiedTriple": ("reified_triple",), "TripleTerm": ("triple_term",), "TripleTermData": ("triple_term",),
    "VarOrTerm": ("var_or_term",), "Expression": ("expression",), "ConditionalOrExpression": ("expression",),
    "ConditionalAndExpression": ("cond_and",), "RelationalExpression": ("relational",),
    "AdditiveExpression": ("additive",), "MultiplicativeExpression": ("multiplicative",),
    "UnaryExpression": ("unary",), "PrimaryExpression": ("primary",), "ExprTripleTerm": ("expr_triple_term",),
    "BrackettedExpression": ("bracketted",), "BuiltInCall": ("builtin",), "Aggregate": ("aggregate",),
    "RDFLiteral": ("literal",), "NumericLiteral": ("literal",), "BooleanLiteral": ("literal",),
    "String": ("string", "literal"), "iri": ("iri",), "BlankNode": ("bnode",), "Var": ("var",),
}  # fmt: skip


def _covered() -> set[str]:
    return {name for case in CASES for name in case.covers}


def test_the_table_is_the_grammar():
    assert len(PRODUCTIONS) == 194 and ALL_ROWS[0] == "QueryUnit" and ALL_ROWS[-1] == "PN_LOCAL_ESC"
    assert {PRODUCTIONS[n] for n in ("Query",)} and len(UPDATE_ONLY) == 24
    assert {"UpdateUnit", "Update", "Load", "Quads", "QuadsNotTriples"} <= UPDATE_ONLY


def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


def test_every_covers_name_is_a_real_production():
    bad = {(c.id, n) for c in CASES for n in c.covers if n not in PRODUCTIONS}
    assert not bad, f"cases name productions that are not in the grammar table: {sorted(bad)}"


def test_every_query_production_has_a_case():
    missing = [n for n in ALL_ROWS if n not in _covered() and n not in UPDATE_ONLY]
    assert not missing, f"productions with no case (add one to corpus.py): {missing}"


def test_update_only_rows_are_not_claimed():
    assert not (_covered() & UPDATE_ONLY), "an Update production is claimed by a Query case"


def test_every_method_mapping_names_a_real_production_and_method():
    from starlayer.sparql.parse_sparql import _Parser

    assert set(METHODS) <= set(PRODUCTIONS)
    for methods in METHODS.values():
        for m in methods:
            assert hasattr(_Parser, m), m


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case_parses_or_is_rejected(case):
    if case.ok:
        parse_sparql(case.text)
    else:
        with pytest.raises(SparqlSyntaxError):
            parse_sparql(case.text)


def _methods_run(text: str) -> set[str]:
    seen: set[str] = set()
    path = sys.modules["starlayer.sparql.parse_sparql"].__file__

    def prof(frame, event, arg):
        if event == "call" and frame.f_code.co_filename == path:
            seen.add(frame.f_code.co_name)

    sys.setprofile(prof)
    try:
        try:
            parse_sparql(text)
        except SparqlSyntaxError:
            pass
    finally:
        sys.setprofile(None)
    return seen


def test_claims_are_backed_by_the_parser_running_the_production():
    """A positive case that claims a production with a dedicated method must make that method run."""
    ran: dict[str, set[str]] = {c.id: _methods_run(c.text) for c in CASES}
    unbacked: list[tuple[str, str]] = []
    for prod, methods in METHODS.items():
        claimants = [c for c in CASES if prod in c.covers]
        if not claimants:
            continue
        if not any(set(methods) & ran[c.id] for c in claimants):
            unbacked.append((prod, ",".join(c.id for c in claimants)))
    assert not unbacked, f"claimed but the parser method never ran: {unbacked}"


@pytest.mark.parametrize("name", sorted(BUILTINS))
def test_every_builtin_call_alternative_parses_and_round_trips(name):
    from starlayer.sparql.parse_sparql import sparql_to_tree

    text = P + f"SELECT * {{ ?x :p ?y FILTER({BUILTINS[name]}) }}"
    tree = sparql_to_tree(text)
    again = sparql_to_tree(sqe_tree_to_text(*tree))
    from rdflib.compare import isomorphic
    from tests.sparql.parse_sparql_support import canonical_graph

    assert isomorphic(canonical_graph(tree[0]), canonical_graph(again[0]))


def test_builtin_table_matches_the_grammar():
    """Every quoted keyword of the BuiltInCall production is in BUILTINS (so a new draft keyword fails here)."""
    import re

    body = PRODUCTIONS["BuiltInCall"] + PRODUCTIONS["Aggregate"] + PRODUCTIONS["ExistsFunc"] + PRODUCTIONS["NotExistsFunc"]
    keywords = set(re.findall(r"'([A-Za-z_0-9]+)'", body))
    structural = {"COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE", "GROUP_CONCAT", "DISTINCT", "SEPARATOR", "NOT", "EXISTS"}
    covered = {k.split("-")[0] for k in BUILTINS}
    assert keywords - structural - covered == set()
