"""Tests for starlayer.sparql.StarQuery - binds a SPARQL query (prepared
once) plus StarLayerGraph.query()'s own per-call options, so the same
query can run against several different graphs without repeating them.
"""

from starlayer.graph import Namespace, StarLayerGraph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.sparql import StarQuery

EX = Namespace("http://example.org/")


def _graph(data: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.parse(data=data, format="turtle")
    return g


class TestRunsAgainstDifferentGraphs:
    def test_same_query_runs_against_two_different_graphs(self):
        g1 = _graph("@prefix ex: <http://example.org/> . ex:alice ex:worksFor ex:Acme .")
        g2 = _graph("@prefix ex: <http://example.org/> . ex:bob ex:worksFor ex:Globex .")

        q = StarQuery("SELECT ?s WHERE { ?s ex:worksFor ?o }", initNs={"ex": EX})
        assert {str(r.s) for r in q.run(g1)} == {str(EX.alice)}
        assert {str(r.s) for r in q.run(g2)} == {str(EX.bob)}

    def test_prepares_only_once(self):
        """The whole point - prepare_query_12 runs at construction, not on
        every run() call. Confirmed by swapping in a spy and counting."""
        import starlayer.sparql.star_query as star_query_mod

        calls = []
        real = star_query_mod.prepare_query_12

        def spy(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        star_query_mod.prepare_query_12 = spy
        try:
            q = StarQuery("SELECT ?s WHERE { ?s ?p ?o }")
            assert len(calls) == 1
            q.run(_graph("@prefix ex: <http://example.org/> . ex:a ex:b ex:c ."))
            q.run(_graph("@prefix ex: <http://example.org/> . ex:x ex:y ex:z ."))
            assert len(calls) == 1
        finally:
            star_query_mod.prepare_query_12 = real


class TestEntailmentBinding:
    def _graph_with_subclass(self):
        return _graph(
            """
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Manager rdfs:subClassOf ex:Employee .
            ex:carol a ex:Manager .
            """
        )

    def test_bound_entailment_used_by_default(self):
        g = self._graph_with_subclass()
        q = StarQuery("SELECT ?s WHERE { ?s a ex:Employee }", initNs={"ex": EX}, entailment=ENTAILMENT.RDFS)
        assert {str(r.s) for r in q.run(g)} == {str(EX.carol)}

    def test_per_call_override_does_not_disturb_the_bound_value(self):
        g = self._graph_with_subclass()
        q = StarQuery("SELECT ?s WHERE { ?s a ex:Employee }", initNs={"ex": EX}, entailment=ENTAILMENT.RDFS)
        assert list(q.run(g, entailment=None)) == []
        # bound value still intact for the next call with no override
        assert {str(r.s) for r in q.run(g)} == {str(EX.carol)}

    def test_repeated_calls_with_bound_entailment_stay_correct(self):
        """Regression guard for the real bug this class works around (see
        its own module docstring): entailment=RDF/RDFS only rewrites a
        query's algebra when given as text, never when given an already-
        prepared Query object. A naive "prepare once, reuse the prepared
        object" implementation would silently stop applying entailment -
        confirmed empirically to fail silently (empty results, no error)
        before this class's run() picked text vs. prepared object based on
        the effective entailment. Calling run() twice guards against a
        once-only accidental pass too."""
        g = self._graph_with_subclass()
        q = StarQuery("SELECT ?s WHERE { ?s a ex:Employee }", initNs={"ex": EX}, entailment=ENTAILMENT.RDFS)
        assert {str(r.s) for r in q.run(g)} == {str(EX.carol)}
        assert {str(r.s) for r in q.run(g)} == {str(EX.carol)}

    def test_entailment_override_to_a_different_regime(self):
        g = self._graph_with_subclass()
        q = StarQuery("SELECT ?s WHERE { ?s a ex:Employee }", initNs={"ex": EX}, entailment=ENTAILMENT.RDFS)
        rows = q.run(g, entailment=ENTAILMENT["OWL-RDF-Based"])
        assert {str(r.s) for r in rows} == {str(EX.carol)}
