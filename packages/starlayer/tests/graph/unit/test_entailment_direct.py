"""
tests/unit/test_entailment_direct.py

Coverage for StarLayerGraph.query(..., entailment=ENTAILMENT['OWL-Direct']) - the
query-time counterpart to StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine=...):
query() a throwaway copy of the store closed by infer(); the closure is computed on every call, as
for entailment=ENTAILMENT['OWL-RDF-Based'] (see test_entailment.py).

`owlready2`/`rustdl` are both optional extras of this package (`pip install
starlayer[hermit]`/`[rustdl]`) - the skip markers below are copied
locally rather than imported from test_infer_owl_dl.py/test_infer_owl_dl_rustdl.py,
matching those two files' own precedent of each keeping its own copy rather
than sharing markers across files.
"""

import shutil

import pytest
from rdflib import RDF, Namespace
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.graph.owl_dl import InconsistentOntologyError
from starlayer.graph.oxgraph import StarLayerGraph

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
           'install with: pip install starlayer[hermit]',
)

java_required = pytest.mark.skipif(
    shutil.which("java") is None,
    reason='no Java runtime on PATH — owlready2\'s HermiT reasoner needs a JVM '
           '(e.g. `brew install openjdk` on macOS)',
)

rustdl_extra = pytest.mark.skipif(
    not _RUSTDL_AVAILABLE,
    reason='rustdl not importable - it is an optional extra of this package; '
           'install with: pip install starlayer[rustdl]',
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
        assert [r.x.value for r in rows] == [str(EX.alice)]

    def test_engine_kwarg_rejected_for_other_entailment(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="only meaningful for entailment="):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-RDF-Based'], engine="rustdl")

    def test_timeout_kwarg_rejected_for_other_entailment(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="only meaningful for entailment="):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-RDF-Based'], timeout=5)

    def test_tiny_timeout_raises_reasoning_timeout_error(self):
        from starlayer.graph.graph._timeout import ReasoningTimeoutError

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
        assert [r.x.value for r in rows] == [str(EX.alice)]


@owl_dl_extra
@java_required
class TestEntailmentDirectInferArgument:
    """The closure is computed on every call, so ``infer=`` has no caching to select; it is only checked."""

    @pytest.mark.parametrize("infer", ["always", "cached", "changed"])
    def test_every_documented_value_gives_the_same_answer(self, infer):
        g = _disjunctive_graph()
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], infer=infer))
        assert [r.x.value for r in rows] == [str(EX.alice)]

    def test_a_mutation_is_seen_by_the_next_query(self):
        g = _disjunctive_graph()
        list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], infer="changed"))
        g.add((EX.carol, RDF.type, EX.Person))
        rows = list(g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], infer="changed"))
        assert [r.x.value for r in rows] == [str(EX.alice)]

    def test_an_unknown_value_is_rejected(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="infer must be one of"):
            g.query(_Q_WOMAN, entailment=ENTAILMENT['OWL-Direct'], infer="sometimes")
