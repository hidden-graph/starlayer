"""
tests/unit/test_infer_owl_dl.py

Coverage for StarLayerGraph.infer(profile="owl-dl") - OWL 2 Direct
Semantics reasoning via owlready2 + Java HermiT, a genuinely different
computational model (tableau DL reasoning) from every owlrl-backed
profile covered by test_infer.py. `owlready2` is a normal (core)
dependency of this package, so it should always be importable - the
`owl_dl_extra` skip below guards against a broken/incomplete install
rather than an optional extra a user needs to opt into (the same pattern
`pyshacl`'s own tests use, even though it's core to that package too).
A real Java runtime on PATH is the one prerequisite that genuinely can't
be satisfied by `pip` alone - HermiT is a Java program, not a
pure-Python one - so it gets its own, separate skip condition.

Per this project's own testing discipline (starsparql/CLAUDE.md: "any new
query/update shape needs an execution-comparison test, not just a
structural one"), the key test here uses a disjunctive entailment
(`Person subClassOf (Man or Woman)`, `Man`/`Woman` disjoint, `not-Man`
asserted) that owlrl's forward-chaining rule engine structurally cannot
derive - proving this profile is doing genuine DL reasoning, not
something already covered by profile="owl-rl".
"""

import os
import shutil

import pytest

from starlayergraph import RDF, Namespace, StarLayerGraph

try:
    import owlready2
    _OWLREADY2_AVAILABLE = True
except ImportError:
    _OWLREADY2_AVAILABLE = False

owl_dl_extra = pytest.mark.skipif(
    not _OWLREADY2_AVAILABLE,
    reason='owlready2 not importable - it is a core dependency of this package; '
           'reinstall with: pip install -e .',
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
    correct result here proves profile="owl-dl" is genuine DL reasoning,
    not something profile="owl-rl" could already produce.
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
        # Confirms the premise: profile="owl-rl" really does miss this,
        # so the profile="owl-dl" result below isn't redundant with it.
        pytest.importorskip("owlrl")
        g = self._disjunctive_graph()
        closed = g.infer(profile="owl-rl")
        assert (EX.alice, RDF.type, EX.Woman) not in closed

    def test_owl_dl_derives_the_disjunctive_entailment(self):
        g = self._disjunctive_graph()
        closed = g.infer(profile="owl-dl")
        assert (EX.alice, RDF.type, EX.Woman) in closed

    def test_delta_contains_just_the_new_fact(self):
        g = self._disjunctive_graph()
        delta = g.infer(profile="owl-dl", mode="delta")
        assert (EX.alice, RDF.type, EX.Woman) in delta
        # the originally-asserted facts are not repeated in delta
        assert (EX.alice, RDF.type, EX.Person) not in delta

    def test_original_graph_untouched_by_mode_full(self):
        g = self._disjunctive_graph()
        before_count = len(g)
        g.infer(profile="owl-dl", mode="full")
        assert len(g) == before_count


@owl_dl_extra
@java_required
class TestOwlDlSubClassClosure:
    """HermiT's own CLI realization output only reports each individual's
    most-specific type(s), not every ancestor class - confirmed live while
    implementing this bridge. Every other profile gives the full
    transitive rdf:type closure, so profile="owl-dl" needs to match that
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
        closed = g.infer(profile="owl-dl")
        assert (EX.alice, RDF.type, EX.Employee) in closed
        assert (EX.alice, RDF.type, EX.Person) in closed


@owl_dl_extra
@java_required
class TestOwlDlInconsistency:
    def test_inconsistent_ontology_raises(self):
        from starlayergraph.graph.owl_dl import InconsistentOntologyError

        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man, ex:Woman .
        """, format="turtle12")
        with pytest.raises(InconsistentOntologyError):
            g.infer(profile="owl-dl")

    def test_consistent_ontology_does_not_raise(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man .
        """, format="turtle12")
        closed = g.infer(profile="owl-dl")  # should not raise
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
        result = g.infer(profile="owl-dl", mode="in-place")
        assert result is g
        assert (EX.alice, RDF.type, EX.Employee) in g


@owl_dl_extra
def test_missing_java_raises_a_distinct_clear_error(monkeypatch):
    """Simulates a JVM-missing environment (independent of whether Java is
    actually installed on this machine) to confirm a missing JVM raises
    its own clear, actionable RuntimeError rather than an opaque failure
    from deep inside owlready2/subprocess.
    """
    from starlayergraph.graph import owl_dl

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
    from starlayergraph.graph import owl_dl

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
