"""
tests/unit/test_entailment_rdf.py

Coverage for starsparql.entailment_rdf.rewrite_algebra_for_rdf - the
query-time RDF entailment rewrite (rdfD2 only - see the module's own
docstring), independent of StarLayerGraph's own entailment= wiring (see
packages/graph/tests/unit/test_entailment.py for that end-to-end coverage).

Per this project's own testing discipline (this package's own CLAUDE.md:
"any new query/update shape needs an execution-comparison test, not just a
structural one"), the oracle test compares rewritten-query results against
rdfD2's own direct definition ("every predicate used anywhere in the
graph") rather than owlrl.RDFS_Semantics's full closure - see
test_matches_the_direct_definition_of_rdfD2's own comment for why that
closure isn't actually a clean oracle for this one isolated rule.
"""

from rdflib import RDF, Graph, Namespace
from rdflib.plugins.sparql import prepareQuery

from starsparql.entailment_rdf import rewrite_algebra_for_rdf

EX = Namespace("http://example.org/")


def _query(graph: Graph, text: str):
    q = prepareQuery(text, initNs={"ex": EX, "rdf": RDF})
    rewrite_algebra_for_rdf(q.algebra)
    return graph.query(q)


class TestPredicateIsProperty:
    def test_no_rewrite_misses_the_fact(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = list(g.query(prepareQuery(
            "SELECT ?p WHERE { ?p a rdf:Property }", initNs={"rdf": RDF})))
        assert rows == []

    def test_predicate_used_anywhere_is_entailed_a_property(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = _query(g, "SELECT ?p WHERE { ?p a rdf:Property }")
        assert [str(r.p) for r in rows] == [str(EX.worksAt)]

    def test_multiple_distinct_predicates(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        g.add((EX.alice, EX.knows, EX.bob))
        rows = _query(g, "SELECT ?p WHERE { ?p a rdf:Property }")
        assert {str(r.p) for r in rows} == {str(EX.worksAt), str(EX.knows)}

    def test_bound_subject_as_boolean_style_check(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = _query(g, "SELECT ?x WHERE { ex:worksAt a rdf:Property . BIND(1 AS ?x) }")
        assert [str(r.x) for r in rows] == ["1"]
        rows = _query(g, "SELECT ?x WHERE { ex:knows a rdf:Property . BIND(1 AS ?x) }")
        assert list(rows) == []

    def test_literally_asserted_fact_still_matches(self):
        # the literal branch of the rewrite - not just the "used as a
        # predicate" branch - still works. Note rdf:type itself is also
        # correctly entailed here: this very triple uses rdf:type as its
        # own predicate, which rdfD2 applies to just as much as any other.
        g = Graph()
        g.add((EX.worksAt, RDF.type, RDF.Property))
        rows = _query(g, "SELECT ?p WHERE { ?p a rdf:Property }")
        assert {str(r.p) for r in rows} == {str(EX.worksAt), str(RDF.type)}

    def test_composes_correctly_with_an_unrelated_join(self):
        # ex:name is itself a valid ?p binding too (it's used as a
        # predicate in the second triple), so the correct result is the
        # full cross product with the unrelated ex:alice ex:name ?n join -
        # not just the "obvious" ex:worksAt row.
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        g.add((EX.alice, EX.name, EX.Alice))
        rows = _query(
            g,
            "SELECT ?p ?n WHERE { ?p a rdf:Property . ex:alice ex:name ?n }",
        )
        assert {(str(r.p), str(r.n)) for r in rows} == {
            (str(EX.worksAt), str(EX.Alice)),
            (str(EX.name), str(EX.Alice)),
        }

    def test_matches_the_direct_definition_of_rdfD2(self):
        # rdfD2's ground truth is simply "every predicate used anywhere in
        # the graph" - a direct, independent check, not owlrl's full RDFS
        # closure: that closure isn't a clean oracle for this one isolated
        # rule, since owlrl's own rdfs6 (subPropertyOf reflexivity) adds
        # `P rdfs:subPropertyOf P` for every property P as part of
        # computing the closure, and that newly-added triple itself uses
        # rdfs:subPropertyOf as a predicate - feeding back into more
        # rdf:Property entailments this one-shot, non-iterative rewrite
        # deliberately does not chase (confirmed live: comparing against
        # owlrl.RDFS_Semantics's full closure here picks up rdf:type and
        # rdfs:subPropertyOf as spurious extras, neither of which rdfD2
        # applied to the original, un-closed data would entail).
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        g.add((EX.alice, EX.knows, EX.bob))

        rewritten = {str(r.p) for r in _query(g, "SELECT ?p WHERE { ?p a rdf:Property }")}
        ground_truth = {str(p) for _, p, _ in g}

        assert rewritten == ground_truth == {str(EX.worksAt), str(EX.knows)}


class TestScopingBoundary:
    def test_variable_object_type_query_is_not_rewritten(self):
        # rdfD2 is a single fixed axiom about one specific class - a
        # generic ?p rdf:type ?class query has no principled bounded
        # rewrite (see module docstring) and must be left untouched.
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = list(_query(g, "SELECT ?p ?c WHERE { ?p a ?c }"))
        assert rows == []

    def test_class_other_than_property_is_not_rewritten(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = list(_query(g, "SELECT ?p WHERE { ?p a ex:SomeOtherClass }"))
        assert rows == []

    def test_idempotent_on_a_second_pass(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        q = prepareQuery("SELECT ?p WHERE { ?p a rdf:Property }", initNs={"rdf": RDF})
        rewrite_algebra_for_rdf(q.algebra)
        rewrite_algebra_for_rdf(q.algebra)  # second pass, same tree
        rows = list(g.query(q))
        assert [str(r.p) for r in rows] == [str(EX.worksAt)]
