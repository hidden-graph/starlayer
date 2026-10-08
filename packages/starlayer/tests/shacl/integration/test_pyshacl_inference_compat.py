"""tests/shacl/integration/test_pyshacl_inference_compat.py

Coverage for validate()'s inference= keyword (starlayer.shacl.entailment
.apply_entailment's own inference= parameter) - lets a caller request
entailment without declaring sh:entailment in the shapes graph, routed
through StarLayerGraph's own triple-term-safe entailment machinery.

2026-10-08: inference= now takes a real ENTAILMENT.* IRI (or an iterable of
them), the exact same vocabulary sh:entailment itself uses - not pySHACL's
own ad-hoc strings ("rdfs"/"owlrl"/"both"/etc.), which no longer work at
all. This was a deliberate disconnection from pySHACL's own vocabulary, on
direct user instruction, not an incremental extension of it - see
starlayer.shacl.entailment's own module docstring for the full account.

Per this project's own testing discipline, plain pyshacl.validate() is
still the oracle for the *underlying entailment semantics* (does our
ENTAILMENT.RDFS regime produce the same conformance result pySHACL's own
inference="rdfs" does) - only pySHACL's own, unrelated string vocabulary
on its side of the comparison is unaffected by this change, since that's
pySHACL's own API, not ours.
"""

import pyshacl
import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import RDF
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.shacl.validator import apply_rules, validate

EX = Namespace("http://example.org/")

SHAPES = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:EmployeeShape a sh:NodeShape ;
        sh:targetClass ex:Employee ;
        sh:property [ sh:path ex:name ; sh:minCount 1 ] .
"""

DATA_RDFS_DOMAIN = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:worksAt rdfs:domain ex:Employee .
    ex:alice ex:worksAt ex:Acme .
"""


def _shapes() -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=SHAPES, format="turtle")
    return g


class TestInferenceRdfsMatchesPyshaclOracle:
    def test_domain_entailment_conforms_matches_pyshacl(self) -> None:
        data = StarLayerGraph()
        data.parse(data=DATA_RDFS_DOMAIN, format="turtle")

        result = validate(data, _shapes(), meta_shacl=False, inference=ENTAILMENT.RDFS)

        oracle_data = Graph()
        oracle_data.parse(data=DATA_RDFS_DOMAIN, format="turtle")
        oracle_shapes = Graph()
        oracle_shapes.parse(data=SHAPES, format="turtle")
        oracle_conforms, _, _ = pyshacl.validate(
            oracle_data, shacl_graph=oracle_shapes, inference="rdfs", meta_shacl=False, advanced=True
        )

        assert result.conforms == oracle_conforms is False

    def test_combined_rdfs_and_owlrl_matches_pyshacl_both(self) -> None:
        data = StarLayerGraph()
        data.parse(data=DATA_RDFS_DOMAIN, format="turtle")

        result = validate(
            data, _shapes(), meta_shacl=False, inference=frozenset({ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]})
        )

        oracle_data = Graph()
        oracle_data.parse(data=DATA_RDFS_DOMAIN, format="turtle")
        oracle_shapes = Graph()
        oracle_shapes.parse(data=SHAPES, format="turtle")
        oracle_conforms, _, _ = pyshacl.validate(
            oracle_data, shacl_graph=oracle_shapes, inference="both", meta_shacl=False, advanced=True
        )

        assert result.conforms == oracle_conforms is False


class TestInferenceOwlrlMatchesPyshaclOracle:
    def test_owlrl_conforms_matches_pyshacl(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                ex:Manager owl:equivalentClass ex:Employee .
                ex:alice a ex:Manager .
            """,
            format="turtle",
        )

        result = validate(data, _shapes(), meta_shacl=False, inference=ENTAILMENT["OWL-RDF-Based"])

        oracle_data = Graph()
        oracle_data.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix owl: <http://www.w3.org/2002/07/owl#> .
                ex:Manager owl:equivalentClass ex:Employee .
                ex:alice a ex:Manager .
            """,
            format="turtle",
        )
        oracle_shapes = Graph()
        oracle_shapes.parse(data=SHAPES, format="turtle")
        oracle_conforms, _, _ = pyshacl.validate(
            oracle_data, shacl_graph=oracle_shapes, inference="owlrl", meta_shacl=False, advanced=True
        )

        assert result.conforms == oracle_conforms is False


