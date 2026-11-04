"""Migrated from tests/sparql/unit/test_entailment_rdf.py: the same tests, on an ``OxGraph``, with the query-time rewrite of
``starlayer.sparql.sqe.entailment`` (text in, text out, Oxigraph evaluates) instead of the rdflib-algebra rewrite. Differences from
the original are listed in the module docstring of ``tests/graph/oxgraph/test_entailment_query.py``.
"""

from rdflib import RDF, Namespace
from starlayer.graph.oxgraph import OxGraph
from starlayer.graph.oxgraph.helpers.entailment import ENTAILMENT
from starlayer.sparql.sqe.entailment import rewrite_for_entailment

_REGIME = ENTAILMENT.RDF


class _Row(tuple):
    """A result row as the rdflib one was: a tuple of the values (as strings) with attribute access by variable name."""

    def __new__(cls, row, names):
        self = super().__new__(cls, (getattr(row[n], "value", row[n]) if row[n] is not None else None for n in names))
        self._names = names
        return self

    def __getattr__(self, name):
        if name.startswith("_") or name not in self._names:
            raise AttributeError(name)
        return self[self._names.index(name)]


def _rows(res):
    names = [str(getattr(v, "value", v)) for v in res.vars]
    return [_Row(r, names) for r in res]


class _Prepared:
    def __init__(self, text, initNs):
        self.text, self.ns = text, initNs


def prepareQuery(text, initNs=None):  # noqa: N802
    return _Prepared(text, initNs)


def Graph():  # noqa: N802
    return OxGraph()


def _run(graph, text, regime, ns):
    ns = {k: str(v) for k, v in (ns or {}).items()}
    res = graph.query(text, initNs=ns, entailment=regime)
    return res if res.type == "ASK" else _rows(res)


def _plain(graph, q):
    ns = {k: str(v) for k, v in (q.ns or {}).items()}
    return _rows(graph.query(q.text, initNs=ns))

EX = Namespace("http://example.org/")


def _query(graph, text: str):
    return _run(graph, text, _REGIME, {"ex": EX, "rdf": RDF})


class TestPredicateIsProperty:
    def test_no_rewrite_misses_the_fact(self):
        g = Graph()
        g.add((EX.alice, EX.worksAt, EX.Acme))
        rows = list(_plain(g, prepareQuery(
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
        ground_truth = {p.value for _, p, _ in g}

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
        q.text = rewrite_for_entailment(rewrite_for_entailment(q.text, _REGIME, prefixes={k: str(v) for k, v in q.ns.items()}), _REGIME)
        rows = _rows(g.query(q.text))
        # A second pass nests the first pass's union once more, which is the same answer set. The row count used to be
        # one only because rdflib's non-lazy join de-duplicated its right side (see upstream-issues 33), so compare
        # the set of answers.
        assert {str(r.p) for r in rows} == {str(EX.worksAt)}
