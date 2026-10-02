"""Tests that starlayer.sparql.validate_query() itself catches an unbound
projected variable via the real SHACL constraint component
(native_components.py, activated by salg:noUnboundProjectedVariables
on salg:ProjectShape in sparql_shapes.ttl) - not just via the standalone
starlayer.sparql.find_unbound_projected_variables() function
(test_semantic_checks.py already covers that path directly).
"""

import starlayer.sparql
from rdflib.namespace import SH


def _validate(query_text):
    parsed = starlayer.sparql.prepare_query_12(query_text)
    graph, root = starlayer.sparql.query_to_rdf(parsed)
    return starlayer.sparql.validate_query(graph)


class TestNativeComponentCatchesUnboundProjectedVariable:
    def test_conforms_is_false(self):
        conforms, _report_graph, _report_text = _validate(
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> }"
        )
        assert conforms is False

    def test_report_names_the_right_source_constraint_component(self):
        _conforms, report_graph, _report_text = _validate(
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> }"
        )
        SALG = starlayer.sparql.SALG
        components = set(report_graph.objects(None, SH.sourceConstraintComponent))
        assert SALG.NoUnboundProjectedVariablesConstraintComponent in components

    def test_report_names_the_unbound_variable_as_the_value_node(self):
        # A rdflib.Variable isn't a valid RDF term for real triple storage -
        # once added to the report graph, it round-trips as a URIRef of the
        # same name (confirmed empirically, not assumed) rather than
        # staying a Variable instance.
        _conforms, report_graph, _report_text = _validate(
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> }"
        )
        values = {str(v) for v in report_graph.objects(None, SH.value)}
        assert "y" in values

    def test_ordinary_fully_bound_query_conforms(self):
        conforms, _report_graph, _report_text = _validate(
            "SELECT ?x WHERE { ?x a <http://example.org/Foo> }"
        )
        assert conforms is True

    def test_select_star_conforms(self):
        conforms, _report_graph, _report_text = _validate("SELECT * WHERE { ?x a <http://example.org/Foo> }")
        assert conforms is True

    def test_bind_bound_variable_conforms(self):
        conforms, _report_graph, _report_text = _validate(
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> . BIND(STR(?x) AS ?y) }"
        )
        assert conforms is True

    def test_optional_bound_variable_conforms(self):
        conforms, _report_graph, _report_text = _validate(
            "SELECT ?x ?y WHERE { ?x a <http://example.org/Foo> . "
            "OPTIONAL { ?x <http://example.org/age> ?y } }"
        )
        assert conforms is True
