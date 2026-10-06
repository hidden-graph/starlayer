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
from rdflib.plugins.sparql.evaluate import evalQuery
from rdflib.plugins.sparql.processor import prepareQuery

from starlayer.sparql.sqe import (
    sqe_parse_to_tree,
    sqe_tree_to_query,
    sqe_tree_to_text,
    sqe_validate,
)
from starlayer.sparql.sqe.vocab import TRIPLE_PATTERN_PREDICATE

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
        assert "sqe:predicate" in report_text
