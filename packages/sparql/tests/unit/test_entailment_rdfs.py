"""
tests/unit/test_entailment_rdfs.py

Coverage for starsparql.entailment_rdfs.rewrite_algebra_for_rdfs - the
query-time RDFS rewrite, independent of StarLayerGraph's own entailment=
wiring (see packages/graph/tests/unit/test_entailment.py for that
end-to-end coverage).

Per this project's own testing discipline (this package's own CLAUDE.md:
"any new query/update shape needs an execution-comparison test, not just a
structural one"), most tests compare rewritten-query results directly
against owlrl.RDFS_Semantics run on the same data - owlrl is the oracle.
Two known, deliberate divergences from raw owlrl output are documented and
tested explicitly rather than papered over (see the module docstring in
entailment_rdfs.py): this rewrite's subClassOf*/subPropertyOf* reflexivity
is unconditional (a superset of owlrl's stricter "only if explicitly typed
rdfs:Class/rdf:Property" reflexivity - rdfs6/rdfs10), and it deliberately
excludes the "vocabulary-level" rules (rdfs4a/4b/8/12/13, the ~30 fixed
axiomatic triples) that account for most of a real RDFS closure's size
without answering any actual question about the data.
"""

from rdflib import RDF, RDFS, Graph, Namespace
from rdflib.plugins.sparql import prepareQuery

import pytest

from starsparql.entailment_rdfs import rewrite_algebra_for_rdfs

try:
    import owlrl
    _OWLRL_AVAILABLE = True
except ImportError:
    _OWLRL_AVAILABLE = False

owlrl_extra = pytest.mark.skipif(not _OWLRL_AVAILABLE, reason="owlrl not installed")

EX = Namespace("http://example.org/")


def _query(graph: Graph, text: str):
    q = prepareQuery(text, initNs={"ex": EX, "rdfs": RDFS, "rdf": RDF})
    rewrite_algebra_for_rdfs(q.algebra)
    return graph.query(q)


def _materialize(*triples) -> Graph:
    g = Graph()
    for t in triples:
        g.add(t)
    owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
    return g


class TestSubClassOf:
    def test_no_rewrite_misses_the_subclass_fact(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.alice, RDF.type, EX.Manager))
        rows = list(g.query(prepareQuery(
            "SELECT ?x WHERE { ?x a ex:Employee }", initNs={"ex": EX})))
        assert rows == []

    def test_multi_hop_transitivity(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.Employee, RDFS.subClassOf, EX.Person))
        g.add((EX.alice, RDF.type, EX.Manager))
        rows = _query(g, "SELECT ?x WHERE { ?x a ex:Person }")
        assert [str(r.x) for r in rows] == [str(EX.alice)]

    def test_variable_type_yields_every_reachable_class(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.alice, RDF.type, EX.Manager))
        rows = _query(g, "SELECT ?x WHERE { ex:alice a ?x }")
        assert {str(r.x) for r in rows} == {str(EX.Manager), str(EX.Employee)}

    @owlrl_extra
    def test_matches_owlrl_oracle(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.Employee, RDFS.subClassOf, EX.Person))
        g.add((EX.alice, RDF.type, EX.Manager))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ?x a ex:Person }")}
        oracle = _materialize(
            (EX.Manager, RDFS.subClassOf, EX.Employee),
            (EX.Employee, RDFS.subClassOf, EX.Person),
            (EX.alice, RDF.type, EX.Manager),
        )
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Person)}
        assert rewritten == materialized == {str(EX.alice)}


class TestSubClassOfAsQueryPredicate:
    def test_transitivity_when_subclassof_is_the_query_predicate(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.Employee, RDFS.subClassOf, EX.Person))
        rows = _query(g, "SELECT ?x WHERE { ex:Manager rdfs:subClassOf ?x }")
        # includes Manager itself too - reflexivity, see the dedicated test below
        assert {str(r.x) for r in rows} == {str(EX.Manager), str(EX.Employee), str(EX.Person)}

    def test_reflexivity_is_unconditional_a_documented_superset_of_owlrl(self):
        # Manager is never typed rdfs:Class here - owlrl's own rdfs10 would
        # NOT entail Manager subClassOf Manager for this data (confirmed
        # live against owlrl directly), but this rewrite's reflexivity is
        # unconditional by design (see entailment_rdfs.py's module
        # docstring) - Manager shows up in its own result.
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        rows = _query(g, "SELECT ?x WHERE { ex:Manager rdfs:subClassOf ?x }")
        assert str(EX.Manager) in {str(r.x) for r in rows}


