"""
tests/unit/test_infer_owl_dl_rustdl.py

Coverage for StarLayerGraph.infer(profile="owl-dl", engine="rustdl") -
OWL 2 DL reasoning via RustDL, the second engine alongside engine="hermit"
(test_infer_owl_dl.py). `rustdl` is an optional extra of this package
(`pip install starlayergraph[rustdl]`), not a core dependency - the
`rustdl_extra` skip below is a real "not opted into this engine" skip,
mirroring test_infer_owl_dl.py's own skip for `[hermit]`. No JVM/Java
skip condition here (RustDL's entire appeal is not needing one) - that's
the one asymmetry against the HermiT test file, not an oversight.

Per this project's own testing discipline (starsparql/CLAUDE.md: "any new
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

from starlayergraph import RDF, Namespace, StarLayerGraph

try:
    import rustdl
    _RUSTDL_AVAILABLE = True
except ImportError:
    _RUSTDL_AVAILABLE = False

rustdl_extra = pytest.mark.skipif(
    not _RUSTDL_AVAILABLE,
    reason='rustdl not importable - it is an optional extra of this package; '
           'install with: pip install starlayergraph[rustdl]',
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


def test_missing_rustdl_raises_actionable_error(monkeypatch):
    """Simulates rustdl not being installed (independent of whether it
    actually is, in this test environment) - confirms the "opt-in package
    missing" case raises a clear, actionable RuntimeError naming the
    exact extra to install, not a bare ImportError. Mirrors
    test_infer_owl_dl.py's identical test for the other engine.
    """
    import sys

    from starlayergraph.graph import owl_dl_rustdl

    monkeypatch.setitem(sys.modules, "rustdl", None)
    with pytest.raises(RuntimeError, match=r"starlayergraph\[rustdl\]"):
        owl_dl_rustdl._require_rustdl()
