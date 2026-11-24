"""OWL-Direct combined with other entailment regimes in SHACL (``infer._delta_for``, ``cache.build_entailed_copy``).

SHACL Core 1.4: the processor provides the entailments of every ``sh:entailment`` value of the shapes graph; a processor-level
``inference=`` is combined with them. The entry holds the entailments of every regime in the set; the others also see what OWL-Direct
inferred (not a fixpoint over all regimes).
"""

from __future__ import annotations

import shutil

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT, StarLayerGraph
from starlayer.graph.entailment import infer as infer_module
from starlayer.graph.execution import union
from starlayer.shacl import (
    StarShaclProcessor,
    apply_rules,
    evaluate,
    target_nodes,
    validate,
)

try:
    import owlready2  # noqa: F401

    _OWLREADY2 = True
except ImportError:
    _OWLREADY2 = False

pytestmark = pytest.mark.skipif(not _OWLREADY2 or shutil.which("java") is None, reason="OWL-Direct (HermiT) needs owlready2 and a Java runtime")

N = ox.NamedNode
RDF_TYPE = N("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
EX = "http://example.org/"
DIRECT = ENTAILMENT["OWL-Direct"]
OWL_RL = ENTAILMENT["OWL-RDF-Based"]
RDFS = ENTAILMENT.RDFS
PFX = (
    "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
)
# ex:p1 is an ex:Owner only by rdfs:domain (RDFS); ex:q is an ex:Parent only through the equivalent class with a restriction (DL).
DATA = (
    "ex:hasPet rdfs:domain ex:Owner . ex:p1 ex:hasPet ex:rex . "
    "ex:Parent owl:equivalentClass [ a owl:Restriction ; owl:onProperty ex:hasChild ; owl:someValuesFrom ex:Person ] . "
    "ex:hasChild a owl:ObjectProperty . ex:q ex:hasChild ex:c . ex:c a ex:Person . ex:Person a owl:Class ."
)
SHAPES = (
    "ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ; sh:property [ sh:path ex:name ; sh:minCount 1 ] . "
    "ex:ParentShape a sh:NodeShape ; sh:targetClass ex:Parent ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
)


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def data() -> StarLayerGraph:
    return g(DATA)


def shapes(extra: str = "") -> StarLayerGraph:
    return g(SHAPES + extra)


def focus(report) -> set[str]:
    return {o.value for o in report.report_graph.objects(None, N("http://www.w3.org/ns/shacl#focusNode"))}


@pytest.fixture
def closures(monkeypatch):
    calls: list = []
    real = infer_module._delta_for

    def counting(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(infer_module, "_delta_for", counting)
    return calls


def entries(graph) -> dict:
    cache = union.version_of(graph.store).entailed
    return {} if cache is None else dict(cache.entries)


# (1) the processor's OWL-Direct plus the shapes graph's sh:entailment
def test_processor_owl_direct_plus_declared_rdfs():
    declared = shapes(f" ex:Decl sh:entailment <{RDFS.value}> .")
    assert focus(validate(data(), declared, inference=DIRECT)) == {EX + "p1", EX + "q"}


def test_each_single_regime_finds_only_its_own_target():
    only_dl = focus(validate(data(), shapes(), inference=DIRECT))
    only_rdfs = focus(validate(data(), shapes(), inference=RDFS))
    assert EX + "q" in only_dl and EX + "q" not in only_rdfs
    assert EX + "p1" in only_rdfs


def test_declared_owl_direct_plus_processor_rdfs():
    declared = shapes(f" ex:Decl sh:entailment <{DIRECT.value}> .")
    assert focus(validate(data(), declared, inference=RDFS)) == {EX + "p1", EX + "q"}
    assert focus(StarShaclProcessor(declared, inference=RDFS).validate(data())) == {EX + "p1", EX + "q"}


# (2) sets by inference=
@pytest.mark.parametrize(
    "regimes",
    [{DIRECT, OWL_RL}, {DIRECT, RDFS}, {DIRECT, RDFS, ENTAILMENT.RDF}, [DIRECT, RDFS, OWL_RL]],
)
def test_combined_sets_by_inference(regimes):
    assert focus(validate(data(), shapes(), inference=regimes)) == {EX + "p1", EX + "q"}


# (3) the cache
def test_the_combined_set_is_one_entry_computed_once(closures):
    d, s = data(), shapes()
    validate(d, s, inference={DIRECT, RDFS})
    validate(d, s, inference={RDFS, DIRECT})
    assert closures == [frozenset({DIRECT.value, RDFS.value})]
    assert len(entries(d)) == 1


def test_a_different_combination_is_a_separate_entry(closures):
    d, s = data(), shapes()
    validate(d, s, inference={DIRECT, RDFS})
    validate(d, s, inference={DIRECT, OWL_RL})
    validate(d, s, inference=DIRECT)
    assert len(closures) == 3 and len(entries(d)) == 3


# (4) a superset of each single regime's entailments
@pytest.mark.parametrize("other", [RDFS, OWL_RL])
def test_the_copy_holds_the_entailments_of_every_regime(other):
    from starlayer.graph.entailment.cache import entailed_store_view

    d = data()

    def triples(*regimes) -> set:
        return set(entailed_store_view(d, regimes).triples((None, None, None)))

    both, direct, single = triples(DIRECT, other), triples(DIRECT), triples(other)
    assert direct <= both and single <= both
    assert both > direct and both > single or both >= direct | single
    assert both >= set(d.triples((None, None, None)))


def test_the_delta_has_no_input_triple_and_no_duplicate():
    d = data()
    delta = infer_module._delta_for(d, frozenset({DIRECT.value, RDFS.value}), "hermit", 120)
    assert isinstance(delta, set) and not delta & set(d.triples((None, None, None)))
    assert delta >= infer_module._delta_for(d, frozenset({DIRECT.value}), "hermit", 120)
    assert delta >= infer_module._delta_for(d, frozenset({RDFS.value}), "hermit", 120)


# (5) engine and timeout need OWL-Direct in the set
def test_engine_and_timeout_are_rejected_without_owl_direct():
    d, s = data(), shapes()
    with pytest.raises(ValueError, match="only meaningful"):
        validate(d, s, inference={RDFS, OWL_RL}, engine="rustdl")
    with pytest.raises(ValueError, match="only meaningful"):
        validate(d, s, inference={RDFS, OWL_RL}, timeout=5)


def test_engine_and_timeout_are_accepted_with_owl_direct_in_a_set():
    assert focus(validate(data(), shapes(), inference={DIRECT, RDFS}, engine="hermit", timeout=120)) == {EX + "p1", EX + "q"}


def test_an_unknown_engine_is_a_value_error_in_a_set():
    with pytest.raises(ValueError, match="engine"):
        validate(data(), shapes(), inference={DIRECT, RDFS}, engine="pellet")


# (6) infer() keeps rejecting the combination (starlayer-reasoning pins it)
def test_infer_still_rejects_the_combination():
    with pytest.raises(ValueError, match="Unsupported entailment regime combination"):
        data().infer(entailment={DIRECT, RDFS})


# (7) the other entry points
def test_evaluate_target_nodes_and_apply_rules_accept_the_combination():
    d, s = data(), shapes()
    inference = {DIRECT, RDFS}
    assert evaluate(d, s, inference=inference) is not None
    nodes = target_nodes(data_graph=d, shacl_graph=s, shape_node=N(EX + "ParentShape"), inference=inference)
    assert {n.value if hasattr(n, "value") else str(n) for n in nodes} == {EX + "q"}
    nodes = target_nodes(data_graph=d, shacl_graph=s, shape_node=N(EX + "OwnerShape"), inference=inference)
    assert {n.value if hasattr(n, "value") else str(n) for n in nodes} == {EX + "p1"}
    assert apply_rules(d, s, inference=inference) is not None
