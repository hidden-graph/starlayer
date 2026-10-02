"""
tests/unit/test_infer_owl_dl_rustdl.py

Coverage for StarLayerGraph.infer(profile="owl-dl", engine="rustdl") -
OWL 2 DL reasoning via RustDL, the second engine alongside engine="hermit"
(test_infer_owl_dl.py). `rustdl` is an optional extra of this package
(`pip install starlayer.graph[rustdl]`), not a core dependency - the
`rustdl_extra` skip below is a real "not opted into this engine" skip,
mirroring test_infer_owl_dl.py's own skip for `[hermit]`. No JVM/Java
skip condition here (RustDL's entire appeal is not needing one) - that's
the one asymmetry against the HermiT test file, not an oversight.

Per this project's own testing discipline (starlayer.sparql/CLAUDE.md: "any new
query/update shape needs an execution-comparison test, not just a
structural one"), the key test here uses the *same* disjunctive-class
entailment shape test_infer_owl_dl.py's own oracle-comparison test uses
(`Person subClassOf (Man or Woman)`, `Man`/`Woman` disjoint, `not-Man`
asserted) - confirmed live that engine="rustdl" derives this correctly,
same as engine="hermit". What's deliberately NOT tested here as a "forced
by inference alone" case: a disjunctive *property* entailment (the
logic-puzzle shape in docs/guides/05e-owl-dl-reasoning.ipynb section 1.b)
- confirmed live that RustDL's materialize_inferred_property_assertions()
does not reproduce it (its own docs: "sound under-approximation, no
disjunctive-derived edges") - see owl_dl_rustdl.py's own module docstring
for the fuller account. That is a real, documented scope difference from
engine="hermit", not a bug to chase down here.
"""

import pytest

from starlayer.graph import RDF, Namespace, StarLayerGraph

try:
    import rustdl
    _RUSTDL_AVAILABLE = True
except ImportError:
    _RUSTDL_AVAILABLE = False

rustdl_extra = pytest.mark.skipif(
    not _RUSTDL_AVAILABLE,
    reason='rustdl not importable - it is an optional extra of this package; '
           'install with: pip install starlayer.graph[rustdl]',
)

EX = Namespace("http://example.org/")


@rustdl_extra
class TestOwlDlRustdlDisjunctiveClassEntailment:
    """Same shape as test_infer_owl_dl.py's own oracle-comparison case -
    confirms engine="rustdl" derives the same disjunctive *class*
    entailment engine="hermit" does, for the one shape RustDL's own
    materialize_inferred_class_assertions() is confirmed (live) to handle
    correctly.
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

    def test_owl_dl_derives_the_disjunctive_entailment(self):
        g = self._disjunctive_graph()
        closed = g.infer(profile="owl-dl", engine="rustdl")
        assert (EX.alice, RDF.type, EX.Woman) in closed

    def test_delta_contains_just_the_new_fact(self):
        g = self._disjunctive_graph()
        delta = g.infer(profile="owl-dl", engine="rustdl", mode="delta")
        assert (EX.alice, RDF.type, EX.Woman) in delta
        assert (EX.alice, RDF.type, EX.Person) not in delta

    def test_original_graph_untouched_by_mode_full(self):
        g = self._disjunctive_graph()
        before_count = len(g)
        g.infer(profile="owl-dl", engine="rustdl", mode="full")
        assert len(g) == before_count


@rustdl_extra
class TestOwlDlRustdlSubClassClosure:
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
        closed = g.infer(profile="owl-dl", engine="rustdl")
        assert (EX.alice, RDF.type, EX.Employee) in closed
        assert (EX.alice, RDF.type, EX.Person) in closed


@rustdl_extra
class TestOwlDlRustdlInconsistency:
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
            g.infer(profile="owl-dl", engine="rustdl")

    def test_consistent_ontology_does_not_raise(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:Man owl:disjointWith ex:Woman .
            ex:bob a ex:Man .
        """, format="turtle12")
        closed = g.infer(profile="owl-dl", engine="rustdl")  # should not raise
        assert (EX.bob, RDF.type, EX.Man) in closed


