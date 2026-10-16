"""
tests/unit/test_infer_owl_dl.py

Coverage for StarLayerGraph.infer(entailment=ENTAILMENT['OWL-Direct'], engine="hermit") -
OWL 2 Direct Semantics reasoning via owlready2 + Java HermiT, a genuinely
different computational model (tableau DL reasoning) from every owlrl-backed
entailment regime covered by test_infer.py. `owlready2` is an optional extra of this
package (`pip install starlayer.graph[hermit]`), not a core dependency -
the `owl_dl_extra` skip below is a real "not opted into this engine" skip,
the same spirit as test_infer_owl_dl_rustdl.py's own skip for `[rustdl]`.
A real Java runtime on PATH is a *further* prerequisite that genuinely
can't be satisfied by `pip` alone even once the extra is installed -
HermiT is a Java program, not a pure-Python one - so it gets its own,
separate skip condition.

Per this project's own testing discipline (starlayer.sparql/CLAUDE.md: "any new
query/update shape needs an execution-comparison test, not just a
structural one"), the key test here uses a disjunctive entailment
(`Person subClassOf (Man or Woman)`, `Man`/`Woman` disjoint, `not-Man`
asserted) that owlrl's forward-chaining rule engine structurally cannot
derive - proving this entailment regime is doing genuine DL reasoning, not
something already covered by entailment=ENTAILMENT['OWL-RDF-Based'].
"""

import os
import shutil

import pytest
from starlayer.graph import RDF, Namespace, StarLayerGraph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT

try:
    import owlready2  # noqa: F401
    _OWLREADY2_AVAILABLE = True
except ImportError:
    _OWLREADY2_AVAILABLE = False

owl_dl_extra = pytest.mark.skipif(
    not _OWLREADY2_AVAILABLE,
    reason='owlready2 not importable - it is an optional extra of this package; '
           'install with: pip install starlayer.graph[hermit]',
)

java_required = pytest.mark.skipif(
    shutil.which("java") is None,
    reason='no Java runtime on PATH — owlready2\'s HermiT reasoner needs a JVM '
           '(e.g. `brew install openjdk` on macOS)',
)

EX = Namespace("http://example.org/")


@owl_dl_extra
@java_required
class TestOwlDlDisjunctiveEntailment:
    """The oracle-comparison case: owlrl's forward-chaining rule engine
    structurally cannot derive a disjunctive entailment (it would need to
    case-split on `owl:unionOf`, which no Horn rule can express) - so a
    correct result here proves entailment=ENTAILMENT['OWL-Direct'] is genuine DL reasoning,
    not something entailment=ENTAILMENT['OWL-RDF-Based'] could already produce.
    """

    def _disjunctive_graph(self):
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

    def test_owlrl_cannot_derive_this(self):
        # Confirms the premise: entailment=ENTAILMENT['OWL-RDF-Based'] really does miss this,
        # so the entailment=ENTAILMENT['OWL-Direct'] result below isn't redundant with it.
        pytest.importorskip("owlrl")
        g = self._disjunctive_graph()
        closed = g.infer(entailment=ENTAILMENT['OWL-RDF-Based'])
        assert (EX.alice, RDF.type, EX.Woman) not in closed

    def test_owl_dl_derives_the_disjunctive_entailment(self):
        g = self._disjunctive_graph()
        closed = g.infer(entailment=ENTAILMENT['OWL-Direct'])
        assert (EX.alice, RDF.type, EX.Woman) in closed

    def test_delta_contains_just_the_new_fact(self):
        g = self._disjunctive_graph()
        delta = g.infer(entailment=ENTAILMENT['OWL-Direct'], mode="delta")
        assert (EX.alice, RDF.type, EX.Woman) in delta
        # the originally-asserted facts are not repeated in delta
        assert (EX.alice, RDF.type, EX.Person) not in delta

    def test_original_graph_untouched_by_mode_full(self):
        g = self._disjunctive_graph()
        before_count = len(g)
        g.infer(entailment=ENTAILMENT['OWL-Direct'], mode="full")
        assert len(g) == before_count


