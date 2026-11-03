"""RDFS / OWL RL entailment for the native engine, compared with the old validator on the same inline Turtle."""

import time

import pytest
from rdflib import Graph
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl.validator import validate as old_validate
from starlayer.shacl_engine import entailment as _entailment
from starlayer.shacl_engine.api import validate as engine_validate
from starlayer.shacl_engine.terms import NS as Namespace
from starlayer.shacl_engine.terms import RDF, RDFS

entailed_view = _entailment.entailed_view
resolve_data_view = _entailment.resolve_data_view

pytest.importorskip("owlrl")

EX = Namespace("http://example.org/")
PFX = """@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
"""
SHAPES = PFX + "ex:EmployeeShape a sh:NodeShape ; sh:targetClass ex:Employee ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
DOMAIN = PFX + "ex:worksAt rdfs:domain ex:Employee . ex:alice ex:worksAt ex:Acme ."


def _g(ttl: str) -> OxGraph:
    g = OxGraph()
    g.parse(data=ttl, format="turtle")
    return g


def _old_signature(result) -> tuple:
    rg = result.report_graph
    SHNS = Namespace("http://www.w3.org/ns/shacl#")
    rows = set()
    for r in rg.subjects(RDF.type, SHNS.ValidationResult):
        rows.add(
            (
                next(rg.objects(r, SHNS.focusNode), None),
                next(rg.objects(r, SHNS.sourceConstraintComponent), None),
            )
        )
    return result.conforms, rows


def _new_signature(outcome) -> tuple:
    return outcome.conforms, {(r.focus, r.component) for r in outcome.results}


def _both(data_ttl, shapes_ttl, *, inference=None, ont_ttl=None, declare=None):
    shapes_old = _g(shapes_ttl)
    shapes_new = _g(shapes_ttl)
    if declare is not None:
        shapes_old.add((EX.EmployeeShape, Namespace("http://www.w3.org/ns/shacl#").entailment, declare))
        shapes_new.add((EX.EmployeeShape, Namespace("http://www.w3.org/ns/shacl#").entailment, declare))
    old = old_validate(_g(data_ttl), shapes_old, _g(ont_ttl) if ont_ttl else None, meta_shacl=False, inference=inference)
    data = _g(data_ttl)
    before = set(data)
    view = resolve_data_view(data, shapes_new, inference=inference, ont_graph=_g(ont_ttl) if ont_ttl else None)
    new = engine_validate(view, shapes_new)
    assert set(data) == before, "the caller's graph is not mutated"
    return _old_signature(old), _new_signature(new)


def test_domain_inference_option_agrees() -> None:
    old, new = _both(DOMAIN, SHAPES, inference=ENTAILMENT.RDFS)
    assert old == new and old[0] is False


def test_without_regime_alice_is_not_a_target() -> None:
    old, new = _both(DOMAIN, SHAPES)
    assert old == new and old[0] is True


def test_sh_entailment_declaration_agrees() -> None:
    old, new = _both(DOMAIN, SHAPES, declare=ENTAILMENT.RDFS)
    assert old == new and old[0] is False


def test_rdfs_and_owlrl_combined_agrees() -> None:
    old, new = _both(DOMAIN, SHAPES, inference=frozenset({ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]}))
    assert old == new and old[0] is False


def test_owlrl_equivalent_class_agrees() -> None:
    data = PFX + "ex:Manager owl:equivalentClass ex:Employee . ex:alice a ex:Manager ."
    old, new = _both(data, SHAPES, inference=ENTAILMENT["OWL-RDF-Based"])
    assert old == new and old[0] is False


def test_ont_graph_axiom_is_seen_but_not_copied() -> None:
    data = PFX + "ex:alice ex:worksAt ex:Acme ."
    ont = PFX + "ex:worksAt rdfs:domain ex:Employee ."
    old, new = _both(data, SHAPES, inference=ENTAILMENT.RDFS, ont_ttl=ont)
    assert old == new and old[0] is False
    view = entailed_view(_g(data), ENTAILMENT.RDFS, _g(ont))
    assert (EX.worksAt, RDFS.domain, EX.Employee) not in view
    assert (EX.alice, RDF.type, EX.Employee) in view


def test_range_and_subclass_closure_feed_sh_class() -> None:
    shapes = PFX + "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:pet ; sh:class ex:Animal ] ."
    data = PFX + "ex:pet rdfs:range ex:Dog . ex:Dog rdfs:subClassOf ex:Animal . ex:alice ex:pet ex:rex ."
    old, new = _both(data, shapes, inference=ENTAILMENT.RDFS)
    assert old == new and old[0] is True
    assert _new_signature(engine_validate(_g(data), _g(shapes)))[0] is False  # needs the entailment


def test_subclass_class_targets() -> None:
    data = PFX + "ex:Manager rdfs:subClassOf ex:Employee . ex:bob a ex:Manager ."
    old, new = _both(data, SHAPES)
    assert old == new and old[0] is False  # SHACL's own subclass reasoning, no regime needed


def test_regime_iris_and_no_regime() -> None:
    g = _g(DOMAIN)
    assert entailed_view(g, None) is g
    assert (EX.alice, RDF.type, EX.Employee) in entailed_view(g, ENTAILMENT.RDFS)
    assert (EX.alice, RDF.type, EX.Employee) in resolve_data_view(g, _g(SHAPES), inference=ENTAILMENT.RDFS)
    assert resolve_data_view(g, _g(SHAPES)) is g


@pytest.mark.parametrize("name", ["rdfs", "owlrl", "both", "none"])
def test_pyshacl_style_names_are_not_regimes(name) -> None:
    """``inference=`` takes the W3C entailment regime IRIs (the vocabulary of ``sh:entailment``), not pySHACL's own names."""
    with pytest.raises(ValueError):  # pyoxigraph rejects the non-IRI string itself
        entailed_view(_g(DOMAIN), name)


def test_unsupported_regime_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported entailment"):
        resolve_data_view(_g(DOMAIN), _g(SHAPES), inference=ENTAILMENT.D)
    shapes = _g(SHAPES + " ex:Shapes sh:entailment ex:NotARuleSet .")
    with pytest.raises(ValueError, match="Unsupported entailment"):
        resolve_data_view(_g(DOMAIN), shapes)


def test_rules_entailment_and_rule_sets_are_not_regimes() -> None:
    shapes = _g(SHAPES + " ex:Shapes sh:entailment sh:RulesEntailment . ex:Set a sh:RuleSet . ex:Shapes sh:entailment ex:Set .")
    g = _g(DOMAIN)
    assert resolve_data_view(g, shapes) is g


def test_plain_rdflib_graph_input() -> None:
    g = Graph()
    g.parse(data=DOMAIN, format="turtle")
    assert (EX.alice, RDF.type, EX.Employee) in entailed_view(g, ENTAILMENT.RDFS)


def test_closure_performance_5k_triples() -> None:
    lines = [PFX, "ex:worksAt rdfs:domain ex:Employee ."]
    lines += [f"ex:p{i} a ex:Person ; ex:worksAt ex:Acme ; ex:name \"n{i}\" ; ex:knows ex:p{i + 1} ." for i in range(1000)]
    g = _g("\n".join(lines))
    assert len(g) >= 4000
    t = time.perf_counter()
    view = entailed_view(g, ENTAILMENT.RDFS)
    elapsed = time.perf_counter() - t
    print(f"5k-triple RDFS closure: {elapsed:.2f}s, {len(view.inferred)} inferred")
    assert (EX.p5, RDF.type, EX.Employee) in view
    assert elapsed < 60