@rustdl_extra
class TestOwlDlRustdlHangRisk:
    """A property declared both owl:FunctionalProperty and
    owl:InverseFunctionalProperty, used in a someValuesFrom restriction
    whose filler is an owl:oneOf nominal enumeration, is confirmed to hang
    RustDL's materialize_inferred_class_assertions() indefinitely - see
    owl_dl_rustdl.py's own module docstring, point 4, for the full account.
    The pre-flight SHACL check must reject this fast (well under a test
    timeout) rather than let the caller hang."""

    def _hang_pattern_graph(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:hasSpouse a owl:ObjectProperty, owl:FunctionalProperty, owl:InverseFunctionalProperty .

            ex:MarriedToNominal a owl:Class ;
                owl:oneOf ( ex:alice ex:bob ex:carol ) .

            ex:Married rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:hasSpouse ;
                owl:someValuesFrom ex:MarriedToNominal
            ] .

            ex:dave a ex:Married .
        """, format="turtle12")
        return g

    def test_hang_pattern_raises_unsupported_axiom_error_instead_of_hanging(self):
        g = self._hang_pattern_graph()
        with pytest.raises(rustdl.UnsupportedAxiomError):
            g.infer(profile="owl-dl", engine="rustdl")

    def test_hermit_does_not_raise_on_the_identical_ontology(self):
        """Confirms this is a RustDL-specific hang, not a general problem
        with the ontology itself - engine="hermit" handles it fine."""
        g = self._hang_pattern_graph()
        g.infer(profile="owl-dl", engine="hermit")  # should not raise

    def test_ordinary_ontology_is_unaffected_by_the_preflight_check(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Cat rdfs:subClassOf ex:Animal .
            ex:alice a ex:Cat .
        """, format="turtle12")
        closed = g.infer(profile="owl-dl", engine="rustdl")  # should not raise
        assert (EX.alice, RDF.type, EX.Animal) in closed


@rustdl_extra
class TestOwlDlRustdlModes:
    def test_mode_in_place_mutates_and_returns_self(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Manager rdfs:subClassOf ex:Employee .
            ex:alice a ex:Manager .
        """, format="turtle12")
        result = g.infer(profile="owl-dl", engine="rustdl", mode="in-place")
        assert result is g
        assert (EX.alice, RDF.type, EX.Employee) in g


@rustdl_extra
class TestOwlDlRustdlTimeout:
    """Wiring coverage only - does infer(profile="owl-dl", engine="rustdl",
    timeout=...) actually thread through to the real reasoning call. The
    timeout *mechanism* itself (process spawn/deadline/process-group kill)
    has its own thorough, engine-independent coverage in test_timeout.py
    using synthetic workers, not real RustDL calls."""

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
        closed = self._simple_graph().infer(profile="owl-dl", engine="rustdl")
        assert (EX.alice, RDF.type, EX.Animal) in closed

    def test_tiny_timeout_raises_reasoning_timeout_error(self):
        from starlayer.graph.graph._timeout import ReasoningTimeoutError

        with pytest.raises(ReasoningTimeoutError):
            self._simple_graph().infer(profile="owl-dl", engine="rustdl", timeout=0.001)

    def test_timeout_none_disables_it(self):
        closed = self._simple_graph().infer(profile="owl-dl", engine="rustdl", timeout=None)
        assert (EX.alice, RDF.type, EX.Animal) in closed

    def test_hang_risk_preflight_check_still_fires_before_the_timeout(self):
        """The fast, specific pre-flight check (owl_dl_rustdl.py point 4)
        must still fire immediately, well under even a generous timeout -
        not get silently superseded now that a general timeout also
        exists."""
        g = self._hang_pattern_graph()
        with pytest.raises(rustdl.UnsupportedAxiomError):
            g.infer(profile="owl-dl", engine="rustdl", timeout=60)

    def _hang_pattern_graph(self):
        g = StarLayerGraph()
        g.bind("ex", EX)
        g.parse(data="""
            @prefix ex: <http://example.org/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

            ex:hasSpouse a owl:ObjectProperty, owl:FunctionalProperty, owl:InverseFunctionalProperty .

            ex:MarriedToNominal a owl:Class ;
                owl:oneOf ( ex:alice ex:bob ex:carol ) .

            ex:Married rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:hasSpouse ;
                owl:someValuesFrom ex:MarriedToNominal
            ] .

            ex:dave a ex:Married .
        """, format="turtle12")
        return g


def test_missing_rustdl_raises_actionable_error(monkeypatch):
    """Simulates rustdl not being installed (independent of whether it
    actually is, in this test environment) - confirms the "opt-in package
    missing" case raises a clear, actionable RuntimeError naming the
    exact extra to install, not a bare ImportError. Mirrors
    test_infer_owl_dl.py's identical test for the other engine.
    """
    import sys

    from starlayer.graph.graph import owl_dl_rustdl

    monkeypatch.setitem(sys.modules, "rustdl", None)
    with pytest.raises(RuntimeError, match=r"starlayer.graph\[rustdl\]"):
        owl_dl_rustdl._require_rustdl()
