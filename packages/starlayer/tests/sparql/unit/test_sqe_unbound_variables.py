"""The "a projected variable is never bound anywhere in its own pattern" check, on ``sqe:`` trees.

It was the one semantic check the retired ``salg:`` export had (``find_unbound_projected_variables``); the ``sqe:`` shapes
(``sqe_shapes.ttl``) now carry it, and ``sqe_parse_to_tree`` refuses a query that fails it. The cases below were moved from
the salg tests; the SHACL pre-bound names (``$this`` / ``$value`` / ``$PATH``) are exempt in an embedded ``sh:select`` /
``sh:ask`` / ``sh:construct`` query (``starlayer.shacl.meta_shapes.sparql_query_problems``).
"""

import pytest
from starlayer.sparql.sqe import SQEValidationError, sqe_parse_to_tree

EX = "http://example.org/"


def _issues(query_text: str) -> list[str]:
    """The messages of the violations ``sqe_parse_to_tree`` reports for the query (empty when it conforms)."""
    try:
        sqe_parse_to_tree(query_text)
    except SQEValidationError as exc:
        from starlayer.shacl_engine.terms import SH

        return sorted(m.value for m in exc.report_graph.objects(None, SH.resultMessage))
    return []


class TestGenuinelyUnbound:
    def test_flagged_issue_names_the_right_variable(self):
        issues = _issues(f"SELECT ?x ?y WHERE {{ ?x a <{EX}Foo> }}")
        assert len(issues) == 1
        assert "variable y " in issues[0]

    def test_nested_subquery_outer_projecting_inner_only_var(self):
        issues = _issues(f"SELECT ?z WHERE {{ {{ SELECT ?x WHERE {{ ?x a <{EX}Foo> }} }} }}")
        assert len(issues) == 1

    def test_unbound_variable_inside_an_expression(self):
        issues = _issues(f"SELECT ?x WHERE {{ ?x a <{EX}Foo> FILTER(?zz > 1) }}")
        assert len(issues) == 1 and "ariable zz " in issues[0]


class TestGenuinelyBound:
    def test_ordinary_fully_bound_query_is_clean(self):
        assert _issues(f"SELECT ?x WHERE {{ ?x a <{EX}Foo> }}") == []

    def test_select_star_has_nothing_to_misname(self):
        assert _issues(f"SELECT * WHERE {{ ?x a <{EX}Foo> }}") == []

    def test_bind_bound_variable_not_flagged(self):
        assert _issues(f"SELECT ?x ?y WHERE {{ ?x a <{EX}Foo> . BIND(STR(?x) AS ?y) }}") == []

    def test_optional_bound_variable_not_flagged(self):
        assert _issues(f"SELECT ?x ?y WHERE {{ ?x a <{EX}Foo> . OPTIONAL {{ ?x <{EX}age> ?y }} }}") == []

    def test_property_path_bound_variable_not_flagged(self):
        assert _issues(f"SELECT ?x ?y WHERE {{ ?x <{EX}knows>* ?y }}") == []

    def test_values_bound_variable_not_flagged(self):
        assert _issues("SELECT ?x WHERE { VALUES ?x { 1 2 } }") == []

    def test_sub_select_projected_variable_not_flagged(self):
        assert _issues(f"SELECT ?x ?c WHERE {{ {{ SELECT ?x (COUNT(?o) AS ?c) WHERE {{ ?x <{EX}p> ?o }} GROUP BY ?x }} }}") == []


class TestEmbeddedShaclQueries:
    """``sparql_query_problems`` exempts exactly ``$this`` / ``$value`` / ``$PATH`` (bound by the SHACL engine), and only there."""

    def _problems(self, select: str, *, target: bool = False) -> list[str]:
        from starlayer.graph.oxgraph.core import StarLayerGraph
        from starlayer.shacl.meta_shapes import sparql_query_problems

        wrapper = "sh:target [ a sh:SPARQLTarget ; sh:select" if target else "sh:sparql [ a sh:SPARQLConstraint ; sh:select"
        g = StarLayerGraph()
        g.parse(
            data=f'@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <{EX}> . ex:S a sh:NodeShape ; {wrapper} """{select}""" ] .',
            format="turtle",
        )
        return [message for _node, _predicate, message in sparql_query_problems(g)]

    def test_this_only_validator_is_not_flagged(self):
        assert self._problems("SELECT $this WHERE { FILTER(isIRI($value)) }") == []

    def test_a_target_query_must_bind_this(self):
        assert self._problems("SELECT $this WHERE { FILTER(true) }", target=True)

    @pytest.mark.parametrize("variable", ["x", "other"])
    def test_any_other_unbound_variable_is_still_a_defect(self, variable):
        assert self._problems(f"SELECT $this ?{variable} WHERE {{ $this ?p ?o }}")