@owl_dl_extra
@java_required
class TestOwlDlSubClassClosure:
    """HermiT's own CLI realization output only reports each individual's
    most-specific type(s), not every ancestor class - confirmed live while
    implementing this bridge. Every other entailment regime gives the full
    transitive rdf:type closure, so entailment=ENTAILMENT['OWL-Direct'] needs to match that
    (see owl_dl._complete_type_closure), not just the disjunctive case.
    """

    def test_multi_hop_subclass_entailment(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Manager rdfs:subClassOf ex:Employee .
            ex:Employee rdfs:subClassOf ex:Person .
            ex:alice a ex:Manager .
        """, format="turtle12")
        closed = g.infer(entailment=ENTAILMENT['OWL-Direct'])
        assert (EX.alice, RDF.type, EX.Employee) in closed
        assert (EX.alice, RDF.type, EX.Person) in closed


@owl_dl_extra
@java_required
class TestOwlDlInconsistency:
    def test_inconsistent_ontology_raises(self):
        from starlayer.graph.graph.owl_dl import InconsistentOntologyError

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man, ex:Woman .
        """, format="turtle12")
        with pytest.raises(InconsistentOntologyError):
            g.infer(entailment=ENTAILMENT['OWL-Direct'])

    def test_consistent_ontology_does_not_raise(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man .
        """, format="turtle12")
        closed = g.infer(entailment=ENTAILMENT['OWL-Direct'])  # should not raise
        assert (EX.bob, RDF.type, EX.Man) in closed


@owl_dl_extra
@java_required
class TestOwlDlModes:
    def test_mode_in_place_mutates_and_returns_self(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Manager rdfs:subClassOf ex:Employee .
            ex:alice a ex:Manager .
        """, format="turtle12")
        result = g.infer(entailment=ENTAILMENT['OWL-Direct'], mode="in-place")
        assert result is g
        assert (EX.alice, RDF.type, EX.Employee) in g


@owl_dl_extra
@java_required
class TestOwlDlTripleTermDecomposition:
    """classify_owl_dl() shares the same decompose-before-reasoning
    architecture as the owlrl-backed regimes (see
    starlayer.graph.compare._decompose_for_entailment()), so it's
    susceptible in principle to the same bug class fixed there 2026-10-16:
    a term that exists only *inside* a triple term getting spuriously
    typed as if it had been asserted standalone, because decomposing the
    triple term into synthetic structure exposes it to the reasoner.

    Honestly scoped: unlike owlrl's RDFS_Semantics (which explicitly
    implements a universal "every subject/object is rdfs:Resource" rule),
    this bridge's own class-assertion extraction
    (materialize_inferred_class_assertions() -> RDF/XML realization
    output) was confirmed live, while writing this test, to not report
    rdfs:domain/rdfs:range-driven class membership at all - not for a
    triple term's inner components, and not even for a completely
    ordinary named individual with no triple terms involved. So a sharper
    live repro proving a *behavior difference* isn't achievable against
    this particular bridge's current scope - these tests confirm the fix
    doesn't break anything and that the placeholder genuinely carries no
    leaked content, rather than proving a before/after output difference
    the way test_infer.py's own equivalent test does for the owlrl path.
    """

    def test_triple_term_does_not_crash_and_real_entailments_still_work(self):
        from rdflib import URIRef
        reifies = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:Manager rdfs:subClassOf ex:Employee .
            ex:alice a ex:Manager .
            ex:claim1 rdf:reifies <<( ex:bob ex:manages ex:alice )>> .
        """, format="turtle12")

        closed = g.infer(entailment=ENTAILMENT['OWL-Direct'])

        assert (EX.alice, RDF.type, EX.Employee) in closed
        assert any(closed.triples((EX.claim1, reifies, None)))
        # ex:bob only ever appears inside the triple term - confirms no
        # fact about it leaked into the closure, same spirit as the owlrl
        # test even though this bridge never produced one to begin with.
        assert not any(EX.bob in (s, o) for s, p, o in closed if p != reifies)
    """Wiring coverage only - does infer(entailment=ENTAILMENT['OWL-Direct'], engine="hermit",
    timeout=...) actually thread through to the real reasoning call. The
    timeout *mechanism* itself (process spawn/deadline/process-group kill)
    has its own thorough, engine-independent coverage in test_timeout.py
    using synthetic workers, not real HermiT calls."""

    def _simple_graph(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Cat rdfs:subClassOf ex:Animal .
            ex:alice a ex:Cat .
        """, format="turtle12")
        return g

    def test_default_timeout_does_not_interfere_with_a_normal_call(self):
        closed = self._simple_graph().infer(entailment=ENTAILMENT['OWL-Direct'], engine="hermit")
        assert (EX.alice, RDF.type, EX.Animal) in closed

    def test_tiny_timeout_raises_reasoning_timeout_error(self):
        from starlayer.graph.graph._timeout import ReasoningTimeoutError

        with pytest.raises(ReasoningTimeoutError):
            self._simple_graph().infer(entailment=ENTAILMENT['OWL-Direct'], engine="hermit", timeout=0.001)

    def test_timeout_none_disables_it(self):
        closed = self._simple_graph().infer(entailment=ENTAILMENT['OWL-Direct'], engine="hermit", timeout=None)
        assert (EX.alice, RDF.type, EX.Animal) in closed


