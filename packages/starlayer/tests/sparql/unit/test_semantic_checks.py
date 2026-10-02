"""Tests for starlayer.sparql.semantic_checks.find_unbound_projected_variables -
the "Project.PV names a variable never bound anywhere in its own pattern
subtree" cross-referential check SHACL's own per-node shapes structurally
can't see (previously an open, deliberately-not-pursued gap in
packages/sparql/CLAUDE.md - see that module's own docstring for the full
design rationale: reusing rdflib's real _addVars bookkeeping rather than
reimplementing SPARQL's variable-scoping rules as SHACL shapes).
"""

import starlayer.sparql
from starlayer.sparql import UnboundProjectedVariable, find_unbound_projected_variables


def _query_issues(query_text):
    parsed = starlayer.sparql.prepare_query_12(query_text)
    graph, root = starlayer.sparql.query_to_rdf(parsed)
    return find_unbound_projected_variables(graph)


def _update_issues(update_text):
    parsed = starlayer.sparql.prepare_update_12(update_text)
    graph, root = starlayer.sparql.update_to_rdf(parsed)
    return find_unbound_projected_variables(graph)


class TestGenuinelyUnbound:
    def test_flagged_issue_names_the_right_variable(self):
        from rdflib import Variable

        issues = _query_issues("SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> }")
        assert len(issues) == 1
        assert issues[0].variable == Variable("y")
        assert isinstance(issues[0], UnboundProjectedVariable)

    def test_nested_subquery_outer_projecting_inner_only_var(self):
        issues = _query_issues(
            "SELECT ?z WHERE { { SELECT ?x WHERE { ?x a <http://example.org/Foo> } } }"
        )
        assert len(issues) == 1

    def test_update_subquery_projecting_unbound_var(self):
        issues = _update_issues(
            "PREFIX ex: <http://example.org/> "
            'INSERT { ?x ex:tag "y" } WHERE { { SELECT ?z WHERE { ?x a ex:Foo } } }'
        )
        assert len(issues) == 1


class TestGenuinelyBound:
    def test_ordinary_fully_bound_query_is_clean(self):
        assert _query_issues("SELECT ?x WHERE { ?x a <http://example.org/Foo> }") == []

    def test_select_star_has_nothing_to_misname(self):
        assert _query_issues("SELECT * WHERE { ?x a <http://example.org/Foo> }") == []

    def test_bind_bound_variable_not_flagged(self):
        q = "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> . BIND(STR(?x) AS ?y) }"
        assert _query_issues(q) == []

    def test_optional_bound_variable_not_flagged(self):
        q = (
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> . "
            "OPTIONAL { ?x <http://example.org/age> ?y } }"
        )
        assert _query_issues(q) == []

    def test_property_path_bound_variable_not_flagged(self):
        q = "SELECT ?x ?y WHERE { ?x <http://example.org/knows>* ?y }"
        assert _query_issues(q) == []

    def test_ordinary_update_no_subquery_is_clean(self):
        u = "PREFIX ex: <http://example.org/> INSERT { ?x ex:tag \"y\" } WHERE { ?x a ex:Foo }"
        assert _update_issues(u) == []

    def test_update_with_no_where_clause_is_clean(self):
        assert _update_issues("CLEAR DEFAULT") == []
        assert _update_issues("PREFIX ex: <http://example.org/> INSERT DATA { ex:a ex:b ex:c }") == []