@owlrl_extra
class TestDomainAndRange:
    def test_domain_entailment(self):
        g = Graph()
        g.add((EX.worksAt, RDFS.domain, EX.Person))
        g.add((EX.alice, EX.worksAt, EX.Acme))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ?x a ex:Person }")}
        oracle = _materialize((EX.worksAt, RDFS.domain, EX.Person), (EX.alice, EX.worksAt, EX.Acme))
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Person)}
        assert rewritten == materialized == {str(EX.alice)}

    def test_range_entailment(self):
        g = Graph()
        g.add((EX.worksAt, RDFS.range, EX.Organization))
        g.add((EX.alice, EX.worksAt, EX.Acme))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ?x a ex:Organization }")}
        oracle = _materialize((EX.worksAt, RDFS.range, EX.Organization), (EX.alice, EX.worksAt, EX.Acme))
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Organization)}
        assert rewritten == materialized == {str(EX.Acme)}

    def test_domain_composes_with_subclass_chain(self):
        g = Graph()
        g.add((EX.worksAt, RDFS.domain, EX.Person))
        g.add((EX.Person, RDFS.subClassOf, EX.Agent))
        g.add((EX.alice, EX.worksAt, EX.Acme))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ?x a ex:Agent }")}
        oracle = _materialize(
            (EX.worksAt, RDFS.domain, EX.Person),
            (EX.Person, RDFS.subClassOf, EX.Agent),
            (EX.alice, EX.worksAt, EX.Acme),
        )
        materialized = {str(s) for s in oracle.subjects(RDF.type, EX.Agent)}
        assert rewritten == materialized == {str(EX.alice)}


@owlrl_extra
class TestSubPropertyOf:
    def test_subproperty_entailment(self):
        g = Graph()
        g.add((EX.hasParent, RDFS.subPropertyOf, EX.hasRelative))
        g.add((EX.alice, EX.hasParent, EX.bob))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ex:alice ex:hasRelative ?x }")}
        oracle = _materialize(
            (EX.hasParent, RDFS.subPropertyOf, EX.hasRelative), (EX.alice, EX.hasParent, EX.bob)
        )
        materialized = {str(o) for o in oracle.objects(EX.alice, EX.hasRelative)}
        assert rewritten == materialized == {str(EX.bob)}

    def test_subproperty_transitivity_when_subpropertyof_is_the_query_predicate(self):
        g = Graph()
        g.add((EX.hasParent, RDFS.subPropertyOf, EX.hasAncestor))
        g.add((EX.hasAncestor, RDFS.subPropertyOf, EX.hasRelative))
        rows = _query(g, "SELECT ?x WHERE { ex:hasParent rdfs:subPropertyOf ?x }")
        # includes hasParent itself too - reflexivity, same as subClassOf
        assert {str(r.x) for r in rows} == {str(EX.hasParent), str(EX.hasAncestor), str(EX.hasRelative)}

    def test_two_hop_subproperty_entailment(self):
        g = Graph()
        g.add((EX.hasParent, RDFS.subPropertyOf, EX.hasAncestor))
        g.add((EX.hasAncestor, RDFS.subPropertyOf, EX.hasRelative))
        g.add((EX.alice, EX.hasParent, EX.bob))

        rewritten = {str(r.x) for r in _query(g, "SELECT ?x WHERE { ex:alice ex:hasRelative ?x }")}
        oracle = _materialize(
            (EX.hasParent, RDFS.subPropertyOf, EX.hasAncestor),
            (EX.hasAncestor, RDFS.subPropertyOf, EX.hasRelative),
            (EX.alice, EX.hasParent, EX.bob),
        )
        materialized = {str(o) for o in oracle.objects(EX.alice, EX.hasRelative)}
        assert rewritten == materialized == {str(EX.bob)}


class TestDeliberateExclusions:
    """The rewrite does NOT chase the "vocabulary-level" rules - see
    entailment_rdfs.py's module docstring for why. These tests pin that
    scope down explicitly, rather than leaving it as an implicit gap a
    future change could silently widen or narrow without anyone noticing.
    """

    def test_does_not_entail_universal_rdfs_resource_typing(self):
        g = Graph()
        g.add((EX.alice, EX.knows, EX.bob))
        rows = _query(g, "SELECT ?x WHERE { ?x a rdfs:Resource }")
        assert list(rows) == []

    def test_does_not_entail_rdf_property_typing_for_used_predicates(self):
        g = Graph()
        g.add((EX.alice, EX.knows, EX.bob))
        rows = _query(g, "SELECT ?x WHERE { ?x a rdf:Property }")
        assert list(rows) == []


class TestMixedQuery:
    def test_rewrite_composes_with_an_ordinary_join_in_the_same_query(self):
        g = Graph()
        g.bind("ex", EX)
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.alice, RDF.type, EX.Manager))
        g.add((EX.alice, EX.name, __import__("rdflib").Literal("Alice")))

        rows = _query(g, 'SELECT ?name WHERE { ?x a ex:Employee . ?x ex:name ?name }')
        assert [str(r.name) for r in rows] == ["Alice"]

    def test_idempotent_on_a_second_rewrite(self):
        g = Graph()
        g.add((EX.Manager, RDFS.subClassOf, EX.Employee))
        g.add((EX.alice, RDF.type, EX.Manager))
        q = prepareQuery("SELECT ?x WHERE { ?x a ex:Employee }", initNs={"ex": EX})
        rewrite_algebra_for_rdfs(q.algebra)
        rewrite_algebra_for_rdfs(q.algebra)
        assert [str(r.x) for r in g.query(q)] == [str(EX.alice)]