def test_timeout_rejected_for_non_owl_dl_entailment():
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, RDF.type, EX.Person))
    with pytest.raises(ValueError, match="only meaningful for entailment="):
        g.infer(entailment=ENTAILMENT.RDFS, timeout=5)


def test_missing_owlready2_raises_actionable_error(monkeypatch):
    """Simulates owlready2 not being installed (independent of whether it
    actually is, in this test environment) - confirms the "opt-in package
    missing" case raises a clear, actionable RuntimeError naming the
    exact extra to install, not a bare ImportError. Mirrors
    test_infer_owl_dl_rustdl.py's identical test for the other engine.
    """
    import sys

    from starlayer.graph.graph import owl_dl

    monkeypatch.setitem(sys.modules, "owlready2", None)
    with pytest.raises(RuntimeError, match=r"starlayer.graph\[hermit\]"):
        owl_dl._require_owlready2()


def test_invalid_engine_raises_value_error():
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, RDF.type, EX.Person))
    with pytest.raises(ValueError, match="Unsupported engine"):
        g.infer(entailment=ENTAILMENT['OWL-Direct'], engine="not-a-real-engine")


def test_engine_rejected_for_non_owl_dl_entailment():
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, RDF.type, EX.Person))
    with pytest.raises(ValueError, match="only meaningful for entailment="):
        g.infer(entailment=ENTAILMENT.RDFS, engine="rustdl")


@owl_dl_extra
def test_missing_java_raises_a_distinct_clear_error(monkeypatch):
    """Simulates a JVM-missing environment (independent of whether Java is
    actually installed on this machine) to confirm a missing JVM raises
    its own clear, actionable RuntimeError rather than an opaque failure
    from deep inside owlready2/subprocess.
    """
    from starlayer.graph.graph import owl_dl

    monkeypatch.setattr(owl_dl.shutil, "which", lambda name: None)
    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, RDF.type, EX.Person))
    with pytest.raises(RuntimeError, match="Java runtime"):
        owl_dl.classify_owl_dl(g)


@owl_dl_extra
@java_required
def test_broken_java_raises_a_distinct_clear_error(tmp_path, monkeypatch):
    """A `java` binary that's present on PATH but fails when actually run
    (corrupted install, bad JAVA_HOME, missing shared libs, ...) is a
    genuinely different failure mode from "no java at all" -
    `_require_java()`'s own presence check can't catch it, since it only
    confirms *something* is on PATH, not that it works. Confirmed live
    that this surfaces as owlready2's own OwlReadyJavaError if not
    explicitly caught; this test pins the re-wrap into the same
    RuntimeError family `_require_java()` already uses.
    """
    from starlayer.graph.graph import owl_dl

    fake_java = tmp_path / "java"
    fake_java.write_text(
        "#!/bin/sh\n"
        'echo "Error: A JNI error has occurred, please check your installation and try again" >&2\n'
        "exit 1\n"
    )
    fake_java.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    g = StarLayerGraph()
    g.bind("ex", EX)
    g.add((EX.alice, RDF.type, EX.Person))
    with pytest.raises(RuntimeError, match="broken or misconfigured"):
        owl_dl.classify_owl_dl(g)
