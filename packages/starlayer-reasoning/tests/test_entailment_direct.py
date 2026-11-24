"""
tests/unit/test_entailment_direct.py

Coverage for StarLayerGraph.query(..., entailment=ENTAILMENT['OWL-Direct']) - the
query-time counterpart to StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine=...):
query() a throwaway copy of the store plus the entailed triples, which the graph keeps between calls
(recompute= says when they are computed again), as for entailment=ENTAILMENT['OWL-RDF-Based'].

`owlready2`/`rustdl` are both optional extras of this package (`pip install
starlayer-reasoning[hermit]`/`[rustdl]`) - the skip markers below are copied
locally rather than imported from test_infer_owl_dl.py/test_infer_owl_dl_rustdl.py,
matching those two files' own precedent of each keeping its own copy rather
than sharing markers across files.
"""

import shutil

import pyoxigraph as ox
import pytest
from starlayer.graph import RDF, Namespace, StarLayerDataset, StarLayerGraph
from starlayer.graph.entailment import ENTAILMENT
from starlayer.graph.entailment import infer as ent
from starlayer.graph.execution import union
from starlayer_reasoning.owl_dl import InconsistentOntologyError

try:
    import owlready2  # noqa: F401
    _OWLREADY2_AVAILABLE = True
except ImportError:
    _OWLREADY2_AVAILABLE = False

try:
    import rustdl  # noqa: F401
    _RUSTDL_AVAILABLE = True
except ImportError:
    _RUSTDL_AVAILABLE = False

owl_dl_extra = pytest.mark.skipif(
    not _OWLREADY2_AVAILABLE,
    reason='owlready2 not importable - it is an optional extra of this package; '
           'install with: pip install starlayer-reasoning[hermit]',
)

java_required = pytest.mark.skipif(
    shutil.which("java") is None,
    reason='no Java runtime on PATH — owlready2\'s HermiT reasoner needs a JVM '
           '(e.g. `brew install openjdk` on macOS)',
)

rustdl_extra = pytest.mark.skipif(
    not _RUSTDL_AVAILABLE,
    reason='rustdl not importable - it is an optional extra of this package; '
           'install with: pip install starlayer-reasoning[rustdl]',
)

EX = Namespace("http://example.org/")

_Q_WOMAN = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Woman }"


def _disjunctive_graph():
    # Same oracle fixture as test_infer_owl_dl.py's own disjunctive-entailment
    # test - owlrl's forward-chaining rule engine structurally cannot derive
    # this, so a correct result here proves entailment=ENTAILMENT['OWL-Direct'] is doing
    # genuine DL reasoning at query time, not something entailment=ENTAILMENT['OWL-RDF-Based']
    # could already answer.
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Man owl:disjointWith ex:Woman .
        ex:Person rdfs:subClassOf [ owl:unionOf ( ex:Man ex:Woman ) ] .
        ex:alice a ex:Person, [ owl:complementOf ex:Man ] .
    """, format="turtle12")
    return g


@owl_dl_extra
@java_required
class TestEntailmentDirect:
    def test_direct_entailment_answers_disjunctive_query(self):
        g = _disjunctive_graph()
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct']))
        assert [r.x.value for r in rows] == [EX.alice.value]

    def test_engine_kwarg_rejected_for_other_entailment(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="only meaningful for entailment="):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-RDF-Based'], engine="rustdl")

    def test_timeout_kwarg_rejected_for_other_entailment(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="only meaningful for entailment="):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-RDF-Based'], timeout=5)

    def test_tiny_timeout_raises_reasoning_timeout_error(self):
        from starlayer_reasoning._timeout import ReasoningTimeoutError

        g = _disjunctive_graph()
        with pytest.raises(ReasoningTimeoutError):
            list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], timeout=0.001))

    def test_inconsistent_ontology_propagates(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man, ex:Woman .
        """, format="turtle12")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Man }"
        with pytest.raises(InconsistentOntologyError):
            list(g.query(q, entailment=ENTAILMENT['OWL-Direct']))

    def test_direct_entailment_is_accepted_on_an_empty_graph(self):
        # The regime is dispatched (no NotImplementedError) and an empty graph has no answers.
        assert list(StarLayerGraph().query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'])) == []


@rustdl_extra
class TestEntailmentDirectRustdl:
    def test_engine_rustdl_selectable_via_query(self):
        g = _disjunctive_graph()
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], engine="rustdl"))
        assert [r.x.value for r in rows] == [EX.alice.value]


@owl_dl_extra
@java_required
class TestEntailmentDirectRecomputeArgumentWithHermit:
    """With the real reasoner: every ``recompute=`` value gives the right answer, and a write is seen."""

    @pytest.mark.parametrize("recompute", ["always", "never", "onChange"])
    def test_every_documented_value_gives_the_same_answer(self, recompute):
        g = _disjunctive_graph()
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], recompute=recompute))
        assert [r.x.value for r in rows] == [EX.alice.value]

    def test_a_mutation_is_seen_by_the_next_query(self):
        g = _disjunctive_graph()
        list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], recompute="onChange"))
        g.add((EX.carol, RDF.type, EX.Person))
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], recompute="onChange"))
        assert [r.x.value for r in rows] == [EX.alice.value]

    def test_an_unknown_value_is_rejected(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="recompute must be one of"):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], recompute="sometimes")


_ALICE, _WOMAN = ox.NamedNode(EX.alice.value), ox.NamedNode(EX.Woman.value)
_REGIMES = [ENTAILMENT["OWL-Direct"], ENTAILMENT["OWL-RDF-Based"]]


