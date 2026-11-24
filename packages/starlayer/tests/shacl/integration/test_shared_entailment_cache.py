"""One entailed copy per store, shared by SPARQL query-time entailment and SHACL validation (``graph/entailment/cache.py``).

RDF and RDFS are the query rewrite in SPARQL and a copy in SHACL (SHACL reads through triple lookups); the OWL regimes are the same copy
in both, so running a regime in one and then in the other does not run the closure again. The cache is invalidated by the write count
of the store only.
"""

from __future__ import annotations

import shutil

import pyoxigraph as ox
import pytest
from starlayer.graph import ENTAILMENT, StarLayerDataset, StarLayerGraph
from starlayer.graph.entailment import cache as cache_module
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
try:
    import rustdl  # noqa: F401

    _RUSTDL = True
except ImportError:
    _RUSTDL = False

direct_needs = pytest.mark.skipif(not _OWLREADY2 or shutil.which("java") is None, reason="OWL-Direct (HermiT) needs owlready2 and a Java runtime")
rustdl_needs = pytest.mark.skipif(not _RUSTDL, reason="rustdl not importable")

EX = "http://example.org/"
N = ox.NamedNode
RDF_TYPE = N("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
SUBCLASS = N("http://www.w3.org/2000/01/rdf-schema#subClassOf")
OWL_RL = ENTAILMENT["OWL-RDF-Based"]
DIRECT = ENTAILMENT["OWL-Direct"]
PFX = "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
SHAPES = PFX + "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
QUERY = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }"


