"""Tests for starlayer.sparql.sqe - a human-readable, editable SPARQL
query tree meant to be paired with its own SHACL shapes to drive a UI
editor (see sqe/vocab.py's own module docstring for the full design).

Three things get verified, mirroring the standards already established
elsewhere in this package:

1. Round-trip + execution (same standard as test_ast_ontology.py/
   test_roundtrip.py): text -> parse tree -> sqe: RDF -> reconstructed
   parse tree -> translateQuery -> execute, compared against the
   originally-prepared query's own real execution, by result set.
2. Text round-trip, which the other RDF-as-SPARQL layers don't have:
   sqe: RDF -> rendered text -> re-parsed -> executed, still compared
   against the original - and the original PREFIX declaration is
   confirmed to survive into the rendered text (the whole reason
   to_text.py exists as a bespoke renderer rather than reusing
   translateAlgebra, which ignores query.prologue entirely).
3. SHACL conformance (same standard as test_shacl_shapes.py): valid
   queries conform; a deliberately malformed graph fails for the specific
   structural reason the mutation introduces.
"""

import pytest
from rdflib import RDF, BNode, Literal, URIRef
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery
from starlayer.sparql.sqe import (
    SQEValidationError,
    sqe_parse_to_tree,
    sqe_tree_to_query,
    sqe_tree_to_text,
    sqe_validate,
)
from starlayer.sparql.sqe.vocab import (
    PREFIX_BINDING,
    PREFIX_LABEL,
    PREFIX_NAMESPACE,
    QUERY,
    TEMPLATE,
    TRIPLE_PATTERN_PREDICATE,
    UNION,
    UNION_ALTERNATIVES,
)