@pytest.fixture
def calls(monkeypatch):
    """A stub reasoner that entails ``ex:alice a ex:Woman`` (so no Java or owlrl is needed) and records each time it is asked."""
    asked = []

    def fake(g, regimes, engine, timeout):
        asked.append((next(iter(regimes)), engine))
        return {(_ALICE, ox.NamedNode(RDF.type.value), _WOMAN)}

    monkeypatch.setattr(ent, "_delta_for", fake)
    return asked


class TestEntailedTriplesAreKept:  # the copy of the store with the entailed triples added
    @staticmethod
    def _graph():
        g = StarLayerGraph()
        g.add((EX.bob, RDF.type, EX.Person))
        return g

    @staticmethod
    def _who(g, **kw):
        return sorted(r.x.value for r in g.query(_Q_WOMAN, **kw))

    @pytest.mark.parametrize("regime", _REGIMES)
    def test_an_unchanged_graph_is_reasoned_about_once(self, calls, regime):
        g = self._graph()
        assert self._who(g, entailment=regime) == [EX.alice.value]
        assert self._who(g, entailment=regime) == [EX.alice.value]
        assert len(calls) == 1

    @pytest.mark.parametrize("regime", _REGIMES)
    def test_changed_reasons_again_after_a_write(self, calls, regime):
        g = self._graph()
        self._who(g, entailment=regime, recompute="onChange")
        g.add((EX.carol, RDF.type, EX.Person))
        self._who(g, entailment=regime, recompute="onChange")
        assert len(calls) == 2

    @pytest.mark.parametrize("regime", _REGIMES)
    def test_always_reasons_on_every_call(self, calls, regime):
        g = self._graph()
        for _ in range(3):
            self._who(g, entailment=regime, recompute="always")
        assert len(calls) == 3

    def test_never_reuses_the_kept_copy_data_included(self, calls):
        g = self._graph()
        regime = ENTAILMENT["OWL-Direct"]
        self._who(g, entailment=regime, recompute="never")
        g.add((EX.carol, RDF.type, EX.Woman))
        assert self._who(g, entailment=regime, recompute="never") == [EX.alice.value]  # the copy as it was made, without carol
        assert len(calls) == 1

    def test_each_engine_and_regime_has_its_own_kept_triples(self, calls):
        g = self._graph()
        direct = ENTAILMENT["OWL-Direct"]
        self._who(g, entailment=direct, engine="hermit")
        self._who(g, entailment=direct, engine="rustdl")
        self._who(g, entailment=direct, engine="hermit")
        self._who(g, entailment=ENTAILMENT["OWL-RDF-Based"])
        assert calls == [(direct.value, "hermit"), (direct.value, "rustdl"), (ENTAILMENT["OWL-RDF-Based"].value, "hermit")]

    def test_a_write_on_the_raw_store_counts_once_it_was_handed_out(self, calls):
        g = self._graph()
        regime = ENTAILMENT["OWL-Direct"]
        self._who(g, entailment=regime)
        g.as_store()
        self._who(g, entailment=regime)
        assert len(calls) == 2

    def test_the_graph_itself_never_holds_the_entailed_triples(self, calls):
        g = self._graph()
        before = set(g.triples())
        self._who(g, entailment=ENTAILMENT["OWL-Direct"])
        assert set(g.triples()) == before

    def test_a_dataset_keeps_them_too(self, calls):
        d = StarLayerDataset()
        d.add((EX.bob, RDF.type, EX.Person))
        regime = ENTAILMENT["OWL-Direct"]
        assert self._who(d, entailment=regime) == [EX.alice.value]
        assert self._who(d, entailment=regime) == [EX.alice.value]
        assert len(calls) == 1


class TestClearEntailmentCache:
    @staticmethod
    def _graph():
        g = StarLayerGraph()
        g.add((EX.bob, RDF.type, EX.Person))
        return g

    @staticmethod
    def _who(g, **kw):
        return sorted(r.x.value for r in g.query(_Q_WOMAN, **kw))

    @pytest.mark.parametrize("regime", _REGIMES)
    def test_the_next_query_reasons_again_after_clearing(self, calls, regime):
        g = self._graph()
        self._who(g, entailment=regime)
        self._who(g, entailment=regime)
        assert len(calls) == 1
        assert g.clear_entailment_cache() is g
        self._who(g, entailment=regime)
        assert len(calls) == 2

    def test_a_cleared_cache_reads_the_current_data_even_for_never(self, calls):
        g = self._graph()
        regime = ENTAILMENT["OWL-Direct"]
        self._who(g, entailment=regime, recompute="never")
        g.add((EX.carol, RDF.type, EX.Woman))
        assert self._who(g, entailment=regime, recompute="never") == [EX.alice.value]
        g.clear_entailment_cache()
        assert self._who(g, entailment=regime, recompute="never") == [EX.alice.value, EX.carol.value]

    def test_clearing_drops_every_regime_and_engine(self, calls):
        g = self._graph()
        direct = ENTAILMENT["OWL-Direct"]
        self._who(g, entailment=direct, engine="hermit")
        self._who(g, entailment=direct, engine="rustdl")
        self._who(g, entailment=ENTAILMENT["OWL-RDF-Based"])
        assert len(union.version_of(g.store).entailed.entries) == 3
        g.clear_entailment_cache()
        assert not union.version_of(g.store).entailed.entries

    def test_clearing_a_graph_with_nothing_kept_does_nothing(self, calls):
        g = self._graph()
        assert g.clear_entailment_cache() is g

    def test_a_dataset_clears_too(self, calls):
        d = StarLayerDataset()
        d.add((EX.bob, RDF.type, EX.Person))
        regime = ENTAILMENT["OWL-Direct"]
        self._who(d, entailment=regime)
        d.clear_entailment_cache()
        self._who(d, entailment=regime)
        assert len(calls) == 2