def g(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def data() -> StarLayerGraph:
    return g("ex:Employee rdfs:subClassOf ex:Person . ex:a a ex:Employee . ex:b a ex:Employee .")


def shapes() -> StarLayerGraph:
    return g(SHAPES[len(PFX):])


def violations(report) -> int:
    return len(list(report.report_graph.subjects(RDF_TYPE, N("http://www.w3.org/ns/shacl#ValidationResult"))))


@pytest.fixture
def closures(monkeypatch):
    """The regime sets the closure function ran for, in order."""
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


# ---- one copy for both ---------------------------------------------------------------------------------------------------------
def test_a_sparql_owl_query_then_shacl_builds_one_copy(closures):
    d, s = data(), shapes()
    assert len(list(d.query(QUERY, entailment=OWL_RL))) == 2
    assert violations(validate(d, s, inference=OWL_RL)) == 2
    assert len(closures) == 1 and len(entries(d)) == 1


def test_shacl_then_a_sparql_owl_query_builds_one_copy(closures):
    d, s = data(), shapes()
    assert violations(validate(d, s, inference=OWL_RL)) == 2
    assert len(list(d.query(QUERY, entailment=OWL_RL))) == 2
    assert len(closures) == 1 and len(entries(d)) == 1


def test_sh_entailment_in_the_shapes_graph_is_the_same_entry_as_inference(closures):
    d = data()
    declared = g(SHAPES[len(PFX):] + f" ex:S2 sh:entailment <{OWL_RL.value}> .")
    validate(d, declared)
    validate(d, shapes(), inference=OWL_RL)
    list(d.query(QUERY, entailment=OWL_RL))
    assert len(closures) == 1


def test_rdfs_is_the_rewrite_in_sparql_and_a_copy_in_shacl(closures):
    d, s = data(), shapes()
    assert len(list(d.query(QUERY, entailment=ENTAILMENT.RDFS))) == 2
    assert closures == [] and not entries(d)  # the rewrite: no copy, no closure
    assert violations(validate(d, s, inference=ENTAILMENT.RDFS)) == 2
    assert len(closures) == 1 and len(entries(d)) == 1


def test_a_sparql_rdfs_query_after_a_shacl_rdfs_validation_neither_builds_nor_reads_a_copy(closures, monkeypatch):
    d, s = data(), shapes()
    assert violations(validate(d, s, inference=ENTAILMENT.RDFS)) == 2
    assert len(closures) == 1
    def forbidden(*a, **kw):
        raise AssertionError("SPARQL RDFS must use the rewrite, not the shared copy")
    monkeypatch.setattr(cache_module, "entailed_store_view", forbidden)
    assert len(list(d.query(QUERY, entailment=ENTAILMENT.RDFS))) == 2
    assert len(list(d.query(QUERY, entailment=ENTAILMENT.RDF))) == 0
    assert len(closures) == 1


def test_a_larger_regime_is_never_used_for_a_smaller_one(closures):
    d, s = data(), shapes()
    validate(d, s, inference=[ENTAILMENT.RDFS, OWL_RL])
    validate(d, s, inference=OWL_RL)
    validate(d, s, inference=ENTAILMENT.RDFS)
    assert len(closures) == 3 and len(entries(d)) == 3


# ---- invalidation by the write count ------------------------------------------------------------------------------------------
def test_the_stamp_does_not_move_across_validations_and_queries():
    d, s = data(), shapes()
    stamp = union.version_of(d.store).stamp()
    validate(d, s, inference=OWL_RL)
    validate(d, s, inference=ENTAILMENT.RDFS)
    list(d.query(QUERY, entailment=OWL_RL))
    assert union.version_of(d.store).stamp() == stamp


def test_a_write_invalidates_both_routes(closures):
    d, s = data(), shapes()
    validate(d, s, inference=OWL_RL)
    list(d.query(QUERY, entailment=OWL_RL))
    assert len(closures) == 1
    d.add((N(EX + "c"), RDF_TYPE, N(EX + "Employee")))
    assert violations(validate(d, s, inference=OWL_RL)) == 3
    assert len(closures) == 2
    assert len(list(d.query(QUERY, entailment=OWL_RL))) == 3  # the copy SHACL made after the write
    assert len(closures) == 2


def test_a_raw_store_write_is_seen_after_touch_only(closures):
    d, s = data(), shapes()
    validate(d, s, inference=OWL_RL)
    d.store.add(ox.Quad(N(EX + "c"), RDF_TYPE, N(EX + "Employee"), ox.DefaultGraph()))
    assert violations(validate(d, s, inference=OWL_RL)) == 2 and len(closures) == 1  # not noticed
    union.touch(d.store)
    assert violations(validate(d, s, inference=OWL_RL)) == 3 and len(closures) == 2


def test_inplace_write_back_invalidates(closures):
    d, s = data(), shapes()
    validate(d, s, inference=ENTAILMENT.RDFS, inplace=True)
    assert (N(EX + "a"), RDF_TYPE, N(EX + "Person")) in d  # written to the data: the write count moved
    validate(d, s, inference=ENTAILMENT.RDFS)
    assert len(closures) == 2


def test_the_report_graph_does_not_invalidate(closures):
    d, s = data(), shapes()
    for _ in range(3):
        validate(d, s, inference=ENTAILMENT.RDFS)
    assert len(closures) == 1


# ---- regime overrides, the processor ----------------------------------------------------------------------------------------
def test_alternating_regimes_compute_each_closure_once(closures):
    d = data()
    p = StarShaclProcessor(shapes(), inference=ENTAILMENT.RDFS)
    for _ in range(3):
        assert violations(p.validate(d)) == 2
        assert violations(p.validate(d, inference=OWL_RL)) == 2
        p.validate(d, inference=None)  # no regime of its own: no entry (class targets read rdfs:subClassOf from the data anyway)
    assert len(closures) == 2 and len(entries(d)) == 2


def test_clear_entailment_cache_clears_what_shacl_used(closures):
    d, s = data(), shapes()
    validate(d, s, inference=OWL_RL)
    d.clear_entailment_cache()
    assert not entries(d)
    validate(d, s, inference=OWL_RL)
    assert len(closures) == 2


def test_clear_entailment_cache_clears_it_for_every_wrapper_of_the_store(closures):
    d = data()
    other = StarLayerGraph(d.as_store())
    validate(d, shapes(), inference=OWL_RL)
    other.clear_entailment_cache()
    assert not entries(d)


# ---- recompute ------------------------------------------------------------------------------------------------------------------
def test_recompute_never_uses_what_is_kept_even_after_a_write(closures):
    d, s = data(), shapes()
    validate(d, s, inference=OWL_RL)
    d.add((N(EX + "c"), RDF_TYPE, N(EX + "Employee")))
    assert violations(validate(d, s, inference=OWL_RL, recompute="never")) == 2  # out of date, as asked
    assert len(closures) == 1
    assert violations(validate(d, s, inference=OWL_RL)) == 3  # onChange: made again


def test_recompute_never_computes_when_nothing_is_kept(closures):
    d, s = data(), shapes()
    assert violations(validate(d, s, inference=OWL_RL, recompute="never")) == 2
    assert len(closures) == 1


def test_recompute_always_computes_every_time_and_keeps_none(closures):
    d, s = data(), shapes()
    validate(d, s, inference=OWL_RL)
    assert len(entries(d)) == 1
    validate(d, s, inference=OWL_RL, recompute="always")
    assert len(closures) == 2 and not entries(d)  # what was kept is dropped
    validate(d, s, inference=OWL_RL, recompute="always")
    assert len(closures) == 3


def test_recompute_is_bound_on_the_processor_and_a_call_overrides_it(closures):
    d = data()
    p = StarShaclProcessor(shapes(), inference=OWL_RL, recompute="always")
    p.validate(d)
    p.validate(d)
    assert len(closures) == 2
    p.validate(d, recompute="onChange")
    p.validate(d, recompute="onChange")
    assert len(closures) == 3


def test_a_bad_recompute_is_a_value_error():
    with pytest.raises(ValueError, match="recompute"):
        validate(data(), shapes(), inference=OWL_RL, recompute="sometimes")


@pytest.mark.parametrize("entry", ["evaluate", "target_nodes"])
def test_recompute_reaches_evaluate_and_target_nodes(closures, entry):
    d, s = data(), shapes()
    node = N(EX + "S")

    def call(**kw):
        if entry == "evaluate":
            return evaluate(d, s, inference=OWL_RL, **kw)
        return target_nodes(data_graph=d, shacl_graph=s, shape_node=node, inference=OWL_RL, **kw)

    call()
    call(recompute="always")
    assert len(closures) == 2
    p = StarShaclProcessor(s, inference=OWL_RL, recompute="always")
    n = len(closures)
    for _ in range(2):
        p.evaluate(d) if entry == "evaluate" else p.target_nodes(data_graph=d, shape_node=node)
    assert len(closures) == n + 2


# ---- the ontology graph is part of the key ----------------------------------------------------------------------------------
def test_the_ontology_graph_is_part_of_the_key_and_a_change_to_it_invalidates(closures):
    d, s = data(), shapes()
    ont = g("ex:Person rdfs:subClassOf ex:Agent .")
    shape_agent = g("ex:SA a sh:NodeShape ; sh:targetClass ex:Agent ; sh:property [ sh:path ex:name ; sh:minCount 1 ] .")
    assert violations(validate(d, shape_agent, ont, inference=OWL_RL)) == 2
    assert violations(validate(d, shape_agent, None, inference=OWL_RL)) == 0
    assert len(closures) == 2
    validate(d, shape_agent, ont, inference=OWL_RL)
    assert len(closures) == 2
    ont.add((N(EX + "Agent"), SUBCLASS, N(EX + "Thing")))
    validate(d, shape_agent, ont, inference=OWL_RL)
    assert len(closures) == 3
    list(d.query(QUERY, entailment=OWL_RL))  # SPARQL has no ontology graph: it finds the entry SHACL made without one
    assert len(closures) == 3
    del s


# ---- datasets ---------------------------------------------------------------------------------------------------------------
def test_a_dataset_that_is_not_a_union_is_wrapped_anew_per_call_and_still_hits(closures):
    ds = StarLayerDataset(default_union=False)
    ds.parse(data=PFX + "ex:Employee rdfs:subClassOf ex:Person . ex:a a ex:Employee .", format="turtle")
    s = shapes()
    for _ in range(3):
        assert violations(validate(ds, s, inference=OWL_RL)) == 1
    assert len(closures) == 1


def test_a_dataset_union_copy_is_the_one_sparql_uses(closures):
    ds = StarLayerDataset(default_union=True)
    ds.parse(data=PFX + "ex:Employee rdfs:subClassOf ex:Person . ex:a a ex:Employee .", format="turtle")
    assert violations(validate(ds, shapes(), inference=OWL_RL)) == 1
    n = len(closures)
    assert len(list(ds.query(QUERY, entailment=OWL_RL))) == 1
    assert len(closures) == n


# ---- rules never write into the cached copy ---------------------------------------------------------------------------------
RULES = (
    PFX
    + """@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> .
ex:Rule a sh:TripleRule ; sh:subject [ shnex:var "focusNode" ] ; sh:predicate ex:flag ; sh:object ex:yes .
ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:Rule ; sh:property [ sh:path ex:flag ; sh:hasValue ex:yes ] .
"""
)


def test_rules_do_not_write_into_the_cached_copy(closures):
    d = data()
    s = StarLayerGraph()
    s.parse(data=RULES, format="turtle")
    validate(d, s, inference=ENTAILMENT.RDFS)  # make the entry
    (entry,) = entries(d).values()
    before = len(entry.copy)
    first = apply_rules(d, s, inference=ENTAILMENT.RDFS)
    second = apply_rules(d, s, inference=ENTAILMENT.RDFS)
    assert len(first.inferred_graph) == len(second.inferred_graph) > 0  # the second sees no leakage of the first
    assert len(entry.copy) == before
    assert not any(entry.copy.triples((None, N(EX + "flag"), None)))
    assert len(entries(d)) == 1 and list(entries(d).values())[0].copy is entry.copy  # the entry from before the rules is still the one kept


def test_validate_with_rules_leaves_the_cached_copy_alone(closures):
    d = data()
    s = StarLayerGraph()
    s.parse(data=RULES, format="turtle")
    report = validate(d, s, inference=ENTAILMENT.RDFS, rules=True)
    assert report.conforms
    (entry,) = entries(d).values()
    assert not any(entry.copy.triples((None, N(EX + "flag"), None)))
    assert not any(d.triples((None, N(EX + "flag"), None)))


# ---- OWL-Direct --------------------------------------------------------------------------------------------------------------
def test_engine_and_timeout_are_rejected_for_other_regimes():
    d, s = data(), shapes()
    for regime in (ENTAILMENT.RDFS, OWL_RL):
        with pytest.raises(ValueError, match="only meaningful"):
            validate(d, s, inference=regime, engine="rustdl")
        with pytest.raises(ValueError, match="only meaningful"):
            validate(d, s, inference=regime, timeout=5)
    with pytest.raises(ValueError, match="only meaningful"):
        StarShaclProcessor(s, inference=OWL_RL, timeout=5).validate(d)


def test_an_unknown_engine_is_a_value_error_for_owl_direct():
    with pytest.raises(ValueError, match="engine"):
        validate(data(), shapes(), inference=DIRECT, engine="pellet")


@direct_needs
def test_owl_direct_through_shacl_and_the_copy_is_shared_with_sparql(closures):
    d, s = data(), shapes()
    assert violations(validate(d, s, inference=DIRECT)) == 2
    assert len(list(d.query(QUERY, entailment=DIRECT))) == 2
    assert len(closures) == 1
    assert violations(validate(d, s, inference=DIRECT)) == 2 and len(closures) == 1


@direct_needs
def test_a_declared_owl_direct_in_the_shapes_graph_is_supported():
    """It used to pass ``declared_regimes`` and fail later in ``normalise_regimes``."""
    declared = g(SHAPES[len(PFX):] + f" ex:Decl sh:entailment <{DIRECT.value}> .")
    assert violations(validate(data(), declared)) == 2


@direct_needs
def test_owl_direct_timeout_propagates():
    from starlayer_reasoning._timeout import ReasoningTimeoutError

    with pytest.raises(ReasoningTimeoutError):
        validate(data(), shapes(), inference=DIRECT, timeout=0.001)


@direct_needs
def test_owl_direct_inconsistency_propagates():
    from starlayer_reasoning.owl_dl import InconsistentOntologyError

    bad = g("ex:x a ex:A , ex:B .")
    bad.parse(data="@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ex: <http://example.org/> . ex:A owl:disjointWith ex:B .", format="turtle")
    with pytest.raises(InconsistentOntologyError):
        validate(bad, shapes(), inference=DIRECT)


@direct_needs
@rustdl_needs
def test_each_owl_direct_engine_has_its_own_entry(closures):
    d, s = data(), shapes()
    validate(d, s, inference=DIRECT, engine="hermit")
    validate(d, s, inference=DIRECT, engine="rustdl")
    validate(d, s, inference=DIRECT, engine="hermit")
    assert len(closures) == 2 and len(entries(d)) == 2


def test_the_cache_holds_at_most_four_entries_per_store():
    d, s = data(), shapes()
    for regimes in ([ENTAILMENT.RDF], [ENTAILMENT.RDFS], [OWL_RL], [ENTAILMENT.RDF, ENTAILMENT.RDFS], [ENTAILMENT.RDFS, OWL_RL]):
        validate(d, s, inference=regimes)
    assert len(entries(d)) == cache_module.MAX_ENTRIES