PREFIXES = """
PREFIX : <http://example.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

QUERIES = [
    PREFIXES + "SELECT ?name WHERE { ?p a foaf:Person ; foaf:name ?name }",
    PREFIXES + """
        SELECT ?name ?age WHERE {
          ?p foaf:name ?name .
          OPTIONAL { ?p foaf:age ?age }
          FILTER(!BOUND(?age) || ?age > 26)
        }
    """,
    PREFIXES + """
        SELECT ?p WHERE {
          { ?p foaf:name "Alice" } UNION { ?p foaf:name "Bob" }
        }
    """,
    PREFIXES + """
        SELECT ?name ?greeting WHERE {
          ?p foaf:name ?name .
          BIND(CONCAT("Hi ", ?name) AS ?greeting)
        }
    """,
    # property path - covered, not excluded from v1 (see vocab.py's own
    # module docstring correction)
    PREFIXES + "SELECT ?a ?b WHERE { ?a foaf:knows+ ?b }",
    PREFIXES + "ASK { ?p foaf:name \"Alice\" }",
    PREFIXES + "CONSTRUCT { ?p :label ?name } WHERE { ?p foaf:name ?name }",
]


def _canon(res):
    if "askAnswer" in res:
        return res["askAnswer"]
    if "graph" in res:
        return sorted(" ".join(term.n3() for term in triple) for triple in res["graph"])
    rows = []
    for b in res["bindings"]:
        rows.append(frozenset((str(k), v.n3()) for k, v in b.items() if v is not None))
    return sorted(rows, key=lambda r: sorted(r))


class TestRoundtripResultEquivalence:
    @pytest.mark.parametrize("query_text", QUERIES)
    def test_rdf_roundtrip(self, fixture_graph, query_text):
        prepared = prepareQuery(query_text)
        original = evalQuery(fixture_graph, prepared)

        graph, root = sqe_parse_to_tree(query_text)
        reconstructed = sqe_tree_to_query(graph, root)
        roundtripped = evalQuery(fixture_graph, reconstructed)

        canon_original = _canon(original)
        canon_roundtripped = _canon(roundtripped)
        assert canon_original == canon_roundtripped
        # guard against a vacuously-true empty comparison (not meaningful for
        # ASK's plain boolean result)
        if not isinstance(canon_original, bool):
            assert len(canon_original) > 0

    @pytest.mark.parametrize("query_text", QUERIES)
    def test_text_roundtrip(self, fixture_graph, query_text):
        """Encode -> render text -> re-parse -> execute - the path only
        sqe: has (salg:/ssyn:/sast: all accept unprefixed-only text
        output; this is the point of to_text.py's bespoke renderer)."""
        prepared = prepareQuery(query_text)
        original = evalQuery(fixture_graph, prepared)

        graph, root = sqe_parse_to_tree(query_text)
        rendered = sqe_tree_to_text(graph, root)
        reparsed = prepareQuery(rendered)
        roundtripped = evalQuery(fixture_graph, reparsed)

        assert _canon(original) == _canon(roundtripped)

    def test_original_prefix_survives_into_rendered_text(self):
        """The whole reason to_text.py exists instead of reusing
        translateAlgebra: the user's own PREFIX declaration must appear in
        the regenerated text, and the WHERE clause must use it - not just
        a resolvable full IRI."""
        query_text = PREFIXES + "SELECT ?name WHERE { ?p foaf:name ?name }"
        graph, root = sqe_parse_to_tree(query_text)
        rendered = sqe_tree_to_text(graph, root)
        where_clause = rendered.split("WHERE", 1)[1]
        assert "PREFIX foaf: <http://xmlns.com/foaf/0.1/>" in rendered
        assert "foaf:name" in where_clause
        assert "xmlns.com/foaf" not in where_clause


class TestRootParameter:
    """sqe_parse_to_tree()'s optional root= - gives a caller a stable,
    named identity for the encoded query instead of always minting a
    fresh BNode(), useful once a graph accumulates more than one encoded
    query (via repeated calls sharing one graph=) and a bare
    `?s a sqe:Query` lookup can no longer tell them apart on its own."""

    QUERY_TEXT = "SELECT ?s WHERE { ?s a <http://example.org/Thing> }"

    def test_defaults_to_a_fresh_bnode(self):
        graph, root = sqe_parse_to_tree(self.QUERY_TEXT)
        assert isinstance(root, BNode)

    def test_accepts_a_real_uriref(self):
        my_iri = URIRef("urn:test:query1")
        graph, root = sqe_parse_to_tree(self.QUERY_TEXT, root=my_iri)
        assert root == my_iri
        assert (my_iri, RDF.type, QUERY) in graph

    def test_named_root_round_trips_through_query_and_text(self):
        my_iri = URIRef("urn:test:query1")
        graph, root = sqe_parse_to_tree(self.QUERY_TEXT, root=my_iri)

        reconstructed = sqe_tree_to_query(graph, root)
        assert reconstructed.algebra is not None

        rendered = sqe_tree_to_text(graph, root)
        assert "SELECT ?s" in rendered

    def test_two_named_queries_in_one_shared_graph_stay_distinguishable(self):
        """The real motivating case: a bare `?s a sqe:Query` lookup can't
        tell two accumulated queries apart, but each one's own given IRI
        can."""
        iri1, iri2 = URIRef("urn:test:q1"), URIRef("urn:test:q2")
        graph, root1 = sqe_parse_to_tree(self.QUERY_TEXT, root=iri1)
        graph, root2 = sqe_parse_to_tree(
            "SELECT ?s WHERE { ?s a <http://example.org/Other> }", graph=graph, root=iri2
        )

        assert root1 == iri1 and root2 == iri2
        query_subjects = set(graph.subjects(RDF.type, QUERY))
        assert query_subjects == {iri1, iri2}

        # each one decodes back to its own, distinct query
        q1_text = sqe_tree_to_text(graph, iri1)
        q2_text = sqe_tree_to_text(graph, iri2)
        assert "Thing" in q1_text
        assert "Other" in q2_text


class TestShaclConformance:
    def test_valid_query_conforms(self):
        query_text = PREFIXES + """
            SELECT ?name WHERE {
              ?p foaf:name ?name .
              OPTIONAL { ?p foaf:age ?age }
              FILTER(?age > 18)
            }
        """
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_triple_pattern_missing_predicate_fails(self):
        query_text = PREFIXES + "SELECT ?name WHERE { ?p foaf:name ?name }"
        graph, root = sqe_parse_to_tree(query_text)
        tp = next(graph.subjects(TRIPLE_PATTERN_PREDICATE, None))
        graph.remove((tp, TRIPLE_PATTERN_PREDICATE, None))

        conforms, _report_graph, report_text = sqe_validate(graph)
        assert not conforms


class TestUnboundProjectedVariable:
    """A real sh:sparql constraint on sqe:SelectQueryShape (added 2026-10-15):
    valid SPARQL syntactically - SPARQL allows projecting a variable the
    WHERE clause never binds, it just comes back unbound in every result
    row - but flagged as a SHACL violation here, since it almost always
    signals a typo or an incomplete edit (an "output" with no matching
    "input"). Mirrors salg:noUnboundProjectedVariables' own semantics
    (Filter never binds; OPTIONAL/UNION/BIND do), but as a declarative
    sh:sparql property-path query over sqe:'s own raw tree shape, not a
    custom Python ConstraintComponent - sqe:'s tree needs no algebra
    resolution to answer this, unlike salg:'s resolved Project node.

    sqe_parse_to_tree() itself validates and raises SQEValidationError on
    a non-conforming result (2026-10-15) - these tests exercise that
    raise directly, not a separate sqe_validate() call after a
    successful parse."""

    def test_unbound_projected_variable_fails(self):
        query_text = "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o }"
        with pytest.raises(SQEValidationError) as exc_info:
            sqe_parse_to_tree(query_text)
        assert "z" in exc_info.value.report_text

    def test_all_projected_variables_bound_conforms(self):
        query_text = "SELECT ?s ?o WHERE { ?s <http://example.org/knows> ?o }"
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_bound_only_via_optional_conforms(self):
        query_text = (
            "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o . "
            "OPTIONAL { ?s <http://example.org/age> ?z } }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_bound_only_via_union_conforms(self):
        query_text = (
            "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o . "
            "{ ?s <http://example.org/a> ?z } UNION { ?s <http://example.org/b> ?z } }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_bound_only_via_bind_conforms(self):
        query_text = (
            "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o . BIND(?o AS ?z) }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_filter_alone_does_not_count_as_binding(self):
        """FILTER only ever constrains an already-bound variable - it can
        never bind a new one, so a variable appearing only inside a
        FILTER's own expression still fails, the same as not appearing at
        all."""
        query_text = (
            "SELECT ?s ?z WHERE { ?s <http://example.org/knows> ?o . FILTER(?o = ?z) }"
        )
        with pytest.raises(SQEValidationError) as exc_info:
            sqe_parse_to_tree(query_text)
        assert "z" in exc_info.value.report_text


class TestTemplateListShape:
    """sqe:ConstructQuery's sqe:template had zero structural shape at all
    (added 2026-10-15) - bare sh:minCount/sh:maxCount 1, no sh:node - so
    the whole template could be replaced with a bare string literal and
    still conform. sqe:TemplateListShape closes this the same way
    WhereListShape already does for sqe:where, just restricted to
    sqe:TriplePattern only (CONSTRUCT's own template can never contain
    OPTIONAL/UNION/FILTER/BIND)."""

    def test_valid_construct_conforms(self):
        query_text = (
            "CONSTRUCT { ?s <http://example.org/q> ?o } "
            "WHERE { ?s <http://example.org/p> ?o }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_template_corrupted_to_bare_literal_fails(self):
        query_text = (
            "CONSTRUCT { ?s <http://example.org/q> ?o } "
            "WHERE { ?s <http://example.org/p> ?o }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        graph.set((root, TEMPLATE, Literal("not a list of triple patterns at all")))

        conforms, _report_graph, report_text = sqe_validate(graph)
        assert not conforms


class TestAlternativesListShape:
    """sqe:Union's sqe:alternatives had zero structural shape at all
    (added 2026-10-15) - same bare-cardinality-only gap as sqe:template
    above. Confirmed via an ASK-form query specifically (no sqe:projection
    at all, so no incidental catch via the unbound-projected-variable
    check) that corrupting sqe:alternatives previously went completely
    undetected. sqe:AlternativesListShape closes it: a well-formed
    rdf:List whose own members are themselves well-formed pattern lists
    (sqe:WhereListShape's own type set), checked via a single flat
    SPARQL query (no sh:node self-recursion), not two chained shapes."""

    def test_valid_union_conforms(self):
        query_text = (
            "ASK { { ?s <http://example.org/a> ?o } "
            "UNION { ?s <http://example.org/b> ?o } }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_alternatives_corrupted_fails_even_without_incidental_catch(self):
        query_text = (
            "ASK { { ?s <http://example.org/a> ?o } "
            "UNION { ?s <http://example.org/b> ?o } }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        union_node = next(graph.subjects(RDF.type, UNION))
        graph.set((union_node, UNION_ALTERNATIVES, Literal("garbage, not a list of pattern-lists")))

        conforms, _report_graph, report_text = sqe_validate(graph)
        assert not conforms


class TestPrefixBindingShape:
    """sqe:PrefixBinding (the whole prologue encoding) had zero shape of
    any kind targeting it (added 2026-10-15) - removing sqe:namespace
    entirely and replacing sqe:prefixLabel with a plain integer both
    previously conformed."""

    def test_valid_prefix_conforms(self):
        query_text = "PREFIX ex: <http://example.org/>\nSELECT ?s WHERE { ?s ex:p ?o }"
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_empty_string_default_prefix_conforms(self):
        """The default `:` prefix encodes as the empty string, not absence
        - a real, legal case (see to_rdf.py's own docstring) that must
        not be rejected by the new minCount/datatype constraints."""
        query_text = "PREFIX : <http://example.org/>\nSELECT ?s WHERE { ?s :p ?o }"
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_missing_namespace_fails(self):
        query_text = "PREFIX ex: <http://example.org/>\nSELECT ?s WHERE { ?s ex:p ?o }"
        graph, root = sqe_parse_to_tree(query_text)
        prefix_node = next(graph.subjects(RDF.type, PREFIX_BINDING))
        graph.remove((prefix_node, PREFIX_NAMESPACE, None))

        conforms, _report_graph, report_text = sqe_validate(graph)
        assert not conforms

    def test_non_string_prefix_label_fails(self):
        query_text = "PREFIX ex: <http://example.org/>\nSELECT ?s WHERE { ?s ex:p ?o }"
        graph, root = sqe_parse_to_tree(query_text)
        prefix_node = next(graph.subjects(RDF.type, PREFIX_BINDING))
        graph.set((prefix_node, PREFIX_LABEL, Literal(12345)))

        conforms, _report_graph, report_text = sqe_validate(graph)
        assert not conforms


class TestUnboundExpressionVariable:
    """A second, broader unbound-variable check than
    TestUnboundProjectedVariable above (added 2026-10-15): that one only
    ever inspects sqe:projection's own members (SELECT-specific) - a
    variable referenced only inside a FILTER/BIND expression, that is
    never itself projected, was never checked at all, for any query form.
    This generalizes to "every variable used inside any expression must
    be bound somewhere in scope," reused identically across
    SelectQueryShape/AskQueryShape/ConstructQueryShape."""

    def test_select_filter_unbound_variable_fails(self):
        query_text = (
            "SELECT ?s WHERE { ?s <http://example.org/p> ?o . FILTER(?x > 5) }"
        )
        with pytest.raises(SQEValidationError) as exc_info:
            sqe_parse_to_tree(query_text)
        assert "x" in exc_info.value.report_text

    def test_select_filter_all_bound_conforms(self):
        query_text = (
            "SELECT ?s WHERE { ?s <http://example.org/p> ?o . FILTER(?o > 5) }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_ask_filter_unbound_variable_fails(self):
        query_text = "ASK { ?s <http://example.org/p> ?o . FILTER(?x > 5) }"
        with pytest.raises(SQEValidationError):
            sqe_parse_to_tree(query_text)

    def test_ask_filter_all_bound_conforms(self):
        query_text = "ASK { ?s <http://example.org/p> ?o . FILTER(?o > 5) }"
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text

    def test_construct_filter_unbound_variable_fails(self):
        query_text = (
            "CONSTRUCT { ?s <http://example.org/q> ?o } "
            "WHERE { ?s <http://example.org/p> ?o . FILTER(?x > 5) }"
        )
        with pytest.raises(SQEValidationError):
            sqe_parse_to_tree(query_text)

    def test_bind_then_filter_on_bound_variable_conforms(self):
        """Regression guard: a variable bound via BIND and then used in a
        later FILTER must not be flagged - confirms the reachability
        closure this check shares with the projection check already
        covers BIND targets correctly."""
        query_text = (
            "SELECT ?s WHERE { ?s <http://example.org/p> ?o . "
            "BIND(?o AS ?z) . FILTER(?z > 5) }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text


class TestUnboundTemplateVariable:
    """CONSTRUCT's own sqe:template had no unbound-variable check at all
    (added 2026-10-15) - the direct analog of SelectQueryShape's existing
    sqe:projection check, retargeted at sqe:template's own TriplePattern
    subject/predicate/object variables instead. This is the exact gap
    reported earlier in the same conversation (CONSTRUCT { ?s ex:q ?z }
    conforming while producing zero result triples) - now closed."""

    def test_template_variable_unbound_fails(self):
        query_text = (
            "CONSTRUCT { ?s <http://example.org/q> ?z } "
            "WHERE { ?s <http://example.org/p> ?o }"
        )
        with pytest.raises(SQEValidationError) as exc_info:
            sqe_parse_to_tree(query_text)
        assert "z" in exc_info.value.report_text

    def test_template_variable_bound_conforms(self):
        query_text = (
            "CONSTRUCT { ?s <http://example.org/q> ?o } "
            "WHERE { ?s <http://example.org/p> ?o }"
        )
        graph, root = sqe_parse_to_tree(query_text)
        conforms, _report_graph, report_text = sqe_validate(graph)
        assert conforms, report_text


from starlayer.sparql.sqe import vocab as V  # noqa: E402


class TestShapesForTheWiderVocabulary:
    """Each of these corruptions was accepted before the list shapes were added."""

    QUERY = (
        "PREFIX ex: <http://x/> SELECT ?s (COUNT(?o) AS ?c) WHERE { ?s ex:p ?o } GROUP BY ?s HAVING (COUNT(?o) > 0) "
        "VALUES ?o { 1 2 }"
    )

    def _corrupted(self, predicate_local, find_node):
        from rdflib import Literal
        from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_validate
        from starlayer.sparql.sqe.vocab import SQE

        tree, _root = sqe_parse_to_tree(self.QUERY)
        node = find_node(tree)
        predicate = SQE[predicate_local]
        tree.remove((node, predicate, None))
        tree.add((node, predicate, Literal("JUNK")))
        return sqe_validate(tree)[0]

    def test_group_by_must_be_a_list(self):
        assert not self._corrupted("groupBy", lambda t: next(t.subjects(V.GROUP_BY)))

    def test_having_must_be_a_list(self):
        assert not self._corrupted("having", lambda t: next(t.subjects(V.HAVING)))

    def test_trailing_values_must_be_a_values_block(self):
        assert not self._corrupted("values", lambda t: next(t.subjects(V.QUERY_VALUES)))

    def test_values_vars_must_be_a_list(self):
        assert not self._corrupted("vars", lambda t: next(t.subjects(V.VALUES_VARS)))

    def test_values_rows_must_be_a_list(self):
        assert not self._corrupted("rows", lambda t: next(t.subjects(V.VALUES_ROWS)))

    def test_projection_must_be_a_list(self):
        assert not self._corrupted("projection", lambda t: next(t.subjects(V.PROJECTION)))

    def test_shared_properties_declare_no_domain(self):
        """sqe:expr, var, subject, predicate and object are used by several node types; a domain would give
        an Alias the type Filter (and a TripleTerm the type TriplePattern) under RDFS inference."""
        from rdflib import RDFS
        from starlayer import starontology

        ontology = starontology.get_ontology_graph("sqe_owl")
        from starlayer.sparql.sqe.vocab import SQE

        for name in ("expr", "var", "subject", "predicate", "object"):
            assert (SQE[name], RDFS.domain, None) not in ontology, name