class TestInferenceWithOntGraph:
    """(b)+(c) convergence: inference= now also sees ont_graph-only axioms,
    the same way sh:entailment does - both route through the same shared
    entailment helper."""

    def test_rdfs_domain_axiom_in_ont_graph_is_seen(self) -> None:
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:alice ex:worksAt ex:Acme .", format="turtle"
        )
        ont = StarLayerGraph()
        ont.parse(
            data="@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
            "ex:worksAt rdfs:domain ex:Employee .",
            format="turtle",
        )

        result = validate(data, _shapes(), ont, meta_shacl=False, inference=ENTAILMENT.RDFS)

        assert result.conforms is False


class TestInferenceSurvivesApplyRulesGlobalRulePass:
    """SHACL Core §1.4 only mandates entailment be visible "during the
    validation process" - i.e. once, over the *complete* evaluation graph,
    after every rule (shape-attached and global) has run. apply_rules()'s
    own re-application of sh:entailment/inference= at that point must
    correctly see the global rule's own output too (e.g. a rule-asserted
    ex:worksAt triple that a declared RDFS regime should close over) when
    computing conforms - even though the entailed triple itself never
    appears in result.inferred_graph (strictly rule output, not entailment -
    see RulesResult.inferred_graph's own docstring)."""

    def test_domain_entailment_on_global_rule_output_affects_conforms(self) -> None:
        shapes = StarLayerGraph()
        shapes.parse(
            data="""
                @prefix ex: <http://example.org/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:HasFriendRule a sh:SPARQLRule ;
                  sh:construct \"\"\"
                    PREFIX ex: <http://example.org/>
                    CONSTRUCT { ?s ex:worksAt ex:NewOrg . }
                    WHERE { ?s ex:friend ?o . }
                  \"\"\" .
                ex:EmployeeShape a sh:NodeShape ;
                    sh:targetClass ex:Employee ;
                    sh:property [ sh:path ex:name ; sh:minCount 1 ] .
            """,
            format="turtle",
        )
        data = StarLayerGraph()
        data.parse(
            data="@prefix ex: <http://example.org/> . ex:bob ex:friend ex:caren .",
            format="turtle",
        )
        ont = StarLayerGraph()
        ont.parse(
            data="@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
            "ex:worksAt rdfs:domain ex:Employee .",
            format="turtle",
        )

        result = apply_rules(data, shacl_graph=shapes, ont_graph=ont, meta_shacl=False, inference=ENTAILMENT.RDFS)

        assert (EX.bob, EX.worksAt, EX.NewOrg) in result.inferred_graph
        assert (EX.bob, RDF.type, EX.Employee) not in result.inferred_graph
        assert result.validation.conforms is False


class TestInferenceNoneAndInvalid:
    def test_none_is_a_noop(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Employee ; ex:name \"Alice\" .", format="turtle")

        result = validate(data, _shapes(), meta_shacl=False, inference=None)

        assert result.conforms is True

    def test_unsupported_regime_iri_raises(self) -> None:
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Employee .", format="turtle")

        with pytest.raises(ValueError, match="Unsupported entailment regime"):
            validate(data, _shapes(), meta_shacl=False, inference=ENTAILMENT.D)

    def test_pyshacl_style_string_no_longer_accepted(self) -> None:
        """Regression coverage for the deliberate 2026-10-08 disconnection
        from pySHACL's own string vocabulary - a caller's old
        inference="rdfs" must now fail loudly, not silently resolve to
        something unintended."""
        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice a ex:Employee .", format="turtle")

        with pytest.raises(ValueError, match="Unsupported entailment regime"):
            validate(data, _shapes(), meta_shacl=False, inference="rdfs")
