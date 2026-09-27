"""
tests/unit/test_entailment_direct.py

Coverage for StarLayerGraph.query(..., entailment="direct") - the
query-time counterpart to StarLayerGraph.infer(profile="owl-dl", engine=...):
query() a live union of self and a small cached OWL-DL entailment delta,
mirroring exactly how entailment="owl-rl" already works for the owlrl-backed
profile (see test_entailment.py's TestEntailmentOwlRl*/TestEntailmentOwlRlCaching,
whose shapes this file's classes deliberately mirror).

`owlready2`/`rustdl` are both optional extras of this package (`pip install
starlayergraph[hermit]`/`[rustdl]`) - the skip markers below are copied
locally rather than imported from test_infer_owl_dl.py/test_infer_owl_dl_rustdl.py,
matching those two files' own precedent of each keeping its own copy rather
than sharing markers across files.
"""

import shutil

import pytest

from starlayergraph import RDF, Namespace, StarLayerGraph
from starlayergraph.graph.owl_dl import InconsistentOntologyError

try:
    import owlready2
    _OWLREADY2_AVAILABLE = True
except ImportError:
    _OWLREADY2_AVAILABLE = False

try:
    import rustdl
    _RUSTDL_AVAILABLE = True
except ImportError:
    _RUSTDL_AVAILABLE = False

owl_dl_extra = pytest.mark.skipif(
    not _OWLREADY2_AVAILABLE,
    reason='owlready2 not importable - it is an optional extra of this package; '
           'install with: pip install starlayergraph[hermit]',
)

java_required = pytest.mark.skipif(
    shutil.which("java") is None,
    reason='no Java runtime on PATH — owlready2\'s HermiT reasoner needs a JVM '
           '(e.g. `brew install openjdk` on macOS)',
)

rustdl_extra = pytest.mark.skipif(
    not _RUSTDL_AVAILABLE,
    reason='rustdl not importable - it is an optional extra of this package; '
           'install with: pip install starlayergraph[rustdl]',
)

EX = Namespace("http://example.org/")

_Q_WOMAN = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Woman }"


def _disjunctive_graph():
    # Same oracle fixture as test_infer_owl_dl.py's own disjunctive-entailment
    # test - owlrl's forward-chaining rule engine structurally cannot derive
    # this, so a correct result here proves entailment="direct" is doing
    # genuine DL reasoning at query time, not something entailment="owl-rl"
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
        rows = list(g.query(_Q_WOMAN, entailment="direct"))
        assert [str(r.x) for r in rows] == [str(EX.alice)]

    def test_engine_kwarg_rejected_for_other_entailment(self):
        g = _disjunctive_graph()
        with pytest.raises(ValueError, match="only meaningful for entailment='direct'"):
            g.query(_Q_WOMAN, entailment="owl-rl", engine="rustdl")

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
            list(g.query(q, entailment="direct"))

    def test_direct_entailment_accepted_on_native_backend_no_store(self):
        # No live store configured, so this can't reach an actual endpoint -
        # confirms validation passes and dispatch is reached (a RuntimeError
        # about the missing store, not a NotImplementedError about
        # entailment), mirroring test_entailment.py's identical check for
        # entailment="native".
        g = StarLayerGraph(backend="rdf-1.2")
        with pytest.raises(RuntimeError, match="store"):
            g.query(_Q_WOMAN, entailment="direct")


@rustdl_extra
class TestEntailmentDirectRustdl:
    def test_engine_rustdl_selectable_via_query(self):
        g = _disjunctive_graph()
        rows = list(g.query(_Q_WOMAN, entailment="direct", engine="rustdl"))
        assert [str(r.x) for r in rows] == [str(EX.alice)]


@owl_dl_extra
@java_required
class TestEntailmentDirectCaching:
    def test_unchanged_graph_reuses_the_identical_cached_delta(self):
        g = _disjunctive_graph()
        list(g.query(_Q_WOMAN, entailment="direct"))
        first = g._owl_dl_cache["hermit"][0]
        list(g.query(_Q_WOMAN, entailment="direct"))
        second = g._owl_dl_cache["hermit"][0]
        assert first is second

    def test_changed_mode_recomputes_after_a_mutation(self):
        g = _disjunctive_graph()
        list(g.query(_Q_WOMAN, entailment="direct", infer="changed"))
        first = g._owl_dl_cache["hermit"][0]

        g.add((EX.carol, RDF.type, EX.Person))
        list(g.query(_Q_WOMAN, entailment="direct", infer="changed"))
        second = g._owl_dl_cache["hermit"][0]

        assert first is not second


@owl_dl_extra
@java_required
@rustdl_extra
class TestEntailmentDirectMultiEngineCaching:
    def test_switching_engine_does_not_invalidate_other_engines_cache(self):
        g = _disjunctive_graph()
        list(g.query(_Q_WOMAN, entailment="direct", engine="hermit"))
        hermit_first = g._owl_dl_cache["hermit"][0]

        list(g.query(_Q_WOMAN, entailment="direct", engine="rustdl"))
        list(g.query(_Q_WOMAN, entailment="direct", engine="hermit"))
        hermit_second = g._owl_dl_cache["hermit"][0]

        assert hermit_first is hermit_second
